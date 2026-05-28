"""Unit tests for app.draft_reconstruction (shared by T006/T007).

Covers the reverse index, full-position reconstruction, the deterministic
fallback (missing/UNKNOWN/duplicated positions and spectator-style no-position),
and unknown-championId handling. No network, no DB.
"""

import pytest

from app.draft_reconstruction import (
    CANONICAL_ROLES,
    DraftReconstructionError,
    name_for_champion_id,
    reconstruct_draft,
)

DRAFT_KEYS = [f"{side}_{role}" for side in ("blue", "red") for role in CANONICAL_ROLES]


# ──────────────────────────────────────────
# reverse index
# ──────────────────────────────────────────

def test_name_for_champion_id_known():
    # From champion_id_map.json: 266 -> Aatrox, 103 -> Ahri, 266..
    assert name_for_champion_id(266) == "Aatrox"
    assert name_for_champion_id(103) == "Ahri"
    assert name_for_champion_id("266") == "Aatrox"  # numeric string accepted


def test_name_for_champion_id_unknown_returns_none():
    assert name_for_champion_id(99999999) is None
    assert name_for_champion_id(None) is None
    assert name_for_champion_id("notanumber") is None


# ──────────────────────────────────────────
# full-position reconstruction (match-v5)
# ──────────────────────────────────────────

def _full_participants():
    positions = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
    champ_ids = {"TOP": 266, "JUNGLE": 64, "MIDDLE": 103, "BOTTOM": 22, "UTILITY": 412}
    out = []
    for team_id in (100, 200):
        for pos in positions:
            out.append({"championId": champ_ids[pos], "teamId": team_id, "teamPosition": pos})
    return out


def test_reconstruct_full_positions():
    result = reconstruct_draft(_full_participants())
    for k in DRAFT_KEYS:
        assert k in result
        assert isinstance(result[k], str) and result[k]
    assert result["blue_top"] == "Aatrox"
    assert result["blue_jungle"] == name_for_champion_id(64)  # LeeSin
    assert result["blue_mid"] == "Ahri"
    assert result["blue_adc"] == name_for_champion_id(22)     # Ashe
    assert result["blue_support"] == name_for_champion_id(412)  # Thresh
    assert result["fallback_used"] is False


# ──────────────────────────────────────────
# fallback: missing / UNKNOWN / duplicated positions
# ──────────────────────────────────────────

def test_reconstruct_missing_and_unknown_positions_uses_fallback():
    # Blue team: positions are all empty/UNKNOWN -> canonical order by index.
    blue = [
        {"championId": 266, "teamId": 100, "teamPosition": ""},
        {"championId": 64, "teamId": 100, "teamPosition": "UNKNOWN"},
        {"championId": 103, "teamId": 100},
        {"championId": 22, "teamId": 100, "teamPosition": ""},
        {"championId": 412, "teamId": 100, "teamPosition": "UNKNOWN"},
    ]
    # Red team: full valid positions (no fallback for this side).
    red_positions = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
    red_ids = [266, 64, 103, 22, 412]
    red = [
        {"championId": cid, "teamId": 200, "teamPosition": pos}
        for cid, pos in zip(red_ids, red_positions)
    ]
    result = reconstruct_draft(blue + red)
    assert result["fallback_used"] is True
    # Fallback fills in participant order across canonical roles.
    assert result["blue_top"] == "Aatrox"
    assert result["blue_jungle"] == name_for_champion_id(64)
    assert result["blue_mid"] == "Ahri"
    assert result["blue_adc"] == name_for_champion_id(22)
    assert result["blue_support"] == name_for_champion_id(412)


def test_reconstruct_duplicate_positions_uses_fallback_for_collision():
    # Two TOPs on blue: first wins TOP, the second is reassigned by fallback.
    blue = [
        {"championId": 266, "teamId": 100, "teamPosition": "TOP"},
        {"championId": 64, "teamId": 100, "teamPosition": "TOP"},
        {"championId": 103, "teamId": 100, "teamPosition": "MIDDLE"},
        {"championId": 22, "teamId": 100, "teamPosition": "BOTTOM"},
        {"championId": 412, "teamId": 100, "teamPosition": "UTILITY"},
    ]
    red = [
        {"championId": cid, "teamId": 200, "teamPosition": pos}
        for cid, pos in zip([266, 64, 103, 22, 412], ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"])
    ]
    result = reconstruct_draft(blue + red)
    assert result["fallback_used"] is True
    assert result["blue_top"] == "Aatrox"            # first TOP honoured
    # Second TOP (LeeSin) goes to the first free canonical slot = jungle.
    assert result["blue_jungle"] == name_for_champion_id(64)
    assert result["blue_mid"] == "Ahri"
    # Each of the 10 keys must be present and unique-ish (all 5 blue assigned).
    blue_vals = {result[f"blue_{r}"] for r in CANONICAL_ROLES}
    assert len(blue_vals) == 5


# ──────────────────────────────────────────
# spectator-v5: no position field at all
# ──────────────────────────────────────────

def test_reconstruct_spectator_no_positions():
    parts = []
    for team_id in (100, 200):
        for cid in [266, 64, 103, 22, 412]:
            parts.append({"championId": cid, "teamId": team_id})  # no teamPosition
    result = reconstruct_draft(parts)
    assert result["fallback_used"] is True
    assert set(DRAFT_KEYS).issubset(result.keys())
    assert result["red_top"] == "Aatrox"
    assert result["red_support"] == name_for_champion_id(412)


# ──────────────────────────────────────────
# error handling
# ──────────────────────────────────────────

def test_reconstruct_unknown_champion_id_raises():
    parts = []
    for team_id in (100, 200):
        for cid in [266, 64, 103, 22, 412]:
            parts.append({"championId": cid, "teamId": team_id})
    parts[0]["championId"] = 99999999  # unknown
    with pytest.raises(DraftReconstructionError):
        reconstruct_draft(parts)


def test_reconstruct_wrong_team_size_raises():
    # Only 4 on blue.
    parts = [{"championId": 266, "teamId": 100} for _ in range(4)]
    parts += [{"championId": 266, "teamId": 200} for _ in range(5)]
    # Add one more to make 10 total but unbalanced (6 red / 4 blue).
    parts.append({"championId": 266, "teamId": 200})
    with pytest.raises(DraftReconstructionError):
        reconstruct_draft(parts)


def test_reconstruct_bad_team_id_raises():
    parts = [{"championId": 266, "teamId": 300} for _ in range(10)]
    with pytest.raises(DraftReconstructionError):
        reconstruct_draft(parts)
