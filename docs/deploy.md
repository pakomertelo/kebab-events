# Despliegue en Vercel

Esta versión de Kebab Events es 100% estática y se despliega solo en Vercel. No requiere backend, base de datos ni variables de entorno.

## Configuración Vercel

- **Framework Preset:** `Other`
- **Install Command:** vacío o `npm install`
- **Build Command:** `npm run build`
- **Output Directory:** `public`

## Pasos

1. Publica el repositorio en GitHub, GitLab o Bitbucket.
2. Entra en Vercel y pulsa **Add New → Project**.
3. Importa el repositorio.
4. Usa la configuración indicada arriba.
5. Pulsa **Deploy**.

## Comprobación posterior

1. Abre la URL generada por Vercel.
2. Inicia sesión como administrador:
   - Email: `admin@kebab-events.local`
   - Contraseña: `Admin123!`
3. Crea o edita un evento.
4. Cierra sesión y entra como trabajador:
   - Email: `ana@kebab-events.local`
   - Contraseña: `Worker123!`
5. Comprueba que puedes apuntarte a eventos disponibles.

## Persistencia

Todos los cambios se guardan en `localStorage`. Para resetear datos de demo en un navegador:

```js
localStorage.removeItem('kebabEventsStaticDb');
localStorage.removeItem('token');
location.reload();
```
