# MLOPS — LOL Draft Analyzer

Projet MLOps pour la prédiction de résultats de matchs League of Legends à partir de la composition d'équipe (draft).

## Architecture

```
MLOPS---LOL-draft-analyzer/
├── database/                       # Base de données PostgreSQL (Docker)
│   ├── docker-compose.yml
│   ├── init.sql
│   ├── migrate_sqlite_to_postgres.py
│   ├── .env.example
│   └── README.md
└── README.md
```

## Démarrage rapide

### Prérequis

- Docker Desktop
- Python 3.8+
- Le fichier `lol_matches.db` (base SQLite source, ~2.8 Go)

### 1. Cloner le repo

```bash
git clone <repo-url>
cd MLOPS---LOL-draft-analyzer
```

### 2. Lancer la base de données

```bash
cd database
cp .env.example .env
docker compose up -d
```

### 3. Migrer les données

```bash
pip install psycopg2-binary
python migrate_sqlite_to_postgres.py --sqlite-path /chemin/vers/lol_matches.db
```

### 4. Vérifier

```bash
docker exec -it lol_draft_db psql -U lol_admin -d lol_draft -c "SELECT COUNT(*) FROM matches;"
```

## Données

~12 millions de lignes issues de l'API Riot Games :

- **305K** matchs ranked SoloQ (patches 15.x → 16.x)
- **3M** statistiques joueurs (KDA, damage, gold, vision)
- **4.4M** données timeline minute par minute
- **2.5M** événements in-game (kills, objectifs)
- **1.6M** maîtrises de champions
- Synergies et matchups de champions (op.gg)

## Connexion à la base

```
postgresql://lol_admin:lol_draft_2025@localhost:5434/lol_draft
```
