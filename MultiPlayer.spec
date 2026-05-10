# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

# Cartella del progetto (quella dove si trova questo .spec)
project_dir = os.path.abspath(os.path.dirname(SPEC) if '__file__' not in globals() else os.path.dirname(__file__))

block_cipher = None

# Tutti i moduli locali del progetto, elencati esplicitamente
local_modules = [
    'grid_manager',
    'mainapp',
    'mp3file',
    'mp3widget',
    'project_manager',
    'waveform',
    'waveform_service',
]

# Se i file stanno dentro un pacchetto (cartella con __init__.py),
# aggiungi anche le versioni con il nome del pacchetto come prefisso.
# Esempio: se il pacchetto si chiama "multiplayer", scommenta e adatta:
# package_name = 'multiplayer'
# local_modules += [f'{package_name}.{m}' for m in local_modules]
# local_modules += [package_name]

# Librerie tipicamente usate per audio + GUI con waveform:
# scegli quelle effettivamente importate dal tuo progetto
extra_hidden = []
# extra_hidden += collect_submodules('PyQt5')      # se usi PyQt5
# extra_hidden += collect_submodules('PySide6')    # se usi PySide6
# extra_hidden += collect_submodules('pydub')      # se usi pydub
# extra_hidden += collect_submodules('mutagen')    # tag MP3
# extra_hidden += collect_submodules('numpy')      # waveform
# extra_hidden += collect_submodules('matplotlib') # se plotti la waveform

a = Analysis(
    ['MultiPlayer.py'],
    pathex=[project_dir],
    binaries=[],
    datas=[
        # Aggiungi qui eventuali risorse non-Python:
        # ('assets', 'assets'),
        # ('config.json', '.'),
        # ('icons/*.png', 'icons'),
    ],
    hiddenimports=local_modules + extra_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MultiPlayer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # metti True se vuoi vedere i print/log su terminale
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',      # decommenta se hai un'icona
)