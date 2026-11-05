# Validación de la V1

Fecha de ejecución: 5 de noviembre de 2026. Datos exclusivamente ficticios y bases aisladas temporales.

## Resultado

52 pruebas de integración API y persistencia, ejecutadas con el runner de sandbox, más compilación Python y comprobación de sintaxis JavaScript. El runner usa el mismo TestClient y endpoints que la ejecución normal; solo añade sondeo de asyncio para compensar la limitación de despertar entre hilos del sandbox. No concede red ni cambia autorizaciones.

```bash
python scripts/test_sandbox.py
python -m compileall -q app scripts tests
node --check static/app.js
```

## Cobertura

- Empresa B no puede consultar ni cargar en el ámbito de A, aun con UUID conocido; filtros del dashboard.
- Usuarios externos no pueden crear permisos, administrarse, revisar reglas ni auto-validar.
- Obras sin proyecto, incluso con subcontratas, no reciben candidatos PSS; autónomos, ejecutoras y solo suministro difieren.
- Subida como recibido; rechazo motivado; aprobación separada exige validación; firmas no validan ni aprueban.
- Caducidad recalculada y rojo de bloqueante por encima de porcentajes; prioridad y motivos visibles.
- Versiones anteriores conservadas; versión nueva sin heredar solicitudes/firmas.
- Invitación de un solo uso/revocada; enlaces de firma cancelados/caducados; cuenta distinta no suplanta al firmante.
- Envío manual se registra únicamente como confirmación del usuario sin entrega acreditada.
- Archivo de resultado y evento sin duplicados; firma secuencial impide saltar orden; recordatorios idempotentes.
- Documento firmado externo conserva procedencia, recibido y sin evidencias inventadas; PDF externo conservado byte a byte.
- Técnicos limitados a obra/categoría; encargado sin documentos, tareas o alertas de salud.
- Firmante limitado a documento y versión asignados; revocación de asignación con efecto inmediato.
- ZIP excluye otras empresas y categorías restringidas; dashboard/expediente/exportación coherentes.
- Alertas no duplicadas; mover fase o paralizar no borra requisitos; cerrar tarea no valida requisito.
- CSRF y rechazo de carga HTML; copia cifrada, restauración con hashes/integridad y revocación de sesiones.

## Ampliación V1.1

- Biblioteca por empresa/categoría y obra participante, publicación autorizada y declaración de ámbito general.
- Reutilización del mismo hash con aplicación recibida, sin heredar revisión, aprobación ni solicitudes de firma.
- Publicaciones y aplicaciones idempotentes. Caducidad, sustitución y revocación coherentes en requisito, dashboard, alertas y exportaciones.
- Acceso al archivo general sin conceder acceso al expediente original ni a otras empresas; documentación de trabajadores, salud y firmas de obra excluida.
- Adhesión al PSS específica de obra no publicable como general; REA no se aplica como equivalente de modalidad preventiva.
- Motivo de rechazo consultable por colaborador sin otorgar permisos de revisión.
- Comentarios de tareas persistentes, sin validar requisitos, con aislamiento y dependencias restringidas.
- Minimizados los datos de ficha externa también en dashboard y corregidos permisos combinados de firmante.
- Migraciones repetibles sin pérdida de versiones/biblioteca. Preflight de arranque sin abrir puertos.

## Límites de verificación

El CLI de preview está disponible, pero no hay herramienta de navegador `cua_repl.js` en la vía admitida por Sites; no se ha arrancado un preview visible ni instalado un navegador alternativo. No están verificados el recorrido táctil, renderizado de PDF en móviles, apertura real de WhatsApp/correo, portapapeles en HTTPS, accesibilidad o drag-and-drop en un navegador real. El selector de fase proporciona alternativa al arrastre.

No se ha probado un proveedor real de firma, SMTP, S3 ni PostgreSQL: no están implementados. Tampoco se ha efectuado auditoría de seguridad independiente, prueba de carga o validación legal del catálogo. Las pruebas funcionales no certifican seguridad operativa ni cumplimiento legal.


## Preparación Render

Cuatro pruebas adicionales: alta inicial única sin reinicializar usuarios/contraseñas, fallo seguro sin secretos válidos en producción, puerto asignado y directorio persistente requeridos, y health check público sin datos privados con 503 ante fallo de base. Las 52 pruebas han pasado. No verifican un despliegue real ni sustituyen validación oficial del Blueprint.
