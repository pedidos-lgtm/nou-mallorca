import os, tempfile, unittest, json, io, zipfile, secrets
from pathlib import Path
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='nm-tests-')
os.environ['APP_ENV']='test'
from fastapi.testclient import TestClient
from app.main import app,run_alerts
from app.db import *
from app.security import password_hash,ROLES,SAFE_CATEGORIES
from app.files import pdf_report
from app.engine import generate,seed_catalog

class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context=TestClient(app); cls.context.__enter__()
    @classmethod
    def tearDownClass(cls): cls.context.__exit__(None,None,None)
    def setUp(self):
        # Isolated fresh DB for every acceptance case.
        with connect() as c:
            tables=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            c.execute('PRAGMA foreign_keys=OFF')
            for t in tables: c.execute(f'DELETE FROM {t}')
            c.commit();c.execute('PRAGMA foreign_keys=ON');seed_catalog(c)
            self.admin=uid();insert(c,'users',id=self.admin,email='admin@example.test',name='Admin de prueba',password=password_hash('Password-test-1234'),admin=1)
        self.a=self.client('admin@example.test')
        self.p=self.post('/projects',{'name':'Obra ficticia','code':'TEST-1','has_project':True},self.a)['id']
        self.ca=self.post('/companies',{'project_id':self.p,'name':'Empresa A ficticia','kind':'con_trabajadores','role':'subcontrata'},self.a)['id']
        self.cb=self.post('/companies',{'project_id':self.p,'name':'Empresa B ficticia','kind':'con_trabajadores','role':'subcontrata'},self.a)['id']
        self.ua=self.add_user('a@example.test','empresa',self.ca)
        self.ub=self.add_user('b@example.test','empresa',self.cb)
        self.ea=self.client('a@example.test');self.eb=self.client('b@example.test')
    def client(self,email):
        c=TestClient(app);r=c.post('/api/login',json={'email':email,'password':'Password-test-1234'});self.assertEqual(r.status_code,200,r.text);c.headers['X-CSRF-Token']=r.json()['user']['csrf'];return c
    def add_user(self,email,role,cid=None,cats=None,perms=None):
        with connect() as c:
            i=uid();insert(c,'users',id=i,email=email,name=email,password=password_hash('Password-test-1234'))
            insert(c,'grants',id=uid(),user_id=i,project_id=self.p,company_id=cid,role=role,categories=js(cats or SAFE_CATEGORIES),permissions=js(perms or ROLES[role]));return i
    def post(self,path,b,client):
        r=client.post('/api'+path,json=b);self.assertEqual(r.status_code,200,r.text);return r.json()
    def upload(self,cid=None,client=None,rid=None,did=None,cat='prl',expires=None,external=False):
        b={'project_id':self.p,'company_id':cid,'requirement_id':rid,'document_id':did,'category':cat,'title':'Documento ficticio','expires':expires,'validity_reason':'Vigencia explícita del documento de prueba' if expires else None,'external_signed':external,'external_source':'correo manual' if external else None}
        r=(client or self.a).post('/api/documents',data={'metadata':js(b)},files={'file':('test.pdf',pdf_report('Prueba ficticia',['Sin datos reales']),'application/pdf')});self.assertEqual(r.status_code,200,r.text);return r.json()
    def req(self,cid=None):
        return next(r for r in self.a.get('/api/projects/'+self.p).json()['requirements'] if r['company_id']==cid and r['category']=='prl')
    def health(self): return self.a.get('/api/dashboard').json()['projects'][0]['health']
    def signature(self,vid,users=None):return self.post('/signatures',{'version_id':vid,'mode':'paralela','signers':[{'user_id':u,'function':'Representante de prueba'} for u in (users or [self.ua])]},self.a)
    def sign(self,s,client=None):
        token=s['links'][0]['link'].split('/')[-1];return self.post('/sign/'+token,{'consent':True},client or self.ea)
    def test_company_isolation_known_url_and_ids(self):
        d=self.upload(self.ca,self.ea)
        self.assertEqual(self.eb.get('/api/versions/'+d['version_id']+'/file').status_code,403)
        visible=self.eb.get('/api/dashboard').json()
        self.assertNotIn(d['id'],[x['id'] for x in visible['documents']])
        r=self.eb.post('/api/documents',data={'metadata':js({'project_id':self.p,'company_id':self.ca,'title':'Ataque','category':'prl'})},files={'file':('x.pdf',b'%PDF','application/pdf')})
        self.assertEqual(r.status_code,403)
    def test_external_cannot_escalate_permissions(self):
        r=self.ea.post('/api/invitations',json={'project_id':self.p,'email':'evil@example.test','name':'Evil','role':'gestor'})
        self.assertEqual(r.status_code,403)
        self.assertEqual(self.ea.post('/api/rules',json={'name':'Rule'}).status_code,403)
        self.assertEqual(self.ea.post('/api/projects',json={'name':'X','code':'X'}).status_code,403)
    def test_no_project_does_not_get_pss(self):
        p=self.post('/projects',{'name':'Sin proyecto','code':'NO-P','has_project':False},self.a)
        self.post('/companies',{'project_id':p['id'],'name':'Sin proyecto ejecutora','kind':'con_trabajadores','role':'subcontrata'},self.a)
        reqs=self.a.get('/api/projects/'+p['id']).json()['requirements']
        self.assertFalse(any('PSS' in r['name'] for r in reqs));self.assertTrue(any('gestión preventiva' in r['name'] for r in reqs))
    def test_distinct_supply_autonomous_and_employee_requirements(self):
        supply=self.post('/companies',{'project_id':self.p,'name':'Suministro ficticio','kind':'suministro','role':'suministro'},self.a)['id']
        auto=self.post('/companies',{'project_id':self.p,'name':'Autónomo ficticio','kind':'autonomo','role':'subcontrata'},self.a)['id']
        reqs=self.a.get('/api/projects/'+self.p).json()['requirements'];names=lambda cid:[r['name'] for r in reqs if r['company_id']==cid]
        self.assertEqual(len(names(supply)),2);self.assertFalse(any('REA' in n for n in names(auto)));self.assertTrue(any('REA' in n for n in names(self.ca)))
    def test_upload_does_not_validate(self):
        d=self.upload(self.ca,self.ea)
        with connect() as c:self.assertEqual(one(c,'SELECT status FROM versions WHERE id=?',(d['version_id'],))['status'],'recibido')
    def test_signature_not_validation_or_approval_and_archive_idempotent(self):
        d=self.upload(self.ca,self.ea);s=self.signature(d['version_id']);self.sign(s);self.sign(s)
        self.post('/signatures/'+s['id']+'/retry-archive',{},self.a)
        with connect() as c:
            self.assertEqual(one(c,'SELECT status FROM versions WHERE id=?',(d['version_id'],))['status'],'recibido')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM signature_archives').fetchone()[0],1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM audit WHERE action='firma_prueba_archivada'").fetchone()[0],1)
        self.assertEqual(self.ea.get('/api/signatures/'+s['id']+'/archive').status_code,200)
    def test_expiry_recalculates_and_critical_overrides(self):
        r=self.req(self.ca);self.post('/requirements/'+r['id'],{'action':'aplica','blocking':True,'reason':'Condición interna ficticia'},self.a)
        d=self.upload(self.ca,self.ea,rid=r['id'],expires='2020-01-01')
        self.post('/versions/'+d['version_id']+'/review',{'action':'validado','reason':'Revisado para prueba'},self.a)
        self.assertEqual(self.health()['color'],'rojo')
        req=self.a.get('/api/projects/'+self.p).json()['requirements'];self.assertEqual(next(x for x in req if x['id']==r['id'])['effective_status'],'caducado')
    def test_new_version_preserves_old_and_no_inherited_signatures(self):
        d=self.upload(self.ca,self.ea);s=self.signature(d['version_id']);self.sign(s)
        d2=self.upload(self.ca,self.ea,did=d['id'])
        with connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM versions WHERE document_id=?',(d['id'],)).fetchone()[0],2)
            self.assertFalse(one(c,'SELECT id FROM signature_requests WHERE version_id=?',(d2['version_id'],)))
        self.assertEqual(self.ea.get('/api/versions/'+d['version_id']+'/file').status_code,200)
    def test_revoked_and_expired_signature_links(self):
        d=self.upload(self.ca,self.ea);s=self.signature(d['version_id']);token=s['links'][0]['link'].split('/')[-1]
        self.post('/signatures/'+s['id']+'/cancel',{},self.a);self.assertEqual(self.ea.get('/api/sign/'+token).status_code,410)
        s2=self.signature(d['version_id']);token=s2['links'][0]['link'].split('/')[-1]
        with connect() as c:c.execute("UPDATE signature_requests SET expires='2000' WHERE id=?",(s2['id'],))
        self.assertEqual(self.ea.get('/api/sign/'+token).status_code,410)
    def test_link_cannot_impersonate_signer(self):
        d=self.upload(self.ca,self.ea);s=self.signature(d['version_id']);token=s['links'][0]['link'].split('/')[-1]
        self.assertEqual(self.eb.get('/api/sign/'+token).status_code,403)
        self.assertEqual(TestClient(app).get('/api/sign/'+token).status_code,401)
    def test_manual_share_not_delivery(self):
        d=self.upload(self.ca,self.ea);s=self.signature(d['version_id'])
        with connect() as c:self.assertFalse(one(c,"SELECT id FROM audit WHERE action='envio_confirmado_usuario'"))
        self.post('/signatures/'+s['id']+'/confirm-sent',{},self.a)
        with connect() as c:
            a=one(c,"SELECT * FROM audit WHERE action='envio_confirmado_usuario'");self.assertFalse(json.loads(a['details'])['delivery_verified'])
    def test_external_signature_provenance_not_evidence(self):
        d=self.upload(self.ca,self.ea,external=True)
        with connect() as c:
            v=one(c,'SELECT * FROM versions WHERE id=?',(d['version_id'],));self.assertEqual(v['status'],'recibido');self.assertEqual(v['provenance'],'externo: correo manual');self.assertFalse(one(c,'SELECT * FROM signature_archives'))
    def test_direction_categories_and_other_project_denied(self):
        self.add_user('df@example.test','direccion',cats=['proyecto']);df=self.client('df@example.test')
        plan=self.upload(cat='proyecto');prl=self.upload(cat='prl')
        self.assertEqual(df.get('/api/versions/'+plan['version_id']+'/file').status_code,200)
        self.assertEqual(df.get('/api/versions/'+prl['version_id']+'/file').status_code,403)
        p2=self.post('/projects',{'name':'Otra','code':'OTHER'},self.a)
        self.assertEqual(df.get('/api/projects/'+p2['id']).status_code,403)
    def test_foreman_medical_denied(self):
        self.add_user('foreman@example.test','encargado',cats=['*']);f=self.client('foreman@example.test');d=self.upload(cat='salud')
        self.assertEqual(f.get('/api/versions/'+d['version_id']+'/file').status_code,403)
        self.assertEqual(f.get('/api/dashboard').json()['documents'],[])
    def test_export_filters_company_health_and_download_permission(self):
        d1=self.upload(self.ca);d2=self.upload(self.cb);medical=self.upload(self.ca,cat='salud')
        with connect() as c:c.execute('UPDATE grants SET permissions=? WHERE user_id=?',(js(ROLES['empresa']+['export']),self.ua))
        r=self.ea.get('/api/projects/'+self.p+'/export');self.assertEqual(r.status_code,200)
        z=zipfile.ZipFile(io.BytesIO(r.content));idx=json.loads(z.read('indice.json'));ids=[d['id'] for d in idx['documents']]
        self.assertEqual(ids,[d1['id']]);self.assertNotIn(d2['id'],ids);self.assertNotIn(medical['id'],ids)
    def test_alerts_no_duplicates(self):
        self.upload(self.ca,expires='2020-01-01');a=self.post('/alerts/run',{},self.a);b=self.post('/alerts/run',{},self.a)
        self.assertGreater(a['created'],0);self.assertEqual(b['created'],0)
    def test_pipeline_move_preserves_requirements_and_pause_phase(self):
        before=len(self.a.get('/api/projects/'+self.p).json()['requirements'])
        self.assertEqual(self.a.patch('/api/projects/'+self.p,json={'phase':3}).status_code,409)
        r=self.a.patch('/api/projects/'+self.p,json={'phase':3,'exception_reason':'Excepción ficticia autorizada para prueba'});self.assertEqual(r.status_code,200,r.text)
        self.a.patch('/api/projects/'+self.p,json={'paused':True,'pause_reason':'Prueba'})
        p=self.a.get('/api/projects/'+self.p).json();self.assertEqual(p['phase'],3);self.assertEqual(len(p['requirements']),before);self.assertEqual(p['paused'],1)
    def test_task_completion_does_not_validate_requirement(self):
        r=self.req(self.ca)
        with connect() as c:t=one(c,'SELECT * FROM tasks WHERE requirement_id=?',(r['id'],))
        self.assertEqual(self.a.patch('/api/tasks/'+t['id'],json={'status':'completada'}).status_code,200)
        with connect() as c:self.assertEqual(one(c,'SELECT status FROM requirements WHERE id=?',(r['id'],))['status'],'pendiente')
    def test_generation_idempotent_and_template_snapshots(self):
        before=self.a.get('/api/projects/'+self.p).json()['requirements'];r=before[0]
        self.post('/rules/'+r['rule_id'],{'source':'Fuente ficticia para prueba','reason':'Revisión de prueba','blocking':True},self.a)
        self.post('/projects/'+self.p+'/generate',{},self.a);after_=self.a.get('/api/projects/'+self.p).json()['requirements']
        self.assertEqual(len(before),len(after_));self.assertEqual(next(x for x in after_ if x['id']==r['id'])['snapshot'],r['snapshot'])
    def test_reject_requires_reason_and_approve_requires_validation(self):
        d=self.upload(self.ca,self.ea)
        self.assertEqual(self.a.post('/api/versions/'+d['version_id']+'/review',json={'action':'rechazado'}).status_code,422)
        self.assertEqual(self.a.post('/api/versions/'+d['version_id']+'/review',json={'action':'aprobado','reason':'Prueba'}).status_code,409)
        self.assertEqual(self.ea.post('/api/versions/'+d['version_id']+'/review',json={'action':'validado','reason':'Auto-validar'}).status_code,403)
    def test_invitation_single_use_expired_revoked(self):
        i=self.post('/invitations',{'project_id':self.p,'company_id':self.ca,'name':'Responsable ficticio','email':'new@example.test','role':'empresa'},self.a);token=i['link'].split('/')[-1]
        guest=TestClient(app);r=guest.post('/api/invitations/'+token+'/accept',json={'password':'Password-new-12345'});self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(guest.post('/api/invitations/'+token+'/accept',json={'password':'Password-new-12345'}).status_code,410)
        i2=self.post('/invitations',{'project_id':self.p,'company_id':self.ca,'name':'Revocado','email':'revoke@example.test','role':'empresa'},self.a)
        self.post('/invitations/'+i2['id']+'/revoke',{},self.a);self.assertEqual(guest.get('/api/invitations/'+i2['link'].split('/')[-1]).status_code,410)
    def test_csrf_and_malicious_file_rejected(self):
        token=self.a.headers.pop('X-CSRF-Token');r=self.a.post('/api/categories',json={'name':'Ataque'});self.assertEqual(r.status_code,403);self.a.headers['X-CSRF-Token']=token
        r=self.a.post('/api/documents',data={'metadata':js({'project_id':self.p,'category':'prl','title':'Malware'})},files={'file':('x.html',b'<script>alert(1)</script>','text/html')});self.assertEqual(r.status_code,422)
    def test_coherent_dashboard_project_export(self):
        r=self.req(self.ca);self.post('/requirements/'+r['id'],{'action':'aplica','blocking':True,'reason':'Regla interna de prueba'},self.a)
        p=self.a.get('/api/projects/'+self.p).json();dash=self.a.get('/api/dashboard').json();self.assertEqual(p['health'],dash['projects'][0]['health'])
        z=zipfile.ZipFile(io.BytesIO(self.a.get('/api/projects/'+self.p+'/export').content));self.assertEqual(len(json.loads(z.read('indice.json'))['requirements']),len(p['requirements']))
    def test_sequential_signature_enforces_order(self):
        d=self.upload(self.ca);s=self.post('/signatures',{'version_id':d['version_id'],'mode':'secuencial','signers':[{'user_id':self.ua,'function':'Primero'},{'user_id':self.admin,'function':'Segundo'}]},self.a)
        token=s['links'][1]['link'].split('/')[-1];self.assertEqual(self.a.post('/api/sign/'+token,json={'consent':True}).status_code,409)
        self.sign(s);self.assertEqual(self.a.post('/api/sign/'+token,json={'consent':True}).status_code,200)
    def test_reminder_deduplicated(self):
        d=self.upload(self.ca);s=self.signature(d['version_id']);self.post('/signatures/'+s['id']+'/remind',{},self.a);self.post('/signatures/'+s['id']+'/remind',{},self.a)
        with connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],1)

    def test_signer_only_sees_assigned_document_version(self):
        user_id=self.add_user('signer@example.test','firmante',self.ca)
        f=self.client('signer@example.test')
        d=self.upload(self.ca);v2=self.upload(self.ca,did=d['id']);other=self.upload(self.ca)
        self.signature(d['version_id'],[user_id])
        self.assertEqual(f.get('/api/versions/'+d['version_id']+'/file').status_code,200)
        self.assertEqual(f.get('/api/versions/'+v2['version_id']+'/file').status_code,403)
        self.assertEqual(f.get('/api/versions/'+other['version_id']+'/file').status_code,403)
        ds=f.get('/api/dashboard').json()['documents']
        self.assertEqual(len(ds),1);self.assertEqual(len(ds[0]['versions']),1)
        self.assertEqual(ds[0]['versions'][0]['id'],d['version_id'])
    def test_medical_alerts_and_tasks_are_not_leaked(self):
        self.add_user('foreman@example.test','encargado',cats=['*']);f=self.client('foreman@example.test')
        self.upload(self.ca,cat='salud',expires='2020-01-01')
        self.post('/alerts/run',{},self.a)
        self.assertEqual(f.get('/api/dashboard').json()['alerts'],[])
        self.assertFalse(any('aptitud' in t['title'] for t in f.get('/api/dashboard').json()['tasks']))
    def test_live_grant_revocation_and_external_cannot_change_grants(self):
        d=self.upload(self.ca)
        with connect() as c:g=one(c,'SELECT id FROM grants WHERE user_id=?',(self.ua,))
        self.assertEqual(self.ea.patch('/api/grants/'+g['id'],json={'permissions':['manage'],'categories':['prl']}).status_code,403)
        self.assertEqual(self.a.delete('/api/grants/'+g['id']).status_code,200)
        self.assertEqual(self.ea.get('/api/versions/'+d['version_id']+'/file').status_code,403)
    def test_encrypted_backup_restore_and_replay_tokens_revoked(self):
        from cryptography.fernet import Fernet
        from scripts.backup import backup
        from scripts.restore import restore
        import sqlite3
        self.upload(self.ca)
        os.environ['BACKUP_KEY']=Fernet.generate_key().decode()
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'copy.nmbackup';count=backup(dest)
            self.assertGreater(count,1);self.assertNotIn(b'SQLite format',dest.read_bytes())
            target=Path(tmp)/'restore';self.assertEqual(restore(dest,target),count)
            with sqlite3.connect(target/'nm.sqlite3') as c:
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],0)
                self.assertEqual(c.execute('SELECT COUNT(*) FROM documents').fetchone()[0],1)
            with self.assertRaises(ValueError): restore(dest,target)
        del os.environ['BACKUP_KEY']

    def test_external_signed_pdf_exact_bytes_preserved(self):
        raw=pdf_report('Documento externo ficticio',['No se atribuye evidencia de firma.'])
        metadata={'project_id':self.p,'company_id':self.ca,'category':'prl','title':'PDF externo','external_signed':True,'external_source':'correo de prueba'}
        r=self.a.post('/api/documents',data={'metadata':js(metadata)},files={'file':('externo.pdf',raw,'application/pdf')})
        self.assertEqual(r.status_code,200,r.text)
        saved=self.a.get('/api/versions/'+r.json()['version_id']+'/file')
        self.assertEqual(saved.content,raw)

    def test_incomplete_project_can_be_completed_and_requirements_generated(self):
        p=self.post('/projects',{'name':'Ficha incompleta','code':'INCOMPLETE'},self.a)
        r=self.a.patch('/api/projects/'+p['id'],json={'name':'Ficha completada','municipality':'Municipio ficticio','has_project':False,'details':{'foreman':'Encargado ficticio'}})
        self.assertEqual(r.status_code,200,r.text)
        completed=self.a.get('/api/projects/'+p['id']).json()
        self.assertEqual(completed['has_project'],0);self.assertEqual(completed['name'],'Ficha completada')
        self.assertTrue(any('gestión preventiva' in r['name'] for r in completed['requirements']))
        self.assertFalse(any('PSS' in r['name'] for r in completed['requirements']))

    def library_fixture(self):
        source=self.upload(self.ca,self.ea)
        self.post('/versions/'+source['version_id']+'/review',{'action':'validado','reason':'Documento general ficticio revisado'},self.a)
        library=self.post('/library',{'version_id':source['version_id'],'general_scope_confirmed':True,'reason':'Documento general de empresa, sin datos de obra'},self.a)
        target=self.post('/projects',{'name':'Destino ficticio','code':'LIB-TARGET','has_project':True},self.a)['id']
        self.post('/companies',{'project_id':target,'company_id':self.ca,'kind':'con_trabajadores','role':'subcontrata'},self.a)
        with connect() as c:
            insert(c,'grants',id=uid(),user_id=self.ua,project_id=target,company_id=self.ca,role='empresa',categories=js(SAFE_CATEGORIES),permissions=js(ROLES['empresa']))
        return source,library,target
    def apply_library(self,library,target,requirement=None,client=None):
        return self.post('/library/'+library['id']+'/apply',{'project_id':target,'requirement_id':requirement,'reason':'Aplicación justificada a esta obra ficticia'},client or self.ea)
    def test_library_apply_retains_hash_and_requires_local_review(self):
        source,lib,target=self.library_fixture();applied=self.apply_library(lib,target)
        with connect() as c:
            sv=one(c,'SELECT * FROM versions WHERE id=?',(source['version_id'],));v=one(c,'SELECT * FROM versions WHERE id=?',(applied['version_id'],))
            self.assertEqual(sv['hash'],v['hash']);self.assertNotEqual(sv['storage_key'],v['storage_key'])
            self.assertEqual(v['status'],'recibido');self.assertEqual(v['provenance'],'biblioteca_empresa')
            self.assertFalse(one(c,'SELECT id FROM signature_requests WHERE version_id=?',(v['id'],)))
            self.assertFalse(one(c,'SELECT id FROM reviews WHERE version_id=?',(v['id'],)))
        ds=self.ea.get('/api/dashboard').json()['documents'];version=next(d for d in ds if d['id']==applied['id'])['versions'][0]
        self.assertEqual(version['reuse']['library_id'],lib['id']);self.assertEqual(version['reuse']['source_hash'],sv['hash'])
    def test_library_other_company_and_unassigned_project_denied(self):
        source,lib,target=self.library_fixture()
        self.assertEqual(self.eb.get('/api/library',params={'project_id':self.p,'company_id':self.ca}).status_code,403)
        self.assertEqual(self.eb.get('/api/library/'+lib['id']+'/file',params={'project_id':self.p}).status_code,403)
        self.assertEqual(self.eb.post('/api/library/'+lib['id']+'/apply',json={'project_id':target,'reason':'Ataque'}).status_code,403)
    def test_library_publication_requires_validation_scope_and_permission(self):
        source=self.upload(self.ca,self.ea)
        body={'version_id':source['version_id'],'general_scope_confirmed':True,'reason':'Documento general'}
        self.assertEqual(self.ea.post('/api/library',json=body).status_code,403)
        self.assertEqual(self.a.post('/api/library',json=body).status_code,409)
        self.post('/versions/'+source['version_id']+'/review',{'action':'validado','reason':'Prueba'},self.a)
        self.assertEqual(self.a.post('/api/library',json={**body,'general_scope_confirmed':False}).status_code,422)
        health=self.upload(self.ca,cat='salud');self.post('/versions/'+health['version_id']+'/review',{'action':'validado','reason':'Prueba'},self.a)
        self.assertEqual(self.a.post('/api/library',json={**body,'version_id':health['version_id']}).status_code,422)
    def test_library_worker_and_signed_scopes_not_publishable(self):
        worker=self.post('/people/workers',{'project_id':self.p,'company_id':self.ca,'name':'Persona ficticia'},self.ea)
        req=next(r for r in self.a.get('/api/projects/'+self.p).json()['requirements'] if r['worker_id']==worker['id'] and r['category']=='prl')
        source=self.upload(self.ca,rid=req['id']);self.post('/versions/'+source['version_id']+'/review',{'action':'validado','reason':'Prueba'},self.a)
        self.assertEqual(self.a.post('/api/library',json={'version_id':source['version_id'],'general_scope_confirmed':True,'reason':'Prueba'}).status_code,422)
        source2=self.upload(self.ca);self.post('/versions/'+source2['version_id']+'/review',{'action':'validado','reason':'Prueba'},self.a);self.signature(source2['version_id'])
        self.assertEqual(self.a.post('/api/library',json={'version_id':source2['version_id'],'general_scope_confirmed':True,'reason':'Prueba'}).status_code,422)
    def test_library_publish_and_apply_are_idempotent(self):
        source,lib,target=self.library_fixture()
        again=self.post('/library',{'version_id':source['version_id'],'general_scope_confirmed':True,'reason':'Publicación repetida'},self.a)
        self.assertEqual(again['id'],lib['id']);one_=self.apply_library(lib,target);two=self.apply_library(lib,target)
        self.assertEqual(one_['id'],two['id']);self.assertTrue(two['already_applied'])
        with connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM versions WHERE document_id=?',(one_['id'],)).fetchone()[0],1)
    def test_library_source_superseded_updates_requirement_dashboard_and_export(self):
        source,lib,target=self.library_fixture()
        req=next(r for r in self.a.get('/api/projects/'+target).json()['requirements'] if r['company_id']==self.ca)
        self.post('/requirements/'+req['id'],{'action':'aplica','blocking':True,'reason':'Condición de prueba'},self.a)
        applied=self.apply_library(lib,target,req['id']);self.post('/versions/'+applied['version_id']+'/review',{'action':'validado','reason':'Revisado en destino'},self.a)
        self.upload(self.ca,self.ea,did=source['id'])
        detail=self.a.get('/api/projects/'+target).json();self.assertEqual(detail['health']['color'],'rojo')
        self.assertEqual(next(r for r in detail['requirements'] if r['id']==req['id'])['effective_status'],'sustituido')
        dash=self.a.get('/api/dashboard').json();v=next(d for d in dash['documents'] if d['id']==applied['id'])['versions'][0];self.assertEqual(v['effective_status'],'sustituido')
        zipped=self.a.get('/api/projects/'+target+'/export');idx=json.loads(zipfile.ZipFile(io.BytesIO(zipped.content)).read('indice.json'))
        entry=next(d for d in idx['documents'] if d['id']==applied['id'])['versions'][0]
        self.assertEqual(entry['effective_status'],'sustituido');self.assertEqual(entry['reuse']['source_hash'],v['hash'])
        r=self.a.post('/api/versions/'+applied['version_id']+'/review',json={'action':'validado','reason':'Intento de ignorar origen'});self.assertEqual(r.status_code,409)
        alerts1=self.post('/alerts/run',{},self.a);alerts2=self.post('/alerts/run',{},self.a);self.assertGreater(alerts1['created'],0);self.assertEqual(alerts2['created'],0)
    def test_library_revocation_preserves_history_and_disables_reuse(self):
        source,lib,target=self.library_fixture();applied=self.apply_library(lib,target)
        self.post('/library/'+lib['id']+'/revoke',{'reason':'Revocación de prueba'},self.a)
        self.assertEqual(self.ea.get('/api/library/'+lib['id']+'/file',params={'project_id':target}).status_code,410)
        self.assertEqual(self.ea.post('/api/library/'+lib['id']+'/apply',json={'project_id':target,'reason':'Intento'}).status_code,409)
        self.assertEqual(self.ea.get('/api/versions/'+applied['version_id']+'/file').status_code,200)
        with connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM document_reuse').fetchone()[0],1)
    def test_library_target_access_does_not_grant_origin_project_access(self):
        source,lib,target=self.library_fixture()
        with connect() as c:c.execute('DELETE FROM grants WHERE user_id=? AND project_id=?',(self.ua,self.p))
        self.assertEqual(self.ea.get('/api/versions/'+source['version_id']+'/file').status_code,403)
        listing=self.ea.get('/api/library',params={'project_id':target,'company_id':self.ca});self.assertEqual(listing.status_code,200)
        self.assertNotIn('project_id',listing.text);self.assertNotIn('published_by',listing.text)
        self.apply_library(lib,target)
    def test_library_expiration_and_mismatched_requirement(self):
        source,lib,target=self.library_fixture()
        other_req=next(r for r in self.a.get('/api/projects/'+target).json()['requirements'] if r['company_id'] is None)
        self.assertEqual(self.a.post('/api/library/'+lib['id']+'/apply',json={'project_id':target,'requirement_id':other_req['id'],'reason':'Prueba'}).status_code,422)
        with connect() as c:c.execute('UPDATE versions SET expires=? WHERE id=?',('2020-01-01',source['version_id']))
        self.assertEqual(self.ea.post('/api/library/'+lib['id']+'/apply',json={'project_id':target,'reason':'Prueba'}).status_code,409)
    def test_dashboard_external_project_details_minimized(self):
        self.a.patch('/api/projects/'+self.p,json={'details':{'notes':'NOTAS-INTERNAS','contacts':'CONTACTOS-INTERNOS','description':'Descripción compartida'}})
        ext=self.ea.get('/api/dashboard').json()['projects'][0]['details']
        self.assertNotIn('notes',ext);self.assertNotIn('contacts',ext);self.assertEqual(ext['description'],'Descripción compartida')
    def test_mixed_signer_grant_cannot_download_other_versions(self):
        with connect() as c:insert(c,'grants',id=uid(),user_id=self.ua,project_id=self.p,company_id=self.cb,role='firmante',categories=js(SAFE_CATEGORIES),permissions=js(ROLES['firmante']))
        source=self.upload(self.cb);new=self.upload(self.cb,did=source['id']);self.signature(source['version_id'],[self.ua])
        self.assertEqual(self.ea.get('/api/versions/'+source['version_id']+'/file').status_code,200)
        self.assertEqual(self.ea.get('/api/versions/'+new['version_id']+'/file').status_code,403)
        versions=next(d for d in self.ea.get('/api/dashboard').json()['documents'] if d['id']==source['id'])['versions']
        self.assertEqual([v['id'] for v in versions],[source['version_id']])

    def test_collaborator_can_read_rejection_reason_without_review_permission(self):
        d=self.upload(self.ca,self.ea)
        reason='Corregir la página de vigencia. Aportar una copia minimizada.'
        self.post('/versions/'+d['version_id']+'/review',{'action':'rechazado','reason':reason},self.a)
        doc=next(d0 for d0 in self.ea.get('/api/dashboard').json()['documents'] if d0['id']==d['id'])
        self.assertEqual(doc['versions'][0]['reviews'][0]['reason'],reason)
        self.assertNotIn(d['id'],[d0['id'] for d0 in self.eb.get('/api/dashboard').json()['documents']])
        self.assertEqual(self.ea.post('/api/versions/'+d['version_id']+'/review',json={'action':'validado','reason':'Intento'}).status_code,403)
    def test_task_comments_visible_to_same_company_and_do_not_validate(self):
        req=self.req(self.ca)
        with connect() as c:task=one(c,'SELECT * FROM tasks WHERE requirement_id=?',(req['id'],))
        r=self.post('/tasks/'+task['id']+'/comments',{'body':'He preparado la documentación. Pendiente de carga.'},self.ea)
        history=self.a.get('/api/tasks/'+task['id']+'/history')
        self.assertEqual(history.status_code,200);self.assertEqual(history.json()['comments'][0]['id'],r['id'])
        self.assertEqual(self.eb.get('/api/tasks/'+task['id']+'/history').status_code,403)
        self.assertEqual(self.eb.post('/api/tasks/'+task['id']+'/comments',json={'body':'Ataque'}).status_code,403)
        with connect() as c:self.assertEqual(one(c,'SELECT status FROM requirements WHERE id=?',(req['id'],))['status'],'pendiente')
    def test_task_history_does_not_disclose_restricted_dependency(self):
        source=self.req(self.ca)
        with connect() as c:
            task=one(c,'SELECT * FROM tasks WHERE requirement_id=?',(source['id'],))
            health=insert(c,'tasks',id=uid(),project_id=self.p,company_id=self.cb,title='Dependencia de otra empresa')
            insert(c,'dependencies',task_id=task['id'],depends_on=health['id'])
        history=self.ea.get('/api/tasks/'+task['id']+'/history').json()
        self.assertEqual(history['dependencies'],[{'title':'Dependencia restringida','status':'sin_acceso'}])
    def test_migrations_can_repeat_without_losing_versions_or_library(self):
        source,lib,target=self.library_fixture();applied=self.apply_library(lib,target)
        migrate();migrate()
        with connect() as c:
            self.assertTrue(one(c,'SELECT id FROM versions WHERE id=?',(applied['version_id'],)))
            self.assertTrue(one(c,'SELECT id FROM company_library WHERE id=?',(lib['id'],)))
            self.assertEqual([x['version'] for x in rows(c,'SELECT version FROM schema_migrations ORDER BY version')],[1,2,3,4])

    def test_site_specific_company_document_cannot_enter_general_library(self):
        req=next(r for r in self.a.get('/api/projects/'+self.p).json()['requirements'] if r['company_id']==self.ca and 'adhesión al PSS' in r['name'])
        source=self.upload(self.ca,rid=req['id']);self.post('/versions/'+source['version_id']+'/review',{'action':'validado','reason':'Prueba'},self.a)
        response=self.a.post('/api/library',json={'version_id':source['version_id'],'general_scope_confirmed':True,'reason':'Intento de generalizar un documento específico'})
        self.assertEqual(response.status_code,422)
    def test_general_company_rule_is_reusable_but_other_rule_is_not_equivalent(self):
        req=next(r for r in self.a.get('/api/projects/'+self.p).json()['requirements'] if r['company_id']==self.ca and r['name']=='Inscripción REA')
        source=self.upload(self.ca,rid=req['id']);self.post('/versions/'+source['version_id']+'/review',{'action':'validado','reason':'Prueba'},self.a)
        lib=self.post('/library',{'version_id':source['version_id'],'general_scope_confirmed':True,'reason':'Certificado general ficticio'},self.a)
        other=next(r for r in self.a.get('/api/projects/'+self.p).json()['requirements'] if r['company_id']==self.ca and r['name']=='Modalidad preventiva')
        response=self.a.post('/api/library/'+lib['id']+'/apply',json={'project_id':self.p,'requirement_id':other['id'],'reason':'No son equivalentes'})
        self.assertEqual(response.status_code,422)

    def test_render_bootstrap_is_one_time_and_never_resets_password(self):
        import sqlite3
        from unittest.mock import patch
        from app.bootstrap import bootstrap_admin
        from app.security import password_ok
        with sqlite3.connect(':memory:') as c:
            c.row_factory=sqlite3.Row;c.executescript((ROOT/'migrations/001_initial.sql').read_text())
            with patch.dict(os.environ,{'APP_ENV':'production','BOOTSTRAP_ADMIN_EMAIL':'initial@example.test','BOOTSTRAP_ADMIN_PASSWORD':'First-password-generated-for-test'},clear=True):
                self.assertTrue(bootstrap_admin(c))
                u=one(c,'SELECT * FROM users');self.assertEqual(u['admin'],1)
                self.assertTrue(password_ok('First-password-generated-for-test',u['password']))
            with patch.dict(os.environ,{'APP_ENV':'production','BOOTSTRAP_ADMIN_EMAIL':'different@example.test','BOOTSTRAP_ADMIN_PASSWORD':'Other-password-generated-for-test'},clear=True):
                self.assertFalse(bootstrap_admin(c));self.assertEqual(c.execute('SELECT COUNT(*) FROM users').fetchone()[0],1)
                self.assertEqual(one(c,'SELECT * FROM users')['email'],'initial@example.test')
                self.assertFalse(password_ok('Other-password-generated-for-test',one(c,'SELECT * FROM users')['password']))
    def test_render_bootstrap_missing_secrets_fails_closed_without_logging(self):
        import sqlite3
        from unittest.mock import patch
        from app.bootstrap import bootstrap_admin
        with sqlite3.connect(':memory:') as c:
            c.row_factory=sqlite3.Row;c.executescript((ROOT/'migrations/001_initial.sql').read_text())
            with patch.dict(os.environ,{'APP_ENV':'production'},clear=True):
                with self.assertRaises(RuntimeError): bootstrap_admin(c)
            with patch.dict(os.environ,{'APP_ENV':'production','BOOTSTRAP_ADMIN_EMAIL':'valid@example.test','BOOTSTRAP_ADMIN_PASSWORD':'short'},clear=True):
                with self.assertRaises(RuntimeError): bootstrap_admin(c)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM users').fetchone()[0],0)
    def test_render_server_uses_assigned_port_and_requires_data_dir(self):
        from unittest.mock import patch
        from scripts.serve import server_options
        with patch.dict(os.environ,{'PORT':'10000','RENDER':'true','DATA_DIR':'/var/data/nou-mallorca'},clear=True):
            opts=server_options();self.assertEqual(opts['port'],10000);self.assertEqual(opts['workers'],1);self.assertFalse(opts['access_log'])
        with patch.dict(os.environ,{'PORT':'wrong'},clear=True):
            with self.assertRaises(RuntimeError):server_options()
        with patch.dict(os.environ,{'RENDER':'true'},clear=True):
            with self.assertRaises(RuntimeError):server_options()
    def test_public_health_check_returns_no_private_details_and_db_failure_is_503(self):
        from unittest.mock import patch
        guest=TestClient(app);r=guest.get('/healthz')
        self.assertEqual(r.status_code,200);self.assertEqual(r.json(),{'status':'ok'})
        with patch('app.main.connect',side_effect=RuntimeError('internal database detail')):
            failed=guest.get('/healthz');self.assertEqual(failed.status_code,503)
            self.assertEqual(failed.json(),{'status':'unavailable'})

if __name__=='__main__': unittest.main(verbosity=2)
