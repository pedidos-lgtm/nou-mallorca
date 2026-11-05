"""Biblioteca explícita de documentos generales de empresa y aplicaciones por obra."""
from pathlib import Path
import hashlib,json
from fastapi import APIRouter,Request
from fastapi.responses import FileResponse
from .db import connect,one,rows,insert,audit,uid,now,FILES,js
from .security import user,require,document_access,allowed,fail,RESTRICTED
from .document_state import library_status,reuse_trace
from .files import store

router=APIRouter(prefix='/api/library',tags=['Biblioteca de empresa'])

def text(body,name):
    value=body.get(name)
    if not isinstance(value,str) or not value.strip() or len(value)>2000: fail(422,'Falta o no es válido: '+name)
    return value.strip()

def item_get(c,lid):
    item=one(c,'SELECT * FROM company_library WHERE id=?',(lid,))
    if not item: fail(404,'Documento general no encontrado.')
    return item

def authorize_target(c,u,item,pid,action):
    if not one(c,'SELECT id FROM participations WHERE project_id=? AND company_id=?',(pid,item['company_id'])):
        fail(403,'La empresa no participa en esta obra.')
    require(c,u,pid,action,item['company_id'],item['category'])

@router.post('')
async def publish(request:Request):
    b=await request.json()
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');u=user(c,request,True)
        v=one(c,'SELECT * FROM versions WHERE id=?',(text(b,'version_id'),))
        if not v: fail(404,'Versión no encontrada.')
        d=one(c,'SELECT * FROM documents WHERE id=?',(v['document_id'],))
        document_access(c,u,d,'validate');document_access(c,u,d,'download')
        if b.get('general_scope_confirmed') is not True: fail(422,'Confirma expresamente que el documento es general de empresa, sin información específica de obra.')
        category=one(c,'SELECT sensitive FROM categories WHERE id=?',(d['category'],))
        if not d['company_id'] or d.get('worker_id') or d['category'] in RESTRICTED or not category or category['sensitive']:
            fail(422,'Solo se puede publicar documentación general de empresa sin datos restringidos o de trabajadores.')
        r=one(c,'SELECT * FROM requirements WHERE id=?',(d['requirement_id'],)) if d['requirement_id'] else None
        if r and (r['worker_id'] or r['equipment_id'] or json.loads(r['snapshot']).get('scope')!='empresa'):
            fail(422,'El requisito no corresponde al ámbito general de empresa.')
        if r:
            snapshot=json.loads(r['snapshot'])
            policy=snapshot.get('details',{})
            if isinstance(policy,str): policy=json.loads(policy)
            if policy.get('company_reusable') is not True:
                fail(422,'La regla conservada no autoriza reutilización general: conserva el ámbito de esta obra. No se publican adhesiones, instrucciones, asignaciones ni alcances específicos.')
        if one(c,'SELECT id FROM document_reuse WHERE target_document_id=?',(d['id'],)):
            fail(422,'Publica desde el documento de origen, no desde una copia reutilizada.')
        if one(c,'SELECT id FROM signature_requests WHERE version_id=?',(v['id'],)):
            fail(422,'Las solicitudes y firmas de obra no se publican como documentación general.')
        temporary={'revoked_at':None,'source_version_id':v['id']}
        if library_status(c,temporary)!='validado': fail(409,'Publica una versión vigente y validada.')
        reason=text(b,'reason')
        existing=one(c,'SELECT * FROM company_library WHERE source_version_id=?',(v['id'],))
        if existing:
            if existing['revoked_at']: fail(409,'Esta publicación fue revocada. Aporta y revisa una nueva versión para publicarla.')
            return {'id':existing['id'],'already_published':True}
        item=insert(c,'company_library',id=uid(),company_id=d['company_id'],source_version_id=v['id'],category=d['category'],title=d['title'],rule_id=r['rule_id'] if r else None,reason=reason,published_by=u['id'],published_at=now())
        audit(c,u['id'],d['project_id'],'documento_general_publicado',item['id'],{'source_version_id':v['id'],'reason':reason},d['company_id'])
        return {'id':item['id']}

@router.get('')
def listing(request:Request,project_id:str,company_id:str):
    with connect() as c:
        u=user(c,request)
        if not one(c,'SELECT id FROM participations WHERE project_id=? AND company_id=?',(project_id,company_id)): fail(403,'Participación no autorizada.')
        # A read grant for one category must not expose another category's library.
        if not u['admin'] and not any(allowed(c,u,project_id,'read',company_id,x['category']) for x in rows(c,'SELECT DISTINCT category FROM company_library WHERE company_id=?',(company_id,))):
            require(c,u,project_id,'read',company_id,'prl')
        result=[]
        for item in rows(c,'SELECT * FROM company_library WHERE company_id=? ORDER BY published_at DESC',(company_id,)):
            if not allowed(c,u,project_id,'read',company_id,item['category']): continue
            v=one(c,'SELECT number,hash,expires FROM versions WHERE id=?',(item['source_version_id'],))
            result.append({k:item[k] for k in ['id','title','company_id','category','rule_id','published_at']}|{'source_version':v['number'],'hash':v['hash'],'expires':v['expires'],'effective_status':library_status(c,item),'available':library_status(c,item)=='validado'})
        return {'items':result}

@router.get('/{lid}/file')
def download(lid:str,request:Request,project_id:str):
    with connect() as c:
        u=user(c,request);item=item_get(c,lid);authorize_target(c,u,item,project_id,'read');authorize_target(c,u,item,project_id,'download')
        if item['revoked_at']: fail(410,'La publicación ha sido revocada.')
        v=one(c,'SELECT * FROM versions WHERE id=?',(item['source_version_id'],))
        audit(c,u['id'],project_id,'consulta_documento_general',lid,company=item['company_id'])
        return FileResponse(FILES/v['storage_key'],media_type=v['mime'],filename=v['filename'])

@router.post('/{lid}/apply')
async def apply(lid:str,request:Request):
    b=await request.json();pid=text(b,'project_id');rid=b.get('requirement_id')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');u=user(c,request,True);item=item_get(c,lid)
        authorize_target(c,u,item,pid,'read');authorize_target(c,u,item,pid,'upload');authorize_target(c,u,item,pid,'download')
        if library_status(c,item)!='validado': fail(409,'El documento de origen no está vigente, ha sido sustituido o su publicación está revocada.')
        r=one(c,'SELECT * FROM requirements WHERE id=?',(rid,)) if rid else None
        if rid and (not r or r['project_id']!=pid or r['company_id']!=item['company_id'] or r['worker_id'] or r['equipment_id'] or r['category']!=item['category']):
            fail(422,'El requisito no corresponde a esta empresa, categoría y obra.')
        if r and item['rule_id'] and r['rule_id']!=item['rule_id']: fail(422,'El documento general corresponde a otro tipo de requisito.')
        existing=one(c,'''SELECT r.target_document_id,r.target_version_id FROM document_reuse r
            JOIN documents d ON d.id=r.target_document_id WHERE r.library_id=? AND d.project_id=?
            AND r.requirement_id IS ?''',(lid,pid,rid))
        if existing: return {'id':existing['target_document_id'],'version_id':existing['target_version_id'],'already_applied':True}
        if rid and one(c,'SELECT id FROM documents WHERE requirement_id=?',(rid,)): fail(409,'El requisito ya tiene un documento. Revisa su versión antes de sustituirlo.')
        source=one(c,'SELECT * FROM versions WHERE id=?',(item['source_version_id'],))
        raw=(FILES/source['storage_key']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source['hash']: fail(409,'La integridad del documento de origen no coincide. No se ha aplicado.')
        reason=text(b,'reason');did=uid();vid=uid();key,h=store(raw,Path(source['storage_key']).suffix)
        insert(c,'documents',id=did,project_id=pid,company_id=item['company_id'],requirement_id=rid,title=item['title'],category=item['category'],details=js({'scope':'company_general_application'}),created_by=u['id'],created_at=now())
        insert(c,'versions',id=vid,document_id=did,number=1,storage_key=key,filename=source['filename'],mime=source['mime'],hash=h,status='recibido',expires=source['expires'],provenance='biblioteca_empresa',created_by=u['id'],created_at=now())
        insert(c,'document_reuse',id=uid(),library_id=lid,target_document_id=did,target_version_id=vid,requirement_id=rid,applied_by=u['id'],applied_at=now(),reason=reason)
        audit(c,u['id'],pid,'documento_general_aplicado',did,{'library_id':lid,'source_hash':h,'reason':reason},item['company_id'])
        return {'id':did,'version_id':vid,'status':'recibido','notice':'Pendiente de revisión en esta obra. No hereda firmas ni aprobación técnica.'}

@router.post('/{lid}/revoke')
async def revoke(lid:str,request:Request):
    b=await request.json();reason=text(b,'reason')
    with connect() as c:
        c.execute('BEGIN IMMEDIATE');u=user(c,request,True);item=item_get(c,lid)
        source=one(c,'SELECT d.* FROM documents d JOIN versions v ON v.document_id=d.id WHERE v.id=?',(item['source_version_id'],))
        document_access(c,u,source,'validate')
        if item['revoked_at']: return {'ok':True}
        c.execute('UPDATE company_library SET revoked_at=?,revoked_by=?,revoke_reason=? WHERE id=?',(now(),u['id'],reason,lid))
        audit(c,u['id'],source['project_id'],'documento_general_revocado',lid,{'reason':reason},item['company_id'])
        for d in rows(c,'SELECT d.* FROM documents d JOIN document_reuse r ON r.target_document_id=d.id WHERE r.library_id=?',(lid,)):
            audit(c,u['id'],d['project_id'],'origen_documental_revocado',d['id'],{'library_id':lid,'reason':reason},item['company_id'])
        return {'ok':True}
