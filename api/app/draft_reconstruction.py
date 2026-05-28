"""Reconstruct a draft-prediction request from Riot participant lists.

SHARED helper: used by the past-game (match-v5) and live (spectator-v5) paths
(T006 / T007) to turn a list of Riot participants into the 10 champion-NAME
slots the model's ``DraftPredictionRequest`` expects
(``blue_top .. red_support``).

Two facts drive the design (see T002 scout notes):

1. The model takes champion *display names*, not ids — so every ``championId``
   is reverse-mapped through ``champion_id_map.json``.
2. ``DraftPredictionRequest`` demands an explicit per-role slot per team, but
   Riot lane data is unreliable (match-v5 ``teamPosition`` can be empty /
   ``UNKNOWN`` / duplicated) or entirely absent (spectator-v5 carries no
   position at all). Role assignment is therefore the central reconstruction
   risk and uses the deterministic fallback documented on
   :func:`reconstruct_draft`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Canonical model role order. The fallback fills *remaining* slots in this exact
# order so reconstruction is deterministic for a given participant ordering.
CANONICAL_ROLES = ("top", "jungle", "mid", "adc", "support")

# Riot teamPosition (match-v5) -> model role slot.
_TEAM_POSITION_TO_ROLE = {
    "TOP": "top",
    "JUNGLE": "jungle",
    "MIDDLE": "mid",
    "BOTTOM": "adc",
    "UTILITY": "support",
}

# Riot teamId -> model side prefix.
_TEAM_ID_TO_SIDE = {100: "blue", 200: "red"}

_CHAMPION_MAP_PATH = Path(__file__).parent / "champion_id_map.json"
_id_to_name: Optional[Dict[int, str]] = None


def _load_reverse_index() -> Dict[int, str]:
    """Build & cache the ``championId(int) -> display name(str)`` reverse index.

    ``champion_id_map.json`` is keyed by *normalized name* → ``{id, name}``; the
    feature path only ever needs name→id, so the id→name direction is built
    here once and memoised.
    """
    global _id_to_name
    if _id_to_name is None:
        try:
            with open(_CHAMPION_MAP_PATH, "r", encoding="utf-8") as fh:
                forward: Dict[str, Dict[str, Any]] = json.load(fh)
        except Exception:  # pragma: no cover - file ships with the package
            forward = {}
        index: Dict[int, str] = {}
        for entry in forward.values():
            cid = entry.get("id")
            name = entry.get("name")
            if isinstance(cid, int) and isinstance(name, str):
                index[cid] = name
        _id_to_name = index
    return _id_to_name


def name_for_champion_id(champion_id: Any) -> Optional[str]:
    """Return the Data-Dragon display name for a numeric ``championId``.

    Returns ``None`` for an unknown / non-integer id so callers can surface a
    clear error instead of silently mislabelling a pick.
    """
    try:
        cid = int(champion_id)
    except (TypeError, ValueError):
        return None
    return _load_reverse_index().get(cid)


class DraftReconstructionError(ValueError):
    """Raised when participants cannot be mapped to a valid 10-slot draft."""


def _assign_team_roles(team: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Assign the 5 participants of one team to ``CANONICAL_ROLES`` slots.

    Strategy (deterministic):
      1. Honour each participant's ``teamPosition`` when it maps to a known role
         AND that role slot is still free (first writer wins on a duplicate).
      2. Any participant whose position was missing / ``UNKNOWN`` / unmapped /
         lost a duplicate tie is queued, then assigned — in original participant
         order — to the remaining role slots in canonical order.

    This makes spectator-v5 (no positions at all) collapse to "participant
    order within the team", and makes partial/duplicated match-v5 positions
    fully reproducible.
    """
    slots: Dict[str, Dict[str, Any]] = {}
    leftovers: List[Dict[str, Any]] = []

    for p in team:
        pos = str(p.get("teamPosition") or p.get("individualPosition") or "").upper()
        role = _TEAM_POSITION_TO_ROLE.get(pos)
        if role is not None and role not in slots:
            slots[role] = p
        else:
            leftovers.append(p)

    free_roles = [r for r in CANONICAL_ROLES if r not in slots]
    for role, p in zip(free_roles, leftovers):
        slots[role] = p

    return slots


def reconstruct_draft(participants: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reconstruct a ``DraftPredictionRequest`` payload from Riot participants.

    Parameters
    ----------
    participants:
        A list of 10 dicts, each with at least ``championId`` (int) and
        ``teamId`` (100 blue / 200 red). ``teamPosition`` (TOP/JUNGLE/MIDDLE/
        BOTTOM/UTILITY) is used when present; ``individualPosition`` is a
        secondary source. Extra keys are ignored. Works for both match-v5
        (positions present) and spectator-v5 (no positions).

    Returns
    -------
    dict
        ``{<draft request keys>..., "fallback_used": bool, "warnings": [..]}``.
        The 10 keys are exactly ``blue_top .. red_support`` mapping to champion
        DISPLAY NAMES, ready to feed the ``/predict/draft`` route.

        ``fallback_used`` is ``True`` when any slot had to be filled by the
        canonical-order fallback (so callers can flag the reconstruction as
        approximate). ``warnings`` collects unknown-champion notices.

    Role-slot fallback (the central reconstruction risk)
    ----------------------------------------------------
    When a participant's ``teamPosition`` is empty / ``UNKNOWN`` / unmapped /
    duplicated, OR for spectator-v5 where there is no position at all, the
    remaining role slots are filled in canonical order ``(top, jungle, mid,
    adc, support)`` by the participant's order within its team. This is
    deterministic — never random — so the same input always yields the same
    draft. The result is flagged via ``fallback_used`` so the UI can mark the
    lane assignment as a best-effort guess.

    Raises
    ------
    DraftReconstructionError
        If a side does not have exactly 5 participants, or a ``championId``
        cannot be reverse-mapped to a display name (so an unknown champion is a
        hard, visible error rather than a silent neutral default).
    """
    if not isinstance(participants, list):
        raise DraftReconstructionError("participants must be a list.")

    teams: Dict[int, List[Dict[str, Any]]] = {100: [], 200: []}
    for p in participants:
        team_id = p.get("teamId")
        if team_id not in _TEAM_ID_TO_SIDE:
            raise DraftReconstructionError(
                f"Unexpected teamId {team_id!r}; expected 100 (blue) or 200 (red)."
            )
        teams[team_id].append(p)

    for team_id, members in teams.items():
        side = _TEAM_ID_TO_SIDE[team_id]
        if len(members) != 5:
            raise DraftReconstructionError(
                f"{side} team has {len(members)} players; exactly 5 are required."
            )

    result: Dict[str, Any] = {}
    warnings: List[str] = []
    fallback_used = False

    for team_id, members in teams.items():
        side = _TEAM_ID_TO_SIDE[team_id]
        slots = _assign_team_roles(members)

        # Any slot not produced by an honoured teamPosition counts as fallback.
        for role in CANONICAL_ROLES:
            p = slots[role]
            pos = str(
                p.get("teamPosition") or p.get("individualPosition") or ""
            ).upper()
            if _TEAM_POSITION_TO_ROLE.get(pos) != role:
                fallback_used = True

            name = name_for_champion_id(p.get("championId"))
            if name is None:
                raise DraftReconstructionError(
                    f"Unknown championId {p.get('championId')!r} for "
                    f"{side}_{role}; cannot map to a champion name."
                )
            result[f"{side}_{role}"] = name

    result["fallback_used"] = fallback_used
    result["warnings"] = warnings
    return result
