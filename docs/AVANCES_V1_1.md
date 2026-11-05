# V1.1 · Biblioteca de empresa y colaboración documental

Continuación de la V1, sobre la misma aplicación y sin contratar servicios, publicar documentos ni enviar comunicaciones reales.

## Cambios utilizables

### Reutilización de documentación general

1. Incorporar a una obra una empresa ya existente, seleccionándola en el formulario. No crear otra empresa con el mismo nombre para reutilizar sus documentos.
2. Revisar y validar un documento general de esa empresa.
3. En Documentos y firmas, elegir **Publicar como general**. Confirmar expresamente el ámbito general y justificarlo. Esta acción requiere permiso de validación y descarga en origen.
4. En otra obra donde participe esa empresa, abrir **Empresas y trabajadores → Biblioteca de empresa**, o **PRL → Reutilizar** en un requisito de empresa.
5. Consultar la versión y aplicarla con justificación. Se crea una aplicación trazable con el mismo hash, versión de origen y fecha. Se recibe pendiente de revisión local; no hereda firmas, revisiones ni aprobación técnica.
6. Cada aplicación queda fija a la versión elegida. Una nueva versión de origen no se incorpora silenciosamente. Si el origen caduca, deja de estar validado, se sustituye o se revoca su publicación, el estado efectivo en destino cambia. Un requisito bloqueante pendiente de resolver mantiene rojo. Las alertas y exportaciones utilizan el mismo estado.

Las publicaciones no dan acceso al expediente de origen, a contactos internos ni a otras categorías. Un usuario que solo tenga permiso en la obra de destino puede usar el archivo general publicado de su propia empresa, sin consultar la obra original. Las copias de aplicación se guardan con claves privadas propias para conservar el histórico. Repetir una publicación o aplicación no duplica registros ni ficheros.

No se pueden generalizar documentos de trabajadores, equipos, categorías restringidas ni versiones con solicitudes de firma. Si procede de un requisito, su instantánea debe autorizar expresamente la reutilización general. El catálogo nuevo permite evaluar esta posibilidad para identificación/contactos, modalidad preventiva, REA y seguro RC contractual; no implica que esos documentos sean exigibles ni que su contenido sea adecuado sin revisión. Las plantillas antiguas sin esa autorización no se modifican silenciosamente. Adhesiones al PSS, instrucciones, asignaciones y alcances de obra conservan su ámbito.

### Información y comentarios del portal

Las versiones visibles incluyen el motivo de revisión/rechazo, acción solicitada, revisor y fecha. La subcontrata puede consultar la corrección requerida sin disponer de permiso para revisar o validar.

Los pendientes tienen comentarios persistentes con autor y fecha, historial y dependencias. La empresa puede comentar sus propios pendientes si dispone de permiso de carga; comentar no valida documentos ni modifica el estado del requisito. Un usuario sin acceso a una dependencia ve únicamente «Dependencia restringida».

### Correcciones de acceso

- El dashboard aplica la misma minimización de fichas que el expediente externo: no expone notas ni contactos internos.
- Una persona con permiso de firmante en una empresa y otro papel en otra empresa solo puede descargar la versión que tiene asignada como firmante.
- La interfaz muestra acciones de revisión, publicación y carga según los permisos locales; el servidor sigue siendo quien autoriza cada petición.

## Arranque

Con los requisitos instalados:

```bash
python scripts/run.py --demo
```

Inicializa datos ficticios solo si no hay usuarios, imprime la contraseña aleatoria inicial y arranca en http://127.0.0.1:8000 . Si hay usuarios, no cambia sus contraseñas ni añade más datos. La contraseña inicial no se vuelve a mostrar. Para una instalación sin demostraciones, ejecutar primero `python scripts/admin.py` y después `python scripts/run.py`.

Comprobación sin abrir puertos:

```bash
python scripts/run.py --check
```

Comprueba migraciones e integridad sin inicializar usuarios ni datos. El runner carga `.env` si existe y no permite `--demo` en producción.

Se incluyen Dockerfile y Compose para un despliegue local reproducible. La receta Docker no ha sido construida en este entorno:

```bash
docker compose build
docker compose run --rm app python scripts/admin.py
docker compose up -d
```

Compose publica el puerto solo en 127.0.0.1. El volumen `nm_data` conserva datos; no utilizar `docker compose down -v` si se quieren conservar. El acceso remoto con HTTPS requiere el procedimiento DEPLOY.md y configuración de infraestructura. Esta entrega no constituye una publicación web.

## Migración y verificación

Se añaden las migraciones 003 (biblioteca y aplicaciones) y 004 (comentarios). El arranque las aplica sin eliminar documentos/versiones existentes. Las copias cifradas incluyen las tablas nuevas; la prueba de restauración sigue formando parte de la batería.

Ver VALIDACION.md para las pruebas ejecutadas y sus límites. Sigue pendiente la comprobación visual con navegador y móvil real, y las integraciones de producción indicadas en PENDIENTES.md.
