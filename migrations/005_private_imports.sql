CREATE TABLE IF NOT EXISTS import_authorizations (
 id TEXT PRIMARY KEY,
 token_hash TEXT UNIQUE NOT NULL,
 user_id TEXT NOT NULL REFERENCES users(id),
 project_id TEXT REFERENCES projects(id),
 company_id TEXT REFERENCES companies(id),
 expires TEXT NOT NULL,
 revoked_at TEXT,
 max_files INTEGER NOT NULL CHECK(max_files BETWEEN 1 AND 50),
 max_workers INTEGER NOT NULL DEFAULT 0 CHECK(max_workers BETWEEN 0 AND 500),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS company_archive_documents (
 id TEXT PRIMARY KEY,
 company_id TEXT NOT NULL REFERENCES companies(id),
 title TEXT NOT NULL,
 category TEXT NOT NULL REFERENCES categories(id),
 details TEXT NOT NULL DEFAULT '{}',
 created_by TEXT NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS company_archive_versions (
 id TEXT PRIMARY KEY,
 document_id TEXT NOT NULL REFERENCES company_archive_documents(id),
 number INTEGER NOT NULL DEFAULT 1,
 storage_key TEXT UNIQUE NOT NULL,
 filename TEXT NOT NULL,
 mime TEXT NOT NULL,
 hash TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'recibido',
 provenance TEXT NOT NULL,
 created_by TEXT NOT NULL REFERENCES users(id),
 created_at TEXT NOT NULL,
 UNIQUE(document_id,number)
);
CREATE TABLE IF NOT EXISTS imported_files (
 id TEXT PRIMARY KEY,
 authorization_id TEXT NOT NULL REFERENCES import_authorizations(id),
 scope TEXT NOT NULL CHECK(scope IN ('project','company')),
 project_id TEXT REFERENCES projects(id),
 company_id TEXT REFERENCES companies(id),
 raw_hash TEXT NOT NULL,
 document_id TEXT,
 version_id TEXT,
 created_at TEXT NOT NULL,
 UNIQUE(authorization_id,raw_hash)
);
CREATE INDEX IF NOT EXISTS imported_project_hash ON imported_files(project_id,raw_hash);
CREATE INDEX IF NOT EXISTS imported_company_hash ON imported_files(company_id,raw_hash);

CREATE TABLE IF NOT EXISTS imported_workers (
 id TEXT PRIMARY KEY,
 authorization_id TEXT NOT NULL REFERENCES import_authorizations(id),
 company_id TEXT NOT NULL REFERENCES companies(id),
 worker_id TEXT NOT NULL REFERENCES workers(id),
 fingerprint TEXT NOT NULL,
 created_at TEXT NOT NULL,
 UNIQUE(company_id,fingerprint)
);
