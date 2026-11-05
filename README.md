# Nou Mallorca / NM2022 S.L. · V1.1 local funcional

Aplicación persistente de gestión documental de obras en castellano. **No es una maqueta**: API, usuarios, sesiones, permisos, SQLite, archivos privados, versiones, revisiones, invitaciones, firma simulada y exportaciones están implementados. No es todavía la totalidad del alcance de las 29 secciones ni una versión certificada para producción.

## Ejecutar

Avances de esta entrega: [biblioteca reutilizable, comentarios y correcciones de permisos](docs/AVANCES_V1_1.md). Con las dependencias instaladas, `python scripts/run.py --demo` inicializa una demostración ficticia y arranca la aplicación local en un solo paso.

Python 3.12 o posterior. Desde esta carpeta:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abrir http://127.0.0.1:8000 . El seed imprime un correo ficticio y una contraseña aleatoria de administración una sola vez. No hay contraseñas fijas. Guardar esa contraseña en un gestor. El seed no modifica bases que ya contienen usuarios.

Para una instalación vacía sin demostraciones, usar `python scripts/admin.py` en lugar del seed. Solo pide nombre, correo y contraseña por consola.

La base y los archivos se guardan en `.data/`, excluida de Git. No eliminar esa carpeta para actualizar código. `.env.example` documenta las variables; si se copia a `.env`, arrancar con `uvicorn app.main:app --env-file .env` para cargarlas. No existe un registro público de usuarios: el alta externa es por invitación. El entorno suministrado ya tiene las dependencias instaladas, por lo que puede omitirse `pip install` aquí.

## Recorrido principal

1. Crear obra, con proyecto, sin proyecto o sin definir; completar ficha cuando se disponga de datos reales.
2. En Empresas y trabajadores de la obra, incorporar una subcontrata, autónomo o proveedor de solo suministro.
3. En PRL y coordinación, evaluar los candidatos. Resolver aplicabilidad y carácter bloqueante con justificación competente.
4. Invitar al responsable por nombre y correo ficticios. Copiar el enlace y abrirlo en otra sesión del navegador para aceptar y crear contraseña. Si ya tiene cuenta, debe iniciar sesión con ese correo antes de aceptar.
5. El colaborador ve únicamente su ámbito y puede añadir trabajadores/equipos y aportar documentos desde formularios con carga móvil.
6. Administración consulta, inicia revisión, rechaza con acción necesaria o valida expresamente. La aprobación técnica es una acción distinta y exige validación y permiso previo.
7. Seleccionar versión PDF y solicitar firma; elegir uno o varios usuarios invitados con permisos, modalidad paralela o secuencial y función.
8. Compartir enlace o mensaje con WhatsApp/correo; el programa del usuario realiza el envío. La confirmación manual no es una entrega acreditada.
9. El firmante inicia sesión con su cuenta, consulta el PDF completo y confirma intención o rechaza. El **adaptador de pruebas** produce justificante simulado y evidencias identificadas como tales.
10. Cuando completan todos, se archiva un resultado PDF y JSON de evidencias; reintentos no duplican archivo ni evento. No cambia el estado de revisión/validación.
11. Subir licencia en Licencias y permisos y plano en Proyecto y planos. Los PDF y JPG/PNG se almacenan de forma privada. Las versiones validadas que sean generales de empresa pueden publicarse expresamente en su biblioteca y aplicarse a otras obras participantes, con revisión local y sin heredar firmas.
12. Invitar individualmente a dirección facultativa a la obra y categoría autorizadas, sin categorías restringidas. Las invitaciones permiten permisos específicos y la API permite ajustarlos o revocarlos.
13. Consultar dashboard, próximos pasos, Kanban y calendario. El Kanban explica bloqueos; administración puede registrar excepción motivada sin completar requisitos.
14. Exportar ZIP con índice, documentos, versiones y evidencias permitidas; PDF de pendientes y CSV de tareas. Todo se filtra por permisos en servidor.

## Arquitectura y modelo

La arquitectura inicial solicitada era Next.js + PostgreSQL + S3. El repositorio estaba vacío y el registro de paquetes no era accesible. Se eligió FastAPI + SQLite + disco privado para entregar una V1 que pudiera ejecutarse y probarse con las herramientas instaladas, sin servicios de pago. El cambio se comunicó durante la implementación.

- `app/main.py`: API y autorizaciones por acción; frontend estático servido por la misma aplicación.
- `app/security.py`: scrypt, sesiones aleatorias cuyo token se conserva hasheado, CSRF, aislamiento por participación/categoría y controles de firmante por versión.
- `app/engine.py`: catálogo, condiciones, instantáneas de regla, tareas idempotentes y estado documental. Un bloqueante aplicable incumplido prevalece sobre el porcentaje. Sin datos o aplicabilidad resuelta, gris.
- `app/library.py` y `app/document_state.py`: biblioteca general de empresa, aplicaciones trazables por versión, revocación y estados coherentes.
- `app/files.py`: validación/reprocesado, almacenamiento privado, PDF y adaptador de firma de prueba.
- `migrations/001_initial.sql`: obras, empresas, participaciones, agentes, trabajadores/asignaciones, equipos/asignaciones, plantillas/requisitos, documentos/versiones/revisiones, solicitudes/firmantes/archivos, tareas/dependencias, hitos, alertas, invitaciones, permisos y auditoría.
- `static/`: interfaz responsive sin dependencias externas ni logotipo inventado. Etiquetas en castellano; traducción catalana completa pendiente.
- `scripts/`: inicialización, alertas, copia cifrada y restauración verificada.

Cada permiso de consulta, carga, revisión, validación, aprobación, firma, descarga y exportación se comprueba en servidor. Salud exige categoría expresa y permiso adicional; dirección facultativa y encargado no pueden recibir esas categorías. Los enlaces de firma exigen la cuenta asignada, caducan y pueden revocarse. El perfil firmante solo consulta documentos/versiones asignados, no todo el expediente.

## Pruebas

```bash
python -m unittest discover -s tests -v
node --check static/app.js
```

En el sandbox de desarrollo, el despertar entre hilos de asyncio está restringido. Para ejecutar las mismas pruebas sin pedir acceso a red:

```bash
python scripts/test_sandbox.py
```

El runner añade un temporizador de sondeo **solo en el proceso de pruebas**, sin alterar aplicación o permisos de red. Ver [criterios y resultados](docs/VALIDACION.md). No se ha verificado visualmente en navegador ni en un móvil real; la maquetación responsive no sustituye esa prueba.

## Despliegue e integraciones

Ver [despliegue, firma, correo, almacenamiento y copias](docs/DEPLOY.md), [fuentes y criterios](docs/FUENTES.md) y [pendientes reales](docs/PENDIENTES.md).

No hay publicación web confirmada, proveedor real de firma, SMTP, PostgreSQL ni S3. Cambiar una variable no activa implementaciones inexistentes. Firma y correo se identifican siempre como **PRUEBA**. Ningún trámite administrativo se presenta automáticamente ni se ha enviado correo real.

## Render

Se incluyen un Blueprint propuesto y un arranque adaptado a Render. Ver [configuración y pasos pendientes](docs/RENDER.md). Repositorio previsto: https://github.com/pedidos-lgtm/nou-mallorca . Aún no está desplegado: faltan el espacio correcto de Render, validación remota y autorización de recursos de pago. El primer administrador puede inicializarse con variables seguras; no se crean demostraciones ni se imprimen contraseñas en el servicio.
