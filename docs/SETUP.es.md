# Guía de configuración — Español

[English](SETUP.en.md) · [Inicio](../README.es.md)

## 1. Elige cómo conectar Telegram

**Bot:** recibe mensajes con un bot dedicado; deja el teléfono vacío.
**Cuenta personal:** utiliza tu propia cuenta; introduce teléfono y completa la verificación de acceso. Deja vacío el token del bot.

## 2. Crea o recupera el bot

1. Abre el [@BotFather oficial](https://t.me/BotFather).
2. Envía `/newbot`, elige nombre y un usuario terminado en `bot`.
3. Copia el token completo, incluidos los dos puntos y la parte posterior. El ID numérico del bot por sí solo no sirve.
4. Si ya tienes un bot: `/mybots` → tu bot → **API Token**, desde su cuenta propietaria. Si lo has perdido, `/token` permite reemplazarlo; actualiza otras aplicaciones que utilicen ese bot si cambias el token.

[Guía oficial de BotFather](https://core.telegram.org/bots/features#botfather)

## 3. Añade el bot al grupo

1. Crea un grupo o utiliza uno existente.
2. Añade el bot por su `@usuario`.
3. Hazlo administrador para recibir enlaces normales y comprueba que puede enviar mensajes. En canales, concede permiso para publicar.
4. Envía las pruebas desde tu cuenta, no desde otro bot.

En grupos también se puede desactivar el modo privado con `/setprivacy` en BotFather y volver a añadir el bot. Para un grupo dedicado de descargas, hacerlo administrador es la opción más sencilla. [FAQ de Telegram](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get)

## 4. Obtén API ID y API Hash

1. Abre [my.telegram.org/apps](https://my.telegram.org/apps).
2. Inicia sesión con teléfono y código recibido en Telegram.
3. Consulta `api_id` y `api_hash` de tu aplicación existente o crea una completando nombre, nombre corto y plataforma.
4. Copia ambos en los ajustes. No son el ID ni el token del bot.

Esta aplicación utiliza MTProto mediante Pyrogram: necesita API ID/Hash con bot y con cuenta personal. [Documentación de Telegram](https://core.telegram.org/api/obtaining_api_id)

## 5. Obtén el ID del grupo

1. Botón derecho sobre un mensaje del grupo/canal privado → copiar enlace.
2. Pulsa **Obtener ID desde enlace** en los ajustes y pégalo.
3. Se admite `https://t.me/c/1234567890/12`; el ejemplo corresponde a `-1001234567890`.
4. Los enlaces de invitación (`t.me/+...`) y nombres públicos no contienen el ID numérico. Recupera ese ID de una integración existente o una configuración conocida del grupo.
5. **Recordar ID guardado** recupera el configurado en este PC; no busca grupos nuevos en Telegram.

[Formatos de enlaces de mensaje](https://core.telegram.org/api/links#message-links)

## 6. Introduce los datos y comprueba Telegram

| Campo | Con bot | Con cuenta personal |
|---|---|---|
| API ID | Tu API ID | Tu API ID |
| API Hash | Tu API Hash | Tu API Hash |
| Teléfono | Vacío | Teléfono con prefijo internacional |
| Token del bot | Token completo | Vacío |
| ID grupo | ID del grupo/canal | ID del grupo/canal |

Puedes pegar con botón derecho → **Pegar**. **Mostrar credenciales** revela los campos ocultos guardados en este PC. Pulsa **Guardar y reconectar Telegram**: detiene las descargas activas y reinicia. Con cuenta personal se puede solicitar código y contraseña de verificación en dos pasos.

Espera a que Telegram y Grupo estén verdes. Envía un enlace nuevo al grupo y comprueba la cola. Telegram verde y Grupo rojo significa que el acceso a Telegram funciona, pero hay que revisar el ID o los permisos del grupo.

## 7. Opcional: AllDebrid

1. Entra en [AllDebrid](https://alldebrid.com/) y comprueba la suscripción premium/prueba.
2. Abre [claves API](https://alldebrid.com/apikeys/) y crea o recupera una.
3. Pégala en su pestaña, comprueba y guarda.
4. Si recibes un correo de autorización, sigue sus indicaciones y comprueba otra vez.
5. Premium caducado exige renovar la suscripción; cambiar la clave no la prolonga.
6. Para desactivar el servicio, deja la clave vacía y guarda.

[Ayuda oficial de claves](https://help.alldebrid.com/en/faq/apikeys)

## 8. Opcional: qBittorrent

1. Instala [qBittorrent](https://www.qbittorrent.org/download) y déjalo abierto.
2. En Herramientas → Opciones activa la **interfaz web**, elige puerto y configura usuario/contraseña.
3. Comprueba el acceso desde el navegador, normalmente `http://localhost:8080` en el mismo PC. Usa la dirección real si cambiaste puerto o HTTPS.
4. En su pestaña de Telegram Downloader marca **Enviar torrents a qBittorrent** e introduce dirección, usuario y contraseña.
5. Pulsa **Comprobar conexión** y **Guardar y aplicar**. Se aplica a los siguientes torrents sin reiniciar.
6. Envía un magnet o archivo `.torrent` al grupo. El progreso real del torrent se consulta en qBittorrent.

## Si algo no funciona

- **Telegram rojo:** comprueba API ID/Hash, token o teléfono y verificación de acceso.
- **Grupo rojo:** comprueba el ID numérico, pertenencia y permisos de administrador.
- **No aparece el enlace:** envía un mensaje nuevo al grupo configurado y revisa los registros.
- **AllDebrid rojo:** revisa clave, premium, red y correo de autorización.
- **qBittorrent rojo:** comprueba que está abierto, interfaz web activa y acceso correcto desde el navegador.
- **Error de descarga:** una página web no siempre es un archivo directo; revisa compatibilidad y registros sin información sensible.

La ayuda **? Guía de configuración** incluye estos pasos dentro de la aplicación. No compartas credenciales ni sesiones al pedir soporte.
