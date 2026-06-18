# Kebab Events Static

Aplicación web estática para coordinar eventos, clientes y trabajadores. Esta versión está preparada para desplegarse **únicamente en Vercel** y no depende de backend, API externa ni base de datos.

Los datos se guardan en `localStorage` del navegador, por lo que es ideal para demos, prototipos, presentaciones y pruebas funcionales sin infraestructura adicional.

## Stack

- HTML, CSS y JavaScript estático.
- Persistencia local en el navegador mediante `localStorage`.
- Deploy estático en Vercel desde `dist/`.
- Sin backend, sin PostgreSQL, sin SQLite y sin variables de entorno obligatorias.

## Estructura relevante

```text
.
├── apps/frontend/
│   ├── index.html
│   ├── config.js
│   └── assets/
│       ├── app.js
│       └── styles.css
├── docs/deploy.md
├── package.json
└── vercel.json
```

## Desarrollo local

```bash
npm run dev
```

Abre <http://localhost:4000>.

## Build para Vercel

```bash
npm run build
```

El build copia `apps/frontend` a `dist/`, que es el directorio que Vercel debe publicar.

## Despliegue en Vercel

1. Sube el repositorio a GitHub, GitLab o Bitbucket.
2. En Vercel, crea un proyecto nuevo e importa el repositorio.
3. Configura el proyecto así:
   - **Framework Preset:** `Other`
   - **Install Command:** vacío o `npm install`
   - **Build Command:** `npm run build`
   - **Output Directory:** `dist`
4. Despliega.

No necesitas configurar variables de entorno, bases de datos, servicios serverless ni un backend externo.

## Credenciales de demo

| Rol | Email | Contraseña |
| --- | --- | --- |
| ADMIN | `admin@kebab-events.local` | `Admin123!` |
| WORKER | `ana@kebab-events.local` | `Worker123!` |
| WORKER | `luis@kebab-events.local` | `Worker123!` |
| WORKER | `sara@kebab-events.local` | `Worker123!` |

## Persistencia y reseteo de datos

La aplicación guarda cambios en el navegador con la clave `kebabEventsStaticDb`. Para resetear la demo, abre DevTools y ejecuta:

```js
localStorage.removeItem('kebabEventsStaticDb');
localStorage.removeItem('token');
location.reload();
```

## Limitaciones intencionadas

- Los datos son locales a cada navegador y dispositivo.
- No hay sincronización multiusuario real.
- El login es de demostración y no debe usarse como seguridad de producción.
- Si necesitas datos compartidos o autenticación real, tendrás que añadir un backend/API en otra versión.
