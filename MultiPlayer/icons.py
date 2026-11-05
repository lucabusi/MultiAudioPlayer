"""Simboli dei pulsanti disegnati dall'app.

QIcon.fromTheme dipende dal tema icone del desktop: su Windows Qt ne ha uno
interno, su Linux spesso il tema configurato manca e i pulsanti restano vuoti.
Anche i caratteri Unicode dipendono dai font installati. Qui le forme sono
tracciate con QPainter su una tela grande, che QIcon riduce alla taglia del
pulsante: stesso aspetto su ogni piattaforma, nessun file da distribuire.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

_SIZE = 64
_COLOR = QColor('#1f2a33')
_cache = {}


def _poly(p, *points):
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))


def _play(p):
    _poly(p, (18, 10), (54, 32), (18, 54))


def _pause(p):
    p.drawRect(QRectF(14, 10, 13, 44))
    p.drawRect(QRectF(37, 10, 13, 44))


def _stop(p):
    p.drawRect(QRectF(12, 12, 40, 40))


def _fade_in(p):
    _poly(p, (6, 54), (58, 10), (58, 54))


def _fade_out(p):
    _poly(p, (6, 10), (58, 54), (6, 54))


def _remove(p):
    p.setPen(QPen(_COLOR, 9, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(14, 14, 50, 50)
    p.drawLine(50, 14, 14, 50)


def _norm(p):
    # Forma d'onda il cui picco tocca i limiti: il segnale portato al livello pieno.
    p.drawRect(QRectF(4, 4, 56, 4))
    p.drawRect(QRectF(4, 56, 56, 4))
    for i, h in enumerate((0.35, 0.7, 1.0, 0.55, 0.85, 0.4)):
        half = 22 * h
        p.drawRect(QRectF(7 + i * 9, 32 - half, 6, 2 * half))


def _layout(p):
    for x in (8, 36):
        for y in (8, 36):
            p.drawRect(QRectF(x, y, 20, 20))


def _more(p):
    for x in (12, 32, 52):
        p.drawEllipse(QPointF(x, 32), 6, 6)


_DRAW = {'play': _play, 'pause': _pause, 'stop': _stop, 'fade_in': _fade_in,
         'fade_out': _fade_out, 'remove': _remove, 'norm': _norm,
         'layout': _layout, 'more': _more}


def icon(name: str) -> QIcon:
    """Icona `name` (chiave di _DRAW); sempre la stessa istanza per nome."""
    if name not in _cache:
        pixmap = QPixmap(_SIZE, _SIZE)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(_COLOR)
        _DRAW[name](p)
        p.end()
        _cache[name] = QIcon(pixmap)
    return _cache[name]
