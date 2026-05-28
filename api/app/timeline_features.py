"""Reconstruct timeline-model features from a match-v5 timeline + detail.

This module is PURE (no I/O, no network): it takes a match-v5 detail payload
(for the per-role mapping + the actual result) plus the match-v5 timeline
payload, and reconstructs the game state the ``at{minute}`` win-prob models
consume at minutes 5/10/15/20.

Two payloads, two jobs:

* the **detail** (``info.participants[]``) carries ``participantId`` +
  ``teamId`` + ``teamPosition``, which is the only place the per-role mapping
  lives (the timeline frames carry no role) — so we read roles from the detail;
* the **timeline** (``info.frames[]`` at 60000ms intervals, so ``frames[i]`` is
  the state at minute ``i``) carries ``participantFrames["1".."10"].totalGold``
  and the ``events[]`` we scan for the objective flags.

Participant ids 1–5 are team 100 (blue) and 6–10 are team 200 (red), matching
the detail's ``info.participants[].participantId``.

The timeline-model feature contract (see ``app.main.predict_at_minute``):

* ``gold_diff_at_{minute}``            — blue total gold − red total gold;
* ``{role}_gold_diff_at_{minute}``     — per-role blue−red gold (top/jungle/
  mid/adc/support);
* ``first_blood_team_100`` /
  ``first_tower_team_100`` /
  ``first_dragon_team_100`` /
  ``first_herald_team_100``            — 1 iff BLUE (team 100) secured that
  objective by the cutoff ``minute*60000``, else 0 (also 0 when neither team
  has it yet).

The route layer turns "no usable frames / too short / non-SR" into a clean HTTP
422 rather than a misleading progression.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Minutes the timeline models are trained for. Frame index == minute (frames are
# sampled at 60000ms), so we read ``frames[minute]`` for each.
TIMELINE_MINUTES = (5, 10, 15, 20)

# One frame per minute (Riot samples participantFrames at this interval).
_FRAME_INTERVAL_MS = 60000

# Riot teamPosition (match-v5) -> timeline-model role slot. Same mapping as
# app.draft_reconstruction (adc<-BOTTOM, support<-UTILITY).
_TEAM_POSITION_TO_ROLE = {
    "TOP": "top",
    "JUNGLE": "jungle",
    "MIDDLE": "mid",
    "BOTTOM": "adc",
    "UTILITY": "support",
}

_ROLES = ("top", "jungle", "mid", "adc", "support")

# Riot teamId -> the side label the prediction response uses.
_TEAM_ID_TO_SIDE = {100: "Blue Team", 200: "Red Team"}


class TimelineReconstructionError(ValueError):
    """Raised when a usable timeline progression cannot be reconstructed.

    The route maps this to HTTP 422 (e.g. the timeline has no frames, or the
    game is shorter than 5 minutes so not even the first checkpoint exists).
    """


def _as_bool(value: Any) -> Optional[bool]:
    """Coerce a Riot ``win`` flag to a real bool, or ``None`` when absent."""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return bool(value)


def _team_of_participant_id(participant_id: Any) -> Optional[int]:
    """Map a timeline participantId (1..10) to its teamId (100 / 200).

    1–5 -> 100 (blue), 6–10 -> 200 (red). Returns ``None`` for an out-of-range
    or non-integer id so callers can ignore stray ids rather than mislabel them.
    """
    try:
        pid = int(participant_id)
    except (TypeError, ValueError):
        return None
    if 1 <= pid <= 5:
        return 100
    if 6 <= pid <= 10:
        return 200
    return None


def _frames(timeline: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the timeline frames list (``info.frames``), or an empty list."""
    info = (timeline or {}).get("info") or {}
    frames = info.get("frames")
    return frames if isinstance(frames, list) else []


def available_minutes(timeline: Dict[str, Any]) -> List[int]:
    """Return the subset of [5,10,15,20] for which a frame exists.

    A game of N minutes has ``frames[0..N]``, so the checkpoint at minute M is
    only meaningful when ``len(frames) > M`` (we need ``frames[M]``). A 16-min
    game therefore yields [5, 10, 15] and skips 20; a <5-min game yields [].
    """
    n = len(_frames(timeline))
    return [m for m in TIMELINE_MINUTES if n > m]


def _role_participant_ids(match_detail: Dict[str, Any]) -> Dict[int, Dict[str, int]]:
    """Map each team's role -> the participant's timeline id (1..10).

    Reads ``info.participants[]`` from the DETAIL (the only place roles live),
    keyed by ``participantId`` + ``teamId`` + ``teamPosition``. A role that
    cannot be mapped on a team (empty / UNKNOWN / duplicated teamPosition) is
    simply absent for that team, and the caller sets that role's gold diff to 0.

    Returns ``{100: {role: participant_id, ...}, 200: {...}}``.
    """
    by_team: Dict[int, Dict[str, int]] = {100: {}, 200: {}}
    info = (match_detail or {}).get("info") or {}
    for p in info.get("participants") or []:
        if not isinstance(p, dict):
            continue
        team_id = p.get("teamId")
        if team_id not in by_team:
            continue
        pid = p.get("participantId")
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        pos = str(p.get("teamPosition") or p.get("individualPosition") or "").upper()
        role = _TEAM_POSITION_TO_ROLE.get(pos)
        # First writer wins on a duplicate role (keeps reconstruction stable);
        # the loser stays unmapped and that role's diff falls back to 0.
        if role is not None and role not in by_team[team_id]:
            by_team[team_id][role] = pid
    return by_team


def _total_gold(participant_frames: Dict[str, Any], participant_id: int) -> float:
    """Read one participant's ``totalGold`` from a frame's participantFrames.

    Participant frames are keyed by the participantId as a STRING ("1".."10").
    A missing id / field degrades to 0.0 (so a partial frame never crashes the
    reconstruction).
    """
    pf = (participant_frames or {}).get(str(participant_id)) or {}
    try:
        return float(pf.get("totalGold", 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _objective_flags_at(timeline: Dict[str, Any], minute: int) -> Dict[str, int]:
    """Compute the four ``first_*_team_100`` flags as of ``minute*60000`` ms.

    Scans ``events`` across every frame up to the cutoff (events carry their own
    ``timestamp`` so an event recorded in a later frame but still before the
    cutoff is honoured), tracking the FIRST occurrence of each objective:

    * first blood   = first ``CHAMPION_KILL`` (killerId 1–5 -> team 100);
    * first dragon  = first ``ELITE_MONSTER_KILL`` with monsterType DRAGON;
    * first herald  = first ``ELITE_MONSTER_KILL`` with monsterType RIFTHERALD;
      (both prefer ``killerTeamId`` when present, else map ``killerId``);
    * first tower   = first ``BUILDING_KILL`` with buildingType TOWER_BUILDING.
      GOTCHA: the event's ``teamId`` is the team that LOST the tower, so the team
      that GOT first tower is the OTHER side (100 if teamId==200 else 200).

    Each ``first_*_team_100`` is 1 iff the securing team is 100, else 0 (and 0
    when neither team has secured the objective by the cutoff).
    """
    cutoff = minute * _FRAME_INTERVAL_MS
    # securing team (100/200) for each objective, or None if not yet secured.
    secured: Dict[str, Optional[int]] = {
        "blood": None,
        "tower": None,
        "dragon": None,
        "herald": None,
    }

    for frame in _frames(timeline):
        if not isinstance(frame, dict):
            continue
        for event in frame.get("events") or []:
            if not isinstance(event, dict):
                continue
            ts = event.get("timestamp")
            try:
                ts = int(ts)
            except (TypeError, ValueError):
                continue
            if ts > cutoff:
                continue

            etype = event.get("type")

            if etype == "CHAMPION_KILL" and secured["blood"] is None:
                team = _team_of_participant_id(event.get("killerId"))
                if team is not None:
                    secured["blood"] = team

            elif etype == "BUILDING_KILL" and secured["tower"] is None:
                if event.get("buildingType") == "TOWER_BUILDING":
                    # event.teamId is the team that LOST the tower -> the team
                    # that GOT first tower is the opposite side.
                    loser = event.get("teamId")
                    if loser in _TEAM_ID_TO_SIDE:
                        secured["tower"] = 100 if loser == 200 else 200

            elif etype == "ELITE_MONSTER_KILL":
                monster = str(event.get("monsterType") or "").upper()
                killer_team = event.get("killerTeamId")
                if killer_team not in _TEAM_ID_TO_SIDE:
                    killer_team = _team_of_participant_id(event.get("killerId"))
                if killer_team not in _TEAM_ID_TO_SIDE:
                    continue
                if monster == "DRAGON" and secured["dragon"] is None:
                    secured["dragon"] = killer_team
                elif monster == "RIFTHERALD" and secured["herald"] is None:
                    secured["herald"] = killer_team

    return {
        "first_blood_team_100": 1 if secured["blood"] == 100 else 0,
        "first_tower_team_100": 1 if secured["tower"] == 100 else 0,
        "first_dragon_team_100": 1 if secured["dragon"] == 100 else 0,
        "first_herald_team_100": 1 if secured["herald"] == 100 else 0,
    }


def build_timeline_features(
    match_detail: Dict[str, Any], timeline: Dict[str, Any], minute: int
) -> Dict[str, Any]:
    """Reconstruct the ``at{minute}`` feature dict for one checkpoint.

    Parameters
    ----------
    match_detail:
        A match-v5 detail payload — used ONLY for the per-role mapping
        (``info.participants[].participantId / teamId / teamPosition``).
    timeline:
        A match-v5 timeline payload (``info.frames[]`` at 60000ms intervals).
    minute:
        The checkpoint minute (5/10/15/20). ``frames[minute]`` must exist.

    Returns
    -------
    dict
        ``{gold_diff_at_{m}, top_gold_diff_at_{m}, ..., support_gold_diff_at_{m},
        first_blood_team_100, first_tower_team_100, first_dragon_team_100,
        first_herald_team_100}`` — the exact keys the ``at{minute}`` model
        consumes (the model fills any other column with 0).

    Raises
    ------
    TimelineReconstructionError
        If ``frames[minute]`` does not exist (the game was too short for this
        checkpoint). Callers should only pass minutes from
        :func:`available_minutes`.
    """
    frames = _frames(timeline)
    if minute >= len(frames):
        raise TimelineReconstructionError(
            f"Timeline has no frame for minute {minute} "
            f"(only {len(frames)} frames present)."
        )

    frame = frames[minute] or {}
    participant_frames = frame.get("participantFrames") or {}

    # Total gold diff: blue (ids 1–5) − red (ids 6–10).
    blue_gold = sum(_total_gold(participant_frames, pid) for pid in range(1, 6))
    red_gold = sum(_total_gold(participant_frames, pid) for pid in range(6, 11))

    features: Dict[str, Any] = {
        f"gold_diff_at_{minute}": blue_gold - red_gold,
    }

    # Per-role gold diff from the detail's role->participantId mapping. A role
    # unmapped on either side falls back to 0 (documented contract).
    role_ids = _role_participant_ids(match_detail)
    blue_roles = role_ids.get(100, {})
    red_roles = role_ids.get(200, {})
    for role in _ROLES:
        blue_pid = blue_roles.get(role)
        red_pid = red_roles.get(role)
        if blue_pid is None or red_pid is None:
            features[f"{role}_gold_diff_at_{minute}"] = 0
        else:
            features[f"{role}_gold_diff_at_{minute}"] = (
                _total_gold(participant_frames, blue_pid)
                - _total_gold(participant_frames, red_pid)
            )

    # Objective flags as of the cutoff.
    features.update(_objective_flags_at(timeline, minute))
    return features


def _winning_side(match_detail: Dict[str, Any]) -> Optional[str]:
    """Resolve which side actually won ("Blue Team" / "Red Team").

    Prefers ``info.teams[].win``; falls back to a winning participant's
    ``teamId``. Mirrors :func:`app.match_prediction._winning_side` so the actual
    result is read identically across the draft and timeline routes.
    """
    info = (match_detail or {}).get("info") or {}

    for team in info.get("teams") or []:
        if not isinstance(team, dict):
            continue
        if _as_bool(team.get("win")) is True:
            side = _TEAM_ID_TO_SIDE.get(team.get("teamId"))
            if side is not None:
                return side

    for p in info.get("participants") or []:
        if isinstance(p, dict) and _as_bool(p.get("win")) is True:
            side = _TEAM_ID_TO_SIDE.get(p.get("teamId"))
            if side is not None:
                return side

    return None


def _player_won(match_detail: Dict[str, Any], puuid: str) -> Optional[bool]:
    """Return whether the target ``puuid``'s team won, or ``None`` if absent."""
    info = (match_detail or {}).get("info") or {}
    for p in info.get("participants") or []:
        if isinstance(p, dict) and p.get("puuid") == puuid:
            return _as_bool(p.get("win"))
    return None


def build_timeline_prediction(
    match_detail: Dict[str, Any], timeline: Dict[str, Any], puuid: str
) -> Dict[str, Any]:
    """Build the per-minute win-prob progression for a finished match — the CORE.

    For each minute in [5,10,15,20] that has a frame, reconstructs the
    ``at{minute}`` feature dict (:func:`build_timeline_features`) and runs the
    matching ``at{minute}`` model (via :func:`app.main.predict_timeline_at`),
    producing one checkpoint ``{minute, gold_diff, predicted}``. The ACTUAL
    result (``winner_side`` / ``player_won``) is read straight from the detail.

    Parameters
    ----------
    match_detail:
        A match-v5 detail payload (for roles + the actual result).
    timeline:
        A match-v5 timeline payload (``info.frames[]``).
    puuid:
        The target player's id, used only to surface ``actual.player_won``.

    Returns
    -------
    dict
        ``{match_id, game_duration, actual:{winner_side, player_won},
        checkpoints:[{minute, gold_diff, predicted}, ...]}`` where ``predicted``
        is a :class:`app.main.PredictionResponse`. Short games yield fewer
        checkpoints (only the minutes whose frame exists).

    Raises
    ------
    TimelineReconstructionError
        If the timeline has no usable frame for ANY of 5/10/15/20 (e.g. the game
        is shorter than 5 minutes, or the frames list is empty/malformed). The
        route maps this to HTTP 422.
    """
    minutes = available_minutes(timeline)
    if not minutes:
        raise TimelineReconstructionError(
            "Timeline has no usable frame at minute 5 or later; the game is too "
            "short (or has no timeline) to chart a win-probability progression."
        )

    # Imported lazily to avoid a circular import at module load (main.py imports
    # app modules; this module is imported by main.py's route).
    from app.main import predict_timeline_at

    checkpoints: List[Dict[str, Any]] = []
    for minute in minutes:
        features = build_timeline_features(match_detail, timeline, minute)
        predicted = predict_timeline_at(minute, features)
        checkpoints.append(
            {
                "minute": minute,
                "gold_diff": float(features[f"gold_diff_at_{minute}"]),
                "predicted": predicted,
            }
        )

    metadata = (match_detail or {}).get("metadata") or {}
    info = (match_detail or {}).get("info") or {}
    match_id = metadata.get("matchId")
    if not match_id:
        game_id = info.get("gameId")
        match_id = str(game_id) if game_id is not None else ""

    game_duration = info.get("gameDuration")

    return {
        "match_id": str(match_id),
        "game_duration": int(game_duration) if game_duration is not None else None,
        "actual": {
            "winner_side": _winning_side(match_detail),
            "player_won": _player_won(match_detail, puuid),
        },
        "checkpoints": checkpoints,
    }
