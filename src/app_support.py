"""Persistence, validation and service checks shared by the UI and downloads."""
import json
import os
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import urlparse

_write_lock = threading.RLock()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)


def read_json(path, default):
    try:
        with open(path, encoding='utf-8') as stream:
            value = json.load(stream)
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def safe_filename(name):
    name = str(name or '').replace('\\', '/').rsplit('/', 1)[-1]
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*]', '_', name).strip().rstrip('. ')
    if not name or name in ('.', '..'):
        name = 'archivo'
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        name = '_' + name
    stem, extension = os.path.splitext(name)
    return stem[:180] + extension[:20]


def is_debrid_url(url):
    host = (urlparse(url).hostname or '').lower()
    return any(host == domain or host.endswith('.' + domain)
               for domain in ('alldebrid.com', 'alldebrid.fr', 'debrid.it', 'debrid.link'))


def validate_connections(values):
    result = {key: str(value).strip() for key, value in values.items()}
    try:
        if int(result['API_ID']) <= 0 or int(result['CHANNEL_ID']) == 0:
            raise ValueError
    except (ValueError, KeyError):
        raise ValueError('API ID debe ser positivo y el ID del grupo debe ser un número distinto de cero.') from None
    if not re.fullmatch(r'[0-9a-fA-F]{32}', result.get('API_HASH', '')):
        raise ValueError('API Hash de Telegram debe contener 32 caracteres hexadecimales.')
    token = result.get('BOT_TOKEN', '')
    if token and not re.fullmatch(r'\d+:[A-Za-z0-9_-]+', token):
        raise ValueError('El token del bot de Telegram no tiene un formato válido.')
    if not token and not re.fullmatch(r'\+?\d{7,15}', result.get('PHONE', '')):
        raise ValueError('Introduce el teléfono con prefijo internacional o un token de bot.')
    return result


def check_alldebrid(key, request):
    if not key:
        return False, 'No configurado'
    try:
        response = request('https://api.alldebrid.com/v4/user',
                           headers={'Authorization': f'Bearer {key}'}, timeout=(10, 20))
        data = response.json()
        if data.get('status') != 'success':
            error = data.get('error') or {}
            return False, str(error.get('message') or error.get('code') or f'HTTP {response.status_code}')
        response.raise_for_status()
        user = (data.get('data') or {}).get('user') or {}
        if not user.get('isPremium') and not user.get('isTrial'):
            return False, 'Clave válida; suscripción premium caducada o no activa'
        return True, 'Premium activo'
    except Exception:
        return False, 'No se pudo comprobar AllDebrid. Revisa la conexión o la clave.'


def group_id_from_link(value):
    match = re.fullmatch(r'(?:https?://)?(?:t\.me|telegram\.me)/c/([1-9]\d*)/[1-9]\d*(?:/[1-9]\d*)?(?:\?[^\s]*)?', value.strip())
    if not match:
        raise ValueError('Copia el enlace de un mensaje del grupo: https://t.me/c/1234567890/12. Los enlaces de invitación o con nombre público no contienen el ID numérico.')
    return str(-1000000000000 - int(match.group(1)))
