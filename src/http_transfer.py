"""HTTP transfers with safe partial files and conditional Range requests."""
import os
import re
import time
from pathlib import Path

import requests
from app_support import atomic_json, read_json


def transfer_http(url, destination, cancelled, on_progress, expected_total=0):
    partial = destination + '.downloading'
    metadata_path = partial + '.json'
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        if cancelled():
            raise RuntimeError('Cancelado por el usuario')
        metadata = read_json(metadata_path, {})
        validator = metadata.get('etag') or metadata.get('last_modified')
        offset = os.path.getsize(partial) if os.path.isfile(partial) and validator else 0
        headers = {'Accept-Encoding': 'identity'}
        if offset:
            headers.update({'Range': f'bytes={offset}-', 'If-Range': validator})
        try:
            with requests.get(url, stream=True, timeout=(10, 30), allow_redirects=True, headers=headers) as response:
                if response.status_code == 416 and offset:
                    os.remove(partial)
                    if os.path.exists(metadata_path):
                        os.remove(metadata_path)
                    continue
                response.raise_for_status()
                if 'text/html' in response.headers.get('Content-Type', '').lower():
                    raise ValueError('El enlace devolvió una página web, no un archivo descargable.')
                length = int(response.headers.get('Content-Length') or 0)
                total = length or int(expected_total or 0)
                if response.status_code == 206:
                    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
                    if not match or int(match[1]) != offset:
                        raise ValueError('El servidor devolvió un rango de descarga incorrecto.')
                    total = int(match[3])
                    if offset and ((metadata.get('etag') and response.headers.get('ETag') != metadata['etag']) or
                                   (not metadata.get('etag') and metadata.get('last_modified') and
                                    response.headers.get('Last-Modified') != metadata['last_modified'])):
                        raise ValueError('El archivo remoto ha cambiado durante la reanudación.')
                else:
                    offset = 0
                if expected_total and total and total != int(expected_total):
                    raise ValueError('El tamaño del archivo no coincide con el indicado por AllDebrid.')
                # Requests decodes compressed bodies; their encoded length cannot validate written bytes.
                encoded = response.headers.get('Content-Encoding', '').lower() not in ('', 'identity')
                if encoded:
                    if offset:
                        raise ValueError('El servidor comprimió una respuesta parcial.')
                    total = int(expected_total or 0)
                etag = response.headers.get('ETag') or ''
                atomic_json(metadata_path, {'etag': etag if not etag.startswith('W/') and not encoded else '',
                                           'last_modified': response.headers.get('Last-Modified', '') if not encoded else ''})
                current = offset
                with open(partial, 'ab' if offset else 'wb') as stream:
                    for chunk in response.iter_content(chunk_size=256 * 1024):
                        if cancelled():
                            raise RuntimeError('Cancelado por el usuario')
                        if chunk:
                            stream.write(chunk)
                            current += len(chunk)
                            on_progress(current, total)
                    stream.flush()
                    os.fsync(stream.fileno())
                if cancelled():
                    raise RuntimeError('Cancelado por el usuario')
                if not current or (total and current != total):
                    raise requests.ConnectionError(f'Descarga incompleta: {current} de {total or "tamaño desconocido"} bytes')
                # Paths are reserved before starting. Never overwrite an unrelated final file.
                if os.path.exists(destination):
                    raise FileExistsError('Ya existe un archivo con el nombre de destino.')
                os.rename(partial, destination)
                if os.path.exists(metadata_path):
                    os.remove(metadata_path)
                on_progress(current, total or current)
                return current
        except requests.RequestException:
            if attempt == 2:
                raise
            for _ in range(10 * (attempt + 1)):
                if cancelled():
                    raise RuntimeError('Cancelado por el usuario')
                time.sleep(0.1)
    raise RuntimeError('No se pudo completar la descarga HTTP.')
