"""
SQLite Database Interface for LoL Match Data Collection

This module provides a robust database interface for storing and retrieving
League of Legends match data. It replaces the previous JSON/CSV storage
for better reliability during long-running data collection.
"""

import sqlite3
import json
import pandas as pd
from contextlib import contextmanager
from datetime import datetime
from typing import Optional, Set, Dict, Any, List

from config import REGION


class MatchDatabase:
    """
    SQLite database interface for LoL match data.

    Features:
    - Atomic transactions for data integrity
    - Automatic deduplication via PRIMARY KEY
    - Progress tracking for resumable collection
    - Export to pandas DataFrame for ML
    """

    def __init__(self, db_path: str = 'lol_matches.db'):
        self.db_path = db_path
        self._init_db()
        self._migrate_schema()
        self._enable_wal()

    @contextmanager
    def get_connection(self):
        """Context manager for database connections with auto-commit"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database schema"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Table 1: Core match information
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS matches (
                    match_id TEXT PRIMARY KEY,
                    region TEXT,
                    source_elo TEXT,
                    game_creation INTEGER,
                    game_duration INTEGER,
                    game_version TEXT,
                    queue_id INTEGER DEFAULT 420,
                    map_id INTEGER,
                    game_mode TEXT,
                    game_type TEXT,
                    team_100_win BOOLEAN,
                    team_100_early_surrendered BOOLEAN DEFAULT FALSE,
                    team_200_early_surrendered BOOLEAN DEFAULT FALSE,
                    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table 2: Team-level objectives and bans
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS team_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT NOT NULL,
                    team_id INTEGER NOT NULL,
                    -- Objectives (first)
                    first_blood BOOLEAN,
                    first_tower BOOLEAN,
                    first_inhibitor BOOLEAN,
                    first_dragon BOOLEAN,
                    first_rift_herald BOOLEAN,
                    first_baron BOOLEAN,
                    -- Objective kills
                    dragon_kills INTEGER DEFAULT 0,
                    baron_kills INTEGER DEFAULT 0,
                    tower_kills INTEGER DEFAULT 0,
                    inhibitor_kills INTEGER DEFAULT 0,
                    rift_herald_kills INTEGER DEFAULT 0,
                    -- Bans (champion IDs)
                    ban_1_champion_id INTEGER,
                    ban_2_champion_id INTEGER,
                    ban_3_champion_id INTEGER,
                    ban_4_champion_id INTEGER,
                    ban_5_champion_id INTEGER,
                    -- Bans (champion names)
                    ban_1_name TEXT,
                    ban_2_name TEXT,
                    ban_3_name TEXT,
                    ban_4_name TEXT,
                    ban_5_name TEXT,
                    FOREIGN KEY (match_id) REFERENCES matches(match_id),
                    UNIQUE(match_id, team_id)
                )
            ''')

            # Table 3: Individual player performance
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS player_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT NOT NULL,
                    team_id INTEGER NOT NULL,
                    position TEXT NOT NULL,
                    -- Player identity (NEW)
                    puuid TEXT,
                    riot_id_name TEXT,
                    riot_id_tagline TEXT,
                    -- Champion info
                    champion_id INTEGER NOT NULL,
                    champion_name TEXT,
                    champ_level INTEGER,
                    -- Summoner spells
                    summoner_1_id INTEGER,
                    summoner_2_id INTEGER,
                    summoner_1_name TEXT,
                    summoner_2_name TEXT,
                    -- KDA
                    kills INTEGER,
                    deaths INTEGER,
                    assists INTEGER,
                    -- Damage stats
                    total_damage_dealt INTEGER,
                    total_damage_to_champions INTEGER,
                    total_damage_taken INTEGER,
                    true_damage_dealt INTEGER,
                    physical_damage_dealt INTEGER,
                    magic_damage_dealt INTEGER,
                    -- Economy
                    gold_earned INTEGER,
                    total_minions_killed INTEGER,
                    neutral_minions_killed INTEGER,
                    -- Vision
                    vision_score INTEGER,
                    wards_placed INTEGER,
                    wards_killed INTEGER,
                    vision_wards_bought INTEGER,
                    -- Combat
                    enemy_champion_immobilizations INTEGER DEFAULT 0,
                    first_blood_kill BOOLEAN,
                    first_tower_kill BOOLEAN,
                    turret_kills INTEGER,
                    inhibitor_kills INTEGER,
                    largest_killing_spree INTEGER,
                    largest_multi_kill INTEGER,
                    killing_sprees INTEGER,
                    double_kills INTEGER,
                    triple_kills INTEGER,
                    quadra_kills INTEGER,
                    penta_kills INTEGER,
                    -- Advanced metrics (from challenges)
                    damage_per_minute REAL,
                    damage_taken_percentage REAL,
                    gold_per_minute REAL,
                    team_damage_percentage REAL,
                    kill_participation REAL,
                    kda REAL,
                    lane_minions_first_10_min INTEGER,
                    turret_plates_taken INTEGER,
                    solo_kills INTEGER,
                    FOREIGN KEY (match_id) REFERENCES matches(match_id),
                    UNIQUE(match_id, team_id, position)
                )
            ''')

            # Table 4: Collection progress tracking
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS collection_progress (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    puuid TEXT UNIQUE,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table 5: Collection statistics
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS collection_stats (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            # Table 6: Summoners (player profiles)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS summoners (
                    puuid TEXT PRIMARY KEY,
                    riot_id_name TEXT,
                    riot_id_tagline TEXT,
                    -- Current rank info
                    current_tier TEXT,
                    current_rank TEXT,
                    current_lp INTEGER,
                    -- Stats
                    total_games_tracked INTEGER DEFAULT 0,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table 7: Summoner elo history (elo par patch)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS summoner_elo_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    puuid TEXT NOT NULL,
                    patch TEXT NOT NULL,
                    tier TEXT,
                    rank TEXT,
                    lp INTEGER,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (puuid) REFERENCES summoners(puuid),
                    UNIQUE(puuid, patch)
                )
            ''')

            # Table 8: Champion mastery per summoner
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS champion_mastery (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    puuid TEXT NOT NULL,
                    champion_id INTEGER NOT NULL,
                    champion_level INTEGER,
                    champion_points INTEGER,
                    last_play_time INTEGER,
                    tokens_earned INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (puuid) REFERENCES summoners(puuid),
                    UNIQUE(puuid, champion_id)
                )
            ''')

            # Table 9: Patches history
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS patches (
                    patch TEXT PRIMARY KEY,
                    release_date DATE,
                    data_dragon_version TEXT,
                    notes_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Table 10: Champion stats per patch (winrate, pickrate, banrate)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS champion_patch_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    champion_id INTEGER NOT NULL,
                    patch TEXT NOT NULL,
                    -- Calculated from our data
                    games_played INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    bans INTEGER DEFAULT 0,
                    -- Calculated rates
                    winrate REAL,
                    pickrate REAL,
                    banrate REAL,
                    -- Per role stats
                    top_games INTEGER DEFAULT 0,
                    jungle_games INTEGER DEFAULT 0,
                    mid_games INTEGER DEFAULT 0,
                    adc_games INTEGER DEFAULT 0,
                    support_games INTEGER DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(champion_id, patch)
                )
            ''')

            # Table 11: Match timeline snapshots (gold per minute)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS match_timeline (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT NOT NULL,
                    minute INTEGER NOT NULL,
                    -- Team gold totals
                    team_100_gold INTEGER,
                    team_200_gold INTEGER,
                    gold_diff INTEGER,
                    -- Per position gold (team 100)
                    team_100_top_gold INTEGER,
                    team_100_jungle_gold INTEGER,
                    team_100_mid_gold INTEGER,
                    team_100_adc_gold INTEGER,
                    team_100_support_gold INTEGER,
                    -- Per position gold (team 200)
                    team_200_top_gold INTEGER,
                    team_200_jungle_gold INTEGER,
                    team_200_mid_gold INTEGER,
                    team_200_adc_gold INTEGER,
                    team_200_support_gold INTEGER,
                    FOREIGN KEY (match_id) REFERENCES matches(match_id),
                    UNIQUE(match_id, minute)
                )
            ''')

            # Table 12: Match events with timestamps (kills, objectives, buildings)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS match_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    match_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp_ms INTEGER NOT NULL,
                    minute INTEGER,

                    -- For CHAMPION_KILL
                    killer_id INTEGER,
                    victim_id INTEGER,
                    killer_team_id INTEGER,

                    -- For ELITE_MONSTER_KILL
                    monster_type TEXT,
                    monster_subtype TEXT,

                    -- For BUILDING_KILL
                    building_type TEXT,
                    lane_type TEXT,
                    tower_type TEXT,
                    team_id INTEGER,

                    FOREIGN KEY (match_id) REFERENCES matches(match_id)
                )
            ''')

            # Create indices for common queries (only for new tables, player_stats index created in migration)
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_matches_game_creation ON matches(game_creation)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_stats_champion ON player_stats(champion_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_stats_match ON player_stats(match_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_team_stats_match ON team_stats(match_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_champion_mastery_puuid ON champion_mastery(puuid)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_summoner_elo_puuid ON summoner_elo_history(puuid)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timeline_match ON match_timeline(match_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_match ON match_events(match_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_type ON match_events(event_type)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_events_minute ON match_events(minute)')

    def _migrate_schema(self):
        """
        Migrate existing database to new schema.
        Adds new columns to existing tables without losing data.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check existing columns in player_stats
            cursor.execute('PRAGMA table_info(player_stats)')
            existing_player_cols = {row[1] for row in cursor.fetchall()}

            # Add new columns to player_stats if they don't exist
            new_player_cols = [
                ('puuid', 'TEXT'),
                ('riot_id_name', 'TEXT'),
                ('riot_id_tagline', 'TEXT'),
                ('summoner_1_name', 'TEXT'),
                ('summoner_2_name', 'TEXT'),
            ]

            for col_name, col_type in new_player_cols:
                if col_name not in existing_player_cols:
                    try:
                        cursor.execute(f'ALTER TABLE player_stats ADD COLUMN {col_name} {col_type}')
                        print(f"  Added column {col_name} to player_stats")
                    except Exception as e:
                        pass  # Column might already exist

            # Check existing columns in team_stats table
            cursor.execute('PRAGMA table_info(team_stats)')
            existing_team_cols = {row[1] for row in cursor.fetchall()}

            # Add ban name columns to team_stats if they don't exist
            new_team_cols = [
                ('ban_1_name', 'TEXT'),
                ('ban_2_name', 'TEXT'),
                ('ban_3_name', 'TEXT'),
                ('ban_4_name', 'TEXT'),
                ('ban_5_name', 'TEXT'),
            ]

            for col_name, col_type in new_team_cols:
                if col_name not in existing_team_cols:
                    try:
                        cursor.execute(f'ALTER TABLE team_stats ADD COLUMN {col_name} {col_type}')
                        print(f"  Added column {col_name} to team_stats")
                    except Exception as e:
                        pass  # Column might already exist

            # Check existing columns in matches table
            cursor.execute('PRAGMA table_info(matches)')
            existing_match_cols = {row[1] for row in cursor.fetchall()}

            # Add new columns to matches if they don't exist
            new_match_cols = [
                ('region', 'TEXT'),
                ('source_elo', 'TEXT')
            ]

            for col_name, col_type in new_match_cols:
                if col_name not in existing_match_cols:
                    try:
                        cursor.execute(f'ALTER TABLE matches ADD COLUMN {col_name} {col_type}')
                        print(f"  Added column {col_name} to matches")
                    except Exception as e:
                        pass  # Column might already exist

            # Create indices for new columns (ignore if exists)
            try:
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_player_stats_puuid ON player_stats(puuid)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_matches_region ON matches(region)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_matches_source_elo ON matches(source_elo)')
            except:
                pass

            # Create summoner_role_stats cache table (for future performance optimization)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS summoner_role_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    puuid TEXT NOT NULL,
                    snapshot_timestamp INTEGER NOT NULL,

                    -- Games par rôle
                    total_games INTEGER DEFAULT 0,
                    top_games INTEGER DEFAULT 0,
                    jungle_games INTEGER DEFAULT 0,
                    mid_games INTEGER DEFAULT 0,
                    adc_games INTEGER DEFAULT 0,
                    support_games INTEGER DEFAULT 0,

                    -- Victoires par rôle
                    top_wins INTEGER DEFAULT 0,
                    jungle_wins INTEGER DEFAULT 0,
                    mid_wins INTEGER DEFAULT 0,
                    adc_wins INTEGER DEFAULT 0,
                    support_wins INTEGER DEFAULT 0,

                    -- KDA et vision moyens par rôle
                    top_avg_kda REAL,
                    jungle_avg_kda REAL,
                    mid_avg_kda REAL,
                    adc_avg_kda REAL,
                    support_avg_kda REAL,

                    top_avg_vision REAL,
                    jungle_avg_vision REAL,
                    mid_avg_vision REAL,
                    adc_avg_vision REAL,
                    support_avg_vision REAL,

                    -- Séries victoires/défaites
                    current_streak_type TEXT,
                    current_streak_length INTEGER DEFAULT 0,
                    last_3_win_streaks TEXT,
                    last_3_loss_streaks TEXT,

                    -- Champions récents (JSON)
                    recent_champions TEXT,

                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (puuid) REFERENCES summoners(puuid),
                    UNIQUE(puuid, snapshot_timestamp)
                )
            ''')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_summoner_role_stats_puuid ON summoner_role_stats(puuid)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_summoner_role_stats_timestamp ON summoner_role_stats(snapshot_timestamp)')

            # Migrate match_timeline: add level/xp/cs columns
            cursor.execute('PRAGMA table_info(match_timeline)')
            existing_timeline_cols = {row[1] for row in cursor.fetchall()}

            teams = ['100', '200']
            positions = ['top', 'jungle', 'mid', 'adc', 'support']
            new_metrics = ['level', 'xp', 'cs']

            for metric in new_metrics:
                for team in teams:
                    for pos in positions:
                        col_name = f'team_{team}_{pos}_{metric}'
                        if col_name not in existing_timeline_cols:
                            col_type = 'INTEGER'
                            try:
                                cursor.execute(f'ALTER TABLE match_timeline ADD COLUMN {col_name} {col_type}')
                                print(f"  Added column {col_name} to match_timeline")
                            except Exception:
                                pass

    def _enable_wal(self):
        """
        Enable WAL (Write-Ahead Logging) mode for better concurrent access.
        This allows multiple processes to read/write simultaneously.
        """
        with self.get_connection() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=30000')  # 30 second timeout for locked DB

    def match_exists(self, match_id: str) -> bool:
        """Check if match already exists in database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM matches WHERE match_id = ?', (match_id,))
            return cursor.fetchone() is not None

    def get_collected_match_ids(self) -> Set[str]:
        """Get set of all collected match IDs"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT match_id FROM matches')
            return {row[0] for row in cursor.fetchall()}

    def insert_match(self, match_data: Dict[str, Any], source_elo: str = None) -> bool:
        """
        Insert complete match with all related data.
        Uses transaction for atomic insert.

        Args:
            match_data: Raw match data from Riot API
            source_elo: The elo tier of the player used to find this match (CHALLENGER, GRANDMASTER, MASTER, DIAMOND)

        Returns:
            True if inserted, False if already exists
        """
        info = match_data.get("info", {})
        metadata = match_data.get("metadata", {})
        match_id = metadata.get("matchId")

        if not match_id:
            return False

        # Check if already exists
        if self.match_exists(match_id):
            return False

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Insert match info
            teams = info.get("teams", [])
            team_100_win = None
            team_100_early_surrendered = False
            team_200_early_surrendered = False

            for team in teams:
                if team.get("teamId") == 100:
                    team_100_win = team.get("win")
                    team_100_early_surrendered = team.get("teamEarlySurrendered", False)
                elif team.get("teamId") == 200:
                    team_200_early_surrendered = team.get("teamEarlySurrendered", False)

            cursor.execute('''
                INSERT INTO matches (
                    match_id, region, source_elo, game_creation, game_duration, game_version,
                    queue_id, map_id, game_mode, game_type,
                    team_100_win, team_100_early_surrendered, team_200_early_surrendered
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                match_id,
                REGION,
                source_elo,
                info.get("gameCreation"),
                info.get("gameDuration"),
                info.get("gameVersion"),
                info.get("queueId"),
                info.get("mapId"),
                info.get("gameMode"),
                info.get("gameType"),
                team_100_win,
                team_100_early_surrendered,
                team_200_early_surrendered
            ))

            # Insert team stats
            # Get champion data for ban names
            try:
                from champion_data import get_champion_data
                champion_data = get_champion_data()
            except Exception:
                champion_data = None

            for team in teams:
                team_id = team.get("teamId")
                objectives = team.get("objectives", {})
                bans = team.get("bans", [])

                # Prepare ban champion IDs and names
                ban_ids = [None] * 5
                ban_names = [None] * 5
                for i, ban in enumerate(bans[:5]):
                    ban_id = ban.get("championId")
                    ban_ids[i] = ban_id
                    if champion_data and ban_id and ban_id > 0:
                        ban_names[i] = champion_data.get_champion_name(ban_id)

                cursor.execute('''
                    INSERT INTO team_stats (
                        match_id, team_id,
                        first_blood, first_tower, first_inhibitor,
                        first_dragon, first_rift_herald, first_baron,
                        dragon_kills, baron_kills, tower_kills,
                        inhibitor_kills, rift_herald_kills,
                        ban_1_champion_id, ban_2_champion_id, ban_3_champion_id,
                        ban_4_champion_id, ban_5_champion_id,
                        ban_1_name, ban_2_name, ban_3_name, ban_4_name, ban_5_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    match_id, team_id,
                    objectives.get("champion", {}).get("first", False),
                    objectives.get("tower", {}).get("first", False),
                    objectives.get("inhibitor", {}).get("first", False),
                    objectives.get("dragon", {}).get("first", False),
                    objectives.get("riftHerald", {}).get("first", False),
                    objectives.get("baron", {}).get("first", False),
                    objectives.get("dragon", {}).get("kills", 0),
                    objectives.get("baron", {}).get("kills", 0),
                    objectives.get("tower", {}).get("kills", 0),
                    objectives.get("inhibitor", {}).get("kills", 0),
                    objectives.get("riftHerald", {}).get("kills", 0),
                    ban_ids[0], ban_ids[1], ban_ids[2], ban_ids[3], ban_ids[4],
                    ban_names[0], ban_names[1], ban_names[2], ban_names[3], ban_names[4]
                ))

            # Insert player stats
            # Import summoner spell name function
            try:
                from champion_data import get_summoner_spell_name
            except Exception:
                get_summoner_spell_name = lambda x: f"Spell_{x}"

            position_map = {
                "TOP": "top",
                "JUNGLE": "jungle",
                "MIDDLE": "mid",
                "BOTTOM": "adc",
                "UTILITY": "support"
            }

            for participant in info.get("participants", []):
                team_id = participant.get("teamId")
                position = position_map.get(
                    participant.get("teamPosition"),
                    participant.get("teamPosition", "unknown")
                )
                challenges = participant.get("challenges", {})

                # Get summoner spell names
                summoner_1_id = participant.get("summoner1Id")
                summoner_2_id = participant.get("summoner2Id")
                summoner_1_name = get_summoner_spell_name(summoner_1_id) if summoner_1_id else None
                summoner_2_name = get_summoner_spell_name(summoner_2_id) if summoner_2_id else None

                cursor.execute('''
                    INSERT INTO player_stats (
                        match_id, team_id, position,
                        puuid, riot_id_name, riot_id_tagline,
                        champion_id, champion_name, champ_level,
                        summoner_1_id, summoner_2_id, summoner_1_name, summoner_2_name,
                        kills, deaths, assists,
                        total_damage_dealt, total_damage_to_champions, total_damage_taken,
                        true_damage_dealt, physical_damage_dealt, magic_damage_dealt,
                        gold_earned, total_minions_killed, neutral_minions_killed,
                        vision_score, wards_placed, wards_killed, vision_wards_bought,
                        enemy_champion_immobilizations,
                        first_blood_kill, first_tower_kill,
                        turret_kills, inhibitor_kills,
                        largest_killing_spree, largest_multi_kill, killing_sprees,
                        double_kills, triple_kills, quadra_kills, penta_kills,
                        damage_per_minute, damage_taken_percentage, gold_per_minute,
                        team_damage_percentage, kill_participation, kda,
                        lane_minions_first_10_min, turret_plates_taken, solo_kills
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    match_id, team_id, position,
                    participant.get("puuid"),
                    participant.get("riotIdGameName"),
                    participant.get("riotIdTagline"),
                    participant.get("championId"),
                    participant.get("championName"),
                    participant.get("champLevel"),
                    summoner_1_id,
                    summoner_2_id,
                    summoner_1_name,
                    summoner_2_name,
                    participant.get("kills"),
                    participant.get("deaths"),
                    participant.get("assists"),
                    participant.get("totalDamageDealt"),
                    participant.get("totalDamageDealtToChampions"),
                    participant.get("totalDamageTaken"),
                    participant.get("trueDamageDealt"),
                    participant.get("physicalDamageDealt"),
                    participant.get("magicDamageDealt"),
                    participant.get("goldEarned"),
                    participant.get("totalMinionsKilled"),
                    participant.get("neutralMinionsKilled"),
                    participant.get("visionScore"),
                    participant.get("wardsPlaced"),
                    participant.get("wardsKilled"),
                    participant.get("visionWardsBoughtInGame"),
                    participant.get("enemyChampionImmobilizations", 0),
                    participant.get("firstBloodKill"),
                    participant.get("firstTowerKill"),
                    participant.get("turretKills"),
                    participant.get("inhibitorKills"),
                    participant.get("largestKillingSpree"),
                    participant.get("largestMultiKill"),
                    participant.get("killingSprees"),
                    participant.get("doubleKills"),
                    participant.get("tripleKills"),
                    participant.get("quadraKills"),
                    participant.get("pentaKills"),
                    challenges.get("damagePerMinute"),
                    challenges.get("damageTakenOnTeamPercentage"),
                    challenges.get("goldPerMinute"),
                    challenges.get("teamDamagePercentage"),
                    challenges.get("killParticipation"),
                    challenges.get("kda"),
                    challenges.get("laneMinionsFirst10Minutes"),
                    challenges.get("turretPlatesTaken"),
                    challenges.get("soloKills")
                ))

            return True

    def insert_matches_batch(self, matches: list, source_elo: str = None) -> int:
        """
        Insert multiple matches in a single transaction for better performance.

        Args:
            matches: List of (match_id, match_data) tuples from Riot API
            source_elo: The elo tier of the player used to find these matches (CHALLENGER, GRANDMASTER, MASTER, DIAMOND)

        Returns:
            Number of successfully inserted matches
        """
        if not matches:
            return 0

        inserted_count = 0

        with self.get_connection() as conn:
            cursor = conn.cursor()

            for match_id, match_data in matches:
                # Check if already exists
                cursor.execute('SELECT 1 FROM matches WHERE match_id = ?', (match_id,))
                if cursor.fetchone():
                    continue

                info = match_data.get("info", {})
                metadata = match_data.get("metadata", {})

                if not match_id:
                    continue

                # Extract team info
                teams = info.get("teams", [])
                team_100_win = None
                team_100_early_surrendered = False
                team_200_early_surrendered = False

                for team in teams:
                    if team.get("teamId") == 100:
                        team_100_win = team.get("win")
                        team_100_early_surrendered = team.get("teamEarlySurrendered", False)
                    elif team.get("teamId") == 200:
                        team_200_early_surrendered = team.get("teamEarlySurrendered", False)

                # Insert match
                cursor.execute('''
                    INSERT INTO matches (
                        match_id, region, source_elo, game_creation, game_duration, game_version,
                        queue_id, map_id, game_mode, game_type,
                        team_100_win, team_100_early_surrendered, team_200_early_surrendered
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    match_id,
                    REGION,
                    source_elo,
                    info.get("gameCreation"),
                    info.get("gameDuration"),
                    info.get("gameVersion"),
                    info.get("queueId"),
                    info.get("mapId"),
                    info.get("gameMode"),
                    info.get("gameType"),
                    team_100_win,
                    team_100_early_surrendered,
                    team_200_early_surrendered
                ))

                # Insert team stats
                # Get champion data for ban names (once per batch for efficiency)
                try:
                    from champion_data import get_champion_data
                    champion_data = get_champion_data()
                except Exception:
                    champion_data = None

                for team in teams:
                    team_id = team.get("teamId")
                    objectives = team.get("objectives", {})
                    bans = team.get("bans", [])

                    ban_ids = [None] * 5
                    ban_names = [None] * 5
                    for i, ban in enumerate(bans[:5]):
                        ban_id = ban.get("championId")
                        ban_ids[i] = ban_id
                        if champion_data and ban_id and ban_id > 0:
                            ban_names[i] = champion_data.get_champion_name(ban_id)

                    cursor.execute('''
                        INSERT INTO team_stats (
                            match_id, team_id,
                            first_blood, first_tower, first_inhibitor,
                            first_dragon, first_rift_herald, first_baron,
                            dragon_kills, baron_kills, tower_kills,
                            inhibitor_kills, rift_herald_kills,
                            ban_1_champion_id, ban_2_champion_id, ban_3_champion_id,
                            ban_4_champion_id, ban_5_champion_id,
                            ban_1_name, ban_2_name, ban_3_name, ban_4_name, ban_5_name
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        match_id, team_id,
                        objectives.get("champion", {}).get("first", False),
                        objectives.get("tower", {}).get("first", False),
                        objectives.get("inhibitor", {}).get("first", False),
                        objectives.get("dragon", {}).get("first", False),
                        objectives.get("riftHerald", {}).get("first", False),
                        objectives.get("baron", {}).get("first", False),
                        objectives.get("dragon", {}).get("kills", 0),
                        objectives.get("baron", {}).get("kills", 0),
                        objectives.get("tower", {}).get("kills", 0),
                        objectives.get("inhibitor", {}).get("kills", 0),
                        objectives.get("riftHerald", {}).get("kills", 0),
                        ban_ids[0], ban_ids[1], ban_ids[2], ban_ids[3], ban_ids[4],
                        ban_names[0], ban_names[1], ban_names[2], ban_names[3], ban_names[4]
                    ))

                # Insert player stats
                # Import summoner spell name function
                try:
                    from champion_data import get_summoner_spell_name
                except Exception:
                    get_summoner_spell_name = lambda x: f"Spell_{x}"

                position_map = {
                    "TOP": "top",
                    "JUNGLE": "jungle",
                    "MIDDLE": "mid",
                    "BOTTOM": "adc",
                    "UTILITY": "support"
                }

                for participant in info.get("participants", []):
                    team_id = participant.get("teamId")
                    position = position_map.get(
                        participant.get("teamPosition"),
                        participant.get("teamPosition", "unknown")
                    )
                    challenges = participant.get("challenges", {})

                    # Get summoner spell names
                    summoner_1_id = participant.get("summoner1Id")
                    summoner_2_id = participant.get("summoner2Id")
                    summoner_1_name = get_summoner_spell_name(summoner_1_id) if summoner_1_id else None
                    summoner_2_name = get_summoner_spell_name(summoner_2_id) if summoner_2_id else None

                    cursor.execute('''
                        INSERT INTO player_stats (
                            match_id, team_id, position,
                            puuid, riot_id_name, riot_id_tagline,
                            champion_id, champion_name, champ_level,
                            summoner_1_id, summoner_2_id, summoner_1_name, summoner_2_name,
                            kills, deaths, assists,
                            total_damage_dealt, total_damage_to_champions, total_damage_taken,
                            true_damage_dealt, physical_damage_dealt, magic_damage_dealt,
                            gold_earned, total_minions_killed, neutral_minions_killed,
                            vision_score, wards_placed, wards_killed, vision_wards_bought,
                            enemy_champion_immobilizations,
                            first_blood_kill, first_tower_kill,
                            turret_kills, inhibitor_kills,
                            largest_killing_spree, largest_multi_kill, killing_sprees,
                            double_kills, triple_kills, quadra_kills, penta_kills,
                            damage_per_minute, damage_taken_percentage, gold_per_minute,
                            team_damage_percentage, kill_participation, kda,
                            lane_minions_first_10_min, turret_plates_taken, solo_kills
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        match_id, team_id, position,
                        participant.get("puuid"),
                        participant.get("riotIdGameName"),
                        participant.get("riotIdTagline"),
                        participant.get("championId"),
                        participant.get("championName"),
                        participant.get("champLevel"),
                        summoner_1_id,
                        summoner_2_id,
                        summoner_1_name,
                        summoner_2_name,
                        participant.get("kills"),
                        participant.get("deaths"),
                        participant.get("assists"),
                        participant.get("totalDamageDealt"),
                        participant.get("totalDamageDealtToChampions"),
                        participant.get("totalDamageTaken"),
                        participant.get("trueDamageDealt"),
                        participant.get("physicalDamageDealt"),
                        participant.get("magicDamageDealt"),
                        participant.get("goldEarned"),
                        participant.get("totalMinionsKilled"),
                        participant.get("neutralMinionsKilled"),
                        participant.get("visionScore"),
                        participant.get("wardsPlaced"),
                        participant.get("wardsKilled"),
                        participant.get("visionWardsBoughtInGame"),
                        participant.get("enemyChampionImmobilizations", 0),
                        participant.get("firstBloodKill"),
                        participant.get("firstTowerKill"),
                        participant.get("turretKills"),
                        participant.get("inhibitorKills"),
                        participant.get("largestKillingSpree"),
                        participant.get("largestMultiKill"),
                        participant.get("killingSprees"),
                        participant.get("doubleKills"),
                        participant.get("tripleKills"),
                        participant.get("quadraKills"),
                        participant.get("pentaKills"),
                        challenges.get("damagePerMinute"),
                        challenges.get("damageTakenOnTeamPercentage"),
                        challenges.get("goldPerMinute"),
                        challenges.get("teamDamagePercentage"),
                        challenges.get("killParticipation"),
                        challenges.get("kda"),
                        challenges.get("laneMinionsFirst10Minutes"),
                        challenges.get("turretPlatesTaken"),
                        challenges.get("soloKills")
                    ))

                inserted_count += 1

        return inserted_count

    def save_player_progress(self, puuid: str):
        """Mark player as processed (updates timestamp if already exists)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO collection_progress (puuid, processed_at)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(puuid) DO UPDATE SET processed_at = CURRENT_TIMESTAMP
            ''', (puuid,))

    def is_player_processed(self, puuid: str, refresh_hours: int = 24) -> bool:
        """
        Check if player was recently processed.

        Args:
            puuid: Player's PUUID
            refresh_hours: Hours after which a player can be re-processed (default: 24h)
                          Set to 0 to never re-process (old behavior)

        Returns:
            True if player was processed within refresh_hours, False otherwise
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if refresh_hours > 0:
                # Check if processed within the last refresh_hours
                cursor.execute('''
                    SELECT 1 FROM collection_progress
                    WHERE puuid = ?
                    AND processed_at > datetime('now', ?)
                ''', (puuid, f'-{refresh_hours} hours'))
            else:
                # Old behavior: check if ever processed
                cursor.execute(
                    'SELECT 1 FROM collection_progress WHERE puuid = ?',
                    (puuid,)
                )
            return cursor.fetchone() is not None

    def get_processed_players(self) -> List[str]:
        """Get list of all processed player PUUIDs"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT puuid FROM collection_progress')
            return [row[0] for row in cursor.fetchall()]

    def clear_processed_players(self):
        """Clear all processed players to allow re-fetching new matches"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM collection_progress')
            return cursor.rowcount

    def clear_processed_players_by_prefix(self, prefix: str):
        """Clear processed players with a specific prefix (e.g., 'sid_' for Master+ players)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM collection_progress WHERE puuid LIKE ?', (f'{prefix}%',))
            return cursor.rowcount

    def update_stat(self, key: str, value: Any):
        """Update a collection statistic"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO collection_stats (key, value)
                VALUES (?, ?)
            ''', (key, json.dumps(value)))

    def get_stat(self, key: str, default: Any = None) -> Any:
        """Get a collection statistic"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT value FROM collection_stats WHERE key = ?',
                (key,)
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return default

    def get_stats(self) -> Dict[str, Any]:
        """Get all collection statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Count matches
            cursor.execute('SELECT COUNT(*) FROM matches')
            match_count = cursor.fetchone()[0]

            # Count players
            cursor.execute('SELECT COUNT(*) FROM collection_progress')
            player_count = cursor.fetchone()[0]

            # Get stored stats
            stats = {
                'total_matches': match_count,
                'processed_players': player_count,
                'total_requests': self.get_stat('total_requests', 0),
                'successful_requests': self.get_stat('successful_requests', 0),
                'rate_limit_errors': self.get_stat('rate_limit_errors', 0),
                'other_errors': self.get_stat('other_errors', 0),
                'last_page': self.get_stat('last_page', 1),
                'last_player_index': self.get_stat('last_player_index', 0)
            }

            return stats

    def increment_stat(self, key: str, amount: int = 1):
        """Increment a numeric statistic"""
        current = self.get_stat(key, 0)
        self.update_stat(key, current + amount)

    # ================================================================
    # Summoner Methods (NEW)
    # ================================================================

    def upsert_summoner(self, puuid: str, riot_id_name: str = None, riot_id_tagline: str = None,
                        tier: str = None, rank: str = None, lp: int = None):
        """Insert or update summoner info"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO summoners (puuid, riot_id_name, riot_id_tagline, current_tier, current_rank, current_lp, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(puuid) DO UPDATE SET
                    riot_id_name = COALESCE(excluded.riot_id_name, riot_id_name),
                    riot_id_tagline = COALESCE(excluded.riot_id_tagline, riot_id_tagline),
                    current_tier = COALESCE(excluded.current_tier, current_tier),
                    current_rank = COALESCE(excluded.current_rank, current_rank),
                    current_lp = COALESCE(excluded.current_lp, current_lp),
                    total_games_tracked = total_games_tracked + 1,
                    last_seen_at = CURRENT_TIMESTAMP,
                    last_updated_at = CURRENT_TIMESTAMP
            ''', (puuid, riot_id_name, riot_id_tagline, tier, rank, lp))

    def get_summoner(self, puuid: str) -> Optional[Dict]:
        """Get summoner info by PUUID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM summoners WHERE puuid = ?', (puuid,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def record_elo_history(self, puuid: str, patch: str, tier: str, rank: str, lp: int):
        """Record summoner's elo for a specific patch"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO summoner_elo_history (puuid, patch, tier, rank, lp)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(puuid, patch) DO UPDATE SET
                    tier = excluded.tier,
                    rank = excluded.rank,
                    lp = excluded.lp,
                    recorded_at = CURRENT_TIMESTAMP
            ''', (puuid, patch, tier, rank, lp))

    # ================================================================
    # Champion Mastery Methods (NEW)
    # ================================================================

    def upsert_champion_mastery(self, puuid: str, champion_id: int, champion_level: int,
                                 champion_points: int, last_play_time: int = None, tokens_earned: int = 0):
        """Insert or update champion mastery"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO champion_mastery (puuid, champion_id, champion_level, champion_points, last_play_time, tokens_earned)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(puuid, champion_id) DO UPDATE SET
                    champion_level = excluded.champion_level,
                    champion_points = excluded.champion_points,
                    last_play_time = excluded.last_play_time,
                    tokens_earned = excluded.tokens_earned,
                    updated_at = CURRENT_TIMESTAMP
            ''', (puuid, champion_id, champion_level, champion_points, last_play_time, tokens_earned))

    def get_summoner_mastery(self, puuid: str, limit: int = None) -> List[Dict]:
        """Get champion mastery for a summoner, sorted by points"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM champion_mastery WHERE puuid = ? ORDER BY champion_points DESC'
            if limit:
                query += f' LIMIT {limit}'
            cursor.execute(query, (puuid,))
            return [dict(row) for row in cursor.fetchall()]

    def get_mastery_for_champion(self, puuid: str, champion_id: int) -> Optional[Dict]:
        """Get mastery for a specific champion"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM champion_mastery WHERE puuid = ? AND champion_id = ?',
                (puuid, champion_id)
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    # ================================================================
    # Patch Methods (NEW)
    # ================================================================

    def upsert_patch(self, patch: str, release_date: str = None, data_dragon_version: str = None):
        """Insert or update patch info"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO patches (patch, release_date, data_dragon_version)
                VALUES (?, ?, ?)
                ON CONFLICT(patch) DO UPDATE SET
                    release_date = COALESCE(excluded.release_date, release_date),
                    data_dragon_version = COALESCE(excluded.data_dragon_version, data_dragon_version)
            ''', (patch, release_date, data_dragon_version))

    def get_patches(self) -> List[Dict]:
        """Get all patches"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM patches ORDER BY patch DESC')
            return [dict(row) for row in cursor.fetchall()]

    # ================================================================
    # Champion Patch Stats Methods (NEW)
    # ================================================================

    def update_champion_patch_stats(self, champion_id: int, patch: str, win: bool, position: str):
        """Update champion stats for a patch (called after each match insert)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get position column name
            position_col = f'{position}_games' if position in ['top', 'jungle', 'mid', 'adc', 'support'] else None

            # Upsert champion stats
            cursor.execute('''
                INSERT INTO champion_patch_stats (champion_id, patch, games_played, wins)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(champion_id, patch) DO UPDATE SET
                    games_played = games_played + 1,
                    wins = wins + ?,
                    updated_at = CURRENT_TIMESTAMP
            ''', (champion_id, patch, 1 if win else 0, 1 if win else 0))

            # Update position-specific count if valid position
            if position_col:
                cursor.execute(f'''
                    UPDATE champion_patch_stats
                    SET {position_col} = {position_col} + 1
                    WHERE champion_id = ? AND patch = ?
                ''', (champion_id, patch))

    def recalculate_champion_rates(self, patch: str):
        """Recalculate winrate/pickrate/banrate for a patch"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get total games for this patch
            cursor.execute('''
                SELECT COUNT(*) FROM matches WHERE game_version LIKE ?
            ''', (f'{patch}%',))
            total_games = cursor.fetchone()[0]

            if total_games == 0:
                return

            # Update rates
            cursor.execute('''
                UPDATE champion_patch_stats
                SET winrate = CAST(wins AS REAL) / NULLIF(games_played, 0),
                    pickrate = CAST(games_played AS REAL) / ? / 10,
                    banrate = CAST(bans AS REAL) / ? / 10
                WHERE patch = ?
            ''', (total_games, total_games, patch))

    def get_champion_role_distribution(self, champion_id: int = None, patch: str = None) -> pd.DataFrame:
        """
        Get role distribution for champions (% of games played in each role).

        SRZ request: "% des games où il est joué supp" etc.

        Args:
            champion_id: Optional - filter for specific champion
            patch: Optional - filter for specific patch

        Returns:
            DataFrame with champion_id, champion_name, patch, and percentage columns:
            top_pct, jungle_pct, mid_pct, adc_pct, support_pct
        """
        with self.get_connection() as conn:
            query = '''
                SELECT
                    champion_id,
                    patch,
                    games_played,
                    top_games,
                    jungle_games,
                    mid_games,
                    adc_games,
                    support_games,
                    ROUND(CAST(top_games AS REAL) / NULLIF(games_played, 0) * 100, 2) as top_pct,
                    ROUND(CAST(jungle_games AS REAL) / NULLIF(games_played, 0) * 100, 2) as jungle_pct,
                    ROUND(CAST(mid_games AS REAL) / NULLIF(games_played, 0) * 100, 2) as mid_pct,
                    ROUND(CAST(adc_games AS REAL) / NULLIF(games_played, 0) * 100, 2) as adc_pct,
                    ROUND(CAST(support_games AS REAL) / NULLIF(games_played, 0) * 100, 2) as support_pct
                FROM champion_patch_stats
                WHERE 1=1
            '''
            params = []

            if champion_id:
                query += ' AND champion_id = ?'
                params.append(champion_id)

            if patch:
                query += ' AND patch = ?'
                params.append(patch)

            query += ' ORDER BY patch DESC, games_played DESC'

            df = pd.read_sql_query(query, conn, params=params if params else None)

        if len(df) > 0:
            try:
                from champion_data import get_champion_data
                cd = get_champion_data()
                df['champion_name'] = df['champion_id'].apply(cd.get_champion_name)
            except Exception:
                df['champion_name'] = df['champion_id'].apply(lambda x: f'Champion_{x}')

        return df

    def populate_champion_stats_from_matches(self, patch: str = None):
        """
        Populate champion_patch_stats from existing player_stats data.

        This should be run after collecting matches to calculate per-champion stats.

        Args:
            patch: Optional patch filter. If None, processes all matches.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Build query to aggregate stats
            patch_filter = ""
            params = []
            if patch:
                patch_filter = "WHERE m.game_version LIKE ?"
                params.append(f'{patch}%')

            # Aggregate champion stats per patch
            cursor.execute(f'''
                INSERT OR REPLACE INTO champion_patch_stats
                    (champion_id, patch, games_played, wins, top_games, jungle_games, mid_games, adc_games, support_games)
                SELECT
                    ps.champion_id,
                    SUBSTR(m.game_version, 1, INSTR(m.game_version || '.', '.') + INSTR(SUBSTR(m.game_version, INSTR(m.game_version, '.') + 1) || '.', '.') - 1) as patch,
                    COUNT(*) as games_played,
                    SUM(CASE WHEN (ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0) THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN ps.position = 'top' THEN 1 ELSE 0 END) as top_games,
                    SUM(CASE WHEN ps.position = 'jungle' THEN 1 ELSE 0 END) as jungle_games,
                    SUM(CASE WHEN ps.position = 'mid' THEN 1 ELSE 0 END) as mid_games,
                    SUM(CASE WHEN ps.position = 'adc' THEN 1 ELSE 0 END) as adc_games,
                    SUM(CASE WHEN ps.position = 'support' THEN 1 ELSE 0 END) as support_games
                FROM player_stats ps
                JOIN matches m ON ps.match_id = m.match_id
                {patch_filter}
                GROUP BY ps.champion_id, SUBSTR(m.game_version, 1, INSTR(m.game_version || '.', '.') + INSTR(SUBSTR(m.game_version, INSTR(m.game_version, '.') + 1) || '.', '.') - 1)
            ''', params)

            # Now update bans count
            cursor.execute(f'''
                UPDATE champion_patch_stats
                SET bans = (
                    SELECT COUNT(*)
                    FROM team_stats ts
                    JOIN matches m ON ts.match_id = m.match_id
                    WHERE (
                        ts.ban_1_champion_id = champion_patch_stats.champion_id OR
                        ts.ban_2_champion_id = champion_patch_stats.champion_id OR
                        ts.ban_3_champion_id = champion_patch_stats.champion_id OR
                        ts.ban_4_champion_id = champion_patch_stats.champion_id OR
                        ts.ban_5_champion_id = champion_patch_stats.champion_id
                    )
                    AND SUBSTR(m.game_version, 1, INSTR(m.game_version || '.', '.') + INSTR(SUBSTR(m.game_version, INSTR(m.game_version, '.') + 1) || '.', '.') - 1) = champion_patch_stats.patch
                )
            ''')

    def get_champion_stats_for_patch(self, patch: str) -> List[Dict]:
        """Get all champion stats for a patch"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM champion_patch_stats
                WHERE patch = ?
                ORDER BY games_played DESC
            ''', (patch,))
            return [dict(row) for row in cursor.fetchall()]

    # ================================================================
    # Backfill Methods - Fill missing data in existing records
    # ================================================================

    def backfill_ban_names(self) -> int:
        """
        Backfill ban champion names from IDs for existing team_stats records.

        Returns:
            Number of records updated
        """
        from champion_data import get_champion_data
        cd = get_champion_data()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get all team_stats with missing ban names
            cursor.execute('''
                SELECT id, ban_1_champion_id, ban_2_champion_id, ban_3_champion_id,
                       ban_4_champion_id, ban_5_champion_id
                FROM team_stats
                WHERE (ban_1_name IS NULL AND ban_1_champion_id IS NOT NULL)
                   OR (ban_2_name IS NULL AND ban_2_champion_id IS NOT NULL)
                   OR (ban_3_name IS NULL AND ban_3_champion_id IS NOT NULL)
                   OR (ban_4_name IS NULL AND ban_4_champion_id IS NOT NULL)
                   OR (ban_5_name IS NULL AND ban_5_champion_id IS NOT NULL)
            ''')

            rows = cursor.fetchall()
            updated = 0

            for row in rows:
                row_id = row[0]
                ban_names = []
                for i in range(1, 6):
                    ban_id = row[i]
                    if ban_id and ban_id > 0:
                        ban_names.append(cd.get_champion_name(ban_id))
                    else:
                        ban_names.append(None)

                cursor.execute('''
                    UPDATE team_stats
                    SET ban_1_name = ?, ban_2_name = ?, ban_3_name = ?,
                        ban_4_name = ?, ban_5_name = ?
                    WHERE id = ?
                ''', (*ban_names, row_id))
                updated += 1

            return updated

    def backfill_summoner_spell_names(self) -> int:
        """
        Backfill summoner spell names from IDs for existing player_stats records.

        Returns:
            Number of records updated
        """
        from champion_data import get_summoner_spell_name

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get all player_stats with missing spell names
            cursor.execute('''
                SELECT id, summoner_1_id, summoner_2_id
                FROM player_stats
                WHERE (summoner_1_name IS NULL AND summoner_1_id IS NOT NULL)
                   OR (summoner_2_name IS NULL AND summoner_2_id IS NOT NULL)
            ''')

            rows = cursor.fetchall()
            updated = 0

            for row in rows:
                row_id, spell_1_id, spell_2_id = row
                spell_1_name = get_summoner_spell_name(spell_1_id) if spell_1_id else None
                spell_2_name = get_summoner_spell_name(spell_2_id) if spell_2_id else None

                cursor.execute('''
                    UPDATE player_stats
                    SET summoner_1_name = ?, summoner_2_name = ?
                    WHERE id = ?
                ''', (spell_1_name, spell_2_name, row_id))
                updated += 1

            return updated

    def backfill_source_elo(self, default_elo: str = "UNKNOWN") -> int:
        """
        Backfill source_elo for matches that don't have it.

        Args:
            default_elo: Default value to use (default: "UNKNOWN")

        Returns:
            Number of records updated
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE matches
                SET source_elo = ?
                WHERE source_elo IS NULL
            ''', (default_elo,))
            return cursor.rowcount

    # ================================================================
    # Match Timeline Methods (NEW)
    # ================================================================

    def insert_timeline_frame(self, match_id: str, minute: int, team_gold: Dict, position_gold: Dict,
                              position_level: Dict = None, position_xp: Dict = None, position_cs: Dict = None):
        """Insert a timeline frame (gold/level/xp/cs at minute M)"""
        position_level = position_level or {}
        position_xp = position_xp or {}
        position_cs = position_cs or {}

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO match_timeline (
                    match_id, minute,
                    team_100_gold, team_200_gold, gold_diff,
                    team_100_top_gold, team_100_jungle_gold, team_100_mid_gold, team_100_adc_gold, team_100_support_gold,
                    team_200_top_gold, team_200_jungle_gold, team_200_mid_gold, team_200_adc_gold, team_200_support_gold,
                    team_100_top_level, team_100_jungle_level, team_100_mid_level, team_100_adc_level, team_100_support_level,
                    team_200_top_level, team_200_jungle_level, team_200_mid_level, team_200_adc_level, team_200_support_level,
                    team_100_top_xp, team_100_jungle_xp, team_100_mid_xp, team_100_adc_xp, team_100_support_xp,
                    team_200_top_xp, team_200_jungle_xp, team_200_mid_xp, team_200_adc_xp, team_200_support_xp,
                    team_100_top_cs, team_100_jungle_cs, team_100_mid_cs, team_100_adc_cs, team_100_support_cs,
                    team_200_top_cs, team_200_jungle_cs, team_200_mid_cs, team_200_adc_cs, team_200_support_cs
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                match_id, minute,
                team_gold.get('team_100', 0), team_gold.get('team_200', 0),
                team_gold.get('team_100', 0) - team_gold.get('team_200', 0),
                position_gold.get('team_100_top', 0), position_gold.get('team_100_jungle', 0),
                position_gold.get('team_100_mid', 0), position_gold.get('team_100_adc', 0),
                position_gold.get('team_100_support', 0),
                position_gold.get('team_200_top', 0), position_gold.get('team_200_jungle', 0),
                position_gold.get('team_200_mid', 0), position_gold.get('team_200_adc', 0),
                position_gold.get('team_200_support', 0),
                # Level
                position_level.get('team_100_top'), position_level.get('team_100_jungle'),
                position_level.get('team_100_mid'), position_level.get('team_100_adc'),
                position_level.get('team_100_support'),
                position_level.get('team_200_top'), position_level.get('team_200_jungle'),
                position_level.get('team_200_mid'), position_level.get('team_200_adc'),
                position_level.get('team_200_support'),
                # XP
                position_xp.get('team_100_top'), position_xp.get('team_100_jungle'),
                position_xp.get('team_100_mid'), position_xp.get('team_100_adc'),
                position_xp.get('team_100_support'),
                position_xp.get('team_200_top'), position_xp.get('team_200_jungle'),
                position_xp.get('team_200_mid'), position_xp.get('team_200_adc'),
                position_xp.get('team_200_support'),
                # CS
                position_cs.get('team_100_top'), position_cs.get('team_100_jungle'),
                position_cs.get('team_100_mid'), position_cs.get('team_100_adc'),
                position_cs.get('team_100_support'),
                position_cs.get('team_200_top'), position_cs.get('team_200_jungle'),
                position_cs.get('team_200_mid'), position_cs.get('team_200_adc'),
                position_cs.get('team_200_support'),
            ))

    def update_timeline_level_xp_cs(self, match_id: str, minute: int,
                                     position_level: Dict, position_xp: Dict, position_cs: Dict):
        """Update existing timeline row with level/xp/cs data (for backfill)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE match_timeline SET
                    team_100_top_level = ?, team_100_jungle_level = ?, team_100_mid_level = ?, team_100_adc_level = ?, team_100_support_level = ?,
                    team_200_top_level = ?, team_200_jungle_level = ?, team_200_mid_level = ?, team_200_adc_level = ?, team_200_support_level = ?,
                    team_100_top_xp = ?, team_100_jungle_xp = ?, team_100_mid_xp = ?, team_100_adc_xp = ?, team_100_support_xp = ?,
                    team_200_top_xp = ?, team_200_jungle_xp = ?, team_200_mid_xp = ?, team_200_adc_xp = ?, team_200_support_xp = ?,
                    team_100_top_cs = ?, team_100_jungle_cs = ?, team_100_mid_cs = ?, team_100_adc_cs = ?, team_100_support_cs = ?,
                    team_200_top_cs = ?, team_200_jungle_cs = ?, team_200_mid_cs = ?, team_200_adc_cs = ?, team_200_support_cs = ?
                WHERE match_id = ? AND minute = ?
            ''', (
                position_level.get('team_100_top'), position_level.get('team_100_jungle'),
                position_level.get('team_100_mid'), position_level.get('team_100_adc'),
                position_level.get('team_100_support'),
                position_level.get('team_200_top'), position_level.get('team_200_jungle'),
                position_level.get('team_200_mid'), position_level.get('team_200_adc'),
                position_level.get('team_200_support'),
                position_xp.get('team_100_top'), position_xp.get('team_100_jungle'),
                position_xp.get('team_100_mid'), position_xp.get('team_100_adc'),
                position_xp.get('team_100_support'),
                position_xp.get('team_200_top'), position_xp.get('team_200_jungle'),
                position_xp.get('team_200_mid'), position_xp.get('team_200_adc'),
                position_xp.get('team_200_support'),
                position_cs.get('team_100_top'), position_cs.get('team_100_jungle'),
                position_cs.get('team_100_mid'), position_cs.get('team_100_adc'),
                position_cs.get('team_100_support'),
                position_cs.get('team_200_top'), position_cs.get('team_200_jungle'),
                position_cs.get('team_200_mid'), position_cs.get('team_200_adc'),
                position_cs.get('team_200_support'),
                match_id, minute,
            ))

    def get_match_timeline(self, match_id: str) -> List[Dict]:
        """Get timeline for a match"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM match_timeline
                WHERE match_id = ?
                ORDER BY minute
            ''', (match_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_gold_at_minute(self, match_id: str, minute: int) -> Optional[Dict]:
        """Get gold snapshot at a specific minute"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM match_timeline
                WHERE match_id = ? AND minute = ?
            ''', (match_id, minute))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def insert_event(self, match_id: str, event_type: str, timestamp_ms: int,
                     killer_id: int = None, victim_id: int = None, killer_team_id: int = None,
                     monster_type: str = None, monster_subtype: str = None,
                     building_type: str = None, lane_type: str = None, tower_type: str = None,
                     team_id: int = None):
        """Insert a match event (kill, objective, building)."""
        minute = timestamp_ms // 60000
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO match_events (
                    match_id, event_type, timestamp_ms, minute,
                    killer_id, victim_id, killer_team_id,
                    monster_type, monster_subtype,
                    building_type, lane_type, tower_type, team_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                match_id, event_type, timestamp_ms, minute,
                killer_id, victim_id, killer_team_id,
                monster_type, monster_subtype,
                building_type, lane_type, tower_type, team_id
            ))

    def get_events_at_minute(self, match_id: str, max_minute: int = 10) -> List[Dict]:
        """Get all events up to a specific minute (e.g., first 10 minutes)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM match_events
                WHERE match_id = ? AND minute <= ?
                ORDER BY timestamp_ms
            ''', (match_id, max_minute))
            return [dict(row) for row in cursor.fetchall()]

    def get_early_game_stats(self, match_id: str, max_minute: int = 10) -> Dict:
        """Get aggregated early game stats (kills, dragons, etc.) up to max_minute."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get kills per team
            cursor.execute('''
                SELECT killer_team_id, COUNT(*) as kills
                FROM match_events
                WHERE match_id = ? AND event_type = 'CHAMPION_KILL' AND minute <= ?
                GROUP BY killer_team_id
            ''', (match_id, max_minute))
            kills = {row[0]: row[1] for row in cursor.fetchall()}

            # Get first blood
            cursor.execute('''
                SELECT killer_team_id, MIN(timestamp_ms) as first_blood_time
                FROM match_events
                WHERE match_id = ? AND event_type = 'CHAMPION_KILL'
            ''', (match_id,))
            first_blood_row = cursor.fetchone()
            first_blood_team = first_blood_row[0] if first_blood_row and first_blood_row[0] else None
            first_blood_time = first_blood_row[1] if first_blood_row else None

            # Get dragons per team (before max_minute)
            cursor.execute('''
                SELECT killer_team_id, COUNT(*) as dragons
                FROM match_events
                WHERE match_id = ? AND event_type = 'ELITE_MONSTER_KILL'
                  AND monster_type = 'DRAGON' AND minute <= ?
                GROUP BY killer_team_id
            ''', (match_id, max_minute))
            dragons = {row[0]: row[1] for row in cursor.fetchall()}

            # Get rift herald (before max_minute)
            cursor.execute('''
                SELECT killer_team_id
                FROM match_events
                WHERE match_id = ? AND event_type = 'ELITE_MONSTER_KILL'
                  AND monster_type = 'RIFTHERALD' AND minute <= ?
                LIMIT 1
            ''', (match_id, max_minute))
            herald_row = cursor.fetchone()
            herald_team = herald_row[0] if herald_row else None

            # Get first tower (check if before max_minute)
            cursor.execute('''
                SELECT team_id, MIN(timestamp_ms) as first_tower_time
                FROM match_events
                WHERE match_id = ? AND event_type = 'BUILDING_KILL'
                  AND building_type = 'TOWER_BUILDING'
            ''', (match_id,))
            tower_row = cursor.fetchone()
            first_tower_lost_team = tower_row[0] if tower_row and tower_row[0] else None
            first_tower_time = tower_row[1] if tower_row else None

            return {
                'kills_team_100': kills.get(100, 0),
                'kills_team_200': kills.get(200, 0),
                'first_blood_team': first_blood_team,
                'first_blood_time_ms': first_blood_time,
                'first_blood_before_10': 1 if first_blood_time and first_blood_time < 600000 else 0,
                'dragons_team_100': dragons.get(100, 0),
                'dragons_team_200': dragons.get(200, 0),
                'herald_team': herald_team,
                'first_tower_lost_team': first_tower_lost_team,
                'first_tower_time_ms': first_tower_time,
                'first_tower_before_10': 1 if first_tower_time and first_tower_time < 600000 else 0,
            }

    def clear_events_for_match(self, match_id: str):
        """Clear all events for a match (for re-processing)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM match_events WHERE match_id = ?', (match_id,))

    # ================================================================
    # Teammates Analysis (NEW)
    # ================================================================

    def get_common_teammates(self, puuid: str, limit: int = 10) -> List[Dict]:
        """Get most frequent teammates for a summoner"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT
                    p2.puuid as teammate_puuid,
                    p2.riot_id_name as teammate_name,
                    COUNT(*) as games_together,
                    SUM(CASE WHEN m.team_100_win = (p1.team_id = 100) THEN 1 ELSE 0 END) as wins_together
                FROM player_stats p1
                JOIN player_stats p2 ON p1.match_id = p2.match_id AND p1.team_id = p2.team_id AND p1.puuid != p2.puuid
                JOIN matches m ON p1.match_id = m.match_id
                WHERE p1.puuid = ?
                GROUP BY p2.puuid, p2.riot_id_name
                ORDER BY games_together DESC
                LIMIT ?
            ''', (puuid, limit))
            return [dict(row) for row in cursor.fetchall()]

    # ================================================================
    # Champion & Invocateur Data Endpoints (SRZ requests)
    # ================================================================

    def get_champions_data(self, patch_list: List[str] = None) -> pd.DataFrame:
        """
        Get champion statistics for multiple patches.

        Args:
            patch_list: List of patches to include (e.g., ["14.23", "14.24"])
                       If None, returns all patches

        Returns:
            DataFrame with columns: champion_id, champion_name, patch,
            games_played, wins, winrate, pickrate, banrate,
            top_games, jungle_games, mid_games, adc_games, support_games
        """
        with self.get_connection() as conn:
            if patch_list:
                placeholders = ','.join(['?' for _ in patch_list])
                query = f'''
                    SELECT * FROM champion_patch_stats
                    WHERE patch IN ({placeholders})
                    ORDER BY patch DESC, games_played DESC
                '''
                df = pd.read_sql_query(query, conn, params=patch_list)
            else:
                df = pd.read_sql_query(
                    'SELECT * FROM champion_patch_stats ORDER BY patch DESC, games_played DESC',
                    conn
                )

        if len(df) > 0:
            # Add champion names from ChampionData
            try:
                from champion_data import get_champion_data
                cd = get_champion_data()
                df['champion_name'] = df['champion_id'].apply(cd.get_champion_name)
            except Exception:
                df['champion_name'] = df['champion_id'].apply(lambda x: f'Champion_{x}')

        return df

    def get_invocateurs_data(self, patch_list: List[str] = None) -> pd.DataFrame:
        """
        Get summoner elo history data for patches.

        Args:
            patch_list: List of patches to include
                       If None, returns all patches

        Returns:
            DataFrame with: puuid, riot_id_name, riot_id_tagline, patch, tier, rank, lp
        """
        with self.get_connection() as conn:
            if patch_list:
                placeholders = ','.join(['?' for _ in patch_list])
                query = f'''
                    SELECT
                        seh.puuid,
                        s.riot_id_name,
                        s.riot_id_tagline,
                        seh.patch,
                        seh.tier,
                        seh.rank,
                        seh.lp,
                        seh.recorded_at
                    FROM summoner_elo_history seh
                    LEFT JOIN summoners s ON seh.puuid = s.puuid
                    WHERE seh.patch IN ({placeholders})
                    ORDER BY seh.patch DESC, seh.lp DESC
                '''
                df = pd.read_sql_query(query, conn, params=patch_list)
            else:
                df = pd.read_sql_query('''
                    SELECT
                        seh.puuid,
                        s.riot_id_name,
                        s.riot_id_tagline,
                        seh.patch,
                        seh.tier,
                        seh.rank,
                        seh.lp,
                        seh.recorded_at
                    FROM summoner_elo_history seh
                    LEFT JOIN summoners s ON seh.puuid = s.puuid
                    ORDER BY seh.patch DESC, seh.lp DESC
                ''', conn)

        return df

    def get_summoner_with_mastery(self, puuid: str) -> Dict:
        """
        Get summoner info with top 5 champion masteries.

        Args:
            puuid: Player's PUUID

        Returns:
            Dict with summoner info + top_champions list
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Get summoner info
            cursor.execute('SELECT * FROM summoners WHERE puuid = ?', (puuid,))
            row = cursor.fetchone()
            summoner = dict(row) if row else {'puuid': puuid}

            # Get top 5 masteries
            cursor.execute('''
                SELECT champion_id, champion_level, champion_points
                FROM champion_mastery
                WHERE puuid = ?
                ORDER BY champion_points DESC
                LIMIT 5
            ''', (puuid,))

            try:
                from champion_data import get_champion_data
                cd = get_champion_data()
                summoner['top_champions'] = [
                    {
                        'champion_id': row[0],
                        'champion_name': cd.get_champion_name(row[0]),
                        'mastery_level': row[1],
                        'mastery_points': row[2]
                    }
                    for row in cursor.fetchall()
                ]
            except Exception:
                summoner['top_champions'] = []

        return summoner

    def export_to_dataframe(self) -> pd.DataFrame:
        """
        Export database to pandas DataFrame for ML.
        Returns a flattened view with one row per match.
        Automatically includes all columns from the matches table.
        """
        with self.get_connection() as conn:
            # Get all columns from matches table dynamically
            cursor = conn.cursor()
            cursor.execute('PRAGMA table_info(matches)')
            match_columns = [row[1] for row in cursor.fetchall()]
            match_select = ', '.join([f'm.{col}' for col in match_columns])

            # Build the query with pivoted player stats
            query = f'''
            SELECT
                {match_select},

                -- Team 100 stats
                t100.first_blood as team_100_first_blood,
                t100.first_tower as team_100_first_tower,
                t100.first_inhibitor as team_100_first_inhibitor,
                t100.first_dragon as team_100_first_dragon,
                t100.first_rift_herald as team_100_first_rift_herald,
                t100.first_baron as team_100_first_baron,
                t100.dragon_kills as team_100_dragon_kills,
                t100.baron_kills as team_100_baron_kills,
                t100.tower_kills as team_100_tower_kills,
                t100.inhibitor_kills as team_100_inhibitor_kills,
                t100.rift_herald_kills as team_100_rift_herald_kills,
                t100.ban_1_champion_id as team_100_ban_1,
                t100.ban_2_champion_id as team_100_ban_2,
                t100.ban_3_champion_id as team_100_ban_3,
                t100.ban_4_champion_id as team_100_ban_4,
                t100.ban_5_champion_id as team_100_ban_5,

                -- Team 200 stats
                t200.first_blood as team_200_first_blood,
                t200.first_tower as team_200_first_tower,
                t200.first_inhibitor as team_200_first_inhibitor,
                t200.first_dragon as team_200_first_dragon,
                t200.first_rift_herald as team_200_first_rift_herald,
                t200.first_baron as team_200_first_baron,
                t200.dragon_kills as team_200_dragon_kills,
                t200.baron_kills as team_200_baron_kills,
                t200.tower_kills as team_200_tower_kills,
                t200.inhibitor_kills as team_200_inhibitor_kills,
                t200.rift_herald_kills as team_200_rift_herald_kills,
                t200.ban_1_champion_id as team_200_ban_1,
                t200.ban_2_champion_id as team_200_ban_2,
                t200.ban_3_champion_id as team_200_ban_3,
                t200.ban_4_champion_id as team_200_ban_4,
                t200.ban_5_champion_id as team_200_ban_5,

                -- Team 100 players (with puuid for player features)
                p100_top.puuid as team_100_top_puuid,
                p100_top.riot_id_name as team_100_top_riot_id_name,
                p100_top.riot_id_tagline as team_100_top_riot_id_tagline,
                p100_top.champion_id as team_100_top_champion_id,
                p100_top.champion_name as team_100_top_champion_name,
                p100_top.champ_level as team_100_top_champ_level,
                p100_top.summoner_1_id as team_100_top_summoner_1_id,
                p100_top.summoner_2_id as team_100_top_summoner_2_id,
                p100_top.summoner_1_name as team_100_top_summoner_1_name,
                p100_top.summoner_2_name as team_100_top_summoner_2_name,
                p100_top.kills as team_100_top_kills,
                p100_top.deaths as team_100_top_deaths,
                p100_top.assists as team_100_top_assists,
                p100_top.total_damage_dealt as team_100_top_total_damage_dealt,
                p100_top.total_damage_to_champions as team_100_top_damage_to_champions,
                p100_top.total_damage_taken as team_100_top_damage_taken,
                p100_top.true_damage_dealt as team_100_top_true_damage,
                p100_top.physical_damage_dealt as team_100_top_physical_damage,
                p100_top.magic_damage_dealt as team_100_top_magic_damage,
                p100_top.gold_earned as team_100_top_gold,
                p100_top.total_minions_killed as team_100_top_cs,
                p100_top.neutral_minions_killed as team_100_top_neutral_cs,
                p100_top.vision_score as team_100_top_vision,
                p100_top.wards_placed as team_100_top_wards_placed,
                p100_top.wards_killed as team_100_top_wards_killed,
                p100_top.vision_wards_bought as team_100_top_vision_wards_bought,
                p100_top.enemy_champion_immobilizations as team_100_top_cc_score,
                p100_top.first_blood_kill as team_100_top_first_blood_kill,
                p100_top.first_tower_kill as team_100_top_first_tower_kill,
                p100_top.turret_kills as team_100_top_turret_kills,
                p100_top.inhibitor_kills as team_100_top_inhibitor_kills,
                p100_top.largest_killing_spree as team_100_top_largest_killing_spree,
                p100_top.largest_multi_kill as team_100_top_largest_multi_kill,
                p100_top.killing_sprees as team_100_top_killing_sprees,
                p100_top.double_kills as team_100_top_double_kills,
                p100_top.triple_kills as team_100_top_triple_kills,
                p100_top.quadra_kills as team_100_top_quadra_kills,
                p100_top.penta_kills as team_100_top_penta_kills,
                p100_top.damage_per_minute as team_100_top_damage_per_minute,
                p100_top.damage_taken_percentage as team_100_top_damage_taken_pct,
                p100_top.gold_per_minute as team_100_top_gold_per_minute,
                p100_top.team_damage_percentage as team_100_top_team_damage_pct,
                p100_top.kill_participation as team_100_top_kill_participation,
                p100_top.kda as team_100_top_kda,
                p100_top.lane_minions_first_10_min as team_100_top_lane_minions_10min,
                p100_top.turret_plates_taken as team_100_top_turret_plates,
                p100_top.solo_kills as team_100_top_solo_kills,

                p100_jg.puuid as team_100_jungle_puuid,
                p100_jg.riot_id_name as team_100_jungle_riot_id_name,
                p100_jg.riot_id_tagline as team_100_jungle_riot_id_tagline,
                p100_jg.champion_id as team_100_jungle_champion_id,
                p100_jg.champion_name as team_100_jungle_champion_name,
                p100_jg.champ_level as team_100_jungle_champ_level,
                p100_jg.summoner_1_id as team_100_jungle_summoner_1_id,
                p100_jg.summoner_2_id as team_100_jungle_summoner_2_id,
                p100_jg.summoner_1_name as team_100_jungle_summoner_1_name,
                p100_jg.summoner_2_name as team_100_jungle_summoner_2_name,
                p100_jg.kills as team_100_jungle_kills,
                p100_jg.deaths as team_100_jungle_deaths,
                p100_jg.assists as team_100_jungle_assists,
                p100_jg.total_damage_dealt as team_100_jungle_total_damage_dealt,
                p100_jg.total_damage_to_champions as team_100_jungle_damage_to_champions,
                p100_jg.total_damage_taken as team_100_jungle_damage_taken,
                p100_jg.true_damage_dealt as team_100_jungle_true_damage,
                p100_jg.physical_damage_dealt as team_100_jungle_physical_damage,
                p100_jg.magic_damage_dealt as team_100_jungle_magic_damage,
                p100_jg.gold_earned as team_100_jungle_gold,
                p100_jg.total_minions_killed as team_100_jungle_cs,
                p100_jg.neutral_minions_killed as team_100_jungle_neutral_cs,
                p100_jg.vision_score as team_100_jungle_vision,
                p100_jg.wards_placed as team_100_jungle_wards_placed,
                p100_jg.wards_killed as team_100_jungle_wards_killed,
                p100_jg.vision_wards_bought as team_100_jungle_vision_wards_bought,
                p100_jg.enemy_champion_immobilizations as team_100_jungle_cc_score,
                p100_jg.first_blood_kill as team_100_jungle_first_blood_kill,
                p100_jg.first_tower_kill as team_100_jungle_first_tower_kill,
                p100_jg.turret_kills as team_100_jungle_turret_kills,
                p100_jg.inhibitor_kills as team_100_jungle_inhibitor_kills,
                p100_jg.largest_killing_spree as team_100_jungle_largest_killing_spree,
                p100_jg.largest_multi_kill as team_100_jungle_largest_multi_kill,
                p100_jg.killing_sprees as team_100_jungle_killing_sprees,
                p100_jg.double_kills as team_100_jungle_double_kills,
                p100_jg.triple_kills as team_100_jungle_triple_kills,
                p100_jg.quadra_kills as team_100_jungle_quadra_kills,
                p100_jg.penta_kills as team_100_jungle_penta_kills,
                p100_jg.damage_per_minute as team_100_jungle_damage_per_minute,
                p100_jg.damage_taken_percentage as team_100_jungle_damage_taken_pct,
                p100_jg.gold_per_minute as team_100_jungle_gold_per_minute,
                p100_jg.team_damage_percentage as team_100_jungle_team_damage_pct,
                p100_jg.kill_participation as team_100_jungle_kill_participation,
                p100_jg.kda as team_100_jungle_kda,
                p100_jg.lane_minions_first_10_min as team_100_jungle_lane_minions_10min,
                p100_jg.turret_plates_taken as team_100_jungle_turret_plates,
                p100_jg.solo_kills as team_100_jungle_solo_kills,

                p100_mid.puuid as team_100_mid_puuid,
                p100_mid.riot_id_name as team_100_mid_riot_id_name,
                p100_mid.riot_id_tagline as team_100_mid_riot_id_tagline,
                p100_mid.champion_id as team_100_mid_champion_id,
                p100_mid.champion_name as team_100_mid_champion_name,
                p100_mid.champ_level as team_100_mid_champ_level,
                p100_mid.summoner_1_id as team_100_mid_summoner_1_id,
                p100_mid.summoner_2_id as team_100_mid_summoner_2_id,
                p100_mid.summoner_1_name as team_100_mid_summoner_1_name,
                p100_mid.summoner_2_name as team_100_mid_summoner_2_name,
                p100_mid.kills as team_100_mid_kills,
                p100_mid.deaths as team_100_mid_deaths,
                p100_mid.assists as team_100_mid_assists,
                p100_mid.total_damage_dealt as team_100_mid_total_damage_dealt,
                p100_mid.total_damage_to_champions as team_100_mid_damage_to_champions,
                p100_mid.total_damage_taken as team_100_mid_damage_taken,
                p100_mid.true_damage_dealt as team_100_mid_true_damage,
                p100_mid.physical_damage_dealt as team_100_mid_physical_damage,
                p100_mid.magic_damage_dealt as team_100_mid_magic_damage,
                p100_mid.gold_earned as team_100_mid_gold,
                p100_mid.total_minions_killed as team_100_mid_cs,
                p100_mid.neutral_minions_killed as team_100_mid_neutral_cs,
                p100_mid.vision_score as team_100_mid_vision,
                p100_mid.wards_placed as team_100_mid_wards_placed,
                p100_mid.wards_killed as team_100_mid_wards_killed,
                p100_mid.vision_wards_bought as team_100_mid_vision_wards_bought,
                p100_mid.enemy_champion_immobilizations as team_100_mid_cc_score,
                p100_mid.first_blood_kill as team_100_mid_first_blood_kill,
                p100_mid.first_tower_kill as team_100_mid_first_tower_kill,
                p100_mid.turret_kills as team_100_mid_turret_kills,
                p100_mid.inhibitor_kills as team_100_mid_inhibitor_kills,
                p100_mid.largest_killing_spree as team_100_mid_largest_killing_spree,
                p100_mid.largest_multi_kill as team_100_mid_largest_multi_kill,
                p100_mid.killing_sprees as team_100_mid_killing_sprees,
                p100_mid.double_kills as team_100_mid_double_kills,
                p100_mid.triple_kills as team_100_mid_triple_kills,
                p100_mid.quadra_kills as team_100_mid_quadra_kills,
                p100_mid.penta_kills as team_100_mid_penta_kills,
                p100_mid.damage_per_minute as team_100_mid_damage_per_minute,
                p100_mid.damage_taken_percentage as team_100_mid_damage_taken_pct,
                p100_mid.gold_per_minute as team_100_mid_gold_per_minute,
                p100_mid.team_damage_percentage as team_100_mid_team_damage_pct,
                p100_mid.kill_participation as team_100_mid_kill_participation,
                p100_mid.kda as team_100_mid_kda,
                p100_mid.lane_minions_first_10_min as team_100_mid_lane_minions_10min,
                p100_mid.turret_plates_taken as team_100_mid_turret_plates,
                p100_mid.solo_kills as team_100_mid_solo_kills,

                p100_adc.puuid as team_100_adc_puuid,
                p100_adc.riot_id_name as team_100_adc_riot_id_name,
                p100_adc.riot_id_tagline as team_100_adc_riot_id_tagline,
                p100_adc.champion_id as team_100_adc_champion_id,
                p100_adc.champion_name as team_100_adc_champion_name,
                p100_adc.champ_level as team_100_adc_champ_level,
                p100_adc.summoner_1_id as team_100_adc_summoner_1_id,
                p100_adc.summoner_2_id as team_100_adc_summoner_2_id,
                p100_adc.summoner_1_name as team_100_adc_summoner_1_name,
                p100_adc.summoner_2_name as team_100_adc_summoner_2_name,
                p100_adc.kills as team_100_adc_kills,
                p100_adc.deaths as team_100_adc_deaths,
                p100_adc.assists as team_100_adc_assists,
                p100_adc.total_damage_dealt as team_100_adc_total_damage_dealt,
                p100_adc.total_damage_to_champions as team_100_adc_damage_to_champions,
                p100_adc.total_damage_taken as team_100_adc_damage_taken,
                p100_adc.true_damage_dealt as team_100_adc_true_damage,
                p100_adc.physical_damage_dealt as team_100_adc_physical_damage,
                p100_adc.magic_damage_dealt as team_100_adc_magic_damage,
                p100_adc.gold_earned as team_100_adc_gold,
                p100_adc.total_minions_killed as team_100_adc_cs,
                p100_adc.neutral_minions_killed as team_100_adc_neutral_cs,
                p100_adc.vision_score as team_100_adc_vision,
                p100_adc.wards_placed as team_100_adc_wards_placed,
                p100_adc.wards_killed as team_100_adc_wards_killed,
                p100_adc.vision_wards_bought as team_100_adc_vision_wards_bought,
                p100_adc.enemy_champion_immobilizations as team_100_adc_cc_score,
                p100_adc.first_blood_kill as team_100_adc_first_blood_kill,
                p100_adc.first_tower_kill as team_100_adc_first_tower_kill,
                p100_adc.turret_kills as team_100_adc_turret_kills,
                p100_adc.inhibitor_kills as team_100_adc_inhibitor_kills,
                p100_adc.largest_killing_spree as team_100_adc_largest_killing_spree,
                p100_adc.largest_multi_kill as team_100_adc_largest_multi_kill,
                p100_adc.killing_sprees as team_100_adc_killing_sprees,
                p100_adc.double_kills as team_100_adc_double_kills,
                p100_adc.triple_kills as team_100_adc_triple_kills,
                p100_adc.quadra_kills as team_100_adc_quadra_kills,
                p100_adc.penta_kills as team_100_adc_penta_kills,
                p100_adc.damage_per_minute as team_100_adc_damage_per_minute,
                p100_adc.damage_taken_percentage as team_100_adc_damage_taken_pct,
                p100_adc.gold_per_minute as team_100_adc_gold_per_minute,
                p100_adc.team_damage_percentage as team_100_adc_team_damage_pct,
                p100_adc.kill_participation as team_100_adc_kill_participation,
                p100_adc.kda as team_100_adc_kda,
                p100_adc.lane_minions_first_10_min as team_100_adc_lane_minions_10min,
                p100_adc.turret_plates_taken as team_100_adc_turret_plates,
                p100_adc.solo_kills as team_100_adc_solo_kills,

                p100_sup.puuid as team_100_support_puuid,
                p100_sup.riot_id_name as team_100_support_riot_id_name,
                p100_sup.riot_id_tagline as team_100_support_riot_id_tagline,
                p100_sup.champion_id as team_100_support_champion_id,
                p100_sup.champion_name as team_100_support_champion_name,
                p100_sup.champ_level as team_100_support_champ_level,
                p100_sup.summoner_1_id as team_100_support_summoner_1_id,
                p100_sup.summoner_2_id as team_100_support_summoner_2_id,
                p100_sup.summoner_1_name as team_100_support_summoner_1_name,
                p100_sup.summoner_2_name as team_100_support_summoner_2_name,
                p100_sup.kills as team_100_support_kills,
                p100_sup.deaths as team_100_support_deaths,
                p100_sup.assists as team_100_support_assists,
                p100_sup.total_damage_dealt as team_100_support_total_damage_dealt,
                p100_sup.total_damage_to_champions as team_100_support_damage_to_champions,
                p100_sup.total_damage_taken as team_100_support_damage_taken,
                p100_sup.true_damage_dealt as team_100_support_true_damage,
                p100_sup.physical_damage_dealt as team_100_support_physical_damage,
                p100_sup.magic_damage_dealt as team_100_support_magic_damage,
                p100_sup.gold_earned as team_100_support_gold,
                p100_sup.total_minions_killed as team_100_support_cs,
                p100_sup.neutral_minions_killed as team_100_support_neutral_cs,
                p100_sup.vision_score as team_100_support_vision,
                p100_sup.wards_placed as team_100_support_wards_placed,
                p100_sup.wards_killed as team_100_support_wards_killed,
                p100_sup.vision_wards_bought as team_100_support_vision_wards_bought,
                p100_sup.enemy_champion_immobilizations as team_100_support_cc_score,
                p100_sup.first_blood_kill as team_100_support_first_blood_kill,
                p100_sup.first_tower_kill as team_100_support_first_tower_kill,
                p100_sup.turret_kills as team_100_support_turret_kills,
                p100_sup.inhibitor_kills as team_100_support_inhibitor_kills,
                p100_sup.largest_killing_spree as team_100_support_largest_killing_spree,
                p100_sup.largest_multi_kill as team_100_support_largest_multi_kill,
                p100_sup.killing_sprees as team_100_support_killing_sprees,
                p100_sup.double_kills as team_100_support_double_kills,
                p100_sup.triple_kills as team_100_support_triple_kills,
                p100_sup.quadra_kills as team_100_support_quadra_kills,
                p100_sup.penta_kills as team_100_support_penta_kills,
                p100_sup.damage_per_minute as team_100_support_damage_per_minute,
                p100_sup.damage_taken_percentage as team_100_support_damage_taken_pct,
                p100_sup.gold_per_minute as team_100_support_gold_per_minute,
                p100_sup.team_damage_percentage as team_100_support_team_damage_pct,
                p100_sup.kill_participation as team_100_support_kill_participation,
                p100_sup.kda as team_100_support_kda,
                p100_sup.lane_minions_first_10_min as team_100_support_lane_minions_10min,
                p100_sup.turret_plates_taken as team_100_support_turret_plates,
                p100_sup.solo_kills as team_100_support_solo_kills,

                -- Team 200 players (with puuid for player features)
                p200_top.puuid as team_200_top_puuid,
                p200_top.riot_id_name as team_200_top_riot_id_name,
                p200_top.riot_id_tagline as team_200_top_riot_id_tagline,
                p200_top.champion_id as team_200_top_champion_id,
                p200_top.champion_name as team_200_top_champion_name,
                p200_top.champ_level as team_200_top_champ_level,
                p200_top.summoner_1_id as team_200_top_summoner_1_id,
                p200_top.summoner_2_id as team_200_top_summoner_2_id,
                p200_top.summoner_1_name as team_200_top_summoner_1_name,
                p200_top.summoner_2_name as team_200_top_summoner_2_name,
                p200_top.kills as team_200_top_kills,
                p200_top.deaths as team_200_top_deaths,
                p200_top.assists as team_200_top_assists,
                p200_top.total_damage_dealt as team_200_top_total_damage_dealt,
                p200_top.total_damage_to_champions as team_200_top_damage_to_champions,
                p200_top.total_damage_taken as team_200_top_damage_taken,
                p200_top.true_damage_dealt as team_200_top_true_damage,
                p200_top.physical_damage_dealt as team_200_top_physical_damage,
                p200_top.magic_damage_dealt as team_200_top_magic_damage,
                p200_top.gold_earned as team_200_top_gold,
                p200_top.total_minions_killed as team_200_top_cs,
                p200_top.neutral_minions_killed as team_200_top_neutral_cs,
                p200_top.vision_score as team_200_top_vision,
                p200_top.wards_placed as team_200_top_wards_placed,
                p200_top.wards_killed as team_200_top_wards_killed,
                p200_top.vision_wards_bought as team_200_top_vision_wards_bought,
                p200_top.enemy_champion_immobilizations as team_200_top_cc_score,
                p200_top.first_blood_kill as team_200_top_first_blood_kill,
                p200_top.first_tower_kill as team_200_top_first_tower_kill,
                p200_top.turret_kills as team_200_top_turret_kills,
                p200_top.inhibitor_kills as team_200_top_inhibitor_kills,
                p200_top.largest_killing_spree as team_200_top_largest_killing_spree,
                p200_top.largest_multi_kill as team_200_top_largest_multi_kill,
                p200_top.killing_sprees as team_200_top_killing_sprees,
                p200_top.double_kills as team_200_top_double_kills,
                p200_top.triple_kills as team_200_top_triple_kills,
                p200_top.quadra_kills as team_200_top_quadra_kills,
                p200_top.penta_kills as team_200_top_penta_kills,
                p200_top.damage_per_minute as team_200_top_damage_per_minute,
                p200_top.damage_taken_percentage as team_200_top_damage_taken_pct,
                p200_top.gold_per_minute as team_200_top_gold_per_minute,
                p200_top.team_damage_percentage as team_200_top_team_damage_pct,
                p200_top.kill_participation as team_200_top_kill_participation,
                p200_top.kda as team_200_top_kda,
                p200_top.lane_minions_first_10_min as team_200_top_lane_minions_10min,
                p200_top.turret_plates_taken as team_200_top_turret_plates,
                p200_top.solo_kills as team_200_top_solo_kills,

                p200_jg.puuid as team_200_jungle_puuid,
                p200_jg.riot_id_name as team_200_jungle_riot_id_name,
                p200_jg.riot_id_tagline as team_200_jungle_riot_id_tagline,
                p200_jg.champion_id as team_200_jungle_champion_id,
                p200_jg.champion_name as team_200_jungle_champion_name,
                p200_jg.champ_level as team_200_jungle_champ_level,
                p200_jg.summoner_1_id as team_200_jungle_summoner_1_id,
                p200_jg.summoner_2_id as team_200_jungle_summoner_2_id,
                p200_jg.summoner_1_name as team_200_jungle_summoner_1_name,
                p200_jg.summoner_2_name as team_200_jungle_summoner_2_name,
                p200_jg.kills as team_200_jungle_kills,
                p200_jg.deaths as team_200_jungle_deaths,
                p200_jg.assists as team_200_jungle_assists,
                p200_jg.total_damage_dealt as team_200_jungle_total_damage_dealt,
                p200_jg.total_damage_to_champions as team_200_jungle_damage_to_champions,
                p200_jg.total_damage_taken as team_200_jungle_damage_taken,
                p200_jg.true_damage_dealt as team_200_jungle_true_damage,
                p200_jg.physical_damage_dealt as team_200_jungle_physical_damage,
                p200_jg.magic_damage_dealt as team_200_jungle_magic_damage,
                p200_jg.gold_earned as team_200_jungle_gold,
                p200_jg.total_minions_killed as team_200_jungle_cs,
                p200_jg.neutral_minions_killed as team_200_jungle_neutral_cs,
                p200_jg.vision_score as team_200_jungle_vision,
                p200_jg.wards_placed as team_200_jungle_wards_placed,
                p200_jg.wards_killed as team_200_jungle_wards_killed,
                p200_jg.vision_wards_bought as team_200_jungle_vision_wards_bought,
                p200_jg.enemy_champion_immobilizations as team_200_jungle_cc_score,
                p200_jg.first_blood_kill as team_200_jungle_first_blood_kill,
                p200_jg.first_tower_kill as team_200_jungle_first_tower_kill,
                p200_jg.turret_kills as team_200_jungle_turret_kills,
                p200_jg.inhibitor_kills as team_200_jungle_inhibitor_kills,
                p200_jg.largest_killing_spree as team_200_jungle_largest_killing_spree,
                p200_jg.largest_multi_kill as team_200_jungle_largest_multi_kill,
                p200_jg.killing_sprees as team_200_jungle_killing_sprees,
                p200_jg.double_kills as team_200_jungle_double_kills,
                p200_jg.triple_kills as team_200_jungle_triple_kills,
                p200_jg.quadra_kills as team_200_jungle_quadra_kills,
                p200_jg.penta_kills as team_200_jungle_penta_kills,
                p200_jg.damage_per_minute as team_200_jungle_damage_per_minute,
                p200_jg.damage_taken_percentage as team_200_jungle_damage_taken_pct,
                p200_jg.gold_per_minute as team_200_jungle_gold_per_minute,
                p200_jg.team_damage_percentage as team_200_jungle_team_damage_pct,
                p200_jg.kill_participation as team_200_jungle_kill_participation,
                p200_jg.kda as team_200_jungle_kda,
                p200_jg.lane_minions_first_10_min as team_200_jungle_lane_minions_10min,
                p200_jg.turret_plates_taken as team_200_jungle_turret_plates,
                p200_jg.solo_kills as team_200_jungle_solo_kills,

                p200_mid.puuid as team_200_mid_puuid,
                p200_mid.riot_id_name as team_200_mid_riot_id_name,
                p200_mid.riot_id_tagline as team_200_mid_riot_id_tagline,
                p200_mid.champion_id as team_200_mid_champion_id,
                p200_mid.champion_name as team_200_mid_champion_name,
                p200_mid.champ_level as team_200_mid_champ_level,
                p200_mid.summoner_1_id as team_200_mid_summoner_1_id,
                p200_mid.summoner_2_id as team_200_mid_summoner_2_id,
                p200_mid.summoner_1_name as team_200_mid_summoner_1_name,
                p200_mid.summoner_2_name as team_200_mid_summoner_2_name,
                p200_mid.kills as team_200_mid_kills,
                p200_mid.deaths as team_200_mid_deaths,
                p200_mid.assists as team_200_mid_assists,
                p200_mid.total_damage_dealt as team_200_mid_total_damage_dealt,
                p200_mid.total_damage_to_champions as team_200_mid_damage_to_champions,
                p200_mid.total_damage_taken as team_200_mid_damage_taken,
                p200_mid.true_damage_dealt as team_200_mid_true_damage,
                p200_mid.physical_damage_dealt as team_200_mid_physical_damage,
                p200_mid.magic_damage_dealt as team_200_mid_magic_damage,
                p200_mid.gold_earned as team_200_mid_gold,
                p200_mid.total_minions_killed as team_200_mid_cs,
                p200_mid.neutral_minions_killed as team_200_mid_neutral_cs,
                p200_mid.vision_score as team_200_mid_vision,
                p200_mid.wards_placed as team_200_mid_wards_placed,
                p200_mid.wards_killed as team_200_mid_wards_killed,
                p200_mid.vision_wards_bought as team_200_mid_vision_wards_bought,
                p200_mid.enemy_champion_immobilizations as team_200_mid_cc_score,
                p200_mid.first_blood_kill as team_200_mid_first_blood_kill,
                p200_mid.first_tower_kill as team_200_mid_first_tower_kill,
                p200_mid.turret_kills as team_200_mid_turret_kills,
                p200_mid.inhibitor_kills as team_200_mid_inhibitor_kills,
                p200_mid.largest_killing_spree as team_200_mid_largest_killing_spree,
                p200_mid.largest_multi_kill as team_200_mid_largest_multi_kill,
                p200_mid.killing_sprees as team_200_mid_killing_sprees,
                p200_mid.double_kills as team_200_mid_double_kills,
                p200_mid.triple_kills as team_200_mid_triple_kills,
                p200_mid.quadra_kills as team_200_mid_quadra_kills,
                p200_mid.penta_kills as team_200_mid_penta_kills,
                p200_mid.damage_per_minute as team_200_mid_damage_per_minute,
                p200_mid.damage_taken_percentage as team_200_mid_damage_taken_pct,
                p200_mid.gold_per_minute as team_200_mid_gold_per_minute,
                p200_mid.team_damage_percentage as team_200_mid_team_damage_pct,
                p200_mid.kill_participation as team_200_mid_kill_participation,
                p200_mid.kda as team_200_mid_kda,
                p200_mid.lane_minions_first_10_min as team_200_mid_lane_minions_10min,
                p200_mid.turret_plates_taken as team_200_mid_turret_plates,
                p200_mid.solo_kills as team_200_mid_solo_kills,

                p200_adc.puuid as team_200_adc_puuid,
                p200_adc.riot_id_name as team_200_adc_riot_id_name,
                p200_adc.riot_id_tagline as team_200_adc_riot_id_tagline,
                p200_adc.champion_id as team_200_adc_champion_id,
                p200_adc.champion_name as team_200_adc_champion_name,
                p200_adc.champ_level as team_200_adc_champ_level,
                p200_adc.summoner_1_id as team_200_adc_summoner_1_id,
                p200_adc.summoner_2_id as team_200_adc_summoner_2_id,
                p200_adc.summoner_1_name as team_200_adc_summoner_1_name,
                p200_adc.summoner_2_name as team_200_adc_summoner_2_name,
                p200_adc.kills as team_200_adc_kills,
                p200_adc.deaths as team_200_adc_deaths,
                p200_adc.assists as team_200_adc_assists,
                p200_adc.total_damage_dealt as team_200_adc_total_damage_dealt,
                p200_adc.total_damage_to_champions as team_200_adc_damage_to_champions,
                p200_adc.total_damage_taken as team_200_adc_damage_taken,
                p200_adc.true_damage_dealt as team_200_adc_true_damage,
                p200_adc.physical_damage_dealt as team_200_adc_physical_damage,
                p200_adc.magic_damage_dealt as team_200_adc_magic_damage,
                p200_adc.gold_earned as team_200_adc_gold,
                p200_adc.total_minions_killed as team_200_adc_cs,
                p200_adc.neutral_minions_killed as team_200_adc_neutral_cs,
                p200_adc.vision_score as team_200_adc_vision,
                p200_adc.wards_placed as team_200_adc_wards_placed,
                p200_adc.wards_killed as team_200_adc_wards_killed,
                p200_adc.vision_wards_bought as team_200_adc_vision_wards_bought,
                p200_adc.enemy_champion_immobilizations as team_200_adc_cc_score,
                p200_adc.first_blood_kill as team_200_adc_first_blood_kill,
                p200_adc.first_tower_kill as team_200_adc_first_tower_kill,
                p200_adc.turret_kills as team_200_adc_turret_kills,
                p200_adc.inhibitor_kills as team_200_adc_inhibitor_kills,
                p200_adc.largest_killing_spree as team_200_adc_largest_killing_spree,
                p200_adc.largest_multi_kill as team_200_adc_largest_multi_kill,
                p200_adc.killing_sprees as team_200_adc_killing_sprees,
                p200_adc.double_kills as team_200_adc_double_kills,
                p200_adc.triple_kills as team_200_adc_triple_kills,
                p200_adc.quadra_kills as team_200_adc_quadra_kills,
                p200_adc.penta_kills as team_200_adc_penta_kills,
                p200_adc.damage_per_minute as team_200_adc_damage_per_minute,
                p200_adc.damage_taken_percentage as team_200_adc_damage_taken_pct,
                p200_adc.gold_per_minute as team_200_adc_gold_per_minute,
                p200_adc.team_damage_percentage as team_200_adc_team_damage_pct,
                p200_adc.kill_participation as team_200_adc_kill_participation,
                p200_adc.kda as team_200_adc_kda,
                p200_adc.lane_minions_first_10_min as team_200_adc_lane_minions_10min,
                p200_adc.turret_plates_taken as team_200_adc_turret_plates,
                p200_adc.solo_kills as team_200_adc_solo_kills,

                p200_sup.puuid as team_200_support_puuid,
                p200_sup.riot_id_name as team_200_support_riot_id_name,
                p200_sup.riot_id_tagline as team_200_support_riot_id_tagline,
                p200_sup.champion_id as team_200_support_champion_id,
                p200_sup.champion_name as team_200_support_champion_name,
                p200_sup.champ_level as team_200_support_champ_level,
                p200_sup.summoner_1_id as team_200_support_summoner_1_id,
                p200_sup.summoner_2_id as team_200_support_summoner_2_id,
                p200_sup.summoner_1_name as team_200_support_summoner_1_name,
                p200_sup.summoner_2_name as team_200_support_summoner_2_name,
                p200_sup.kills as team_200_support_kills,
                p200_sup.deaths as team_200_support_deaths,
                p200_sup.assists as team_200_support_assists,
                p200_sup.total_damage_dealt as team_200_support_total_damage_dealt,
                p200_sup.total_damage_to_champions as team_200_support_damage_to_champions,
                p200_sup.total_damage_taken as team_200_support_damage_taken,
                p200_sup.true_damage_dealt as team_200_support_true_damage,
                p200_sup.physical_damage_dealt as team_200_support_physical_damage,
                p200_sup.magic_damage_dealt as team_200_support_magic_damage,
                p200_sup.gold_earned as team_200_support_gold,
                p200_sup.total_minions_killed as team_200_support_cs,
                p200_sup.neutral_minions_killed as team_200_support_neutral_cs,
                p200_sup.vision_score as team_200_support_vision,
                p200_sup.wards_placed as team_200_support_wards_placed,
                p200_sup.wards_killed as team_200_support_wards_killed,
                p200_sup.vision_wards_bought as team_200_support_vision_wards_bought,
                p200_sup.enemy_champion_immobilizations as team_200_support_cc_score,
                p200_sup.first_blood_kill as team_200_support_first_blood_kill,
                p200_sup.first_tower_kill as team_200_support_first_tower_kill,
                p200_sup.turret_kills as team_200_support_turret_kills,
                p200_sup.inhibitor_kills as team_200_support_inhibitor_kills,
                p200_sup.largest_killing_spree as team_200_support_largest_killing_spree,
                p200_sup.largest_multi_kill as team_200_support_largest_multi_kill,
                p200_sup.killing_sprees as team_200_support_killing_sprees,
                p200_sup.double_kills as team_200_support_double_kills,
                p200_sup.triple_kills as team_200_support_triple_kills,
                p200_sup.quadra_kills as team_200_support_quadra_kills,
                p200_sup.penta_kills as team_200_support_penta_kills,
                p200_sup.damage_per_minute as team_200_support_damage_per_minute,
                p200_sup.damage_taken_percentage as team_200_support_damage_taken_pct,
                p200_sup.gold_per_minute as team_200_support_gold_per_minute,
                p200_sup.team_damage_percentage as team_200_support_team_damage_pct,
                p200_sup.kill_participation as team_200_support_kill_participation,
                p200_sup.kda as team_200_support_kda,
                p200_sup.lane_minions_first_10_min as team_200_support_lane_minions_10min,
                p200_sup.turret_plates_taken as team_200_support_turret_plates,
                p200_sup.solo_kills as team_200_support_solo_kills,

                -- Timeline @10min (gold per position)
                mt10.team_100_gold as team_100_gold_at_10,
                mt10.team_200_gold as team_200_gold_at_10,
                mt10.gold_diff as gold_diff_at_10,
                mt10.team_100_top_gold as team_100_top_gold_at_10,
                mt10.team_100_jungle_gold as team_100_jungle_gold_at_10,
                mt10.team_100_mid_gold as team_100_mid_gold_at_10,
                mt10.team_100_adc_gold as team_100_adc_gold_at_10,
                mt10.team_100_support_gold as team_100_support_gold_at_10,
                mt10.team_200_top_gold as team_200_top_gold_at_10,
                mt10.team_200_jungle_gold as team_200_jungle_gold_at_10,
                mt10.team_200_mid_gold as team_200_mid_gold_at_10,
                mt10.team_200_adc_gold as team_200_adc_gold_at_10,
                mt10.team_200_support_gold as team_200_support_gold_at_10,

                -- CS @10min from player_stats
                p100_top.lane_minions_first_10_min as team_100_top_cs_at_10,
                p100_jg.lane_minions_first_10_min as team_100_jungle_cs_at_10,
                p100_mid.lane_minions_first_10_min as team_100_mid_cs_at_10,
                p100_adc.lane_minions_first_10_min as team_100_adc_cs_at_10,
                p100_sup.lane_minions_first_10_min as team_100_support_cs_at_10,
                p200_top.lane_minions_first_10_min as team_200_top_cs_at_10,
                p200_jg.lane_minions_first_10_min as team_200_jungle_cs_at_10,
                p200_mid.lane_minions_first_10_min as team_200_mid_cs_at_10,
                p200_adc.lane_minions_first_10_min as team_200_adc_cs_at_10,
                p200_sup.lane_minions_first_10_min as team_200_support_cs_at_10

            FROM matches m
            LEFT JOIN team_stats t100 ON m.match_id = t100.match_id AND t100.team_id = 100
            LEFT JOIN team_stats t200 ON m.match_id = t200.match_id AND t200.team_id = 200
            LEFT JOIN player_stats p100_top ON m.match_id = p100_top.match_id AND p100_top.team_id = 100 AND p100_top.position = 'top'
            LEFT JOIN player_stats p100_jg ON m.match_id = p100_jg.match_id AND p100_jg.team_id = 100 AND p100_jg.position = 'jungle'
            LEFT JOIN player_stats p100_mid ON m.match_id = p100_mid.match_id AND p100_mid.team_id = 100 AND p100_mid.position = 'mid'
            LEFT JOIN player_stats p100_adc ON m.match_id = p100_adc.match_id AND p100_adc.team_id = 100 AND p100_adc.position = 'adc'
            LEFT JOIN player_stats p100_sup ON m.match_id = p100_sup.match_id AND p100_sup.team_id = 100 AND p100_sup.position = 'support'
            LEFT JOIN player_stats p200_top ON m.match_id = p200_top.match_id AND p200_top.team_id = 200 AND p200_top.position = 'top'
            LEFT JOIN player_stats p200_jg ON m.match_id = p200_jg.match_id AND p200_jg.team_id = 200 AND p200_jg.position = 'jungle'
            LEFT JOIN player_stats p200_mid ON m.match_id = p200_mid.match_id AND p200_mid.team_id = 200 AND p200_mid.position = 'mid'
            LEFT JOIN player_stats p200_adc ON m.match_id = p200_adc.match_id AND p200_adc.team_id = 200 AND p200_adc.position = 'adc'
            LEFT JOIN player_stats p200_sup ON m.match_id = p200_sup.match_id AND p200_sup.team_id = 200 AND p200_sup.position = 'support'
            LEFT JOIN match_timeline mt10 ON m.match_id = mt10.match_id AND mt10.minute = 10
            ORDER BY m.game_creation DESC
            '''

            return pd.read_sql_query(query, conn)

    def get_match_count(self) -> int:
        """Get total number of matches in database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM matches')
            return cursor.fetchone()[0]

    def export_with_timeline_at_minutes(self, minutes: List[int]) -> pd.DataFrame:
        """
        Export match data with timeline gold data at multiple specific minutes.

        This method creates dynamic JOINs for each requested minute to include
        gold data from match_timeline table.

        Args:
            minutes: List of minutes to include (e.g., [5, 10, 15, 20])

        Returns:
            DataFrame with columns like gold_diff_at_5, gold_diff_at_10, etc.
            along with position-specific gold diffs per minute.
        """
        with self.get_connection() as conn:
            positions = ['top', 'jungle', 'mid', 'adc', 'support']

            # Build dynamic SELECT clauses for each minute
            timeline_selects = []
            for minute in minutes:
                alias = f'mt{minute}'
                timeline_selects.extend([
                    f'{alias}.team_100_gold as team_100_gold_at_{minute}',
                    f'{alias}.team_200_gold as team_200_gold_at_{minute}',
                    f'{alias}.gold_diff as gold_diff_at_{minute}',
                ])
                # Position-specific gold, level, xp, cs
                for pos in positions:
                    timeline_selects.extend([
                        f'{alias}.team_100_{pos}_gold as team_100_{pos}_gold_at_{minute}',
                        f'{alias}.team_200_{pos}_gold as team_200_{pos}_gold_at_{minute}',
                    ])
                for metric in ['level', 'xp']:
                    for pos in positions:
                        timeline_selects.extend([
                            f'{alias}.team_100_{pos}_{metric} as team_100_{pos}_{metric}_at_{minute}',
                            f'{alias}.team_200_{pos}_{metric} as team_200_{pos}_{metric}_at_{minute}',
                        ])
                # CS from timeline uses different alias to avoid collision with player_stats CS@10
                for pos in positions:
                    timeline_selects.extend([
                        f'{alias}.team_100_{pos}_cs as team_100_{pos}_timeline_cs_at_{minute}',
                        f'{alias}.team_200_{pos}_cs as team_200_{pos}_timeline_cs_at_{minute}',
                    ])

            timeline_select_str = ',\n                '.join(timeline_selects)

            # Build dynamic JOINs for each minute
            timeline_joins = []
            for minute in minutes:
                alias = f'mt{minute}'
                timeline_joins.append(
                    f'LEFT JOIN match_timeline {alias} ON m.match_id = {alias}.match_id AND {alias}.minute = {minute}'
                )
            timeline_join_str = '\n            '.join(timeline_joins)

            # CS @10min from player_stats (only available at 10 minutes)
            cs_at_10_selects = []
            if 10 in minutes:
                for team in ['100', '200']:
                    for pos in positions:
                        pos_alias = 'jg' if pos == 'jungle' else ('sup' if pos == 'support' else pos[:3])
                        cs_at_10_selects.append(
                            f'p{team}_{pos_alias}.lane_minions_first_10_min as team_{team}_{pos}_cs_at_10'
                        )
            cs_at_10_str = ',\n                ' + ',\n                '.join(cs_at_10_selects) if cs_at_10_selects else ''

            query = f'''
            SELECT
                m.match_id,
                m.team_100_win,
                m.game_duration,
                m.game_version,

                -- First objectives (from team_stats)
                t100.first_blood as first_blood_team_100,
                t100.first_tower as first_tower_team_100,
                t100.first_dragon as first_dragon_team_100,
                t100.first_rift_herald as first_herald_team_100,

                -- Timeline data at each minute
                {timeline_select_str}{cs_at_10_str}

            FROM matches m
            LEFT JOIN team_stats t100 ON m.match_id = t100.match_id AND t100.team_id = 100
            LEFT JOIN team_stats t200 ON m.match_id = t200.match_id AND t200.team_id = 200
            LEFT JOIN player_stats p100_top ON m.match_id = p100_top.match_id AND p100_top.team_id = 100 AND p100_top.position = 'top'
            LEFT JOIN player_stats p100_jg ON m.match_id = p100_jg.match_id AND p100_jg.team_id = 100 AND p100_jg.position = 'jungle'
            LEFT JOIN player_stats p100_mid ON m.match_id = p100_mid.match_id AND p100_mid.team_id = 100 AND p100_mid.position = 'mid'
            LEFT JOIN player_stats p100_adc ON m.match_id = p100_adc.match_id AND p100_adc.team_id = 100 AND p100_adc.position = 'adc'
            LEFT JOIN player_stats p100_sup ON m.match_id = p100_sup.match_id AND p100_sup.team_id = 100 AND p100_sup.position = 'support'
            LEFT JOIN player_stats p200_top ON m.match_id = p200_top.match_id AND p200_top.team_id = 200 AND p200_top.position = 'top'
            LEFT JOIN player_stats p200_jg ON m.match_id = p200_jg.match_id AND p200_jg.team_id = 200 AND p200_jg.position = 'jungle'
            LEFT JOIN player_stats p200_mid ON m.match_id = p200_mid.match_id AND p200_mid.team_id = 200 AND p200_mid.position = 'mid'
            LEFT JOIN player_stats p200_adc ON m.match_id = p200_adc.match_id AND p200_adc.team_id = 200 AND p200_adc.position = 'adc'
            LEFT JOIN player_stats p200_sup ON m.match_id = p200_sup.match_id AND p200_sup.team_id = 200 AND p200_sup.position = 'support'
            {timeline_join_str}
            WHERE m.game_duration >= 600
            ORDER BY m.game_creation DESC
            '''

            return pd.read_sql_query(query, conn)

    # ================================================================
    # Summoner Role Stats Methods (NEW - for draft prediction)
    # ================================================================

    def get_summoner_role_stats(self, puuid: str, before_timestamp: int = None,
                                 last_n_games: int = None) -> Dict[str, Any]:
        """
        Get summoner's role distribution and winrates.

        Args:
            puuid: Player's PUUID
            before_timestamp: Only count matches before this timestamp (for temporal correctness)
            last_n_games: Limit to last N games (applied after timestamp filter)

        Returns:
            Dict with:
            - total_games: number total de parties
            - role_distribution: {'top': 0.15, 'mid': 0.60, ...}
            - role_winrates: {'top': 0.52, 'mid': 0.55, ...}
            - role_games: {'top': 15, 'mid': 60, ...}
        """
        with self.get_connection() as conn:
            time_filter = ""
            params = [puuid]
            if before_timestamp is not None:
                time_filter = "AND m.game_creation < ?"
                params.append(before_timestamp)

            # If last_n_games is specified, we need a subquery to get the most recent N games
            if last_n_games is not None:
                query = f'''
                    WITH recent_matches AS (
                        SELECT ps.match_id, ps.position, ps.team_id, m.team_100_win
                        FROM player_stats ps
                        JOIN matches m ON ps.match_id = m.match_id
                        WHERE ps.puuid = ? {time_filter}
                        ORDER BY m.game_creation DESC
                        LIMIT ?
                    )
                    SELECT
                        COUNT(*) as total_games,
                        SUM(CASE WHEN position = 'top' THEN 1 ELSE 0 END) as top_games,
                        SUM(CASE WHEN position = 'jungle' THEN 1 ELSE 0 END) as jungle_games,
                        SUM(CASE WHEN position = 'mid' THEN 1 ELSE 0 END) as mid_games,
                        SUM(CASE WHEN position = 'adc' THEN 1 ELSE 0 END) as adc_games,
                        SUM(CASE WHEN position = 'support' THEN 1 ELSE 0 END) as support_games,
                        SUM(CASE WHEN position = 'top' AND
                            ((team_id = 100 AND team_100_win = 1) OR (team_id = 200 AND team_100_win = 0))
                            THEN 1 ELSE 0 END) as top_wins,
                        SUM(CASE WHEN position = 'jungle' AND
                            ((team_id = 100 AND team_100_win = 1) OR (team_id = 200 AND team_100_win = 0))
                            THEN 1 ELSE 0 END) as jungle_wins,
                        SUM(CASE WHEN position = 'mid' AND
                            ((team_id = 100 AND team_100_win = 1) OR (team_id = 200 AND team_100_win = 0))
                            THEN 1 ELSE 0 END) as mid_wins,
                        SUM(CASE WHEN position = 'adc' AND
                            ((team_id = 100 AND team_100_win = 1) OR (team_id = 200 AND team_100_win = 0))
                            THEN 1 ELSE 0 END) as adc_wins,
                        SUM(CASE WHEN position = 'support' AND
                            ((team_id = 100 AND team_100_win = 1) OR (team_id = 200 AND team_100_win = 0))
                            THEN 1 ELSE 0 END) as support_wins
                    FROM recent_matches
                '''
                params.append(last_n_games)
            else:
                query = f'''
                    SELECT
                        COUNT(*) as total_games,
                        SUM(CASE WHEN ps.position = 'top' THEN 1 ELSE 0 END) as top_games,
                        SUM(CASE WHEN ps.position = 'jungle' THEN 1 ELSE 0 END) as jungle_games,
                        SUM(CASE WHEN ps.position = 'mid' THEN 1 ELSE 0 END) as mid_games,
                        SUM(CASE WHEN ps.position = 'adc' THEN 1 ELSE 0 END) as adc_games,
                        SUM(CASE WHEN ps.position = 'support' THEN 1 ELSE 0 END) as support_games,
                        SUM(CASE WHEN ps.position = 'top' AND
                            ((ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0))
                            THEN 1 ELSE 0 END) as top_wins,
                        SUM(CASE WHEN ps.position = 'jungle' AND
                            ((ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0))
                            THEN 1 ELSE 0 END) as jungle_wins,
                        SUM(CASE WHEN ps.position = 'mid' AND
                            ((ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0))
                            THEN 1 ELSE 0 END) as mid_wins,
                        SUM(CASE WHEN ps.position = 'adc' AND
                            ((ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0))
                            THEN 1 ELSE 0 END) as adc_wins,
                        SUM(CASE WHEN ps.position = 'support' AND
                            ((ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0))
                            THEN 1 ELSE 0 END) as support_wins
                    FROM player_stats ps
                    JOIN matches m ON ps.match_id = m.match_id
                    WHERE ps.puuid = ? {time_filter}
                '''

            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()

            if not row or row['total_games'] == 0:
                return {
                    'total_games': 0,
                    'role_distribution': {'top': 0.2, 'jungle': 0.2, 'mid': 0.2, 'adc': 0.2, 'support': 0.2},
                    'role_winrates': {'top': 0.5, 'jungle': 0.5, 'mid': 0.5, 'adc': 0.5, 'support': 0.5},
                    'role_games': {'top': 0, 'jungle': 0, 'mid': 0, 'adc': 0, 'support': 0}
                }

            total = row['total_games']
            roles = ['top', 'jungle', 'mid', 'adc', 'support']

            role_games = {role: row[f'{role}_games'] for role in roles}
            role_wins = {role: row[f'{role}_wins'] for role in roles}

            role_distribution = {role: role_games[role] / total if total > 0 else 0.2 for role in roles}
            role_winrates = {
                role: role_wins[role] / role_games[role] if role_games[role] > 0 else 0.5
                for role in roles
            }

            return {
                'total_games': total,
                'role_distribution': role_distribution,
                'role_winrates': role_winrates,
                'role_games': role_games
            }

    def get_summoner_role_performance(self, puuid: str, before_timestamp: int = None,
                                       last_n_games: int = None) -> Dict[str, Any]:
        """
        Get summoner's KDA and vision score averages per role.

        Args:
            puuid: Player's PUUID
            before_timestamp: Only count matches before this timestamp
            last_n_games: Limit to last N games

        Returns:
            Dict with:
            - role_kda: {'top': 2.5, 'jungle': 3.1, ...}
            - role_vision_score: {'top': 15.2, 'jungle': 35.5, ...}
        """
        with self.get_connection() as conn:
            time_filter = ""
            params = [puuid]
            if before_timestamp is not None:
                time_filter = "AND m.game_creation < ?"
                params.append(before_timestamp)

            if last_n_games is not None:
                query = f'''
                    WITH recent_matches AS (
                        SELECT ps.position, ps.kda, ps.vision_score
                        FROM player_stats ps
                        JOIN matches m ON ps.match_id = m.match_id
                        WHERE ps.puuid = ? {time_filter}
                        ORDER BY m.game_creation DESC
                        LIMIT ?
                    )
                    SELECT
                        position,
                        AVG(kda) as avg_kda,
                        AVG(vision_score) as avg_vision
                    FROM recent_matches
                    GROUP BY position
                '''
                params.append(last_n_games)
            else:
                query = f'''
                    SELECT
                        ps.position,
                        AVG(ps.kda) as avg_kda,
                        AVG(ps.vision_score) as avg_vision
                    FROM player_stats ps
                    JOIN matches m ON ps.match_id = m.match_id
                    WHERE ps.puuid = ? {time_filter}
                    GROUP BY ps.position
                '''

            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            roles = ['top', 'jungle', 'mid', 'adc', 'support']
            role_kda = {role: 2.0 for role in roles}
            role_vision = {role: 20.0 for role in roles}

            for row in rows:
                pos = row['position']
                if pos in roles:
                    role_kda[pos] = row['avg_kda'] if row['avg_kda'] is not None else 2.0
                    role_vision[pos] = row['avg_vision'] if row['avg_vision'] is not None else 20.0

            return {
                'role_kda': role_kda,
                'role_vision_score': role_vision
            }

    def get_summoner_streaks(self, puuid: str, before_timestamp: int = None) -> Dict[str, Any]:
        """
        Get summoner's current win/loss streak and recent streak history.

        Args:
            puuid: Player's PUUID
            before_timestamp: Only count matches before this timestamp

        Returns:
            Dict with:
            - current_streak_type: 'win' or 'loss'
            - current_streak_length: int
            - last_3_win_streaks: [5, 3, 2]
            - last_3_loss_streaks: [2, 1, 4]
        """
        with self.get_connection() as conn:
            time_filter = ""
            params = [puuid]
            if before_timestamp is not None:
                time_filter = "AND m.game_creation < ?"
                params.append(before_timestamp)

            # Get recent matches with win/loss info
            query = f'''
                SELECT
                    m.game_creation,
                    CASE WHEN
                        (ps.team_id = 100 AND m.team_100_win = 1) OR
                        (ps.team_id = 200 AND m.team_100_win = 0)
                    THEN 1 ELSE 0 END as won
                FROM player_stats ps
                JOIN matches m ON ps.match_id = m.match_id
                WHERE ps.puuid = ? {time_filter}
                ORDER BY m.game_creation DESC
                LIMIT 100
            '''

            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            if not rows:
                return {
                    'current_streak_type': 'none',
                    'current_streak_length': 0,
                    'last_3_win_streaks': [],
                    'last_3_loss_streaks': []
                }

            # Calculate current streak
            results = [row['won'] for row in rows]
            current_result = results[0]
            current_streak = 1
            for i in range(1, len(results)):
                if results[i] == current_result:
                    current_streak += 1
                else:
                    break

            current_streak_type = 'win' if current_result == 1 else 'loss'

            # Calculate streak history
            win_streaks = []
            loss_streaks = []
            streak_count = 1
            streak_type = results[0]

            for i in range(1, len(results)):
                if results[i] == streak_type:
                    streak_count += 1
                else:
                    if streak_type == 1:
                        win_streaks.append(streak_count)
                    else:
                        loss_streaks.append(streak_count)
                    streak_type = results[i]
                    streak_count = 1

            # Don't forget the last streak
            if streak_type == 1:
                win_streaks.append(streak_count)
            else:
                loss_streaks.append(streak_count)

            return {
                'current_streak_type': current_streak_type,
                'current_streak_length': current_streak,
                'last_3_win_streaks': win_streaks[:3],
                'last_3_loss_streaks': loss_streaks[:3]
            }

    def get_summoner_recent_champions(self, puuid: str, before_timestamp: int = None,
                                       last_n_games: int = 20) -> List[Dict]:
        """
        Get summoner's recently played champions with stats.

        Args:
            puuid: Player's PUUID
            before_timestamp: Only count matches before this timestamp
            last_n_games: Number of recent games to consider

        Returns:
            List of dicts with:
            - champion_id: int
            - champion_name: str
            - games: int
            - wins: int
            - winrate: float
        """
        with self.get_connection() as conn:
            time_filter = ""
            params = [puuid]
            if before_timestamp is not None:
                time_filter = "AND m.game_creation < ?"
                params.append(before_timestamp)

            query = f'''
                WITH recent_matches AS (
                    SELECT ps.champion_id, ps.champion_name, ps.team_id, m.team_100_win
                    FROM player_stats ps
                    JOIN matches m ON ps.match_id = m.match_id
                    WHERE ps.puuid = ? {time_filter}
                    ORDER BY m.game_creation DESC
                    LIMIT ?
                )
                SELECT
                    champion_id,
                    champion_name,
                    COUNT(*) as games,
                    SUM(CASE WHEN
                        (team_id = 100 AND team_100_win = 1) OR
                        (team_id = 200 AND team_100_win = 0)
                    THEN 1 ELSE 0 END) as wins
                FROM recent_matches
                GROUP BY champion_id, champion_name
                ORDER BY games DESC
            '''
            params.append(last_n_games)

            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

            result = []
            for row in rows:
                games = row['games']
                wins = row['wins']
                result.append({
                    'champion_id': row['champion_id'],
                    'champion_name': row['champion_name'] or f'Champion_{row["champion_id"]}',
                    'games': games,
                    'wins': wins,
                    'winrate': wins / games if games > 0 else 0.5
                })

            return result

    def get_encounter_frequency(self, puuid: str, opponent_puuids: List[str],
                                 teammate_puuids: List[str], before_timestamp: int = None) -> Dict[str, Any]:
        """
        Get how often this player has played with/against the specified players.

        Args:
            puuid: Player's PUUID
            opponent_puuids: List of opponent PUUIDs
            teammate_puuids: List of teammate PUUIDs
            before_timestamp: Only count matches before this timestamp

        Returns:
            Dict with:
            - total_encounters_with_opponents: int
            - total_encounters_with_teammates: int
            - opponent_familiarity: list of {puuid, games, winrate}
            - teammate_familiarity: list of {puuid, games, winrate}
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            time_filter = ""
            if before_timestamp is not None:
                time_filter = f"AND m.game_creation < {before_timestamp}"

            opponent_familiarity = []
            teammate_familiarity = []
            total_vs_opponents = 0
            total_with_teammates = 0

            # Check opponents (different team)
            for opp_puuid in opponent_puuids:
                if not opp_puuid:
                    continue
                query = f'''
                    SELECT
                        COUNT(*) as games,
                        SUM(CASE WHEN
                            (p1.team_id = 100 AND m.team_100_win = 1) OR
                            (p1.team_id = 200 AND m.team_100_win = 0)
                        THEN 1 ELSE 0 END) as wins
                    FROM player_stats p1
                    JOIN player_stats p2 ON p1.match_id = p2.match_id AND p1.team_id != p2.team_id
                    JOIN matches m ON p1.match_id = m.match_id
                    WHERE p1.puuid = ? AND p2.puuid = ? {time_filter}
                '''
                cursor.execute(query, (puuid, opp_puuid))
                row = cursor.fetchone()
                if row and row['games'] > 0:
                    games = row['games']
                    wins = row['wins'] or 0
                    opponent_familiarity.append({
                        'puuid': opp_puuid,
                        'games': games,
                        'winrate': wins / games
                    })
                    total_vs_opponents += games

            # Check teammates (same team)
            for tm_puuid in teammate_puuids:
                if not tm_puuid:
                    continue
                query = f'''
                    SELECT
                        COUNT(*) as games,
                        SUM(CASE WHEN
                            (p1.team_id = 100 AND m.team_100_win = 1) OR
                            (p1.team_id = 200 AND m.team_100_win = 0)
                        THEN 1 ELSE 0 END) as wins
                    FROM player_stats p1
                    JOIN player_stats p2 ON p1.match_id = p2.match_id AND p1.team_id = p2.team_id
                    JOIN matches m ON p1.match_id = m.match_id
                    WHERE p1.puuid = ? AND p2.puuid = ? AND p1.puuid != p2.puuid {time_filter}
                '''
                cursor.execute(query, (puuid, tm_puuid))
                row = cursor.fetchone()
                if row and row['games'] > 0:
                    games = row['games']
                    wins = row['wins'] or 0
                    teammate_familiarity.append({
                        'puuid': tm_puuid,
                        'games': games,
                        'winrate': wins / games
                    })
                    total_with_teammates += games

            return {
                'total_encounters_with_opponents': total_vs_opponents,
                'total_encounters_with_teammates': total_with_teammates,
                'opponent_familiarity': opponent_familiarity,
                'teammate_familiarity': teammate_familiarity
            }

    def get_all_summoner_stats_batch(self, puuids: List[str], before_timestamp: int = None,
                                      last_n_games: int = 20) -> Dict[str, Dict]:
        """
        Batch version of summoner stats retrieval for multiple players.
        Optimized for performance with chunking for large player lists.

        Args:
            puuids: List of player PUUIDs
            before_timestamp: Only count matches before this timestamp
            last_n_games: Number of recent games for certain stats

        Returns:
            Dict mapping puuid -> full stats dict with:
            - role_stats: from get_summoner_role_stats
            - performance: from get_summoner_role_performance
            - streaks: from get_summoner_streaks
            - recent_champions: from get_summoner_recent_champions
        """
        # Filter out None/empty puuids
        valid_puuids = [p for p in puuids if p]

        if not valid_puuids:
            return {}

        # SQLite has a limit of 999 parameters per query
        # We'll process in chunks of 500 to be safe
        CHUNK_SIZE = 500
        role_rows = {}
        perf_by_puuid = {}
        roles = ['top', 'jungle', 'mid', 'adc', 'support']

        with self.get_connection() as conn:
            cursor = conn.cursor()
            time_filter = ""
            time_param = []
            if before_timestamp is not None:
                time_filter = "AND m.game_creation < ?"
                time_param = [before_timestamp]

            # Process puuids in chunks
            for chunk_start in range(0, len(valid_puuids), CHUNK_SIZE):
                chunk = valid_puuids[chunk_start:chunk_start + CHUNK_SIZE]
                placeholders = ','.join(['?' for _ in chunk])

                # Batch query for role stats
                query = f'''
                    SELECT
                        ps.puuid,
                        COUNT(*) as total_games,
                        SUM(CASE WHEN ps.position = 'top' THEN 1 ELSE 0 END) as top_games,
                        SUM(CASE WHEN ps.position = 'jungle' THEN 1 ELSE 0 END) as jungle_games,
                        SUM(CASE WHEN ps.position = 'mid' THEN 1 ELSE 0 END) as mid_games,
                        SUM(CASE WHEN ps.position = 'adc' THEN 1 ELSE 0 END) as adc_games,
                        SUM(CASE WHEN ps.position = 'support' THEN 1 ELSE 0 END) as support_games,
                        SUM(CASE WHEN ps.position = 'top' AND
                            ((ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0))
                            THEN 1 ELSE 0 END) as top_wins,
                        SUM(CASE WHEN ps.position = 'jungle' AND
                            ((ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0))
                            THEN 1 ELSE 0 END) as jungle_wins,
                        SUM(CASE WHEN ps.position = 'mid' AND
                            ((ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0))
                            THEN 1 ELSE 0 END) as mid_wins,
                        SUM(CASE WHEN ps.position = 'adc' AND
                            ((ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0))
                            THEN 1 ELSE 0 END) as adc_wins,
                        SUM(CASE WHEN ps.position = 'support' AND
                            ((ps.team_id = 100 AND m.team_100_win = 1) OR (ps.team_id = 200 AND m.team_100_win = 0))
                            THEN 1 ELSE 0 END) as support_wins
                    FROM player_stats ps
                    JOIN matches m ON ps.match_id = m.match_id
                    WHERE ps.puuid IN ({placeholders}) {time_filter}
                    GROUP BY ps.puuid
                '''
                cursor.execute(query, chunk + time_param)
                for row in cursor.fetchall():
                    role_rows[row['puuid']] = dict(row)

                # Batch query for performance (KDA, vision)
                query = f'''
                    SELECT
                        ps.puuid,
                        ps.position,
                        AVG(ps.kda) as avg_kda,
                        AVG(ps.vision_score) as avg_vision
                    FROM player_stats ps
                    JOIN matches m ON ps.match_id = m.match_id
                    WHERE ps.puuid IN ({placeholders}) {time_filter}
                    GROUP BY ps.puuid, ps.position
                '''
                cursor.execute(query, chunk + time_param)
                for row in cursor.fetchall():
                    puuid = row['puuid']
                    if puuid not in perf_by_puuid:
                        perf_by_puuid[puuid] = {}
                    perf_by_puuid[puuid][row['position']] = {
                        'avg_kda': row['avg_kda'],
                        'avg_vision': row['avg_vision']
                    }

            # Build results
            results = {}

            for puuid in valid_puuids:
                # Role stats
                if puuid in role_rows:
                    row = role_rows[puuid]
                    total = row['total_games']
                    role_games = {role: row[f'{role}_games'] for role in roles}
                    role_wins = {role: row[f'{role}_wins'] for role in roles}
                    role_distribution = {role: role_games[role] / total if total > 0 else 0.2 for role in roles}
                    role_winrates = {
                        role: role_wins[role] / role_games[role] if role_games[role] > 0 else 0.5
                        for role in roles
                    }
                    role_stats = {
                        'total_games': total,
                        'role_distribution': role_distribution,
                        'role_winrates': role_winrates,
                        'role_games': role_games
                    }
                else:
                    role_stats = {
                        'total_games': 0,
                        'role_distribution': {role: 0.2 for role in roles},
                        'role_winrates': {role: 0.5 for role in roles},
                        'role_games': {role: 0 for role in roles}
                    }

                # Performance stats
                perf = perf_by_puuid.get(puuid, {})
                role_kda = {role: perf.get(role, {}).get('avg_kda', 2.0) or 2.0 for role in roles}
                role_vision = {role: perf.get(role, {}).get('avg_vision', 20.0) or 20.0 for role in roles}

                results[puuid] = {
                    'role_stats': role_stats,
                    'performance': {
                        'role_kda': role_kda,
                        'role_vision_score': role_vision
                    }
                }

            # Get streaks individually (complex query, not easily batched)
            for puuid in valid_puuids:
                results[puuid]['streaks'] = self.get_summoner_streaks(puuid, before_timestamp)
                results[puuid]['recent_champions'] = self.get_summoner_recent_champions(
                    puuid, before_timestamp, last_n_games
                )

            return results

    def get_summoner_champion_recent_winrate(self, puuid: str, champion_id: int,
                                              before_timestamp: int = None,
                                              last_n_games: int = 20) -> Dict[str, Any]:
        """
        Get a summoner's recent winrate on a specific champion.

        Args:
            puuid: Player's PUUID
            champion_id: Champion ID to check
            before_timestamp: Only count matches before this timestamp
            last_n_games: Number of recent games on this champion to consider

        Returns:
            Dict with games, wins, winrate for this champion
        """
        with self.get_connection() as conn:
            time_filter = ""
            params = [puuid, champion_id]
            if before_timestamp is not None:
                time_filter = "AND m.game_creation < ?"
                params.append(before_timestamp)

            query = f'''
                SELECT
                    COUNT(*) as games,
                    SUM(CASE WHEN
                        (ps.team_id = 100 AND m.team_100_win = 1) OR
                        (ps.team_id = 200 AND m.team_100_win = 0)
                    THEN 1 ELSE 0 END) as wins
                FROM (
                    SELECT ps.team_id, ps.match_id
                    FROM player_stats ps
                    JOIN matches m ON ps.match_id = m.match_id
                    WHERE ps.puuid = ? AND ps.champion_id = ? {time_filter}
                    ORDER BY m.game_creation DESC
                    LIMIT ?
                ) as recent
                JOIN matches m ON recent.match_id = m.match_id
            '''
            params.append(last_n_games)

            # Simpler query without subquery limit issue
            query = f'''
                WITH recent_champ_games AS (
                    SELECT ps.team_id, m.team_100_win
                    FROM player_stats ps
                    JOIN matches m ON ps.match_id = m.match_id
                    WHERE ps.puuid = ? AND ps.champion_id = ? {time_filter}
                    ORDER BY m.game_creation DESC
                    LIMIT ?
                )
                SELECT
                    COUNT(*) as games,
                    SUM(CASE WHEN
                        (team_id = 100 AND team_100_win = 1) OR
                        (team_id = 200 AND team_100_win = 0)
                    THEN 1 ELSE 0 END) as wins
                FROM recent_champ_games
            '''

            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()

            if not row or row['games'] == 0:
                return {'games': 0, 'wins': 0, 'winrate': 0.5}

            games = row['games']
            wins = row['wins'] or 0
            return {
                'games': games,
                'wins': wins,
                'winrate': wins / games if games > 0 else 0.5
            }


# Utility function for testing
def test_database():
    """Test database operations"""
    import os

    test_db = 'test_lol_matches.db'

    try:
        db = MatchDatabase(test_db)

        # Test with sample data
        sample_match = {
            "metadata": {"matchId": "TEST_123"},
            "info": {
                "gameCreation": 1234567890,
                "gameDuration": 1800,
                "gameVersion": "14.1",
                "queueId": 420,
                "mapId": 11,
                "gameMode": "CLASSIC",
                "gameType": "MATCHED_GAME",
                "teams": [
                    {
                        "teamId": 100,
                        "win": True,
                        "objectives": {
                            "champion": {"first": True, "kills": 0},
                            "dragon": {"first": True, "kills": 3},
                            "baron": {"first": False, "kills": 0},
                            "tower": {"first": True, "kills": 5},
                            "inhibitor": {"first": True, "kills": 1},
                            "riftHerald": {"first": True, "kills": 2}
                        },
                        "bans": [
                            {"championId": 1, "pickTurn": 1},
                            {"championId": 2, "pickTurn": 2}
                        ]
                    },
                    {
                        "teamId": 200,
                        "win": False,
                        "objectives": {
                            "champion": {"first": False, "kills": 0},
                            "dragon": {"first": False, "kills": 1},
                            "baron": {"first": False, "kills": 0},
                            "tower": {"first": False, "kills": 2},
                            "inhibitor": {"first": False, "kills": 0},
                            "riftHerald": {"first": False, "kills": 0}
                        },
                        "bans": []
                    }
                ],
                "participants": [
                    {
                        "teamId": 100,
                        "teamPosition": "TOP",
                        "championId": 86,
                        "championName": "Garen",
                        "kills": 5,
                        "deaths": 2,
                        "assists": 10,
                        "goldEarned": 12000,
                        "totalMinionsKilled": 200,
                        "visionScore": 30,
                        "challenges": {"kda": 7.5}
                    }
                ]
            }
        }

        # Test insert
        result = db.insert_match(sample_match)
        print(f"Insert result: {result}")

        # Test exists
        exists = db.match_exists("TEST_123")
        print(f"Match exists: {exists}")

        # Test duplicate
        result2 = db.insert_match(sample_match)
        print(f"Duplicate insert result: {result2}")

        # Test player progress
        db.save_player_progress("test_puuid_123")
        is_processed = db.is_player_processed("test_puuid_123")
        print(f"Player processed: {is_processed}")

        # Test stats
        db.increment_stat('total_requests', 5)
        stats = db.get_stats()
        print(f"Stats: {stats}")

        # Test export
        df = db.export_to_dataframe()
        print(f"DataFrame shape: {df.shape}")
        print(f"Columns: {list(df.columns)[:10]}...")

        print("\nAll tests passed!")

    finally:
        if os.path.exists(test_db):
            os.remove(test_db)


if __name__ == "__main__":
    test_database()
