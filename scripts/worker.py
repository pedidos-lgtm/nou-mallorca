"""Ejecutar periódicamente con cron. No envía correos reales."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.db import migrate, connect
from app.main import run_alerts
if __name__=='__main__':
    migrate()
    with connect() as c: print(run_alerts(c))
