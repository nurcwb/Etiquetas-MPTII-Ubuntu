#!/usr/bin/env python3
"""Editor local de etiquetas; Python 3 + Tkinter + Pillow + CUPS."""
import json
import tempfile
import math
import os
import sys
import queue
from urllib.parse import urlsplit, parse_qs
import struct
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

DOTS_MM = 8  # 203 dpi nominal
MAX_DOTS = 384
ASSET_DIR = Path(__file__).resolve().parent
FONT_DIR = ASSET_DIR / 'fonts' if (ASSET_DIR / 'fonts').exists() else Path('/usr/share/fonts/truetype/dejavu')


def number(value, label, low, high):
    try:
        result = float(str(value).replace(',', '.'))
    except ValueError:
        raise ValueError(f'{label}: informe um número.') from None
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f'{label}: use um valor entre {low} e {high}.')
    return result


def render_label(width, height, text, size, align='Centro', bold=False, gap=0, offset=0):
    width = number(width, 'Largura', 15, 58)
    height = number(height, 'Altura', 10, 300)
    size = number(size, 'Fonte (pt)', 6, 48)
    gap = number(gap, 'Espaço entre etiquetas', 0, 20)
    offset = number(offset, 'Ajuste vertical', -20, 20)
    if not text.strip():
        raise ValueError('Digite o conteúdo da etiqueta.')
    if len(text) > 10000:
        raise ValueError('Use até 10.000 caracteres por etiqueta.')
    # Papel de 58 mm geralmente tem cabeça de 48 mm (384 pontos).
    w, h = round(min(width * DOTS_MM, MAX_DOTS)), round(height * DOTS_MM)
    margin = 12
    font = ImageFont.truetype(str(FONT_DIR / ('DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf')),
                              round(size * 203 / 72))
    image = Image.new('L', (w, h + round(gap * DOTS_MM)), 255)
    draw = ImageDraw.Draw(image)
    lines = []
    for paragraph in text.replace('\t', '    ').split('\n'):
        line = ''
        for word in paragraph.split(' '):
            candidate = f'{line} {word}' if line else word
            if draw.textlength(candidate, font=font) <= w - 2 * margin:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ''
            # Quebra também palavras/códigos sem espaços.
            for char in word:
                if draw.textlength(line + char, font=font) > w - 2 * margin:
                    if not line:
                        raise ValueError('Fonte muito grande para essa largura.')
                    lines.append(line)
                    line = ''
                line += char
        lines.append(line)
    ascent, descent = font.getmetrics()
    step = ascent + descent + 3
    total = len(lines) * step
    if total > h - 2 * margin:
        raise ValueError('O texto não cabe. Reduza a fonte ou aumente a altura.')
    y = (h - total) // 2 + round(offset * DOTS_MM)
    if y < margin or y + total > h - margin:
        raise ValueError('O ajuste vertical desloca o texto para fora da etiqueta. Reduza o ajuste ou a fonte.')
    for line in lines:
        length = draw.textlength(line, font=font)
        x = margin if align == 'Esquerda' else ((w - length) / 2 if align == 'Centro' else w - margin - length)
        draw.text((x, y), line, font=font, fill=0, anchor='lt')
        y += step
    return image.point(lambda p: 255 if p >= 160 else 0, mode='1')


def escpos(image):
    """GS v 0 em faixas; bit 1 representa um ponto preto."""
    width_bytes = (image.width + 7) // 8
    padded = Image.new('1', (width_bytes * 8, image.height), 1)
    padded.paste(image, (0, 0))
    data = bytearray(b'\x1b@\x1ba\x00')
    for top in range(0, image.height, 128):
        band = padded.crop((0, top, padded.width, min(top + 128, image.height)))
        pixels = ImageOps.invert(band.convert('L')).convert('1').tobytes()
        data.extend(b'\x1dv0\x00' + struct.pack('<HH', width_bytes, band.height) + pixels)
    return bytes(data)


def paper_motion(distance):
    distance = number(distance, 'Avanço aproximado (mm)', 1, 50)
    # Mesmo caminho do teste USB que funcionou: inicializar + quebras de linha.
    # Entrelinha padrão nominal de 1/6 polegada; firmware pode variar.
    lines = max(1, round(distance / (25.4 / 6)))
    return b'\x1b@' + b'\n' * lines


def printer_status(printer):
    """CUPS informa a fila; sysfs confirma presença do dispositivo USB."""
    env = dict(os.environ, LC_ALL='C')
    def cups(*args):
        r = subprocess.run(['lpstat', *args, printer], capture_output=True,
                           text=True, timeout=4, env=env)
        if r.returncode:
            raise RuntimeError(r.stderr.strip() or 'Fila CUPS indisponível')
        return r.stdout
    try:
        if not printer or printer.startswith('-'):
            return 'warning', 'Informe uma fila CUPS válida.'
        uri = cups('-v').strip().split(': ', 1)[-1]
        state = cups('-p')
        acceptance = cups('-a')
        if not uri.startswith('usb://'):
            return 'warning', 'Fila disponível; conexão física não verificada (não USB).'
        serial = parse_qs(urlsplit(uri).query).get('serial', [None])[0]
        if not serial:
            return 'warning', 'Fila USB sem número de série; conexão não confirmada.'
        devices = Path('/sys/bus/usb/devices')
        if not devices.exists():
            return 'warning', 'Não foi possível consultar os dispositivos USB.'
        found = False
        unreadable = False
        for device in devices.iterdir():
            try:
                if (device / 'serial').read_text().strip() == serial:
                    found = True
                    break
            except FileNotFoundError:
                continue
            except OSError:
                unreadable = True
        if not found:
            if unreadable:
                return 'warning', 'Não foi possível confirmar a conexão USB.'
            return 'offline', 'Impressora desconectada do USB.'
        if 'disabled' in state or 'not accepting' in acceptance:
            return 'warning', 'USB conectado; fila pausada ou sem aceitar trabalhos.'
        return 'online', 'USB conectado · fila CUPS habilitada'
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        return 'warning', 'CUPS indisponível: ' + str(error)


def read_labels(filename):
    raw = Path(filename).read_bytes()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('cp1252')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError('O TXT não contém linhas com conteúdo.')
    if len(lines) > 1000:
        raise ValueError('Importe até 1.000 linhas por lote.')
    return lines


PROFILE_FIELDS = {
    'width': ('Largura', 15, 58), 'height': ('Altura', 10, 300),
    'gap': ('Espaço', 0, 20), 'offset': ('Ajuste vertical', -20, 20),
}


def validate_profile(values):
    return {key: number(values[key], label, low, high)
            for key, (label, low, high) in PROFILE_FIELDS.items()}


class ProfileStore:
    def __init__(self, path):
        self.path = Path(path)
        self.profiles = {}
        self.last = ''
        self.error = ''
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(data, dict) or data.get('version') != 1:
                    raise ValueError('Formato de perfis desconhecido.')
                for name, values in data['profiles'].items():
                    if not isinstance(name, str) or not name.strip() or len(name) > 80:
                        raise ValueError('Nome de perfil inválido.')
                    self.profiles[name] = validate_profile(values)
                self.last = data.get('last', '')
                if self.last not in self.profiles:
                    self.last = ''
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            self.profiles = {}
            self.last = ''
            self.error = f'Não foi possível ler perfis.json: {error}'

    def write(self, profiles, last):
        if self.error:
            raise ValueError(self.error + ' Corrija ou renomeie esse arquivo antes de salvar.')
        payload = json.dumps({'version': 1, 'profiles': profiles, 'last': last}, ensure_ascii=False, indent=2)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.perfis-', suffix='.tmp', delete=False) as file:
                temporary = Path(file.name)
                file.write(payload + '\n')
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        self.profiles = profiles
        self.last = last

    def save(self, name, values):
        name = name.strip()
        if not name or len(name) > 80:
            raise ValueError('Dê ao perfil um nome de 1 a 80 caracteres.')
        profile = validate_profile(values)
        self.write(dict(self.profiles, **{name: profile}), name)
        return name

    def select(self, name):
        if name not in self.profiles:
            raise ValueError('Selecione um perfil da lista.')
        self.write(dict(self.profiles), name)
        return self.profiles[name]

    def delete(self, name):
        if name not in self.profiles:
            raise ValueError('Selecione um perfil da lista para excluir.')
        remaining = dict(self.profiles)
        del remaining[name]
        self.write(remaining, '' if self.last == name else self.last)


class App:
    def __init__(self, root):
        from PIL import ImageTk
        self.ImageTk = ImageTk
        self.root = root
        self.timer = None
        self.image = None
        self.busy = False
        self.lines = []
        self.line_index = 0
        self.events = queue.Queue()
        self.checking_connection = False
        self.values = {}
        icon_path = ASSET_DIR / 'icone.png'
        if icon_path.exists():
            self.window_icon = tk.PhotoImage(file=str(icon_path))
            root.iconphoto(True, self.window_icon)
        root.title('Etiquetas · Estúdio de impressão MPT-II')
        root.configure(bg='#f2f5f3')
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f'{min(1280, sw - 60)}x{min(850, sh - 80)}')
        root.minsize(1060, 700)
        root.option_add('*Font', ('DejaVu Sans', 10))
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('TFrame', background='#ffffff')
        style.configure('TLabel', background='#ffffff', foreground='#203b3b', font=('DejaVu Sans', 10))
        style.configure('Muted.TLabel', foreground='#647975', font=('DejaVu Sans', 9))
        style.configure('Heading.TLabel', font=('DejaVu Sans', 12, 'bold'), foreground='#1f4140')
        style.configure('TEntry', fieldbackground='#f9fbfa', foreground='#203b3b', bordercolor='#d7e1dc', padding=7)
        style.configure('TCombobox', fieldbackground='#f9fbfa', background='#f0f5f2', foreground='#203b3b', padding=6, arrowsize=14)
        style.map('TCombobox', fieldbackground=[('readonly', '#f9fbfa')], foreground=[('readonly', '#203b3b')])
        style.configure('TButton', background='#eef4f0', foreground='#23554f', borderwidth=0, padding=(12, 9), font=('DejaVu Sans', 9))
        style.map('TButton', background=[('active', '#deebe3'), ('disabled', '#f3f5f4')], foreground=[('disabled', '#9aaba3')])
        style.configure('Primary.TButton', background='#126b60', foreground='#ffffff', padding=(22, 12), font=('DejaVu Sans', 11, 'bold'))
        style.map('Primary.TButton', background=[('active', '#0b554c'), ('disabled', '#b5cbc0')], foreground=[('disabled', '#f6faf7')])
        style.configure('TCheckbutton', background='#ffffff', foreground='#203b3b')
        style.map('TCheckbutton', background=[('active', '#ffffff')])
        outer = tk.Frame(root, bg='#f2f5f3', padx=22, pady=18)
        outer.pack(fill='both', expand=True)
        header = tk.Frame(outer, bg='#f2f5f3')
        header.pack(fill='x', pady=(0, 18))
        brand = tk.Frame(header, bg='#f2f5f3')
        brand.pack(side='left')
        tk.Label(brand, text='Etiquetas', bg='#f2f5f3', fg='#183f39', font=('DejaVu Sans', 26, 'bold')).pack(anchor='w')
        tk.Label(brand, text='Seu estúdio de impressão  /  MPT-II', bg='#f2f5f3', fg='#687d75', font=('DejaVu Sans', 10)).pack(anchor='w', pady=(3, 0))
        connection_box = tk.Frame(header, bg='#e4eee7', padx=16, pady=12)
        connection_box.pack(side='right', padx=(10, 0))
        self.connection = tk.StringVar(value='● Verificando impressora…')
        self.connection_label = tk.Label(connection_box, textvariable=self.connection, bg='#e4eee7', fg='#506c5c', font=('DejaVu Sans', 9, 'bold'), wraplength=330, justify='left')
        self.connection_label.pack(anchor='w')
        tk.Label(connection_box, text='Conexão USB e fila de impressão', bg='#e4eee7', fg='#6a7f71', font=('DejaVu Sans', 8)).pack(anchor='w', pady=(3, 0))
        # Barra inferior fixa: as ações continuam acessíveis ao redimensionar.
        bottom = tk.Frame(outer, bg='#f2f5f3')
        bottom.pack(side='bottom', fill='x', pady=(14, 0))
        toolbar = tk.Frame(bottom, bg='#ffffff', padx=14, pady=12, highlightthickness=1, highlightbackground='#e0e7e2')
        toolbar.pack(fill='x')
        def caption(parent, value):
            ttk.Label(parent, text=value, style='Muted.TLabel').pack(anchor='w', pady=(0, 4))
        feed = ttk.Frame(toolbar)
        feed.pack(side='left')
        caption(feed, 'Avanço aproximado (mm)')
        feed_row = ttk.Frame(feed)
        feed_row.pack()
        self.feed_distance = tk.StringVar(value='12')
        ttk.Entry(feed_row, textvariable=self.feed_distance, width=5).pack(side='left', padx=(0, 7))
        self.feed_button = ttk.Button(feed_row, text='Avançar papel', command=self.move_paper)
        self.feed_button.pack(side='left')
        self.print_button = ttk.Button(toolbar, text='Imprimir etiqueta', style='Primary.TButton', command=self.print_label)
        self.print_button.pack(side='right', padx=(14, 0), pady=(10, 0))
        copies = ttk.Frame(toolbar)
        copies.pack(side='right')
        caption(copies, 'Cópias por etiqueta')
        self.values['copies'] = tk.StringVar(value='1')
        ttk.Entry(copies, textvariable=self.values['copies'], width=6).pack(anchor='e')
        self.status = tk.StringVar()
        tk.Label(bottom, textvariable=self.status, bg='#f2f5f3', fg='#5f7569', anchor='w', justify='left', wraplength=990, font=('DejaVu Sans', 9)).pack(fill='x', pady=(8, 0))
        columns = tk.Frame(outer, bg='#f2f5f3')
        columns.pack(fill='both', expand=True)
        columns.columnconfigure(0, weight=0, minsize=300)
        columns.columnconfigure(1, weight=1, minsize=300)
        columns.columnconfigure(2, weight=1, minsize=330)
        columns.rowconfigure(0, weight=1)
        def panel(col, title):
            border = tk.Frame(columns, bg='#ffffff', highlightbackground='#e0e7e2', highlightthickness=1)
            border.grid(row=0, column=col, sticky='nsew', padx=(0, 14 if col < 2 else 0))
            if col == 0:
                viewport = tk.Canvas(border, bg='#ffffff', width=296, highlightthickness=0)
                viewport.pack(side='left', fill='both', expand=True)
                scrollbar = ttk.Scrollbar(border, orient='vertical', command=viewport.yview)
                viewport.configure(yscrollcommand=scrollbar.set)
                content = ttk.Frame(viewport, padding=16)
                window = viewport.create_window((0, 0), window=content, anchor='nw')
                def resize_sidebar(event=None):
                    viewport.itemconfigure(window, width=viewport.winfo_width())
                    viewport.configure(scrollregion=viewport.bbox('all'))
                    if content.winfo_reqheight() > viewport.winfo_height():
                        scrollbar.pack(side='right', fill='y')
                    else:
                        scrollbar.pack_forget()
                viewport.bind('<Configure>', resize_sidebar)
                content.bind('<Configure>', resize_sidebar)
                self.sidebar_canvas = viewport
                def wheel(event):
                    x, y = root.winfo_pointerxy()
                    if (viewport.winfo_rootx() <= x < viewport.winfo_rootx() + viewport.winfo_width()
                            and viewport.winfo_rooty() <= y < viewport.winfo_rooty() + viewport.winfo_height()):
                        direction = -1 if getattr(event, 'num', None) == 4 or getattr(event, 'delta', 0) > 0 else 1
                        viewport.yview_scroll(direction, 'units')
                for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                    root.bind_all(sequence, wheel)
            else:
                content = ttk.Frame(border, padding=16)
                content.pack(fill='both', expand=True)
            ttk.Label(content, text=title, style='Heading.TLabel').pack(anchor='w', pady=(0, 16))
            return content
        form = panel(0, '01  Configurar etiqueta')
        editor = panel(1, '02  Escrever conteúdo')
        preview = panel(2, '03  Conferir prévia')
        portable_dir = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ASSET_DIR.parent
        self.profiles = ProfileStore(portable_dir / 'perfis.json')
        caption(form, 'Tamanhos salvos / nome do perfil')
        self.profile_name = tk.StringVar()
        self.profile_combo = ttk.Combobox(form, textvariable=self.profile_name, values=sorted(self.profiles.profiles), width=25)
        self.profile_combo.pack(fill='x')
        self.profile_combo.bind('<<ComboboxSelected>>', self.select_profile)
        profile_actions = ttk.Frame(form)
        profile_actions.pack(fill='x', pady=(8, 0))
        ttk.Button(profile_actions, text='Salvar perfil', command=self.save_profile).pack(side='left')
        ttk.Button(profile_actions, text='Excluir', command=self.delete_profile).pack(side='right')
        self.profile_note = tk.StringVar(value=self.profiles.error or 'Digite um nome para guardar suas medidas.')
        ttk.Label(form, textvariable=self.profile_note, style='Muted.TLabel', wraplength=250).pack(anchor='w', pady=(8, 14))
        ttk.Separator(form).pack(fill='x', pady=(0, 14))
        fields = ttk.Frame(form)
        fields.pack(fill='x')
        definitions = [('width', 'Largura (mm)', '58'), ('height', 'Altura (mm)', '30'), ('gap', 'Espaço (mm)', '2'), ('offset', 'Ajuste vertical (mm)', '0')]
        for index, (key, label, default) in enumerate(definitions):
            row, col = divmod(index, 2)
            fields.columnconfigure(col, weight=1)
            cell = ttk.Frame(fields)
            cell.grid(row=row, column=col, sticky='ew', padx=(0 if col == 0 else 8, 0), pady=(0, 12))
            caption(cell, label)
            var = tk.StringVar(value=default)
            self.values[key] = var
            ttk.Entry(cell, textvariable=var, width=11).pack(fill='x')
            var.trace_add('write', self.schedule)
        ttk.Label(form, text='+ desce o texto · − sobe o texto', style='Muted.TLabel').pack(anchor='w')
        self.pitch_info = tk.StringVar()
        ttk.Label(form, textvariable=self.pitch_info, wraplength=250).pack(anchor='w', pady=(8, 14))
        ttk.Separator(form).pack(fill='x', pady=(0, 14))
        caption(form, 'Fila de impressão')
        self.printer = tk.StringVar(value='MPTII')
        ttk.Entry(form, textvariable=self.printer).pack(fill='x')
        self.printer.trace_add('write', lambda *args: self.connection.set('● Aguardando verificação da fila…'))
        ttk.Label(form, text='Posicionamento calculado. Alinhe a primeira etiqueta antes de imprimir o lote.', style='Muted.TLabel', wraplength=250).pack(anchor='w', pady=(12, 0))
        imports = ttk.Frame(editor)
        imports.pack(fill='x')
        ttk.Button(imports, text='Importar TXT…', command=self.import_txt).pack(side='left')
        ttk.Button(imports, text='Texto manual', command=self.manual).pack(side='right')
        ttk.Label(editor, text='No TXT, cada linha vira uma etiqueta.', style='Muted.TLabel').pack(anchor='w', pady=(8, 12))
        self.text = tk.Text(editor, height=7, width=24, wrap='word', font=('DejaVu Sans', 12), bg='#f8fbf9', fg='#203b3b', insertbackground='#126b60', relief='flat', highlightthickness=1, highlightbackground='#d7e1dc', highlightcolor='#126b60', padx=14, pady=14, undo=True)
        self.text.pack(fill='both', expand=True)
        self.text.insert('1.0', 'PRODUTO ARTESANAL\nCafé especial · 250 g\nR$ 25,00')
        self.text.bind('<<Modified>>', self.modified)
        formatting = ttk.Frame(editor)
        formatting.pack(fill='x', pady=(14, 0))
        size_box = ttk.Frame(formatting)
        size_box.pack(side='left', padx=(0, 10))
        caption(size_box, 'Fonte (pt)')
        self.values['size'] = tk.StringVar(value='12')
        self.values['size'].trace_add('write', self.schedule)
        ttk.Entry(size_box, textvariable=self.values['size'], width=5).pack()
        align_box = ttk.Frame(formatting)
        align_box.pack(side='left', fill='x', expand=True)
        caption(align_box, 'Alinhamento')
        self.align = tk.StringVar(value='Centro')
        ttk.Combobox(align_box, textvariable=self.align, values=['Esquerda', 'Centro', 'Direita'], state='readonly', width=11).pack(fill='x')
        self.align.trace_add('write', self.schedule)
        self.bold = tk.BooleanVar(value=False)
        ttk.Checkbutton(editor, text='Negrito', variable=self.bold, command=self.schedule).pack(anchor='w', pady=8)
        ttk.Separator(editor).pack(fill='x', pady=(0, 10))
        self.batch_info = tk.StringVar(value='Modo manual · uma etiqueta')
        ttk.Label(editor, textvariable=self.batch_info, style='Muted.TLabel', wraplength=280).pack(anchor='w')
        navigation = ttk.Frame(editor)
        navigation.pack(fill='x', pady=(8, 0))
        self.previous_button = ttk.Button(navigation, text='← Anterior', command=lambda: self.navigate(-1), state='disabled')
        self.previous_button.pack(side='left')
        self.next_button = ttk.Button(navigation, text='Próxima →', command=lambda: self.navigate(1), state='disabled')
        self.next_button.pack(side='right')
        self.preview_info = tk.StringVar(value='Área imprimível · 48 mm')
        ttk.Label(preview, textvariable=self.preview_info, style='Muted.TLabel', wraplength=300).pack(anchor='w', pady=(0, 12))
        self.canvas = tk.Canvas(preview, bg='#e9efeb', highlightthickness=0, width=300, height=240)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', self.schedule)
        ttk.Label(preview, text='A linha verde marca o intervalo e não é impressa. Em papel de 58 mm, a área imprimível é de até 48 mm.', style='Muted.TLabel', wraplength=300).pack(anchor='w', pady=(12, 10))
        ttk.Button(preview, text='Salvar prévia PNG', command=self.save).pack(fill='x')
        if self.profiles.last:
            self.profile_name.set(self.profiles.last)
            self.apply_profile(self.profiles.profiles[self.profiles.last])
            self.profile_note.set('Último perfil restaurado. Salve após alterar as medidas.')
        root.bind('<Control-o>', lambda event: self.import_txt())
        root.bind('<Control-s>', lambda event: self.save_profile())
        root.bind('<Control-Return>', lambda event: self.print_label())
        self.schedule()
        self.root.after(100, self.poll_events)
        self.root.after(200, self.check_connection)

    def apply_profile(self, values):
        for key, value in values.items():
            self.values[key].set(f'{value:g}')

    def save_profile(self):
        try:
            name = self.profiles.save(self.profile_name.get(),
                                      {key: self.values[key].get() for key in PROFILE_FIELDS})
            self.profile_name.set(name)
            self.profile_combo.configure(values=sorted(self.profiles.profiles))
            self.profile_note.set('Perfil salvo. Será restaurado na próxima abertura.')
        except (OSError, ValueError) as error:
            messagebox.showerror('Não foi possível salvar o perfil', str(error))

    def select_profile(self, event=None):
        name = self.profile_name.get()
        if name not in self.profiles.profiles:
            return
        # Aplica as medidas mesmo se a pasta estiver sem permissão de escrita.
        self.apply_profile(self.profiles.profiles[name])
        try:
            self.profiles.select(name)
            self.profile_note.set('Perfil carregado. Salve após alterar as medidas.')
        except (OSError, ValueError) as error:
            self.profile_note.set('Perfil carregado; não foi possível lembrar a seleção: ' + str(error))

    def delete_profile(self):
        try:
            self.profiles.delete(self.profile_name.get())
            self.profile_combo.configure(values=sorted(self.profiles.profiles))
            self.profile_name.set('')
            self.profile_note.set('Perfil excluído; medidas atuais mantidas.')
        except (OSError, ValueError) as error:
            messagebox.showerror('Não foi possível excluir o perfil', str(error))

    def import_txt(self):
        filename = filedialog.askopenfilename(filetypes=[('Texto', '*.txt'), ('Todos os arquivos', '*')])
        if not filename:
            return
        try:
            lines = read_labels(filename)
        except (OSError, UnicodeError, ValueError) as error:
            messagebox.showerror('Não foi possível abrir o TXT', str(error))
            return
        self.lines = lines
        self.line_index = 0
        self.show_line()

    def show_line(self):
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', self.lines[self.line_index])
        self.text.configure(state='disabled')
        self.batch_info.set(f'TXT: etiqueta {self.line_index + 1} de {len(self.lines)} · linhas vazias ignoradas')
        self.print_button.configure(text=f'Imprimir lote ({len(self.lines)})')
        self.previous_button.state(['!disabled'])
        self.next_button.state(['!disabled'])
        self.schedule()

    def navigate(self, delta):
        if self.lines:
            self.line_index = (self.line_index + delta) % len(self.lines)
            self.show_line()

    def manual(self):
        self.lines = []
        self.text.configure(state='normal')
        self.batch_info.set('Modo manual · uma etiqueta')
        self.previous_button.state(['disabled'])
        self.next_button.state(['disabled'])
        self.print_button.configure(text='Imprimir etiqueta')
        self.schedule()

    def check_connection(self):
        if not self.checking_connection:
            self.checking_connection = True
            printer = self.printer.get().strip()
            def worker():
                self.events.put(('connection', printer, printer_status(printer)))
            threading.Thread(target=worker, daemon=True).start()
        self.root.after(4000, self.check_connection)

    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'sent':
                    self.finished(event[1])
                elif event[1] == self.printer.get().strip():
                    level, message = event[2]
                    colors = {'online': '#167044', 'offline': '#b42318', 'warning': '#956000'}
                    self.connection.set('● ' + message)
                    self.connection_label.configure(foreground=colors[level])
                if event[0] == 'connection':
                    self.checking_connection = False
        except queue.Empty:
            pass
        self.root.after(100, self.poll_events)

    def modified(self, event=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.schedule()

    def schedule(self, *args):
        if self.timer:
            self.root.after_cancel(self.timer)
        self.timer = self.root.after(160, self.refresh)

    def render(self):
        return render_label(self.values['width'].get(), self.values['height'].get(),
                            self.text.get('1.0', 'end-1c'), self.values['size'].get(), self.align.get(), self.bold.get(),
                            self.values['gap'].get(), self.values['offset'].get())

    def refresh(self):
        self.timer = None
        self.canvas.delete('all')
        try:
            self.image = self.render()
            self.pitch_info.set(f'Avanço: {self.image.height / DOTS_MM:g} mm por etiqueta')
            self.preview_info.set(f'{self.values["width"].get()} × {self.values["height"].get()} mm · intervalo {self.values["gap"].get()} mm')
            image = self.image.convert('RGB')
            image.thumbnail((max(20, self.canvas.winfo_width() - 32), max(20, self.canvas.winfo_height() - 24)))
            self.photo = self.ImageTk.PhotoImage(image)
            cx, cy = self.canvas.winfo_width() // 2, self.canvas.winfo_height() // 2
            left, top = cx - image.width / 2, cy - image.height / 2
            self.canvas.create_rectangle(left + 4, top + 5, left + image.width + 4, top + image.height + 5, fill='#cedbd1', outline='')
            self.canvas.create_image(cx, cy, image=self.photo)
            gap = number(self.values['gap'].get(), 'Espaço', 0, 20)
            height = number(self.values['height'].get(), 'Altura', 10, 300)
            if gap > 0:
                top = cy - image.height / 2
                boundary = top + image.height * round(height * DOTS_MM) / self.image.height
                self.canvas.create_line(cx - image.width / 2, boundary, cx + image.width / 2,
                                        boundary, fill='#126b60', dash=(4, 3))
            if not self.busy:
                self.status.set(f'Avanço por etiqueta: {float(self.values["height"].get().replace(",", ".")) + float(self.values["gap"].get().replace(",", ".")):g} mm. Confira primeiro uma cópia.')
        except (ValueError, OSError) as error:
            self.image = None
            self.pitch_info.set('Confira as medidas')
            self.status.set(str(error))
            self.canvas.create_text(self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2, text=str(error), width=max(100, self.canvas.winfo_width() - 36), fill='#8d5344', font=('DejaVu Sans', 10), justify='center')

    def save(self):
        try:
            image = self.render()
            filename = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('Imagem PNG', '*.png')], initialfile='etiqueta.png')
            if filename:
                image.save(filename, dpi=(203, 203))
                self.status.set('Prévia salva.')
        except (ValueError, OSError) as error:
            messagebox.showerror('Não foi possível salvar', str(error))

    def print_label(self):
        if self.busy:
            return
        try:
            image = self.render()
            copies = number(self.values['copies'].get(), 'Cópias', 1, 50)
            if copies != int(copies):
                raise ValueError('Cópias: informe um número inteiro.')
            printer = self.printer.get().strip()
            if not printer or printer.startswith('-'):
                raise ValueError('Informe o nome da fila CUPS, por exemplo MPTII.')
            if self.lines and len(self.lines) * int(copies) > 1000:
                raise ValueError('O lote deve ter no máximo 1.000 etiquetas, incluindo cópias.')
            if self.lines:
                parts = []
                for index, line in enumerate(self.lines, 1):
                    try:
                        label = render_label(self.values['width'].get(), self.values['height'].get(),
                                             line, self.values['size'].get(), self.align.get(), self.bold.get(),
                                             self.values['gap'].get(), self.values['offset'].get())
                        parts.append(escpos(label) * int(copies))
                    except ValueError as error:
                        raise ValueError(f'Linha {index}: {error}') from None
                payload = b''.join(parts)
            else:
                payload = escpos(image) * int(copies)
        except (ValueError, OSError) as error:
            messagebox.showerror('Confira a etiqueta', str(error))
            return
        self.busy = True
        self.print_button.state(['disabled'])
        self.feed_button.state(['disabled'])
        self.status.set('Enviando para o CUPS…')
        threading.Thread(target=self.send, args=(printer, payload), daemon=True).start()

    def move_paper(self):
        if self.busy:
            return
        try:
            printer = self.printer.get().strip()
            if not printer or printer.startswith('-'):
                raise ValueError('Informe uma fila CUPS válida.')
            payload = paper_motion(self.feed_distance.get())
        except ValueError as error:
            messagebox.showerror('Confira o movimento do papel', str(error))
            return
        self.busy = True
        self.print_button.state(['disabled'])
        self.feed_button.state(['disabled'])
        self.status.set('Enviando comando de movimento ao CUPS…')
        threading.Thread(target=self.send, args=(printer, payload), daemon=True).start()

    def send(self, printer, payload):
        try:
            result = subprocess.run(['lp', '-d', printer, '-o', 'raw', '-t', 'Etiqueta MPT-II'], input=payload, capture_output=True, timeout=30)
            if result.returncode:
                raise RuntimeError(result.stderr.decode(errors='replace').strip() or 'Falha no CUPS.')
            message = 'Enviada ao CUPS: ' + result.stdout.decode(errors='replace').strip()
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            message = 'Falha ao enviar: ' + str(error)
        self.events.put(('sent', message))

    def finished(self, message):
        self.busy = False
        self.print_button.state(['!disabled'])
        self.feed_button.state(['!disabled'])
        self.status.set(message)


def install_kde():
    folder = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else ASSET_DIR
    executable = folder / 'Etiquetas-MPTII'
    if not executable.exists():
        raise RuntimeError('Execute o instalador na pasta da versão portátil.')
    def desktop_quote(value):
        value = str(value).replace('%', '%%')
        for char in ('\\', '"', '`', '$'):
            value = value.replace(char, '\\' + char)
        return '"' + value + '"'
    data_home = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    apps = data_home / 'applications'
    apps.mkdir(parents=True, exist_ok=True)
    destination = apps / 'etiquetas-mptii.desktop'
    destination.write_text(
        '[Desktop Entry]\nVersion=1.0\nType=Application\n'
        'Name=Etiquetas MPT-II\nComment=Configure e imprima etiquetas térmicas\n'
        f'Exec={desktop_quote(executable)}\nIcon={folder / "icone.png"}\n'
        'Terminal=false\nCategories=Office;\nKeywords=etiqueta;impressora;MPTII;\n'
        'StartupNotify=false\n', encoding='utf-8')
    import shutil
    for command in ('update-desktop-database', 'kbuildsycoca6', 'kbuildsycoca5'):
        if shutil.which(command):
            args = [command, str(apps)] if command == 'update-desktop-database' else [command, '--noincremental']
            subprocess.run(args, capture_output=True, timeout=30, check=False)
            if command.startswith('kbuildsycoca'):
                break
    print(f'Entrada criada: {destination}\nProcure por Etiquetas MPT-II no menu do KDE.')


if __name__ == '__main__':
    if '--install-kde' in sys.argv:
        install_kde()
    elif '--self-test' in sys.argv:
        assert render_label(58, 30, 'Café · teste', 12).size == (384, 240)
        assert escpos(render_label(58, 30, 'Teste', 12)).startswith(b'\x1b@')
        from PIL import ImageTk
        print('Runtime, fontes, Tk e renderização OK.')
    elif '--smoke-ui' in sys.argv:
        root = tk.Tk()
        root.withdraw()
        app = App(root)
        root.update()
        app.refresh()
        assert app.image is not None
        root.destroy()
        print('Janela e prévia OK.')
    else:
        root = tk.Tk()
        App(root)
        root.mainloop()

