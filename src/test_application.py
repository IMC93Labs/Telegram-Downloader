import asyncio
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

TEST_ROOT = tempfile.TemporaryDirectory(prefix='td-tests-', dir=Path(__file__).parent)
os.environ['TELEGRAM_DOWNLOADER_DATA_DIR'] = TEST_ROOT.name
os.environ['DOWNLOAD_PATH'] = str(Path(TEST_ROOT.name) / 'downloads')
for key in ('API_ID', 'API_HASH', 'CHANNEL_ID', 'PHONE', 'BOT_TOKEN', 'ALLDEBRID_API_KEY', 'ALLDEBRID_APIKEY'):
    os.environ.pop(key, None)

import auto
from app_support import atomic_json, read_json, safe_filename, check_alldebrid, validate_connections, is_debrid_url
from http_transfer import transfer_http


def close_gui(gui):
    gui.root.update_idletasks()
    def descendants(widget):
        yield widget
        for child in widget.winfo_children():
            yield from descendants(child)
    owners = list(descendants(gui.root))
    for timer in gui.root.tk.call('after', 'info'):
        script = gui.root.tk.call('after', 'info', timer)[0].split()[0]
        owner = next((widget for widget in owners if script in (widget._tclCommands or [])), gui.root)
        owner.after_cancel(timer)
    while not auto.GUI_EVENTS.empty():
        auto.GUI_EVENTS.get_nowait()
    gui.root.destroy()


class Response:
    def __init__(self, body=b'abcdef', status=200, headers=None, error=None, data=None):
        self.status_code = status
        self.headers = headers or {'Content-Length': str(len(body)), 'Content-Type': 'application/octet-stream', 'ETag': '"v1"'}
        self.body = body
        self.error = error
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        if self.status_code >= 400:
            raise auto.requests.HTTPError(str(self.status_code))

    def json(self):
        return self.data

    def iter_content(self, **kwargs):
        yield self.body
        if self.error:
            raise self.error


class SupportTests(unittest.TestCase):
    def test_filenames(self):
        for name in ('../a.zip', '..\\a.zip', 'CON', 'a:bad?.zip', '..', 'a. ', '\x00name'):
            safe = safe_filename(name)
            self.assertFalse(any(c in safe for c in '\\/:*?"<>|\x00'))
            self.assertNotIn(safe, ('', '.', '..', 'CON'))

    def test_atomic_concurrent_writes(self):
        target = Path(TEST_ROOT.name) / 'atomic.json'
        workers = [threading.Thread(target=atomic_json, args=(target, {'value': i})) for i in range(20)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertIn(read_json(target, {})['value'], range(20))

    def test_validation(self):
        values = {'API_ID': '123', 'API_HASH': 'a' * 32, 'CHANNEL_ID': '-100123', 'PHONE': '+34123456789', 'BOT_TOKEN': ''}
        self.assertEqual(validate_connections(values), values)
        self.assertEqual(validate_connections({**values, 'PHONE': '', 'BOT_TOKEN': '123:abc_DEF'})['BOT_TOKEN'], '123:abc_DEF')
        with self.assertRaises(ValueError):
            validate_connections({**values, 'CHANNEL_ID': 'invalid'})

    def test_premium_and_expired(self):
        for premium, expected in ((True, True), (False, False)):
            response = Response(data={'status': 'success', 'data': {'user': {'isPremium': premium, 'isTrial': False}}})
            connected, status = check_alldebrid('secret', lambda *args, **kwargs: response)
            self.assertEqual(connected, expected)
            self.assertNotIn('secret', status)
        connected, status = check_alldebrid('secret', lambda *args, **kwargs: Response(status=401, data={'status': 'error', 'error': {'code': 'AUTH_BAD_APIKEY'}}))
        self.assertFalse(connected)
        self.assertIn('AUTH_BAD_APIKEY', status)

    def test_domain_matching(self):
        self.assertTrue(is_debrid_url('https://cdn.debrid.it/file'))
        self.assertFalse(is_debrid_url('https://debrid.it.attacker.test/file'))
        self.assertFalse(is_debrid_url('https://alldebrid@attacker.test/file'))


class TransferTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=TEST_ROOT.name)
        self.path = str(Path(self.folder.name) / 'file.bin')

    def tearDown(self):
        self.folder.cleanup()

    def download(self, **kwargs):
        return transfer_http('https://example.test/file', self.path, kwargs.get('cancelled', lambda: False), lambda *args: None, kwargs.get('expected', 0))

    def test_success_and_no_overwrite(self):
        with patch('http_transfer.requests.get', return_value=Response()):
            self.assertEqual(self.download(), 6)
            self.assertEqual(Path(self.path).read_bytes(), b'abcdef')
            with self.assertRaises(FileExistsError):
                self.download()
            self.assertEqual(Path(self.path).read_bytes(), b'abcdef')

    def test_resume_after_interruption(self):
        first = Response(b'abc', headers={'Content-Length': '6', 'ETag': '"v1"'}, error=auto.requests.ConnectionError('interrupted'))
        second = Response(b'def', status=206, headers={'Content-Length': '3', 'Content-Range': 'bytes 3-5/6', 'ETag': '"v1"'})
        with patch('http_transfer.requests.get', side_effect=[first, second]) as get, patch('http_transfer.time.sleep'):
            self.assertEqual(self.download(), 6)
            self.assertEqual(get.call_args_list[1].kwargs['headers']['Range'], 'bytes=3-')
            self.assertEqual(get.call_args_list[1].kwargs['headers']['If-Range'], '"v1"')
            self.assertEqual(Path(self.path).read_bytes(), b'abcdef')

    def test_server_ignores_range(self):
        Path(self.path + '.downloading').write_bytes(b'abc')
        atomic_json(self.path + '.downloading.json', {'etag': '"old"'})
        with patch('http_transfer.requests.get', return_value=Response()):
            self.download()
        self.assertEqual(Path(self.path).read_bytes(), b'abcdef')

    def test_invalid_range_and_html(self):
        for response in (Response(status=206, headers={'Content-Range': 'bytes 2-5/6'}),
                         Response(headers={'Content-Type': 'text/html'})):
            with patch('http_transfer.requests.get', return_value=response), self.assertRaises(ValueError):
                self.download()
            self.assertFalse(Path(self.path).exists())

    def test_cancel_and_size_mismatch(self):
        with self.assertRaisesRegex(RuntimeError, 'Cancelado'):
            self.download(cancelled=lambda: True)
        with patch('http_transfer.requests.get', return_value=Response()), self.assertRaises(ValueError):
            self.download(expected=12)

    def test_changed_file_cannot_append(self):
        Path(self.path + '.downloading').write_bytes(b'abc')
        atomic_json(self.path + '.downloading.json', {'etag': '"old"'})
        response = Response(b'def', 206, {'Content-Range': 'bytes 3-5/6', 'ETag': '"new"'})
        with patch('http_transfer.requests.get', return_value=response), self.assertRaises(ValueError):
            self.download()
        self.assertFalse(Path(self.path).exists())


class ApplicationTests(unittest.TestCase):
    def setUp(self):
        auto.download_items.clear()
        auto.items_by_id.clear()
        auto.SHUTDOWN.clear()
        auto._active_downloads = 0
        auto._active_by_source.update(telegram=0, http=0, alldebrid=0)
        auto.current_max_parallel = 4

    def add(self, item):
        auto.download_items.append(item)
        auto.items_by_id[item.message_id] = item

    def test_queue_uses_available_transport(self):
        self.add(auto.DownloadItem(1, 'telegram', source='telegram'))
        self.add(auto.DownloadItem(2, 'http', source='http'))
        auto._active_by_source['telegram'] = 3
        auto._active_downloads = 3
        self.assertTrue(auto.app.loop.run_until_complete(asyncio.wait_for(auto.acquire_slot(2, 'http'), 1)))
        self.assertEqual(auto.items_by_id[2].status, 'Descargando')
        auto.release_slot('http')
        self.assertEqual(auto._active_downloads, 3)

    def test_deleted_queue_task_exits(self):
        self.assertFalse(auto.app.loop.run_until_complete(auto.acquire_slot(999, 'http')))

    def test_cancelled_http_task_releases_slot(self):
        self.add(auto.DownloadItem(3, 'http', source='http'))
        msg = SimpleNamespace(id=3)
        with patch('auto._http_download_task_impl', new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError):
                auto.app.loop.run_until_complete(auto._http_download_task(None, msg, 'https://example.test', 'file'))
        self.assertEqual(auto._active_downloads, 0)
        self.assertEqual(auto._active_by_source['http'], 0)

    def test_bot_and_account_authorization(self):
        user = SimpleNamespace(id=12)
        client = SimpleNamespace(sign_in_bot=AsyncMock(return_value=user),
                                 send_code=AsyncMock(return_value=SimpleNamespace(phone_code_hash='hash')),
                                 sign_in=AsyncMock(return_value=user))
        with patch('auto.BOT_TOKEN', '123:token'):
            self.assertIs(auto.app.loop.run_until_complete(auto.DesktopClient.authorize(client)), user)
            client.sign_in_bot.assert_awaited_once_with('123:token')
        with patch('auto.BOT_TOKEN', ''), patch('auto.PHONE', '+34123456789'), patch('auto.ask_telegram', new=AsyncMock(return_value='12345')):
            self.assertIs(auto.app.loop.run_until_complete(auto.DesktopClient.authorize(client)), user)
            client.sign_in.assert_awaited_once_with('+34123456789', 'hash', '12345')

    def test_unique_paths_and_history(self):
        first = auto.make_unique_path(TEST_ROOT.name, 'same.zip')
        second = auto.make_unique_path(TEST_ROOT.name, 'same.zip')
        self.assertNotEqual(first, second)
        self.add(auto.DownloadItem(1, 'same.zip', status='Enviado a qBittorrent', dest_path=first))
        auto.save_download_state()
        auto.load_download_state()
        self.assertEqual(auto.items_by_id[1].status, 'Enviado a qBittorrent')
        self.assertEqual(auto.items_by_id[1].dest_path, first)

    def test_photo_is_object(self):
        photo = object()
        msg = SimpleNamespace(document=None, video=None, audio=None, voice=None, video_note=None, photo=photo, animation=None)
        self.assertIs(auto.get_media_file(msg), photo)

    def test_own_notification_is_ignored(self):
        msg = SimpleNamespace(id=11, text='[Telegram Downloader]\nhttps://example.test/file', caption=None,
                              document=None, video=None, audio=None, voice=None, video_note=None, photo=None, animation=None)
        auto.app.loop.run_until_complete(auto.auto_http_download(None, msg))
        self.assertNotIn(11, auto.items_by_id)

    def test_restart_resets_frozen_environment(self):
        with patch('auto.subprocess.Popen') as process:
            auto.restart_application()
            self.assertEqual(process.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')

    def test_qbittorrent_configuration_and_classic_entry_paste(self):
        with patch.multiple(auto, USE_QBITTORRENT=False, QBITTORRENT_URL='', QBITTORRENT_USERNAME='',
                            QBITTORRENT_PASSWORD='', QBITTORRENT_CONNECTED=False, QBITTORRENT_STATUS_MSG='No configurado', _qb_session=None):
            gui = auto.DownloadGUI()
            try:
                self.assertTrue(gui.root.bind_class('Entry', '<Button-3>'))
                self.assertTrue(gui.root.bind_class('TEntry', '<Button-3>'))
                gui.abrir_conexiones()
                notebook = next(widget for widget in gui.connections_window.winfo_children() if isinstance(widget, auto.ttk.Notebook))
                self.assertEqual(len(notebook.tabs()), 3)
                panel = notebook.nametowidget(notebook.tabs()[2])
                widgets = []
                def collect(widget):
                    for child in widget.winfo_children():
                        widgets.append(child)
                        collect(child)
                collect(panel)
                entries = [widget for widget in widgets if isinstance(widget, auto.ttk.Entry)]
                for entry, value in zip(entries, ('http://localhost:8080', 'test-user', 'test-password')):
                    entry.delete(0, 'end')
                    entry.insert(0, value)
                    self.assertTrue(entry.bind('<Button-3>'))
                next(widget for widget in widgets if isinstance(widget, auto.ttk.Checkbutton)
                     and widget.cget('text') == 'Enviar torrents a qBittorrent').invoke()
                save = next(widget for widget in widgets if isinstance(widget, auto.ttk.Button) and widget.cget('text') == 'Guardar y aplicar')
                with patch('auto.requests.Session') as session, patch('auto.threading.Thread') as thread:
                    session.return_value.__enter__.return_value.post.return_value = SimpleNamespace(status_code=200, text='Ok.')
                    thread.side_effect = lambda target, **kwargs: SimpleNamespace(start=target)
                    save.invoke()
                    gui.process_events()
                    self.assertTrue(auto.QBITTORRENT_CONNECTED)
                    self.assertEqual(read_json(auto.CONNECTIONS_FILE, {})['QBITTORRENT_USERNAME'], 'test-user')
                    self.assertFalse(auto.SHUTDOWN.is_set())
            finally:
                close_gui(gui)

    def test_guide_navigation(self):
        gui = auto.DownloadGUI()
        try:
            window = auto.show_connection_help(gui, auto.DATA_DIR)
            notebook = next(widget for widget in window.winfo_children() if isinstance(widget, auto.ttk.Notebook))
            panel = notebook.nametowidget(notebook.tabs()[0])
            bar = next(widget for widget in panel.winfo_children() if isinstance(widget, auto.ttk.Frame)
                       and any(isinstance(child, auto.ttk.Button) and child.cget("text") == "Siguiente →" for child in widget.winfo_children()))
            next_button = next(widget for widget in bar.winfo_children() if isinstance(widget, auto.ttk.Button) and widget.cget('text') == 'Siguiente →')
            window.geometry('560x440')
            for _ in range(4):
                gui.root.update()
            self.assertTrue(next_button.winfo_ismapped())
            self.assertLessEqual(next_button.winfo_rooty() + next_button.winfo_height(),
                                 window.winfo_rooty() + window.winfo_height())
            next_button.invoke()
            counter = panel.winfo_children()[0]
            self.assertIn('PASO 2', counter.cget('text'))
            notebook.select(2)
            qpanel = notebook.nametowidget(notebook.tabs()[2])
            self.assertIn('PASO 1', qpanel.winfo_children()[0].cget('text'))
        finally:
            close_gui(gui)

    def test_telegram_and_group_status_colors(self):
        gui = auto.DownloadGUI()
        try:
            with patch.multiple(auto, CHANNEL=-1001234567890, TELEGRAM_STATUS='Conectado;', TELEGRAM_GROUP_STATUS='ID incorrecto o sin acceso'):
                gui.actualizar_estado_servicios()
                self.assertEqual(str(gui.lbl_telegram.cget('foreground')), '#22c55e')
                self.assertEqual(str(gui.lbl_telegram_group.cget('foreground')), '#ef4444')
            with patch.multiple(auto, CHANNEL=-1001234567890, TELEGRAM_STATUS='Conectado', TELEGRAM_GROUP_STATUS='Conectado'):
                gui.actualizar_estado_servicios()
                self.assertEqual(str(gui.lbl_telegram_group.cget('foreground')), '#22c55e')
            with patch('auto.TELEGRAM_STATUS', 'Error de conexión'):
                gui.actualizar_estado_servicios()
                self.assertEqual(str(gui.lbl_telegram.cget('foreground')), '#ef4444')
                self.assertEqual(str(gui.lbl_telegram_group.cget('foreground')), '#ef4444')
        finally:
            close_gui(gui)

    def test_gui_connections_and_save_key(self):
        gui = auto.DownloadGUI()
        gui.root.withdraw()
        try:
            gui.abrir_conexiones()
            window = gui.connections_window
            window.withdraw()
            widgets = []
            def collect(widget):
                for child in widget.winfo_children():
                    widgets.append(child)
                    collect(child)
            collect(window)
            entries = [widget for widget in widgets if isinstance(widget, auto.ttk.Entry)]
            self.assertEqual(len(entries), 9)
            self.assertEqual(entries[0].cget('show'), '*')
            self.assertTrue(entries[0].bind('<Button-3>'))
            with patch.object(entries[0], 'event_generate') as paste:
                entries[0].context_menu.invoke(2)
                paste.assert_called_once_with('<<Paste>>')
            entries[0].delete(0, 'end')
            entries[0].insert(0, 'new-test-key')
            hint = next(widget for widget in widgets if isinstance(widget, auto.ttk.Label)
                        and widget.cget('textvariable') and 'Clave introducida' in str(widget.getvar(widget.cget('textvariable'))))
            self.assertIn('Guardar y aplicar', str(hint.getvar(hint.cget('textvariable'))))
            button = next(widget for widget in widgets if isinstance(widget, auto.ttk.Button) and widget.cget('text') == 'Guardar y aplicar')
            with patch('auto.check_alldebrid', return_value=(True, 'Premium activo')):
                button.invoke()
                self.assertEqual(auto.ALLDEBRID_API_KEY, 'new-test-key')
                self.assertEqual(read_json(auto.CONNECTIONS_FILE, {})['ALLDEBRID_API_KEY'], 'new-test-key')
            self.assertFalse(auto.SHUTDOWN.is_set())
            gui.save_config()
            self.assertTrue(Path(auto.CONFIG_FILE).exists())
        finally:
            close_gui(gui)

    def test_small_windows_preserve_text_and_controls(self):
        gui = auto.DownloadGUI()
        try:
            gui.info_label.configure(text='Carpeta de descargas: C:\\' + 'una_carpeta_muy_larga_' * 15)
            with patch('auto.TELEGRAM_STATUS', 'Error: Revisa el acceso al grupo y la configuración de la conexión de Telegram'), \
                 patch('auto.ALLDEBRID_API_KEY', 'test'), \
                 patch('auto.ALLDEBRID_STATUS_MSG', 'La suscripción premium ha caducado; renueva tu cuenta para poder descargar enlaces premium'), \
                 patch('auto.ALLDEBRID_CONNECTED', False):
                gui.actualizar_estado_servicios()
                for geometry in ('440x320', '650x500', '1150x650'):
                    gui.root.geometry(geometry)
                    for _ in range(5):
                        gui.root.update()
                    for frame in (gui.service_row, gui.action_row, gui.summary_row):
                        for control in frame.controls:
                            self.assertLessEqual(control.winfo_x() + control.winfo_width(), frame.winfo_width())
                            self.assertLessEqual(control.winfo_y() + control.winfo_height(), frame.winfo_height())
                    self.assertLessEqual(gui.btn_options.winfo_rootx() + gui.btn_options.winfo_width(),
                                         gui.root.winfo_rootx() + gui.root.winfo_width())
                    self.assertGreaterEqual(gui.info_label.winfo_height(), gui.info_label.winfo_reqheight())
                    self.assertIn('renueva tu cuenta', gui.lbl_alldebrid.cget('text'))
                gui.root.geometry('440x320')
                gui.root.update()
                self.assertFalse(hasattr(gui, 'main_scroll'))
                for panel in (gui.top_frame, gui.bottom_frame, gui.tree_container):
                    self.assertLessEqual(panel.winfo_rooty() + panel.winfo_height(),
                                         gui.root.winfo_rooty() + gui.root.winfo_height())
                self.assertGreaterEqual(gui.tree.winfo_height(), 80)
                self.assertIsNotNone(gui.tree.cget('xscrollcommand'))
                self.assertGreaterEqual(gui.tree.column('estado', 'minwidth'), 85)

            gui.abrir_conexiones()
            window = gui.connections_window
            window.geometry('540x420')
            for _ in range(5):
                gui.root.update()
            notebook = next(widget for widget in window.winfo_children() if isinstance(widget, auto.ttk.Notebook))
            notebook.select(1)
            for _ in range(5):
                gui.root.update()
            tab = notebook.nametowidget(notebook.tabs()[1])
            self.assertNotIsInstance(tab, auto.ScrollableFrame)
            self.assertGreaterEqual(tab.winfo_height(), tab.winfo_reqheight())
            for row in tab.winfo_children():
                self.assertLessEqual(row.winfo_y() + row.winfo_height(), tab.winfo_height())
                for entry in row.winfo_children():
                    if isinstance(entry, auto.ttk.Entry):
                        self.assertGreater(entry.winfo_width(), 200)
            close = next(widget for widget in window.winfo_children()
                         if isinstance(widget, auto.ttk.Button) and widget.cget('text') == 'Cerrar')
            self.assertLessEqual(close.winfo_y() + close.winfo_height(), window.winfo_height())
            style = auto.ttk.Style(gui.root)
            self.assertEqual(style.lookup('TEntry', 'fieldbackground'), '#172233')
            self.assertEqual(style.lookup('TNotebook', 'background'), gui.bg_frame)
        finally:
            close_gui(gui)

    def test_download_values_visible_in_compact_and_wide_layout(self):
        item = auto.DownloadItem(42, 'archivo_largo.zip', status='Descargando', progress=37.5,
                                 source='alldebrid', total_bytes=8 * 1024**3, downloaded_bytes=3 * 1024**3)
        self.add(item)
        auto._inst_speeds[42] = 12 * 1024**2
        gui = auto.DownloadGUI()
        try:
            gui.root.geometry('440x520')
            gui.refresh()
            for _ in range(5):
                gui.root.update()
            gui.adapt_download_table()
            self.assertFalse(gui.compact_downloads)
            row = gui.tree_items[42]
            for column in gui.columns:
                box = gui.tree.bbox(row, column)
                self.assertTrue(box)
                self.assertLessEqual(box[0] + box[2], gui.tree.winfo_width())
            canvas = gui.row_canvases[42]
            text = '\n'.join(canvas.itemcget(shape, 'text') for shape in canvas.find_all()
                             if canvas.type(shape) == 'text')
            self.assertIn('37.5%', text)
            for shape in canvas.find_all():
                if canvas.type(shape) == 'text':
                    self.assertLessEqual(canvas.bbox(shape)[2], int(canvas.place_info()['width']))
            gui.root.geometry('1150x650')
            for _ in range(5):
                gui.root.update()
            gui.adapt_download_table()
            self.assertFalse(gui.compact_downloads)
            row = gui.tree_items[42]
            box = gui.tree.bbox(row, 'progreso')
            self.assertTrue(box)
            self.assertLessEqual(box[0] + box[2], gui.tree.winfo_width())
        finally:
            auto._inst_speeds.pop(42, None)
            close_gui(gui)

    @unittest.skipUnless(os.name == 'nt', 'Windows title bars')
    def test_native_dark_titlebar(self):
        import ctypes
        from ctypes import wintypes
        gui = auto.DownloadGUI()
        try:
            user32 = ctypes.WinDLL('user32')
            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
            user32.GetAncestor.restype = wintypes.HWND
            dwm = ctypes.WinDLL('dwmapi')
            dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            for restored in (False, True):
                if restored:
                    gui.root.withdraw()
                    gui.root.update()
                    gui.root.deiconify()
                gui.root.after(600, gui.root.quit)
                gui.root.mainloop()
                hwnd = user32.GetAncestor(gui.root.winfo_id(), 2)
                value = ctypes.c_uint()
                result = dwm.DwmGetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
                self.assertEqual(result, 0)
                self.assertEqual(value.value, 1)
                self.assertEqual(gui.root._dark_titlebar_results[35], 0)
                self.assertEqual(gui.root._dark_titlebar_results[36], 0)
        finally:
            close_gui(gui)


class GroupLinkTests(unittest.TestCase):
    def test_private_links_and_invalid_invites(self):
        self.assertEqual(auto.group_id_from_link('https://t.me/c/1234567890/12'), '-1001234567890')
        self.assertEqual(auto.group_id_from_link('t.me/c/1234567890/5/12?single'), '-1001234567890')
        for link in ('https://t.me/+invite', 'https://t.me/public_name/12', 'https://other.test/c/12/3'):
            with self.assertRaises(ValueError):
                auto.group_id_from_link(link)


if __name__ == '__main__':
    unittest.main(verbosity=2)
