"""Alta inicial en ejecución: nunca imprime credenciales ni reinicializa usuarios."""
import os
from .db import one,insert,uid,audit
from .security import password_hash

def bootstrap_admin(c):
    if one(c,'SELECT id FROM users LIMIT 1'):
        return False
    email=os.getenv('BOOTSTRAP_ADMIN_EMAIL','').strip().lower()
    password=os.getenv('BOOTSTRAP_ADMIN_PASSWORD','')
    if not email and not password:
        if os.getenv('APP_ENV')=='production':
            raise RuntimeError('Base vacía: configura BOOTSTRAP_ADMIN_EMAIL y BOOTSTRAP_ADMIN_PASSWORD de forma segura.')
        return False
    if '@' not in email or len(email)>254 or len(password)<16 or len(password)>256:
        raise RuntimeError('La configuración del administrador inicial no es válida. Revisa las variables sin imprimirlas.')
    user_id=uid()
    insert(c,'users',id=user_id,email=email,name='Administración Nou Mallorca',password=password_hash(password),admin=1)
    audit(c,user_id,None,'administrador_inicial_creado',user_id)
    return True
