"""Inicializa un administrador sin datos ficticios ni contraseñas en argumentos."""
import sys, getpass
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.db import *
from app.engine import seed_catalog
from app.security import password_hash
if __name__=='__main__':
    migrate()
    email=input('Correo de administración: ').strip().lower()
    name=input('Nombre: ').strip()
    password=getpass.getpass('Contraseña (mínimo 12 caracteres): ')
    if '@' not in email or not name: raise SystemExit('Datos no válidos')
    with connect() as c:
        if one(c,'SELECT id FROM users WHERE email=?',(email,)): raise SystemExit('El usuario ya existe; no se ha modificado.')
        seed_catalog(c);insert(c,'users',id=uid(),email=email,name=name,password=password_hash(password),admin=1)
    print('Administrador creado. No se han añadido obras o empresas.')
