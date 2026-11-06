"""Delegación temporal acotada: solo incorporar documentos, nunca leer el expediente."""
import secrets,json,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from fastapi import APIRouter,Request,UploadFile,File,Form
from fastapi.responses import FileResponse
from .db import connect,one,rows,insert,uid,now,js,audit,FILES
from .security import user,require_admin,digest,fail
from .engine import generate
from .files import validate_file,store

router=APIRouter(prefix='/api',tags=['Importación privada'])
CATEGORIES={'prl','proyecto','actas','licencias','otros','laboral','economico'}
def text(b,key,required=True,limit=2000):
    value=b.get(key)
    if (value is None or value=='') and not required:return None
    if not isinstance(value,str) or not value.strip() or len(value)>limit:fail(422,'Falta o no es válido: '+key)
    return value.strip()

def delegated(c,request):
    h=request.headers.get('authorization','')
    if not h.startswith('Bearer nm_import_'):fail(401,'Autorización temporal de importación requerida.')
    g=one(c,'SELECT * FROM import_authorizations WHERE token_hash=?',(digest(h[7:]),))
    if not g or g['revoked_at'] or g['expires']<=now():fail(410,'La autorización de importación ha caducado o está revocada.')
    u=one(c,'SELECT * FROM users WHERE id=?',(g['user_id'],))
    if not u or u['disabled'] or not u['admin']:fail(403,'La cuenta que autorizó la importación ya no dispone de permiso.')
    return g,u

@router.post('/imports/authorize')
async def authorize(request:Request):
    b=await request.json()
    with connect() as c:
        u=user(c,request,True);require_admin(u)
        maximum=b.get('max_files',18)
        max_workers=b.get('max_workers',0)
        if type(max_workers)!=int or not 0<=max_workers<=500:fail(422,'Límite de trabajadores no válido.')
        if type(maximum)!=int or not 1<=maximum<=50:fail(422,'Selecciona entre 1 y 50 archivos.')
        pid=b.get('project_id') or None;cid=b.get('company_id') or None
        if pid and not one(c,'SELECT id FROM projects WHERE id=?',(pid,)):fail(404,'Obra no encontrada.')
        if cid and not one(c,'SELECT id FROM companies WHERE id=?',(cid,)):fail(404,'Empresa no encontrada.')
        token='nm_import_'+secrets.token_urlsafe(32);ident=uid()
        expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        insert(c,'import_authorizations',id=ident,token_hash=digest(token),user_id=u['id'],project_id=pid,company_id=cid,expires=expires,max_files=maximum,max_workers=max_workers,created_at=now())
        audit(c,u['id'],pid,'importacion_temporal_autorizada',ident,{'max_files':maximum,'max_workers':max_workers,'company_id':cid,'expires':expires})
        return {'id':ident,'code':token,'expires':expires,'max_files':maximum,'max_workers':max_workers}

@router.post('/imports/{ident}/revoke')
def revoke(ident:str,request:Request):
    with connect() as c:
        u=user(c,request,True);require_admin(u)
        g=one(c,'SELECT * FROM import_authorizations WHERE id=?',(ident,))
        if not g:fail(404,'Autorización no encontrada.')
        c.execute('UPDATE import_authorizations SET revoked_at=? WHERE id=?',(now(),ident));audit(c,u['id'],g['project_id'],'importacion_revocada',ident)
        return {'ok':True}

@router.post('/imports/prepare')
async def prepare(request:Request):
    b=await request.json()
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');g,u=delegated(c,request)
        p=b.get('project') or {};company_name=text(b,'company_name')
        if not g['company_id']:
            matches=[x for x in rows(c,'SELECT id,name FROM companies') if ''.join(ch for ch in x['name'].casefold() if ch.isalnum())==''.join(ch for ch in company_name.casefold() if ch.isalnum())]
            if len(matches)>1:fail(409,'Hay varias empresas coincidentes. Selecciona la empresa correcta al autorizar.')
            existing=matches[0] if matches else None
            cid=existing['id'] if existing else uid()
            if not existing:insert(c,'companies',id=cid,name=company_name,kind='con_trabajadores',details=js({'origin':'documentos_aportados','pending_confirmation':True}))
            c.execute('UPDATE import_authorizations SET company_id=? WHERE id=?',(cid,g['id']));g['company_id']=cid
        selected_company=one(c,'SELECT name FROM companies WHERE id=?',(g['company_id'],))
        normalize=lambda value:''.join(ch for ch in value.casefold() if ch.isalnum())
        if normalize(selected_company['name'])!=normalize(company_name):fail(409,'La empresa seleccionada no coincide con la indicada por los documentos. No se ha realizado la importación.')
        if not g['project_id']:
            name=text(p,'name');code=text(p,'code');municipality=text(p,'municipality')
            if one(c,'SELECT id FROM projects WHERE code=?',(code,)):fail(409,'Ya existe una obra con ese código. Autoriza una importación seleccionando la obra existente para evitar mezclar expedientes.')
            hp=p.get('has_project')
            if hp is not None and type(hp)!=bool:fail(422,'Tipo de proyecto no válido.')
            pid=uid();details={'address':text(p,'address',False),'description':text(p,'description',False),'import_proposal':p.get('proposal',{}),'import_pending_confirmation':True}
            insert(c,'projects',id=pid,name=name,code=code,municipality=municipality,has_project=None if hp is None else int(hp),details=js(details),created_at=now())
            c.execute('UPDATE import_authorizations SET project_id=? WHERE id=?',(pid,g['id']));g['project_id']=pid
            audit(c,u['id'],pid,'obra_importada_pendiente_confirmacion',pid,{'origin':'documentos_aportados'})
        if not one(c,'SELECT id FROM participations WHERE project_id=? AND company_id=?',(g['project_id'],g['company_id'])):
            insert(c,'participations',id=uid(),project_id=g['project_id'],company_id=g['company_id'],role='contratista',activity=None)
        generate(c,g['project_id'])
        return {'project_id':g['project_id'],'company_id':g['company_id'],'status':'datos_pendientes_confirmacion'}

@router.post('/imports/files')
async def import_file(request:Request,file:UploadFile=File(...),metadata:str=Form(...)):
    try:b=json.loads(metadata)
    except Exception:fail(422,'Metadatos no válidos.')
    content=await file.read(15*1024*1024+1)
    if not file.filename or Path(file.filename).suffix.lower()!='.pdf':fail(422,'La importación admite PDF.')
    scope=b.get('scope');category=b.get('category')
    if scope not in ['project','company'] or category not in CATEGORIES:fail(422,'Ámbito o categoría no admitidos.')
    raw_hash=hashlib.sha256(content).hexdigest()
    if b.get('sha256')!=raw_hash:fail(409,'La huella del original no coincide con el manifiesto de importación.')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');g,u=delegated(c,request)
        pid=g['project_id'] if scope=='project' else None;cid=g['company_id'] if scope=='company' else None
        if (scope=='project' and not pid) or (scope=='company' and not cid):fail(409,'Prepara primero el destino de esta importación.')
        prior=one(c,'SELECT * FROM imported_files WHERE scope=? AND project_id IS ? AND company_id IS ? AND raw_hash=?',(scope,pid,cid,raw_hash))
        if prior:return {'id':prior['document_id'],'version_id':prior['version_id'],'already_imported':True,'scope':scope}
        if c.execute('SELECT COUNT(*) FROM imported_files WHERE authorization_id=?',(g['id'],)).fetchone()[0]>=g['max_files']:fail(409,'La autorización ha alcanzado su límite de documentos.')
        clean,mime,ext=validate_file(content,file.filename,preserve_original=True)
        title=text(b,'title');doc_details=b.get('details') or {}
        if not isinstance(doc_details,dict):fail(422,'Detalles no válidos.')
        details=js({**doc_details,'source':'adjuntos_aportados_en_chat','metadata_pending_confirmation':True,'original_hash':raw_hash,'signature_verification':'no_realizada'})
        requirement_id=None
        if b.get('requirement_name'):
            if scope!='project' or doc_details.get('source_class')!='documento_aportado':fail(422,'Un formulario incompleto no se incorpora como evidencia de un requisito.')
            requirement=one(c,'SELECT id,category FROM requirements WHERE project_id=? AND company_id IS NULL AND worker_id IS NULL AND equipment_id IS NULL AND name=?',(pid,text(b,'requirement_name')))
            if not requirement or requirement['category']!=category:fail(422,'El requisito propuesto no pertenece al ámbito importado.')
            if not one(c,'SELECT id FROM documents WHERE requirement_id=?',(requirement['id'],)):
                requirement_id=requirement['id']
            else:
                doc_details={**doc_details,'suggested_requirement_id':requirement['id'],'requirement_link_pending_review':True}
                details=js({**doc_details,'source':'adjuntos_aportados_en_chat','metadata_pending_confirmation':True,'original_hash':raw_hash,'signature_verification':'no_realizada'})
        key,h=store(clean,ext);did=uid();vid=uid();date=now()
        if scope=='project':
            insert(c,'documents',id=did,project_id=pid,company_id=None,requirement_id=requirement_id,title=title,category=category,details=details,created_by=u['id'],created_at=date)
            insert(c,'versions',id=vid,document_id=did,number=1,storage_key=key,filename=Path(file.filename).name,mime=mime,hash=h,status='recibido',expires=None,provenance='adjunto_chat_original_sin_alterar',created_by=u['id'],created_at=date)
        else:
            insert(c,'company_archive_documents',id=did,company_id=cid,title=title,category=category,details=details,created_by=u['id'],created_at=date)
            insert(c,'company_archive_versions',id=vid,document_id=did,number=1,storage_key=key,filename=Path(file.filename).name,mime=mime,hash=h,status='recibido',provenance='adjunto_chat_original_sin_alterar',created_by=u['id'],created_at=date)
        insert(c,'imported_files',id=uid(),authorization_id=g['id'],scope=scope,project_id=pid,company_id=cid,raw_hash=raw_hash,document_id=did,version_id=vid,created_at=date)
        audit(c,u['id'],pid,'documento_importado_privado',did,{'scope':scope,'category':category,'hash':h,'authorization_id':g['id']},cid)
        return {'id':did,'version_id':vid,'scope':scope,'status':'recibido','hash':h}

@router.get('/company-archive/{cid}')
def company_archive(cid:str,request:Request):
    with connect() as c:
        u=user(c,request);require_admin(u)
        if not one(c,'SELECT id FROM companies WHERE id=?',(cid,)):fail(404,'Empresa no encontrada.')
        docs=rows(c,'SELECT * FROM company_archive_documents WHERE company_id=? ORDER BY created_at DESC',(cid,))
        for d in docs:
            d['versions']=rows(c,'SELECT id,number,filename,mime,hash,status,provenance,created_at FROM company_archive_versions WHERE document_id=? ORDER BY number DESC',(d['id'],))
        return {'documents':docs,'scope':'general_empresa','access':'solo_administracion'}

@router.get('/company-archive/versions/{vid}/file')
def company_archive_file(vid:str,request:Request):
    with connect() as c:
        u=user(c,request);require_admin(u)
        v=one(c,'SELECT v.*,d.company_id FROM company_archive_versions v JOIN company_archive_documents d ON d.id=v.document_id WHERE v.id=?',(vid,))
        if not v:fail(404,'Versión no encontrada.')
        audit(c,u['id'],None,'descarga_archivo_general_empresa',vid,company=v['company_id'])
        return FileResponse(FILES/v['storage_key'],media_type=v['mime'],filename=v['filename'])

@router.post('/imports/workers')
async def import_workers(request:Request):
    b=await request.json();entries=b.get('workers')
    if not isinstance(entries,list) or not 1<=len(entries)<=500:fail(422,'Lote de trabajadores no válido.')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');g,u=delegated(c,request)
        if not g['company_id']:fail(409,'Prepara primero la empresa de destino.')
        if not g['max_workers']:fail(403,'Esta autorización no permite importar trabajadores.')
        count=c.execute('SELECT COUNT(*) FROM imported_workers WHERE authorization_id=?',(g['id'],)).fetchone()[0]
        result=[]
        for row in entries:
            if not isinstance(row,dict):fail(422,'Fila de trabajador no válida.')
            if set(row)-{'name','trade','email','phone','active','source_row'}:fail(422,'Campos no admitidos. No se importan DNI completos, datos médicos, permisos ni geolocalización.')
            name=text(row,'name',limit=250);trade=text(row,'trade',False,limit=250)
            email=text(row,'email',False,limit=254);phone=text(row,'phone',False,limit=40)
            if email and ('@' not in email or any(ch in email for ch in '\r\n')):fail(422,'Correo de contacto no válido.')
            active=row.get('active',True)
            if type(active)!=bool:fail(422,'Estado de trabajador no válido.')
            minimal={'name':name,'trade':trade,'email':email.lower() if email else None,'phone':phone,'active':active}
            fingerprint=hashlib.sha256(json.dumps(minimal,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            previous=one(c,'SELECT worker_id FROM imported_workers WHERE company_id=? AND fingerprint=?',(g['company_id'],fingerprint))
            if previous:result.append({'id':previous['worker_id'],'already_imported':True});continue
            if count>=g['max_workers']:fail(409,'La autorización ha alcanzado su límite de trabajadores.')
            existing=one(c,'SELECT * FROM workers WHERE company_id=? AND lower(name)=lower(?)',(g['company_id'],name))
            if existing:
                result.append({'id':existing['id'],'existing_pending_review':True})
                wid=existing['id']
            else:
                wid=uid();details={k:v for k,v in minimal.items() if k not in ['name','trade']}
                details.update({'source':'listado_aportado_en_chat','source_row':row.get('source_row'),'import_pending_confirmation':True})
                insert(c,'workers',id=wid,company_id=g['company_id'],name=name,trade=trade,details=js(details))
                result.append({'id':wid,'created':True})
            insert(c,'imported_workers',id=uid(),authorization_id=g['id'],company_id=g['company_id'],worker_id=wid,fingerprint=fingerprint,created_at=now());count+=1
            audit(c,u['id'],None,'trabajador_importado_sin_asignacion',wid,{'authorization_id':g['id'],'source_row':row.get('source_row')},g['company_id'])
        return {'workers':result,'assigned_to_projects':False,'accounts_created':False}

@router.post('/imports/finish')
def finish(request:Request):
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');g,u=delegated(c,request)
        documents=c.execute('SELECT COUNT(*) FROM imported_files WHERE authorization_id=?',(g['id'],)).fetchone()[0]
        workers=c.execute('SELECT COUNT(*) FROM imported_workers WHERE authorization_id=?',(g['id'],)).fetchone()[0]
        c.execute('UPDATE import_authorizations SET revoked_at=? WHERE id=?',(now(),g['id']))
        audit(c,u['id'],g['project_id'],'importacion_completada_y_revocada',g['id'],{'documents':documents,'workers':workers},g['company_id'])
        return {'documents':documents,'workers':workers,'authorization_closed':True,'project_id':g['project_id'],'company_id':g['company_id']}
