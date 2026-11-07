"""Tema Foyer: palette scura dell'app e stile dei controlli di Mp3Widget.

Toni blu-ardesia per pagina, card, campi e display; i pulsanti si riconoscono
dal colore del loro ruolo (play verde, stop corallo, fade ambra, utilità
grigio-azzurro): tinti quando sono a riposo, pieni quando sono accesi.
I pulsanti scelgono ruolo e stato con le property `role` e `state`.
"""
import os
import tempfile

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPalette, QPen, QPixmap

PAGE = '#0f1317'
SURFACE = '#1a2027'
BORDER = '#2a333d'
FIELD = '#222a33'
FIELD_BORDER = '#2c3640'
DISPLAY = '#141a20'
INK = '#e9eef3'
MUTED = '#9aa8b6'
ON_ACCENT = '#0d1a14'      # simbolo e testo sopra un pulsante acceso
REMAIN = '#7cc4ff'
TRACK = '#2e3843'
WAVE_IDLE = '#4a5866'
WAVE_PLAYED = '#3ecf8e'
ROLES = {'play': '#3ecf8e', 'stop': '#ff7a6b', 'fade': '#f2b84b', 'util': '#a9bdd1'}
# Stato -> colore del pulsante pieno; la pausa è un avviso, non un errore.
STATE_COLOR = {'paused': ROLES['fade']}

CARD_RADIUS = 11
# QSS ignora un border-radius oltre metà del lato: i controlli più bassi, in
# COMPACT_V alla dimensione minima, sono alti 15px.
RADIUS = 6

FONT = 'Inter'
MONO = 'JetBrains Mono'
_FONT_FILES = ('Inter[opsz,wght].ttf', 'JetBrainsMono[wght].ttf')
_fonts_loaded = False


def load_fonts() -> None:
    """Registra i font del tema (una volta sola): senza, Qt ripiega su altri."""
    global _fonts_loaded
    if _fonts_loaded:
        return
    _fonts_loaded = True
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')
    for name in _FONT_FILES:
        QFontDatabase.addApplicationFont(os.path.join(folder, name))


def font(family: str, base: QFont) -> QFont:
    f = QFont(base)
    f.setFamily(family)
    return f


def role_color(role: str, state: str = '') -> str:
    """Colore del simbolo di un pulsante: quello del ruolo, scuro se è pieno."""
    return ON_ACCENT if state else ROLES[role]


def _rgba(hex_color: str, alpha: float) -> str:
    c = QColor(hex_color)
    return f'rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})'


def palette() -> QPalette:
    """Palette di tutta l'app (menu, dialoghi, barre di scorrimento)."""
    p = QPalette()
    for role, color in ((QPalette.Window, PAGE), (QPalette.WindowText, INK),
                        (QPalette.Base, FIELD), (QPalette.AlternateBase, SURFACE),
                        (QPalette.Text, INK), (QPalette.Button, SURFACE),
                        (QPalette.ButtonText, INK), (QPalette.ToolTipBase, SURFACE),
                        (QPalette.ToolTipText, INK), (QPalette.PlaceholderText, MUTED),
                        (QPalette.Highlight, ROLES['play']), (QPalette.HighlightedText, ON_ACCENT),
                        (QPalette.Light, BORDER), (QPalette.Midlight, FIELD_BORDER),
                        (QPalette.Mid, BORDER), (QPalette.Dark, DISPLAY),
                        (QPalette.Shadow, '#000000'), (QPalette.Link, REMAIN)):
        p.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(MUTED).darker(150))
    return p


def _arrow_files() -> tuple:
    """Frecce delle spinbox per il QSS, che le accetta solo come file: create
    al volo nella cartella temporanea, il colore nel nome le rinnova se cambia."""
    folder = os.path.join(tempfile.gettempdir(), 'mp3player_theme')
    os.makedirs(folder, exist_ok=True)
    paths = []
    for name, ys in (('up', (13, 7)), ('down', (7, 13))):
        path = os.path.join(folder, f'arrow_{name}_{MUTED[1:]}.png')
        if not os.path.isfile(path):
            pm = QPixmap(20, 20)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(QPen(QColor(MUTED), 2.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPolyline([QPointF(4, ys[0]), QPointF(10, ys[1]), QPointF(16, ys[0])])
            p.end()
            pm.save(path)
        paths.append(path.replace(os.sep, '/'))
    return tuple(paths)


def frame_qss() -> str:
    """Stylesheet del frame di Mp3Widget (objectName `card`) e dei suoi controlli."""
    up, down = _arrow_files()
    qss = f"""
QFrame#card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: {CARD_RADIUS}px; }}
QLabel {{ background: {FIELD}; border: 1px solid {FIELD_BORDER}; border-radius: {RADIUS}px;
          color: {INK}; font-weight: bold; padding: 0 2px; }}
QLabel[error="true"] {{ color: {ROLES['stop']}; }}
QLabel#lblElapsedTime, QLabel#lblRemainingTime {{ background: {DISPLAY}; }}
QLabel#lblRemainingTime {{ color: {REMAIN}; }}
QLabel#lblVolume {{ background: transparent; border: none; color: {MUTED}; }}
QDoubleSpinBox {{ background: {FIELD}; border: 1px solid {FIELD_BORDER}; border-radius: {RADIUS}px;
                  color: {INK}; font-weight: bold; padding: 0 2px;
                  selection-background-color: {ROLES['fade']}; selection-color: {ON_ACCENT}; }}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ background: transparent; border: none; width: 16px; }}
QDoubleSpinBox::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
QDoubleSpinBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
QPushButton, QToolButton {{ background: {FIELD}; color: {MUTED}; border: 1px solid {FIELD_BORDER};
                            border-radius: {RADIUS}px; font-weight: bold; padding: 0 2px; }}
QPushButton:hover, QToolButton:hover {{ border-color: {MUTED}; }}
QPushButton:disabled, QToolButton:disabled {{ background: transparent; color: {BORDER}; border-color: {BORDER}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QSlider {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 6px; background: {TRACK}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {ROLES['play']}; border-radius: 3px; }}
QSlider::add-page:horizontal {{ background: {TRACK}; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {INK}; border: 1px solid {BORDER}; border-bottom: 2px solid {MUTED};
                              width: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::groove:vertical {{ width: 6px; background: {TRACK}; border-radius: 3px; }}
QSlider::add-page:vertical {{ background: {ROLES['play']}; border-radius: 3px; }}
QSlider::sub-page:vertical {{ background: {TRACK}; border-radius: 3px; }}
QSlider::handle:vertical {{ background: {INK}; border: 1px solid {BORDER}; border-bottom: 2px solid {MUTED};
                            height: 10px; margin: 0 -3px; border-radius: 4px; }}
"""
    for role, c in ROLES.items():
        qss += (f'*[role="{role}"] {{ background: {_rgba(c, 0.14)}; color: {c}; '
                f'border: 1px solid {_rgba(c, 0.33)}; }}\n'
                f'*[role="{role}"]:hover {{ border-color: {c}; }}\n'
                f'*[role="{role}"][state="on"] {{ background: {c}; color: {ON_ACCENT}; border-color: {c}; }}\n')
    for state, c in STATE_COLOR.items():
        qss += f'*[state="{state}"] {{ background: {c}; color: {ON_ACCENT}; border-color: {c}; }}\n'
    return qss
