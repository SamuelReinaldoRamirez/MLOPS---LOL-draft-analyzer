# streamlit_app/

Application Streamlit de présentation et prédiction interactive.

## Lancement

```bash
streamlit run streamlit_app/app.py
```

## Structure

| Fichier / Dossier | Description |
|---|---|
| `app.py` | Point d'entrée, dashboard d'accueil, CSS global et sidebar |
| `config.py` | Configuration (couleurs, chemins, benchmarks modèles, descriptions features) |
| `pages/` | Pages de l'application (navigation automatique via sidebar) |
| `utils/` | Utilitaires (chargement données, modèles, feature builder) |
| `components/` | Composants UI réutilisables |

## Pages

| Page | Description |
|---|---|
| `1_Presentation.py` | Contexte LoL, draft, problématique ML, données |
| `2_Donnees.py` | Exploration du dataset, visualisations interactives |
| `3_Traitement.py` | Pipeline de données, feature engineering, vecteur d'entrée |
| `4_Modeles.py` | Algorithmes (XGBoost, LightGBM), comparaison, feature importance |
| `5_Resultats.py` | Évaluation (confusion, ROC), comparaison des 5 modèles, prédiction interactive |
