# Collection config for the legacy data layer used by the Streamlit app
# (src/collect_data/database.py -> MatchDatabase reads REGION from here).
#
# SECURITY: Riot API keys are NEVER committed. Data collection (out of scope for
# the Streamlit display) reads them from the environment instead, e.g.
#   export RIOT_API_KEYS="key1,key2,..."
import os

API_KEYS = [k.strip() for k in os.getenv("RIOT_API_KEYS", "").split(",") if k.strip()]
API_KEY = API_KEYS[0] if API_KEYS else os.getenv("RIOT_API_KEY", "")

REGION = "euw1"              # Région du shard LoL (euw1, na1, kr, etc.)
QUEUE = "RANKED_SOLO_5x5"
TIER = "DIAMOND"
DIVISION = "I"
