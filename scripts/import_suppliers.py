"""Import a privately prepared supplier batch using an hourly, write-only grant.
No credentials or supplier data are committed. Run from the repository root.
"""
import sys,json,getpass,urllib.request,urllib.error
from pathlib import Path

def run(path,url):
    bundle=json.loads(Path(path).read_text())
    token=getpass.getpass('Código temporal de proveedores: ')
    headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
    def post(endpoint,payload):
        req=urllib.request.Request(url.rstrip('/')+'/api'+endpoint,data=json.dumps(payload).encode(),headers=headers,method='POST')
        with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
    try:
        result=post('/imports/suppliers',{'source_sha256':bundle['report']['source_sha256'],'suppliers':bundle['suppliers']})
        dest=Path(path).with_name('import-result-private.json')
        dest.touch(mode=0o600,exist_ok=True);dest.chmod(0o600);dest.write_text(json.dumps(result,ensure_ascii=False,indent=2))
        conflicts=sum(r['status']=='coincidencia_nombre_revisar' for r in result['results'])
        post('/imports/finish',{})
        print(json.dumps({'created':result['created'],'existing':sum(r['status']=='ya_importado' for r in result['results']),'name_conflicts_review':conflicts,'authorization_closed':True}))
    except urllib.error.HTTPError as error:
        print('Importación no confirmada. HTTP',error.code,file=sys.stderr);raise SystemExit(1)
if __name__=='__main__':run(sys.argv[1],sys.argv[2])
