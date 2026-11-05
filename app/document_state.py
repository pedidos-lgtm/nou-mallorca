"""Estado de una versión y trazabilidad de reutilización, sin cambiar el histórico."""
from datetime import date
from .db import one

def base_status(version):
    if not version: return 'pendiente'
    if version.get('expires') and version['expires'] < date.today().isoformat(): return 'caducado'
    return version['status']

def library_status(c,item):
    if item['revoked_at']: return 'revocado'
    source=one(c,'SELECT * FROM versions WHERE id=?',(item['source_version_id'],))
    if not source: return 'pendiente'
    state=base_status(source)
    if state!='validado': return state
    latest=one(c,'SELECT id FROM versions WHERE document_id=? ORDER BY number DESC LIMIT 1',(source['document_id'],))
    if latest['id']!=source['id']: return 'sustituido'
    return 'validado'

def effective_version_status(c,version):
    state=base_status(version)
    if not version: return state
    reuse=one(c,'''SELECT l.* FROM document_reuse r JOIN company_library l ON l.id=r.library_id
        WHERE r.target_version_id=?''',(version['id'],))
    if reuse:
        source_state=library_status(c,reuse)
        if source_state=='revocado': return 'rechazado'
        if source_state!='validado': return source_state
    return state

def reuse_trace(c,version_id):
    # Intentionally excludes source project contacts, reviews and signature evidence.
    return one(c,'''SELECT r.library_id,r.applied_by,r.applied_at,r.reason,
        l.source_version_id,l.published_at,l.revoked_at,s.hash AS source_hash,
        s.number AS source_version_number FROM document_reuse r
        JOIN company_library l ON l.id=r.library_id
        JOIN versions s ON s.id=l.source_version_id WHERE r.target_version_id=?''',(version_id,))
