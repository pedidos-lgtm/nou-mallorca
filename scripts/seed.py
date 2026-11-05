"""Solo datos ficticios; genera la contraseña, nunca contiene una contraseña fija."""
import sys, secrets, os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.db import *
from app.security import password_hash
from app.engine import seed_catalog,generate

def seed():
    migrate()
    with connect() as c:
        seed_catalog(c)
        if one(c,'SELECT id FROM users LIMIT 1'):
            print('La base ya contiene usuarios. No se han modificado datos.');return
        password=secrets.token_urlsafe(18)
        u=insert(c,'users',id=uid(),email='admin@example.test',name='Administración · DEMO',password=password_hash(password),admin=1)
        for n,(name,municipality,hp) in enumerate([('Vivienda demo A','Municipio de prueba',1),('Reforma demo B','Municipio de prueba',0)]):
            pid=uid();insert(c,'projects',id=pid,name=name,code=f'DEMO-{n+1:03}',municipality=municipality,has_project=hp,details=js({'description':'Expediente ficticio para pruebas. No corresponde a una obra real.','nm_role':'contratista'}),created_at=now())
            cid=uid();insert(c,'companies',id=cid,name=f'Colaboradora ficticia {n+1}',kind='con_trabajadores')
            insert(c,'participations',id=uid(),project_id=pid,company_id=cid,role='subcontrata',activity='Actividad de prueba')
            generate(c,pid)
        print('Datos ficticios creados. Acceso local: admin@example.test')
        print('Contraseña generada (guardar en gestor seguro): '+password)
if __name__=='__main__': seed()
