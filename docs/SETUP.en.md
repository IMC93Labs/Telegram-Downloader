# Setup guide — English

[Español](SETUP.es.md) · [Home](../README.md)

## 1. Choose the Telegram connection

**Bot:** receive messages through a dedicated bot; the phone field stays empty.
**Personal account:** receive messages as your own account; requires your phone and login verification. Do not fill in a bot token in this mode.

## 2. Create or retrieve the bot

1. Open the official [@BotFather](https://t.me/BotFather) in Telegram.
2. Send `/newbot`, choose its display name and a username ending in `bot`.
3. Copy the full token, including the colon and everything after it. The numerical bot ID alone does not authenticate it.
4. Existing bot: use `/mybots`, select your bot and open **API Token** using the account that owns the bot. A lost token can be replaced using `/token`; update other applications using that bot if you replace it.

[Official BotFather guide](https://core.telegram.org/bots/features#botfather)

## 3. Add the bot to the group

1. Create a group or use an existing one.
2. Add the bot using its `@username`.
3. Make it an administrator so ordinary links are delivered to it. Check that it can send messages. For channels, grant publishing permission.
4. Send new test messages from your own account, not another bot.

An alternative for groups is disabling privacy mode through BotFather (`/setprivacy`) and adding the bot again; administrator setup is the simpler route for a dedicated download group. [Telegram bot FAQ](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get)

## 4. Obtain API ID and API Hash

1. Open [my.telegram.org/apps](https://my.telegram.org/apps).
2. Sign in with your phone number and the confirmation code received in Telegram.
3. If an application already exists, view its `api_id` and `api_hash`. Otherwise create an application by filling in its name, short name and platform.
4. Copy both values into the settings. They are different from the bot token and bot ID.

The current application uses MTProto through Pyrogram, so API ID/Hash are required with both account and bot login. [Telegram documentation](https://core.telegram.org/api/obtaining_api_id)

## 5. Obtain the group ID

1. Right-click a message in the target private group/channel and copy its message link.
2. In settings choose **Obtener ID desde enlace** and paste the link.
3. The supported format is `https://t.me/c/1234567890/12`; this example maps to `-1001234567890`.
4. Invitation links (`t.me/+...`) and public usernames do not contain a numerical ID and cannot be converted by this button. For these cases retrieve the numeric ID from an existing integration or known group configuration.
5. **Recordar ID guardado** restores the ID already configured on this PC. It does not search Telegram for new groups.

[Telegram message link formats](https://core.telegram.org/api/links#message-links)

## 6. Fill in and test Telegram

| Field | Bot connection | Personal account |
|---|---|---|
| API ID | Your API ID | Your API ID |
| API Hash | Your API Hash | Your API Hash |
| Teléfono | Empty | Phone with country code |
| Token del bot | Full token | Empty |
| ID grupo | Target group/channel ID | Target group/channel ID |

Use right-click → **Pegar** to paste. **Mostrar credenciales** reveals locally saved masked fields. Select **Guardar y reconectar Telegram**; this stops active downloads and restarts the application. Account login can request a code and two-step verification password.

Wait for both Telegram and group indicators to turn green. Send a new download link to the group and check the queue. Red group status with green Telegram means the login worked but group access/ID needs correction.

## 7. Optional: AllDebrid

1. Sign into [AllDebrid](https://alldebrid.com/) and check premium/trial status.
2. Open [API keys](https://alldebrid.com/apikeys/) and create or retrieve a key.
3. Paste it into the AllDebrid tab, test and save.
4. If an authorization email arrives, follow it and test again.
5. Expired premium requires renewal; a new key does not extend the subscription.
6. Emptying the key and saving disables this integration.

[Official key guide](https://help.alldebrid.com/en/faq/apikeys)

## 8. Optional: qBittorrent

1. Install [qBittorrent](https://www.qbittorrent.org/download) and keep it open.
2. Enable its **Web UI** under Tools → Options; choose a port and set username/password.
3. Verify browser login, usually at `http://localhost:8080` on the same PC. Use the actual address if you chose another port or HTTPS.
4. In the application's qBittorrent tab enable **Enviar torrents a qBittorrent** and enter the same address and credentials.
5. Select **Comprobar conexión**, then **Guardar y aplicar**. Changes apply to subsequent torrents without restarting.
6. Send a magnet link or `.torrent` file to the Telegram group. Check the torrent's progress in qBittorrent.

## Troubleshooting

- **Telegram red:** check API ID/Hash and token, or phone/login verification.
- **Group red:** check the numeric group ID, membership and administrator permissions.
- **No queued link:** send a new message, ensure it is the configured group and check the application's logs.
- **AllDebrid red:** check key, premium status, network access and authorization email.
- **qBittorrent red:** check it is running, Web UI is enabled and browser login succeeds.
- **Download error:** a web page URL may not be a direct file; check host support and sanitized logs.

Open the built-in **? Guía de configuración** for the same steps inside the application. Do not include credentials or session files in support requests.
