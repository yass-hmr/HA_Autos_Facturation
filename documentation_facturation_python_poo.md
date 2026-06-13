# Documentation technique — HA Facturation (Python POO)

> Destinée à la préparation d'entretien — Licence 3 Développement / BTS SIO SLAM  
> Projet : application de facturation bureau pour garages automobiles indépendants  
> Stack : Python 3 · PySide6 · SQLite · ReportLab · PyInstaller

---

## Table des matières

1. [Présentation du projet](#1-présentation-du-projet)
2. [Architecture générale](#2-architecture-générale)
3. [Architecture POO — classes, attributs, méthodes, relations](#3-architecture-poo)
4. [Décisions techniques importantes](#4-décisions-techniques-importantes)
5. [Concepts clés à retenir](#5-concepts-clés-à-retenir)
6. [Points faibles et améliorations production](#6-points-faibles-et-améliorations-production)
7. [Correspondances Django + React](#7-correspondances-django--react)
8. [Questions / réponses entretien](#8-questions--réponses-entretien)
9. [Ce que je retiens de ce projet](#9-ce-que-je-retiens-de-ce-projet)

---

## 1. Présentation du projet

### Domaine métier

HA Facturation est une **application bureau** destinée à un gérant de garage automobile indépendant. Elle lui permet de créer et gérer ses factures sans connexion internet, de générer des PDF professionnels et de sauvegarder automatiquement sa base de données vers OneDrive.

### Fonctionnalités implémentées

| Fonctionnalité | Détail |
|---|---|
| Gestion des factures | Créer, modifier, rechercher, supprimer |
| Numérotation automatique | Compteur auto-incrémenté (001, 002…) |
| Calcul automatique | Sous-total HT, TVA 20%, Total TTC en temps réel |
| Génération PDF | Mise en page professionnelle avec logo garage |
| Partage par email | Template pré-rempli avec coordonnées du garage |
| Paramètres garage | Nom, SIRET, adresse, téléphone, email |
| Sauvegarde automatique | Backup SQLite vers OneDrive toutes les 30 min |
| Interface multi-onglets | Onglets fixes (Factures, PDF, Paramètres) + onglets éditeur dynamiques |
| Déploiement exe | Packaging PyInstaller en `.exe` autonome |

### Technologie choisie et pourquoi

- **PySide6** : binding officiel Qt6 pour Python — framework GUI mature, widgets natifs Windows
- **SQLite** : base de données fichier — zéro serveur, idéal pour un poste local mono-utilisateur
- **ReportLab** : bibliothèque PDF pure Python — contrôle absolu du rendu, pas de dépendance externe
- **PyInstaller** : empaquetage en `.exe` autonome — le gérant installe un seul fichier

---

## 2. Architecture générale

### Arborescence du projet

```
ha_facturation/
├── app/
│   ├── main.py                  ← Point d'entrée + composition root
│   ├── domain/                  ← Logique métier pure (sans dépendances UI/DB)
│   │   ├── money.py             ← Conversion euros ↔ centimes
│   │   └── invoice_calc.py      ← Calcul sous-total / TVA / total
│   ├── db/                      ← Accès données
│   │   ├── db.py                ← Connexion SQLite + init schema + migrations
│   │   ├── schema.sql           ← Schéma déclaratif des tables
│   │   └── repos/               ← Un dépôt par entité
│   │       ├── invoice_repo.py
│   │       ├── pdf_repo.py
│   │       └── settings_repo.py
│   ├── backup/                  ← Sauvegarde automatique
│   │   ├── backup_manager.py    ← Logique de copie SQLite
│   │   └── backup_scheduler.py  ← Timer périodique + dirty flag
│   ├── pdf/
│   │   └── render_invoice.py    ← Génération PDF avec ReportLab
│   ├── ui/                      ← Widgets PySide6
│   │   ├── invoices/
│   │   │   ├── invoice_list.py
│   │   │   └── invoice_editor.py
│   │   ├── pdfs/
│   │   │   └── pdf_list.py
│   │   └── settings/
│   │       └── main_window.py
│   └── utils/                   ← Utilitaires transverses
│       ├── dates.py
│       └── paths.py
└── requirements.txt
```

### Couches logiques

```
┌────────────────────────────────────────────────────┐
│  UI  (PySide6 Widgets — app/ui/)                   │ ← ce que l'utilisateur voit
├────────────────────────────────────────────────────┤
│  Domain  (app/domain/)                             │ ← règles métier pures
├────────────────────────────────────────────────────┤
│  Data Access  (app/db/repos/)                      │ ← requêtes SQL
├────────────────────────────────────────────────────┤
│  Infrastructure  (backup/, pdf/, utils/)           │ ← services techniques
├────────────────────────────────────────────────────┤
│  SQLite  (app/data/app.db)                         │ ← persistance
└────────────────────────────────────────────────────┘
```

> **Principe fondateur** : les couches basses ne connaissent pas les couches hautes. `domain/` n'importe rien de `ui/`. `db/` n'importe rien de `backup/`. C'est la règle de **dépendance dirigée vers le bas**.

---

## 3. Architecture POO

### Vue d'ensemble des classes

```
MainWindow (QMainWindow)
  ├── SettingsRepository
  ├── InvoiceRepository
  ├── PdfExportRepository
  ├── BackupScheduler (QObject)
  │     └── BackupManager
  ├── InvoiceListWidget (QWidget)
  ├── InvoiceEditorWidget (QWidget)  [0..N onglets]
  ├── PdfListWidget (QWidget)
  └── SettingsWidget (QWidget)

Dataclasses (objets valeur immuables) :
  InvoiceListItem, InvoiceHeader, InvoiceLine
  BackupResult, PdfExportItem, PdfResult

Fonctions domaine (pas de classe) :
  euros_to_cents(), cents_to_euros()
  calc_totals()
```

---

### 3.1 Couche Domain — `app/domain/`

#### `money.py`

```python
# Pourquoi des centimes et pas des float ?
# float("0.1") + float("0.2") = 0.30000000000000004 en Python
# En stockant 10 + 20 = 30 centimes (int), le calcul est exact.

def euros_to_cents(text: str) -> int:
    # Accepte "12", "12,5", "12.50", "  12,50 € "
    # Retourne 1250 pour "12,50"
    s = (text or "").strip().replace("€", "").strip()
    if not s:
        return 0
    s = s.replace(",", ".")
    # Regex : uniquement digits + éventuellement 2 décimales
    if not re.fullmatch(r"\d+(\.\d{0,2})?", s):
        raise ValueError("Prix invalide. Exemple: 12,50")
    euros, dec = s.split(".", 1) if "." in s else (s, "00")
    dec = (dec + "00")[:2]  # normalise à 2 chiffres après la virgule
    return int(euros) * 100 + int(dec)


def cents_to_euros(cents: int) -> str:
    # 1250 → "12.50 €"
    cents = abs(int(cents))
    return f"{cents // 100}.{cents % 100:02d} €"
```

> **Analogie** : c'est exactement ce que font les banques. Elles ne stockent jamais "12.50 €" mais l'entier `1250` (centimes ou "cents").

#### `invoice_calc.py`

```python
def calc_totals(lines: List[Tuple[int, int]]) -> tuple[int, int, int]:
    # Entrée : liste de (quantité, prix_unitaire_en_centimes)
    # Retourne : (sous-total, tva, total) — tous en centimes
    subtotal = sum(qty * up for qty, up in lines)
    vat = (subtotal * 20) // 100   # division entière = pas d'arrondi flottant
    return subtotal, vat, subtotal + vat
```

> **Séparation de responsabilité** : cette fonction ne sait pas ce qu'est une facture, un client, une base de données. Elle prend des nombres, rend des nombres. Elle peut être testée en isolation totale.

---

### 3.2 Couche Data — `app/db/`

#### `db.py` — Connexion et initialisation

```python
def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row    # accès par nom: row["customer_name"]
    conn.execute("PRAGMA foreign_keys = ON;")   # active les clés étrangères
    conn.execute("PRAGMA journal_mode = WAL;")  # write-ahead log = meilleure concurrence
    conn.execute("PRAGMA synchronous = NORMAL;") # équilibre perf/sécurité
    conn.execute("PRAGMA busy_timeout = 3000;")  # attend 3s si DB verrouillée
    return conn
```

> **Pourquoi `row_factory = sqlite3.Row`** : sans ça, `fetchone()` retourne un tuple et on accède par index (`row[3]`). Avec `Row`, on accède par nom (`row["customer_name"]`), ce qui rend le code lisible et résistant aux refactors de schéma.

#### `_migrate()` — Migrations sans ORM

```python
def _migrate(conn: sqlite3.Connection) -> None:
    # Ajoute les colonnes manquantes si la DB existante est une ancienne version
    if not _has_column(conn, "settings", "garage_postal_code"):
        conn.execute("ALTER TABLE settings ADD COLUMN garage_postal_code TEXT NOT NULL DEFAULT ''")
    # ... idem pour garage_siret, garage_email, customer_email, customer_phone...
```

> **Problème réel résolu** : l'utilisateur a installé la v1 de l'app, elle a créé sa base. Il installe la v2 qui ajoute un champ SIRET. Sans migration, l'app plante au lancement. Avec `ALTER TABLE ADD COLUMN`, la DB existante est mise à jour sans perte de données.

---

### 3.3 Repository Pattern — `app/db/repos/`

Le **Repository** est un objet dont la seule responsabilité est de savoir comment lire et écrire une entité en base. La UI ne voit jamais de SQL.

#### `InvoiceRepository`

```python
class InvoiceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn  # injection de dépendance : le repo ne crée pas sa connexion

    def list_invoices(self, search: str = "") -> List[InvoiceListItem]:
        # Retourne des dataclasses, jamais des Row SQLite brutes
        ...

    def create_draft(self, date_iso: str) -> int:
        # Crée une facture vide et retourne son id
        # Version robuste : inspecte PRAGMA table_info pour ne passer
        # que les colonnes réellement présentes dans la DB
        cols_in_db = {r["name"] for r in self.conn.execute("PRAGMA table_info(invoice)")}
        cols = [c for c in defaults.keys() if c in cols_in_db]
        ...

    def save_invoice(self, invoice_id, *, number, date_iso, ..., lines) -> None:
        # Auto-incrémente le numéro si le champ est vide
        if not number:
            number = self.next_invoice_number()
            self.bump_invoice_number()
        ...
        # Réécrit toutes les lignes (delete + insert) — simple et cohérent
        self.conn.execute("DELETE FROM invoice_line WHERE invoice_id = ?", (invoice_id,))
        for pos, (qty, ref, desc, unit_cents, total_cents) in enumerate(lines, start=1):
            self.conn.execute("INSERT INTO invoice_line ...", (...))
        self.conn.commit()
```

#### Dataclasses retournées

```python
@dataclass(frozen=True)   # frozen = immuable après création
class InvoiceHeader:
    id: int
    number: Optional[str]
    date: str
    customer_name: str
    customer_address: str
    customer_postal_code: str
    customer_email: str
    customer_phone: str
    subtotal_cents: int
    vat_rate: int
    vat_cents: int
    total_cents: int
```

> **Pourquoi `frozen=True`** : une fois lue de la DB, la facture ne doit pas être modifiée en mémoire silencieusement. Si un développeur écrit `header.total_cents = 999`, Python lève une `FrozenInstanceError`. C'est un filet de sécurité.

---

### 3.4 Couche Backup — `app/backup/`

Deux classes avec des responsabilités distinctes — exemple parfait du **Principe de Responsabilité Unique (SRP)**.

#### `BackupManager` — Le "comment" sauvegarder

```python
class BackupManager:
    def __init__(self, keep_last: int = 10, prefix: str = "backup") -> None:
        self.keep_last = keep_last  # rotation : garde les N plus récents
        self.prefix = prefix

    def create_backup(self, source_conn, target_dir) -> BackupResult:
        # API native sqlite3.Connection.backup() = copie atomique
        # Pas de corruption même si l'app plante au milieu
        dest_conn = sqlite3.connect(str(backup_path))
        source_conn.backup(dest_conn)  # ← une seule ligne, API standard
        dest_conn.commit()
        self._rotate_backups(target_dir)  # supprime les anciens
        return BackupResult(backup_path=backup_path, created_at_iso=...)
```

#### `BackupScheduler(QObject)` — Le "quand" sauvegarder

```python
class BackupScheduler(QObject):
    def __init__(self, *, conn, settings_repo, backup_manager, interval_minutes=30):
        self.db_dirty = False           # flag "des données ont changé"
        self.timer = QTimer(self)       # timer Qt intégré à la boucle d'événements
        self.timer.setInterval(interval_minutes * 60 * 1000)
        self.timer.timeout.connect(self._on_timer)

    def mark_dirty(self) -> None:
        self.db_dirty = True            # appelé après chaque sauvegarde de facture

    def try_backup_now(self, *, force: bool = False) -> bool:
        if not force and not self.db_dirty:
            return False  # rien n'a changé, on économise un accès disque
        # récupère le dossier OneDrive depuis les paramètres
        settings = self.settings_repo.get()
        target_dir = settings.get("onedrive_backup_dir")
        result = self.backup_manager.create_backup(self.conn, Path(target_dir))
        self.settings_repo.update_last_backup(result.created_at_iso)
        self.db_dirty = False
        return True
```

> **Analogie du dirty flag** : c'est exactement comme un document Word. Word ne sauvegarde pas automatiquement si vous n'avez rien modifié depuis le dernier enregistrement. Le flag `db_dirty` joue ce rôle.

**Relation entre les deux classes** : `BackupScheduler` **compose** `BackupManager`. Il en possède une instance et délègue le travail réel.

```
BackupScheduler
  ├── timer : QTimer           (composition — créé dans __init__)
  └── backup_manager : BackupManager  (composition par injection)
```

---

### 3.5 Couche UI — `app/ui/`

#### `MainWindow(QMainWindow)` — La composition root

```python
class MainWindow(QMainWindow):
    def __init__(self, conn, parent=None) -> None:
        # Création des repos (injection de la connexion partagée)
        self.settings_repo = SettingsRepository(conn)
        self.invoice_repo = InvoiceRepository(conn)
        self.pdf_repo = PdfExportRepository(conn)

        # Création du scheduler (injection des deps)
        backup_manager = BackupManager()
        self.backup = BackupScheduler(
            conn=conn,
            settings_repo=self.settings_repo,
            backup_manager=backup_manager,
        )

        # Gestion des onglets dynamiques
        self._open_invoice_editors: dict[int, InvoiceEditorWidget] = {}
        # Empêche d'ouvrir deux onglets pour la même facture
```

> **Composition root** : c'est ici et seulement ici qu'on assemble toutes les dépendances. `MainWindow` crée les repos, les donne aux widgets. Aucun widget ne crée lui-même sa connexion DB. C'est le principe d'**injection de dépendances**.

#### `InvoiceEditorWidget(QWidget)` — Les signaux Qt

```python
class InvoiceEditorWidget(QWidget):
    # Signaux = mécanisme d'événements Qt
    tab_title_changed = Signal(str)    # "Facture" → "Facture - 001"
    invoice_persisted = Signal(int)    # notifie qu'une facture a été créée/modifiée
    closed = Signal()                  # onglet fermé

    def __init__(self, *, repo, pdf_repo, backup_scheduler, invoice_id=None):
        # Si invoice_id est None → on crée un brouillon immédiatement
        self._load_or_create()

    def _recalc_totals(self) -> None:
        # Appelé à chaque changement dans le tableau
        # Calcule les totaux et met à jour les labels en temps réel
        for r in range(self.table.rowCount()):
            qty = self._parse_qty(self._item_text(r, 0))
            up_cents = self._parse_eur_to_cents(self._item_text(r, 3))
            line_total_cents = qty * up_cents
            # Met à jour la colonne Total (lecture seule) de la ligne
```

> **Signaux vs callbacks directs** : plutôt que de donner une référence directe à `MainWindow` à chaque `InvoiceEditorWidget`, on utilise des signaux. `MainWindow` souscrit (`connect`) aux signaux qui l'intéressent. L'éditeur ne sait pas qu'il est dans un onglet — il est découplé de son conteneur.

---

### 3.6 PDF — `app/pdf/render_invoice.py`

```python
def render_invoice_pdf(*, conn, invoice_id, out_path) -> PdfResult:
    # Instancie ses propres repos localement — accès en lecture seule
    settings_repo = SettingsRepository(conn)
    invoice_repo = InvoiceRepository(conn)

    s = settings_repo.get()     # paramètres du garage
    inv = invoice_repo.get_header(invoice_id)
    lines = invoice_repo.get_lines(invoice_id)

    c = canvas.Canvas(str(out_path), pagesize=A4)
    # Rendu en millimètres absolus (positions x, y sur la page)
    # ReportLab: y=0 est en bas, y=page_h est en haut
    ...
    c.save()
    return PdfResult(pdf_path=out_path)
```

> **Pas de classe ici, juste une fonction** : le rendu PDF est une opération sans état — on lui donne des données, elle produit un fichier. Une classe n'apporterait rien de plus.

---

### 3.7 Utilitaires — `app/utils/`

#### `paths.py` — Résolution des chemins dev vs exe

```python
def _is_frozen() -> bool:
    # PyInstaller met sys.frozen = True dans l'exe compilé
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

def app_data_dir() -> Path:
    if _is_frozen():
        # En exe : données dans %APPDATA%/HA_Facturation/ (Windows)
        return user_data_root() / "data"
    else:
        # En dev : données dans le repo Git (app/data/)
        return project_root() / "data"
```

> **Problème réel** : un exe PyInstaller est extrait dans un dossier temporaire `_MEIPASS`. On ne peut pas écrire dedans. `paths.py` centralise cette logique pour que tout le reste du code n'ait pas à y penser.

#### `dates.py` — Conversions de format

```python
def fr_to_iso(d: str) -> str:
    # "25/12/2024" → "2024-12-25" (format attendu par SQLite)

def iso_to_fr(d: str) -> str:
    # "2024-12-25" → "25/12/2024" (format affiché à l'utilisateur)
```

---

### 3.8 Schéma de base de données

```sql
-- Table singleton (id = 1 toujours) = configuration du garage
CREATE TABLE settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  garage_name TEXT NOT NULL DEFAULT '',
  garage_siret TEXT NOT NULL DEFAULT '',
  onedrive_backup_dir TEXT NOT NULL DEFAULT '',
  last_backup_at TEXT DEFAULT NULL
);

-- Compteur pour la numérotation auto des factures
CREATE TABLE counter (
  key TEXT PRIMARY KEY,
  value INTEGER NOT NULL
);
-- Initialisé à 1 ; incrémenté à chaque nouvelle facture numérotée

-- Facture entête
CREATE TABLE invoice (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  number TEXT UNIQUE,   -- UNIQUE + nullable = draft sans numéro possible
  date TEXT NOT NULL,
  customer_name TEXT NOT NULL DEFAULT '',
  subtotal_cents INTEGER NOT NULL DEFAULT 0,
  vat_rate INTEGER NOT NULL DEFAULT 20,
  vat_cents INTEGER NOT NULL DEFAULT 0,
  total_cents INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- Lignes de facture (1 facture → N lignes)
CREATE TABLE invoice_line (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL,
  position INTEGER NOT NULL,          -- ordre d'affichage
  reference TEXT NOT NULL DEFAULT '',
  qty INTEGER NOT NULL CHECK (qty >= 0),
  unit_price_cents INTEGER NOT NULL DEFAULT 0,
  line_total_cents INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (invoice_id) REFERENCES invoice(id) ON DELETE CASCADE
);

-- Métadonnées des PDFs exportés
CREATE TABLE pdf_export (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL,
  filename TEXT NOT NULL,
  rel_path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'INVOICE',
  FOREIGN KEY (invoice_id) REFERENCES invoice(id) ON DELETE CASCADE
);
```

**Relations** :

```
settings  (1 ligne)
counter   (1 ligne clé = 'invoice_number')
invoice   1 ─── N   invoice_line    (ON DELETE CASCADE)
invoice   1 ─── N   pdf_export      (ON DELETE CASCADE)
```

---

## 4. Décisions techniques importantes

### 4.1 Stocker les montants en centimes (int)

**Problème** : `0.1 + 0.2 = 0.30000000000000004` en virgule flottante (IEEE 754).  
**Solution** : tous les montants sont des entiers de centimes. `12,50 €` → `1250`.  
**Alternative rejetée** : `Decimal` de Python — plus précis mais verbeux et sérialisé comme texte en SQLite.  
**Alternative en production** : PostgreSQL offre le type `MONEY` ou `NUMERIC(10,2)`.

### 4.2 Pattern Repository

**Pourquoi** : la UI ne doit pas écrire de SQL. Demain si on migre de SQLite vers PostgreSQL, seuls les repos changent — pas les widgets.  
**Alternative** : accès direct depuis les widgets (anti-pattern fréquent chez les débutants, crée un couplage fort).  
**Avantage test** : on peut tester un repo avec une DB en mémoire (`sqlite3.connect(":memory:")`) sans interface graphique.

### 4.3 Injection de dépendance manuelle

```python
# La connexion est créée UNE seule fois dans main()
conn = connect(db_path)
# Puis injectée partout
invoice_repo = InvoiceRepository(conn)
pdf_repo = PdfExportRepository(conn)
backup = BackupScheduler(conn=conn, ...)
```

**Pourquoi une seule connexion** : SQLite n'est pas multi-thread par défaut. Partager une seule connexion dans le thread principal évite les problèmes de verrouillage.  
**Avantage** : les transactions sont cohérentes — un `commit()` dans un repo est visible immédiatement dans un autre.

### 4.4 Dirty flag pour la sauvegarde

**Problème** : faire un backup toutes les 30 minutes même si rien n'a changé gaspille des ressources (et peut saturer OneDrive).  
**Solution** : `db_dirty = True` positionné seulement après un `save_invoice()` ou un export PDF. Le timer vérifie ce flag avant d'agir.  
**Analogie** : identique au comportement de "l'étoile" dans un titre de fenêtre (`MonFichier *`) qui indique des modifications non sauvegardées.

### 4.5 `create_draft()` dynamique (inspection PRAGMA)

```python
# Inspecte les colonnes réellement présentes avant d'insérer
cols_in_db = {r["name"] for r in self.conn.execute("PRAGMA table_info(invoice)")}
cols = [c for c in defaults.keys() if c in cols_in_db]
```

**Problème** : un utilisateur a une DB v1 sans les colonnes `customer_email` et `customer_phone`. Un `INSERT` avec ces colonnes planterait.  
**Solution** : construire l'INSERT dynamiquement selon ce qui existe réellement. C'est une forme de **programmation défensive**.

### 4.6 Réecriture complète des lignes (`DELETE` + `INSERT`)

```python
# Dans save_invoice()
self.conn.execute("DELETE FROM invoice_line WHERE invoice_id = ?", (invoice_id,))
for pos, (...) in enumerate(lines, start=1):
    self.conn.execute("INSERT INTO invoice_line ...", (...))
```

**Alternative** : identifier les lignes modifiées/ajoutées/supprimées et faire des UPDATE ciblés.  
**Choix retenu** : plus simple, moins de code, moins de bugs. Pour une facture de 5-20 lignes, la performance est négligeable.  
**Limite** : si une ligne avait un id en base et une autre entité y référençait, on perdrait la référence. Ici `invoice_line` n'est jamais référencée par ailleurs → le choix est correct.

### 4.7 Modèle `settings` avec `CHECK (id = 1)`

```sql
CREATE TABLE settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  ...
);
INSERT OR IGNORE INTO settings (id) VALUES (1);
```

**Pourquoi** : les paramètres du garage sont uniques (une seule ligne). La contrainte `CHECK (id = 1)` rend cette unicité explicite dans le schéma — impossible d'insérer un `id = 2` par erreur.  
**Alternative** : `UNIQUE` sur un champ clé textuel, ou une table `key/value`. Le singleton explicite est plus lisible ici.

---

## 5. Concepts clés à retenir

### 5.1 Encapsulation

**Définition** : regrouper données et méthodes qui les manipulent dans une même classe, et masquer les détails d'implémentation.

**Exemple dans le code** : `BackupManager._rotate_backups()` est une méthode privée (convention `_`). L'appelant (`create_backup`) n'a pas à savoir comment la rotation fonctionne.

```python
class BackupManager:
    def create_backup(self, source_conn, target_dir) -> BackupResult:
        # ... logique principale ...
        self._rotate_backups(target_dir)  # ← détail interne, pas exposé
        return BackupResult(...)

    def _rotate_backups(self, target_dir: Path) -> None:
        # détail d'implémentation : qui l'appelle n'a pas à comprendre le tri
        backups = sorted(target_dir.glob(...), key=lambda p: p.stat().st_mtime)
        for old in backups[self.keep_last:]:
            old.unlink()
```

### 5.2 Composition vs Héritage

Le projet n'utilise **pas d'héritage** entre ses classes métier. Il utilise la **composition** : une classe possède une instance d'une autre.

```
# Composition (utilisée ici) :
BackupScheduler
  └── backup_manager: BackupManager   ← "a un" BackupManager

# Héritage (non utilisé ici) :
class BackupScheduler(BackupManager): ← "est un" BackupManager — incorrect
```

> **Règle "favour composition over inheritance"** (Effective Java, Gamma et al.) : l'héritage crée un couplage fort entre les classes parent et enfant. La composition est plus flexible — on peut remplacer `BackupManager` par une autre implémentation sans toucher à `BackupScheduler`.

**Héritage effectivement utilisé** : uniquement pour hériter des classes Qt (`QMainWindow`, `QWidget`, `QObject`). C'est l'usage normal des frameworks GUI — on spécialise un composant existant.

### 5.3 Séparation des responsabilités (SRP)

| Classe/Module | Responsabilité unique |
|---|---|
| `money.py` | Convertir des textes en centimes et vice-versa |
| `invoice_calc.py` | Calculer les totaux d'une liste de lignes |
| `InvoiceRepository` | Lire/écrire les factures en base |
| `BackupManager` | Créer une copie physique de la DB |
| `BackupScheduler` | Décider quand déclencher une sauvegarde |
| `render_invoice_pdf()` | Générer un fichier PDF |
| `paths.py` | Résoudre les chemins selon le contexte (dev/exe) |

> **Signe que le SRP est respecté** : si on me demande "pourquoi modifier ce fichier ?", la réponse tient en une seule phrase.

### 5.4 Objets valeur immuables (Value Objects)

`InvoiceHeader`, `InvoiceLine`, `BackupResult`, `PdfResult` sont tous des `@dataclass(frozen=True)`.

```python
@dataclass(frozen=True)
class BackupResult:
    backup_path: Path
    created_at_iso: str
# On ne peut pas faire: result.backup_path = Path("/autre") → FrozenInstanceError
```

> **Avantage** : ces objets représentent un état à un instant T. Les passer par valeur plutôt que par référence mutable évite les effets de bord (deux parties du code qui modifient le même objet).

### 5.5 Signals/Slots Qt — Observateur sans couplage

```python
# Dans InvoiceEditorWidget (émetteur) :
tab_title_changed = Signal(str)
invoice_persisted = Signal(int)

# Dans MainWindow (abonné) :
editor.tab_title_changed.connect(
    lambda title, ed=editor: self._set_tab_title_safe(self.tabs.indexOf(ed), title)
)
editor.invoice_persisted.connect(
    lambda _id, ed=editor: self._refresh_editor_title(...)
)
```

> **Pattern Observer** : `InvoiceEditorWidget` ne connaît pas `MainWindow`. Il dit juste "j'ai été sauvegardé" (`invoice_persisted.emit(id)`). Qui écoute, il s'en fiche. C'est exactement le pattern Observateur (Observer) des Design Patterns du "Gang of Four".

### 5.6 Programmation défensive

```python
def _t(v) -> str:
    """Force une valeur en texte — protège ReportLab contre les types inattendus."""
    if v is None:
        return ""
    if isinstance(v, set):  # quelqu'un a mis {"texte"} au lieu de "texte"
        if len(v) == 1:
            return str(next(iter(v)))
        return " ".join(str(x) for x in v)
    return str(v)
```

> Cette fonction dans `render_invoice.py` protège contre des données corrompues ou inattendues qui feraient planter ReportLab avec un message d'erreur incompréhensible.

---

## 6. Points faibles et améliorations production

| N° | Problème | Localisation | Amélioration |
|---|---|---|---|
| 1 | TVA hardcodée à 20% | `invoice_calc.py`, `invoice_editor.py` | Paramètre configurable dans Settings |
| 2 | Code mort dans `finalize()` | `invoice_repo.py:312` | `auto_generated` est toujours `False` — supprimer le `if` |
| 3 | Ligne unreachable | `backup_scheduler.py:74` | `return False` à la ligne 72 rend la ligne 74 inaccessible |
| 4 | `cancel()` inexistant | `invoice_list.py` appelle `self.repo.cancel()` qui n'existe pas dans `InvoiceRepository` |
| 5 | Fichiers vides | `models.py` (1 ligne vide), `logging.py`, `invoice_tempalte.py` (typo) | Supprimer ou implémenter |
| 6 | Aucun test | Tout le projet | Ajouter `pytest` + tests sur `money.py`, `invoice_calc.py`, `InvoiceRepository` avec `":memory:"` |
| 7 | Pas de validation des champs | `invoice_editor.py` | Valider email (regex), téléphone (format), SIRET (14 chiffres) |
| 8 | Client sans entité propre | Données client dupliquées dans chaque facture | Créer une table `customer` + FK (clients réguliers) |
| 9 | `os.startfile()` Windows only | `invoice_editor.py:484` | Utiliser `subprocess.run(["xdg-open", path])` sur Linux/Mac |
| 10 | PDF : une seule page | `render_invoice.py` | Gérer la pagination pour les factures avec beaucoup de lignes |

---

## 7. Correspondances Django + React

Le projet Python POO est une bonne base pour comprendre l'architecture d'une application web. Voici comment chaque pièce se traduit.

### 7.1 Modèles Django ↔ Schéma SQLite + Dataclasses

| Python (local) | Django (web) |
|---|---|
| `schema.sql` table `invoice` | `class Invoice(models.Model)` |
| `schema.sql` table `invoice_line` | `class InvoiceLine(models.Model)` avec `ForeignKey(Invoice, on_delete=CASCADE)` |
| `schema.sql` table `settings` | `class GarageSettings(models.Model)` avec `Meta: unique_together` ou singleton |
| `schema.sql` table `counter` | Remplacé par auto-increment Django ou `F('value') + 1` |
| `@dataclass(frozen=True) InvoiceHeader` | Le modèle Django lui-même + méthodes `@property` |
| `@dataclass(frozen=True) InvoiceLine` | `InvoiceLine` Django |

```python
# Django — équivalent de invoice + invoice_line
class Invoice(models.Model):
    number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    date = models.DateField()
    customer_name = models.CharField(max_length=200, default='')
    customer_address = models.TextField(default='')
    customer_postal_code = models.CharField(max_length=10, default='')
    customer_email = models.EmailField(default='')    # validation intégrée
    customer_phone = models.CharField(max_length=20, default='')
    subtotal_cents = models.IntegerField(default=0)
    vat_rate = models.IntegerField(default=20)
    vat_cents = models.IntegerField(default=0)
    total_cents = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-id']

class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='lines')
    position = models.IntegerField()
    reference = models.CharField(max_length=100, default='')
    qty = models.IntegerField(default=0)
    description = models.TextField(default='')
    unit_price_cents = models.IntegerField(default=0)
    line_total_cents = models.IntegerField(default=0)

    class Meta:
        unique_together = [('invoice', 'position')]
        ordering = ['position']
```

### 7.2 Repositories ↔ Serializers DRF + ViewSets

| Python (local) | Django REST Framework (web) |
|---|---|
| `InvoiceRepository.list_invoices()` | `InvoiceViewSet.list()` → `InvoiceListSerializer` |
| `InvoiceRepository.get_header()` | `InvoiceViewSet.retrieve()` → `InvoiceDetailSerializer` |
| `InvoiceRepository.save_invoice()` | `InvoiceViewSet.update()` + `InvoiceWriteSerializer` |
| `InvoiceRepository.create_draft()` | `InvoiceViewSet.create()` |
| `InvoiceRepository.delete()` | `InvoiceViewSet.destroy()` |
| `SettingsRepository.get()` / `update()` | `GarageSettingsView` (APIView singleton) |

```python
# DRF — équivalent de InvoiceRepository.list_invoices()
class InvoiceListSerializer(serializers.ModelSerializer):
    total_ttc = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ['id', 'number', 'date', 'customer_name', 'total_cents']

    def get_total_ttc(self, obj):
        # centimes → euros formatés
        return f"{obj.total_cents / 100:.2f} €"
```

### 7.3 Logique domaine ↔ Services Django

| Python (local) | Django (web) |
|---|---|
| `calc_totals()` dans `invoice_calc.py` | `service_invoice.py` → `def calculate_totals(lines)` |
| `euros_to_cents()` dans `money.py` | Validateur DRF custom ou méthode utilitaire |
| `render_invoice_pdf()` | Tâche Celery `generate_invoice_pdf.delay(invoice_id)` |
| `BackupScheduler` + `BackupManager` | Tâche Celery Beat planifiée (`crontab`) |

> **Pourquoi Celery pour le PDF** : en web, générer un PDF prend du temps. On ne veut pas bloquer la réponse HTTP. On envoie la tâche en arrière-plan et on notifie l'utilisateur via WebSocket ou polling.

### 7.4 Widgets UI ↔ Composants React

| Python (PySide6) | React (web) |
|---|---|
| `InvoiceListWidget` | `<InvoiceList />` avec `useEffect` + fetch API |
| `InvoiceEditorWidget` | `<InvoiceEditor />` avec `useState` pour les lignes |
| `QTableWidget` lignes de facture | `<InvoiceLinesTable />` avec rows éditables |
| `Signal tab_title_changed` | Props + callback parent `onTitleChange` |
| `Signal invoice_persisted` | `onSave` callback ou état global (Redux/Zustand) |
| `QMessageBox.information()` | Toast notification (ex: `react-hot-toast`) |
| `MainWindow` + onglets | React Router + layout avec `<Outlet>` |

```jsx
// React — équivalent de InvoiceEditorWidget
function InvoiceEditor({ invoiceId, onSave }) {
  const [lines, setLines] = useState([]);
  const [totals, setTotals] = useState({ subtotal: 0, vat: 0, total: 0 });

  // Équivalent de _recalc_totals() appelé à chaque changement de table
  useEffect(() => {
    const subtotal = lines.reduce((acc, l) => acc + l.qty * l.unitPrice, 0);
    const vat = Math.floor(subtotal * 20 / 100);
    setTotals({ subtotal, vat, total: subtotal + vat });
  }, [lines]);

  // Équivalent de save_invoice() dans le repo
  const handleSave = async () => {
    await fetch(`/api/invoices/${invoiceId}/`, {
      method: 'PATCH',
      body: JSON.stringify({ lines, ...totals }),
    });
    onSave(invoiceId);  // signal vers le parent (=== invoice_persisted.emit())
  };

  return (
    <form>
      <InvoiceLinesTable lines={lines} onChange={setLines} />
      <TotalsDisplay totals={totals} />
      <button onClick={handleSave}>Enregistrer</button>
    </form>
  );
}
```

### 7.5 Tableau récapitulatif global

| Couche | Python POO (local) | Django + React (web) |
|---|---|---|
| Persistance | SQLite + schema.sql | PostgreSQL + Django ORM |
| Migrations | `_migrate()` manuel | `python manage.py migrate` |
| Accès données | Repository (SQL brut) | ORM Django / QuerySet |
| Sérialisation | Dataclasses `frozen=True` | Serializers DRF |
| API | N/A (local) | ViewSets DRF + URLs |
| Logique métier | Fonctions pures dans `domain/` | Services dans `services/` |
| Interface | Widgets PySide6 | Composants React |
| Événements | Signaux Qt | Callbacks / hooks React |
| Tâches asynchrones | QTimer + thread principal | Celery + Redis |
| Export PDF | ReportLab synchrone | Celery task + stockage S3 |
| Auth | N/A (app locale) | JWT / Session Django |
| Tests | Absents | pytest-django + Jest |

---

## 8. Questions / réponses entretien

---

### Q1. Qu'est-ce que le pattern Repository et pourquoi l'avez-vous utilisé ?

**Réponse** :

Le Repository est un pattern qui isole la logique d'accès aux données du reste de l'application. Dans mon projet, `InvoiceRepository` contient toutes les requêtes SQL liées aux factures. Ni les widgets UI ni la logique domaine ne savent qu'il y a du SQL derrière.

L'avantage principal est la **maintenabilité** : si demain je migre de SQLite vers PostgreSQL, je ne modifie que le repository. Les widgets et les calculs restent intacts. C'est aussi plus testable : je peux instancier `InvoiceRepository` avec une base en mémoire (`sqlite3.connect(":memory:")`) pour tester les requêtes sans interface graphique.

---

### Q2. Pourquoi stocker les montants en centimes plutôt qu'en float ?

**Réponse** :

Les nombres flottants (float) sont représentés en binaire selon la norme IEEE 754. Certaines fractions décimales comme 0.1 n'ont pas de représentation binaire exacte. Résultat : `0.1 + 0.2` donne `0.30000000000000004` en Python, pas `0.3`. Dans un contexte financier, cette imprécision est inacceptable.

En stockant les montants en centimes (entiers), toutes les opérations sont exactes. `10 + 20 = 30` centimes, sans aucune approximation. C'est la pratique universelle dans les systèmes financiers — les banques, les processeurs de paiement (Stripe, PayPal) stockent tous leurs montants en unités entières (centimes, centavos...).

---

### Q3. Expliquez la différence entre composition et héritage. Comment avez-vous appliqué ce choix ?

**Réponse** :

L'héritage (`class B(A)`) crée une relation "B est un A". La composition (B possède une instance de A) crée une relation "B a un A". La règle générale est de préférer la composition quand on veut réutiliser un comportement sans créer une hiérarchie rigide.

Dans mon projet, `BackupScheduler` *a un* `BackupManager`, il ne *est pas* un `BackupManager`. `BackupScheduler` gère le *quand* (timer, dirty flag), `BackupManager` gère le *comment* (copie SQLite, rotation). Si demain je veux changer la stratégie de backup (copier sur un NAS plutôt que OneDrive), je remplace `BackupManager` par une autre classe compatible sans toucher à `BackupScheduler`.

L'héritage est utilisé uniquement pour les widgets Qt (`QWidget`, `QMainWindow`) car c'est la façon normale d'utiliser un framework GUI : on spécialise un composant existant.

---

### Q4. Qu'est-ce que `@dataclass(frozen=True)` et pourquoi l'utiliser ?

**Réponse** :

`@dataclass` est un décorateur Python qui génère automatiquement `__init__`, `__repr__`, `__eq__` à partir des annotations de type. `frozen=True` ajoute une protection contre la modification : toute tentative d'écrire un attribut après la création lève une `FrozenInstanceError`.

Dans mon projet, `InvoiceHeader`, `InvoiceLine` et `BackupResult` sont tous `frozen`. Ces objets représentent des données lues depuis la base à un instant T. Les rendre immuables signifie qu'aucune partie du code ne peut modifier silencieusement ces données après les avoir reçues. C'est ce qu'on appelle un "Value Object" en Domain-Driven Design : un objet qui a une valeur fixe et pas d'identité propre en mémoire.

---

### Q5. Comment fonctionne l'injection de dépendances dans votre projet ?

**Réponse** :

L'injection de dépendances consiste à ne pas laisser un objet créer lui-même ses dépendances, mais à les lui fournir de l'extérieur. Dans mon projet, `MainWindow` crée la connexion SQLite une seule fois et l'injecte dans tous les repositories :

```python
conn = connect(db_path)
invoice_repo = InvoiceRepository(conn)   # conn injecté
settings_repo = SettingsRepository(conn) # même conn
backup = BackupScheduler(conn=conn, settings_repo=settings_repo, ...)
```

L'avantage est double : tous les repos partagent la même connexion (cohérence des transactions) et chaque classe peut être testée indépendamment en lui fournissant une fausse implémentation ou une DB de test.

---

### Q6. Pourquoi utiliser les signaux Qt plutôt que des callbacks directs ?

**Réponse** :

Un callback direct crée un couplage fort : `InvoiceEditorWidget` devrait avoir une référence à `MainWindow` pour appeler `mainwindow.update_tab_title()`. Ça veut dire que l'éditeur ne peut exister que dans une `MainWindow` — impossible de le réutiliser dans un autre contexte.

Avec les signaux Qt, `InvoiceEditorWidget` émet juste `tab_title_changed.emit("Facture - 001")`. Il ignore complètement qui l'écoute. `MainWindow` branche sa fonction de réponse au signal. C'est le **pattern Observateur** : l'émetteur et le récepteur sont découplés.

C'est exactement le principe des événements en JavaScript (`addEventListener`) ou des callbacks en React (`onChange`, `onSave`) — même idée, syntaxe différente.

---

### Q7. Que se passe-t-il lors du premier lancement de l'application sur un PC neuf ? Et lors d'une mise à jour ?

**Réponse** :

**Premier lancement** : `main()` appelle `connect(db_path)` qui crée le fichier `app.db` s'il n'existe pas (`mkdir(parents=True, exist_ok=True)`). Puis `init_schema(conn)` exécute le `schema.sql` avec `CREATE TABLE IF NOT EXISTS` — les tables sont créées. La table `settings` reçoit sa ligne singleton (`INSERT OR IGNORE INTO settings (id) VALUES (1)`). La table `counter` est initialisée à 1.

**Mise à jour** : le `schema.sql` ne change pas les tables existantes (tout est `CREATE TABLE IF NOT EXISTS`). C'est `_migrate(conn)` qui détecte les colonnes manquantes et les ajoute avec `ALTER TABLE ADD COLUMN`. L'utilisateur conserve toutes ses données, les nouvelles colonnes reçoivent des valeurs par défaut vides.

---

### Q8. Comment garantissez-vous la cohérence des données lors d'une sauvegarde pendant qu'une facture est en cours d'édition ?

**Réponse** :

La sauvegarde utilise l'API `sqlite3.Connection.backup()` qui effectue une copie **atomique** de la base. C'est l'équivalent d'un snapshot : la copie reflète l'état de la base à un instant T précis, sans transaction partielle. Même si une facture est en train d'être écrite pendant la copie, le backup ne verra que l'état avant ou après l'écriture, jamais un état intermédiaire.

De plus, le **dirty flag** assure que la sauvegarde ne se déclenche qu'après un `conn.commit()` — donc uniquement quand une opération complète a été validée. Un brouillon non enregistré ne déclenche pas de backup.

---

### Q9. Quelles sont les limites de ce projet et comment l'amélioreriez-vous en version production ?

**Réponse** :

**Limites identifiées** :

1. **TVA hardcodée** à 20% — il faudrait un champ configurable dans les paramètres, car les taux changent (rénovation, alimentaire à 5,5%, etc.)
2. **Aucun test automatisé** — c'est le point le plus risqué. Une régression peut passer inaperçue.
3. **Client sans entité propre** — les coordonnées client sont répétées dans chaque facture. Un client régulier devrait avoir sa propre table avec autocomplete.
4. **Code mort** : la méthode `finalize()` contient une branche `if auto_generated:` qui ne sera jamais exécutée (variable toujours `False`).
5. **PDF mono-page** — une facture avec 30 lignes déborde de la page sans gestion de la pagination.

**Améliorations production** :

- Ajouter `pytest` avec tests unitaires sur `money.py` et `invoice_calc.py` (logique pure, facile à tester)
- Tests d'intégration des repositories avec `sqlite3.connect(":memory:")`
- Table `customer` avec `ForeignKey` optionnelle depuis `invoice`
- Taux de TVA configurable
- Pagination PDF (ReportLab supporte `showPage()` pour les pages multiples)
- Validation des champs (SIRET = 14 chiffres, email regex)

---

### Q10. Comment le projet gère-t-il le déploiement ? Quelles difficultés cela pose-t-il ?

**Réponse** :

Le projet est empaqueté avec **PyInstaller** en `.exe` autonome. PyInstaller analyse les imports et bundle Python + toutes les dépendances (PySide6, ReportLab…) dans un dossier `dist/`. L'utilisateur n'a pas besoin d'installer Python.

La principale difficulté est la **résolution des chemins**. En développement, les fichiers de ressources (logo, schema.sql) sont dans le repo Git. Dans l'exe, PyInstaller extrait les ressources dans un dossier temporaire `sys._MEIPASS`. Le module `paths.py` centralise cette logique :

```python
def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
```

Un second problème : l'exe ne peut pas écrire dans son propre répertoire d'installation (droits Windows). La base de données et les exports PDF sont donc stockés dans `%APPDATA%/HA_Facturation/` — un dossier inscriptible par l'utilisateur, géré par `paths.py`.

---

## 9. Ce que je retiens de ce projet

Ce projet de facturation, je l'ai construit pour un usage réel — un gérant de garage qui avait besoin d'une solution simple, sans serveur, qui tourne sur son PC Windows. Cette contrainte concrète a guidé toutes mes décisions techniques.

**Ce que j'ai appris sur la POO**, c'est que les principes comme la séparation des responsabilités ou l'injection de dépendances ne sont pas des règles abstraites : ils m'ont évité des bugs réels. Quand j'ai dû gérer la compatibilité avec des anciennes bases de données, avoir un `Repository` séparé de l'UI m'a permis de centraliser la migration en un seul endroit plutôt que de disperser des `ALTER TABLE` partout dans les widgets.

**Sur l'architecture en couches**, j'ai compris la différence entre ce qui appartient au *domaine* (calculer une TVA, convertir en centimes) et ce qui appartient à l'*infrastructure* (écrire dans une base, générer un PDF, scheduler un timer). Les fonctions de `domain/` ne dépendent de rien d'externe — elles sont testables en une ligne. C'est cette indépendance que les architectures web cherchent aussi à atteindre, avec les services Django par exemple.

**Sur les choix techniques**, j'ai appris à justifier mes décisions. Stocker les montants en centimes n'est pas une astuce : c'est une convention du secteur financier que j'ai retrouvée dans les docs Stripe et PayPal. Utiliser `@dataclass(frozen=True)` n'est pas du style pour le style : c'est un contrat explicite qui dit "cet objet ne change pas après sa création". Chaque fois que je pouvais expliquer *pourquoi* un choix et pas seulement *quoi*, je savais que j'avais compris le concept.

**Ce que j'améliorerais aujourd'hui** : l'absence de tests automatisés est ma principale dette technique. La logique dans `money.py` et `invoice_calc.py` est parfaitement isolée — je pourrais écrire des tests en trente minutes. Et pourtant je ne l'ai pas fait. En production, cette absence de filet de sécurité signifie qu'une régression peut passer inaperçue. C'est la leçon que je retiens le plus clairement.

**La correspondance avec le web** m'a été utile pour contextualiser le projet. Les `Repository` deviennent des `ViewSet` DRF, les `dataclass frozen` deviennent des modèles Django, les `Signal Qt` deviennent des props et callbacks React. Les concepts voyagent d'un paradigme à l'autre, seule la syntaxe change. C'est ce qui me donne confiance pour aborder un projet full stack : je comprends les principes derrière les frameworks, pas seulement les incantations.

En entretien, si on me demande "ton projet c'est quoi concrètement ?", je réponds : c'est une application qui aide un artisan à facturer ses clients, qui fonctionne sans internet, qui sauvegarde ses données automatiquement, et dont chaque module a une responsabilité claire. C'est simple à expliquer parce que l'architecture le permet.
