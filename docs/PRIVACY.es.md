# Revisión de privacidad de la publicación

El EXE de Windows v1.25 se ha inspeccionado antes de publicarlo el 2026-10-11.

## Comprobaciones realizadas

- Enumeración del archivo PyInstaller y sus entradas/módulos Python descomprimidos: **6.751 entradas comprobadas**.
- Búsqueda de credenciales privadas conocidas de la configuración local y referencias al perfil de Windows: **sin coincidencias**.
- Búsqueda de `.env` privado, sesiones autenticadas `.session`, conexiones, configuración, historial, módulos de pruebas y datos de revisión local: **no incluidos**.
- Revisión de la lista de archivos del instalador: solo ejecutable, `.env.example` vacío e icono de la aplicación.
- Repositorio preparado con una lista explícita de código y recursos; excluye datos locales, entornos, cachés y binarios anteriores.
- Capturas realizadas con datos simulados, sin rutas del perfil personal ni credenciales reales.

Es una inspección de esta versión frente a información privada conocida; no es una auditoría formal de seguridad ni garantiza detectar cualquier información posible. Se incluyen intencionadamente el nombre de la aplicación, su marca y dependencias externas.

## Datos locales tras instalar

Las credenciales y sesiones se guardan en `%LOCALAPPDATA%\TelegramDownloader`. Las credenciales no están cifradas. No compartas esa carpeta, `.env`, `connections.json` ni sesiones autenticadas. La aplicación realiza peticiones a Telegram, AllDebrid y qBittorrent cuando se utilizan sus funciones.

Los archivos publicados incluyen `SHA256SUMS.txt` para comprobar integridad. Los hashes identifican los archivos, pero no son una firma del editor.
