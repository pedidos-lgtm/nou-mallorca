CREATE TABLE IF NOT EXISTS supplier_private (
 company_id TEXT PRIMARY KEY REFERENCES companies(id),
 tax_id TEXT NOT NULL DEFAULT '',
 payment TEXT NOT NULL DEFAULT '',
 notes TEXT NOT NULL DEFAULT '',
 source_hash TEXT NOT NULL,
 source_row INTEGER NOT NULL,
 created_by TEXT NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS imported_suppliers (
 id TEXT PRIMARY KEY,
 authorization_id TEXT NOT NULL REFERENCES import_authorizations(id),
 company_id TEXT NOT NULL REFERENCES companies(id),
 fingerprint TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL
);
