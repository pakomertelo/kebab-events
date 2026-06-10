# Kebab Events

Kebab Events es una aplicación web full stack local para la organización interna de una empresa de coordinación de eventos con muchos empleados. Permite gestionar clientes, eventos, trabajadores, usuarios y asignaciones de personal con autenticación real y permisos por rol.

## Stack usado

Decisión técnica: se usa Python 3 estándar con SQLite y frontend HTML/CSS/JavaScript sin dependencias externas para garantizar que el proyecto arranque en entornos locales incluso cuando el registro de npm no esté disponible. La arquitectura separa API REST, base de datos relacional y UI web.

- **Frontend:** HTML, CSS y JavaScript servidos localmente.
- **Backend:** Python `http.server` con API REST propia.
- **Base de datos:** SQLite relacional.
- **Autenticación:** token firmado HMAC con expiración de 8 horas.
- **Contraseñas:** PBKDF2-HMAC-SHA256 con salt por usuario.
- **Roles:** `ADMIN` y `WORKER` validados en backend.

## Requisitos previos

- Python 3.11 o superior recomendado.
- Node/npm opcional: solo se usa como lanzador de scripts (`npm run ...`). También puedes ejecutar Python directamente.

## Instalación y configuración

1. Copia las variables de entorno de ejemplo si quieres personalizar rutas o puerto:

```bash
cp .env.example .env
```

Variables disponibles:

```env
DATABASE_PATH=backend/dev.db
JWT_SECRET=change-this-local-development-secret
PORT=4000
```

No se incluyen secretos reales. Cambia `JWT_SECRET` si vas a compartir el entorno local.

## Preparar base de datos y datos de prueba

Con npm:

```bash
npm run db:reset
```

O directamente:

```bash
python3 backend/app.py reset
```

Esto crea/migra la base de datos SQLite y carga seed con:

- 1 administrador.
- 3 trabajadores.
- 3 clientes.
- Eventos publicados, borradores, completados y cancelados.
- Eventos con personal suficiente y con falta de personal.

## Arrancar en local

Con npm:

```bash
npm run dev
```

O directamente:

```bash
python3 backend/app.py serve
```

La aplicación queda disponible en:

- Web: <http://localhost:4000>
- API: <http://localhost:4000/api>

## Credenciales de prueba

| Rol | Email | Contraseña |
| --- | --- | --- |
| ADMIN | `admin@kebab-events.local` | `Admin123!` |
| WORKER | `ana@kebab-events.local` | `Worker123!` |
| WORKER | `luis@kebab-events.local` | `Worker123!` |
| WORKER | `sara@kebab-events.local` | `Worker123!` |

## Roles disponibles

### ADMIN

Puede:

- Gestionar clientes.
- Gestionar eventos.
- Gestionar trabajadores.
- Gestionar usuarios.
- Asignar y quitar trabajadores de eventos.
- Ver dashboard completo y métricas de cobertura.

### WORKER

Puede:

- Ver eventos publicados disponibles.
- Ver sus propios eventos.
- Ver detalle operativo de eventos.
- Apuntarse a eventos publicados no cancelados/completados.
- Salirse de eventos cuando las reglas lo permiten.

No puede gestionar clientes, trabajadores, usuarios ni editar datos administrativos. Estas restricciones se validan en backend, no solo en la interfaz.

## Funcionalidades principales

- Login funcional con token de sesión.
- Protección de rutas API por autenticación y rol.
- CRUD de clientes, trabajadores, usuarios y eventos para administradores.
- Modelo intermedio `event_worker_assignments` para relación evento-trabajador.
- Dashboard administrativo con totales, próximos eventos, eventos sin cubrir, completados, trabajadores activos y clientes.
- Buscador y filtros básicos en listados principales.
- Confirmación visual antes de eliminar.
- Mensajes claros de éxito/error tipo toast.
- Estados vacíos y de carga en la UI.
- Vista de eventos disponibles, mis eventos e historial para trabajadores.

## Reglas de cobertura de personal

Cada evento tiene:

- `min_workers`: mínimo obligatorio mayor que 0.
- `max_workers`: máximo opcional.

La aplicación calcula:

- Trabajadores apuntados/asignados activos (`SIGNED_UP` o `ASSIGNED`).
- Trabajadores faltantes.
- Si el mínimo está cubierto.
- Si el evento está lleno por máximo.
- Etiquetas: “Faltan N trabajadores”, “Mínimo cubierto”, “Evento completo” o “Evento cancelado”.

Reglas implementadas:

- Un trabajador solo puede apuntarse a eventos `PUBLISHED`.
- No puede apuntarse dos veces al mismo evento.
- No puede apuntarse si el evento alcanzó `max_workers`.
- No puede salirse de eventos `COMPLETED` o `CANCELLED`.
- Regla de tiempo: no puede salirse con menos de **24 horas** de antelación respecto a la fecha de inicio del evento.

## Validaciones

Backend:

- Autenticación obligatoria en rutas privadas.
- Permisos por rol.
- Mínimo de trabajadores mayor que 0.
- Máximo no menor que mínimo.
- Fecha de fin no anterior a fecha de inicio.
- Evita duplicados por restricción única `(event_id, worker_id)`.
- Impide apuntarse a eventos no publicados, completos, completados o cancelados.

Frontend:

- Campos requeridos en formularios.
- Inputs de email, fecha, hora y número.
- Confirmación antes de eliminar.
- Mensajes de error claros retornados por la API.

## Estructura del proyecto

```text
.
├── backend/
│   └── app.py              # API REST, autenticación, reglas, migración y seed
├── frontend/
│   ├── index.html          # Entrada web
│   └── assets/
│       ├── app.js          # Interfaz y cliente API
│       └── styles.css      # Estilos profesionales responsivos
├── .env.example            # Variables locales de ejemplo
├── CHANGELOG.md            # Historial de cambios
├── package.json            # Scripts locales
└── README.md
```

## Scripts útiles

```bash
npm run install:all   # Comprueba Python disponible
npm run db:migrate    # Crea tablas si no existen
npm run db:seed       # Carga datos de prueba
npm run db:reset      # Recrea base y seed
npm run dev           # Arranca web + API en local
npm run build         # Verifica sintaxis Python
```

Equivalentes directos:

```bash
python3 backend/app.py migrate
python3 backend/app.py seed
python3 backend/app.py reset
python3 backend/app.py serve
python3 -m py_compile backend/app.py
```

## Cómo probar el flujo completo

1. Ejecuta `npm run db:reset`.
2. Ejecuta `npm run dev`.
3. Entra en <http://localhost:4000> como `admin@kebab-events.local` / `Admin123!`.
4. Crea un cliente desde **Clientes**.
5. Crea un evento publicado desde **Eventos** con mínimo de trabajadores.
6. Crea un trabajador desde **Trabajadores**.
7. Cierra sesión.
8. Entra como trabajador, por ejemplo `ana@kebab-events.local` / `Worker123!`.
9. Abre **Eventos disponibles**.
10. Apúntate a un evento.
11. Cierra sesión y vuelve como administrador.
12. Abre **Eventos**, revisa el detalle y comprueba que el evento actualiza trabajadores apuntados y faltantes.

## Limitaciones actuales

- Aplicación pensada solo para local; no incluye despliegue de producción.
- La UI es funcional y profesional, pero sin framework de componentes.
- La API está implementada con librerías estándar para maximizar portabilidad; en una fase futura podría migrarse a FastAPI/Express si se requiere ecosistema avanzado.
- No hay tests automatizados extensos todavía; se incluye verificación de sintaxis y prueba manual/documentada.

## Próximos pasos recomendados

- Añadir suite de tests de API y end-to-end.
- Añadir paginación backend real con `limit`/`offset` para listados muy grandes.
- Añadir auditoría detallada de cambios por entidad.
- Incorporar recuperación de contraseña y rotación de tokens.
- Mejorar diseño visual con sistema de componentes.
