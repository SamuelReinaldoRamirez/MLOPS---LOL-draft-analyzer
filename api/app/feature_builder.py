"""
DB-free champion-side feature builder for the draft model.

This is a faithful port of the SOURCE Streamlit feature builder
(``streamlit_app/utils/feature_builder.py``) reduced to what a *draft request*
can actually supply: the 10 champion picks. It produces the champion-side
features — external winrate/tier/pickrate, lane matchups, team synergy/counter
scores and the derived draft-advantage — by reading the lookup tables that ship
*inside* ``model_draft.pkl`` (``external_data`` + ``synergy_data``).

What it intentionally does NOT do:

  * No database access, no Riot API, no Streamlit imports.
  * The 84 summoner-level features (per-player role winrate, mastery, streaks,
    champion recent winrate, ...) require per-player PUUIDs that a draft request
    cannot carry. They are filled with the SAME neutral defaults the SOURCE uses
    when no PUUID is available (``_add_summoner_stats_defaults``).
  * Timeline features are not relevant to the draft model and are left to the
    caller's reindex/fill step.

Lookup-table key formats (verified against the shipped pickle):
  * ``external_data.wr_dict``      -> keyed by ``(champion_name, position)`` where
    ``champion_name`` is the DB/Data-Dragon form with no spaces (e.g. "MissFortune").
  * ``external_data.matchup_dict`` -> keyed by ``(name_100, name_200, position)``.
  * ``synergy_data.synergy_wr``    -> keyed by a *sorted* ``(champion_id, champion_id)`` tuple.
  * ``synergy_data.counter_wr``    -> keyed by a *directional* ``(champion_id, champion_id)`` tuple.
"""
from itertools import combinations

import numpy as np
import pandas as pd

POSITIONS = ["top", "jungle", "mid", "adc", "support"]


def add_all_model_features(df, model_data):
    """Add all champion-side draft features to a DataFrame.

    Args:
        df: DataFrame whose rows describe drafts. Expected columns are
            ``team_{100,200}_{pos}_champion_name`` (DB/Data-Dragon string form)
            and ``team_{100,200}_{pos}_champion_id`` (int).
        model_data: dict loaded from ``model_draft.pkl`` (provides
            ``external_data`` and ``synergy_data``).

    Returns:
        A new DataFrame with the champion-side features plus summoner-stat
        defaults added. The caller is responsible for reindexing to the model's
        ``feature_columns``.
    """
    ext_data = model_data.get("external_data", {}) or {}
    syn_data = model_data.get("synergy_data", {}) or {}

    wr_dict = ext_data.get("wr_dict", {}) or {}
    matchup_dict = ext_data.get("matchup_dict", {}) or {}
    synergy_wr = syn_data.get("synergy_wr", {}) or {}
    counter_wr = syn_data.get("counter_wr", {}) or {}

    # Always add all champion-side feature types (use defaults if data missing).
    df = _add_ext_winrate(df, wr_dict)
    df = _add_matchup(df, matchup_dict)
    df = _add_synergy_counter(df, synergy_wr, counter_wr)

    # External synergy is a separate (DB-derived) feature in V3; a draft request
    # has no source for it, so mirror the SOURCE neutral default.
    if "ext_synergy_100" not in df.columns:
        df["ext_synergy_100"] = 0.5
        df["ext_synergy_200"] = 0.5
        df["ext_synergy_diff"] = 0.0

    # Summoner stats: a draft request carries no PUUID, so use the SOURCE
    # defaults path verbatim (same neutral values the Streamlit flow uses).
    df = _add_summoner_stats_defaults(df)

    return df


def _add_ext_winrate(df, wr_dict):
    """Add ext_wr / ext_tier / ext_pickrate features (faithful SOURCE port)."""
    df = df.copy()
    n = len(df)

    for team in [100, 200]:
        wr_list, tier_list = [], []
        for pos in POSITIONS:
            col_name = f"team_{team}_{pos}_champion_name"
            wr_col = f"ext_wr_{team}_{pos}"
            tier_col = f"ext_tier_{team}_{pos}"
            pr_col = f"ext_pickrate_{team}_{pos}"

            wr_vals = np.full(n, 0.5)
            tier_vals = np.zeros(n)
            pr_vals = np.zeros(n)

            if col_name in df.columns:
                for i, name in enumerate(df[col_name].values):
                    if pd.notna(name):
                        data = wr_dict.get((str(name).strip(), pos))
                        if data:
                            wr_vals[i] = data.get("winrate", 0.5)
                            tier_vals[i] = data.get("tier_num", 0)
                            pr_vals[i] = data.get("pickrate", 0.0)

            df[wr_col] = wr_vals
            df[tier_col] = tier_vals
            df[pr_col] = pr_vals
            wr_list.append(wr_vals)
            tier_list.append(tier_vals)

        df[f"ext_avg_wr_{team}"] = np.mean(wr_list, axis=0)
        df[f"ext_avg_tier_{team}"] = np.mean(tier_list, axis=0)

    df["ext_wr_diff"] = df["ext_avg_wr_100"] - df["ext_avg_wr_200"]
    df["ext_tier_diff"] = df["ext_avg_tier_100"] - df["ext_avg_tier_200"]
    return df


def _add_matchup(df, matchup_dict):
    """Add matchup_wr / matchup_advantage features (faithful SOURCE port)."""
    df = df.copy()
    n = len(df)
    advantages = []

    for pos in POSITIONS:
        col_100 = f"team_100_{pos}_champion_name"
        col_200 = f"team_200_{pos}_champion_name"
        wr_col = f"matchup_wr_{pos}"
        adv_col = f"matchup_advantage_{pos}"
        wr_vals = np.full(n, 0.5)

        if col_100 in df.columns and col_200 in df.columns:
            for i in range(n):
                c100, c200 = df[col_100].iloc[i], df[col_200].iloc[i]
                if pd.notna(c100) and pd.notna(c200):
                    c100_s, c200_s = str(c100).strip(), str(c200).strip()
                    wr = matchup_dict.get((c100_s, c200_s, pos))
                    if wr is not None:
                        wr_vals[i] = wr
                    else:
                        wr_rev = matchup_dict.get((c200_s, c100_s, pos))
                        if wr_rev is not None:
                            wr_vals[i] = 1.0 - wr_rev

        df[wr_col] = wr_vals
        df[adv_col] = wr_vals - 0.5
        advantages.append(wr_vals - 0.5)

    df["avg_matchup_advantage"] = np.mean(advantages, axis=0)
    df["max_matchup_advantage"] = np.max(advantages, axis=0)
    df["min_matchup_advantage"] = np.min(advantages, axis=0)
    return df


def _add_synergy_counter(df, synergy_wr, counter_wr):
    """Add synergy/counter score features (faithful SOURCE port)."""
    df = df.copy()
    champ_cols = {
        t: [f"team_{t}_{pos}_champion_id" for pos in POSITIONS]
        for t in [100, 200]
    }
    n = len(df)
    syn_100 = np.full(n, 0.5)
    syn_200 = np.full(n, 0.5)
    cnt_100 = np.full(n, 0.5)
    cnt_200 = np.full(n, 0.5)

    for i in range(n):
        row = df.iloc[i]
        champs_100 = [
            int(row[c])
            for c in champ_cols[100]
            if c in df.columns and pd.notna(row.get(c))
        ]
        champs_200 = [
            int(row[c])
            for c in champ_cols[200]
            if c in df.columns and pd.notna(row.get(c))
        ]

        if len(champs_100) >= 2:
            s = [
                synergy_wr.get(tuple(sorted([c1, c2])), 0.5)
                for c1, c2 in combinations(champs_100, 2)
            ]
            syn_100[i] = np.mean(s)
        if len(champs_200) >= 2:
            s = [
                synergy_wr.get(tuple(sorted([c1, c2])), 0.5)
                for c1, c2 in combinations(champs_200, 2)
            ]
            syn_200[i] = np.mean(s)

        if champs_100 and champs_200:
            c1 = [counter_wr.get((a, b), 0.5) for a in champs_100 for b in champs_200]
            c2 = [counter_wr.get((b, a), 0.5) for b in champs_200 for a in champs_100]
            cnt_100[i] = np.mean(c1)
            cnt_200[i] = np.mean(c2)

    df["team_100_synergy_score"] = syn_100
    df["team_200_synergy_score"] = syn_200
    df["team_100_counter_score"] = cnt_100
    df["team_200_counter_score"] = cnt_200
    df["synergy_diff"] = syn_100 - syn_200
    df["counter_diff"] = cnt_100 - cnt_200
    df["draft_advantage"] = (syn_100 - syn_200) + (cnt_100 - cnt_200)
    return df


def _add_summoner_stats_defaults(df):
    """Add summoner-stat features at SOURCE defaults (no PUUID available).

    This is a verbatim port of the SOURCE ``_add_summoner_stats_defaults``: the
    exact same neutral values the Streamlit flow uses when a player's PUUID
    cannot be resolved. A draft request carries no player identity, so every
    summoner-level feature lands here.
    """
    df = df.copy()

    for team in ["team_100", "team_200"]:
        for pos in POSITIONS:
            df[f"{team}_{pos}_role_pct"] = 0.2
            df[f"{team}_{pos}_role_winrate"] = 0.5
            df[f"{team}_{pos}_mastery_points"] = 0.0
            df[f"{team}_{pos}_streak_type"] = 0
            df[f"{team}_{pos}_streak_length"] = 0
            df[f"{team}_{pos}_role_kda"] = 2.0
            df[f"{team}_{pos}_role_vision"] = 20.0
            df[f"{team}_{pos}_champ_recent_wr"] = 0.5

        df[f"{team}_avg_role_specialization"] = 0.2
        df[f"{team}_min_role_specialization"] = 0.2
        df[f"{team}_avg_role_winrate"] = 0.5
        df[f"{team}_total_mastery_points"] = 0.0
        df[f"{team}_streak_momentum"] = 0

    df["role_specialization_diff"] = 0.0
    df["role_winrate_diff"] = 0.0
    df["streak_momentum_diff"] = 0.0
    df["mastery_diff"] = 0.0

    return df
