"""Reglas orientativas versionadas: nunca se declaran verificadas sin aprobación expresa."""
import json
from datetime import date, timedelta
from .db import *
from .security import allowed,grants
from .document_state import base_status,effective_version_status
PHASES=['Preparación y toma de datos','Proyecto, licencias y permisos','Preparación del inicio y PRL','En ejecución','Remates y documentación final','Pendiente de cierre','Cerrada']
CATEGORIES={'prl':'PRL y coordinación','proyecto':'Proyecto y planos','licencias':'Licencias y permisos','actas':'Actas e incidencias','calidad':'Calidad y certificados','final':'Final de obra','fotografias':'Fotografías','otros':'Otros documentos','salud':'Conclusiones de aptitud (restringido)','laboral':'Administrativa laboral (restringido)','economico':'Documentación económica','bancario':'Datos bancarios'}
# scope, condition, names. Each is a candidate, applicability must be resolved by competent reviewer.
CATALOG=[
 ('obra','con_proyecto','Toma de datos para elaboración del PSS|Estudio o estudio básico de seguridad y salud|Plan de seguridad y salud|Aprobación expresa del PSS|Anexos, modificaciones y aprobaciones del PSS'),
 ('obra','sin_proyecto','Evaluación de riesgos o documento de gestión preventiva'),
 ('obra','siempre','Comunicación de apertura y justificante|Designación de coordinador|Designación y acreditación de recurso preventivo|Organización de emergencias|Información e instrucciones preventivas|Actas y registros de coordinación|Libro de subcontratación: documentación|Libro de incidencias: referencias y copias autorizadas'),
 ('empresa','ejecuta','Identificación y contactos|Actividad y alcance contratado|Cadena de contratación|Modalidad preventiva|Evaluación de riesgos y planificación de los trabajos|Inscripción REA|Relación de trabajadores asignados|Riesgos introducidos en la obra|Recepción de instrucciones preventivas|Actas de coordinación|Conocimiento o adhesión al PSS'),
 ('empresa','suministro','Instrucciones de entrega y descarga|Identificación y contacto de suministro'),
 ('empresa','autonomo','Identificación y actividad del autónomo|Riesgos de la actividad del autónomo|Recepción de instrucciones del autónomo'),
 ('empresa','ejecuta','Seguro de responsabilidad civil (contractual, si se exige)|Acreditaciones laborales y de Seguridad Social minimizadas'),
 ('trabajador','siempre','Identificación mínima y empresa empleadora|Oficio, funciones y asignaciones|Formación preventiva aplicable|Información sobre riesgos y medidas de la obra|Entrega de EPIs|Autorizaciones de uso de equipos|Conclusión de aptitud para el puesto|Recepción de instrucciones y firmas individuales'),
 ('equipo','siempre','Identificación, titular y empresa usuaria|Conformidad aplicable al equipo y antigüedad|Manual o instrucciones|Revisiones, mantenimiento e inspecciones|Operadores autorizados y formación'),
 ('equipo','montaje','Montaje, instalación o puesta en servicio'),
]
def seed_catalog(c):
    for k,v in CATEGORIES.items(): c.execute('INSERT OR IGNORE INTO categories VALUES(?,?,?)',(k,v,int(k in ['salud','laboral','economico','bancario'])))
    index=0
    for scope,condition,names in CATALOG:
        for name in names.split('|'):
            index+=1; rid=f'base-{index:03}'
            cat='salud' if name=='Conclusión de aptitud para el puesto' else 'laboral' if name.startswith('Acreditaciones laborales') else 'prl'
            details={'explanation':'Evaluar según actividad, riesgos, funciones y condiciones concretas. No constituye una obligación confirmada.','validity':'Sin caducidad automática. Definir con el responsable competente.','contributor':'Entidad afectada','internal_owner':'Sin designar','reviewer':'Responsable competente por designar','signature_required':False,'source_status':'Referencias localizadas el 2026-11-05; aplicación concreta pendiente de revisión competente','sources_to_verify':['https://www.boe.es/buscar/act.php?id=BOE-A-1997-22614','https://www.boe.es/buscar/act.php?id=BOE-A-2004-1848','https://www.insst.es/materias/sectores-de-actividad/construccion/faq','https://www.caib.es/seucaib/es/tramites/tramite/574008/'],'equipment_type':'según tipo y antigüedad','company_reusable':scope=='empresa' and name in ['Identificación y contactos','Modalidad preventiva','Inscripción REA','Seguro de responsabilidad civil (contractual, si se exige)']}
            c.execute('INSERT OR IGNORE INTO rule_templates(id,version,name,scope,category,condition,details) VALUES(?,?,?,?,?,?,?)',(rid,1,name,scope,cat,condition,js(details)))

def matches(rule,p,entity):
    if 'PSS' in rule['name'] and p['has_project']!=1: return False
    condition=rule['condition']
    if condition=='con_proyecto': return p['has_project']==1
    if condition=='sin_proyecto': return p['has_project']==0
    if condition=='suministro': return entity.get('role')=='suministro'
    if condition=='autonomo': return entity.get('kind')=='autonomo' and entity.get('role')!='suministro'
    if condition=='ejecuta': return entity.get('role') in ['subcontrata','instalador','contratista'] and entity.get('kind')!='autonomo'
    if condition=='montaje': return entity.get('kind') in ['andamio','plataforma','elevacion']
    return condition=='siempre'

def generate(c,pid):
    p=one(c,'SELECT * FROM projects WHERE id=?',(pid,))
    entities=[('obra',{'company_id':None,'worker_id':None,'equipment_id':None})]
    for e in rows(c,'SELECT x.*,c.kind FROM participations x JOIN companies c ON c.id=x.company_id WHERE project_id=?',(pid,)):
        entities.append(('empresa',{**e,'worker_id':None,'equipment_id':None}))
    for e in rows(c,'SELECT w.* FROM workers w JOIN worker_assignments a ON a.worker_id=w.id WHERE a.project_id=?',(pid,)):
        entities.append(('trabajador',{**e,'worker_id':e['id'],'equipment_id':None}))
    for e in rows(c,'SELECT e.* FROM equipment e JOIN equipment_assignments a ON a.equipment_id=e.id WHERE a.project_id=?',(pid,)):
        entities.append(('equipo',{**e,'equipment_id':e['id'],'worker_id':None}))
    for r in rows(c,'SELECT * FROM rule_templates'):
        for scope,e in entities:
            if scope!=r['scope'] or not matches(r,p,e): continue
            args=(pid,e.get('company_id'),e.get('worker_id'),e.get('equipment_id'),r['id'])
            if one(c,'SELECT id FROM requirements WHERE project_id=? AND company_id IS ? AND worker_id IS ? AND equipment_id IS ? AND rule_id=?',args): continue
            rid=uid()
            insert(c,'requirements',id=rid,project_id=pid,company_id=e.get('company_id'),worker_id=e.get('worker_id'),equipment_id=e.get('equipment_id'),rule_id=r['id'],rule_version=r['version'],name=r['name'],category=r['category'],snapshot=js(r),blocking=r['blocking'],applicability='aplica' if r['approved_by'] else 'pendiente_revision')
            insert(c,'tasks',id=uid(),project_id=pid,company_id=e.get('company_id'),requirement_id=rid,title=('Aportar: ' if r['approved_by'] else 'Resolver aplicabilidad: ')+r['name'],origin='requisito',priority='alta' if r['blocking'] else 'normal')

def effective_status(v,c=None):
    return effective_version_status(c,v) if c is not None else base_status(v)
def req_status(c,r):
    if r['status']=='no_aplicable': return 'no_aplicable'
    d=one(c,'SELECT v.* FROM documents d JOIN versions v ON v.document_id=d.id WHERE d.requirement_id=? ORDER BY v.created_at DESC,v.number DESC LIMIT 1',(r['id'],))
    return effective_status(d,c)
def visible_requirements(c,u,pid):
    result=[]
    for r in rows(c,'SELECT * FROM requirements WHERE project_id=?',(pid,)):
        if allowed(c,u,pid,'read',r['company_id'],r['category']): result.append({**r,'effective_status':req_status(c,r)})
    return result

def health(c,u,p):
    reqs=visible_requirements(c,u,p['id']); causes=[]; state='verde'
    global_operational=u['admin'] or any(g['company_id'] is None and g['role'] in ['gestor','encargado'] and 'read' in json.loads(g['permissions']) for g in grants(c,u,p['id']))
    if global_operational:
        reqs=[]
        for r in rows(c,'SELECT * FROM requirements WHERE project_id=?',(p['id'],)):
            visible=allowed(c,u,p['id'],'read',r['company_id'],r['category'])
            reqs.append({**r,'name':r['name'] if visible else 'Requisito de acceso restringido','effective_status':req_status(c,r)})
    unresolved=p['has_project'] is None
    for r in reqs:
        if r['effective_status']=='no_aplicable': continue
        if r['applicability']=='pendiente_revision': unresolved=True; causes.append('Resolver aplicabilidad: '+r['name']); continue
        if r['effective_status']!='validado':
            causes.append(r['name']+' · '+r['effective_status'])
            if r['blocking']: state='rojo'
            elif state!='rojo': state='ambar'
        else:
            v=one(c,'SELECT v.expires FROM versions v JOIN documents d ON d.id=v.document_id WHERE d.requirement_id=? ORDER BY v.created_at DESC LIMIT 1',(r['id'],))
            if v and v['expires'] and v['expires']<=(date.today()+timedelta(days=30)).isoformat():
                if state=='verde': state='ambar'
                causes.append('Próximo vencimiento: '+r['name'])
    if state!='rojo' and (unresolved or not reqs): state='gris'
    return {'color':state,'causes':causes,'critical':sum(r['blocking'] and r['applicability']=='aplica' and r['effective_status'] not in ['validado','no_aplicable'] for r in reqs),'total':len(reqs),'complete':sum(r['effective_status'] in ['validado','no_aplicable'] for r in reqs)}
