# CHANGELOG

## 2026-06-10

### Resumen

- Se creó una aplicación web full stack local para coordinación interna de eventos, clientes, trabajadores y asignaciones de personal.

### Funcionalidades añadidas

- Login con autenticación por token firmado y expiración.
- Roles `ADMIN` y `WORKER` con navegación diferenciada.
- Protección de rutas backend por rol.
- CRUD administrativo de clientes, eventos, trabajadores y usuarios.
- Dashboard de administración con métricas operativas.
- Modelo relacional SQLite con tablas `users`, `worker_profiles`, `clients`, `events` y `event_worker_assignments`.
- Gestión de asignaciones de trabajadores a eventos.
- Vista de trabajador para eventos disponibles, mis eventos e historial.
- Reglas para apuntarse y salirse de eventos.
- Cálculo de cobertura de personal: apuntados, mínimo, faltantes, cubierto y lleno.
- Seeds con usuarios, clientes, eventos y asignaciones de ejemplo.
- UI con buscador, filtros, confirmación de eliminación, mensajes toast, estados vacíos y diseño responsivo.

### Cambios técnicos relevantes

- Se eligió Python estándar + SQLite + frontend vanilla para evitar dependencias externas y asegurar arranque local simple.
- Se añadieron scripts npm como atajos para migración, seed, reset, arranque y verificación.
- Se documentaron credenciales, flujo de prueba completo, decisiones técnicas, limitaciones y próximos pasos.

### Notas importantes

- La regla para que un trabajador salga de un evento impide bajas con menos de 24 horas de antelación.
- La aplicación no está preparada para producción; el objetivo actual es uso local y validación funcional.
