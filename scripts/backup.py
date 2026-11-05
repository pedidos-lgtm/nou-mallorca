"""Copia coherente de SQLite + documentos, cifrada con Fernet.
BACKUP_KEY debe contener una clave Fernet de 32 bytes codificada en base64 URL.
La clave se suministra fuera del repositorio; no se imprime ni se copia al backup.
"""
import os,sys,io,json,hashlib,tarfile,tempfile,sqlite3
from pathlib import Path
from datetime import datetime,timezone
from cryptography.fernet import Fernet
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.db import connect,FILES,DATA

def backup(destination):
    if not os.getenv('BACKUP_KEY'): raise ValueError('Configura BACKUP_KEY desde el gestor de secretos.')
    cipher=Fernet(os.environ['BACKUP_KEY'].encode())
    dest=Path(destination).resolve()
    if dest.exists(): raise ValueError('El destino ya existe; usa un nombre nuevo.')
    with tempfile.TemporaryDirectory() as temp:
        snapshot=Path(temp)/'nm.sqlite3'
        with connect() as lock:
            lock.execute('BEGIN IMMEDIATE')
            with connect() as source,sqlite3.connect(snapshot) as target: source.backup(target)
            buff=io.BytesIO();manifest={}
            with tarfile.open(fileobj=buff,mode='w:gz') as tar:
                files=[(snapshot,'nm.sqlite3')]+[(p,'private/'+p.name) for p in FILES.iterdir() if p.is_file()]
                for p,name in files:
                    manifest[name]=hashlib.sha256(p.read_bytes()).hexdigest();tar.add(p,arcname=name)
                m=json.dumps(manifest).encode();info=tarfile.TarInfo('manifest.json');info.size=len(m);tar.addfile(info,io.BytesIO(m))
            dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            dest.write_bytes(cipher.encrypt(buff.getvalue()));dest.chmod(0o600)
    return len(manifest)
if __name__=='__main__':
    if len(sys.argv)!=2: raise SystemExit('Uso: python scripts/backup.py /ruta/nueva-copia.nmbackup')
    count=backup(sys.argv[1]);print(f'Copia cifrada creada. {count} archivos. La clave no está incluida.')
