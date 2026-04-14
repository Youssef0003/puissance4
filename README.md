# Puissance 4 - Application de jeu et d'analyse

Projet développé par **Kassou Youssef**

## Description

Application web de Puissance 4 développée avec Flask, permettant de jouer contre une IA, contre un autre joueur, ou de faire s'affronter deux IA. Le projet inclut une base de données PostgreSQL pour stocker et analyser les parties.

## Fonctionnalités

- **3 modes de jeu** : Joueur vs Joueur, Joueur vs IA, IA vs IA
- **IA Minimax** avec élagage alpha-bêta et profondeur configurable
- **IA Aléatoire** pour les parties rapides
- **Visualisation des scores Minimax** en temps réel sous chaque colonne
- **Sauvegarde et chargement** de parties en local
- **Base de données PostgreSQL** pour stocker l'historique des parties
- **Export CSV** des parties et statistiques
- **Import de séquences** de coups depuis un fichier
- **Plateau personnalisé** dessinable manuellement
- **Génération automatique** de parties IA pour alimenter la base
- Plateau **9x9**

## Stack technique

- **Backend** : Python 3, Flask
- **Base de données** : PostgreSQL
- **Serveur** : Gunicorn + Nginx
- **Frontend** : HTML, CSS, Bootstrap 5, JavaScript

## Installation

```bash
# Cloner le projet
git clone https://github.com/Youssef0003/puissance4.git
cd puissance4

# Créer un environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Lancer l'application
python3 app.py
```

## Configuration

- La connexion à la base de données se configure dans `app.py` (host, user, password, db_name)
- Les paramètres de l'IA Minimax se configurent dans `minimax_config.json`

## Structure du projet

```
puissance4/
├── app.py                  # Application principale Flask
├── db_manager.py           # Gestionnaire base de données
├── wsgi.py                 # Point d'entrée Gunicorn
├── gunicorn.conf.py        # Configuration Gunicorn
├── minimax_config.json     # Configuration IA Minimax
├── requirements.txt        # Dépendances Python
├── static/                 # Fichiers CSS et JS
├── templates/              # Templates HTML
└── saves/                  # Parties sauvegardées localement
```

## © Kassou Youssef 2026
