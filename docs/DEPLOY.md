# Despliegue de la V1 y operación

La V1 es una aplicación ASGI con SQLite y disco privado. No se ha desplegado ni se ha contratado ningún servicio. El entorno de desarrollo actual no permite descargar paquetes ni abrir un servidor visible de forma verificada. No usar los datos demo para expedientes reales.

## Servidor HTTPS

1. Preparar una máquina Linux con Python 3.12, usuario de servicio sin privilegios, almacenamiento cifrado y copia externa cifrada. Instalar los requisitos del repositorio en un entorno virtual.
2. Copiar código a `/opt/nou-mallorca` y asignar un directorio persistente exclusivo, p. ej. `/var/lib/nou-mallorca`, con permisos 0700 para el usuario del servicio. Mantenerlo fuera de cualquier directorio público del proxy.
3. Configurar secretos y variables en el gestor del servicio (no en Git): `DATA_DIR=/var/lib/nou-mallorca`, `APP_ENV=production`, `APP_URL=https://<dominio-propio>`, `COOKIE_SECURE=true`. El cargador de Uvicorn puede leer `.env` con `--env-file`; el código no carga `.env` por sí solo. Mantener `SIGNATURE_ADAPTER=test` y `MAIL_ADAPTER=test` hasta implementar y auditar proveedores reales. La interfaz informa siempre de pruebas.
4. Crear administración con `python scripts/admin.py`; ejecutar `uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1`. Usar **una instancia y un proceso**: SQLite y el disco local no soportan aquí un despliegue distribuido.
5. Poner un proxy como Caddy delante, con dominio y TLS automático; no publicar directamente el puerto de Uvicorn. Ejemplo de Caddyfile (sustituir el dominio):

```caddy
<dominio-propio> {
    request_body {
        max_size 16MB
    }
    reverse_proxy 127.0.0.1:8000
}
```

6. Configurar systemd para reinicio automático y usuario sin privilegios. No registrar cuerpos de peticiones, contraseñas, cookies, fragmentos o tokens. Los enlaces de invitación y firma usan fragmentos `/#...`, para no filtrarlos en accesos del proxy; las llamadas API con tokens también deben excluirse de logs o redactarse.
7. Programar `python scripts/worker.py` periódicamente con las mismas variables. Produce alertas internas idempotentes y no envía correo real. El umbral de próxima caducidad es actualmente 30 días; su configuración por obra es un pendiente de V2.
8. Antes de introducir información real: restauración ensayada, reglas revisadas por responsable competente, política de conservación aprobada, control de acceso revisado, disco cifrado, protección antivirus en cuarentena y prueba de uso móvil. La V1 admite PDF e imágenes minimizadas; la validación y reescritura no sustituyen un antivirus.

## Firma y correo

Implementado: `TestSignatureAdapter` con comprobación de hash, cuenta autenticada del firmante, consentimiento explícito, rechazo, secuencia, justificante marcado PRUEBA, evidencias de simulación y archivo idempotente. No hay servicio de firma real ni calificación eIDAS.

Antes de contratar, comparar proveedores que permitan API, sandbox, autenticación del firmante, niveles de firma adecuados, evidencia descargable, verificación de webhook, residencia de datos, DPA y precio. Opciones a evaluar por la empresa: Signaturit, Viafirma y DocuSign. No están integradas ni contratadas. Un adaptador real debe verificar callbacks autenticados, versión/hash exactos y resultado antes de archivar, y conservar también los ficheros y evidencias originales del proveedor.

Correo: tabla de buzón `outbox`, sin SMTP ni envío externo. Los recordatorios se deduplican por solicitud, destinatario y día. Añadir adaptador transaccional con reintentos y claves idempotentes antes de activar envíos reales. `mailto:` y WhatsApp son manuales y no proporcionan confirmación de entrega. La URL para compartir utiliza el origen real del navegador; en local no será accesible desde otro móvil salvo que se configure una red/HTTPS accesible.

## Almacenamiento

Los archivos solo se sirven pasando sesión y autorización del servidor; no existen rutas públicas al directorio privado. UUID de archivo no concede acceso. Los PDF normales se reescriben e imágenes se recodifican antes de calcular el hash; en esa carga normal, el hash corresponde al fichero conservado y no a los bytes antes de la sanitización. Los PDF marcados como **firmados externamente** se analizan para rechazar contenido activo, pero se conservan byte a byte para no invalidar su firma preexistente. Se registra origen, usuario y fecha, sin atribuir verificación criptográfica ni evidencias inexistentes. Quedan recibidos y pendientes de revisión. Es necesaria una cuarentena y un antivirus real antes de tratar archivos de terceros en producción. Las evidencias de firma de pruebas se refieren al fichero conservado exacto.

No hay adaptador S3 ni PostgreSQL. Para escalado, sustituir el acceso SQLite por un repositorio PostgreSQL con migración de datos y transacciones, y `files.store`/descargas por S3 privado con controles de servidor, cifrado, versionado y claves de objeto segregadas. No basta con configurar variables inexistentes.

## Copias y restauración

Dependencia: `cryptography`. Proporcionar `BACKUP_KEY` (clave Fernet) mediante gestor de secretos. Generar una clave fuera del repositorio con el método estándar de Fernet y guardarla separada de las copias. Perderla impide restaurar; no rotarla sin conservar claves de descifrado anteriores.

```bash
python scripts/backup.py /destino-seguro/copia-fecha.nmbackup
python scripts/restore.py /destino-seguro/copia-fecha.nmbackup /directorio-vacio/restaurado
```

La copia toma un bloqueo de escritura, genera snapshot SQLite coherente y empaqueta documentos y manifiesto SHA256; cifra todo el archivo. Puede pausar escrituras durante la copia. Para conjuntos grandes hay que sustituir el empaquetado en memoria por streaming.

La restauración exige destino vacío, descifra, comprueba rutas/hashes, integridad SQLite y claves foráneas. Revoca sesiones, invitaciones y enlaces de firma para evitar reutilización después de volver atrás. No arranca ni sustituye automáticamente el servicio: parar la aplicación, verificar en un entorno aislado, configurar `DATA_DIR` al directorio restaurado y reiniciar. Comparar expedientes, versiones, archivos y firmas antes de reabrir acceso. Establecer con la empresa RPO, RTO, frecuencia, ubicación y conservación; no se inventa una política de conservación legal.

La V1 no tiene eliminación automatizada ni bloqueo legal por retención. No borrar documentos/versiones manualmente en producción: implementar primero la política aprobada y sus controles.


## Paquete local V1.1

Se añaden `scripts/run.py`, Dockerfile y `compose.yaml` para facilitar el arranque. La receta Docker está escrita pero no construida ni verificada en este entorno. Compose es local, sin TLS y con puerto vinculado exclusivamente a loopback. No debe exponerse como producción sin aplicar los pasos HTTPS y seguridad anteriores. La biblioteca reutilizable y sus aplicaciones forman parte de las copias SQLite existentes.
