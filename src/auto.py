"""
auto.py - Telegram Downloader
Gestor de descargas de Telegram con GUI estilo gamer + cola con prioridad
- Descarga media reenviada al canal
- Descarga URLs http/https enviadas al canal
- Usa AllDebrid si se configura ALLDEBRID_API_KEY
- Integra qBittorrent para .torrent y magnet links
- GUI con columna de origen (Telegram / HTTP / AllDebrid / Torrent)

Requisitos:

    pip install -U pyrogram tgcrypto python-dotenv requests
    pip install pystray pillow
"""

import os
import sys
import time
import math
import webbrowser
from connection_help import show_connection_help
from app_support import group_id_from_link

import asyncio

_ROOT_REF = None
_ACTIVATE_PENDING = False

import threading
import json
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from urllib.parse import urlparse
from pathlib import Path
import builtins
import socket
import queue
import shutil
import hashlib
import subprocess
import tempfile

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, font as tkfont

import requests
from pyrogram import Client, filters, enums
from dotenv import load_dotenv
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PasswordHashInvalid
from ui_support import install_entry_context_menus, entry_context_menu, FlowFrame, ScrollableFrame, TreeTooltip, wrap_labels, configure_dark_controls, dark_titlebar, install_dark_titlebar
from http_transfer import transfer_http
from app_support import atomic_json, read_json, safe_filename, is_debrid_url, validate_connections, check_alldebrid

# Opcional: registro de Windows para arranque automático
if os.name == "nt":
    try:
        import winreg
    except Exception:
        winreg = None
else:
    winreg = None

# Opcional: icono en bandeja del sistema
try:
    import pystray
    from PIL import Image
except Exception:
    pystray = None
    Image = None

# Registro interno de mensajes para mostrarlos en la GUI
_log_buffer: List[str] = []
_log_lock = threading.Lock()

import builtins as _builtins
_original_print = _builtins.print


def log_print(*args, **kwargs):
    text = " ".join(str(a) for a in args)
    for key in (globals().get("ALLDEBRID_API_KEY"), globals().get("BOT_TOKEN"), globals().get("API_HASH")):
        if key:
            text = text.replace(key, "[oculto]")
    with _log_lock:
        _log_buffer.append(text)
        # Limitar a las últimas 5000 líneas para no crecer infinito
        if len(_log_buffer) > 5000:
            del _log_buffer[:-5000]
    if sys.stdout is not None:
        _original_print(text, **kwargs)


def get_log_lines() -> List[str]:
    with _log_lock:
        return list(_log_buffer)


# Redefinir print para que todo lo que se imprime se guarde en el registro interno
_builtins.print = log_print
print = log_print


# ==========================
# INFORMACIÓN DE LA APLICACIÓN
# ==========================
APP_NAME = "Telegram Downloader"
APP_VERSION = "1.25"
APP_NAME_FULL = f"{APP_NAME} v{APP_VERSION}"


# ==========================
# SINGLE INSTANCE (Windows/Local)
# ==========================
# Evita que el programa se abra 2 veces (por ejemplo al iniciar Windows).
# Si se lanza una segunda instancia, esta solo activa la ventana de la primera.
SINGLE_INSTANCE_HOST = "127.0.0.1"
SINGLE_INSTANCE_PORT = 47651

GUI_APP = None  # se asigna en DownloadGUI.__init__
_single_instance_server_sock = None


def activate_gui_window():
    """Trae la ventana al frente (si está minimizada o en bandeja)."""
    global GUI_APP
    app = GUI_APP
    if not app or not getattr(app, "root", None):
        return

    def _do():
        try:
            app.root.deiconify()
            app.root.state("normal")
            app.root.lift()
            app.root.focus_force()
        except Exception:
            pass

    try:
        GUI_EVENTS.put(_do)
    except Exception:
        pass


def _single_instance_server():
    global _single_instance_server_sock
    sock = _single_instance_server_sock
    if sock is None:
        return
    while True:
        try:
            conn, _ = sock.accept()
            conn.settimeout(1)
            try:
                _ = conn.recv(32)
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            activate_gui_window()
        except Exception:
            break


def ensure_single_instance() -> bool:
    """Devuelve True si es la instancia principal; False si ya había una y se ha activado."""
    global _single_instance_server_sock
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((SINGLE_INSTANCE_HOST, SINGLE_INSTANCE_PORT))
        s.listen(1)
        _single_instance_server_sock = s
        t = threading.Thread(target=_single_instance_server, daemon=True)
        t.start()
        return True
    except OSError:
        # Ya hay una instancia escuchando
        try:
            c = socket.create_connection((SINGLE_INSTANCE_HOST, SINGLE_INSTANCE_PORT), timeout=0.5)
            try:
                c.sendall(b"ACTIVATE")
            finally:
                c.close()
        except Exception:
            pass
        return False

# ==========================
# CARGA DE CONFIGURACIÓN
# ==========================

if __name__ == "__main__" and "--self-test" not in sys.argv:
    if not ensure_single_instance():
        sys.exit(0)

# BASE_DIR funciona tanto con script normal como con exe de PyInstaller
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent

# Nos aseguramos de que el directorio de trabajo sea la carpeta del script/exe
os.chdir(BASE_DIR)

IMAGES_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR)) / "imagenes"
DATA_DIR = Path(os.environ.get("TELEGRAM_DOWNLOADER_DATA_DIR") or
                str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "TelegramDownloader"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
# Migrar una instalación anterior sin modificar ni borrar sus archivos.
for legacy_name in (() if (DATA_DIR / "migration_complete.json").exists() else (".env", "session.session", "session.session-journal", "config.json", "downloads_state.json")):
    old = BASE_DIR / legacy_name
    new = DATA_DIR / legacy_name
    if old.is_file() and not new.exists() and not os.environ.get("TELEGRAM_DOWNLOADER_DATA_DIR"):
        shutil.copy2(old, new)
atomic_json(DATA_DIR / "migration_complete.json", {"complete": True})
ENV_PATH = DATA_DIR / ".env"
CONNECTIONS_FILE = DATA_DIR / "connections.json"

# Cargar SIEMPRE el .env que está junto al script/exe y sobrescribir variables previas
load_dotenv(ENV_PATH, override=True)
CONNECTIONS = read_json(CONNECTIONS_FILE, {})
for key, value in CONNECTIONS.items():
    os.environ[key] = str(value)

def env_int(name, default=0):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default

API_ID = env_int("API_ID")
API_HASH = os.environ.get("API_HASH", "")
PHONE = os.environ.get("PHONE")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL = env_int("CHANNEL_ID")
TELEGRAM_STATUS = "Desconectado"
TELEGRAM_GROUP_STATUS = "No conectado"
SHUTDOWN = threading.Event()
GUI_EVENTS = queue.Queue()
RESTART_REQUESTED = False

CONFIG_FILE = DATA_DIR / "config.json"
DOWNLOADS_STATE_FILE = DATA_DIR / f"downloads_state_{CHANNEL}.json"
if not DOWNLOADS_STATE_FILE.exists() and (DATA_DIR / "downloads_state.json").exists():
    os.replace(DATA_DIR / "downloads_state.json", DOWNLOADS_STATE_FILE)

# AllDebrid (opcional)
ALLDEBRID_API_KEY = (
    os.environ.get("ALLDEBRID_API_KEY")
    or os.environ.get("ALLDEBRID_APIKEY")
    or ""
).strip() or None

# qBittorrent (opcional)
USE_QBITTORRENT = os.environ.get("USE_QBITTORRENT", "false").strip().lower() in (
    "1", "true", "yes", "on"
)
QBITTORRENT_URL = (os.environ.get("QBITTORRENT_URL") or "").strip().rstrip("/")
QBITTORRENT_USERNAME = (os.environ.get("QBITTORRENT_USERNAME") or "").strip()
QBITTORRENT_PASSWORD = (os.environ.get("QBITTORRENT_PASSWORD") or "").strip()

_qb_session: Optional[requests.Session] = None

# Estado de servicios externos para mostrar en la GUI
ALLDEBRID_CONNECTED: bool = False
ALLDEBRID_STATUS_MSG: str = "No configurado"

QBITTORRENT_CONNECTED: bool = False
QBITTORRENT_STATUS_MSG: str = "No configurado"


def qbittorrent_available() -> bool:
    return (
        USE_QBITTORRENT
        and bool(QBITTORRENT_URL)
        and bool(QBITTORRENT_USERNAME)
        and bool(QBITTORRENT_PASSWORD)
    )


def debug_log_alldebrid_key():
    if not ALLDEBRID_API_KEY:
        print("[AD] No hay API key de AllDebrid cargada desde .env")
        return
    print("[AD] Clave configurada (oculta).")


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


_config = load_config()

# ========= NUEVOS VALORES POR DEFECTO =========
# Por defecto SIEMPRE: C:\Telegram Downloader\Descargas
DEFAULT_DOWNLOAD_PATH = os.environ.get("DOWNLOAD_PATH") or str(Path.home() / "Downloads" / "Telegram Downloader")
DEFAULT_MAX_PARALLEL = max(1, min(10, env_int("MAX_PARALLEL", 4)))

# Si en config.json hay una ruta anterior del estilo C:\TelegramAuto\..., la ignoramos
stored_path = _config.get("download_path")
if stored_path:
    norm_stored = os.path.normpath(stored_path)
    lower_stored = norm_stored.lower()
    if "telegramauto" in lower_stored:
        stored_path = None
else:
    stored_path = None

DOWNLOAD_PATH = stored_path or DEFAULT_DOWNLOAD_PATH
try:
    MAX_PARALLEL = max(1, min(10, int(_config.get("max_parallel", DEFAULT_MAX_PARALLEL))))
except (TypeError, ValueError):
    MAX_PARALLEL = DEFAULT_MAX_PARALLEL
WINDOW_GEOMETRY = _config.get("window_geometry", "1150x650")
DISPLAYCOLUMNS = _config.get("displaycolumns", None)
COLUMN_WIDTHS = _config.get("column_widths", {})

MINIMIZE_TO_TRAY = bool(_config.get("minimize_to_tray", False))
START_WITH_WINDOWS = bool(_config.get("start_with_windows", False))
START_MINIMIZED = bool(_config.get("start_minimized", False))
SHOW_SPEED_GRAPH = bool(_config.get("show_speed_graph", True))

try:
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
except OSError:
    DOWNLOAD_PATH = str(DATA_DIR / "Descargas")
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)


async def ask_telegram(prompt, secret=False):
    result = queue.Queue()
    GUI_EVENTS.put(lambda: result.put(simpledialog.askstring(
        "Conectar Telegram", prompt, show="*" if secret else None, parent=GUI_APP.root)))
    while not SHUTDOWN.is_set():
        try:
            value = result.get_nowait()
            if not value:
                raise RuntimeError("Inicio de sesión cancelado. Abre Conexiones para volver a conectar.")
            return value.strip()
        except queue.Empty:
            await asyncio.sleep(0.1)
    raise RuntimeError("Aplicación cerrándose")


class DesktopClient(Client):
    async def authorize(self):
        if BOT_TOKEN:
            return await self.sign_in_bot(BOT_TOKEN)
        phone = PHONE or await ask_telegram("Número de teléfono con prefijo internacional:")
        sent = await self.send_code(phone)
        for _ in range(3):
            code = await ask_telegram("Introduce el código que has recibido en Telegram:", True)
            try:
                user = await self.sign_in(phone, sent.phone_code_hash, code)
                if not hasattr(user, "id"):
                    raise RuntimeError("La cuenta debe estar registrada previamente en Telegram.")
                return user
            except PhoneCodeInvalid:
                continue
            except SessionPasswordNeeded:
                for _ in range(3):
                    try:
                        return await self.check_password(await ask_telegram("Contraseña de verificación en dos pasos:", True))
                    except PasswordHashInvalid:
                        continue
                raise RuntimeError("Contraseña de Telegram incorrecta.")
        raise RuntimeError("Código de Telegram incorrecto.")

app = DesktopClient(
    os.environ.get("SESSION_NAME", "session"),
    api_id=API_ID,
    api_hash=API_HASH,
    phone_number=PHONE,
    bot_token=BOT_TOKEN or None,
    workers=8,
    max_concurrent_transmissions=4,
    workdir=str(DATA_DIR),
)

# ==========================
# MODELO DESCARGAS
# ==========================

@dataclass
class DownloadItem:
    message_id: int
    filename: str
    status: str = "En cola"   # En cola, Descargando, Completado, Error, Detenido
    progress: float = 0.0
    error: Optional[str] = None
    total_bytes: int = 0
    downloaded_bytes: int = 0
    started_at: float = field(default_factory=time.time)
    source: str = "telegram"  # telegram, http, alldebrid, torrent
    dest_path: str = ""


download_items: List[DownloadItem] = []
items_by_id: Dict[int, DownloadItem] = {}
items_lock = threading.Lock()

_progress_stats: Dict[int, dict] = {}
_message_names: Dict[int, str] = {}
_inst_speeds: Dict[int, float] = {}

current_max_parallel = MAX_PARALLEL
_active_downloads = 0
_CANCEL_FLAGS: Dict[int, bool] = {}
_download_tasks: Dict[int, asyncio.Task] = {}
_state_lock = threading.RLock()
_reserved_paths = set()
_path_lock = threading.Lock()


def schedule_download(message_id, coroutine):
    existing = _download_tasks.get(message_id)
    if existing and not existing.done():
        coroutine.close()
        return
    task = asyncio.create_task(coroutine)
    _download_tasks[message_id] = task
    def finished(completed):
        if _download_tasks.get(message_id) is completed:
            _download_tasks.pop(message_id, None)
        if not completed.cancelled() and completed.exception():
            print(f"[!] Tarea de descarga: {completed.exception()}")
    task.add_done_callback(finished)

# ==========================
# ESTADO PERSISTENTE DESCARGAS
# ==========================

def save_download_state():
    try:
        with _state_lock:
            with items_lock:
                data = [asdict(it) for it in download_items]
            atomic_json(DOWNLOADS_STATE_FILE, data)
    except Exception as e:
        print(f"[!] Error guardando estado de descargas: {e}")


def load_download_state():
    if not os.path.exists(DOWNLOADS_STATE_FILE):
        return

    try:
        with open(DOWNLOADS_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[!] Error cargando estado de descargas: {e}")
        return

    with items_lock:
        download_items.clear()
        items_by_id.clear()

        for entry in data:
            try:
                item = DownloadItem(
                    message_id=entry.get("message_id"),
                    filename=entry.get("filename", f"file_{entry.get('message_id')}"),
                    status=entry.get("status", "En cola"),
                    progress=float(entry.get("progress", 0.0)),
                    error=entry.get("error"),
                    total_bytes=int(entry.get("total_bytes", 0)),
                    downloaded_bytes=int(entry.get("downloaded_bytes", 0)),
                    started_at=float(entry.get("started_at", time.time())),
                    source=entry.get("source", "telegram"),
                    dest_path=entry.get("dest_path", ""),
                )
            except Exception:
                continue

            if item.status not in ("Completado", "Enviado a qBittorrent", "Detenido", "Error"):
                item.status = "Error"
                if not item.error:
                    item.error = "Interrumpido al cerrar la aplicación"

            if item.total_bytes and item.downloaded_bytes:
                item.progress = min(100.0, (item.downloaded_bytes / item.total_bytes) * 100.0)

            items_by_id[item.message_id] = item
            download_items.append(item)

# ==========================
# CONCURRENCIA / PRIORIDAD
# ==========================

# Límite por tipo de descarga para evitar inestabilidad con colas largas / muchas transferencias.
_MAX_BY_SOURCE = {
    "telegram": 3,
    "http": 3,
    "alldebrid": 3,
}
_active_by_source = {"telegram": 0, "http": 0, "alldebrid": 0}


def _get_source_for(message_id: int, default: str = "telegram") -> str:
    with items_lock:
        it = items_by_id.get(message_id)
        if it and getattr(it, "source", None):
            s = str(it.source).lower()
            if s == "alldebrid":
                return "http"
            if s in _MAX_BY_SOURCE:
                return s
            if s == "torrent":
                return "http"
        return default


async def acquire_slot(message_id: int, source: str):
    global _active_downloads, current_max_parallel

    source = (source or "telegram").lower()
    if source not in _MAX_BY_SOURCE:
        source = "telegram"

    while True:
        allowed = False
        with items_lock:
            item = items_by_id.get(message_id)
            if SHUTDOWN.is_set() or not item or item.status != "En cola" or _CANCEL_FLAGS.get(message_id):
                return False
            first_waiting = next((it for it in download_items if it.status == "En cola"
                                  and _active_by_source.get(_get_queue_source(it), 0) < _MAX_BY_SOURCE[_get_queue_source(it)]), None)
            if first_waiting and first_waiting.message_id == message_id:
                if _active_downloads < current_max_parallel and _active_by_source.get(source, 0) < _MAX_BY_SOURCE[source]:
                    _active_downloads += 1
                    _active_by_source[source] = _active_by_source.get(source, 0) + 1
                    item.status = "Descargando"
                    allowed = True

        if allowed:
            return True
        await asyncio.sleep(0.1)


def _get_queue_source(item):
    return "telegram" if item.source == "telegram" else "http"


def release_slot(source: str):
    global _active_downloads
    source = (source or "telegram").lower()
    if source not in _active_by_source:
        source = "telegram"
    _active_downloads = max(0, _active_downloads - 1)
    _active_by_source[source] = max(0, _active_by_source.get(source, 0) - 1)

# ==========================
# PROGRESO TELEGRAM
# ==========================

def progress(current: int, total: int, message_id: int):
    if _CANCEL_FLAGS.get(message_id):
        raise Exception("Cancelado por el usuario")

    now = time.time()
    stats = _progress_stats.setdefault(
        message_id,
        {
            "start": now,
            "last_bytes": 0,
            "last_time": now,
            "last_print": 0,
        }
    )

    elapsed = now - stats["start"]
    avg_speed = current / max(elapsed, 0.001)

    interval_bytes = current - stats["last_bytes"]
    interval_time = now - stats["last_time"]
    inst_speed = interval_bytes / max(interval_time, 0.001)

    stats["last_bytes"] = current
    stats["last_time"] = now

    with items_lock:
        _inst_speeds[message_id] = inst_speed
        item = items_by_id.get(message_id)
        if item:
            item.downloaded_bytes = current
            item.total_bytes = total or item.total_bytes
            item.progress = (current / item.total_bytes * 100.0) if item.total_bytes else 0.0
            if item.status == "En cola":
                item.status = "Descargando"

    if now - stats["last_print"] < 0.5 and (total and current < total):
        return
    stats["last_print"] = now

    name = _message_names.get(message_id, f"msg {message_id}")
    print(
        f"[↓ {name}] "
        f"{current/1024/1024:.2f}/{(total or 1)/1024/1024:.2f} MB "
        f"| inst: {inst_speed/1024/1024:.2f} MB/s "
        f"| avg: {avg_speed/1024/1024:.2f} MB/s"
    )


def get_media_file(message):
    if not message or getattr(message, "empty", False):
        return None
    if message.document:
        return message.document
    if message.video:
        return message.video
    if message.audio:
        return message.audio
    if message.voice:
        return message.voice
    if message.video_note:
        return message.video_note
    if message.photo:
        return message.photo
    if message.animation:
        return message.animation
    return None

# ==========================
# UTILIDADES
# ==========================

def format_eta(seconds: float) -> str:
    try:
        seconds = int(seconds)
    except Exception:
        seconds = 0
    if seconds < 0:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    else:
        return f"{m:02d}:{s:02d}"


def short_display_name(name: str, max_len: int = 40) -> str:
    if not name:
        return "—"
    name = name.strip()
    if len(name) <= max_len:
        return name
    end_keep = 10
    if max_len <= end_keep + 4:
        return name[:max_len - 1] + "…"
    start_keep = max_len - end_keep - 1
    return name[:start_keep] + "…" + name[-end_keep:]


def build_status_report() -> str:
    with items_lock:
        snapshot = list(download_items)
        speeds = dict(_inst_speeds)

    if not snapshot:
        return "📋 Estado de descargas:\n(ninguna descarga en la lista ahora mismo)"

    lines = ["📋 Estado de descargas:"]
    char_limit = 3500
    truncated = False

    groups = [
        ("⬇️ En curso", ["Descargando"]),
        ("⏳ En cola", ["En cola"]),
        ("✅ Completadas", ["Completado"]),
        ("📥 Enviadas a qBittorrent", ["Enviado a qBittorrent"]),
        ("⚠️ Con problemas", ["Error", "Detenido"]),
    ]

    for title, statuses in groups:
        group_items = [it for it in snapshot if it.status in statuses]
        if not group_items:
            continue

        header = f"\n{title} ({len(group_items)}):"
        new_text = "\n".join(lines + [header])
        if len(new_text) > char_limit:
            truncated = True
            break
        lines.append(header)

        for it in group_items:
            fname = short_display_name(it.filename)
            speed_bytes = speeds.get(it.message_id, 0.0)
            speed_mbps = speed_bytes / 1024 / 1024 if speed_bytes > 0 else 0.0

            if "Descargando" in statuses:
                prog = f"{it.progress:4.1f}%"
                line = f"- {prog}"
                if speed_mbps > 0:
                    eta_txt = ""
                    if it.total_bytes and it.downloaded_bytes and it.total_bytes > it.downloaded_bytes:
                        remaining = it.total_bytes - it.downloaded_bytes
                        eta_sec = remaining / speed_bytes if speed_bytes > 0 else 0
                        eta_txt = f" · ETA {format_eta(eta_sec)}"
                    line += f" · {speed_mbps:.2f} MB/s{eta_txt}"
                line += f" · {fname}"

            elif "En cola" in statuses:
                prog = f"{it.progress:4.1f}%"
                line = f"- {prog} · {fname}"

            elif "Completado" in statuses:
                line = f"- {fname}"

            else:
                err = it.error or ""
                if len(err) > 60:
                    err = err[:57] + "…"
                line = f"- {fname} · {it.status}"
                if err:
                    line += f" · {err}"

            new_text = "\n".join(lines + [line])
            if len(new_text) > char_limit:
                truncated = True
                break
            lines.append(line)

        if truncated:
            break

    if truncated:
        lines.append("… (resto de descargas truncadas)")

    return "\n".join(lines)


def extract_first_url(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r'(https?://\S+)', text)
    if not m:
        return None
    url = m.group(1).strip()
    url = url.rstrip(').,];\'"')
    return url


def extract_first_magnet(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r'(magnet:\?[^ \n]+)', text)
    if not m:
        return None
    return m.group(1).strip()


def sanitize_filename(name: str) -> str:
    return safe_filename(name)


def make_unique_path(directory: str, filename: str) -> str:
    filename = sanitize_filename(filename)
    base, ext = os.path.splitext(filename)
    with _path_lock:
        candidate = os.path.abspath(os.path.join(directory, filename))
        counter = 1
        while os.path.exists(candidate) or os.path.exists(candidate + ".downloading") or os.path.normcase(candidate) in _reserved_paths:
            candidate = os.path.abspath(os.path.join(directory, f"{base} ({counter}){ext}"))
            counter += 1
        _reserved_paths.add(os.path.normcase(candidate))
    return candidate


APP_RUN_KEY_NAME = "TelegramDownloader"


def get_app_executable_path() -> str:
    """
    Ruta que se registrará para arranque automático.
    - En exe: sys.executable
    - En modo script: auto.py
    """
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable])
    return subprocess.list2cmdline([sys.executable, str(BASE_DIR / "auto.py")])


def set_startup_windows(enabled: bool) -> Optional[str]:
    """
    Crea / elimina la entrada en:
    HKCU / Software / Microsoft / Windows / CurrentVersion / Run
    """
    if os.name != "nt" or winreg is None:
        return "Arranque automático solo soportado en Windows con winreg disponible."

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
    except Exception as e:
        return f"No se pudo abrir la clave de registro: {e}"

    try:
        if enabled:
            exe_path = get_app_executable_path()
            winreg.SetValueEx(key, APP_RUN_KEY_NAME, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(key, APP_RUN_KEY_NAME)
            except FileNotFoundError:
                pass
    except Exception as e:
        return f"No se pudo modificar la clave de arranque: {e}"
    finally:
        try:
            winreg.CloseKey(key)
        except Exception:
            pass

    return None

# ==========================
# ALLDEBRID
# ==========================

def test_alldebrid_key():
    global ALLDEBRID_CONNECTED, ALLDEBRID_STATUS_MSG
    key = ALLDEBRID_API_KEY
    connected, status = check_alldebrid(key, requests.get)
    if key == ALLDEBRID_API_KEY:
        ALLDEBRID_CONNECTED, ALLDEBRID_STATUS_MSG = connected, status
    print(f"[AD] {ALLDEBRID_STATUS_MSG}")


def alldebrid_unlock(url: str) -> Optional[dict]:
    if not ALLDEBRID_API_KEY:
        return None

    print("[AD] Intentando desbloquear enlace.")

    headers = {
        "Authorization": f"Bearer {ALLDEBRID_API_KEY}",
    }

    data = {
        "link": url,
        "agent": "TelegramDownloader",
    }

    try:
        resp = requests.post(
            "https://api.alldebrid.com/v4/link/unlock",
            data=data,
            headers=headers,
            timeout=30,
        )
        print(f"[AD] /link/unlock HTTP {resp.status_code}")
        try:
            data = resp.json()
        except Exception:
            print("[AD] Respuesta unlock no es JSON:", resp.text[:200])
            return None
        # No registrar enlaces premium ni datos de cuenta.
    except Exception as e:
        print(f"[AD] Excepción llamando a AllDebrid: {e}")
        return None

    if data.get("status") != "success":
        error = data.get("error") or {}
        print(f"[AD] No se pudo desbloquear: {error.get('code', 'Error desconocido')}")
        return None

    d = data.get("data") or {}
    dl_link = d.get("link")
    if not dl_link:
        print("[AD] Unlock no devolvió link final")
        return None

    return {
        "link": dl_link,
        "filename": d.get("filename"),
        "filesize": d.get("filesize", 0),
    }

# ==========================
# QBITTORRENT
# ==========================

def test_qbittorrent_connection():
    """Comprueba conexión con qBittorrent y actualiza el estado global."""
    global QBITTORRENT_CONNECTED, QBITTORRENT_STATUS_MSG

    QBITTORRENT_CONNECTED = False
    QBITTORRENT_STATUS_MSG = "No configurado"

    if not qbittorrent_available():
        print("[QB TEST] qBittorrent no está configurado en .env")
        QBITTORRENT_STATUS_MSG = "No configurado"
        return

    sess, err = qbittorrent_get_session()
    if sess and not err:
        QBITTORRENT_CONNECTED = True
        QBITTORRENT_STATUS_MSG = "Conectado"
        print("[QB TEST] qBittorrent conectado correctamente.")
    else:
        QBITTORRENT_CONNECTED = False
        QBITTORRENT_STATUS_MSG = err or "Error desconocido"
        print("[QB TEST] Error al conectar a qBittorrent:", QBITTORRENT_STATUS_MSG)


def qbittorrent_get_session() -> (Optional[requests.Session], Optional[str]):
    global _qb_session
    if not qbittorrent_available():
        return None, "qBittorrent no está configurado en .env"

    if _qb_session is None:
        _qb_session = requests.Session()

    try:
        resp = _qb_session.post(
            QBITTORRENT_URL + "/api/v2/auth/login",
            data={
                "username": QBITTORRENT_USERNAME,
                "password": QBITTORRENT_PASSWORD,
            },
            timeout=10,
        )
        if resp.status_code == 200 and resp.text.startswith("Ok."):
            return _qb_session, None
        else:
            return None, f"Login qBittorrent falló: HTTP {resp.status_code}, resp: {resp.text[:200]}"
    except Exception as e:
        return None, f"Error conectando a qBittorrent: {e}"


def qbittorrent_add_url(url: str) -> (bool, str):
    sess, err = qbittorrent_get_session()
    if not sess:
        return False, err
    try:
        resp = sess.post(
            QBITTORRENT_URL + "/api/v2/torrents/add",
            data={"urls": url},
            timeout=15,
        )
        if resp.status_code == 200:
            return True, ""
        else:
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, str(e)


def qbittorrent_add_torrent_file(file_path: str) -> (bool, str):
    """
    Envía un archivo .torrent local a qBittorrent.
    """
    sess, err = qbittorrent_get_session()
    if not sess:
        return False, err
    try:
        with open(file_path, "rb") as f:
            files = {"torrents": f}
            resp = sess.post(
                QBITTORRENT_URL + "/api/v2/torrents/add",
                files=files,
                timeout=30,
            )
        if resp.status_code == 200:
            return True, ""
        else:
            return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, str(e)

def http_download_file(message_id: int, original_url: str, dest_path: str):
    download_url = original_url
    expected_total = 0
    if not is_debrid_url(original_url):
        info = alldebrid_unlock(original_url)
        if info:
            download_url = info["link"]
            expected_total = int(info.get("filesize") or 0)
            with items_lock:
                item = items_by_id.get(message_id)
            if (info.get("filename") and sanitize_filename(info["filename"]) != os.path.basename(dest_path)
                    and not os.path.exists(dest_path + ".downloading")):
                dest_path = make_unique_path(os.path.dirname(dest_path), info["filename"])
            with items_lock:
                if item:
                    item.filename = os.path.basename(dest_path)
                    item.dest_path = dest_path
                    item.source = "alldebrid"
                    item.total_bytes = expected_total
                    _message_names[message_id] = item.filename
            save_download_state()
    stats = {"bytes": 0, "time": time.monotonic(), "print": 0}
    def report(current, total):
        now = time.monotonic()
        elapsed = max(now - stats["time"], 0.001)
        speed = max(0, current - stats["bytes"]) / elapsed
        with items_lock:
            it = items_by_id.get(message_id)
            if it:
                it.downloaded_bytes = current
                it.total_bytes = total
                it.progress = min(100.0, current / total * 100) if total else 0
                _inst_speeds[message_id] = speed
        stats.update(bytes=current, time=now)
        if now - stats["print"] >= 2:
            stats["print"] = now
            print(f"[HTTP] {os.path.basename(dest_path)}: {current / 1024 / 1024:.2f} MB")
    transfer_http(download_url, dest_path,
                  lambda: SHUTDOWN.is_set() or bool(_CANCEL_FLAGS.get(message_id)), report, expected_total)
    return dest_path


# ==========================
# REINICIO DESCARGA
# ==========================

async def restart_download_coroutine(message_id: int):
    try:
        msg = await app.get_messages(CHANNEL, message_id)
        if get_media_file(msg):
            await auto_download(app, msg)
        elif msg and (msg.text or msg.caption):
            await auto_http_download(app, msg)
        else:
            with items_lock:
                item = items_by_id.get(message_id)
                if item:
                    item.status = "Error"
                    item.error = "El mensaje original ya no está disponible"
            save_download_state()
    except Exception as e:
        print(f"[✗] Error al reiniciar descarga {message_id}: {e}")
        with items_lock:
            item = items_by_id.get(message_id)
            if item:
                item.status = "Error"
                item.error = str(e)
        save_download_state()

# ==========================
# HANDLER MEDIA TELEGRAM
# ==========================

@app.on_message(
    filters.chat(CHANNEL)
    & (filters.document | filters.video | filters.audio
       | filters.photo | filters.voice | filters.video_note | filters.animation)
)
async def auto_download(client, message):
    if message.id in _download_tasks or (message.id in items_by_id and items_by_id[message.id].status != "En cola"):
        return
    media = get_media_file(message)
    if not media:
        return

    filename = getattr(media, "file_name", None)
    if not filename:
        filename = f"file_{message.id}"

    filename = sanitize_filename(filename)
    dest_path = make_unique_path(DOWNLOAD_PATH, filename)
    filename = os.path.basename(dest_path)

    print(f"\n[+] Detectado (Telegram): {filename}")
    print(f"[i] Guardando en: {dest_path}")

    _message_names[message.id] = filename

    _progress_stats[message.id] = {
        "start": time.time(),
        "last_bytes": 0,
        "last_time": time.time(),
        "last_print": 0,
    }

    _CANCEL_FLAGS.pop(message.id, None)

    with items_lock:
        if message.id not in items_by_id:
            item = DownloadItem(
                message_id=message.id,
                filename=filename,
                status="En cola",
                progress=0.0,
                total_bytes=getattr(media, "file_size", 0),
                source="telegram",
            )
            items_by_id[message.id] = item
            download_items.append(item)

    with items_lock:
        item = items_by_id[message.id]
        item.filename = os.path.basename(dest_path)
        item.dest_path = dest_path
    save_download_state()
    # No bloqueamos el handler: encolamos y lanzamos la descarga en segundo plano
    schedule_download(message.id, _telegram_download_task(client, message, dest_path, filename, getattr(media, "file_size", 0)))
    return


async def _telegram_download_task(client, message, dest_path: str, filename: str, size_bytes: int):
    """Descarga Telegram robusta: cola limitada + escritura atómica + validación por bytes.

    Esto evita que queden .rar corruptos cuando llegan muchos mensajes.
    """
    if not await acquire_slot(message.id, "telegram"):
        return
    print(f"[i] Descargas activas ahora: {_active_downloads}")

    with items_lock:
        item = items_by_id.get(message.id)
        if item:
            item.status = "Descargando"

    tmp_path = dest_path + ".downloading"

    def _safe_remove(p: str):
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    try:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        attempts = 3
        last_exc = None

        for attempt in range(1, attempts + 1):
            _safe_remove(tmp_path)
            try:
                # Refrescar el mensaje antes de descargar (evita file_reference caducada tras esperar en cola)
                try:
                    fresh_msg = await client.get_messages(message.chat.id, message.id)
                    if fresh_msg:
                        message_to_download = fresh_msg
                    else:
                        message_to_download = message
                except Exception:
                    message_to_download = message

                # Descargar por chunks con stream_media para evitar archivos truncados/corruptos bajo carga
                # (Pyrogram download_media puede finalizar sin error en algunos escenarios de cola larga)
                # Aseguramos además file_reference fresca.
                # Derivar tamaño esperado si no lo tenemos
                expected_bytes = None
                try:
                    if size_bytes:
                        expected_bytes = int(size_bytes)
                except Exception:
                    expected_bytes = None
                if expected_bytes is None:
                    try:
                        media_obj = (
                            getattr(message_to_download, "document", None)
                            or getattr(message_to_download, "video", None)
                            or getattr(message_to_download, "audio", None)
                            or getattr(message_to_download, "voice", None)
                            or getattr(message_to_download, "animation", None)
                        )
                        if media_obj and getattr(media_obj, "file_size", None):
                            expected_bytes = int(media_obj.file_size)
                    except Exception:
                        expected_bytes = None

                current_bytes = 0
                with open(tmp_path, "wb") as _f:
                    async for _chunk in client.stream_media(message_to_download):
                        if _CANCEL_FLAGS.get(message.id):
                            raise Exception("Cancelado por el usuario")
                        _f.write(_chunk)
                        current_bytes += len(_chunk)
                        # progreso
                        try:
                            if expected_bytes:
                                progress(current_bytes, expected_bytes, message.id)
                        except Exception:
                            pass
                    try:
                        _f.flush()
                        os.fsync(_f.fileno())
                    except Exception:
                        pass

                downloaded_path = tmp_path
# Cancelación
                if _CANCEL_FLAGS.get(message.id):
                    raise Exception("Cancelado por el usuario")

                # Pyrogram puede devolver una ruta distinta si interpreta file_name como carpeta.
                actual_path = downloaded_path or tmp_path
                if actual_path != tmp_path and os.path.exists(tmp_path):
                    _safe_remove(tmp_path)

                # Validación por tamaño (bytes exactos) si Telegram lo proporciona
                if size_bytes:
                    try:
                        actual = os.path.getsize(actual_path) if os.path.exists(actual_path) else 0
                    except Exception:
                        actual = 0
                    if int(actual) != int(size_bytes):
                        # limpiar cualquier salida parcial antes de reintentar
                        _safe_remove(actual_path)
                        raise Exception(
                            f"Integridad fallida: esperado {int(size_bytes)} bytes, recibido {int(actual)} bytes"
                        )

                # Renombrado atómico al nombre final
                if actual_path != dest_path:
                    if os.path.exists(dest_path):
                        raise FileExistsError("Ya existe un archivo con el nombre de destino")
                    os.rename(actual_path, dest_path)

                last_exc = None
                break

            except Exception as e:
                last_exc = e
                # Si es cancelación, no reintentamos
                if "Cancelado por el usuario" in str(e) or _CANCEL_FLAGS.get(message.id):
                    raise

                print(f"[!] Intento {attempt}/{attempts} fallido para {filename}: {e}")
                _safe_remove(tmp_path)
                if attempt < attempts:
                    await asyncio.sleep(1.2 * attempt)
                    continue
                raise

    except Exception as e:
        print(f"\n[✗] Error al descargar: {e}")
        with items_lock:
            item = items_by_id.get(message.id)
            if item:
                msg_err = str(e)
                cancelled = "Cancelado por el usuario" in msg_err or _CANCEL_FLAGS.pop(message.id, False)
                if cancelled:
                    item.status = "Detenido"
                    item.error = "Detenido por el usuario"
                else:
                    item.status = "Error"
                    item.error = msg_err
                _inst_speeds.pop(message.id, None)

        save_download_state()

        try:
            if "Cancelado por el usuario" in str(e) or cancelled:
                motivo = "Detenido por el usuario"
                icon = "⏸️"
            else:
                motivo = f"Detalles: {e}"
                icon = "❌"

            error_text = (
                f"{icon} Descarga no completada en el servidor (archivo Telegram):\n"
                f"{filename}\n"
                f"{motivo}"
            )
            status_text = build_status_report()
            full_text = error_text + "\n\n" + status_text

            await send_report(client,
                CHANNEL,
                full_text,
                reply_to_message_id=message.id
            )
        except Exception:
            pass

        return

    finally:
        # Liberar slot siempre
        release_slot("telegram")
        print(f"[i] Descargas activas ahora: {_active_downloads}")

    cancelled_flag = _CANCEL_FLAGS.pop(message.id, False)
    if cancelled_flag:
        print(f"\n[⏸] Descarga finalizada pero marcada como detenida: {filename}")
        with items_lock:
            item = items_by_id.get(message.id)
            if item:
                item.status = "Detenido"
                if not item.error:
                    item.error = "Detenido por el usuario (terminó justo al cancelar)"
            _inst_speeds.pop(message.id, None)

        save_download_state()

        try:
            text_msg = (
                f"⏸️ Descarga detenida en el servidor (archivo Telegram, terminó justo al cancelar):\n"
                f"{filename}\n"
                f"Ruta: {os.path.abspath(DOWNLOAD_PATH)}"
            )
            status_text = build_status_report()
            full_text = text_msg + "\n\n" + status_text
            await send_report(client,
                CHANNEL,
                full_text,
                reply_to_message_id=message.id
            )
        except Exception:
            pass

        return

    print(f"\n[✓] ¡DESCARGADO! {filename}")

    # Marcamos como completado la descarga del archivo
    with items_lock:
        item = items_by_id.get(message.id)
        if item:
            item.status = "Completado"
            item.progress = 100.0
        _inst_speeds.pop(message.id, None)

    save_download_state()

    # === si es un .torrent, lo mandamos a qBittorrent ===
    torrent_extra = ""
    if qbittorrent_available() and filename.lower().endswith(".torrent"):
        print(f"[qB] Detectado archivo .torrent descargado: {dest_path} -> enviando a qBittorrent")
        ok_t, err_t = await asyncio.to_thread(qbittorrent_add_torrent_file, dest_path)
        with items_lock:
            item = items_by_id.get(message.id)
            if item:
                item.source = "torrent"
                item.status = "Enviado a qBittorrent" if ok_t else "Error"
                if not ok_t and err_t:
                    if not item.error:
                        item.error = f"qBittorrent: {err_t}"
        if ok_t:
            torrent_extra = "\nEnviado a qBittorrent para descargar."
            print("[qB] .torrent enviado correctamente a qBittorrent.")
        else:
            torrent_extra = f"\n⚠️ No se pudo enviar a qBittorrent: {err_t or 'Error desconocido'}"
            print(f"[qB] Error al enviar .torrent a qBittorrent: {err_t}")
        save_download_state()

    try:
        size_mb = size_bytes / 1024 / 1024 if size_bytes else 0
        text_msg = f"✅ Descargado en el servidor (archivo Telegram):\n{filename}"
        if size_bytes:
            text_msg += f"\nTamaño: {size_mb:.2f} MB"
        text_msg += f"\nRuta: {os.path.abspath(DOWNLOAD_PATH)}"
        if torrent_extra:
            text_msg += torrent_extra

        status_text = build_status_report()
        full_text = text_msg + "\n\n" + status_text

        await send_report(client,
            CHANNEL,
            full_text,
            reply_to_message_id=message.id
        )
    except Exception:
        pass

# ==========================
# HANDLER TEXTO: MAGNET + URLS
# ==========================

@app.on_message(filters.chat(CHANNEL) & (filters.text | filters.caption), group=1)
async def auto_http_download(client, message):
    if get_media_file(message):
        return
    if message.id in _download_tasks or (message.id in items_by_id and items_by_id[message.id].status != "En cola"):
        return
    text = message.text or message.caption or ""
    if text.startswith("[Telegram Downloader]"):
        return

    # 1) MAGNET primero
    magnet = extract_first_magnet(text)
    if magnet:
        print(f"\n[+] Detectado MAGNET en mensaje {message.id}: {magnet}")
        if not qbittorrent_available():
            print("[!] Magnet detectado pero qBittorrent no está configurado.")
            return

        fname = f"magnet_{message.id}"
        _message_names[message.id] = fname

        with items_lock:
            if message.id not in items_by_id:
                item = DownloadItem(
                    message_id=message.id,
                    filename=fname,
                    status="En cola",
                    progress=0.0,
                    total_bytes=0,
                    source="torrent",
                )
                items_by_id[message.id] = item
                download_items.append(item)

        with items_lock:
            items_by_id[message.id].status = "Enviando a qBittorrent"
        ok, err = await asyncio.to_thread(qbittorrent_add_url, magnet)

        with items_lock:
            item = items_by_id.get(message.id)
            if item:
                if ok:
                    item.status = "Enviado a qBittorrent"
                    item.progress = 100.0
                    item.error = None
                else:
                    item.status = "Error"
                    item.error = err or "No se pudo añadir el magnet a qBittorrent"

        save_download_state()

        try:
            if ok:
                txt = (
                    "✅ Torrent enviado a qBittorrent (magnet).\n"
                    f"Nombre interno: {fname}"
                )
            else:
                txt = (
                    "❌ No se pudo enviar el magnet a qBittorrent.\n"
                    f"Motivo: {err or 'Error desconocido'}"
                )
            status_text = build_status_report()
            full_text = txt + "\n\n" + status_text
            await send_report(client,
                CHANNEL,
                full_text,
                reply_to_message_id=message.id
            )
        except Exception:
            pass

        return

    # 2) URL HTTP/HTTPS
    url = extract_first_url(text)
    if not url:
        return

    parsed = urlparse(url)
    host = parsed.netloc.lower()

    # Caso especial: URL .torrent -> qBittorrent directo
    if parsed.path.lower().endswith(".torrent") and qbittorrent_available():
        print(f"\n[+] Detectado .torrent para qBittorrent: {url}")
        fname = os.path.basename(parsed.path) or f"torrent_{message.id}"
        fname = sanitize_filename(fname)
        _message_names[message.id] = fname

        with items_lock:
            if message.id not in items_by_id:
                item = DownloadItem(
                    message_id=message.id,
                    filename=fname,
                    status="En cola",
                    progress=0.0,
                    total_bytes=0,
                    source="torrent",
                )
                items_by_id[message.id] = item
                download_items.append(item)

        with items_lock:
            items_by_id[message.id].status = "Enviando a qBittorrent"
        ok, err = await asyncio.to_thread(qbittorrent_add_url, url)

        with items_lock:
            item = items_by_id.get(message.id)
            if item:
                if ok:
                    item.status = "Enviado a qBittorrent"
                    item.progress = 100.0
                    item.error = None
                else:
                    item.status = "Error"
                    item.error = err or "No se pudo añadir el .torrent a qBittorrent"

        save_download_state()

        try:
            if ok:
                txt = (
                    "✅ Torrent enviado a qBittorrent (URL .torrent).\n"
                    f"Archivo: {fname}"
                )
            else:
                txt = (
                    "❌ No se pudo enviar el .torrent a qBittorrent.\n"
                    f"Motivo: {err or 'Error desconocido'}"
                )
            status_text = build_status_report()
            full_text = txt + "\n\n" + status_text
            await send_report(client,
                CHANNEL,
                full_text,
                reply_to_message_id=message.id
            )
        except Exception:
            pass

        return

    # 3) Descarga HTTP normal (con AllDebrid si aplica)
    base_name = parsed.path.split("/")[-1].split("?")[0] or f"link_{message.id}"
    base_name = sanitize_filename(base_name)
    filename = base_name
    previous = items_by_id.get(message.id)
    if previous and previous.dest_path and os.path.isfile(previous.dest_path + ".downloading"):
        dest_path = previous.dest_path
    else:
        dest_path = make_unique_path(DOWNLOAD_PATH, filename)

    print(f"\n[+] Detectado enlace HTTP (mensaje {message.id})")
    print(f"[i] Guardando en: {dest_path}")

    _message_names[message.id] = os.path.basename(dest_path)
    _CANCEL_FLAGS.pop(message.id, None)

    is_alldebrid_host = is_debrid_url(url)
    source = "alldebrid" if is_alldebrid_host else "http"

    with items_lock:
        if message.id not in items_by_id:
            item = DownloadItem(
                message_id=message.id,
                filename=os.path.basename(dest_path),
                status="En cola",
                progress=0.0,
                total_bytes=0,
                source=source,
            )
            items_by_id[message.id] = item
            download_items.append(item)

    with items_lock:
        item = items_by_id[message.id]
        item.filename = os.path.basename(dest_path)
        item.dest_path = dest_path
    save_download_state()
    # No bloqueamos el handler: encolamos y lanzamos la descarga HTTP en segundo plano
    schedule_download(message.id, _http_download_task(client, message, url, dest_path))
    return


async def _http_download_task(client, message, url: str, dest_path: str):
    src = _get_source_for(message.id, "http")
    if not await acquire_slot(message.id, src):
        return
    try:
        await _http_download_task_impl(client, message, url, dest_path)
    finally:
        release_slot(src)


async def _http_download_task_impl(client, message, url: str, dest_path: str):
    print(f"[i] Descargas activas ahora: {_active_downloads}")
    
    with items_lock:
        item = items_by_id.get(message.id)
        if item:
            item.status = "Descargando"
    
    try:
        dest_path = await asyncio.to_thread(http_download_file, message.id, url, dest_path)
    except Exception as e:
        print(f"\n[✗] Error al descargar HTTP: {e}")
        with items_lock:
            item = items_by_id.get(message.id)
            if item:
                dest_path = item.dest_path or dest_path
                msg_err = str(e)
                cancelled = "Cancelado por el usuario" in msg_err or _CANCEL_FLAGS.pop(message.id, False)
                if cancelled:
                    item.status = "Detenido"
                    item.error = "Detenido por el usuario"
                else:
                    item.status = "Error"
                    item.error = msg_err
                _inst_speeds.pop(message.id, None)
    
        save_download_state()
    
        try:
            if "Cancelado por el usuario" in str(e) or cancelled:
                motivo = "Detenido por el usuario"
                icon = "⏸️"
            else:
                motivo = f"Detalles: {e}"
                icon = "❌"
    
            error_text = (
                f"{icon} Descarga HTTP no completada en el servidor:\n"
                f"{os.path.basename(dest_path)}\n"
                f"{motivo}"
            )
            status_text = build_status_report()
            full_text = error_text + "\n\n" + status_text
    
            await send_report(client,
                CHANNEL,
                full_text,
                reply_to_message_id=message.id
            )
        except Exception:
            pass
    
        print(f"[i] Descargas activas ahora: {_active_downloads}")
        return
    
    cancelled_flag = _CANCEL_FLAGS.pop(message.id, False)
    if cancelled_flag:
        print(f"\n[⏸] Descarga HTTP finalizada pero marcada como detenida: {os.path.basename(dest_path)}")
        with items_lock:
            item = items_by_id.get(message.id)
            if item:
                item.status = "Detenido"
                if not item.error:
                    item.error = "Detenido por el usuario (terminó justo al cancelar)"
            _inst_speeds.pop(message.id, None)
    
        save_download_state()
    
        try:
            text = (
                f"⏸️ Descarga HTTP detenida en el servidor (terminó justo al cancelar):\n"
                f"{os.path.basename(dest_path)}\n"
                f"Ruta: {os.path.abspath(DOWNLOAD_PATH)}"
            )
            status_text = build_status_report()
            full_text = text + "\n\n" + status_text
            await send_report(client,
                CHANNEL,
                full_text,
                reply_to_message_id=message.id
            )
        except Exception:
            pass
    
        print(f"[i] Descargas activas ahora: {_active_downloads}")
        return
    
    print(f"\n[✓] ¡DESCARGADO HTTP! {os.path.basename(dest_path)}")
    print(f"[i] Descargas activas ahora: {_active_downloads}")
    
    with items_lock:
        item = items_by_id.get(message.id)
        if item:
            item.status = "Completado"
            item.progress = 100.0
        _inst_speeds.pop(message.id, None)
    
    save_download_state()
    
    try:
        with items_lock:
            item = items_by_id.get(message.id)
            size_bytes = item.total_bytes if item else 0
        size_mb = size_bytes / 1024 / 1024 if size_bytes else 0
    
        text = f"✅ Descargado en el servidor (URL):\n{os.path.basename(dest_path)}"
        if size_bytes:
            text += f"\nTamaño: {size_mb:.2f} MB"
        text += f"\nRuta: {os.path.abspath(DOWNLOAD_PATH)}"
    
        status_text = build_status_report()
        full_text = text + "\n\n" + status_text
    
        await send_report(client,
            CHANNEL,
            full_text,
            reply_to_message_id=message.id
        )
    except Exception:
        pass
    
    
# ==========================
# GUI
# ==========================

class DownloadGUI:
    def __init__(self):
        self.root = tk.Tk()

        # Single-instance: registrar root para poder activar la ventana
        global _ROOT_REF, _ACTIVATE_PENDING
        _ROOT_REF = self.root
        global GUI_APP
        GUI_APP = self

        self.root.title(APP_NAME_FULL)
        self.connections_window = None
        self.root.after(100, self.process_events)

        self.root.geometry(WINDOW_GEOMETRY)

        self.app_icon = None
        try:
            icon_path = IMAGES_DIR / "background.png"
            self.app_icon = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self.app_icon)
        except Exception as e:
            print(f"[!] No se pudo cargar background.png para icono: {e}")

        self.icons: Dict[str, tk.PhotoImage] = {}
        self.icons_small: Dict[str, tk.PhotoImage] = {}
        for key, fname in [
            ("telegram", "icon_telegram.png"),
            ("http", "icon_http.png"),
            ("alldebrid", "icon_alldebrid.png"),
            ("torrent", "icon_torrent.png"),
        ]:
            try:
                img_path = IMAGES_DIR / fname
                img = tk.PhotoImage(file=str(img_path))
                max_dim = max(img.width(), img.height())
                factor = max(1, max_dim // 18)
                if factor > 1:
                    img_small = img.subsample(factor, factor)
                else:
                    img_small = img
                self.icons[key] = img
                self.icons_small[key] = img_small
                print(f"[i] Icono cargado: {fname} ({key}) {img.width()}x{img.height()} -> factor {factor}")
            except Exception:
                pass

        # Colores de la app
        self.bg_root = "#101722"
        self.bg_frame = "#101722"
        self.bg_card = "#1b2738"
        self.fg_text = "#e7edf6"
        self.accent = "#67b7ff"
        self.accent_soft = "#3b82c4"

        self.root.configure(bg=self.bg_root)
        self.root.option_add("*Entry.font", ("Segoe UI", 10))
        self.root.option_add("*Entry.background", "#172233")
        self.root.option_add("*Entry.foreground", self.fg_text)
        self.root.option_add("*Entry.insertBackground", self.fg_text)

        self.tray_icon = None
        self._tray_thread = None
        self.options_menu: Optional[tk.Menu] = None
        self.log_window = None
        self.log_text_widget = None
        self._last_log_len = 0

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=self.bg_frame)
        style.configure("Main.TFrame", background=self.bg_frame)
        style.configure("TLabel", background=self.bg_frame, foreground=self.fg_text, font=("Segoe UI", 9))
        style.configure("Badge.TLabel", background=self.bg_card, foreground=self.fg_text, padding=(8, 5), font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=self.bg_frame, foreground="#a8b8ca", font=("Segoe UI Semibold", 10))
        style.configure("Header.TLabel", background=self.bg_frame, foreground=self.accent,
                        font=("Segoe UI Semibold", 15))
        style.configure("SubHeader.TLabel", background=self.bg_frame, foreground="#a1a1aa",
                        font=("Segoe UI", 9))
        style.configure("Info.TLabel", background=self.bg_frame, foreground=self.fg_text,
                        font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=self.bg_frame, foreground="#22c55e",
                        font=("Segoe UI", 9))

        style.configure(
            "TButton",
            background=self.bg_card,
            foreground=self.fg_text,
            borderwidth=0,
            focusthickness=0,
            padding=(10, 7),
            font=("Segoe UI", 9),
        )
        style.map(
            "TButton",
            background=[("active", "#2a4058")],
            foreground=[("active", "#f9fafb")],
        )

        configure_dark_controls(style, self.bg_frame, self.bg_card, self.fg_text, self.accent)
        install_entry_context_menus(self.root)
        install_dark_titlebar(self.root, self.bg_root, self.fg_text)
        main = ttk.Frame(self.root, padding=10, style="Main.TFrame")
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1, minsize=100)

        # Layout: arriba (cabecera), centro (gráfica+tabla), abajo (botones y estado)
        top_frame = ttk.Frame(main, style="Main.TFrame")
        top_frame.grid(row=0, column=0, sticky="ew")
        self.top_frame = top_frame

        center_frame = ttk.Frame(main, style="Main.TFrame")
        center_frame.grid(row=1, column=0, sticky="nsew")
        self.center_frame = center_frame

        bottom_frame = ttk.Frame(main, style="Main.TFrame")
        bottom_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.bottom_frame = bottom_frame

        # Reserve a visible slot for options, and let all other header text wrap.
        header_row = ttk.Frame(top_frame, style="Main.TFrame")
        header_row.pack(fill="x")
        header_row.columnconfigure(0, weight=1, minsize=0)
        header = ttk.Label(header_row, text=APP_NAME_FULL, style="Header.TLabel")
        header.grid(row=0, column=0, sticky="w")
        self.btn_options = ttk.Button(header_row, text="Ajustes", command=self.abrir_opciones)
        self.btn_options.grid(row=0, column=1, sticky="ne", padx=(8, 0))
        header_row.bind("<Configure>", lambda event: header.configure(
            wraplength=max(100, event.width - self.btn_options.winfo_reqwidth() - 12)), add="+")
        self.subtitle_label = ttk.Label(top_frame,
            text=f"Descargas desde Telegram  /  Grupo: {CHANNEL}",
            style="SubHeader.TLabel", justify="left")
        self.subtitle_label.pack(fill="x", pady=(6, 8))
        self.service_row = FlowFrame(top_frame, gap=14, style="Main.TFrame")
        self.service_row.pack(fill="x")
        self.lbl_alldebrid = ttk.Label(self.service_row, text="", style="Badge.TLabel")
        self.lbl_qbittorrent = ttk.Label(self.service_row, text="", style="Badge.TLabel")
        self.lbl_telegram = ttk.Label(self.service_row, text="Telegram: Desconectado", style="Badge.TLabel")
        self.lbl_telegram_group = ttk.Label(self.service_row, text="", style="Badge.TLabel")
        for label in (self.lbl_telegram, self.lbl_telegram_group, self.lbl_alldebrid, self.lbl_qbittorrent):
            self.service_row.add(label)
        self.actualizar_estado_servicios()

        folder_text = f"Destino: {os.path.abspath(DOWNLOAD_PATH)}"
        self.info_label = ttk.Label(
            top_frame,
            text=folder_text,
            style="Info.TLabel",
            justify="left"
        )
        self.info_label.pack(fill="x", pady=(4, 6))
        wrap_labels(top_frame)
        self.info_label.bind("<Button-1>", self.cambiar_carpeta_descargas)
        self.info_label.configure(cursor="hand2")

        # Variables de opciones (cargadas de config)
        self.var_minimize_tray = tk.BooleanVar(value=MINIMIZE_TO_TRAY)
        self.var_start_windows = tk.BooleanVar(value=START_WITH_WINDOWS)
        self.var_start_minimized = tk.BooleanVar(value=START_MINIMIZED)
        self.var_show_speed = tk.BooleanVar(value=SHOW_SPEED_GRAPH)

        # Gráfica de velocidad
        self.speed_frame = ttk.Frame(center_frame, style="Main.TFrame")

        self.speed_canvas = tk.Canvas(
            self.speed_frame,
            height=48,
            bg="#121c2a",
            highlightthickness=1,
            highlightbackground=self.accent_soft,
        )
        self.speed_canvas.pack(fill="x", pady=(2, 0))

        self.speed_label = ttk.Label(
            self.speed_frame,
            text="Velocidad global: 0.00 MB/s",
            style="Info.TLabel",
        )
        self.speed_label.pack(anchor="center", pady=(4, 0))

        self.speed_history: List[float] = []

        table_header = ttk.Frame(center_frame, style="Main.TFrame")
        table_header.pack(fill="x", pady=(10, 6))
        ttk.Label(table_header, text="DESCARGAS", style="Section.TLabel").pack(side="left")
        self.list_summary = ttk.Label(table_header, text="0 archivos", style="SubHeader.TLabel")
        self.list_summary.pack(side="right")

        # Tabla de descargas + scroll
        tree_container = ttk.Frame(center_frame, style="Main.TFrame")
        tree_container.pack(fill="both", expand=True, pady=(4, 0))
        self.tree_container = tree_container

        self.columns = ("archivo", "origen", "estado", "vel", "progreso")
        self.tree = ttk.Treeview(
            tree_container,
            columns=self.columns,
            show="headings",
            height=6,
            style="Custom.Treeview",
            selectmode="extended",
        )

        tree_scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.tree.yview)
        horizontal_scrollbar = ttk.Scrollbar(tree_container, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=tree_scrollbar.set, xscrollcommand=horizontal_scrollbar.set)
        tree_container.columnconfigure(0, weight=1)
        tree_container.rowconfigure(0, weight=1)
        self.tree.grid(row=0, column=0, sticky="nsew")
        tree_scrollbar.grid(row=0, column=1, sticky="ns")
        # The narrow layout puts each download's values on multiple lines.
        self.compact_downloads = False
        self.download_font = tkfont.Font(family="Segoe UI", size=9)
        self.download_bold_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        self.table_columns = self.columns
        self.tree.bind("<Configure>", self.adapt_download_table, add="+")

        self.tree.heading("archivo", text="Archivo", anchor="w")
        self.tree.heading("origen", text="Origen", anchor="center")
        self.tree.heading("estado", text="Estado", anchor="center")
        self.tree.heading("vel", text="Velocidad", anchor="center")
        self.tree.heading("progreso", text="Progreso", anchor="center")

        default_widths = {
            "archivo": 520,
            "origen": 60,
            "estado": 110,
            "vel": 160,
            "progreso": 220,
        }
        for col in self.columns:
            width = COLUMN_WIDTHS.get(col, default_widths.get(col, 100))
            anchor = "w" if col == "archivo" else "center"
            minimum = {"archivo": 180, "origen": 70, "estado": 180, "vel": 135, "progreso": 200}[col]
            self.tree.column(col, width=max(minimum, width), minwidth=minimum, anchor=anchor, stretch=True)

        style.configure(
            "Custom.Treeview",
            background="#121c2a",
            foreground=self.fg_text,
            fieldbackground="#121c2a",
            rowheight=32,
            bordercolor="#304156",
            borderwidth=0,
        )
        style.layout("Custom.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        # Asegurar que la selección se vea claramente
        style.map(
            "Custom.Treeview",
            background=[("selected", "#214669")],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Custom.Treeview.Heading",
            background="#192739",
            foreground=self.accent,
            relief="flat",
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Custom.Treeview",
            background=[("selected", "#214669")],
            foreground=[("selected", "#f9fafb")],
        )
        style.map(
            "Custom.Treeview.Heading",
            background=[("active", "#263b51")]
        )

        self.sort_reverse_by_col: Dict[str, bool] = {c: False for c in self.columns}
        for col in self.columns:
            if col != "origen":
                self.tree.heading(col, command=lambda c=col: self.sort_by_column(c))

        if DISPLAYCOLUMNS and set(DISPLAYCOLUMNS) == set(self.columns):
            self.tree["displaycolumns"] = DISPLAYCOLUMNS
        else:
            self.tree["displaycolumns"] = self.columns
        self.table_columns = tuple(self.tree["displaycolumns"])

        self.header_menu = tk.Menu(
            self.tree,
            tearoff=0,
            bg=self.bg_card,
            fg=self.fg_text,
            activebackground=self.accent_soft,
            activeforeground="#f9fafb",
            bd=0,
            relief="flat",
            selectcolor=self.accent,
        )
        self.header_menu.add_command(label="Mover a la izquierda", command=self.mover_col_izquierda)
        self.header_menu.add_command(label="Mover a la derecha", command=self.mover_col_derecha)
        self.header_menu_current_col: Optional[str] = None

        self.tree.bind("<Button-3>", self.on_right_click)

        # Selección con ratón (click normal + arrastrar para seleccionar por rango)
        self._drag_start_iid: Optional[str] = None
        self._drag_additive: bool = False
        self.tree.bind("<ButtonPress-1>", self.on_tree_button_press, add="+")
        self.tree.bind("<B1-Motion>", self.on_tree_b1_motion, add="+")
        self.tree.bind("<ButtonRelease-1>", self.on_tree_button_release, add="+")

        self.tree_items: Dict[int, str] = {}
        self.tree_tooltip = TreeTooltip(self.tree, self.download_details)
        self.row_canvases: Dict[int, tk.Canvas] = {}
        self.origin_canvases: Dict[int, tk.Canvas] = {}
        self.tree.tag_configure("even", background="#121c2a")
        self.tree.tag_configure("odd", background="#172233")
        self.tree.tag_configure("complete", foreground="#79d4ab")
        self.tree.tag_configure("failed", foreground="#f19b9b")
        self.tree.tag_configure("paused", foreground="#d9bd7a")
        self.empty_state = ttk.Frame(self.tree, padding=12)
        ttk.Label(self.empty_state, text="Tu próxima descarga empieza en Telegram", style="Section.TLabel").pack()
        ttk.Label(self.empty_state, text="Envía un enlace o archivo al grupo conectado.", style="SubHeader.TLabel").pack(pady=(6, 10))
        ttk.Button(self.empty_state, text="Configurar conexiones", command=self.abrir_conexiones).pack()

        self.selected_message_id: Optional[int] = None
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        # Botones abajo
        btn_row1 = FlowFrame(center_frame, style="Main.TFrame")
        self.action_row = btn_row1
        btn_row1.pack(fill="x", before=tree_container, pady=(6, 8))

        btn_row2 = FlowFrame(bottom_frame, style="Main.TFrame")
        self.summary_row = btn_row2
        btn_row2.pack(fill="x", pady=(4, 0))

        style.configure("Primary.TButton", background="#256395", foreground="#ffffff")
        style.map("Primary.TButton", background=[("active", "#347bab"), ("disabled", "#263b51")])
        style.configure("Move.TButton", background="#263b51", foreground=self.fg_text)
        style.configure("Danger.TButton", background="#38282d", foreground="#f8b4b4")
        style.map("Danger.TButton", background=[("active", "#543039")], foreground=[("active", "#ffd9d9")])
        style.configure("Clean.TButton", background="#213b35", foreground="#a4deca")
        style.map("Clean.TButton", background=[("active", "#2e594c")], foreground=[("active", "#d0f1e4")])
        style.configure("Folder.TButton", background="#214669", foreground="#e7edf6")
        style.map("Folder.TButton", background=[("active", "#2d6089")], foreground=[("active", "#ffffff")])

        self.btn_up = ttk.Button(btn_row1, text="↑ Subir", style="Move.TButton", command=self.mover_arriba)
        btn_row1.add(self.btn_up)

        self.btn_down = ttk.Button(btn_row1, text="↓ Bajar", style="Move.TButton", command=self.mover_abajo)
        btn_row1.add(self.btn_down)

        self.btn_restart = ttk.Button(btn_row1, text="Reintentar", style="Primary.TButton", command=self.reiniciar_descarga)
        btn_row1.add(self.btn_restart)

        self.btn_stop = ttk.Button(btn_row1, text="Detener", style="Move.TButton", command=self.detener_descargas)
        btn_row1.add(self.btn_stop)

        self.btn_delete = ttk.Button(btn_row1, text="Eliminar", style="Danger.TButton", command=self.eliminar_seleccion)
        btn_row1.add(self.btn_delete)

        self.btn_clear = ttk.Button(btn_row1, text="Limpiar finalizados", style="Clean.TButton", command=self.limpiar_completados)
        btn_row1.add(self.btn_clear)

        self.btn_open = ttk.Button(btn_row2, text="Abrir carpeta", style="Folder.TButton", command=self.abrir_descargas)
        btn_row2.add(self.btn_open)

        self.lbl_active = ttk.Label(btn_row2, text="Descargas activas: 0", style="Info.TLabel")
        btn_row2.add(self.lbl_active)

        parallel_group = ttk.Frame(btn_row2)
        self.lbl_limit = ttk.Label(parallel_group, text=f"Simultáneas: {current_max_parallel}", style="Info.TLabel")
        self.btn_dec = ttk.Button(parallel_group, text="−", width=3, command=lambda: self.cambiar_parallel(-1))
        self.btn_inc = ttk.Button(parallel_group, text="+", width=3, command=lambda: self.cambiar_parallel(1))
        for control in (self.btn_dec, self.lbl_limit, self.btn_inc):
            control.pack(side="left", padx=(0, 6))
        btn_row2.controls.remove(self.lbl_active)
        btn_row2.add(parallel_group)
        btn_row2.add(self.lbl_active)

        status = ttk.Label(
            bottom_frame,
            text="Listo para recibir enlaces y archivos desde Telegram.",
            style="SubHeader.TLabel",
            justify="left"
        )
        self.footer_status = status
        status.pack(fill="x", pady=(8, 0))
        wrap_labels(bottom_frame)

        # Visibilidad inicial de la gráfica (siempre arriba del listado)
        self.update_speed_graph_visibility()

        # Reserve the fixed controls and at least one complete download row.
        def fit_main_window(event=None):
            graph_height = self.speed_frame.winfo_reqheight() if self.var_show_speed.get() else 0
            minimum = top_frame.winfo_reqheight() + bottom_frame.winfo_reqheight() + graph_height + btn_row1.winfo_reqheight() + table_header.winfo_reqheight() + 180
            self.root.minsize(440, minimum)

        for panel in (top_frame, bottom_frame, self.speed_frame, btn_row1, table_header):
            panel.bind("<Configure>", fit_main_window, add="+")
        self.root.after_idle(fit_main_window)

        # Icono en bandeja si está activado en config
        if self.var_minimize_tray.get() and pystray and Image:
            self.create_tray_icon()

        # Iniciar minimizado si toca
        if self.var_start_minimized.get():
            if self.var_minimize_tray.get() and pystray and Image:
                self.root.withdraw()
            else:
                self.root.iconify()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Unmap>", self.on_unmap)

        self.root.after(500, self.refresh)
        if START_WITH_WINDOWS:
            set_startup_windows(True)

    # -------- Menú de opciones --------

    def process_events(self):
        try:
            while True:
                GUI_EVENTS.get_nowait()()
        except queue.Empty:
            pass
        except Exception as error:
            print(f"[GUI] {type(error).__name__}: {error}")
        self.actualizar_estado_servicios()
        if not SHUTDOWN.is_set():
            self.root.after(200, self.process_events)

    def request_shutdown(self, restart=False):
        global RESTART_REQUESTED
        if SHUTDOWN.is_set():
            return
        self.save_config()
        RESTART_REQUESTED = restart
        SHUTDOWN.set()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.withdraw()

    def abrir_conexiones(self):
        if self.connections_window and self.connections_window.winfo_exists():
            self.connections_window.lift()
            return
        win = tk.Toplevel(self.root)
        self.connections_window = win
        win.title("Conexiones — Telegram, AllDebrid y qBittorrent")
        win.geometry("600x450")
        win.minsize(540, 420)
        win.configure(bg=self.bg_frame)
        win.transient(self.root)
        install_dark_titlebar(win, self.bg_root, self.fg_text)
        ttk.Label(win, text="Centro de conexiones", style="Header.TLabel").pack(anchor="w", padx=18, pady=(14, 2))
        ttk.Label(win, text="Configura tus servicios y comprueba su estado.", style="SubHeader.TLabel").pack(anchor="w", padx=18, pady=(0, 4))
        ttk.Button(win, text="Cerrar", command=win.destroy).pack(side="bottom", pady=(0, 12))
        ttk.Button(win, text="? Guía de configuración", command=lambda: show_connection_help(self, DATA_DIR)).pack(side="bottom", pady=(0, 6))
        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        ad = ttk.Frame(notebook, padding=12)
        telegram = ttk.Frame(notebook, padding=12)
        notebook.add(ad, text="AllDebrid")
        notebook.add(telegram, text="Telegram")
        qb = ttk.Frame(notebook, padding=12)
        notebook.add(qb, text="qBittorrent")
        notebook.select(telegram)
        ttk.Label(ad, text="Clave API de AllDebrid", style="Header.TLabel").pack(fill="x", pady=(0, 6))
        ttk.Label(ad, text="Se aplica a las nuevas descargas sin reiniciar.", style="Info.TLabel").pack(fill="x", pady=(0, 8))
        key_var = tk.StringVar(value=ALLDEBRID_API_KEY or "")
        key_entry = ttk.Entry(ad, textvariable=key_var, show="*", width=40, style="Compact.TEntry")
        key_entry.pack(fill="x")
        entry_context_menu(key_entry)
        show_key = tk.BooleanVar(value=False)
        ttk.Checkbutton(ad, text="Mostrar clave", variable=show_key,
                        command=lambda: key_entry.configure(show="" if show_key.get() else "*")).pack(fill="x", anchor="w", pady=6)
        ad_status = tk.StringVar(value=ALLDEBRID_STATUS_MSG)
        ttk.Label(ad, textvariable=ad_status, style="Info.TLabel", wraplength=500).pack(fill="x", anchor="w", pady=8)
        ttk.Button(ad, text="Obtener clave API", command=lambda: webbrowser.open("https://alldebrid.com/apikeys/")).pack(anchor="w", pady=(0, 6))
        ad_buttons = FlowFrame(ad)
        ad_buttons.pack(fill="x")

        def check_key(save=False):
            global ALLDEBRID_API_KEY, ALLDEBRID_CONNECTED, ALLDEBRID_STATUS_MSG
            key = key_var.get().strip()
            if save:
                values = dict(CONNECTIONS)
                values["ALLDEBRID_API_KEY"] = key
                try:
                    atomic_json(CONNECTIONS_FILE, values)
                except OSError:
                    messagebox.showerror("AllDebrid", "No se pudo guardar la clave. Revisa los permisos de la carpeta de datos.", parent=win)
                    return
                CONNECTIONS.update(values)
                ALLDEBRID_API_KEY = key or None
                ALLDEBRID_CONNECTED = False
                ALLDEBRID_STATUS_MSG = "Comprobando..." if key else "No configurado"
                self.actualizar_estado_servicios()
            ad_status.set("Comprobando..." if key else "No configurado")
            for button in (test_button, save_button):
                button.configure(state="disabled")

            def worker():
                connected, status = check_alldebrid(key, requests.get)
                def finished():
                    global ALLDEBRID_CONNECTED, ALLDEBRID_STATUS_MSG
                    if save and (ALLDEBRID_API_KEY or "") == key:
                        ALLDEBRID_CONNECTED, ALLDEBRID_STATUS_MSG = connected, status
                        self.actualizar_estado_servicios()
                    if win.winfo_exists():
                        ad_status.set(("Guardada. " if save else "") + status)
                        if save and key_var.get().strip() == key:
                            key_hint.set("Clave guardada. " + status if key else "AllDebrid desactivado: sin clave.")
                        for button in (test_button, save_button):
                            button.configure(state="normal")
                GUI_EVENTS.put(finished)
            threading.Thread(target=worker, daemon=True).start()

        test_button = ttk.Button(ad_buttons, text="Comprobar clave", command=check_key)
        ad_buttons.add(test_button)
        save_button = ttk.Button(ad_buttons, text="Guardar y aplicar", command=lambda: check_key(True))
        ad_buttons.add(save_button)
        key_hint = tk.StringVar()
        def update_key_hint(*args):
            key_hint.set("Clave introducida: pulsa Guardar y aplicar." if key_var.get().strip()
                         else "Sin clave: guardar desactiva AllDebrid.")
        key_var.trace_add("write", update_key_hint)
        update_key_hint()
        ttk.Label(ad, textvariable=key_hint, style="Info.TLabel").pack(fill="x", pady=8)

        ttk.Label(telegram, text="Telegram", style="Header.TLabel").pack(fill="x", pady=(0, 4))
        ttk.Label(telegram, text="Cuenta existente: consulta API ID/Hash en my.telegram.org.\nBot existente: BotFather → /mybots → tu bot → API Token.",
                  style="Info.TLabel").pack(fill="x", pady=(0, 6))
        links = FlowFrame(telegram)
        links.pack(fill="x", pady=(0, 6))
        links.add(ttk.Button(links, text="Ver / crear API ID y Hash", command=lambda: webbrowser.open("https://my.telegram.org/apps")))
        links.add(ttk.Button(links, text="Ver / crear token del bot", command=lambda: webbrowser.open("https://t.me/BotFather")))
        fields = {}
        secret_entries = []
        current = {"API_ID": str(API_ID or ""), "API_HASH": API_HASH, "PHONE": PHONE or "",
                   "BOT_TOKEN": BOT_TOKEN, "CHANNEL_ID": str(CHANNEL or "")}
        for key, label in (("API_ID", "API ID"), ("API_HASH", "API Hash"),
                           ("PHONE", "Teléfono (sin bot)"), ("BOT_TOKEN", "Token del bot"),
                           ("CHANNEL_ID", "ID grupo (-100...)")):
            row = ttk.Frame(telegram)
            row.pack(fill="x", pady=3)
            row.columnconfigure(1, weight=1)
            ttk.Label(row, text=label, style="Info.TLabel", width=20).grid(row=0, column=0, sticky="w", padx=(0, 6))
            variable = tk.StringVar(value=current[key])
            fields[key] = variable
            secret = key in ("API_HASH", "BOT_TOKEN")
            entry = ttk.Entry(row, textvariable=variable, show="*" if secret else "", style="Compact.TEntry")
            entry.grid(row=0, column=1, sticky="ew")
            entry_context_menu(entry)
            if secret:
                secret_entries.append(entry)
        group_buttons = FlowFrame(telegram)
        group_buttons.pack(fill="x", pady=(4, 0))
        def obtain_group_id():
            link = simpledialog.askstring("Obtener ID del grupo",
                "En Telegram: botón derecho en un mensaje → Copiar enlace.\nPega aquí el enlace t.me/c/... (no el enlace de invitación):", parent=win)
            if link is None:
                return
            try:
                fields["CHANNEL_ID"].set(group_id_from_link(link))
            except ValueError as error:
                messagebox.showerror("ID del grupo", str(error), parent=win)
        def recall_group_id():
            if CHANNEL:
                fields["CHANNEL_ID"].set(str(CHANNEL))
            else:
                messagebox.showinfo("ID del grupo", "No hay un ID de grupo guardado. Usa un enlace de mensaje compatible.", parent=win)
        group_buttons.add(ttk.Button(group_buttons, text="Obtener ID desde enlace", command=obtain_group_id))
        group_buttons.add(ttk.Button(group_buttons, text="Recordar ID guardado", command=recall_group_id))
        show_telegram = tk.BooleanVar(value=False)
        ttk.Checkbutton(telegram, text="Mostrar credenciales", variable=show_telegram,
                        command=lambda: [entry.configure(show="" if show_telegram.get() else "*")
                                         for entry in secret_entries]).pack(fill="x", anchor="w", pady=6)
        ttk.Label(telegram, text="Reconectar detiene las descargas. Para cuentas nuevas se pedirá el código.",
                  style="Info.TLabel").pack(fill="x", pady=4)

        def save_telegram():
            try:
                values = validate_connections({key: variable.get() for key, variable in fields.items()})
                identity_changed = any(values[key] != current[key] for key in ("API_ID", "API_HASH", "PHONE", "BOT_TOKEN"))
                if identity_changed:
                    identity = "|".join(values[key] for key in ("API_ID", "API_HASH", "PHONE", "BOT_TOKEN"))
                    values["SESSION_NAME"] = "session_" + hashlib.sha256(identity.encode()).hexdigest()[:16]
                merged = {**CONNECTIONS, **values}
                atomic_json(CONNECTIONS_FILE, merged)
                CONNECTIONS.update(merged)
            except ValueError as error:
                messagebox.showerror("Telegram", str(error), parent=win)
                return
            except OSError:
                messagebox.showerror("Telegram", "No se pudo guardar la conexión. Revisa los permisos de la carpeta de datos.", parent=win)
                return
            self.request_shutdown(restart=True)

        ttk.Button(telegram, text="Guardar y reconectar Telegram", command=save_telegram).pack(fill="x", pady=(4, 0))
        ttk.Label(qb, text="Conexión con qBittorrent", style="Header.TLabel").pack(fill="x", pady=(0, 6))
        ttk.Label(qb, text="Activa la interfaz web en qBittorrent y deja el programa abierto.",
                  style="Info.TLabel", wraplength=480).pack(fill="x", pady=(0, 8))
        qb_enabled = tk.BooleanVar(value=USE_QBITTORRENT)
        ttk.Checkbutton(qb, text="Enviar torrents a qBittorrent", variable=qb_enabled).pack(anchor="w", pady=(0, 8))
        qb_fields = {}
        qb_entries = {}
        for name, label, value in (("QBITTORRENT_URL", "Dirección Web UI", QBITTORRENT_URL or "http://localhost:8080"),
                                   ("QBITTORRENT_USERNAME", "Usuario", QBITTORRENT_USERNAME),
                                   ("QBITTORRENT_PASSWORD", "Contraseña", QBITTORRENT_PASSWORD)):
            row = ttk.Frame(qb)
            row.pack(fill="x", pady=4)
            row.columnconfigure(1, weight=1)
            ttk.Label(row, text=label, width=20, style="Info.TLabel").grid(row=0, column=0, sticky="w")
            variable = tk.StringVar(value=value)
            qb_fields[name] = variable
            entry = ttk.Entry(row, textvariable=variable, style="Compact.TEntry",
                              show="*" if name == "QBITTORRENT_PASSWORD" else "")
            entry.grid(row=0, column=1, sticky="ew")
            entry_context_menu(entry)
            qb_entries[name] = entry
        qb_show = tk.BooleanVar(value=False)
        ttk.Checkbutton(qb, text="Mostrar contraseña", variable=qb_show,
                        command=lambda: qb_entries["QBITTORRENT_PASSWORD"].configure(show="" if qb_show.get() else "*")).pack(anchor="w", pady=6)
        qb_status = tk.StringVar(value=QBITTORRENT_STATUS_MSG if USE_QBITTORRENT else "Desactivado")
        ttk.Label(qb, textvariable=qb_status, wraplength=480, style="Info.TLabel").pack(fill="x", pady=8)
        qb_buttons = FlowFrame(qb)
        qb_buttons.pack(fill="x")

        def configure_qb(save=False):
            global USE_QBITTORRENT, QBITTORRENT_URL, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD
            global QBITTORRENT_CONNECTED, QBITTORRENT_STATUS_MSG, _qb_session
            values = {key: variable.get().strip() if key != "QBITTORRENT_PASSWORD" else variable.get()
                      for key, variable in qb_fields.items()}
            values["QBITTORRENT_URL"] = values["QBITTORRENT_URL"].rstrip("/")
            parsed = urlparse(values["QBITTORRENT_URL"])
            if (not save or qb_enabled.get()) and (parsed.scheme not in ("http", "https") or not parsed.hostname):
                messagebox.showerror("qBittorrent", "Introduce una dirección http:// o https:// válida, por ejemplo http://localhost:8080.", parent=win)
                return
            if save:
                values["USE_QBITTORRENT"] = "true" if qb_enabled.get() else "false"
                try:
                    atomic_json(CONNECTIONS_FILE, {**CONNECTIONS, **values})
                except OSError:
                    messagebox.showerror("qBittorrent", "No se pudo guardar la conexión. Revisa los permisos de la carpeta de datos.", parent=win)
                    return
                CONNECTIONS.update(values)
                USE_QBITTORRENT = qb_enabled.get()
                QBITTORRENT_URL = values["QBITTORRENT_URL"]
                QBITTORRENT_USERNAME = values["QBITTORRENT_USERNAME"]
                QBITTORRENT_PASSWORD = values["QBITTORRENT_PASSWORD"]
                _qb_session = None
                QBITTORRENT_CONNECTED = False
                QBITTORRENT_STATUS_MSG = "Comprobando..." if USE_QBITTORRENT else "Desactivado"
                self.actualizar_estado_servicios()
                if not USE_QBITTORRENT:
                    qb_status.set("Guardado. Envío a qBittorrent desactivado.")
                    return
            qb_status.set("Comprobando...")
            for button in (qb_test, qb_save):
                button.configure(state="disabled")
            def worker():
                connected, status = False, "No se pudo conectar. Revisa dirección, usuario y contraseña."
                try:
                    with requests.Session() as session:
                        response = session.post(values["QBITTORRENT_URL"] + "/api/v2/auth/login",
                            data={"username": values["QBITTORRENT_USERNAME"], "password": values["QBITTORRENT_PASSWORD"]}, timeout=(5, 10))
                        connected = response.status_code == 200 and response.text.strip() == "Ok."
                        status = "Conectado" if connected else f"Acceso rechazado (HTTP {response.status_code}). Revisa usuario y contraseña."
                except requests.RequestException:
                    pass
                def finished():
                    global QBITTORRENT_CONNECTED, QBITTORRENT_STATUS_MSG
                    if save and USE_QBITTORRENT and (QBITTORRENT_URL, QBITTORRENT_USERNAME, QBITTORRENT_PASSWORD) == tuple(values[key] for key in ("QBITTORRENT_URL", "QBITTORRENT_USERNAME", "QBITTORRENT_PASSWORD")):
                        QBITTORRENT_CONNECTED, QBITTORRENT_STATUS_MSG = connected, status
                        self.actualizar_estado_servicios()
                    if win.winfo_exists():
                        qb_status.set(("Guardado. " if save else "") + status)
                        for button in (qb_test, qb_save):
                            button.configure(state="normal")
                GUI_EVENTS.put(finished)
            threading.Thread(target=worker, daemon=True).start()
        qb_test = ttk.Button(qb_buttons, text="Comprobar conexión", command=configure_qb)
        qb_buttons.add(qb_test)
        qb_save = ttk.Button(qb_buttons, text="Guardar y aplicar", command=lambda: configure_qb(True))
        qb_buttons.add(qb_save)
        ttk.Label(qb, text="Se aplica a los próximos torrents sin reiniciar.", wraplength=480, style="Info.TLabel").pack(fill="x", pady=8)
        win.update_idletasks()
        for panel in (ad, telegram, qb):
            for widget in panel.winfo_children():
                if isinstance(widget, ttk.Label):
                    widget.configure(wraplength=480)
        win.update_idletasks()
        minimum_height = max(ad.winfo_reqheight(), telegram.winfo_reqheight(), qb.winfo_reqheight()) + 210
        win.minsize(540, minimum_height)
        height = max(420, minimum_height)
        x = self.root.winfo_rootx() + (self.root.winfo_width() - 600) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        win.geometry(f"600x{height}+{max(0, x)}+{max(0, y)}")

    def abrir_opciones(self):
        if not self.options_menu:
            self.options_menu = tk.Menu(
                self.root,
                tearoff=0,
                bg=self.bg_card,
                fg=self.fg_text,
                activebackground=self.accent_soft,
                activeforeground="#f9fafb",
                bd=1,
                relief="solid",
                selectcolor=self.accent,
            )
            self.options_menu.add_command(label="Conexiones (Telegram / AllDebrid / qBittorrent)...", command=self.abrir_conexiones)
            self.options_menu.add_command(label="? Guía de configuración paso a paso", command=lambda: show_connection_help(self, DATA_DIR))
            self.options_menu.add_separator()
            self.options_menu.add_checkbutton(
                label="Minimizar al icono de la bandeja",
                variable=self.var_minimize_tray,
                command=self.on_change_minimize_tray,
            )
            self.options_menu.add_checkbutton(
                label="Iniciar con Windows",
                variable=self.var_start_windows,
                command=self.on_change_start_windows,
            )
            self.options_menu.add_checkbutton(
                label="Iniciar minimizado",
                variable=self.var_start_minimized,
                command=self.on_change_start_minimized,
            )
            self.options_menu.add_checkbutton(
                label="Mostrar gráfica de velocidad",
                variable=self.var_show_speed,
                command=self.on_change_show_speed,
            )
            self.options_menu.add_separator()
            self.options_menu.add_command(
                label="Seleccionar carpeta de descargas...",
                command=self.cambiar_carpeta_descargas_direct,
            )
            self.options_menu.add_command(
                label="Ver registro...",
                command=self.mostrar_registro,
            )
            self.options_menu.add_separator()
            self.options_menu.add_command(
                label="Guardar configuración ahora",
                command=self.save_config,
            )

        # Mostrar el menú justo debajo del botón de opciones
        try:
            x = self.btn_options.winfo_rootx()
            y = self.btn_options.winfo_rooty() + self.btn_options.winfo_height()
            self.options_menu.tk_popup(x, y)
        finally:
            if self.options_menu:
                self.options_menu.grab_release()

    def on_change_minimize_tray(self):
        if self.var_minimize_tray.get():
            if pystray and Image:
                self.create_tray_icon()
            else:
                messagebox.showwarning(
                    "Bandeja",
                    "pystray o pillow no están disponibles. No se puede usar icono de bandeja."
                )
                self.var_minimize_tray.set(False)
        self.save_config()

    def on_change_start_windows(self):
        err = set_startup_windows(self.var_start_windows.get())
        if err:
            messagebox.showerror("Arranque con Windows", err)
            self.var_start_windows.set(False)
        self.save_config()

    def on_change_start_minimized(self):
        self.save_config()

    def on_change_show_speed(self):
        self.update_speed_graph_visibility()
        self.save_config()

    def actualizar_estado_servicios(self):
        """Actualiza los labels de estado de AllDebrid y qBittorrent en la cabecera."""
        # AllDebrid
        if ALLDEBRID_API_KEY:
            if ALLDEBRID_CONNECTED:
                text_ad = "AllDebrid: Conectado"
                fg_ad = "#22c55e"
            else:
                text_ad = "AllDebrid: No conectado"
                fg_ad = "#ef4444"
        else:
            text_ad = "AllDebrid: No configurado"
       	    fg_ad = "#ef4444"

        if ALLDEBRID_API_KEY and not ALLDEBRID_CONNECTED:
            text_ad = f"AllDebrid: {ALLDEBRID_STATUS_MSG}"
        self.lbl_alldebrid.configure(text=text_ad, foreground=fg_ad)
        if hasattr(self, "lbl_telegram"):
            connected = TELEGRAM_STATUS == "Conectado" or TELEGRAM_STATUS.startswith("Conectado;")
            self.lbl_telegram.configure(text=f"● Telegram / API ID: {'Conectado' if connected else TELEGRAM_STATUS}",
                                        foreground="#22c55e" if connected else "#ef4444")
            group_status = TELEGRAM_GROUP_STATUS if connected else "No conectado"
            if not CHANNEL:
                group_status = "No configurado"
            self.lbl_telegram_group.configure(text=f"● Grupo: {group_status}",
                                              foreground="#22c55e" if group_status == "Conectado" else "#ef4444")

        # qBittorrent
        if qbittorrent_available():
            if QBITTORRENT_CONNECTED:
                text_qb = "qBittorrent: Conectado"
                fg_qb = "#22c55e"
            else:
                text_qb = "qBittorrent: No conectado"
                fg_qb = "#ef4444"
        else:
            text_qb = "qBittorrent: No configurado"
            fg_qb = "#ef4444"

        self.lbl_qbittorrent.configure(text=text_qb, foreground=fg_qb)
        if hasattr(self, "service_row"):
            self.service_row.relayout()

    def update_speed_graph_visibility(self):
        # Siempre arriba del listado dentro de center_frame
        if self.var_show_speed.get():
            self.speed_frame.pack_forget()
            self.speed_frame.pack(
                in_=self.center_frame,
                side="top",
                fill="x",
                pady=(4, 6),
                before=self.tree_container
            )
        else:
            self.speed_frame.pack_forget()

    # -------- Menús contextuales Treeview --------

    def on_right_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            col_id = self.tree.identify_column(event.x)
            try:
                idx = int(col_id[1:]) - 1
            except ValueError:
                return
            display_cols = list(self.tree["displaycolumns"])
            if idx < 0 or idx >= len(display_cols):
                return
            col_name = display_cols[idx]
            if col_name == "origen":
                return
            self.header_menu_current_col = col_name
            self.header_menu.tk_popup(event.x_root, event.y_root)
        else:
            row_id = self.tree.identify_row(event.y)
            if not row_id:
                menu = tk.Menu(
                    self.tree,
                    tearoff=0,
                    bg=self.bg_card,
                    fg=self.fg_text,
                    activebackground=self.accent_soft,
                    activeforeground="#f9fafb",
                    bd=0,
                    relief="flat",
                    selectcolor=self.accent,
                )
                menu.add_command(label="Limpiar completados", command=self.limpiar_completados)
                menu.tk_popup(event.x_root, event.y_root)
                return
            self.tree.selection_set(row_id)
            menu = tk.Menu(
                self.tree,
                tearoff=0,
                bg=self.bg_card,
                fg=self.fg_text,
                activebackground=self.accent_soft,
                activeforeground="#f9fafb",
                bd=0,
                relief="flat",
                selectcolor=self.accent,
            )
            menu.add_command(label="Subir en cola", command=self.mover_arriba)
            menu.add_command(label="Bajar en cola", command=self.mover_abajo)
            menu.add_separator()
            menu.add_command(label="Reiniciar descarga", command=self.reiniciar_descarga)
            menu.add_command(label="Detener descarga", command=self.detener_descargas)
            menu.add_separator()
            menu.add_command(label="Eliminar selección", command=self.eliminar_seleccion)
            menu.add_separator()
            menu.add_command(label="Limpiar completados", command=self.limpiar_completados)
            menu.tk_popup(event.x_root, event.y_root)

    # -------- Persistencia / cierre --------

    def save_config(self):
        try:
            displaycols = list(self.table_columns if self.compact_downloads else self.tree["displaycolumns"])
            col_widths = {col: self.tree.column(col, "width") for col in self.columns}
            cfg = {
                "download_path": os.path.abspath(DOWNLOAD_PATH),
                "max_parallel": current_max_parallel,
                "window_geometry": self.root.winfo_geometry(),
                "displaycolumns": displaycols,
                "column_widths": col_widths,
                "minimize_to_tray": self.var_minimize_tray.get(),
                "start_with_windows": self.var_start_windows.get(),
                "start_minimized": self.var_start_minimized.get(),
                "show_speed_graph": self.var_show_speed.get(),
            }
            atomic_json(CONFIG_FILE, cfg)
        except Exception as e:
            print(f"[!] Error guardando configuración: {e}")

    def mostrar_registro(self):
        """Abre una ventana con el registro de mensajes (prints) de la aplicación."""
        if self.log_window is not None and self.log_window.winfo_exists():
            # Si ya está abierta, solo la traemos al frente
            self.log_window.lift()
            self.log_window.focus_force()
            return

        win = tk.Toplevel(self.root)
        win.title(f"Registro - {APP_NAME_FULL}")
        install_dark_titlebar(win, self.bg_root, self.fg_text)
        win.configure(bg=self.bg_frame)
        win.geometry("900x500")

        text = tk.Text(
            win,
            wrap="none",
            bg="#121c2a",
            fg=self.fg_text,
            insertbackground=self.fg_text,
        )
        text.pack(fill="both", expand=True)

        scrollbar = ttk.Scrollbar(win, orient="vertical", command=text.yview)
        scrollbar.pack(side="right", fill="y")
        text.configure(yscrollcommand=scrollbar.set)

        self.log_window = win
        self.log_text_widget = text
        self._last_log_len = 0

        # Cargar historial existente y empezar a actualizar
        self._update_log_window()

    def _update_log_window(self):
        """Actualiza el contenido de la ventana de registro periódicamente."""
        if self.log_window is None or not self.log_window.winfo_exists():
            self.log_window = None
            self.log_text_widget = None
            return

        if self.log_text_widget is None:
            return

        lines = get_log_lines()
        if len(lines) > self._last_log_len:
            new_lines = lines[self._last_log_len:]
            self.log_text_widget.configure(state="normal")
            self.log_text_widget.insert("end", "\n".join(new_lines) + ("\n" if new_lines else ""))
            self.log_text_widget.see("end")
            self.log_text_widget.configure(state="disabled")
            self._last_log_len = len(lines)

        # Volver a actualizar dentro de 1 segundo
        self.root.after(1000, self._update_log_window)

    def on_close(self):
        # Si está activada la opción de minimizar a bandeja, se oculta en vez de cerrar
        if self.var_minimize_tray.get() and pystray and Image:
            self.root.withdraw()
            return

        self.save_config()
        save_download_state()
        self.request_shutdown()

    def on_unmap(self, event):
        if event.widget is self.root:
            try:
                state = self.root.state()
            except Exception:
                state = ""
            if state == "iconic" and self.var_minimize_tray.get() and pystray and Image:
                self.root.withdraw()

    # -------- Bandeja --------

    def create_tray_icon(self):
        if self.tray_icon or not (pystray and Image):
            return
        try:
            icon_img = None
            try:
                icon_path = IMAGES_DIR / "background.png"
                if icon_path.exists():
                    icon_img = Image.open(str(icon_path)).convert("RGBA")
            except Exception:
                icon_img = None
            if icon_img is None:
                icon_img = Image.new("RGBA", (64, 64), (10, 10, 20, 255))

            menu = pystray.Menu(
                pystray.MenuItem(
                    "Mostrar / ocultar ventana",
                    self.tray_show,
                    default=True  # doble clic
                ),
                pystray.MenuItem(
                    "Salir",
                    self.tray_quit
                ),
            )

            self.tray_icon = pystray.Icon(
                "telegram_downloader",
                icon_img,
                APP_NAME_FULL,
                menu,
            )

            def run_tray():
                self.tray_icon.run()

            self._tray_thread = threading.Thread(target=run_tray, daemon=True)
            self._tray_thread.start()
        except Exception as e:
            print(f"[!] No se pudo crear icono de bandeja: {e}")
            self.tray_icon = None

    def tray_show(self, icon=None, item=None):
        self.root.after(0, self.toggle_window_from_tray)

    def toggle_window_from_tray(self):
        try:
            state = self.root.state()
        except Exception:
            state = "normal"

        try:
            if state in ("withdrawn", "iconic"):
                self.root.deiconify()
                self.root.state("normal")
                self.root.lift()
                self.root.focus_force()
            else:
                self.root.withdraw()
        except Exception:
            pass

    def tray_quit(self, icon=None, item=None):
        GUI_EVENTS.put(self.request_shutdown)

    # -------- Varios GUI --------

    def cambiar_carpeta_descargas_direct(self):
        self.cambiar_carpeta_descargas()

    def cambiar_carpeta_descargas(self, event=None):
        global DOWNLOAD_PATH
        new_dir = filedialog.askdirectory(
            initialdir=DOWNLOAD_PATH,
            title="Selecciona la carpeta de descargas"
        )
        if not new_dir:
            return
        try:
            os.makedirs(new_dir, exist_ok=True)
            with tempfile.TemporaryFile(dir=new_dir):
                pass
        except OSError as error:
            messagebox.showerror("Carpeta de descargas", f"No se puede escribir en esa carpeta:\n{error}")
            return
        DOWNLOAD_PATH = new_dir
        self.info_label.configure(
            text=f"Carpeta de descargas: {os.path.abspath(DOWNLOAD_PATH)}"
        )
        self.save_config()
        print(f"[i] Carpeta de descargas cambiada a: {DOWNLOAD_PATH}")

    def sort_by_column(self, col: str):
        reverse = self.sort_reverse_by_col.get(col, False)

        with items_lock:
            key_func = None
            if col == "archivo":
                key_func = lambda it: it.filename.lower()
            elif col == "estado":
                key_func = lambda it: it.status
            elif col == "vel":
                key_func = lambda it: _inst_speeds.get(it.message_id, 0.0)
            elif col == "progreso":
                key_func = lambda it: it.progress

            if key_func is not None:
                download_items.sort(key=key_func, reverse=reverse)

        self.sort_reverse_by_col[col] = not reverse
        self.reordenar_tree_segun_modelo()
        self.save_config()

    def reordenar_tree_segun_modelo(self):
        with items_lock:
            seq = list(download_items)
        for idx, it in enumerate(seq):
            row_id = self.tree_items.get(it.message_id)
            if row_id:
                self.tree.move(row_id, "", idx)

    def mover_col_izquierda(self):
        col = self.header_menu_current_col
        if not col:
            return
        display_cols = list(self.tree["displaycolumns"])
        idx = display_cols.index(col)
        if idx <= 0:
            return
        display_cols[idx - 1], display_cols[idx] = display_cols[idx], display_cols[idx - 1]
        self.tree["displaycolumns"] = display_cols
        self.save_config()

    def mover_col_derecha(self):
        col = self.header_menu_current_col
        if not col:
            return
        display_cols = list(self.tree["displaycolumns"])
        idx = display_cols.index(col)
        if idx >= len(display_cols) - 1:
            return
        display_cols[idx + 1], display_cols[idx] = display_cols[idx], display_cols[idx + 1]
        self.tree["displaycolumns"] = display_cols
        self.save_config()


    def on_tree_button_press(self, event):
        """Click normal selecciona una fila. Ctrl+click alterna. Permite arrastrar para seleccionar por rango."""
        try:
            region = self.tree.identify_region(event.x, event.y)
            if region in ("heading", "separator"):
                return
            iid = self.tree.identify_row(event.y)
            if not iid:
                return

            ctrl = (event.state & 0x0004) != 0  # Control en Windows
            self._drag_start_iid = iid
            self._drag_additive = ctrl

            if ctrl:
                # Toggle sin borrar el resto
                if iid in self.tree.selection():
                    self.tree.selection_remove(iid)
                else:
                    self.tree.selection_add(iid)
            else:
                self.tree.selection_set(iid)

            self.tree.focus(iid)
            return "break"
        except Exception:
            return

    def on_tree_b1_motion(self, event):
        """Arrastre con botón izquierdo: selecciona rango vertical de filas."""
        if not self._drag_start_iid:
            return
        try:
            region = self.tree.identify_region(event.x, event.y)
            if region in ("heading", "separator"):
                return

            cur = self.tree.identify_row(event.y)
            if not cur:
                return "break"

            children = list(self.tree.get_children(""))
            if self._drag_start_iid not in children or cur not in children:
                return "break"

            i0 = children.index(self._drag_start_iid)
            i1 = children.index(cur)
            lo, hi = (i0, i1) if i0 <= i1 else (i1, i0)
            rango = children[lo : hi + 1]

            if self._drag_additive:
                sel = set(self.tree.selection())
                sel.update(rango)
                self.tree.selection_set(tuple(sel))
            else:
                self.tree.selection_set(tuple(rango))

            self.tree.focus(cur)
            return "break"
        except Exception:
            return "break"

    def on_tree_button_release(self, event):
        if self._drag_start_iid:
            self._drag_start_iid = None
            self._drag_additive = False
            return "break"
        return
    def on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            self.selected_message_id = None
            return
        row_id = sel[0]
        for mid, rid in self.tree_items.items():
            if rid == row_id:
                self.selected_message_id = mid
                break

    def mover_arriba(self):
        if self.selected_message_id is None:
            return
        with items_lock:
            idx = next(
                (i for i, it in enumerate(download_items) if it.message_id == self.selected_message_id),
                None
            )
            if idx is None or idx == 0:
                return
            item = download_items[idx]
            if item.status != "En cola":
                return
            download_items[idx - 1], download_items[idx] = download_items[idx], download_items[idx - 1]
        self.reordenar_tree_segun_modelo()
        self.save_config()

    def mover_abajo(self):
        if self.selected_message_id is None:
            return
        with items_lock:
            idx = next(
                (i for i, it in enumerate(download_items) if it.message_id == self.selected_message_id),
                None
            )
            if idx is None or idx >= len(download_items) - 1:
                return
            item = download_items[idx]
            if item.status != "En cola":
                return
            download_items[idx + 1], download_items[idx] = download_items[idx], download_items[idx + 1]
        self.reordenar_tree_segun_modelo()
        self.save_config()

    def reiniciar_descarga(self):
        if self.selected_message_id is None:
            messagebox.showinfo("Reiniciar descarga", "Selecciona primero una descarga.")
            return

        mid = self.selected_message_id
        with items_lock:
            item = items_by_id.get(mid)

        if not item:
            messagebox.showerror("Reiniciar descarga", "No se ha encontrado la descarga seleccionada.")
            return

        if item.status in ("Descargando", "Enviando a qBittorrent") or mid in _download_tasks:
            messagebox.showinfo(
                "Reiniciar descarga",
                "No puedes reiniciar una descarga que está en curso.\n"
                "Primero detenla con el botón 'Detener descarga'."
            )
            return

        if TELEGRAM_STATUS != "Conectado" and not TELEGRAM_STATUS.startswith("Conectado;"):
            messagebox.showerror("Reiniciar descarga", "Telegram no está conectado. Revisa Opciones → Conexiones.")
            return

        with items_lock:
            item.status = "En cola"
            item.progress = 0.0
            item.downloaded_bytes = 0
            item.total_bytes = 0
            item.error = None
            _progress_stats.pop(mid, None)
            _inst_speeds.pop(mid, None)
            _CANCEL_FLAGS.pop(mid, None)

        save_download_state()

        try:
            asyncio.run_coroutine_threadsafe(
                restart_download_coroutine(mid),
                app.loop
            )
            print(f"[i] Reiniciando descarga de mensaje {mid}")
        except Exception as e:
            messagebox.showerror("Reiniciar descarga", f"No se pudo reiniciar la descarga:\n{e}")

    def detener_descargas(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Detener descarga", "Selecciona una o varias descargas en curso.")
            return

        with items_lock:
            en_curso: List[DownloadItem] = []
            for mid, rid in self.tree_items.items():
                if rid in sel:
                    it = items_by_id.get(mid)
                    if it and it.status in ("Descargando", "En cola"):
                        en_curso.append(it)

        if not en_curso:
            messagebox.showinfo(
                "Detener descarga",
                "No hay descargas en curso en la selección."
            )
            return

        if len(en_curso) == 1:
            it = en_curso[0]
            msg = (
                "¿Seguro que quieres detener esta descarga en curso?\n\n"
                f"{it.filename}\n\n"
                "Se marcará como Detenido."
            )
        else:
            nombres = [it.filename for it in en_curso]
            if len(nombres) > 5:
                lista = "\n".join("• " + n for n in nombres[:5])
                lista += f"\n\n... y otras {len(nombres) - 5} más."
            else:
                lista = "\n".join("• " + n for n in nombres)
            msg = (
                f"Vas a detener {len(en_curso)} descargas en curso.\n\n"
                f"{lista}\n\n"
                "Se marcarán como Detenido."
            )

        if not messagebox.askyesno("Detener descarga", msg):
            return

        for it in en_curso:
            _CANCEL_FLAGS[it.message_id] = True
            with items_lock:
                if it.status == "En cola":
                    it.status = "Detenido"
                    it.error = "Detenido por el usuario"
            print(f"[i] Cancelación solicitada para mensaje {it.message_id}")
        save_download_state()

    def eliminar_seleccion(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Eliminar selección", "Selecciona una o varias descargas.")
            return

        with items_lock:
            mids_seleccionados: List[int] = []
            for mid, rid in self.tree_items.items():
                if rid in sel:
                    mids_seleccionados.append(mid)

            if not mids_seleccionados:
                messagebox.showinfo("Eliminar selección", "No se han encontrado descargas para eliminar.")
                return

            eliminables: List[DownloadItem] = []
            bloqueadas: List[DownloadItem] = []
            for mid in mids_seleccionados:
                it = items_by_id.get(mid)
                if not it:
                    continue
                if it.status in ("Descargando", "Enviando a qBittorrent"):
                    bloqueadas.append(it)
                else:
                    eliminables.append(it)

        if not eliminables:
            messagebox.showinfo(
                "Eliminar selección",
                "Todas las descargas seleccionadas están en curso y no se pueden eliminar.\n"
                "Si quieres detenerlas, usa el botón 'Detener descarga'."
            )
            return

        if len(eliminables) == 1:
            it = eliminables[0]
            confirm_text = (
                "¿Seguro que quieres eliminar esta descarga de la lista?\n\n"
                f"{it.filename}\n\n"
                "Si existe el archivo en disco también será borrado."
            )
            if bloqueadas:
                confirm_text += f"\n\n⚠️ {len(bloqueadas)} descarga(s) en curso no se eliminarán."
        else:
            nombres = [it.filename for it in eliminables]
            if len(nombres) > 5:
                lista = "\n".join("• " + n for n in nombres[:5])
                lista += f"\n\n... y otras {len(nombres) - 5} más."
            else:
                lista = "\n".join("• " + n for n in nombres)

            extra = ""
            if bloqueadas:
                extra = f"\n\n⚠️ {len(bloqueadas)} descarga(s) en curso no se eliminarán."

            confirm_text = (
                f"Vas a eliminar {len(eliminables)} descargas de la lista.\n\n"
                f"{lista}\n\n"
                "Si existen los archivos en disco también serán borrados."
                f"{extra}"
            )

        if not messagebox.askyesno("Eliminar selección", confirm_text):
            return

        mids_a_borrar = set()
        for it in eliminables:
            filepath = it.dest_path or os.path.join(DOWNLOAD_PATH, sanitize_filename(it.filename))
            try:
                for path in (filepath, filepath + ".downloading", filepath + ".downloading.json"):
                    if os.path.isfile(path):
                        os.remove(path)
                mids_a_borrar.add(it.message_id)
            except Exception as e:
                messagebox.showerror(
                    "Eliminar selección",
                    f"No se pudo borrar el archivo:\n{filepath}\n\n{e}"
                )

        with items_lock:
            download_items[:] = [it for it in download_items if it.message_id not in mids_a_borrar]
            for mid in mids_a_borrar:
                items_by_id.pop(mid, None)
                _inst_speeds.pop(mid, None)
                _CANCEL_FLAGS[mid] = True
                row_id = self.tree_items.pop(mid, None)
                if row_id:
                    canv = self.row_canvases.pop(mid, None)
                    if canv:
                        try:
                            canv.destroy()
                        except Exception:
                            pass
                    ocanv = self.origin_canvases.pop(mid, None)
                    if ocanv:
                        try:
                            ocanv.destroy()
                        except Exception:
                            pass
                    self.tree.delete(row_id)

            if getattr(self, "selected_message_id", None) in mids_a_borrar:
                self.selected_message_id = None

        save_download_state()
        self.save_config()

    def cambiar_parallel(self, delta: int):
        global current_max_parallel
        new_val = max(1, min(10, current_max_parallel + delta))
        current_max_parallel = new_val
        self.lbl_limit.configure(text=f"Simultáneas: {new_val}")
        print(f"[i] Nuevo límite de descargas simultáneas: {new_val}")
        self.save_config()

    def draw_speed_graph(self, speed_mbps: float):
        self.speed_history.append(speed_mbps)
        if len(self.speed_history) > 120:
            self.speed_history.pop(0)

        canvas = self.speed_canvas
        canvas.delete("all")

        if not self.speed_history:
            return

        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 1 or height <= 1:
            return

        max_speed = max(self.speed_history) or 1.0
        n = len(self.speed_history)
        if n < 2:
            return

        canvas.create_rectangle(0, 0, width, height, fill="#121c2a", outline="")

        for i in range(1, 4):
            y = height * i / 4
            canvas.create_line(0, y, width, y, fill="#263b51")

        puntos = []
        for i, val in enumerate(self.speed_history):
            x = i * (width / (n - 1))
            y = height - (val / max_speed) * (height - 6) - 3
            puntos.append((x, y))

        for i in range(len(puntos) - 1):
            x1, y1 = puntos[i]
            x2, y2 = puntos[i + 1]
            canvas.create_line(x1, y1, x2, y2, fill=self.accent, width=2)

        for x, y in puntos[-5:]:
            canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=self.accent, outline="")

    def _bind_tree_mouse_proxy(self, widget):
        """
        Hace que los canvas de progreso/icono reenvíen los eventos de ratón
        al Treeview para que funcione seleccionar / arrastrar.
        """
        self.tree_tooltip.bind(widget)
        widget.bind(
            "<Button-1>",
            lambda e, seq="<Button-1>": self._tree_mouse_from_canvas(e, seq),
        )
        widget.bind(
            "<B1-Motion>",
            lambda e, seq="<B1-Motion>": self._tree_mouse_from_canvas(e, seq),
        )
        widget.bind(
            "<ButtonRelease-1>",
            lambda e, seq="<ButtonRelease-1>": self._tree_mouse_from_canvas(e, seq),
        )

    def download_details(self, row_id):
        with items_lock:
            item = next((items_by_id[mid] for mid, row in self.tree_items.items()
                         if row == row_id and mid in items_by_id), None)
            if item is None:
                return ""
            details = (f"{item.filename}\nOrigen: {item.source}\nEstado: {item.status}"
                       f"\nProgreso: {item.progress:.1f}% · {self.compact_size(item.downloaded_bytes)} / {self.compact_size(item.total_bytes)}"
                       f"\nVelocidad: {_inst_speeds.get(item.message_id, 0) / 1024**2:.2f} MB/s")
            if item.dest_path:
                details += f"\nRuta: {item.dest_path}"
            if item.error:
                details += f"\nDetalle: {item.error}"
            return details

    def _tree_mouse_from_canvas(self, event, sequence: str):
        try:
            tx = event.x_root - self.tree.winfo_rootx()
            ty = event.y_root - self.tree.winfo_rooty()
            self.tree.event_generate(sequence, x=tx, y=ty)
        except Exception:
            pass
        return "break"

    def adapt_download_table(self, event=None):
        available = max(1, self.tree.winfo_width() - 2)
        self.compact_downloads = False
        narrow = available < 900
        style = ttk.Style(self.root)
        style.configure("Custom.Treeview", rowheight=28 if narrow else 34,
                        font=("Segoe UI", 8 if narrow else 9))
        self.tree.configure(displaycolumns=self.table_columns)
        self.tree.heading("archivo", text="Archivo")
        minimums = {"archivo": 85, "origen": 45, "estado": 85, "vel": 75, "progreso": 110}
        preferred = {"archivo": 160, "origen": 70, "estado": 145, "vel": 150, "progreso": 220}
        base = minimums if narrow else preferred
        extra = max(0, available - sum(base[column] for column in self.table_columns))
        for column in self.table_columns:
            width = base[column] + (extra if column == "archivo" else 0)
            self.tree.column(column, width=width, minwidth=base[column], stretch=False)
        self.tree.xview_moveto(0)
        if hasattr(self, "row_canvases"):
            with items_lock:
                snapshot = list(download_items)
            self._actualizar_barras_fila(snapshot)
            self._actualizar_iconos_origen(snapshot)

    @staticmethod
    def compact_size(value):
        amount = float(value)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if amount < 1024 or unit == "TB":
                return f"{amount:.1f} {unit}"
            amount /= 1024

    def _draw_compact_download(self, canvas, item, width, height):
        font = self.download_font
        line = font.metrics("linespace")
        selected = self.tree_items.get(item.message_id) in self.tree.selection()
        background = "#214669" if selected else "#172233"
        canvas.configure(bg=background)
        canvas.create_rectangle(0, 0, width, height, fill=background, outline="#304156")
        name = item.filename
        while name and font.measure(name) > width - 20:
            name = name[:-1]
        if name != item.filename:
            name = name[:-2] + "…"
        canvas.create_text(8, 3, text=name, anchor="nw", fill=self.fg_text, font=font)
        source = {"telegram": "Telegram", "http": "HTTP", "alldebrid": "AllDebrid", "torrent": "Torrent"}.get(item.source, item.source)
        canvas.create_text(8, line + 3, text=f"{source} · {item.status}", anchor="nw", fill="#8bc6ff", font=font)
        speed = _inst_speeds.get(item.message_id, 0)
        speed_text = f"Velocidad: {speed / 1024 / 1024:.2f} MB/s"
        if speed > 0 and item.total_bytes > item.downloaded_bytes:
            speed_text += f" · Restante: {format_eta((item.total_bytes - item.downloaded_bytes) / speed)}"
        canvas.create_text(8, 2 * line + 3, text=speed_text, anchor="nw", fill="#a8b8ca", font=font)
        progress = max(0.0, min(100.0, item.progress))
        top = 3 * line + 7
        canvas.create_rectangle(6, top, width - 6, height - 4, fill="#121c2a", outline="")
        if progress:
            canvas.create_rectangle(6, top, 6 + (width - 12) * progress / 100, height - 4,
                                    fill="#2c6694", outline="")
        text = f"{progress:.1f}%"
        if item.total_bytes:
            text += f" · {self.compact_size(item.downloaded_bytes)} / {self.compact_size(item.total_bytes)}"
        canvas.create_text(width / 2, (top + height - 4) / 2, text=text,
                           fill=self.fg_text, font=self.download_bold_font)

    def _actualizar_barras_fila(self, snapshot: List[DownloadItem]):
        ids_vivos = set()

        for it in snapshot:
            mid = it.message_id
            row_id = self.tree_items.get(mid)
            if not row_id:
                continue

            bbox = self.tree.bbox(row_id, "archivo" if self.compact_downloads else "progreso")
            if not bbox:
                continue

            x, y, w, h = bbox
            ids_vivos.add(mid)

            canv = self.row_canvases.get(mid)
            if canv is None:
                canv = tk.Canvas(self.tree, highlightthickness=0, bd=0, bg="#121c2a")
                self.row_canvases[mid] = canv
                self._bind_tree_mouse_proxy(canv)

            canv.place(x=x+1, y=y+2, width=w-2, height=h-4)
            canv.delete("all")

            if self.compact_downloads:
                self._draw_compact_download(canv, it, w - 2, h - 4)
                continue

            width = w - 2
            height = h - 4
            progress = max(0.0, min(100.0, it.progress))

            canv.create_rectangle(0, 0, width, height, fill="#121c2a", outline="#192739")

            if it.status == "Completado":
                bar_color = "#268d69"
            elif it.status == "Error":
                bar_color = "#ab4e58"
            elif it.status == "Detenido":
                bar_color = "#987335"
            else:
                bar_color = self.accent

            bar_w = int(width * (progress / 100.0))
            if bar_w > 0:
                canv.create_rectangle(0, 0, bar_w, height, fill=bar_color, outline="")

            if it.total_bytes:
                text = f"{progress:.1f}% · {self.compact_size(it.downloaded_bytes)} / {self.compact_size(it.total_bytes)}"
            else:
                text = f"{progress:4.1f}%"

            if self.download_font.measure(text) > width - 8:
                text = f"{progress:.1f}% · {self.compact_size(it.downloaded_bytes)} / {self.compact_size(it.total_bytes)}"
            if self.download_font.measure(text) > width - 8:
                text = f"{progress:.1f}%"
            canv.create_text(
                width // 2,
                height // 2,
                text=text,
                fill="#f9fafb",
                font=("Segoe UI", 8, "bold"),
            )

        muertos = [mid for mid in self.row_canvases.keys() if mid not in ids_vivos]
        for mid in muertos:
            try:
                self.row_canvases[mid].destroy()
            except Exception:
                pass
            self.row_canvases.pop(mid, None)

    def _actualizar_iconos_origen(self, snapshot: List[DownloadItem]):
        ids_vivos = set()

        if self.compact_downloads:
            for canvas in self.origin_canvases.values():
                canvas.destroy()
            self.origin_canvases.clear()
            return

        for it in snapshot:
            mid = it.message_id
            row_id = self.tree_items.get(mid)
            if not row_id:
                continue

            bbox = self.tree.bbox(row_id, "origen")
            if not bbox:
                continue

            x, y, w, h = bbox
            ids_vivos.add(mid)

            canv = self.origin_canvases.get(mid)
            if canv is None:
                canv = tk.Canvas(self.tree, highlightthickness=0, bd=0, bg="#121c2a")
                self.origin_canvases[mid] = canv
                self._bind_tree_mouse_proxy(canv)

            canv.place(x=x, y=y, width=w, height=h)
            canv.delete("all")

            src = it.source or "telegram"
            icon = self.icons_small.get(src)
            if icon:
                canv.create_image(w//2, h//2, image=icon)
            else:
                txt = {
                    "telegram": "TG",
                    "http": "DL",
                    "alldebrid": "AD",
                    "torrent": "TR",
                }.get(src, "?")
                canv.create_text(
                    w//2,
                    h//2,
                    text=txt,
                    fill="#e5e7eb",
                    font=("Segoe UI", 8, "bold"),
                )

        muertos = [mid for mid in self.origin_canvases.keys() if mid not in ids_vivos]
        for mid in muertos:
            try:
                self.origin_canvases[mid].destroy()
            except Exception:
                pass
            self.origin_canvases.pop(mid, None)

    def refresh(self):
        with items_lock:
            snapshot = list(download_items)
            active_count = sum(1 for it in snapshot if it.status == "Descargando")
            total_speed_bytes = sum(_inst_speeds.get(it.message_id, 0.0) for it in snapshot)

        speed_mbps = total_speed_bytes / 1024 / 1024
        if self.var_show_speed.get():
            self.speed_label.configure(text=f"Velocidad global: {speed_mbps:.2f} MB/s")
            self.draw_speed_graph(speed_mbps)

        for index, it in enumerate(snapshot):
            mid = it.message_id
            speed_bytes = _inst_speeds.get(mid, 0.0)
            speed_mbps_item = speed_bytes / 1024 / 1024

            vel_text = "—"
            if it.status == "Descargando":
                if it.total_bytes and speed_bytes > 0:
                    remaining = max(0, it.total_bytes - it.downloaded_bytes)
                    eta_sec = remaining / speed_bytes if remaining > 0 else 0
                    eta_str = format_eta(eta_sec)
                    vel_text = f"{speed_mbps_item:.2f} MB/s · {eta_str}"
                else:
                    vel_text = f"{speed_mbps_item:.2f} MB/s"

            if it.status == "Descargando" and self.tree.winfo_width() < 900:
                vel_text = f"{speed_mbps_item:.1f} MB/s"
            values = (
                it.filename,
                "",
                it.status,
                vel_text,
                "",
            )

            if mid not in self.tree_items:
                row_id = self.tree.insert("", "end", values=values)
                self.tree_items[mid] = row_id
            else:
                row_id = self.tree_items[mid]
                self.tree.item(row_id, values=values)
            state_tag = "complete" if it.status in ("Completado", "Enviado a qBittorrent") else "failed" if it.status == "Error" else "paused" if it.status == "Detenido" else ""
            self.tree.item(row_id, tags=("odd" if index % 2 else "even", state_tag))

        if snapshot:
            self.empty_state.place_forget()
        elif self.tree.winfo_height() >= 150:
            self.empty_state.place(relx=0.5, rely=0.5, anchor="center")
        else:
            self.empty_state.place_forget()
        completed = sum(it.status in ("Completado", "Enviado a qBittorrent") for it in snapshot)
        self.list_summary.configure(text=f"{len(snapshot)} archivos · {completed} finalizados")
        self.footer_status.configure(text="Telegram conectado · Envía un enlace al grupo para descargar." if TELEGRAM_STATUS == "Conectado" else f"Telegram: {TELEGRAM_STATUS}")
        self._actualizar_barras_fila(snapshot)
        self._actualizar_iconos_origen(snapshot)

        self.lbl_active.configure(text=f"Descargas activas: {active_count}")
        self.root.after(500, self.refresh)

    def limpiar_completados(self):
        with items_lock:
            ids_a_borrar = [it.message_id for it in download_items if it.status == "Completado"]
            if not ids_a_borrar:
                return

            download_items[:] = [it for it in download_items if it.message_id not in ids_a_borrar]
            for mid in ids_a_borrar:
                items_by_id.pop(mid, None)
                _inst_speeds.pop(mid, None)
                _CANCEL_FLAGS[mid] = True
                row_id = self.tree_items.pop(mid, None)
                if row_id:
                    canv = self.row_canvases.pop(mid, None)
                    if canv:
                        try:
                            canv.destroy()
                        except Exception:
                            pass
                    ocanv = self.origin_canvases.pop(mid, None)
                    if ocanv:
                        try:
                            ocanv.destroy()
                        except Exception:
                            pass
                    self.tree.delete(row_id)

            if getattr(self, "selected_message_id", None) in ids_a_borrar:
                self.selected_message_id = None

        save_download_state()
        self.save_config()

    def abrir_descargas(self):
        try:
            path = os.path.abspath(DOWNLOAD_PATH)
            if os.name == "nt":
                os.startfile(path)
            else:
                import subprocess, sys as _sys
                if _sys.platform == "darwin":
                    subprocess.Popen(["open", path])
                else:
                    subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la carpeta de descargas:\n{e}")

    def run(self):
        self.root.mainloop()


def start_gui():
    gui = DownloadGUI()
    gui.run()

# ==========================
# ARRANQUE
# ==========================

async def send_report(client, chat_id, text, **kwargs):
    if SHUTDOWN.is_set():
        return
    try:
        await client.send_message(chat_id, "[Telegram Downloader]\n" + text[:3900],
                                  parse_mode=enums.ParseMode.DISABLED, **kwargs)
    except Exception:
        print("[!] No se pudo enviar el aviso a Telegram.")


async def run_application():
    global TELEGRAM_STATUS, TELEGRAM_GROUP_STATUS
    TELEGRAM_GROUP_STATUS = "No conectado" if CHANNEL else "No configurado"
    started = False
    try:
        if not API_ID or not API_HASH or not CHANNEL:
            TELEGRAM_STATUS = "Configura la conexión en Opciones"
            GUI_EVENTS.put(lambda: GUI_APP.abrir_conexiones())
        else:
            TELEGRAM_STATUS = "Conectando..."
            connection = asyncio.create_task(app.start())
            while not connection.done() and not SHUTDOWN.is_set():
                await asyncio.sleep(0.1)
            if SHUTDOWN.is_set() and not connection.done():
                connection.cancel()
            try:
                await connection
                started = True
                TELEGRAM_STATUS = "Conectado"
                try:
                    await app.get_chat(CHANNEL)
                    TELEGRAM_GROUP_STATUS = "Conectado"
                except Exception:
                    TELEGRAM_GROUP_STATUS = "ID incorrecto o sin acceso"
                    TELEGRAM_STATUS = "Conectado; revisa el ID o el acceso al grupo"
            except asyncio.CancelledError:
                pass
            except Exception as error:
                TELEGRAM_STATUS = f"Error: {type(error).__name__}. Revisa Conexiones"
                print(f"[Telegram] {TELEGRAM_STATUS}")
        while not SHUTDOWN.is_set():
            await asyncio.sleep(0.2)
    finally:
        for mid in list(_download_tasks):
            _CANCEL_FLAGS[mid] = True
        tasks = list(_download_tasks.values())
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=5)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        try:
            if started:
                await asyncio.wait_for(app.stop(), timeout=10)
            elif app.is_connected:
                await asyncio.wait_for(app.disconnect(), timeout=10)
        except Exception:
            print("[Telegram] No se pudo completar la desconexión en el tiempo previsto.")
        with items_lock:
            for item in download_items:
                if item.status in ("Descargando", "En cola", "Enviando a qBittorrent"):
                    item.status = "Detenido"
                    item.error = "Interrumpido al cerrar; puedes reiniciarlo desde la lista"
        save_download_state()


def restart_application(extra_arguments=()):
    arguments = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, str(BASE_DIR / "auto.py")]
    return subprocess.Popen([*arguments, *extra_arguments], cwd=str(BASE_DIR),
                            env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"})


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        gui = DownloadGUI()
        gui.root.withdraw()
        gui.abrir_conexiones()
        gui.connections_window.withdraw()
        help_window = show_connection_help(gui, DATA_DIR)
        help_window.withdraw()
        gui.root.update()
        atomic_json(DATA_DIR / "self_test.json", {"version": APP_VERSION, "connections": True, "help": help_window.winfo_exists(),
                                                  "images": len(gui.icons), "bundle_dir": getattr(sys, "_MEIPASS", None), "tgcrypto": bool(__import__("tgcrypto"))})
        gui.root.destroy()
        if "--self-test-restart" in sys.argv:
            atomic_json(DATA_DIR / "restart_test.json", {"parent_bundle_dir": getattr(sys, "_MEIPASS", None)})
            restart_application(("--self-test",))
        sys.exit(0)
    load_download_state()
    gui_thread = threading.Thread(target=start_gui, daemon=True)
    gui_thread.start()
    threading.Thread(target=test_alldebrid_key, daemon=True).start()
    if qbittorrent_available():
        threading.Thread(target=test_qbittorrent_connection, daemon=True).start()
    try:
        app.run(run_application())
    finally:
        SHUTDOWN.set()
        if _single_instance_server_sock:
            _single_instance_server_sock.close()
        if RESTART_REQUESTED:
            restart_application()
        os._exit(0)

