"""Summarise a match-v5 detail payload from one player's point of view.

This module is intentionally PURE (no I/O, no network): it takes a match
detail dict (as returned by ``RiotClient.get_match_detail``) plus the target
``puuid`` and produces a small, testable :class:`~app.riot_models.MatchSummary`.
The route layer in ``main.py`` does the fetching; the SR-5v5 filter set lives
here so both the route and tests share one source of truth.

Champion resolution reuses the shared reverse index from
``draft_reconstruction`` (``championId -> display name``), falling back to the
``championName`` string Riot already includes on each participant so a brand-new
champion missing from the static map still renders a real name.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.draft_reconstruction import name_for_champion_id
from app.riot_models import MatchSummary

# Summoner's Rift 5v5 queues we surface by default (draft, ranked solo, blind,
# ranked flex). Anything else (ARAM, Arena, bots, Clash variants, ...) is
# filtered out so the history shows games the draft model is actually trained
# on. Exposed for reuse by the route + tests.
SR_5V5_QUEUE_IDS = frozenset({400, 420, 430, 440})


def is_sr_5v5_queue(queue_id: Any) -> bool:
    """True when ``queue_id`` is one of the default SR 5v5 queues."""
    try:
        return int(queue_id) in SR_5V5_QUEUE_IDS
    except (TypeError, ValueError):
        return False


def _find_participant(match_detail: Dict[str, Any], puuid: str) -> Optional[Dict[str, Any]]:
    """Return the participant dict for ``puuid`` from a match detail, or None."""
    info = match_detail.get("info") or {}
    participants = info.get("participants") or []
    for p in participants:
        if isinstance(p, dict) and p.get("puuid") == puuid:
            return p
    return None


def _resolve_champion_name(participant: Dict[str, Any]) -> Optional[str]:
    """Resolve the participant's champion DISPLAY name.

    Prefers the shared ``championId -> name`` reverse index (canonical with the
    rest of the feature path); falls back to Riot's own ``championName`` field
    when the id is missing/unknown so a freshly-released champion still shows a
    real name instead of blank.
    """
    name = name_for_champion_id(participant.get("championId"))
    if name:
        return name
    riot_name = participant.get("championName")
    if isinstance(riot_name, str) and riot_name.strip():
        return riot_name.strip()
    return None


def summarize_match_for_player(
    match_detail: Dict[str, Any], puuid: str
) -> Optional[MatchSummary]:
    """Summarise a single match for ``puuid`` into a :class:`MatchSummary`.

    Pulls the match id from ``metadata.matchId`` (falling back to
    ``info.gameId`` only as a last resort) and the match-level
    ``queueId / gameDuration / gameCreation / gameMode`` from ``info``. The
    player's ``win`` and champion come from their own participant row.

    Returns ``None`` when ``puuid`` is not one of the match's participants, so
    the route can skip a match it cannot attribute rather than emit a misleading
    row.
    """
    info = match_detail.get("info") or {}
    metadata = match_detail.get("metadata") or {}

    participant = _find_participant(match_detail, puuid)
    if participant is None:
        return None

    match_id = metadata.get("matchId")
    if not match_id:
        game_id = info.get("gameId")
        match_id = str(game_id) if game_id is not None else ""

    win = participant.get("win")
    if not isinstance(win, bool):
        win = bool(win) if win is not None else None

    return MatchSummary(
        match_id=str(match_id),
        champion_name=_resolve_champion_name(participant),
        win=win,
        queue_id=info.get("queueId"),
        game_duration=info.get("gameDuration"),
        game_creation=info.get("gameCreation"),
        game_mode=info.get("gameMode"),
    )


def summarize_matches_for_player(
    match_details: List[Dict[str, Any]],
    puuid: str,
    sr_5v5_only: bool = True,
) -> List[MatchSummary]:
    """Summarise many matches for ``puuid``, optionally keeping only SR 5v5.

    Order is preserved (Riot returns match ids newest-first). Matches the
    player is not in are dropped; when ``sr_5v5_only`` is set, non-SR-5v5 queues
    are filtered out using :data:`SR_5V5_QUEUE_IDS`.
    """
    summaries: List[MatchSummary] = []
    for detail in match_details:
        summary = summarize_match_for_player(detail, puuid)
        if summary is None:
            continue
        if sr_5v5_only and not is_sr_5v5_queue(summary.queue_id):
            continue
        summaries.append(summary)
    return summaries
