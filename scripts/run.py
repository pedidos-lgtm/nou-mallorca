"""Arranque local reproducible. No crea usuarios ni datos sin --demo explícito."""
import argparse,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))

def main():
    parser=argparse.ArgumentParser(description='Nou Mallorca · arranque local')
    parser.add_argument('--demo',action='store_true',help='Inicializar datos ficticios solo si no hay usuarios')
    parser.add_argument('--check',action='store_true',help='Comprobar migraciones y base de datos sin abrir un servidor')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv(ROOT/'.env',override=False)
    if args.demo and os.getenv('APP_ENV','development')=='production':
        parser.error('No se permite inicializar demostraciones en producción.')
    if not 1024<=args.port<=65535: parser.error('El puerto debe estar entre 1024 y 65535.')
    from app.db import migrate,connect,DATA
    migrate()
    if args.demo:
        from scripts.seed import seed
        seed()
    with connect() as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise SystemExit('Integridad de base de datos no válida.')
        if c.execute('PRAGMA foreign_key_check').fetchall(): raise SystemExit('Referencias de base de datos no válidas.')
        users=c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        migrations=[r[0] for r in c.execute('SELECT version FROM schema_migrations ORDER BY version')]
    print('Migraciones aplicadas:',', '.join(map(str,migrations)))
    print('Persistencia:',DATA)
    if not users:
        print('No hay usuarios. Ejecuta python scripts/admin.py o python scripts/run.py --demo para una prueba ficticia.')
        if not args.check: return 1
    if args.check:
        print('Comprobación local correcta. No se ha abierto ningún puerto.');return 0
    print(f'Aplicación local: http://127.0.0.1:{args.port}',flush=True)
    print('Firma y correo: PRUEBAS. Sin comunicaciones externas.',flush=True)
    import uvicorn
    uvicorn.run('app.main:app',host='127.0.0.1',port=args.port,workers=1,access_log=False)
    return 0
if __name__=='__main__': raise SystemExit(main())
