# Telegram Downloader

**Turn a Telegram group into a download queue for your Windows PC.**

[English](README.md) · [Español](README.es.md) · [Download / Descargar](https://github.com/IMC93Labs/Telegram-Downloader/releases/latest)

![Windows](https://img.shields.io/badge/platform-Windows%2010%20%2F%2011-blue) ![Version](https://img.shields.io/badge/version-1.25-67b7ff) ![Python](https://img.shields.io/badge/Python-3.11-3776AB)

Send a link or forward a file to your configured Telegram group. Telegram Downloader receives it and adds it to the queue on your PC. It can use **AllDebrid** for supported premium links and send **magnet links and torrents to qBittorrent**.

> The application interface is currently in Spanish. Documentation and setup instructions are available in English and Spanish.

![Download manager with simulated downloads](docs/images/downloads.png)

## What it does

| Feature | How it works |
|---|---|
| Telegram intake | Connect your own account or a bot to a group/channel. |
| Download queue | Reorder, stop, retry, remove and clear finished downloads. |
| Concurrent downloads | Adjust the number of simultaneous downloads from the main window. |
| Direct downloads | Receive Telegram files and HTTP/HTTPS download links. |
| AllDebrid integration | Unlock supported links when your key and premium/trial account are valid. |
| qBittorrent integration | Forward magnet links and `.torrent` files to a running qBittorrent Web UI. |
| Live information | View speed, progress, state, file sizes and a speed graph. |
| Compact layout | Columns adapt to the window width; only the download list scrolls. Hover for full details. |
| Connection settings | Change credentials, test services and retrieve a group ID from a compatible message link. |
| Built-in guide | Follow visual steps with official links and troubleshooting advice. |
| Desktop controls | Optional tray minimization and Windows startup. |

## Download and install

1. Open the [latest release](https://github.com/IMC93Labs/Telegram-Downloader/releases/latest).
2. Download **`TelegramDownloader_Setup_v1.25.exe`** for installation, or **`TelegramDownloader_v1.25.exe`** to run the standalone executable.
3. Launch the application and open **Ajustes → Conexiones**.
4. Follow **? Guía de configuración** or the [English setup guide](docs/SETUP.en.md).

The PC and application must remain running to receive new messages and perform downloads. qBittorrent must also be running when you use torrent forwarding. The standalone EXE still stores settings in your Windows user profile; it is not a folder-contained portable installation.

## Configure your services

### Telegram — required

For a bot connection, create a bot with **@BotFather**, copy its **full token**, add it to your group and make it an administrator so it can receive ordinary messages. Obtain **API ID and API Hash** from [my.telegram.org/apps](https://my.telegram.org/apps). This application uses Pyrogram/MTProto, so those two values are required even when using a bot.

Enter API ID, API Hash, bot token and **group ID** in the Telegram settings. Leave the phone field empty for a bot. To use your personal account instead, leave the bot token empty and enter your phone number with country code; Telegram may request a login code and two-step verification password.

**Telegram/API ID and group access have separate status indicators:** green means connected, red means disconnected, missing setup or access error. Logging into Telegram does not automatically grant access to your group.

### AllDebrid — optional

Create or retrieve a key from [AllDebrid API keys](https://alldebrid.com/apikeys/), paste it into the AllDebrid settings and use **Comprobar clave → Guardar y aplicar**. An expired subscription must be renewed on AllDebrid; changing a key does not renew premium.

### qBittorrent — optional

Enable **Web UI** in qBittorrent, set its username/password and verify the address in your browser. Enter the same address and credentials in the application's qBittorrent tab, enable torrent forwarding, test and save. For a typical local configuration the address is `http://localhost:8080`.

**Enviado a qBittorrent** means the torrent was handed over; monitor its actual download progress inside qBittorrent.

![qBittorrent connection settings, empty demonstration fields](docs/images/connections.png)

![Visual setup guide](docs/images/guide.png)

## Privacy and sharing

- Credentials, Telegram sessions, settings and history are stored locally under **`%LOCALAPPDATA%\TelegramDownloader`**. Downloaded files go to the folder you select.
- Saved credentials are **not encrypted**. Protect the Windows account and do not share the data directory or session files.
- The published EXE was inspected for embedded private configuration, session files, known developer credentials and local profile paths: none were found. See the [release privacy review](docs/PRIVACY.en.md).
- Screenshots use simulated downloads and demonstration data.
- Share release binaries, not a configured data folder or a development folder containing `.env`/`.session` files.
- Telegram, AllDebrid and qBittorrent receive requests necessary for their respective integrations. This is not an offline application.

## Development

Use **Python 3.11** on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r src/requirements.txt
python src/auto.py
```

Source execution also uses your local application data. For isolated development or tests, set `TELEGRAM_DOWNLOADER_DATA_DIR` and `DOWNLOAD_PATH` to separate directories.

Run tests:

```powershell
cd src
python -m unittest test_application -q
```

Build the Windows EXE:

```powershell
cd src
python -m PyInstaller --noconfirm TelegramDownloader_v1.25.spec
```

Optional installer: install [Inno Setup](https://jrsoftware.org/isinfo.php) and compile `src/TelegramDownloader_v1.25.iss`. Release binaries are attached to GitHub Releases rather than committed to the source tree.

## Limits and support

AllDebrid support depends on the host and your account. A normal web page URL is not always a direct downloadable file. Resume support depends on the server. Bot permissions and Telegram restrictions affect what messages/files can be received.

The release passed **27 automated tests**, plus compiled EXE startup and privacy checks. Those checks do not guarantee compatibility with every host or account.

Use [Issues](https://github.com/IMC93Labs/Telegram-Downloader/issues) for bugs and suggestions. Include the version, steps to reproduce and sanitized logs. **Never post passwords, tokens, API hashes or session files.**

[Changelog / Historial](CHANGELOG.md) · [Detailed setup / Configuración](docs/SETUP.en.md) · [Español](README.es.md)
