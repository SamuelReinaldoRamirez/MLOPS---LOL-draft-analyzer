-- ============================================================
-- LOL Draft Analyzer — PostgreSQL Schema
-- 15 tables, ~12M rows from Riot API match data
-- ============================================================

-- Matches (305K ranked SoloQ games)
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    game_creation BIGINT,
    game_duration INTEGER,
    game_version TEXT,
    queue_id INTEGER DEFAULT 420,
    map_id INTEGER,
    game_mode TEXT,
    game_type TEXT,
    team_100_win SMALLINT,
    team_100_early_surrendered SMALLINT DEFAULT 0,
    team_200_early_surrendered SMALLINT DEFAULT 0,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    region TEXT,
    source_elo TEXT
);

-- Team stats (bans, objectives, firsts)
CREATE TABLE IF NOT EXISTS team_stats (
    id SERIAL PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(match_id),
    team_id INTEGER NOT NULL,
    first_blood SMALLINT,
    first_tower SMALLINT,
    first_inhibitor SMALLINT,
    first_dragon SMALLINT,
    first_rift_herald SMALLINT,
    first_baron SMALLINT,
    dragon_kills INTEGER DEFAULT 0,
    baron_kills INTEGER DEFAULT 0,
    tower_kills INTEGER DEFAULT 0,
    inhibitor_kills INTEGER DEFAULT 0,
    rift_herald_kills INTEGER DEFAULT 0,
    ban_1_champion_id INTEGER,
    ban_2_champion_id INTEGER,
    ban_3_champion_id INTEGER,
    ban_4_champion_id INTEGER,
    ban_5_champion_id INTEGER,
    ban_1_name TEXT,
    ban_2_name TEXT,
    ban_3_name TEXT,
    ban_4_name TEXT,
    ban_5_name TEXT,
    UNIQUE(match_id, team_id)
);

-- Player stats (KDA, damage, gold, vision per player per match)
CREATE TABLE IF NOT EXISTS player_stats (
    id SERIAL PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(match_id),
    team_id INTEGER NOT NULL,
    position TEXT NOT NULL,
    champion_id INTEGER NOT NULL,
    champion_name TEXT,
    champ_level INTEGER,
    summoner_1_id INTEGER,
    summoner_2_id INTEGER,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    total_damage_dealt INTEGER,
    total_damage_to_champions INTEGER,
    total_damage_taken INTEGER,
    true_damage_dealt INTEGER,
    physical_damage_dealt INTEGER,
    magic_damage_dealt INTEGER,
    gold_earned INTEGER,
    total_minions_killed INTEGER,
    neutral_minions_killed INTEGER,
    vision_score INTEGER,
    wards_placed INTEGER,
    wards_killed INTEGER,
    vision_wards_bought INTEGER,
    enemy_champion_immobilizations INTEGER DEFAULT 0,
    first_blood_kill SMALLINT,
    first_tower_kill SMALLINT,
    turret_kills INTEGER,
    inhibitor_kills INTEGER,
    largest_killing_spree INTEGER,
    largest_multi_kill INTEGER,
    killing_sprees INTEGER,
    double_kills INTEGER,
    triple_kills INTEGER,
    quadra_kills INTEGER,
    penta_kills INTEGER,
    damage_per_minute REAL,
    damage_taken_percentage REAL,
    gold_per_minute REAL,
    team_damage_percentage REAL,
    kill_participation REAL,
    kda REAL,
    lane_minions_first_10_min INTEGER,
    turret_plates_taken INTEGER,
    solo_kills INTEGER,
    puuid TEXT,
    riot_id_name TEXT,
    riot_id_tagline TEXT,
    summoner_1_name TEXT,
    summoner_2_name TEXT,
    UNIQUE(match_id, team_id, position)
);

-- Summoners
CREATE TABLE IF NOT EXISTS summoners (
    puuid TEXT PRIMARY KEY,
    riot_id_name TEXT,
    riot_id_tagline TEXT,
    current_tier TEXT,
    current_rank TEXT,
    current_lp INTEGER,
    total_games_tracked INTEGER DEFAULT 0,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Summoner elo history
CREATE TABLE IF NOT EXISTS summoner_elo_history (
    id SERIAL PRIMARY KEY,
    puuid TEXT NOT NULL REFERENCES summoners(puuid),
    patch TEXT NOT NULL,
    tier TEXT,
    rank TEXT,
    lp INTEGER,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(puuid, patch)
);

-- Champion mastery
CREATE TABLE IF NOT EXISTS champion_mastery (
    id SERIAL PRIMARY KEY,
    puuid TEXT NOT NULL,
    champion_id INTEGER NOT NULL,
    champion_level INTEGER,
    champion_points INTEGER,
    last_play_time BIGINT,
    tokens_earned INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(puuid, champion_id)
);

-- Patches
CREATE TABLE IF NOT EXISTS patches (
    patch TEXT PRIMARY KEY,
    release_date DATE,
    data_dragon_version TEXT,
    notes_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Champion stats per patch (winrate, pickrate, banrate)
CREATE TABLE IF NOT EXISTS champion_patch_stats (
    id SERIAL PRIMARY KEY,
    champion_id INTEGER NOT NULL,
    patch TEXT NOT NULL,
    games_played INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    bans INTEGER DEFAULT 0,
    winrate REAL,
    pickrate REAL,
    banrate REAL,
    top_games INTEGER DEFAULT 0,
    jungle_games INTEGER DEFAULT 0,
    mid_games INTEGER DEFAULT 0,
    adc_games INTEGER DEFAULT 0,
    support_games INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    opgg_winrate REAL,
    opgg_pickrate REAL,
    opgg_banrate REAL,
    opgg_tier TEXT,
    opgg_updated_at TIMESTAMP,
    UNIQUE(champion_id, patch)
);

-- Match timeline (gold, xp, cs, level per minute per position)
CREATE TABLE IF NOT EXISTS match_timeline (
    id SERIAL PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(match_id),
    minute INTEGER NOT NULL,
    team_100_gold INTEGER,
    team_200_gold INTEGER,
    gold_diff INTEGER,
    team_100_top_gold INTEGER,
    team_100_jungle_gold INTEGER,
    team_100_mid_gold INTEGER,
    team_100_adc_gold INTEGER,
    team_100_support_gold INTEGER,
    team_200_top_gold INTEGER,
    team_200_jungle_gold INTEGER,
    team_200_mid_gold INTEGER,
    team_200_adc_gold INTEGER,
    team_200_support_gold INTEGER,
    team_100_top_level INTEGER,
    team_100_jungle_level INTEGER,
    team_100_mid_level INTEGER,
    team_100_adc_level INTEGER,
    team_100_support_level INTEGER,
    team_200_top_level INTEGER,
    team_200_jungle_level INTEGER,
    team_200_mid_level INTEGER,
    team_200_adc_level INTEGER,
    team_200_support_level INTEGER,
    team_100_top_xp INTEGER,
    team_100_jungle_xp INTEGER,
    team_100_mid_xp INTEGER,
    team_100_adc_xp INTEGER,
    team_100_support_xp INTEGER,
    team_200_top_xp INTEGER,
    team_200_jungle_xp INTEGER,
    team_200_mid_xp INTEGER,
    team_200_adc_xp INTEGER,
    team_200_support_xp INTEGER,
    team_100_top_cs INTEGER,
    team_100_jungle_cs INTEGER,
    team_100_mid_cs INTEGER,
    team_100_adc_cs INTEGER,
    team_100_support_cs INTEGER,
    team_200_top_cs INTEGER,
    team_200_jungle_cs INTEGER,
    team_200_mid_cs INTEGER,
    team_200_adc_cs INTEGER,
    team_200_support_cs INTEGER,
    UNIQUE(match_id, minute)
);

-- Match events (kills, objectives, buildings)
CREATE TABLE IF NOT EXISTS match_events (
    id SERIAL PRIMARY KEY,
    match_id TEXT NOT NULL REFERENCES matches(match_id),
    event_type TEXT NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    minute INTEGER,
    killer_id INTEGER,
    victim_id INTEGER,
    killer_team_id INTEGER,
    monster_type TEXT,
    monster_subtype TEXT,
    building_type TEXT,
    lane_type TEXT,
    tower_type TEXT,
    team_id INTEGER
);

-- Champion synergies (op.gg data)
CREATE TABLE IF NOT EXISTS champion_synergies (
    id SERIAL PRIMARY KEY,
    champion_id INTEGER NOT NULL,
    champion_name TEXT NOT NULL,
    ally_champion_id INTEGER NOT NULL,
    ally_champion_name TEXT NOT NULL,
    role TEXT NOT NULL,
    ally_role TEXT NOT NULL,
    games_played INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    winrate REAL,
    region TEXT DEFAULT 'kr',
    tier TEXT DEFAULT 'diamond_plus',
    patch TEXT,
    source TEXT DEFAULT 'opgg',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Champion matchups (op.gg data)
CREATE TABLE IF NOT EXISTS champion_matchups (
    id SERIAL PRIMARY KEY,
    champion_id INTEGER NOT NULL,
    champion_name TEXT NOT NULL,
    enemy_champion_id INTEGER NOT NULL,
    enemy_champion_name TEXT NOT NULL,
    role TEXT NOT NULL,
    games_played INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    winrate REAL,
    gold_diff REAL,
    kill_diff REAL,
    region TEXT DEFAULT 'kr',
    tier TEXT DEFAULT 'diamond_plus',
    patch TEXT,
    source TEXT DEFAULT 'opgg',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Collection tracking
CREATE TABLE IF NOT EXISTS collection_progress (
    id SERIAL PRIMARY KEY,
    puuid TEXT UNIQUE,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS collection_stats (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Summoner role stats
CREATE TABLE IF NOT EXISTS summoner_role_stats (
    id SERIAL PRIMARY KEY,
    puuid TEXT NOT NULL,
    role TEXT NOT NULL,
    games INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0,
    UNIQUE(puuid, role)
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_matches_game_creation ON matches(game_creation);
CREATE INDEX IF NOT EXISTS idx_matches_region ON matches(region);
CREATE INDEX IF NOT EXISTS idx_player_stats_champion ON player_stats(champion_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_match ON player_stats(match_id);
CREATE INDEX IF NOT EXISTS idx_player_stats_puuid ON player_stats(puuid);
CREATE INDEX IF NOT EXISTS idx_team_stats_match ON team_stats(match_id);
CREATE INDEX IF NOT EXISTS idx_match_timeline_match ON match_timeline(match_id);
CREATE INDEX IF NOT EXISTS idx_match_events_match ON match_events(match_id);
CREATE INDEX IF NOT EXISTS idx_match_events_type ON match_events(event_type);
CREATE INDEX IF NOT EXISTS idx_champion_mastery_puuid ON champion_mastery(puuid);
CREATE INDEX IF NOT EXISTS idx_champion_patch_stats_champ ON champion_patch_stats(champion_id);
