"""Carga un manifiesto privado usando una autorización temporal de la aplicación.
El manifiesto y los adjuntos deben permanecer fuera del repositorio.
Uso: python scripts/import_bundle.py /ruta/privada/manifest.json --url https://app.example
El código se solicita sin eco, nunca se pasa en argumentos ni se guarda.
"""
import argparse,json,getpass,secrets,hashlib,urllib.request,urllib.error,time
from pathlib import Path

def main():
    parser=argparse.ArgumentParser();parser.add_argument('manifest');parser.add_argument('--url',required=True)
    args=parser.parse_args();base=args.url.rstrip('/')
    if not base.startswith('https://'):raise SystemExit('Se requiere una URL HTTPS.')
    manifest_path=Path(args.manifest);manifest=json.loads(manifest_path.read_text())
    token=getpass.getpass('Código temporal de importación: ').strip()
    if not token.startswith('nm_import_'):raise SystemExit('Código de importación no válido.')
    def request(path,body,kind='application/json'):
        req=urllib.request.Request(base+path,data=body,headers={'Authorization':'Bearer '+token,'Content-Type':kind,'User-Agent':'NouMallorca-Authorized-Import'},method='POST')
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req,timeout=120) as response:return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code>=500 and attempt<2:time.sleep(attempt+1);continue
                try:message=json.loads(error.read()).get('detail','Error de importación')
                except Exception:message='Error de importación'
                raise RuntimeError(f'HTTP {error.code}: {message}') from None
            except (TimeoutError,urllib.error.URLError):
                if attempt==2:raise RuntimeError('No ha sido posible contactar con la aplicación; se puede reintentar sin duplicar archivos.') from None
                time.sleep(attempt+1)
    output={'prepared':request('/api/imports/prepare',json.dumps(manifest['prepare']).encode()),'files':[]}
    output_path=manifest_path.parent/'import-result.json'
    def save():output_path.write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n');output_path.chmod(0o600)
    save()
    for index,item in enumerate(manifest.get('files',[]),1):
        raw=Path(item['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise RuntimeError('La huella local de un archivo no coincide. Importación detenida.')
        boundary='nm-'+secrets.token_hex(16)
        metadata={k:v for k,v in item.items() if k not in ['path','filename']}
        name=item['filename'].replace('"','').replace('\r','').replace('\n','')
        payload=(f'--{boundary}\r\nContent-Disposition: form-data; name="metadata"\r\n\r\n'.encode()+json.dumps(metadata,ensure_ascii=False).encode()+f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\nContent-Type: application/pdf\r\n\r\n'.encode()+raw+f'\r\n--{boundary}--\r\n'.encode())
        result=request('/api/imports/files',payload,'multipart/form-data; boundary='+boundary);output['files'].append(result);save()
        print(f'PDF {index}/{len(manifest["files"])} incorporado como recibido.',flush=True)
    if manifest.get('workers'):
        output['workers']=request('/api/imports/workers',json.dumps({'workers':manifest['workers']},ensure_ascii=False).encode());save()
        print('Trabajadores registrados sin asignaciones a obras ni cuentas de usuario.',flush=True)
    output['finished']=request('/api/imports/finish',b'{}');save()
    print('Importación completada; autorización temporal cerrada.',flush=True)
if __name__=='__main__':main()
