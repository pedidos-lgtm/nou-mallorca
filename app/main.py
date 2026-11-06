import os, json, secrets, io, zipfile, csv, hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta, date
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from .db import *
from .security import *
from .engine import *
from .files import validate_file, store, pdf_report, TestSignatureAdapter
from .library import router as library_router
from .document_state import reuse_trace,library_status
from .bootstrap import bootstrap_admin
from .imports import router as imports_router

@asynccontextmanager
async def lifespan(app):
    migrate()
    with connect() as c: seed_catalog(c)
    if os.getenv('APP_ENV')=='production' and (os.getenv('COOKIE_SECURE')!='true' or not (os.getenv('APP_URL') or os.getenv('RENDER_EXTERNAL_URL','')).startswith('https://')):
        raise RuntimeError('Producción exige APP_URL HTTPS y COOKIE_SECURE=true')
    if os.getenv('SIGNATURE_ADAPTER','test')!='test' or os.getenv('MAIL_ADAPTER','test')!='test':
        raise RuntimeError('Esta V1 solo implementa adaptadores de prueba. No se puede seleccionar un proveedor real.')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        bootstrap_admin(c)
    yield
app=FastAPI(title='Nou Mallorca · Gestión de obras',lifespan=lifespan)
app.include_router(library_router)
app.include_router(imports_router)

@app.middleware('http')
async def security_headers(request,call_next):
    length=request.headers.get('content-length')
    if length and int(length)>16*1024*1024: return JSONResponse({'detail':'Solicitud demasiado grande'},413)
    response=await call_next(request)
    response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"})
    if request.url.path.startswith('/api/versions/') and request.url.path.endswith('/file') and request.query_params.get('inline')=='true':
        response.headers['X-Frame-Options']='SAMEORIGIN'
        response.headers['Content-Security-Policy']="default-src 'none'; frame-ancestors 'self'; sandbox"
    if os.getenv('COOKIE_SECURE')=='true': response.headers['Strict-Transport-Security']='max-age=31536000'
    return response

def body_text(b,key,required=True,maxlen=1000):
    v=b.get(key)
    if v is None or v=='':
        if required: fail(422,'Falta el campo: '+key)
        return None
    if not isinstance(v,str) or len(v)>maxlen: fail(422,'Campo no válido: '+key)
    value=v.strip()
    if required and not value:fail(422,'Falta el campo: '+key)
    return value
def password_value(b,key):
    value=b.get(key)
    if not isinstance(value,str) or not value or len(value)>256:fail(422,'Contraseña no válida.')
    return value
def valid_date(v):
    if not v: return None
    try: return date.fromisoformat(v).isoformat()
    except (ValueError,TypeError): fail(422,'Fecha no válida.')
def get_project(c,pid):
    p=one(c,'SELECT * FROM projects WHERE id=?',(pid,))
    if not p: fail(404,'Obra no encontrada.')
    return p
def get_doc(c,did):
    d=one(c,'SELECT * FROM documents WHERE id=?',(did,))
    if not d: fail(404,'Documento no encontrado.')
    return d
def get_version(c,vid):
    v=one(c,'SELECT * FROM versions WHERE id=?',(vid,))
    if not v: fail(404,'Versión no encontrada.')
    return v,get_doc(c,v['document_id'])
def related_company(c,pid,cid):
    if cid and not one(c,'SELECT id FROM participations WHERE project_id=? AND company_id=?',(pid,cid)): fail(422,'Empresa no participante en la obra.')
def task_category(c,t):
    category='prl'
    if t.get('requirement_id'):
        r=one(c,'SELECT category FROM requirements WHERE id=?',(t['requirement_id'],))
        if r: category=r['category']
    return category
def visible_task(c,u,t):
    return allowed(c,u,t['project_id'],'read',t['company_id'],task_category(c,t))
def visible_project_details(c,u,pid,details):
    internal=u['admin'] or any(g['company_id'] is None and g['role']!='firmante' for g in grants(c,u,pid))
    return details if internal else {k:v for k,v in details.items() if k in ['description','address','start','end','emergency']}

def public_user(u): return {k:u[k] for k in ['id','email','name','admin','csrf'] if k in u}

@app.post('/api/login')
async def login(request:Request):
    b=await request.json(); email=body_text(b,'email').lower(); pw=password_value(b,'password')
    key=digest((request.client.host if request.client else '')+email)
    with connect() as c:
        a=one(c,'SELECT * FROM login_attempts WHERE key=?',(key,))
        if a and a['window']>now() and a['attempts']>=8: fail(429,'Demasiados intentos. Espera 15 minutos.')
        if not a or a['window']<now(): c.execute('INSERT OR REPLACE INTO login_attempts VALUES(?,?,?)',(key,0,(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat()))
        c.execute('UPDATE login_attempts SET attempts=attempts+1 WHERE key=?',(key,));c.commit()
        u=one(c,'SELECT * FROM users WHERE email=?',(email,))
        if not u or u['disabled'] or not password_ok(pw,u['password']): fail(401,'Credenciales incorrectas.')
        c.execute('DELETE FROM login_attempts WHERE key=?',(key,))
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        insert(c,'sessions',token=digest(token),user_id=u['id'],csrf=csrf,expires=after(0.5))
        audit(c,u['id'],None,'login')
    r=JSONResponse({'user':public_user({**u,'csrf':csrf})});r.set_cookie('nm_session',token,httponly=True,secure=os.getenv('COOKIE_SECURE')=='true',samesite='strict',max_age=43200,path='/');return r

@app.post('/api/logout')
def logout(request:Request):
    with connect() as c:
        u=user(c,request,True);c.execute('DELETE FROM sessions WHERE token=?',(digest(request.cookies.get('nm_session','')),))
    r=JSONResponse({'ok':True});r.delete_cookie('nm_session');return r

@app.get('/api/me')
def me(request:Request):
    with connect() as c:
        u=user(c,request)
        return {'user':public_user(u),'grants':rows(c,'SELECT * FROM grants WHERE user_id=?',(u['id'],)),'phases':PHASES,'categories':rows(c,'SELECT * FROM categories'),'signature_adapter':'test','mail_adapter':'test','environment':os.getenv('APP_ENV','development')}

@app.get('/api/dashboard')
def dashboard(request:Request):
    with connect() as c:
        u=user(c,request);projects=[];tasks=[];docs=[];signatures=[];alerts=[]
        for p in rows(c,'SELECT * FROM projects ORDER BY created_at DESC'):
            if not u['admin'] and not grants(c,u,p['id']): continue
            p['details']=visible_project_details(c,u,p['id'],json.loads(p['details']));p['health']=health(c,u,p)
            ts=[t for t in rows(c,'SELECT * FROM tasks WHERE project_id=? ORDER BY due IS NULL,due,priority',(p['id'],)) if visible_task(c,u,t)]
            tasks+=ts;p['next_action']=next((t for t in ts if t['status'] not in ['completada','cancelada']),None)
            projects.append(p)
            for d in rows(c,'SELECT * FROM documents WHERE project_id=?',(p['id'],)):
                if document_allowed(c,u,d,'read'):
                    d['versions']=rows(c,'SELECT * FROM versions WHERE document_id=? ORDER BY number DESC',(d['id'],))
                    if not normal_document_allowed(c,u,d,'read'):
                        d['versions']=[v for v in d['versions'] if one(c,'''SELECT s.id FROM signers s JOIN signature_requests r ON r.id=s.request_id WHERE s.user_id=? AND r.version_id=? AND s.revoked=0 AND r.expires>? AND r.status NOT IN ('cancelada','rechazada')''',(u['id'],v['id'],now()))]
                    for v in d['versions']:
                        v.pop('storage_key',None);v['effective_status']=effective_status(v,c);v['reuse']=reuse_trace(c,v['id'])
                        v['reviews']=rows(c,'SELECT r.action,r.reason,r.created_at,u.name AS reviewer FROM reviews r JOIN users u ON u.id=r.user_id WHERE r.version_id=? ORDER BY r.created_at DESC',(v['id'],))
                    docs.append(d)
            for s in rows(c,'SELECT s.*,d.title,d.company_id,d.category,d.project_id FROM signature_requests s JOIN versions v ON v.id=s.version_id JOIN documents d ON d.id=v.document_id WHERE d.project_id=?',(p['id'],)):
                if allowed(c,u,p['id'],'read',s['company_id'],s['category']) or one(c,'SELECT id FROM signers WHERE request_id=? AND user_id=? AND revoked=0',(s['id'],u['id'])):
                    if s['expires']<now() and s['status'] in ['pendiente','parcial']: s['status']='caducada'
                    signatures.append(s)
            alerts += [a for a in rows(c,'SELECT * FROM alerts WHERE project_id=?',(p['id'],)) if allowed(c,u,p['id'],'read',a['company_id'],a['category'])]
        companies=[x for x in rows(c,'SELECT * FROM companies') if u['admin'] or any(allowed(c,u,p['id'],'read',x['id'],'prl') and one(c,'SELECT id FROM participations WHERE company_id=? AND project_id=?',(x['id'],p['id'])) for p in projects)]
        for company in companies:
            company['project_ids']=[p['id'] for p in projects if one(c,'SELECT id FROM participations WHERE project_id=? AND company_id=?',(p['id'],company['id']))]
        workers=[];equipment=[]
        for table,assignment,key,dest in [('workers','worker_assignments','worker_id',workers),('equipment','equipment_assignments','equipment_id',equipment)]:
            for e in rows(c,f'SELECT * FROM {table}'):
                e['project_ids']=[r['project_id'] for r in rows(c,f'SELECT project_id FROM {assignment} WHERE {key}=?',(e['id'],)) if any(p['id']==r['project_id'] for p in projects) and allowed(c,u,r['project_id'],'read',e['company_id'],'prl')]
                if e['project_ids'] or u['admin']: dest.append(e)
        return {'projects':projects,'tasks':tasks,'documents':docs,'signatures':signatures,'companies':companies,'workers':workers,'equipment':equipment,'alerts':alerts}

@app.post('/api/projects')
async def create_project(request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);require_admin(u)
        hp=b.get('has_project')
        if hp not in [None,True,False]: fail(422,'Indica con proyecto, sin proyecto o sin definir.')
        p=insert(c,'projects',id=uid(),name=body_text(b,'name'),code=body_text(b,'code'),municipality=b.get('municipality',''),has_project=None if hp is None else int(hp),details=js(b.get('details',{})),created_at=now())
        generate(c,p['id']);audit(c,u['id'],p['id'],'obra_creada',p['id'])
        return p

@app.get('/api/projects/{pid}')
def project_detail(pid:str,request:Request):
    with connect() as c:
        u=user(c,request);p=get_project(c,pid);project_access(c,u,pid);p['details']=visible_project_details(c,u,p['id'],json.loads(p['details']));p['health']=health(c,u,p)
        # External users receive their own participation, never internal contacts or project financial notes.
        internal=u['admin'] or any(g['company_id'] is None for g in grants(c,u,pid))
        if not internal: p['details']={k:v for k,v in p['details'].items() if k in ['description','address','start','end','emergency']}
        p['requirements']=visible_requirements(c,u,pid)
        p['participations']=[x for x in rows(c,'SELECT x.*,c.name,c.kind FROM participations x JOIN companies c ON c.id=x.company_id WHERE project_id=?',(pid,)) if allowed(c,u,pid,'read',x['company_id'],'prl')]
        p['agents']=rows(c,'SELECT * FROM agents WHERE project_id=?',(pid,)) if internal else []
        p['milestones']=[m for m in rows(c,'SELECT * FROM milestones WHERE project_id=?',(pid,)) if internal]
        p['audit']=rows(c,'SELECT a.*,u.name AS user_name FROM audit a LEFT JOIN users u ON u.id=a.user_id WHERE project_id=? ORDER BY created_at DESC LIMIT 100',(pid,)) if u['admin'] else []
        p['invitations']=[{k:v for k,v in i.items() if k!='token_hash'} for i in rows(c,'SELECT * FROM invitations WHERE project_id=?',(pid,))] if u['admin'] else []
        return p

@app.patch('/api/projects/{pid}')
async def update_project(pid:str,request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);require(c,u,pid,'manage');p=get_project(c,pid)
        for key in ['name','code','municipality']:
            if key in b:
                value=body_text(b,key,required=key!='municipality') or ''
                c.execute(f'UPDATE projects SET {key}=? WHERE id=?',(value,pid))
        if 'has_project' in b:
            hp=b['has_project']
            if hp is not None and type(hp)!=bool: fail(422,'Tipo de obra no válido.')
            new_hp=None if hp is None else int(hp)
            if p['has_project'] is not None and new_hp!=p['has_project']:
                fail(409,'El cambio de tipología de una obra ya definida requiere revisión de sus requisitos. No se realiza silenciosamente; conserva el expediente y revisa con administración.')
            c.execute('UPDATE projects SET has_project=? WHERE id=?',(new_hp,pid));generate(c,pid)
            audit(c,u['id'],pid,'tipologia_definida',details={'has_project':hp})
        if 'phase' in b:
            phase=b['phase']
            if type(phase)!=int or phase not in range(len(PHASES)): fail(422,'Fase no válida.')
            h=health(c,u,p)
            if phase>p['phase'] and h['color'] in ['rojo','gris']:
                if not u['admin'] or not b.get('exception_reason'): fail(409,'Paso bloqueado: '+('; '.join(h['causes'][:6]) or 'Datos insuficientes')+'. Administración puede registrar una excepción motivada.')
                audit(c,u['id'],pid,'excepcion_paso',details={'reason':b['exception_reason'],'causes':h['causes']})
            c.execute('UPDATE projects SET phase=? WHERE id=?',(phase,pid))
            audit(c,u['id'],pid,'cambio_fase',details={'from':p['phase'],'to':phase})
        if 'paused' in b:
            if b['paused'] and not b.get('pause_reason'): fail(422,'Indica el motivo de paralización.')
            c.execute('UPDATE projects SET paused=?,pause_reason=? WHERE id=?',(bool(b['paused']),b.get('pause_reason'),pid));audit(c,u['id'],pid,'paralizacion',details=b)
        if 'details' in b:
            d={**json.loads(p['details']),**b['details']};c.execute('UPDATE projects SET details=? WHERE id=?',(js(d),pid));audit(c,u['id'],pid,'datos_actualizados')
        return {'ok':True}

@app.post('/api/companies')
async def company_create(request:Request):
    b=await request.json();pid=body_text(b,'project_id');kind=body_text(b,'kind');role=body_text(b,'role')
    if kind not in ['con_trabajadores','autonomo','suministro'] or role not in ['subcontrata','contratista','instalador','suministro','otro']: fail(422,'Tipo o papel no válido.')
    with connect() as c:
        u=user(c,request,True);require(c,u,pid,'manage')
        cid=b.get('company_id')
        if cid:
            if not one(c,'SELECT id FROM companies WHERE id=?',(cid,)): fail(404,'Empresa no encontrada.')
            if one(c,'SELECT kind FROM companies WHERE id=?',(cid,))['kind']=='pendiente_definir':
                c.execute('UPDATE companies SET kind=? WHERE id=?',(kind,cid))
                audit(c,u['id'],pid,'clasificacion_proveedor_confirmada',cid,{'kind':kind},cid)
        else:
            cid=uid();insert(c,'companies',id=cid,name=body_text(b,'name'),kind=kind,details=js(b.get('details',{})))
        if one(c,'SELECT id FROM participations WHERE project_id=? AND company_id=?',(pid,cid)): fail(409,'La empresa ya participa en esta obra.')
        insert(c,'participations',id=uid(),project_id=pid,company_id=cid,role=role,activity=b.get('activity'))
        generate(c,pid);audit(c,u['id'],pid,'empresa_incorporada',cid,company=cid)
        return {'id':cid}

@app.post('/api/people/{kind}')
async def people_create(kind:str,request:Request):
    if kind not in ['workers','equipment']: fail(404,'Tipo no válido.')
    b=await request.json();pid=body_text(b,'project_id');cid=body_text(b,'company_id')
    with connect() as c:
        u=user(c,request,True);require(c,u,pid,'upload',cid,'prl');related_company(c,pid,cid)
        eid=uid();name=body_text(b,'name')
        if kind=='workers': insert(c,'workers',id=eid,company_id=cid,name=name,trade=b.get('trade',''),details='{}');insert(c,'worker_assignments',worker_id=eid,project_id=pid)
        else:
            ek=b.get('kind','herramienta')
            if ek not in ['andamio','plataforma','elevacion','tierras','herramienta','otro']: fail(422,'Tipo de equipo no válido.')
            insert(c,'equipment',id=eid,company_id=cid,name=name,kind=ek,details='{}');insert(c,'equipment_assignments',equipment_id=eid,project_id=pid)
        generate(c,pid);audit(c,u['id'],pid,'asignacion_'+kind,eid,company=cid)
        return {'id':eid}

@app.post('/api/agents')
async def agent_create(request:Request):
    b=await request.json();pid=body_text(b,'project_id')
    with connect() as c:
        u=user(c,request,True);require(c,u,pid,'manage');a=insert(c,'agents',id=uid(),project_id=pid,name=body_text(b,'name'),function=body_text(b,'function'),details=js(b.get('details',{})));audit(c,u['id'],pid,'agente_incorporado',a['id']);return a

@app.post('/api/requirements/{rid}')
async def requirement_action(rid:str,request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);r=one(c,'SELECT * FROM requirements WHERE id=?',(rid,))
        if not r: fail(404,'Requisito no encontrado.')
        require(c,u,r['project_id'],'validate',r['company_id'],r['category'])
        action=b.get('action');reason=body_text(b,'reason')
        if action=='no_aplicable': c.execute('UPDATE requirements SET status=?,reason=?,author=? WHERE id=?',('no_aplicable',reason,u['id'],rid))
        elif action=='aplica':
            c.execute('UPDATE requirements SET applicability=?,status=?,blocking=?,reason=?,author=? WHERE id=?',('aplica','pendiente',int(bool(b.get('blocking'))),reason,u['id'],rid))
        else: fail(422,'Acción no válida.')
        if action=='aplica':
            c.execute("UPDATE tasks SET title=?,priority=? WHERE requirement_id=? AND status NOT IN ('completada','cancelada')",('Aportar: '+r['name'],'alta' if b.get('blocking') else 'normal',rid))
        audit(c,u['id'],r['project_id'],'requisito_'+action,rid,{'reason':reason,'blocking':b.get('blocking')},r['company_id']);return {'ok':True}

@app.post('/api/documents')
async def upload(request:Request,file:UploadFile=File(...),metadata:str=Form(...)):
    try: b=json.loads(metadata)
    except Exception: fail(422,'Metadatos no válidos.')
    pid=body_text(b,'project_id');cid=b.get('company_id');category=body_text(b,'category');rid=b.get('requirement_id');did=b.get('document_id')
    content=await file.read(15*1024*1024+1)
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        u=user(c,request,True);require(c,u,pid,'upload',cid,category);related_company(c,pid,cid)
        if not one(c,'SELECT id FROM categories WHERE id=?',(category,)): fail(422,'Categoría desconocida.')
        if rid:
            r=one(c,'SELECT * FROM requirements WHERE id=?',(rid,))
            if not r or r['project_id']!=pid or r['company_id']!=cid or r['category']!=category: fail(422,'El requisito no corresponde al ámbito del documento.')
        expires=valid_date(b.get('expires'))
        if expires and not b.get('validity_reason'): fail(422,'Justifica la vigencia (fuente, documento o regla configurada).')
        if did:
            d=get_doc(c,did);document_access(c,u,d,'upload')
            if (d['project_id'],d['company_id'],d['category'],d['requirement_id'])!=(pid,cid,category,rid): fail(422,'No se puede cambiar el ámbito de una versión.')
        else:
            if rid and one(c,'SELECT id FROM documents WHERE requirement_id=?',(rid,)): fail(409,'El requisito ya tiene documento. Añade una nueva versión.')
            did=uid();insert(c,'documents',id=did,project_id=pid,company_id=cid,requirement_id=rid,title=body_text(b,'title'),category=category,details=js({**b.get('details',{}),'validity_reason':b.get('validity_reason')}),created_by=u['id'],created_at=now())
        clean,mime,ext=validate_file(content,file.filename,preserve_original=bool(b.get('external_signed')))
        key,hash_value=store(clean,ext)
        n=c.execute('SELECT COALESCE(MAX(number),0)+1 FROM versions WHERE document_id=?',(did,)).fetchone()[0]
        # Previous version remains intact; current is highest number. No inherited signatures.
        provenance='externo: '+body_text(b,'external_source') if b.get('external_signed') else 'carga_usuario'
        v=insert(c,'versions',id=uid(),document_id=did,number=n,storage_key=key,filename=Path(file.filename or 'documento').name,mime=mime,hash=hash_value,expires=expires,provenance=provenance,created_by=u['id'],created_at=now(),status='recibido')
        audit(c,u['id'],pid,'version_recibida',v['id'],{'number':n,'provenance':provenance,'hash':hash_value},cid)
        return {'id':did,'version_id':v['id'],'status':'recibido'}

@app.get('/api/versions/{vid}/file')
def version_download(vid:str,request:Request,inline:bool=False):
    with connect() as c:
        u=user(c,request);v,d=get_version(c,vid);version_access(c,u,v,d,'download');audit(c,u['id'],d['project_id'],'descarga_version',vid,company=d['company_id'])
        # Originals are sanitized on ingestion; image MIME preserved.
        return FileResponse(FILES/v['storage_key'],media_type=v['mime'],filename=v['filename'],content_disposition_type='inline' if inline else 'attachment')

@app.post('/api/versions/{vid}/review')
async def review(vid:str,request:Request):
    b=await request.json();action=b.get('action');reason=body_text(b,'reason')
    perms={'en_revision':'review','rechazado':'review','validado':'validate','aprobado':'approve'}
    if action not in perms: fail(422,'Estado no válido.')
    with connect() as c:
        u=user(c,request,True);v,d=get_version(c,vid);document_access(c,u,d,perms[action])
        if action in ['validado','aprobado'] and effective_status(v,c) in ['sustituido','rechazado','caducado'] and reuse_trace(c,vid):
            fail(409,'El documento reutilizado ha perdido vigencia en origen. Aporta una versión vigente antes de validar.')
        current=one(c,'SELECT id FROM versions WHERE document_id=? ORDER BY number DESC LIMIT 1',(d['id'],))
        if current['id']!=vid: fail(409,'Revisa la versión vigente, no una histórica.')
        if action=='aprobado':
            if v['status']!='validado': fail(409,'La aprobación técnica requiere validación previa y expresa.')
        else: c.execute('UPDATE versions SET status=? WHERE id=?',(action,vid))
        insert(c,'reviews',id=uid(),version_id=vid,action=action,reason=reason,user_id=u['id'],created_at=now())
        audit(c,u['id'],d['project_id'],'revision_'+action,vid,{'reason':reason},d['company_id']);return {'ok':True}

@app.post('/api/invitations')
async def invite(request:Request):
    b=await request.json();pid=body_text(b,'project_id');cid=b.get('company_id');role=body_text(b,'role')
    if role not in ROLES: fail(422,'Perfil no válido.')
    cats=b.get('categories',SAFE_CATEGORIES);perms=b.get('permissions',ROLES[role])
    if not isinstance(cats,list) or not isinstance(perms,list) or any(p not in ACTIONS for p in perms): fail(422,'Permisos no válidos.')
    if role in ['empresa','firmante'] and (not cid or any(p not in ROLES[role] for p in perms)): fail(422,'Perfil externo limitado a su empresa y trámites.')
    if role in ['direccion','encargado'] and any(cat in RESTRICTED for cat in cats): fail(422,'Este perfil no puede recibir categorías restringidas.')
    with connect() as c:
        u=user(c,request,True);require_admin(u);get_project(c,pid);related_company(c,pid,cid)
        if any(not one(c,'SELECT id FROM categories WHERE id=?',(cat,)) for cat in cats): fail(422,'Categoría no válida.')
        email=body_text(b,'email').lower()
        if '@' not in email: fail(422,'Correo no válido.')
        token=secrets.token_urlsafe(32);iid=uid()
        insert(c,'invitations',id=iid,token_hash=digest(token),email=email,name=body_text(b,'name'),project_id=pid,company_id=cid,role=role,categories=js(cats),permissions=js(perms),expires=after(7),created_by=u['id'])
        link='/#invitacion/'+token
        insert(c,'outbox',id=uid(),event_key='invite:'+iid,recipient=email,subject='Invitación a Nou Mallorca',body=link,adapter='test',created_at=now())
        audit(c,u['id'],pid,'invitacion_creada',iid,{'email':email,'role':role},cid)
        return {'id':iid,'link':link,'expires':after(7),'delivery':'prueba_no_enviado'}

@app.get('/api/invitations/{token}')
def invitation_info(token:str):
    with connect() as c:
        i=one(c,'SELECT i.*,p.name AS project_name FROM invitations i JOIN projects p ON p.id=i.project_id WHERE token_hash=?',(digest(token),))
        if not i or i['used_at'] or i['revoked'] or i['expires']<now(): fail(410,'Invitación caducada, usada o revocada.')
        return {k:i[k] for k in ['name','email','role','project_name','expires']}

@app.post('/api/invitations/{token}/accept')
async def accept_invite(token:str,request:Request):
    b=await request.json()
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        i=one(c,'SELECT * FROM invitations WHERE token_hash=?',(digest(token),))
        if not i or i['used_at'] or i['revoked'] or i['expires']<now(): fail(410,'Invitación caducada, usada o revocada.')
        existing=one(c,'SELECT * FROM users WHERE email=?',(i['email'],))
        if existing:
            u=user(c,request,True)
            if u['id']!=existing['id']: fail(403,'Inicia sesión con el correo invitado para aceptar.')
            user_id=existing['id']
        else:
            user_id=uid();insert(c,'users',id=user_id,email=i['email'],name=i['name'],password=password_hash(password_value(b,'password')))
        # Reaccepting does not silently replace existing grants.
        c.execute('DELETE FROM grants WHERE user_id=? AND project_id=? AND company_id IS ?',(user_id,i['project_id'],i['company_id']))
        insert(c,'grants',id=uid(),user_id=user_id,project_id=i['project_id'],company_id=i['company_id'],role=i['role'],categories=i['categories'],permissions=i['permissions'])
        c.execute('UPDATE invitations SET used_at=? WHERE id=?',(now(),i['id']));audit(c,user_id,i['project_id'],'invitacion_aceptada',i['id'],company=i['company_id']);return {'ok':True,'email':i['email']}

@app.post('/api/invitations/{iid}/revoke')
def revoke_invite(iid:str,request:Request):
    with connect() as c:
        u=user(c,request,True);require_admin(u);c.execute('UPDATE invitations SET revoked=1 WHERE id=?',(iid,));return {'ok':True}

@app.get('/api/projects/{pid}/signer-options')
def signer_options(pid:str,request:Request,company_id:str|None=None,category:str='prl'):
    with connect() as c:
        u=user(c,request);require(c,u,pid,'manage')
        return [{'id':v['id'],'name':v['name'],'email':v['email']} for v in rows(c,'SELECT * FROM users WHERE disabled=0') if allowed(c,v,pid,'sign',company_id,category) and allowed(c,v,pid,'download',company_id,category)]

@app.post('/api/signatures')
async def signature_create(request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);v,d=get_version(c,body_text(b,'version_id'));require(c,u,d['project_id'],'manage',d['company_id'],d['category'])
        if v['mime']!='application/pdf': fail(422,'El adaptador de prueba firma únicamente PDF.')
        if b.get('mode','paralela') not in ['paralela','secuencial']: fail(422,'Modalidad no válida.')
        signers=b.get('signers',[])
        if not signers or len(signers)>20 or len({s.get('user_id') for s in signers})!=len(signers): fail(422,'Selecciona de 1 a 20 firmantes distintos.')
        for s in signers:
            su=one(c,'SELECT * FROM users WHERE id=? AND disabled=0',(s.get('user_id'),))
            if not su or not allowed(c,su,d['project_id'],'sign',d['company_id'],d['category']) or not allowed(c,su,d['project_id'],'download',d['company_id'],d['category']): fail(422,'Firmante sin permiso sobre la versión.')
        sid=uid();expires=after(7)
        insert(c,'signature_requests',id=sid,version_id=v['id'],mode=b.get('mode','paralela'),provider='test',expires=expires,created_by=u['id'],created_at=now())
        links=[]
        for pos,s in enumerate(signers):
            tok=secrets.token_urlsafe(32);insert(c,'signers',id=uid(),request_id=sid,user_id=s['user_id'],position=pos,function=s.get('function','Firmante'),token_hash=digest(tok));links.append({'user_id':s['user_id'],'link':'/#firma/'+tok})
        audit(c,u['id'],d['project_id'],'firma_prueba_solicitada',sid,{'version_id':v['id'],'original_hash':v['hash']},d['company_id']);return {'id':sid,'links':links,'expires':expires,'provider':'test'}

def signature_token(c,u,token):
    s=one(c,'SELECT * FROM signers WHERE token_hash=?',(digest(token),))
    if not s: fail(404,'Trámite no encontrado.')
    sr=one(c,'SELECT * FROM signature_requests WHERE id=?',(s['request_id'],))
    if s['revoked'] or sr['expires']<now() or sr['status'] in ['cancelada','rechazada']: fail(410,'Enlace caducado, cancelado o revocado.')
    if s['user_id']!=u['id']: fail(403,'Debes identificarte con la cuenta del firmante asignado.')
    v,d=get_version(c,sr['version_id']);document_access(c,u,d,'sign');document_access(c,u,d,'download')
    return s,sr,v,d

@app.get('/api/sign/{token}')
def sign_info(token:str,request:Request):
    with connect() as c:
        u=user(c,request);s,sr,v,d=signature_token(c,u,token)
        previous=one(c,"SELECT id FROM signers WHERE request_id=? AND position<? AND status!='completada'",(sr['id'],s['position']))
        return {'title':d['title'],'version_id':v['id'],'version':v['number'],'hash':v['hash'],'provider':'test','status':s['status'],'request_status':sr['status'],'function':s['function'],'expires':sr['expires'],'waiting':bool(sr['mode']=='secuencial' and previous)}

def archive_signature(c,sr,v,d):
    if one(c,'SELECT request_id FROM signature_archives WHERE request_id=?',(sr['id'],)): return
    signers=rows(c,'SELECT s.user_id,u.name,s.function,s.signed_at,s.status FROM signers s JOIN users u ON u.id=s.user_id WHERE request_id=? ORDER BY position',(sr['id'],))
    if any(s['status']!='completada' for s in signers): fail(409,'Faltan firmantes.')
    evidence={'request_id':sr['id'],'provider':'test','warning':'Simulación sin firma electrónica real. No equivale a aprobación técnica.','version_id':v['id'],'original_hash':v['hash'],'signers':signers,'archived_at':now()}
    signed=TestSignatureAdapter().complete((FILES/v['storage_key']).read_bytes(),evidence)
    key,h=store(signed,'.pdf');ek,_=store(js(evidence).encode(),'.json')
    insert(c,'signature_archives',request_id=sr['id'],storage_key=key,evidence_key=ek,hash=h,created_at=now())
    c.execute("UPDATE signature_requests SET status='completada' WHERE id=?",(sr['id'],))
    c.execute('INSERT OR IGNORE INTO alerts(id,event_key,project_id,company_id,message,created_at,category) VALUES(?,?,?,?,?,?,?)',(uid(),'signature:'+sr['id'],d['project_id'],d['company_id'],'Firma de prueba archivada: '+d['title'],now(),d['category']))
    audit(c,sr['created_by'],d['project_id'],'firma_prueba_archivada',sr['id'],{'hash':h},d['company_id'])

@app.post('/api/sign/{token}')
async def sign_action(token:str,request:Request):
    b=await request.json()
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');u=user(c,request,True);s,sr,v,d=signature_token(c,u,token)
        if s['status']=='completada': return {'status':'completada','request_status':sr['status']}
        if sr['mode']=='secuencial' and one(c,"SELECT id FROM signers WHERE request_id=? AND position<? AND status!='completada'",(sr['id'],s['position'])): fail(409,'Debe firmar antes el firmante anterior.')
        if b.get('action')=='reject':
            reason=body_text(b,'reason');c.execute("UPDATE signers SET status='rechazada',reason=? WHERE id=?",(reason,s['id']));c.execute("UPDATE signature_requests SET status='rechazada' WHERE id=?",(sr['id'],));audit(c,u['id'],d['project_id'],'firma_rechazada',sr['id'],{'reason':reason},d['company_id']);return {'status':'rechazada'}
        if b.get('consent') is not True: fail(422,'Debes confirmar que has consultado el documento completo y deseas realizar la firma simulada.')
        c.execute("UPDATE signers SET status='completada',signed_at=? WHERE id=?",(now(),s['id']))
        audit(c,u['id'],d['project_id'],'firma_prueba_confirmada',sr['id'],{'hash':v['hash'],'intent':True,'mechanism':'cuenta_autenticada_prueba'},d['company_id'])
        if not one(c,"SELECT id FROM signers WHERE request_id=? AND status!='completada'",(sr['id'],)): archive_signature(c,sr,v,d)
        else: c.execute("UPDATE signature_requests SET status='parcial' WHERE id=?",(sr['id'],))
        return {'status':'completada','request_status':one(c,'SELECT status FROM signature_requests WHERE id=?',(sr['id'],))['status']}

@app.post('/api/signatures/{sid}/{action}')
async def signature_manage(sid:str,action:str,request:Request):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE')
        u=user(c,request,True);sr=one(c,'SELECT * FROM signature_requests WHERE id=?',(sid,))
        if not sr: fail(404,'Solicitud no encontrada.')
        v,d=get_version(c,sr['version_id']);require(c,u,d['project_id'],'manage',d['company_id'],d['category'])
        if action=='cancel':
            if sr['status']=='completada':fail(409,'Una firma completada conserva su resultado y no se puede cancelar. Crea una nueva solicitud si necesitas otro trámite.')
            c.execute("UPDATE signature_requests SET status='cancelada' WHERE id=? AND status!='completada'",(sid,));c.execute('UPDATE signers SET revoked=1 WHERE request_id=?',(sid,))
        elif action=='confirm-sent': audit(c,u['id'],d['project_id'],'envio_confirmado_usuario',sid,{'delivery_verified':False},d['company_id'])
        elif action=='remind':
            for s in rows(c,"SELECT u.email FROM signers s JOIN users u ON u.id=s.user_id WHERE s.request_id=? AND s.status='pendiente'",(sid,)):
                c.execute('INSERT OR IGNORE INTO outbox VALUES(?,?,?,?,?,?,?,?)',(uid(),'remind:'+sid+':'+s['email']+':'+date.today().isoformat(),s['email'],'Firma pendiente',d['title'],'test','prueba_no_enviado',now()))
        elif action=='retry-archive': archive_signature(c,sr,v,d)
        else: fail(422,'Acción no válida.')
        return {'ok':True}

@app.get('/api/signatures/{sid}/archive')
def download_archive(sid:str,request:Request,evidence:bool=False):
    with connect() as c:
        u=user(c,request);sr=one(c,'SELECT * FROM signature_requests WHERE id=?',(sid,))
        if not sr: fail(404,'Solicitud no encontrada.')
        v,d=get_version(c,sr['version_id']);version_access(c,u,v,d,'download')
        a=one(c,'SELECT * FROM signature_archives WHERE request_id=?',(sid,))
        if not a: fail(404,'Resultado todavía no archivado.')
        audit(c,u['id'],d['project_id'],'descarga_firma',sid,company=d['company_id'])
        return FileResponse(FILES/a['evidence_key' if evidence else 'storage_key'],media_type='application/json' if evidence else 'application/pdf',filename='evidencias-prueba.json' if evidence else 'resultado-firma-PRUEBA.pdf')

@app.post('/api/tasks')
async def create_task(request:Request):
    b=await request.json();pid=body_text(b,'project_id');cid=b.get('company_id')
    with connect() as c:
        u=user(c,request,True);require(c,u,pid,'manage',cid);related_company(c,pid,cid)
        t=insert(c,'tasks',id=uid(),project_id=pid,company_id=cid,title=body_text(b,'title'),actor=b.get('actor'),owner=b.get('owner'),due=valid_date(b.get('due')),priority=b.get('priority','normal'),details=js({'priority_reason':b.get('priority_reason','Prioridad manual inicial')}))
        for dep in b.get('dependencies',[]):
            if not one(c,'SELECT id FROM tasks WHERE id=? AND project_id=?',(dep,pid)): fail(422,'Dependencia ajena a la obra.')
            insert(c,'dependencies',task_id=t['id'],depends_on=dep)
        audit(c,u['id'],pid,'tarea_creada',t['id'],company=cid);return t

@app.patch('/api/tasks/{tid}')
async def update_task(tid:str,request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);t=one(c,'SELECT * FROM tasks WHERE id=?',(tid,))
        if not t: fail(404,'Tarea no encontrada.')
        require(c,u,t['project_id'],'manage',t['company_id'],task_category(c,t))
        if 'status' in b:
            if b['status'] not in ['pendiente','en_curso','esperando_tercero','completada','cancelada']: fail(422,'Estado no válido.')
            if b['status']=='completada' and one(c,"SELECT d.task_id FROM dependencies d JOIN tasks t ON t.id=d.depends_on WHERE d.task_id=? AND t.status!='completada'",(tid,)): fail(409,'Hay dependencias pendientes.')
            c.execute('UPDATE tasks SET status=? WHERE id=?',(b['status'],tid))
        for key in ['actor','owner','due','priority']:
            if key in b:
                v=valid_date(b[key]) if key=='due' else b[key]
                if key=='priority' and (v not in ['normal','alta','urgente'] or not b.get('reason')): fail(422,'Justifica el ajuste de prioridad.')
                c.execute(f'UPDATE tasks SET {key}=? WHERE id=?',(v,tid))
        audit(c,u['id'],t['project_id'],'tarea_actualizada',tid,b,t['company_id']);return {'ok':True}

@app.post('/api/milestones')
async def create_milestone(request:Request):
    b=await request.json();pid=body_text(b,'project_id')
    with connect() as c:
        u=user(c,request,True);require(c,u,pid,'manage');return insert(c,'milestones',id=uid(),project_id=pid,title=body_text(b,'title'),date=valid_date(b.get('date')),details=js(b.get('details',{})))

@app.get('/api/settings')
def get_settings(request:Request):
    with connect() as c:
        u=user(c,request);require_admin(u)
        return {'rules':rows(c,'SELECT * FROM rule_templates'),'outbox':rows(c,'SELECT * FROM outbox ORDER BY created_at DESC LIMIT 100'),'settings':rows(c,'SELECT * FROM settings'),'users':[{k:v for k,v in x.items() if k!='password'} for x in rows(c,'SELECT * FROM users')],'grants':rows(c,'SELECT * FROM grants')}

@app.post('/api/categories')
async def add_category(request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);require_admin(u);cid=uid();insert(c,'categories',id=cid,name=body_text(b,'name'),sensitive=0);return {'id':cid}

@app.post('/api/rules')
async def add_rule(request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);require_admin(u);name=body_text(b,'name');scope=b.get('scope','obra');cond=b.get('condition','siempre')
        if scope not in ['obra','empresa','trabajador','equipo'] or cond not in ['siempre','con_proyecto','sin_proyecto','suministro','autonomo','ejecuta','montaje']: fail(422,'Ámbito o condición no válido.')
        category=b.get('category','prl')
        if not one(c,'SELECT id FROM categories WHERE id=?',(category,)): fail(422,'Categoría no válida.')
        classification=b.get('classification','procedimiento_interno')
        if classification not in ['legal','recomendacion_tecnica','contractual','procedimiento_interno','pendiente_revision']: fail(422,'Clasificación no válida.')
        rid=uid();insert(c,'rule_templates',id=rid,version=1,name=name,scope=scope,category=category,condition=cond,classification=classification,source=b.get('source'),details=js(b.get('details',{})),blocking=int(bool(b.get('blocking'))))
        audit(c,u['id'],None,'plantilla_creada',rid);return {'id':rid}

@app.post('/api/rules/{rid}')
async def update_rule(rid:str,request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);require_admin(u);r=one(c,'SELECT * FROM rule_templates WHERE id=?',(rid,))
        if not r: fail(404,'Plantilla no encontrada.')
        if not b.get('source') or not b.get('reason'): fail(422,'Indica fuente y fundamento de revisión. La aprobación debe hacerla una persona competente.')
        c.execute('UPDATE rule_templates SET version=version+1,source=?,review_date=?,approved_by=?,blocking=?,details=? WHERE id=?',(b['source'],date.today().isoformat(),u['id'],int(bool(b.get('blocking'))),js({**json.loads(r['details']),'review_reason':b['reason']}),rid))
        audit(c,u['id'],None,'plantilla_revisada',rid,{'previous':r,'reason':b['reason']});return {'ok':True,'notice':'Los requisitos existentes conservan su instantánea. No se modifican automáticamente.'}

@app.post('/api/projects/{pid}/generate')
def generate_requirements(pid:str,request:Request):
    with connect() as c:
        u=user(c,request,True);require(c,u,pid,'manage');generate(c,pid);return {'ok':True}

@app.post('/api/alerts/run')
def alerts_run(request:Request):
    with connect() as c:
        u=user(c,request,True);require_admin(u);return run_alerts(c)

def run_alerts(c):
    before=c.total_changes
    for v in rows(c,'SELECT v.*,d.project_id,d.company_id,d.title,d.category FROM versions v JOIN documents d ON d.id=v.document_id WHERE v.expires IS NOT NULL AND v.number=(SELECT MAX(v2.number) FROM versions v2 WHERE v2.document_id=v.document_id)'):
        if v['expires']<= (date.today()+timedelta(days=30)).isoformat():
            event='expired' if v['expires']<date.today().isoformat() else 'expiring'
            c.execute('INSERT OR IGNORE INTO alerts(id,event_key,project_id,company_id,message,created_at,category) VALUES(?,?,?,?,?,?,?)',(uid(),event+':'+v['id']+':'+v['expires'],v['project_id'],v['company_id'],('Caducado: ' if event=='expired' else 'Próximo vencimiento: ')+v['title'],now(),v['category']))
    for item in rows(c,'SELECT * FROM company_library'):
        state=library_status(c,item)
        if state=='validado': continue
        for d in rows(c,'SELECT d.* FROM documents d JOIN document_reuse r ON r.target_document_id=d.id WHERE r.library_id=?',(item['id'],)):
            c.execute('INSERT OR IGNORE INTO alerts(id,event_key,project_id,company_id,message,created_at,category) VALUES(?,?,?,?,?,?,?)',(uid(),'library:'+item['id']+':'+d['id']+':'+state,d['project_id'],d['company_id'],'Revisar origen documental ('+state+'): '+d['title'],now(),d['category']))
    for t in rows(c,"SELECT * FROM tasks WHERE due<? AND status NOT IN ('completada','cancelada')",(date.today().isoformat(),)):
        c.execute('INSERT OR IGNORE INTO alerts(id,event_key,project_id,company_id,message,created_at,category) VALUES(?,?,?,?,?,?,?)',(uid(),'overdue:'+t['id']+':'+t['due'],t['project_id'],t['company_id'],'Tarea vencida: '+t['title'],now(),one(c,'SELECT category FROM requirements WHERE id=?',(t['requirement_id'],))['category'] if t['requirement_id'] else 'prl'))
    return {'created':c.total_changes-before,'adapter':'interno; no se ha enviado correo'}

@app.get('/api/projects/{pid}/export')
def export(pid:str,request:Request,format:str='zip'):
    with connect() as c:
        u=user(c,request);project_access(c,u,pid);p=get_project(c,pid)
        docs=[d for d in rows(c,'SELECT * FROM documents WHERE project_id=?',(pid,)) if allowed(c,u,pid,'export',d['company_id'],d['category']) and allowed(c,u,pid,'download',d['company_id'],d['category'])]
        can_export=u['admin'] or any('export' in json.loads(g['permissions']) for g in grants(c,u,pid))
        if not can_export: fail(403,'No tienes permiso de exportación.')
        tasks=[t for t in rows(c,'SELECT * FROM tasks WHERE project_id=?',(pid,)) if visible_task(c,u,t) and allowed(c,u,pid,'export',t['company_id'],task_category(c,t))]
        audit(c,u['id'],pid,'exportacion',pid,{'format':format,'document_count':len(docs),'filters':'obra y permisos actuales'})
        if format=='csv':
            out=io.StringIO();w=csv.writer(out);w.writerow(['Generado',now(),'Filtros','Obra y permisos actuales']);w.writerow(['Tarea','Estado','Responsable','Fecha límite','Origen'])
            def safe(x):
                x=str(x or 'Sin definir');return "'"+x if x.startswith(('=','+','-','@','\t','\r')) else x
            for t in tasks:w.writerow([safe(t['title']),t['status'],safe(t['owner']),t['due'] or 'Sin fecha definida',t['origin']])
            return Response('\ufeff'+out.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="tareas.csv"'})
        reqs=[r for r in visible_requirements(c,u,pid) if allowed(c,u,pid,'export',r['company_id'],r['category'])]
        if format=='pdf':
            data=pdf_report('Pendientes · '+p['name'],['Filtros: obra y permisos del usuario; sin fechas inventadas.',*[r['name']+' · '+r['effective_status']+' · '+r['applicability'] for r in reqs if r['effective_status'] not in ['validado','no_aplicable']],*[t['title']+' · '+(t['due'] or 'Sin fecha definida') for t in tasks if t['status'] not in ['completada','cancelada']]])
            return Response(data,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="pendientes.pdf"'})
        if format!='zip': fail(422,'Formato no disponible.')
        index={'project':{'id':pid,'name':p['name'],'code':p['code']},'generated_at':now(),'filters':'Solo documentos descargables y exportables por este usuario','documents':[],'requirements':reqs,'tasks':tasks}
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for d in docs:
                vs=rows(c,'SELECT * FROM versions WHERE document_id=? ORDER BY number',(d['id'],));entry={**d,'versions':[]}
                for v in vs:
                    fname=f"documentos/{d['id']}/v{v['number']}{Path(v['storage_key']).suffix}";z.write(FILES/v['storage_key'],fname)
                    entry['versions'].append({k:val for k,val in v.items() if k!='storage_key'}|{'path':fname,'reuse':reuse_trace(c,v['id']),'effective_status':effective_status(v,c),'reviews':rows(c,'SELECT action,reason,user_id,created_at FROM reviews WHERE version_id=?',(v['id'],))})
                    for a in rows(c,'SELECT a.* FROM signature_archives a JOIN signature_requests s ON s.id=a.request_id WHERE s.version_id=?',(v['id'],)):
                        z.write(FILES/a['storage_key'],f"firmas/{a['request_id']}/resultado-PRUEBA.pdf");z.write(FILES/a['evidence_key'],f"firmas/{a['request_id']}/evidencias-PRUEBA.json")
                index['documents'].append(entry)
            z.writestr('indice.json',js(index));z.writestr('LEEME.txt','Expediente filtrado por permisos. Firmas PRUEBA son simulaciones sin firma electrónica real. El estado documental no certifica la seguridad ni el cumplimiento legal.')
        return Response(out.getvalue(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="expediente.zip"'})

@app.get('/api/templates/{name}/draft')
def draft(name:str,request:Request,project_id:str):
    choices={'solicitud':'Solicitud de documentación','pss':'Toma de datos del PSS','recepcion':'Recepción de información preventiva','acta':'Acta de coordinación','epis':'Entrega de EPIs','designacion':'Designación','autorizacion':'Autorización','adhesion':'Conocimiento o adhesión'}
    if name not in choices: fail(404,'Plantilla no disponible.')
    with connect() as c:
        u=user(c,request);require(c,u,project_id,'manage');p=get_project(c,project_id)
        content=pdf_report('BORRADOR SIN APROBAR · '+choices[name],['Obra: '+p['name'],'Plantilla orientativa pendiente de revisión y aprobación competente.','No es un PSS revisado ni aprobado. Completar y revisar antes de utilizar.','Responsable: sin designar','Fecha del trámite: sin fecha definida','Contenido / alcance: pendiente de completar','Observaciones:','Firmantes: pendientes de designar'])
        return Response(content,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="borrador.pdf"'})

app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
@app.get('/')
def index(): return FileResponse(ROOT/'static/index.html')

@app.delete('/api/grants/{gid}')
def remove_grant(gid:str,request:Request):
    with connect() as c:
        u=user(c,request,True);require_admin(u);g=one(c,'SELECT * FROM grants WHERE id=?',(gid,))
        if not g: fail(404,'Asignación no encontrada.')
        c.execute('DELETE FROM grants WHERE id=?',(gid,));audit(c,u['id'],g['project_id'],'permiso_revocado',gid,{'user_id':g['user_id']},g['company_id']);return {'ok':True}

@app.patch('/api/grants/{gid}')
async def configure_grant(gid:str,request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);require_admin(u);g=one(c,'SELECT * FROM grants WHERE id=?',(gid,))
        if not g: fail(404,'Asignación no encontrada.')
        perms=b.get('permissions');cats=b.get('categories')
        if not isinstance(perms,list) or any(p not in ACTIONS for p in perms) or not isinstance(cats,list): fail(422,'Permisos o categorías no válidos.')
        if any(not one(c,'SELECT id FROM categories WHERE id=?',(cat,)) for cat in cats): fail(422,'Categoría no válida.')
        if g['role'] in ['empresa','firmante'] and any(p not in ROLES[g['role']]+['export'] for p in perms): fail(422,'El perfil externo no puede gestionar ni revisar.')
        if g['role'] in ['direccion','encargado'] and (any(cat in RESTRICTED for cat in cats) or 'health' in perms): fail(422,'Perfil sin acceso a categorías restringidas.')
        c.execute('UPDATE grants SET permissions=?,categories=? WHERE id=?',(js(perms),js(cats),gid));audit(c,u['id'],g['project_id'],'permisos_configurados',gid,b,g['company_id']);return {'ok':True}

@app.get('/api/tasks/{tid}/history')
def task_history(tid:str,request:Request):
    with connect() as c:
        u=user(c,request);t=one(c,'SELECT * FROM tasks WHERE id=?',(tid,))
        if not t: fail(404,'Tarea no encontrada.')
        if not visible_task(c,u,t): fail(403,'Tarea no autorizada.')
        comments=rows(c,'SELECT x.id,x.body,x.created_at,u.name AS author FROM task_comments x JOIN users u ON u.id=x.user_id WHERE x.task_id=? ORDER BY x.created_at',(tid,))
        dependencies=[]
        for dep in rows(c,'SELECT t.* FROM tasks t JOIN dependencies d ON d.depends_on=t.id WHERE d.task_id=?',(tid,)):
            if visible_task(c,u,dep): dependencies.append({'id':dep['id'],'title':dep['title'],'status':dep['status']})
            else: dependencies.append({'title':'Dependencia restringida','status':'sin_acceso'})
        return {'comments':comments,'dependencies':dependencies,'events':rows(c,"SELECT a.action,a.details,a.created_at,u.name AS author FROM audit a LEFT JOIN users u ON u.id=a.user_id WHERE a.entity_id=? AND a.action IN ('tarea_creada','tarea_actualizada') ORDER BY a.created_at",(tid,))}

@app.post('/api/tasks/{tid}/comments')
async def task_comment(tid:str,request:Request):
    b=await request.json();comment=body_text(b,'body',maxlen=4000)
    with connect() as c:
        u=user(c,request,True);t=one(c,'SELECT * FROM tasks WHERE id=?',(tid,))
        if not t: fail(404,'Tarea no encontrada.')
        cat=task_category(c,t)
        if not visible_task(c,u,t) or not (allowed(c,u,t['project_id'],'upload',t['company_id'],cat) or allowed(c,u,t['project_id'],'manage',t['company_id'],cat)):
            fail(403,'No tienes permiso para comentar este pendiente.')
        entry=insert(c,'task_comments',id=uid(),task_id=tid,user_id=u['id'],body=comment,created_at=now())
        audit(c,u['id'],t['project_id'],'comentario_tarea',entry['id'],{'task_id':tid},t['company_id'])
        return {'id':entry['id']}


@app.get('/healthz',include_in_schema=False)
def healthz():
    # Never expose user, project, credential, path or document details.
    try:
        with connect() as c:
            c.execute('SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1').fetchone()
            c.execute('SELECT id FROM users LIMIT 1').fetchone()
        return {'status':'ok'}
    except Exception:
        return JSONResponse({'status':'unavailable'},status_code=503)

@app.post('/api/people/{kind}/{ident}/assign')
async def assign_existing(kind:str,ident:str,request:Request):
    if kind not in ['workers','equipment']:fail(404,'Tipo no válido.')
    b=await request.json();pid=body_text(b,'project_id')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');u=user(c,request,True)
        entity=one(c,f'SELECT * FROM {kind} WHERE id=?',(ident,))
        if not entity:fail(404,'Ficha no encontrada.')
        cid=entity['company_id'];require(c,u,pid,'upload',cid,'prl');related_company(c,pid,cid)
        table='worker_assignments' if kind=='workers' else 'equipment_assignments'
        key='worker_id' if kind=='workers' else 'equipment_id'
        if one(c,f'SELECT {key} FROM {table} WHERE {key}=? AND project_id=?',(ident,pid)):
            return {'ok':True,'already_assigned':True}
        insert(c,table,**{key:ident,'project_id':pid});generate(c,pid)
        audit(c,u['id'],pid,'asignacion_existente_'+kind,ident,company=cid)
        return {'ok':True,'project_id':pid,'id':ident,'notice':'Asignación registrada; los requisitos documentales deben revisarse.'}

@app.post('/api/account/password')
async def change_password(request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);stored=one(c,'SELECT password FROM users WHERE id=?',(u['id'],))
        if not password_ok(password_value(b,'current_password'),stored['password']):fail(403,'La contraseña actual no es correcta.')
        new=password_value(b,'new_password')
        if new!=b.get('confirm_password'):fail(422,'La confirmación no coincide.')
        c.execute('UPDATE users SET password=? WHERE id=?',(password_hash(new),u['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],));audit(c,u['id'],None,'contrasena_modificada_sesiones_revocadas')
    response=JSONResponse({'ok':True,'notice':'Contraseña actualizada. Inicia sesión de nuevo.'});response.delete_cookie('nm_session');return response
