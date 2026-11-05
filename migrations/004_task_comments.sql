CREATE TABLE IF NOT EXISTS task_comments (
 id TEXT PRIMARY KEY,
 task_id TEXT NOT NULL REFERENCES tasks(id),
 user_id TEXT NOT NULL REFERENCES users(id),
 body TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS task_comments_task ON task_comments(task_id,created_at);
