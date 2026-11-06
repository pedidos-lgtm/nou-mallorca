"""Restaura en una carpeta nueva y vacía; no sobrescribe una instalación activa."""
import os,sys,io,json,tarfile,hashlib,sqlite3
from pathlib import Path
from cryptography.fernet import Fernet

def restore(archive,destination):
    dest=Path(destination).resolve()
    if dest.exists() and any(dest.iterdir()): raise ValueError('El destino debe estar vacío; no se sobrescriben datos.')
    if not os.getenv('BACKUP_KEY'): raise ValueError('Falta BACKUP_KEY.')
    content=Fernet(os.environ['BACKUP_KEY'].encode()).decrypt(Path(archive).read_bytes())
    with tarfile.open(fileobj=io.BytesIO(content),mode='r:gz') as tar:
        manifest=json.load(tar.extractfile('manifest.json')); verified={}
        for name,h in manifest.items():
            if name!='nm.sqlite3' and not (name.startswith('private/') and len(Path(name).parts)==2): raise ValueError('Ruta de archivo no válida.')
            if '..' in Path(name).parts or Path(name).is_absolute(): raise ValueError('Ruta de archivo no válida.')
            member=tar.getmember(name)
            if not member.isfile(): raise ValueError('Tipo de archivo no válido.')
            data=tar.extractfile(member).read()
            if hashlib.sha256(data).hexdigest()!=h: raise ValueError('La verificación de integridad ha fallado.')
            verified[name]=data
        dest.mkdir(parents=True,exist_ok=True,mode=0o700)
        for name,data in verified.items():
            p=dest/name;p.parent.mkdir(parents=True,exist_ok=True,mode=0o700);p.write_bytes(data);p.chmod(0o600)
    with sqlite3.connect(dest/'nm.sqlite3') as c:
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('SQLite no ha superado la comprobación de integridad.')
        if c.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('Referencias inconsistentes.')
        # Revocation of all authentication/bearer tokens after restore prevents replay.
        c.execute('DELETE FROM sessions');c.execute('UPDATE invitations SET revoked=1');c.execute('UPDATE signers SET revoked=1')
        if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='import_authorizations'").fetchone():
            c.execute("UPDATE import_authorizations SET revoked_at=COALESCE(revoked_at,datetime('now'))")
    return len(verified)
if __name__=='__main__':
    if len(sys.argv)!=3: raise SystemExit('Uso: python scripts/restore.py copia.nmbackup /destino/nuevo')
    print('Archivos restaurados y verificados:',restore(*sys.argv[1:]))
