# Configuración de redes sociales

Sin estas claves, la app usa **mock mode** — simula la publicación y devuelve URLs falsas. Ideal para desarrollo y demos.

## YouTube Shorts

- Tiempo: ~1 día
- Costo: Gratis
- Límite: 10,000 unidades/día

1. Ir a https://console.cloud.google.com/
2. Crear proyecto → habilitar YouTube Data API v3
3. Crear credenciales OAuth 2.0
4. Configurar redirect URI: `http://localhost:8000/api/social/youtube/callback`
5. Agregar a `.env`:
   ```
   YOUTUBE_CLIENT_ID=...
   YOUTUBE_CLIENT_SECRET=...
   ```

## TikTok

- Tiempo: 1-2 semanas (revisión)
- Costo: Gratis
- Límite: 5 publicaciones/día/usuario

1. Ir a https://developers.tiktok.com/
2. Crear app → solicitar scopes `video.publish`, `video.upload`
3. Configurar redirect URI: `http://localhost:8000/api/social/tiktok/callback`
4. Agregar a `.env`:
   ```
   TIKTOK_CLIENT_KEY=...
   TIKTOK_CLIENT_SECRET=...
   ```

## Instagram Reels

- Tiempo: 3-5 días (revisión)
- Costo: Gratis
- Límite: 50 publicaciones/día

1. Ir a https://developers.facebook.com/
2. Crear app de tipo "Business" → agregar Instagram Graph API
3. Configurar redirect URI: `http://localhost:8000/api/social/instagram/callback`
4. Agregar a `.env`:
   ```
   INSTAGRAM_CLIENT_ID=...
   INSTAGRAM_CLIENT_SECRET=...
   ```

## Referencia del código

Ver `backend/app/services/social_publisher.py` para la implementación completa del flujo OAuth + publicación.
