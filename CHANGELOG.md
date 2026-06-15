# CHANGELOG

## 2026-06-10 - Fase 2 UX, reservas y economía

### Resumen

- Se mejoró la experiencia visual y móvil de la aplicación sin cambiar la arquitectura local Python/SQLite + frontend vanilla.

### Funcionalidades añadidas

- Formularios de creación y edición de eventos en modal reutilizable.
- Modal de detalle de evento con información operativa, económica, plazas normales, reservas y acciones por rol.
- Precio por hora, moneda, duración calculada y ganancia estimada por trabajador.
- Sistema de plazas normales y reservas con porcentaje configurable por evento, por defecto 10%.
- Promoción automática del primer trabajador en reserva cuando se libera una plaza normal.
- Gestión administrativa de asistencia: pendiente, asistió, no presentado y cancelado.
- Cálculo de coste estimado y confirmado por evento.
- Vista de agenda/calendario agrupada por días para administrador y trabajador.
- Filtros ampliados por tipo, estado, cliente, fechas, disponibilidad, reserva, cobertura y participación.
- Área personal del trabajador con perfil, estadísticas y resumen de ganancias.
- Vista de ganancias mensuales con totales estimados y confirmados.
- Diseño responsive más pulido, tarjetas móviles, bottom-sheet modals, botones táctiles y estados vacíos mejorados.

### Cambios técnicos relevantes

- Nuevos campos en `events`: `type`, `hourly_rate`, `currency`, `reserve_enabled` y `reserve_percentage`.
- Nuevos campos en `event_worker_assignments`: `slot_type`, `attendance_status`, `joined_at`, `promoted_at` y `attended_at`.
- Nuevas rutas para calendario, perfil/ganancias del trabajador, promoción de reserva y asistencia.
- Validaciones de precio/hora, fechas con hora, reserva, máximo/mínimo y permisos por rol.

### Notas importantes

- La reserva requiere máximo normal definido para calcular cupos de reserva de forma consistente.
- Las ganancias confirmadas solo se computan si el administrador marca asistencia como `ATTENDED`.

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
