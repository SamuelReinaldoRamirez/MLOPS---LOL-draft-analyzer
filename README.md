# MLOPS — LOL Draft Analyzer

Projet MLOps pour la prédiction de résultats de matchs League of Legends à partir de la composition d'équipe (draft).

## Démarrage rapide

### Prérequis

- Docker Desktop

### Installation

```bash
git clone <repo-url>
cd MLOPS---LOL-draft-analyzer/database
```

Télécharger le dump de la base (~747 Mo) :
> https://drive.google.com/drive/folders/14YpB_eyofJiXBE38qdKgSR6SNOWkpcVh?usp=sharing

Placer `lol_draft.dump` dans le dossier `database/`, puis :

```bash
cp .env.example .env
docker compose up -d
```

La base PostgreSQL démarre avec **12M+ lignes** pré-chargées. Prêt en ~1 min.

### Vérifier

```bash
docker exec -it lol_draft_db psql -U lol_admin -d lol_draft -c "SELECT COUNT(*) FROM matches;"
# → 305591
```

## Connexion

```
postgresql://lol_admin:lol_draft_2025@localhost:5434/lol_draft
```

## Architecture

```
MLOPS---LOL-draft-analyzer/
├── database/                          # Base PostgreSQL (Docker)
│   ├── docker-compose.yml
│   ├── init.sql                       # Schéma (15 tables)
│   ├── restore.sh                     # Auto-restore au 1er lancement
│   ├── lol_draft.dump                 # Données compressées (~747 Mo)
│   ├── migrate_sqlite_to_postgres.py  # Migration SQLite (optionnel)
│   ├── .env.example
│   └── README.md
├── .gitignore
└── README.md
```

## Données

~12 millions de lignes issues de l'API Riot Games :

- **305K** matchs ranked SoloQ (patches 15.x → 16.x)
- **3M** statistiques joueurs (KDA, damage, gold, vision)
- **4.4M** données timeline minute par minute
- **2.5M** événements in-game (kills, objectifs)
- **1.6M** maîtrises de champions
- Synergies et matchups de champions (op.gg)
