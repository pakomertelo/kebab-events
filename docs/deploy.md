# Guía de despliegue

## Arquitectura recomendada

- Vercel: frontend estático desde `apps/frontend`.
- Render: backend Python desde `apps/backend`.
- Render PostgreSQL: base de datos gestionada conectada por `DATABASE_URL`.

## Checklist

1. Crear repo remoto.
2. Crear Blueprint en Render con `render.yaml`.
3. Ejecutar migración y seed inicial en Render.
4. Copiar la URL pública del backend.
5. Configurar `apps/frontend/config.js` con `API_BASE_URL`.
6. Crear proyecto Vercel con build `npm run vercel:build` y output `dist`.
7. Probar login y endpoints `/api/auth/login` y `/api/auth/me`.

## Variables

Backend:

```env
DATABASE_URL=postgresql://...
JWT_SECRET=...
PORT=4000
CORS_ORIGIN=https://tu-frontend.vercel.app
```

Frontend:

```js
window.KEBAB_EVENTS_CONFIG = {
  API_BASE_URL: 'https://kebab-events-api.onrender.com'
};
```
