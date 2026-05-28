"""Apply the draft model to a finished (past) match — THE CORE of Slice 3.

This module is intentionally PURE (no I/O, no network): it takes a match-v5
detail payload (as returned by :meth:`app.riot_client.RiotClient.get_match_detail`)
plus the target player's ``puuid`` and produces the per-game prediction object
the ``GET /riot/match/{matchId}/prediction`` route returns.

Pipeline (one match -> one prediction):

1. :func:`app.draft_reconstruction.reconstruct_draft` turns the 10 Riot
   participants into the 10 ``blue_top .. red_support`` champion DISPLAY names
   (plus ``fallback_used`` + ``warnings``).
2. :func:`app.main.predict_draft_from_names` (the extracted draft-prediction
   core) runs the SAME model the ``POST /predict/draft`` route uses, returning a
   :class:`app.main.PredictionResponse`.
3. The ACTUAL result is read straight from the detail: ``winner_side`` (which
   side really won) and ``player_won`` (did the target player's team win).

The route layer maps :class:`app.draft_reconstruction.DraftReconstructionError`
(non-Summoner's-Rift game, or a side without exactly 5 resolvable champions) to
HTTP 422 — a clear, visible error rather than a misleading prediction.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.draft_reconstruction import DraftReconstructionError, reconstruct_draft

# The 10 draft slots, in display order (blue then red, canonical role order).
# Shared with the response shape so callers iterate one source of truth.
DRAFT_SLOTS = (
    "blue_top",
    "blue_jungle",
    "blue_mid",
    "blue_adc",
    "blue_support",
    "red_top",
    "red_jungle",
    "red_mid",
    "red_adc",
    "red_support",
)

# Riot teamId -> the side label the prediction core / response uses.
_TEAM_ID_TO_SIDE = {100: "Blue Team", 200: "Red Team"}

# Summoner's Rift 5v5 queues the draft model is trained on. Spectator-v5 carries
# the queue as ``gameQueueConfigId``; anything outside this set is rejected as
# "unsupported" (-> 422) before we even try to reconstruct a 5v5 draft.
_SR_5V5_QUEUES = frozenset({400, 420, 430, 440})


def _as_bool(value: Any) -> Optional[bool]:
    """Coerce a Riot ``win`` flag to a real bool, or ``None`` when absent."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return bool(value)


def _winning_side(match_detail: Dict[str, Any]) -> Optional[str]:
    """Resolve which side actually won ("Blue Team" / "Red Team").

    Prefers the authoritative team-level ``info.teams[].win`` flag; falls back
    to any participant's ``win`` keyed by ``teamId`` when ``teams`` is missing
    or ambiguous. Returns ``None`` if the winner cannot be determined.
    """
    info = match_detail.get("info") or {}

    for team in info.get("teams") or []:
        if not isinstance(team, dict):
            continue
        if _as_bool(team.get("win")) is True:
            side = _TEAM_ID_TO_SIDE.get(team.get("teamId"))
            if side is not None:
                return side

    # Fallback: derive from a winning participant's teamId.
    for p in info.get("participants") or []:
        if isinstance(p, dict) and _as_bool(p.get("win")) is True:
            side = _TEAM_ID_TO_SIDE.get(p.get("teamId"))
            if side is not None:
                return side

    return None


def _player_won(match_detail: Dict[str, Any], puuid: str) -> Optional[bool]:
    """Return whether the target ``puuid``'s team won, or ``None`` if absent."""
    info = match_detail.get("info") or {}
    for p in info.get("participants") or []:
        if isinstance(p, dict) and p.get("puuid") == puuid:
            return _as_bool(p.get("win"))
    return None


def build_match_prediction(match_detail: Dict[str, Any], puuid: str) -> Dict[str, Any]:
    """Predict a finished match's outcome and compare it to what really happened.

    Parameters
    ----------
    match_detail:
        A full match-v5 detail payload (``metadata`` + ``info`` with
        ``participants`` / ``teams``).
    puuid:
        The target player's globally-unique id. Used only to surface whether
        *that* player's team won (``actual.player_won``); the prediction itself
        is side-based and player-agnostic.

    Returns
    -------
    dict
        ``{match_id, draft, predicted, actual:{winner_side, player_won},
        fallback_used, warnings}`` where:

        * ``draft`` — the 10 ``blue_top .. red_support`` champion display names.
        * ``predicted`` — a :class:`app.main.PredictionResponse` (the model's
          favoured side + blue/red win probabilities + confidence).
        * ``actual.winner_side`` — "Blue Team" / "Red Team" (or ``None`` if the
          detail does not record a winner).
        * ``actual.player_won`` — the target player's team result (or ``None``).
        * ``fallback_used`` / ``warnings`` — propagated from reconstruction so
          the UI can flag approximate lane assignment.

    Raises
    ------
    app.draft_reconstruction.DraftReconstructionError
        If the participants cannot be mapped to a valid 10-slot draft (e.g. a
        non-SR game whose teams are not 5v5, or an unknown champion). The route
        maps this to HTTP 422.
    """
    info = match_detail.get("info") or {}
    participants: List[Dict[str, Any]] = info.get("participants") or []
    if not participants:
        raise DraftReconstructionError(
            "Match detail has no participants; cannot reconstruct a draft."
        )

    # 1) Reconstruct the 10-name draft (propagates DraftReconstructionError).
    reconstructed = reconstruct_draft(participants)
    fallback_used = bool(reconstructed.get("fallback_used"))
    warnings = list(reconstructed.get("warnings") or [])
    draft = {slot: reconstructed[slot] for slot in DRAFT_SLOTS}

    # 2) Run the SAME draft-prediction core the /predict/draft route uses.
    #    Imported lazily to avoid a circular import at module load (main.py
    #    imports app modules; this module is imported by main.py's route).
    from app.main import predict_draft_from_names

    predicted = predict_draft_from_names(draft)

    # 3) Read the ACTUAL result straight from the detail.
    metadata = match_detail.get("metadata") or {}
    match_id = metadata.get("matchId")
    if not match_id:
        game_id = info.get("gameId")
        match_id = str(game_id) if game_id is not None else ""

    return {
        "match_id": str(match_id),
        "draft": draft,
        "predicted": predicted,
        "actual": {
            "winner_side": _winning_side(match_detail),
            "player_won": _player_won(match_detail, puuid),
        },
        "fallback_used": fallback_used,
        "warnings": warnings,
    }


def build_live_prediction(
    current_game_info: Dict[str, Any], puuid: str
) -> Dict[str, Any]:
    """Predict a LIVE (in-progress) game's outcome — the Slice 4 CORE.

    Like :func:`build_match_prediction` but for a spectator-v5
    ``CurrentGameInfo`` payload: the game is still being played, so there is NO
    actual result to compare against. Spectator-v5 also carries **no per-player
    lane/role field at all**, so reconstruction always lands on the documented
    participant-order fallback and ``fallback_used`` is expected to be ``True``.

    Parameters
    ----------
    current_game_info:
        A spectator-v5 ``CurrentGameInfo`` payload with ``gameId``,
        ``gameQueueConfigId`` and ``participants`` (each with ``championId`` and
        ``teamId``; positions absent).
    puuid:
        The target player's id. Accepted for symmetry with
        :func:`build_match_prediction` and so callers / tests can scope the
        request to a specific player; the prediction itself is side-based and
        player-agnostic, and live games have no ``player_won`` yet.

    Returns
    -------
    dict
        ``{game_id, queue_id, draft, predicted, fallback_used, warnings}`` —
        deliberately WITHOUT an ``actual`` key (the game is in progress):

        * ``draft`` — the 10 ``blue_top .. red_support`` champion display names.
        * ``predicted`` — a :class:`app.main.PredictionResponse` from the SAME
          draft model the ``POST /predict/draft`` route uses.
        * ``fallback_used`` — expected ``True`` for spectator data (no roles).
        * ``warnings`` — propagated from reconstruction.

    Raises
    ------
    app.draft_reconstruction.DraftReconstructionError
        If the game is not a Summoner's Rift 5v5 queue, a side does not have
        exactly 5 participants, or a ``championId`` cannot be mapped. The route
        maps this to HTTP 422.
    """
    if not isinstance(current_game_info, dict):
        raise DraftReconstructionError(
            "Live game payload is not an object; cannot reconstruct a draft."
        )

    participants: List[Dict[str, Any]] = (
        current_game_info.get("participants") or []
    )
    if not participants:
        raise DraftReconstructionError(
            "Live game has no participants; cannot reconstruct a draft."
        )

    # Reject non-SR-5v5 queues up front (e.g. ARAM 450) — the draft model is only
    # trained on SR 5v5, so this is a clear "unsupported" 422 rather than a
    # misleading prediction. queueId absent -> let reconstruction decide (a real
    # 5v5 still works; a non-5v5 fails the team-size check below).
    queue_id = current_game_info.get("gameQueueConfigId")
    if queue_id is not None and int(queue_id) not in _SR_5V5_QUEUES:
        raise DraftReconstructionError(
            f"Live game queue {queue_id} is not a Summoner's Rift 5v5 queue; "
            "the draft model can only analyze SR 5v5 games."
        )

    # 1) Reconstruct the 10-name draft. Spectator participants have no
    #    teamPosition, so this always uses the participant-order fallback.
    reconstructed = reconstruct_draft(participants)
    fallback_used = bool(reconstructed.get("fallback_used"))
    warnings = list(reconstructed.get("warnings") or [])
    draft = {slot: reconstructed[slot] for slot in DRAFT_SLOTS}

    # 2) Run the SAME draft-prediction core the /predict/draft route uses.
    from app.main import predict_draft_from_names

    predicted = predict_draft_from_names(draft)

    game_id = current_game_info.get("gameId")

    return {
        "game_id": str(game_id) if game_id is not None else "",
        "queue_id": int(queue_id) if queue_id is not None else None,
        "draft": draft,
        "predicted": predicted,
        "fallback_used": fallback_used,
        "warnings": warnings,
    }
