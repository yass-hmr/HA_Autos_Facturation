# HA Facturation

Application de facturation bureau pour garage automobile indépendant.  
Fonctionne hors ligne, zéro serveur, déployable en `.exe` autonome.

---

## Fonctionnalités

| Fonctionnalité | Détail |
| --- | --- |
| Gestion des factures | Créer, modifier, rechercher, supprimer |
| Numérotation automatique | Compteur auto-incrémenté (001, 002…) |
| Calcul en temps réel | Sous-total HT · TVA 20% · Total TTC recalculés à chaque saisie |
| Export PDF | Mise en page professionnelle avec logo, coordonnées garage, tableau lignes |
| Partage e-mail | Template pré-rempli avec signature du garage, ouvre le client mail |
| Paramètres garage | Nom, adresse, SIRET, téléphone, email |
| Sauvegarde automatique | Backup SQLite atomique vers OneDrive toutes les 30 min (dirty flag) |
| Interface multi-onglets | Onglets fixes + onglets éditeur dynamiques et fermables |
| Application portable | Packaging PyInstaller — un seul `.exe`, aucune installation requise |

---

## Stack technique

- **Python 3** — logique métier et orchestration
- **PySide6** — interface graphique native Qt6 (Windows)
- **SQLite** — base de données locale, zéro configuration
- **ReportLab** — génération PDF pure Python
- **PyInstaller** — empaquetage en exécutable autonome

---

## Architecture

```text
app/
├── domain/          # Logique métier pure (calculs, conversions monétaires)
├── db/              # Accès données : connexion, schema SQL, repositories
│   └── repos/       # Un repository par entité (Invoice, Pdf, Settings)
├── backup/          # Sauvegarde automatique (BackupManager + BackupScheduler)
├── pdf/             # Génération PDF avec ReportLab
├── ui/              # Widgets PySide6 (liste, éditeur, paramètres)
└── utils/           # Utilitaires transverses (chemins, dates)
```

Séparation stricte des couches : la UI ne contient aucun SQL, le domaine ne dépend d'aucun framework.  
Les montants sont stockés en **centimes** (entiers) pour éviter les erreurs d'arrondi flottant.

---

## Lancement en développement

```bash
# Créer et activer l'environnement virtuel
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/Mac

# Installer les dépendances
pip install -r requirements.txt

# Lancer l'application
python -m app.main
```

---

## Build — packaging en .exe

```bash
pyinstaller HA_Facturation.spec
# Exécutable généré dans : dist/HA_Facturation/HA_Facturation.exe
```

Le `.spec` inclut automatiquement le schéma SQL et les assets (logo, icône).  
En mode frozen, les données utilisateur sont stockées dans `%APPDATA%\HA_Facturation\`.

---

## Dépendances

```text
PySide6>=6.5
reportlab>=4.0
```
