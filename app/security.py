import hashlib, secrets, hmac, json
from fastapi import HTTPException
from .db import one, rows, now
ACTIONS=['read','upload','review','validate','approve','sign','download','export','manage','health']
ROLES={
 'gestor':ACTIONS[:-1],
 'encargado':['read','download'],
 'direccion':['read','download','upload','review','approve','sign'],
 'prl':['read','download','review','validate','sign'],
 'empresa':['read','upload','download','sign'],
 'firmante':['read','download','sign'],
}
SAFE_CATEGORIES=['prl','proyecto','licencias','actas','calidad','final','fotografias','otros']
RESTRICTED=['salud','laboral','economico','bancario']
def fail(status,msg): raise HTTPException(status,msg)
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def password_hash(p):
    if len(p)<12: fail(422,'La contraseña debe tener al menos 12 caracteres.')
    salt=secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(p.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
def password_ok(p,stored):
    salt,expected=stored.split(':')
    actual=hashlib.scrypt(p.encode(),salt=salt.encode(),n=16384,r=8,p=1).hex()
    return hmac.compare_digest(expected,actual)
def user(c,request,mutation=False):
    token=request.cookies.get('nm_session','')
    s=one(c,'SELECT s.*,u.email,u.name,u.admin,u.disabled FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(digest(token),now()))
    if not s or s['disabled']: fail(401,'Inicia sesión para continuar.')
    if mutation and not hmac.compare_digest(request.headers.get('x-csrf-token',''),s['csrf']): fail(403,'La sesión no autoriza esta acción. Recarga la página.')
    s['id']=s['user_id']
    return s

def grants(c,u,p): return rows(c,'SELECT * FROM grants WHERE user_id=? AND project_id=?',(u['id'],p))
def allowed(c,u,p,action='read',company=None,category=None):
    if not one(c,'SELECT id FROM projects WHERE id=?',(p,)): return False
    if u['admin']: return True
    for g in grants(c,u,p):
        perms=json.loads(g['permissions']); cats=json.loads(g['categories'])
        if action not in perms: continue
        # Signer-only accounts never gain generic project/category access.
        if g['role']=='firmante' and action not in ['sign','download']: continue
        if g['company_id'] is not None and g['company_id'] != company: continue
        if category in RESTRICTED and (category not in cats or (category=='salud' and 'health' not in perms)): continue
        if category and category not in cats and '*' not in cats: continue
        return True
    return False

def require(c,u,p,action='read',company=None,category=None):
    if not allowed(c,u,p,action,company,category): fail(403,'No tienes permiso para este recurso o acción.')
def project_access(c,u,p):
    if not u['admin'] and not grants(c,u,p): fail(403,'Obra no autorizada.')
def normal_document_allowed(c,u,d,action='read'):
    if u['admin']: return True
    for g in grants(c,u,d['project_id']):
        if g['role']=='firmante' or action not in json.loads(g['permissions']): continue
        if g['company_id'] is not None and g['company_id']!=d['company_id']: continue
        cats=json.loads(g['categories'])
        if d['category'] in RESTRICTED and (d['category'] not in cats or (d['category']=='salud' and 'health' not in json.loads(g['permissions']))): continue
        if d['category'] in cats or '*' in cats: return True
    return False

def document_allowed(c,u,d,action='read'):
    if normal_document_allowed(c,u,d,action): return True
    if action not in ['read','download','sign']: return False
    assignment=one(c,'''SELECT s.id FROM signers s JOIN signature_requests r ON r.id=s.request_id
        JOIN versions v ON v.id=r.version_id WHERE s.user_id=? AND v.document_id=? AND s.revoked=0
        AND r.status NOT IN ('cancelada','rechazada') AND r.expires>?''',(u['id'],d['id'],now()))
    return bool(assignment and allowed(c,u,d['project_id'],'download' if action=='read' else action,d['company_id'],d['category']))

def document_access(c,u,d,action='read'):
    if not document_allowed(c,u,d,action): fail(403,'No tienes permiso para este documento o acción.')
def require_admin(u):
    if not u['admin']: fail(403,'Acción reservada a administración.')

def version_access(c,u,v,d,action='download'):
    document_access(c,u,d,action)
    if u['admin']: return
    if normal_document_allowed(c,u,d,action): return
    if not one(c,'''SELECT s.id FROM signers s JOIN signature_requests r ON r.id=s.request_id
        WHERE s.user_id=? AND r.version_id=? AND s.revoked=0 AND r.expires>?
        AND r.status NOT IN ('cancelada','rechazada')''',(u['id'],v['id'],now())):
        fail(403,'El firmante solo puede acceder a su versión asignada.')
