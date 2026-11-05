# Alcance real y pendientes

La V1.1 prioriza el recorrido persistente de la sección 26. No cubre íntegramente el producto de las 29 secciones. No introducir documentación real hasta completar la revisión de implantación descrita en DEPLOY.md.

## Funciona en esta entrega

- Usuarios e invitaciones de un solo uso, sesiones, CSRF, limitación de intentos, permisos en API y archivos y revocación de asignaciones en vivo.
- Obras y fichas incompletas, participantes con papel, agentes con función, personas/equipos asignados, categorías configurables.
- Catálogo PRL orientativo y versionado; evaluación diferenciada por proyecto, entidad, participación y clase de equipo; aplicabilidad/no aplica justificados; instantáneas que no cambian al revisar la plantilla.
- Documentos privados PDF/JPG/PNG, metadatos básicos, revisiones, rechazo motivado, validación y aprobación técnica separadas, vigencias justificadas, versiones e historial.
- Alta de licencia y plano. Acceso individual de técnicos por obra/categorías; salud restringida.
- Firma **simulada** paralela/secuencial sobre versión exacta, autenticación de cuenta asignada, consentimiento, rechazo, caducidad, cancelación, recordatorio de prueba, resultado/evidencias de prueba y archivo idempotente.
- Documento firmado externamente con PDF exacto conservado, procedencia registrada y estado recibido. No se le atribuye validación criptográfica.
- Compartir/copiar enlaces y mensajes, WhatsApp y borrador `mailto:` sin integración; registro separado de envío confirmado manualmente.
- Dashboard de obras, causas de estado, próximos pasos, tareas con dependencia, Kanban con cambio de fase e historial, paralización independiente, calendario básico, hitos e incidencias como documentos internos.
- ZIP autorizado con índice/versiones/evidencias, pendientes PDF y tareas CSV. Borradores PDF orientativos.
- Alertas internas idempotentes para tareas vencidas y caducidades; buzón de pruebas. Copias cifradas y restauración verificada.

## Pendientes antes de una implantación real

1. **Infraestructura**: Next.js/TypeScript, PostgreSQL y S3 no se han implementado. La entrega usa FastAPI, SQLite y disco privado, un solo proceso/instancia. No hay publicación web confirmada. El despliegue HTTPS debe realizarse en una infraestructura aprobada.
2. **Firma/correo**: solo pruebas. Adaptador comercial, callbacks verificados, OTP/MFA adecuado al mecanismo elegido, firma avanzada/cualificada si procede y correo transaccional con reintentos requieren implementación y configuración. Para renovar un enlace se cancela y crea una nueva solicitud; no hay botón específico de renovación.
3. **Reglas**: consulta y aprobación competente de todas las reglas. Los campos de riesgos, oficio, fases y condiciones están en la ficha, pero aún no forman un motor completo de expresiones ni de transiciones configurables. No hay doble aprobación separada de autor/aprobador. El PSS y estudio son candidatos según con proyecto, no documentos aprobados por la aplicación.
4. **Documentación general reutilizable**: implementada la biblioteca con publicación expresa, aplicaciones por versión, hash, revisión local, revocación y estados compartidos. Quedan el editor completo de políticas de reutilización y las sugerencias automáticas. Las aplicaciones no se actualizan silenciosamente al subir una nueva versión de origen. Ver AVANCES_V1_1.md.
5. **Privacidad/seguridad operativa**: cuarentena y antivirus real; cifrado de disco y copias externas configurados por el operador; política de conservación, bloqueo legal y eliminación aprobada; revisión de permisos y logs; recuperación de contraseña, MFA y gestión completa de cuentas. La V1 restringe tipos y contenido activo, pero no certifica que un archivo esté libre de malware. No existe comprobación automática que detecte todos los datos médicos prohibidos dentro de un PDF; el procedimiento debe exigir solo conclusiones minimizadas.
6. **Interfaz y móvil**: responsive implementado y sintaxis JavaScript comprobada. No hay prueba real de navegador/móvil ni accesibilidad completa. No hay traducción catalana; las etiquetas deberán extraerse a catálogos de idioma.
7. **Agenda/avisos**: el calendario global muestra fechas previstas, tareas, firmas y caducidades; hitos se ven en cada obra. Faltan calendario mensual interactivo, dependencias de hitos, recordatorios configurables, plazos de permisos temporales y descargas como entidades estructuradas. Las condiciones/horarios pueden registrarse como metadatos del permiso. El umbral de 30 días de aviso es fijo en esta V1.
8. **Informes/plantillas**: faltan informes dedicados por empresa/trabajador/firma, Excel y editor de plantillas con aprobación. El ZIP incluye las entidades y estados autorizados. Los borradores PDF son esqueletos sin aprobar y pueden descargarse; se pueden subir plantillas existentes como documentos, sin motor de cumplimentación de plantillas corporativas.
9. **Gestión avanzada**: reasignación de personas y equipos existentes entre obras, edición completa de empresas y participaciones (ya se permite incorporar una empresa existente a otra obra), cambios de tipología de obra con requisitos ya generados (solo se permite definir una tipología antes desconocida), fecha límite de solicitud documental, aprobaciones dentro de flujos técnicos específicos y configuración completa del pipeline.
10. **Procedimiento**: fijar con la empresa responsables, reglas de revisión, RPO/RTO, conservación y tratamiento de datos de salud. No se han inventado datos fiscales, técnicos, licencias, direcciones ni documentos reales.
