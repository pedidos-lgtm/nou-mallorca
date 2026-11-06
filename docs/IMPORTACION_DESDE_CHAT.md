# Importación privada desde la conversación

La aplicación permite delegar un lote desde una sesión autenticada de administración. No se utiliza ni se comparte la contraseña principal.

1. Abrir «Importar desde chat» en el menú de la aplicación.
2. Elegir una obra y empresa existentes o autorizar la creación de sus fichas a partir de los datos aportados.
3. Seleccionar límites de PDF y trabajadores. Por defecto se proponen 18 PDF y 10 trabajadores; los límites se comprueban en el servidor.
4. Generar el código temporal y compartirlo únicamente en la conversación correspondiente. Caduca en una hora y puede revocarse.
5. El proceso autorizado incorpora archivos y trabajadores, conserva los originales PDF y su hash y cierra la autorización al terminar. Si una petición se reintenta, no duplica documentos ya importados.

El código solo acepta las rutas de importación. No permite leer el dashboard, descargar documentos, validar, asignar trabajadores ni modificar permisos. Cada petición comprueba la vigencia del código y que su titular siga siendo un administrador activo.

Los PDF quedan «recibidos», sin firmas electrónicas inventadas ni validación técnica. Los metadatos propuestos y las discrepancias entre fuentes se conservan para revisión. Los formularios incompletos se identifican expresamente y no se vinculan como requisitos cumplidos. Ninguna fase o fecha operativa se deduce automáticamente de su carga.

La documentación general de empresa se incorpora a un archivo reservado a administración, separado de cada obra. Desde Empresas → Archivo general puede consultarse y descargarse. No aparece en el ZIP de un expediente de obra ni se comparte con colaboradores externos.

El listado de trabajadores admite exclusivamente nombre, oficio, correo y teléfono de contacto, estado y referencia de fila. No admite DNI completos, datos médicos, cumpleaños, geolocalización ni permisos de aplicaciones externas. No crea usuarios, no envía invitaciones y no asigna obras. Las coincidencias de nombre con fichas existentes quedan pendientes de revisión, sin sobrescribirlas.

El cliente genérico `scripts/import_bundle.py` recibe un manifiesto privado y pide el código sin eco. Los manifiestos, las hojas de cálculo y los PDF originales no se guardan en Git ni se publican como recursos estáticos. Los resultados se conservan fuera del repositorio. El análisis de PDF es estructural: las secuencias de bytes que casualmente se parezcan a nombres de acciones dentro de imágenes o fuentes no se confunden con acciones ejecutables; JavaScript, adjuntos y acciones activas siguen rechazándose. Esto no sustituye un antivirus de producción.

Migración añadida: 005. Las copias SQLite incluyen las tablas de importación y archivo general.
