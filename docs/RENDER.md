# Preparación para Render

Estado: configuración preparada para el repositorio GitHub `pedidos-lgtm/nou-mallorca`. El despliegue de Render sigue pendiente de confirmar espacio, coste y validación remota.

## Propuesta revisable

`render.yaml` propone un servicio Python, una instancia, plan `0.5c-512mb`, disco de 1 GB en `/var/data`, datos en `/var/data/nou-mallorca`, región Frankfurt, arranque `python scripts/serve.py`, salud `/healthz` y despliegues automáticos desactivados. Es una propuesta de pago, pendiente de autorización y precio confirmado en la cuenta. No hay PostgreSQL, S3 ni servicios adicionales.

Antes de aplicar se comprobará que el nombre del servicio no coincide con otro recurso del espacio elegido. El repositorio debe contener la aplicación en su raíz; si se utiliza un subdirectorio, hay que adaptar el Blueprint. `.python-version` fija la rama Python 3.12, como en las pruebas locales.

Se ha leído la documentación oficial HTML porque el lector conectado no admite sus versiones Markdown. Se ha comprobado la sintaxis YAML local, no se ha efectuado validación oficial mediante CLI/API ni compilación remota. El CLI de Render no está instalado. El repositorio de destino es https://github.com/pedidos-lgtm/nou-mallorca . Antes de crear recursos se debe verificar que la rama publicada contiene esta configuración.

## Próximos pasos para completar el despliegue

1. Conectar una cuenta Render con acceso al espacio correcto e indicar su nombre/ID. No utilizar ningún espacio no confirmado por el titular.
2. Indicar o crear el repositorio GitHub. Publicar únicamente el código: excluir `.data`, documentos, `.env`, copias, claves y credenciales. Un repositorio privado debe ser accesible por la integración GitHub de Render.
3. Confirmar coste y región del servicio y disco antes de crearlos. Validar el Blueprint con `render blueprints validate render.yaml` cuando esté disponible el CLI o el validador oficial.
4. Subir código y Blueprint a la rama acordada y verificar que Render puede leerlos.
5. Crear el Blueprint desde la cuenta/espacio confirmados. Completar `BOOTSTRAP_ADMIN_EMAIL` en el panel, sin compartir contraseñas por chat.
6. Render generará `BOOTSTRAP_ADMIN_PASSWORD`; mantenerlo en su gestor de variables. Usarlo para el primer acceso sin imprimirlo en logs ni copiarlo al repositorio.
7. Revisar el despliegue hasta que termine, comprobar `/healthz`, login, subida/descarga privada, permisos y persistencia tras un reinicio autorizado. Solo entonces comunicar la URL como desplegada y verificada.

## Comportamiento del arranque

- El servidor escucha en `0.0.0.0` y en el puerto `PORT` asignado, con un único proceso y sin logs de URLs que puedan contener tokens.
- Las migraciones y el alta inicial se ejecutan al arrancar el proceso, cuando el disco está disponible. No se ejecutan en build o pre-deploy.
- Si la base está vacía, producción exige los datos iniciales válidos; falla sin publicar una aplicación vacía sin administrador. Si ya hay usuarios, nunca cambia contraseñas, no los reemplaza y no repite el alta.
- HTTPS se comprueba mediante `APP_URL` o la variable documentada `RENDER_EXTERNAL_URL`. Las cookies seguras se activan en el Blueprint. Para un dominio propio, se puede configurar `APP_URL` al dominio final.
- `/healthz` prueba acceso a las tablas y devuelve exclusivamente un estado; no expone rutas, usuarios ni documentos. Un fallo de base devuelve 503.
- Firma y correo permanecen en pruebas. No se cargan datos demo en el despliegue público.

Las alertas se pueden procesar desde Configuración. No se ha añadido un cron/worker separado, que no podría acceder al disco de este servicio. Las copias nativas cifradas y su traslado fuera del servicio deben configurarse antes de introducir datos reales. Un snapshot de disco no sustituye una copia coherente de SQLite.

## Referencias consultadas

- https://render.com/docs/blueprint-spec
- https://render.com/docs/disks
- https://render.com/docs/compute-plans
- https://render.com/docs/configure-environment-variables
- https://render.com/docs/environment-variables
- https://render.com/docs/python-version

El precio exacto no pudo extraerse de la página pública dinámica; debe verificarse en el panel antes de autorizar el recurso. Esta preparación no levanta los pendientes de producción de PENDIENTES.md.
