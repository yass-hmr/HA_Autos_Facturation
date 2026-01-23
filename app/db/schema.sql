PRAGMA foreign_keys = ON;

-- =========================
-- SETTINGS
-- =========================
CREATE TABLE IF NOT EXISTS settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  garage_name TEXT NOT NULL DEFAULT '',
  garage_address TEXT NOT NULL DEFAULT '',
  garage_postal_code TEXT NOT NULL DEFAULT '',
  garage_phone TEXT NOT NULL DEFAULT '',
  garage_siret TEXT NOT NULL DEFAULT '',
  onedrive_backup_dir TEXT NOT NULL DEFAULT '',
  last_backup_at TEXT DEFAULT NULL
);

INSERT OR IGNORE INTO settings (id) VALUES (1);

-- =========================
-- COUNTER (numérotation)
-- =========================
CREATE TABLE IF NOT EXISTS counter (
  key TEXT PRIMARY KEY,
  value INTEGER NOT NULL
);

INSERT OR IGNORE INTO counter (key, value) VALUES ('invoice_number', 1);

-- =========================
-- INVOICE
-- =========================
CREATE TABLE IF NOT EXISTS invoice (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  number TEXT UNIQUE,
  date TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('DRAFT', 'FINAL', 'CANCELED', 'PAID')) DEFAULT 'DRAFT',
  customer_name TEXT NOT NULL DEFAULT '',
  customer_address TEXT NOT NULL DEFAULT '',
  customer_postal_code TEXT NOT NULL DEFAULT '',
  subtotal_cents INTEGER NOT NULL DEFAULT 0,
  vat_rate INTEGER NOT NULL DEFAULT 20,
  vat_cents INTEGER NOT NULL DEFAULT 0,
  total_cents INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_invoice_date ON invoice(date);
CREATE INDEX IF NOT EXISTS idx_invoice_status ON invoice(status);

-- =========================
-- INVOICE LINE
-- =========================
CREATE TABLE IF NOT EXISTS invoice_line (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL,
  position INTEGER NOT NULL,
  qty INTEGER NOT NULL CHECK (qty >= 0),
  description TEXT NOT NULL DEFAULT '',
  unit_price_cents INTEGER NOT NULL DEFAULT 0 CHECK (unit_price_cents >= 0),
  line_total_cents INTEGER NOT NULL DEFAULT 0 CHECK (line_total_cents >= 0),
  FOREIGN KEY (invoice_id) REFERENCES invoice(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_invoice_line_invoice_id ON invoice_line(invoice_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_invoice_line_position ON invoice_line(invoice_id, position);

-- =========================
-- PDF EXPORTS (métadonnées)
-- =========================
CREATE TABLE IF NOT EXISTS pdf_export (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id INTEGER NOT NULL,
  filename TEXT NOT NULL,
  rel_path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'INVOICE',
  FOREIGN KEY (invoice_id) REFERENCES invoice(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pdf_export_invoice_id ON pdf_export(invoice_id);
CREATE INDEX IF NOT EXISTS idx_pdf_export_created_at ON pdf_export(created_at);

CREATE UNIQUE INDEX IF NOT EXISTS uq_pdf_export_invoice_filename
ON pdf_export(invoice_id, filename);
CREATE UNIQUE INDEX IF NOT EXISTS uq_pdf_export_invoice_rel_path
ON pdf_export(invoice_id, rel_path);