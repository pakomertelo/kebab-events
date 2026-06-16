# Kebab Events

Monorepo full stack para coordinación interna de eventos, clientes y trabajadores. El repositorio contiene el frontend estático, el backend Python y configuración lista para desplegar el frontend en Vercel y el backend con PostgreSQL gestionado en Render u otro host compatible.

## Estructura del monorepo

```text
.
├── apps/
│   ├── backend/
│   │   ├── app.py              # API REST, autenticación, migraciones, seed y servidor local
│   │   ├── requirements.txt    # Dependencias Python para producción
│   │   ├── Procfile            # Start command para hosts tipo Heroku/Railway
│   │   └── Dockerfile          # Imagen opcional para hosts Docker
│   └── frontend/
│       ├── index.html          # Entrada web estática
│       ├── config.js           # Config runtime del origen API
│       ├── config.example.js   # Ejemplo documentado para Vercel
│       └── assets/
│           ├── app.js          # Interfaz y cliente API
│           └── styles.css      # Estilos responsivos
├── packages/                   # Espacio reservado para código compartido futuro
├── render.yaml                 # Blueprint Render: web service + PostgreSQL
├── vercel.json                 # Rewrites/headers para frontend estático en Vercel
├── .env.example                # Variables locales y producción
└── package.json                # Scripts del monorepo
```

## Stack usado

- **Frontend:** HTML, CSS y JavaScript estático.
- **Backend:** Python `http.server` con API REST propia.
- **Base de datos local:** SQLite.
- **Base de datos producción:** PostgreSQL usando `DATABASE_URL`.
- **Autenticación:** token firmado HMAC con expiración de 8 horas.
- **Contraseñas:** PBKDF2-HMAC-SHA256 con salt por usuario.
- **Roles:** `ADMIN` y `WORKER` validados en backend.

## Requisitos previos

- Python 3.11 o superior recomendado.
- Node/npm opcional: se usa como lanzador de scripts.
- Para producción con PostgreSQL, instalar dependencias de `apps/backend/requirements.txt`.

## Instalación local

```bash
cp .env.example .env
npm run install:all
npm run db:reset
npm run dev
```

La aplicación queda disponible en:

- Web: <http://localhost:4000>
- API: <http://localhost:4000/api>

Variables locales principales:

```env
DATABASE_PATH=apps/backend/dev.db
JWT_SECRET=change-this-local-development-secret
PORT=4000
CORS_ORIGIN=http://localhost:4000
```

## Scripts útiles

```bash
npm run install:all     # Comprueba Python e instala dependencias backend
npm run db:migrate      # Crea tablas si no existen
npm run db:seed         # Carga datos de prueba
npm run db:reset        # Recrea base local y seed
npm run dev             # Arranca web + API en local
npm run build           # Verifica sintaxis Python
npm run vercel:build    # Copia frontend estático a dist/ para Vercel
```

Equivalentes directos:

```bash
python3 apps/backend/app.py migrate
python3 apps/backend/app.py seed
python3 apps/backend/app.py reset
python3 apps/backend/app.py serve
python3 -m py_compile apps/backend/app.py
```

## Deploy recomendado

### 1. Backend + DB en Render

El archivo `render.yaml` define:

- Un servicio web Python llamado `kebab-events-api`.
- Una base PostgreSQL llamada `kebab-events-db`.
- `DATABASE_URL` inyectado automáticamente desde la base.
- `JWT_SECRET` generado por Render.

Pasos:

1. Sube este repositorio a GitHub/GitLab.
2. En Render, elige **New → Blueprint**.
3. Selecciona el repositorio.
4. Render detectará `render.yaml`.
5. Crea el blueprint.
6. Cuando el servicio esté desplegado, abre una Shell/Job del backend y ejecuta:

```bash
python3 app.py migrate
python3 app.py seed
```

> Nota: `seed` carga datos de prueba. En producción real úsalo solo para demo inicial.

### 2. Frontend en Vercel

El frontend está en `apps/frontend` y se puede publicar como sitio estático.

Configuración del proyecto en Vercel:

- **Framework Preset:** Other
- **Build Command:** `npm run vercel:build`
- **Output Directory:** `dist`
- **Install Command:** vacío o `npm install`

Después de desplegar el backend, edita `apps/frontend/config.js` antes de desplegar o reemplázalo durante tu pipeline con la URL pública del backend:

```js
window.KEBAB_EVENTS_CONFIG = {
  API_BASE_URL: 'https://kebab-events-api.onrender.com'
};
```

El cliente construye las llamadas como `${API_BASE_URL}/api`. Si `API_BASE_URL` está vacío, usa `/api`, útil cuando frontend y backend se sirven juntos en local.

### 3. Otros hosts para el backend

También puedes desplegar `apps/backend` en Railway, Fly.io, DigitalOcean App Platform o cualquier host que soporte Python persistente.

Variables requeridas:

```env
DATABASE_URL=postgresql://user:password@host:5432/kebab_events
JWT_SECRET=un-secreto-largo-y-aleatorio
PORT=4000
CORS_ORIGIN=https://tu-frontend.vercel.app
```

Start command:

```bash
python3 app.py serve
```

Si el host usa el repo root como working directory:

```bash
python3 apps/backend/app.py serve
```

## Credenciales de prueba

Después de `npm run db:reset` o `python3 apps/backend/app.py seed`:

| Rol | Email | Contraseña |
| --- | --- | --- |
| ADMIN | `admin@kebab-events.local` | `Admin123!` |
| WORKER | `ana@kebab-events.local` | `Worker123!` |
| WORKER | `luis@kebab-events.local` | `Worker123!` |
| WORKER | `sara@kebab-events.local` | `Worker123!` |

## Funcionalidades principales

- Login funcional con token de sesión.
- Protección de rutas API por autenticación y rol.
- CRUD de clientes, trabajadores, usuarios y eventos para administradores.
- Asignación, reserva, promoción y retirada de trabajadores en eventos.
- Dashboard administrativo con métricas operativas y económicas.
- Vista de eventos disponibles, mis eventos, agenda y ganancias para trabajadores.
- Soporte local SQLite y producción PostgreSQL mediante `DATABASE_URL`.

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

## Notas de producción

- Cambia siempre `JWT_SECRET` en producción.
- Restringe `CORS_ORIGIN` al dominio final de Vercel cuando salgas de demo.
- Usa PostgreSQL gestionado para datos persistentes.
- No uses `seed` con datos demo después de tener datos reales.
- Configura CORS o proxy si decides servir frontend y backend desde dominios diferentes y ampliar el backend más allá del flujo actual.
