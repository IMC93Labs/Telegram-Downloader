"""Beginner connection guide shown inside the application."""
import tkinter as tk
from tkinter import ttk
import webbrowser
import re
from ui_support import install_dark_titlebar

SECTIONS = {
    "Telegram": """CONFIGURAR TELEGRAM DESDE CERO

1. Crea el bot
Abre Telegram y busca @BotFather (oficial). Envía /newbot, elige un nombre y un usuario terminado en bot. Copia el TOKEN completo que te entrega, con el formato 123456789:AA... No copies solo el número: ese es el ID del bot y no sirve como token.
Si ya tienes un bot: /mybots → selecciona tu bot → API Token. No necesitas crear otro.

2. Crea o elige el grupo
Puedes usar un grupo que ya tengas. En sus miembros, añade el bot por su @usuario y hazlo administrador para que reciba los enlaces normales. Comprueba que puede enviar mensajes. En un canal, añádelo como administrador con permiso para publicar.

3. Obtén API ID y API Hash
Abre my.telegram.org/apps e inicia sesión con tu número de teléfono y el código recibido en Telegram. Si ya creaste una aplicación, consulta sus datos; si no, completa el formulario para crearla (nombre y nombre corto; plataforma Desktop). Copia api_id y api_hash.
Esta aplicación necesita ambos también si conectas mediante un bot. No son el ID ni el token del bot.

4. Obtén el ID del grupo
En Telegram, pulsa con el botón derecho sobre un mensaje del grupo y copia su enlace. En nuestros ajustes, pulsa Obtener ID desde enlace y pégalo.
Funciona con enlaces de mensaje privados t.me/c/...; los enlaces de invitación t.me/+... y los nombres públicos no contienen el ID numérico. Si tu grupo no ofrece un enlace compatible, consulta el ID en la configuración de la aplicación que ya lo utiliza. Recordar ID guardado recupera el último configurado en este PC.

5. Introduce los datos
Opciones → Conexiones → Telegram:
• API ID: api_id de my.telegram.org.
• API Hash: api_hash de my.telegram.org.
• Token del bot: token completo de BotFather.
• Teléfono: déjalo vacío cuando uses el bot.
• ID grupo: ID del grupo o canal, no del bot.
Pulsa Guardar y reconectar Telegram. La aplicación se reinicia; guarda después de terminar tus descargas activas.

6. Comprueba la conexión
Mantén la aplicación abierta en el PC y envía tú un enlace nuevo al grupo. Debe aparecer en la cola. Si no aparece, revisa el ID, que el bot esté añadido como administrador y que Telegram indique conexión activa.

ALTERNATIVA: TU CUENTA PERSONAL
No es obligatorio crear un bot. Introduce API ID, API Hash, teléfono con prefijo internacional y el ID del grupo; deja Token del bot vacío. Tu cuenta debe pertenecer al grupo. Al conectar se solicitará el código de Telegram y, si la tienes activada, la contraseña de verificación en dos pasos.
""",
    "AllDebrid": """CONFIGURAR ALLDEBRID (OPCIONAL)

1. Crea una cuenta o inicia sesión en alldebrid.com. Para enlaces premium necesitas una suscripción o prueba activa.

2. Abre alldebrid.com/apikeys/. Crea una clave con un nombre reconocible, por ejemplo Telegram Downloader, y cópiala completa.

3. En Opciones → Conexiones → AllDebrid, pega la clave. Puedes usar botón derecho → Pegar.

4. Pulsa Comprobar clave y después Guardar y aplicar. Guardar también comprueba la conexión. Si AllDebrid te envía un correo para autorizar la conexión, sigue sus indicaciones y vuelve a comprobarla.

5. Debe indicar Premium activo. La nueva clave se usa en las siguientes descargas sin reiniciar. Envía un enlace compatible al grupo para probar.

Si indica suscripción caducada, renueva la cuenta en AllDebrid: cambiar la clave no renueva premium. Para desactivar AllDebrid, deja la clave vacía y guarda.
""",
    "qBittorrent": """CONFIGURAR QBITTORRENT (OPCIONAL)

1. Instala y abre qBittorrent
Descárgalo desde el botón inferior e instálalo en el PC. Déjalo abierto para recibir los torrents.

2. Activa su interfaz web
En qBittorrent: Herramientas → Opciones → Interfaz web (Web UI). Actívala, configura un puerto (por ejemplo 8080) y un usuario y contraseña propios. Aplica los cambios.

3. Comprueba el acceso
Abre http://localhost:8080 en el navegador e inicia sesión con ese usuario y contraseña. Si cambiaste el puerto o activaste HTTPS, utiliza la dirección correspondiente.

4. Configura esta aplicación
Opciones → Conexiones → qBittorrent. Marca Enviar torrents a qBittorrent. Introduce la dirección Web UI, el usuario y la contraseña. Puedes pegar con botón derecho. Pulsa Comprobar conexión y después Guardar y aplicar.

5. Envía un torrent de prueba
Comprueba que indica Conectado y envía un enlace magnet o un archivo .torrent al grupo de Telegram. La aplicación lo enviará a qBittorrent.

Enviado a qBittorrent significa que se ha entregado el torrent: su progreso real se consulta dentro de qBittorrent. Los cambios de conexión se aplican a los siguientes torrents sin reiniciar.
""",
    "Datos y ayuda": """DÓNDE SE GUARDAN LOS DATOS

Las conexiones, ajustes, historial y sesiones de Telegram se guardan en este PC, en %LOCALAPPDATA%\TelegramDownloader. Las claves guardadas no están cifradas; protege tu cuenta de Windows y no compartas esta carpeta.

Para compartir la aplicación, entrega solo el instalador o el ejecutable generado. No compartas la carpeta del código fuente con sus archivos .env o .session, ni la carpeta de datos.

RECUPERAR UNA CONEXIÓN EXISTENTE
En las pestañas de conexiones, Mostrar credenciales permite consultar lo que este PC tiene guardado. API ID/Hash se consultan con la cuenta que los creó en my.telegram.org/apps. El token de un bot se gestiona desde la cuenta propietaria en BotFather. Tener acceso al grupo no da acceso a esas credenciales.

SI NO FUNCIONA
• Telegram desconectado: revisa API ID/Hash, token o teléfono y el código de acceso.
• No entran enlaces: revisa el grupo configurado, la pertenencia del bot y sus permisos.
• AllDebrid no conecta: comprueba clave, suscripción y autorización por correo.
• Torrent no enviado: comprueba que qBittorrent está abierto y que la interfaz web acepta tus credenciales.
• Revisa Opciones → registros cuando haya un error y no compartas tokens al pedir ayuda.
"""
}

def guide_steps(content):
    steps = []
    for paragraph in content.strip().split('\n\n'):
        lines = paragraph.splitlines()
        heading = lines[0]
        is_heading = re.match(r'^\d+\. ', heading) or re.fullmatch(r'[A-ZÁÉÍÓÚÑ /():]+', heading)
        if is_heading:
            steps.append([heading, '\n'.join(lines[1:])])
        elif steps:
            steps[-1][1] += '\n\n' + paragraph
        else:
            steps.append(['Antes de empezar', paragraph])
    return [step for step in steps if step[1].strip()]


def show_connection_help(gui, data_dir):
    previous = getattr(gui, 'connection_help_window', None)
    if previous is not None and previous.winfo_exists():
        previous.lift()
        return previous
    win = tk.Toplevel(gui.root)
    gui.connection_help_window = win
    win.title('Guía de configuración — paso a paso')
    win.configure(bg=gui.bg_root)
    win.transient(gui.root)
    install_dark_titlebar(win, gui.bg_root, gui.fg_text)
    win.minsize(560, 440)
    width, height = 760, 580
    win.geometry(f'{width}x{height}+{max(0, gui.root.winfo_rootx() + (gui.root.winfo_width()-width)//2)}+{max(0, gui.root.winfo_rooty() + (gui.root.winfo_height()-height)//2)}')
    footer = ttk.Frame(win, padding=10)
    footer.pack(side='bottom', fill='x')
    ttk.Button(footer, text='Cerrar', command=win.destroy).pack(side='right')
    import os
    ttk.Button(footer, text='Abrir carpeta de datos', command=lambda: os.startfile(str(data_dir))).pack(side='left')
    ttk.Label(win, text='Configura tu gestor, un paso cada vez', style='Header.TLabel').pack(anchor='w', padx=18, pady=(14, 4))
    ttk.Label(win, text='Telegram conecta el grupo. AllDebrid y qBittorrent son opcionales.', style='Info.TLabel').pack(anchor='w', padx=18)
    ttk.Style(win).configure('Horizontal.TProgressbar', troughcolor=gui.bg_card, background=gui.accent, bordercolor=gui.bg_card, lightcolor=gui.accent, darkcolor=gui.accent)
    notebook = ttk.Notebook(win)
    notebook.pack(fill='both', expand=True, padx=12, pady=12)
    links = {'Telegram': [('Abrir BotFather', 'https://t.me/BotFather'), ('Obtener API ID / Hash', 'https://my.telegram.org/apps')],
             'AllDebrid': [('Obtener clave AllDebrid', 'https://alldebrid.com/apikeys/')],
             'qBittorrent': [('Descargar qBittorrent', 'https://www.qbittorrent.org/download')],
             'Datos y ayuda': []}
    def make_panel(title, content):
        panel = ttk.Frame(notebook, padding=12)
        notebook.add(panel, text=title)
        steps = guide_steps(content)
        position = [0]
        counter = ttk.Label(panel, style='Info.TLabel', foreground='#8bc6ff', font=('Segoe UI', 10, 'bold'))
        counter.pack(anchor='w')
        progress = ttk.Progressbar(panel, maximum=len(steps))
        progress.pack(fill='x', pady=(6, 12))
        heading = ttk.Label(panel, style='Header.TLabel', wraplength=650, justify='left')
        heading.pack(fill='x', pady=(0, 10))
        bar = ttk.Frame(panel)
        bar.pack(side='bottom', fill='x', pady=(8, 0))
        link_bar = ttk.Frame(panel)
        link_bar.pack(side='bottom', fill='x', pady=(8, 0))
        body_frame = ttk.Frame(panel)
        body_frame.pack(fill='both', expand=True)
        text = tk.Text(body_frame, wrap='word', font=('Segoe UI', 11), bg=gui.bg_card, fg=gui.fg_text,
                       padx=16, pady=14, relief='flat', borderwidth=0, highlightthickness=0, spacing1=3, spacing3=8)
        scroll = ttk.Scrollbar(body_frame, orient='vertical', command=text.yview)
        scroll.pack(side='right', fill='y')
        text.pack(fill='both', expand=True)
        text.configure(yscrollcommand=scroll.set)
        previous = ttk.Button(bar, text='← Anterior', command=lambda: move(-1))
        previous.pack(side='left')
        following = ttk.Button(bar, text='Siguiente →', command=lambda: move(1))
        following.pack(side='right')
        for label, url in links[title]:
            ttk.Button(link_bar, text=label, command=lambda url=url: webbrowser.open(url)).pack(side='left', padx=(0, 6))
        def move(delta):
            position[0] = max(0, min(len(steps)-1, position[0] + delta))
            index = position[0]
            counter.configure(text=f'{title.upper()}  ·  PASO {index+1} DE {len(steps)}')
            progress.configure(value=index+1)
            heading.configure(text=steps[index][0])
            text.configure(state='normal')
            text.delete('1.0', 'end')
            text.insert('1.0', steps[index][1].strip())
            text.configure(state='disabled')
            text.yview_moveto(0)
            previous.configure(state='disabled' if index == 0 else 'normal')
            following.configure(state='disabled' if index == len(steps)-1 else 'normal')
        panel.bind('<Configure>', lambda event: heading.configure(wraplength=max(160, event.width-24)))
        move(0)
    for title, content in SECTIONS.items():
        make_panel(title, content)
    return win
