import io, hashlib, json
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from .db import FILES, uid, now
from .security import fail

def reject_active_pdf(reader):
    from pypdf.generic import IndirectObject, DictionaryObject, ArrayObject
    seen=set(); count=0
    forbidden={'/JavaScript','/JS','/Launch','/EmbeddedFiles','/EmbeddedFile','/RichMedia','/OpenAction','/AA','/XFA'}
    def visit(obj):
        nonlocal count
        count+=1
        if count>200000: fail(422,'PDF excesivamente complejo.')
        if isinstance(obj,IndirectObject):
            key=(obj.idnum,obj.generation)
            if key in seen:return
            seen.add(key);obj=obj.get_object()
        if isinstance(obj,DictionaryObject):
            if any(str(k) in forbidden for k in obj.keys()) or str(obj.get('/S','')) in forbidden or str(obj.get('/Type',''))=='/EmbeddedFile':
                fail(422,'El PDF contiene acciones activas o adjuntos no admitidos.')
            for value in obj.values():visit(value)
        elif isinstance(obj,ArrayObject):
            for value in obj:visit(value)
    visit(reader.trailer)

def validate_file(content,filename,preserve_original=False):
    if len(content)>15*1024*1024 or not content: fail(422,'Archivo vacío o mayor de 15 MB.')
    ext=Path(filename or '').suffix.lower()
    if ext=='.pdf':
        try:
            r=PdfReader(io.BytesIO(content),strict=True)
            if r.is_encrypted or len(r.pages)>500: fail(422,'PDF cifrado o más de 500 páginas.')
            # Parse PDF object names instead of scanning compressed stream bytes.
            # Raw /JS or /AA substrings can occur innocently inside fonts or images.
            reject_active_pdf(r)
            if preserve_original: return content,'application/pdf','.pdf'
            # Rewrite parsed pages to strip catalog metadata and non-page payloads.
            w=PdfWriter()
            for page in r.pages:
                if '/Annots' in page: del page['/Annots']
                w.add_page(page)
            out=io.BytesIO();w.write(out)
            return out.getvalue(),'application/pdf','.pdf'
        except Exception as e:
            if hasattr(e,'status_code'): raise
            fail(422,'PDF no válido.')
    if ext in ['.jpg','.jpeg','.png']:
        try:
            Image.MAX_IMAGE_PIXELS=25000000
            im=Image.open(io.BytesIO(content)); im.load()
            if im.width*im.height>25000000: fail(422,'Imagen demasiado grande.')
            im=im.convert('RGB'); out=io.BytesIO(); im.save(out,format='JPEG')
            return out.getvalue(),'image/jpeg','.jpg'
        except Exception as e:
            if hasattr(e,'status_code'): raise
            fail(422,'Imagen no válida.')
    fail(422,'Solo se admiten PDF, JPG y PNG. No cargues historias clínicas ni diagnósticos.')

def store(content,extension):
    key=uid()+extension
    path=FILES/key
    path.write_bytes(content);path.chmod(0o600)
    return key,hashlib.sha256(content).hexdigest()

def pdf_report(title,lines):
    out=io.BytesIO(); c=canvas.Canvas(out,pagesize=A4); c.setTitle(title); y=800
    for line in [title,'Generado: '+now(),*lines]:
        # Wrap long lines, maintain explicit empty-date notices.
        text=str(line)
        chunks=[text[i:i+95] for i in range(0,max(1,len(text)),95)]
        for chunk in chunks:
            if y<45: c.showPage();y=800
            c.setFont('Helvetica',10); c.drawString(35,y,chunk);y-=16
    c.save();return out.getvalue()

class TestSignatureAdapter:
    name='test'
    def complete(self,original,evidence):
        # This is an archive receipt appended to exact original, not a qualified signature.
        if hashlib.sha256(original).hexdigest()!=evidence['original_hash']: fail(409,'Hash del original no coincide.')
        receipt=pdf_report('FIRMA SIMULADA · SIN VALIDEZ DE FIRMA ELECTRÓNICA',[
            'Prueba de recorrido. No equivale a aprobación técnica.', 'Solicitud: '+evidence['request_id'],
            'SHA256 original: '+evidence['original_hash'],
            *[f"{s['name']} · {s['function']} · {s['signed_at']}" for s in evidence['signers']]])
        if original.startswith(b'%PDF'):
            w=PdfWriter(); w.append(io.BytesIO(original)); w.append(io.BytesIO(receipt)); out=io.BytesIO();w.write(out);return out.getvalue()
        return receipt
