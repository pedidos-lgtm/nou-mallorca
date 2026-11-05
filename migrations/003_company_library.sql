CREATE TABLE IF NOT EXISTS company_library (
 id TEXT PRIMARY KEY,
 company_id TEXT NOT NULL REFERENCES companies(id),
 source_version_id TEXT NOT NULL UNIQUE REFERENCES versions(id),
 category TEXT NOT NULL REFERENCES categories(id),
 title TEXT NOT NULL,
 rule_id TEXT REFERENCES rule_templates(id),
 reason TEXT NOT NULL,
 published_by TEXT NOT NULL REFERENCES users(id),
 published_at TEXT NOT NULL,
 revoked_at TEXT,
 revoked_by TEXT REFERENCES users(id),
 revoke_reason TEXT
);
CREATE TABLE IF NOT EXISTS document_reuse (
 id TEXT PRIMARY KEY,
 library_id TEXT NOT NULL REFERENCES company_library(id),
 target_document_id TEXT NOT NULL UNIQUE REFERENCES documents(id),
 target_version_id TEXT NOT NULL UNIQUE REFERENCES versions(id),
 requirement_id TEXT REFERENCES requirements(id),
 applied_by TEXT NOT NULL REFERENCES users(id),
 applied_at TEXT NOT NULL,
 reason TEXT NOT NULL,
 UNIQUE(library_id,target_document_id)
);
CREATE INDEX IF NOT EXISTS library_company ON company_library(company_id,category);
