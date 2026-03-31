# Database — PostgreSQL

Base de données PostgreSQL contenant les données de matchs League of Legends collectées via l'API Riot.

## Prérequis

- [Docker](https://docs.docker.com/get-docker/) (Docker Desktop ou Docker Engine)

## Installation (2 commandes)

```bash
cd database/
cp .env.example .env
docker compose up -d
```

C'est tout. Le dump (~747 Mo) se restaure automatiquement au premier lancement.
La base est prête quand le healthcheck passe :

```bash
docker compose ps
# STATUS: healthy
```

## Connexion

```
postgresql://lol_admin:lol_draft_2025@localhost:5434/lol_draft
```

```python
import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5434,
    database="lol_draft",
    user="lol_admin",
    password="lol_draft_2025"
)
```

Via le conteneur :
```bash
docker exec -it lol_draft_db psql -U lol_admin -d lol_draft
```

## Schéma

| Table | Description | ~Lignes |
|---|---|---|
| `matches` | Matchs ranked SoloQ | 305K |
| `player_stats` | Stats joueur par match (KDA, damage, gold, vision) | 3M |
| `team_stats` | Stats équipe (bans, objectifs, firsts) | 611K |
| `match_timeline` | Gold/XP/CS/Level par minute par position | 4.4M |
| `match_events` | Événements (kills, dragons, tours...) | 2.5M |
| `champion_mastery` | Maîtrise des champions par joueur | 1.6M |
| `champion_patch_stats` | Winrate/pickrate/banrate par patch | 3.6K |
| `champion_synergies` | Synergies entre champions (op.gg) | 15K |
| `champion_matchups` | Matchups entre champions (op.gg) | 8.6K |
| `summoners` | Profils joueurs | — |
| `patches` | Versions du jeu | — |

## Commandes utiles

```bash
# Arrêter
docker compose down

# Arrêter et supprimer les données
docker compose down -v

# Logs
docker logs lol_draft_db

# Backup
docker exec lol_draft_db pg_dump -U lol_admin lol_draft > backup.sql
```

## Structure

```
database/
├── docker-compose.yml     # Conteneur PostgreSQL
├── init.sql               # Schéma SQL (15 tables + index)
├── restore.sh             # Script de restauration automatique
├── lol_draft.dump         # Dump compressé (~747 Mo)
├── .env.example           # Variables d'environnement (template)
├── migrate_sqlite_to_postgres.py  # (optionnel) migration depuis SQLite
└── README.md
```
