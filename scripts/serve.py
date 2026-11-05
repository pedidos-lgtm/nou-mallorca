"""Servidor para Render: puerto asignado, un proceso y registros sin URLs con tokens."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))

def server_options():
    try: port=int(os.getenv('PORT','8000'))
    except ValueError: raise RuntimeError('PORT no es un puerto válido.') from None
    if not 1<=port<=65535: raise RuntimeError('PORT fuera de rango.')
    if os.getenv('RENDER')=='true' and not os.getenv('DATA_DIR'):
        raise RuntimeError('Render requiere DATA_DIR en un disco persistente.')
    return {'host':'0.0.0.0','port':port,'workers':1,'access_log':False,'proxy_headers':True}

if __name__=='__main__':
    import uvicorn
    uvicorn.run('app.main:app',**server_options())
