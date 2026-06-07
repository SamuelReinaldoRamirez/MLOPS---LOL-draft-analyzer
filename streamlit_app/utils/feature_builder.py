"""
Feature builder for V3 models.

Adds external winrate, matchup, synergy/counter features and summoner stats
to a DataFrame using the external data stored in model pickle files.
"""
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from itertools import combinations

POSITIONS = ['top', 'jungle', 'mid', 'adc', 'support']

# Add project paths for database access
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "collect_data"))


def add_all_model_features(df, model_data):
    """
    Add all features needed by the V3 model to a DataFrame.

    Args:
        df: DataFrame with at least champion_name columns
        model_data: Dict loaded from model pickle (contains external_data, synergy_data)

    Returns:
        DataFrame with all model features added
    """
    ext_data = model_data.get('external_data', {})
    syn_data = model_data.get('synergy_data', {})

    wr_dict = ext_data.get('wr_dict', {})
    matchup_dict = ext_data.get('matchup_dict', {})
    synergy_wr = syn_data.get('synergy_wr', {})
    counter_wr = syn_data.get('counter_wr', {})

    # Always add all feature types (use defaults if data unavailable)
    df = _add_ext_winrate(df, wr_dict)
    df = _add_matchup(df, matchup_dict)
    df = _add_synergy_counter(df, synergy_wr, counter_wr)

    # Add external synergy defaults if not present
    if 'ext_synergy_100' not in df.columns:
        df['ext_synergy_100'] = 0.5
        df['ext_synergy_200'] = 0.5
        df['ext_synergy_diff'] = 0.0

    # V3: Add summoner stats
    df = _add_summoner_stats(df)

    # Add derived timeline features
    for minute in [5, 10, 15, 20]:
        gdiff = f'gold_diff_at_{minute}'
        if gdiff in df.columns:
            df = _add_derived_timeline(df, minute)

    return df


def _add_ext_winrate(df, wr_dict):
    """Add ext_wr, ext_tier, ext_pickrate features."""
    df = df.copy()
    n = len(df)

    for team in [100, 200]:
        wr_list, tier_list = [], []
        for pos in POSITIONS:
            col_name = f'team_{team}_{pos}_champion_name'
            wr_col = f'ext_wr_{team}_{pos}'
            tier_col = f'ext_tier_{team}_{pos}'
            pr_col = f'ext_pickrate_{team}_{pos}'

            wr_vals = np.full(n, 0.5)
            tier_vals = np.zeros(n)
            pr_vals = np.zeros(n)

            if col_name in df.columns:
                for i, name in enumerate(df[col_name].values):
                    if pd.notna(name):
                        data = wr_dict.get((str(name).strip(), pos))
                        if data:
                            wr_vals[i] = data.get('winrate', 0.5)
                            tier_vals[i] = data.get('tier_num', 0)
                            pr_vals[i] = data.get('pickrate', 0.0)

            df[wr_col] = wr_vals
            df[tier_col] = tier_vals
            df[pr_col] = pr_vals
            wr_list.append(wr_vals)
            tier_list.append(tier_vals)

        df[f'ext_avg_wr_{team}'] = np.mean(wr_list, axis=0)
        df[f'ext_avg_tier_{team}'] = np.mean(tier_list, axis=0)

    df['ext_wr_diff'] = df['ext_avg_wr_100'] - df['ext_avg_wr_200']
    df['ext_tier_diff'] = df['ext_avg_tier_100'] - df['ext_avg_tier_200']
    return df


def _add_matchup(df, matchup_dict):
    """Add matchup_wr and matchup_advantage features."""
    df = df.copy()
    n = len(df)
    advantages = []

    for pos in POSITIONS:
        col_100 = f'team_100_{pos}_champion_name'
        col_200 = f'team_200_{pos}_champion_name'
        wr_col = f'matchup_wr_{pos}'
        adv_col = f'matchup_advantage_{pos}'
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

    df['avg_matchup_advantage'] = np.mean(advantages, axis=0)
    df['max_matchup_advantage'] = np.max(advantages, axis=0)
    df['min_matchup_advantage'] = np.min(advantages, axis=0)
    return df


def _add_synergy_counter(df, synergy_wr, counter_wr):
    """Add synergy/counter score features."""
    df = df.copy()
    champ_cols = {
        t: [f'team_{t}_{pos}_champion_id' for pos in POSITIONS]
        for t in [100, 200]
    }
    n = len(df)
    syn_100 = np.full(n, 0.5)
    syn_200 = np.full(n, 0.5)
    cnt_100 = np.full(n, 0.5)
    cnt_200 = np.full(n, 0.5)

    for i in range(n):
        row = df.iloc[i]
        champs_100 = [int(row[c]) for c in champ_cols[100]
                       if c in df.columns and pd.notna(row.get(c))]
        champs_200 = [int(row[c]) for c in champ_cols[200]
                       if c in df.columns and pd.notna(row.get(c))]

        if len(champs_100) >= 2:
            s = [synergy_wr.get(tuple(sorted([c1, c2])), 0.5) for c1, c2 in combinations(champs_100, 2)]
            syn_100[i] = np.mean(s)
        if len(champs_200) >= 2:
            s = [synergy_wr.get(tuple(sorted([c1, c2])), 0.5) for c1, c2 in combinations(champs_200, 2)]
            syn_200[i] = np.mean(s)

        if champs_100 and champs_200:
            c1 = [counter_wr.get((a, b), 0.5) for a in champs_100 for b in champs_200]
            c2 = [counter_wr.get((b, a), 0.5) for b in champs_200 for a in champs_100]
            cnt_100[i] = np.mean(c1)
            cnt_200[i] = np.mean(c2)

    df['team_100_synergy_score'] = syn_100
    df['team_200_synergy_score'] = syn_200
    df['team_100_counter_score'] = cnt_100
    df['team_200_counter_score'] = cnt_200
    df['synergy_diff'] = syn_100 - syn_200
    df['counter_diff'] = cnt_100 - cnt_200
    df['draft_advantage'] = (syn_100 - syn_200) + (cnt_100 - cnt_200)
    return df


def _add_summoner_stats(df):
    """
    Add summoner stats features for interactive prediction (V3).

    Fetches real-time stats from the database for each player's PUUID.
    Falls back to defaults (0.5 winrate, 0.2 role_pct, etc.) if data unavailable.
    """
    df = df.copy()

    # Check if puuid columns exist
    has_puuids = any(f'team_100_{pos}_puuid' in df.columns for pos in POSITIONS)

    if not has_puuids:
        # No PUUIDs available — set all summoner features to defaults
        return _add_summoner_stats_defaults(df)

    # Try to fetch stats from database
    try:
        from database import MatchDatabase
        from config import DATABASE_PATH as DB_PATH
        db = MatchDatabase(str(DB_PATH))
    except Exception:
        try:
            db_path = Path(__file__).parent.parent.parent / "data" / "lol_matches.db"
            from database import MatchDatabase
            db = MatchDatabase(str(db_path))
        except Exception:
            return _add_summoner_stats_defaults(df)

    # Collect all PUUIDs
    all_puuids = set()
    for team in ['team_100', 'team_200']:
        for pos in POSITIONS:
            col = f'{team}_{pos}_puuid'
            if col in df.columns:
                all_puuids.update(df[col].dropna().unique())

    if not all_puuids:
        return _add_summoner_stats_defaults(df)

    # Fetch stats (no before_timestamp = use all available data for live prediction)
    try:
        all_stats = db.get_all_summoner_stats_batch(list(all_puuids), last_n_games=20)
    except Exception:
        return _add_summoner_stats_defaults(df)

    # Apply stats
    for team in ['team_100', 'team_200']:
        role_spec_cols = []
        role_wr_cols = []
        mastery_cols = []

        for pos in POSITIONS:
            puuid_col = f'{team}_{pos}_puuid'
            champ_col = f'{team}_{pos}_champion_id'

            role_pct_col = f'{team}_{pos}_role_pct'
            role_wr_col = f'{team}_{pos}_role_winrate'
            mastery_col = f'{team}_{pos}_mastery_points'
            streak_type_col = f'{team}_{pos}_streak_type'
            streak_len_col = f'{team}_{pos}_streak_length'
            kda_col = f'{team}_{pos}_role_kda'
            vision_col = f'{team}_{pos}_role_vision'
            champ_wr_col = f'{team}_{pos}_champ_recent_wr'

            # Defaults
            df[role_pct_col] = 0.2
            df[role_wr_col] = 0.5
            df[mastery_col] = 0.0
            df[streak_type_col] = 0
            df[streak_len_col] = 0
            df[kda_col] = 2.0
            df[vision_col] = 20.0
            df[champ_wr_col] = 0.5

            if puuid_col not in df.columns:
                role_spec_cols.append(role_pct_col)
                role_wr_cols.append(role_wr_col)
                mastery_cols.append(mastery_col)
                continue

            puuids = df[puuid_col].values
            champ_ids = df[champ_col].values if champ_col in df.columns else [None] * len(df)

            for i, (puuid, champ_id) in enumerate(zip(puuids, champ_ids)):
                if pd.isna(puuid) or puuid not in all_stats:
                    continue

                stats = all_stats[puuid]
                role_stats = stats.get('role_stats', {})
                df.at[df.index[i], role_pct_col] = role_stats.get('role_distribution', {}).get(pos, 0.2)
                df.at[df.index[i], role_wr_col] = role_stats.get('role_winrates', {}).get(pos, 0.5)

                perf = stats.get('performance', {})
                df.at[df.index[i], kda_col] = perf.get('role_kda', {}).get(pos, 2.0)
                df.at[df.index[i], vision_col] = perf.get('role_vision_score', {}).get(pos, 20.0)

                streaks = stats.get('streaks', {})
                st = streaks.get('current_streak_type', 'none')
                df.at[df.index[i], streak_type_col] = 1 if st == 'win' else (-1 if st == 'loss' else 0)
                df.at[df.index[i], streak_len_col] = streaks.get('current_streak_length', 0)

                recent_champs = stats.get('recent_champions', [])
                if champ_id and not pd.isna(champ_id):
                    for champ_stat in recent_champs:
                        if champ_stat.get('champion_id') == int(champ_id):
                            df.at[df.index[i], champ_wr_col] = champ_stat.get('winrate', 0.5)
                            break

            role_spec_cols.append(role_pct_col)
            role_wr_cols.append(role_wr_col)
            mastery_cols.append(mastery_col)

        # Team aggregates
        df[f'{team}_avg_role_specialization'] = df[role_spec_cols].mean(axis=1)
        df[f'{team}_min_role_specialization'] = df[role_spec_cols].min(axis=1)
        df[f'{team}_avg_role_winrate'] = df[role_wr_cols].mean(axis=1)
        df[f'{team}_total_mastery_points'] = df[mastery_cols].sum(axis=1)

        streak_momentum = 0
        for pos in POSITIONS:
            streak_momentum = streak_momentum + (
                df[f'{team}_{pos}_streak_type'] * df[f'{team}_{pos}_streak_length']
            )
        df[f'{team}_streak_momentum'] = streak_momentum

    # Differentials
    df['role_specialization_diff'] = df['team_100_avg_role_specialization'] - df['team_200_avg_role_specialization']
    df['role_winrate_diff'] = df['team_100_avg_role_winrate'] - df['team_200_avg_role_winrate']
    df['streak_momentum_diff'] = df['team_100_streak_momentum'] - df['team_200_streak_momentum']
    df['mastery_diff'] = df['team_100_total_mastery_points'] - df['team_200_total_mastery_points']

    return df


def _add_summoner_stats_defaults(df):
    """Add summoner stats features with default values (when no DB or no PUUIDs)."""
    df = df.copy()

    for team in ['team_100', 'team_200']:
        for pos in POSITIONS:
            df[f'{team}_{pos}_role_pct'] = 0.2
            df[f'{team}_{pos}_role_winrate'] = 0.5
            df[f'{team}_{pos}_mastery_points'] = 0.0
            df[f'{team}_{pos}_streak_type'] = 0
            df[f'{team}_{pos}_streak_length'] = 0
            df[f'{team}_{pos}_role_kda'] = 2.0
            df[f'{team}_{pos}_role_vision'] = 20.0
            df[f'{team}_{pos}_champ_recent_wr'] = 0.5

        df[f'{team}_avg_role_specialization'] = 0.2
        df[f'{team}_min_role_specialization'] = 0.2
        df[f'{team}_avg_role_winrate'] = 0.5
        df[f'{team}_total_mastery_points'] = 0.0
        df[f'{team}_streak_momentum'] = 0

    df['role_specialization_diff'] = 0.0
    df['role_winrate_diff'] = 0.0
    df['streak_momentum_diff'] = 0.0
    df['mastery_diff'] = 0.0

    return df


def _add_derived_timeline(df, minute):
    """Add per-role gold/CS diff features."""
    df = df.copy()

    for pos in POSITIONS:
        g100 = f'team_100_{pos}_gold_at_{minute}'
        g200 = f'team_200_{pos}_gold_at_{minute}'
        diff_col = f'{pos}_gold_diff_at_{minute}'
        if g100 in df.columns and g200 in df.columns:
            df[diff_col] = df[g100] - df[g200]

    if minute >= 10:
        for pos in POSITIONS:
            cs100 = f'team_100_{pos}_cs_at_10'
            cs200 = f'team_200_{pos}_cs_at_10'
            diff_col = f'{pos}_cs_diff_at_10'
            if cs100 in df.columns and cs200 in df.columns:
                df[diff_col] = df[cs100] - df[cs200]

    return df
