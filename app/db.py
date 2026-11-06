import os, sqlite3, uuid, json
from pathlib import Path
from datetime import datetime, timezone, timedelta
ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.getenv('DATA_DIR', str(ROOT / '.data'))).resolve()
DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
FILES = DATA / 'private'
FILES.mkdir(exist_ok=True, mode=0o700)
def now(): return datetime.now(timezone.utc).isoformat()
def after(days=7): return (datetime.now(timezone.utc)+timedelta(days=days)).isoformat()
def uid(): return str(uuid.uuid4())
def js(v): return json.dumps(v, ensure_ascii=False)
def connect():
    c = sqlite3.connect(DATA/'nm.sqlite3', timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA journal_mode=WAL')
    return c

def migrate():
    with connect() as c:
        c.executescript((ROOT/'migrations/001_initial.sql').read_text())
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(1,?)',(now(),))
        if not one(c,'SELECT version FROM schema_migrations WHERE version=2'):
            if 'category' not in [r[1] for r in c.execute('PRAGMA table_info(alerts)')]:
                c.executescript((ROOT/'migrations/002_alert_categories.sql').read_text())
            c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(2,?)',(now(),))
        c.executescript((ROOT/'migrations/003_company_library.sql').read_text())
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(3,?)',(now(),))
        c.executescript((ROOT/'migrations/004_task_comments.sql').read_text())
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(4,?)',(now(),))
        c.executescript((ROOT/'migrations/005_private_imports.sql').read_text())
        c.execute('INSERT OR IGNORE INTO schema_migrations VALUES(5,?)',(now(),))

def rows(c,sql,args=()): return [dict(r) for r in c.execute(sql,args).fetchall()]
def one(c,sql,args=()):
    r=c.execute(sql,args).fetchone()
    return dict(r) if r else None

def insert(c,table,**values):
    c.execute(f'INSERT INTO {table} ({",".join(values)}) VALUES ({",".join("?" for _ in values)})',tuple(values.values()))
    return values

def audit(c,u,p,action,entity=None,details=None,company=None):
    insert(c,'audit',id=uid(),user_id=u,project_id=p,company_id=company,action=action,entity_id=entity,details=js(details or {}),created_at=now())
