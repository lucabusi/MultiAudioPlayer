# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

# Cartella del progetto (quella dove si trova questo .spec)
project_dir = os.path.abspath(os.path.dirname(SPEC) if '__file__' not in globals() else os.path.dirname(__file__))

block_cipher = None

# Version resource dell'exe (Proprietà > Dettagli) generata da APP_VERSION:
# niente più version_info.txt da allineare a mano a ogni bump.
import sys
from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
    VarFileInfo, VarStruct)
sys.path.insert(0, os.path.join(project_dir, 'MultiPlayer'))
from constants import APP_VERSION

_ver = tuple(int(x) for x in APP_VERSION.split('.')) + (0,) * (4 - len(APP_VERSION.split('.')))
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=_ver, prodvers=_ver, mask=0x3f, flags=0x0,
                      OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable('040904B0', [
            StringStruct('CompanyName', 'Luca Busi'),
            StringStruct('FileDescription', 'MultiPlayer Audio Player'),
            StringStruct('FileVersion', APP_VERSION),
            StringStruct('InternalName', 'MultiPlayer'),
            StringStruct('LegalCopyright', 'Copyright © 2026 Luca Busi'),
            StringStruct('OriginalFilename', 'MultiPlayer.exe'),
            StringStruct('ProductName', 'MultiPlayer'),
            StringStruct('ProductVersion', APP_VERSION),
        ])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])]),
    ])

# Tutti i moduli locali del progetto, elencati esplicitamente
local_modules = [
    'audio_warmup',
    'constants',
    'grid_manager',
    'mainapp',
    'mp3file',
    'mp3widget',
    'project_manager',
    'thread_registry',
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
extra_hidden = ['PySide6.QtMultimedia']  # import lazy nel backend 'qt' (mp3file._QtBackend) e in audio_warmup
# extra_hidden += collect_submodules('PySide6')    # NON serve: gli hook PyInstaller di PySide6 raccolgono i moduli importati
# extra_hidden += collect_submodules('pydub')      # se usi pydub
# extra_hidden += collect_submodules('mutagen')    # tag MP3
# extra_hidden += collect_submodules('numpy')      # waveform
# extra_hidden += collect_submodules('matplotlib') # se plotti la waveform

# Moduli che PyInstaller trova solo per import opzionali/lazy di terze parti
# (numpy.testing, numpy.f2py, plugin PIL, librosa/scipy se installati nel
# Python di build) e che l'app non usa mai a runtime.
# tests/test_regressions.py legge QUESTA lista, la blocca e verifica che l'app
# funzioni lo stesso: se aggiungi qui un modulo necessario, il test va rosso.
EXCLUDED_MODULES = [
    'matplotlib', 'pandas', 'scipy', 'librosa',
    'numpy.testing', 'numpy.f2py', 'yaml', 'psutil', 'charset_normalizer', 'win32pdh',
    'unittest', 'doctest', 'pdb', 'pydoc', 'xmlrpc', 'http', 'ftplib', 'urllib.request',
    'ssl', '_ssl', '_hashlib',
    'PIL.ImageTk', 'PIL._imagingtk', 'PIL.AvifImagePlugin', 'PIL._avif',
    'PIL.WebPImagePlugin', 'PIL._webp', 'PIL.ImageCms', 'PIL._imagingcms',
]

# DLL e plugin Qt che gli hook di PySide6 raccolgono ma l'app non carica:
# niente QML/Quick/PDF/SVG/OpenGL, nessuna traduzione Qt, solo il plugin di
# piattaforma qwindows, il backend multimediale FFmpeg e il plugin JPEG
# (waveform caricata con QPixmap.loadFromData).
QT_UNUSED_DLL = ('opengl32sw', 'Qt6Quick', 'Qt6Qml', 'Qt6Pdf', 'Qt6VirtualKeyboard',
                 'Qt6Svg', 'Qt6OpenGL', 'Qt6MultimediaWidgets')
QT_PLUGINS_USED = ('platforms/qwindows', 'styles/', 'multimedia/ffmpegmediaplugin',
                   'imageformats/qjpeg')


def _qt_unused(dest):
    d = dest.replace(os.sep, '/')
    if not d.startswith('PySide6/'):
        return False
    if '/plugins/' in d:
        return not any(p in d for p in QT_PLUGINS_USED)
    return '/translations/' in d or os.path.basename(d).startswith(QT_UNUSED_DLL)


a = Analysis(
    [os.path.join('MultiPlayer', 'MultiPlayer.py')],
    pathex=[os.path.join(project_dir, 'MultiPlayer')],
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
    excludes=EXCLUDED_MODULES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
a.binaries = [b for b in a.binaries if not _qt_unused(b[0])]
a.datas = [d for d in a.datas if not _qt_unused(d[0])]

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
    icon='icona.ico',
    version=version_info,
)