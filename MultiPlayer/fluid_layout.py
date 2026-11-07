"""Layout proporzionale dei controlli di Mp3Widget.

Ogni disposizione è una tabella di rettangoli in coordinate di riferimento:
la griglia esterna decide la dimensione della cella e i controlli la seguono,
senza che i loro testi possano imporre una larghezza minima.
"""
from PySide6.QtCore import QRect, QSize
from PySide6.QtWidgets import QLayout

QWIDGETSIZE_MAX = 16777215
MIN_FONT_PT = 7.0
MAX_FONT_SCALE = 2.5

# ref: dimensione a cui i rettangoli valgono 1:1 (font base).
# min: sotto questa dimensione interviene lo scroll della griglia esterna:
#      è la soglia a cui i testi, a MIN_FONT_PT, entrano ancora nei controlli.
# filename_vertical / progress_vertical: facoltativi, nome e waveform ruotati di 90°.
# short_times: facoltativo, tempi sempre senza 'Elapsed:'/'Remaining:'.
# band: facoltativo, (fisso, (elastici...)): il fisso ha larghezza che segue
#      l'altezza del widget, gli elastici alla sua destra si spartiscono il resto.
# gain_font_mid: facoltativo, gain a metà tra il font comune e quello dei tempi.
# max: facoltativo, limite del widget: DENSE_A resta una riga, MIXER una striscia.
# narrow: facoltativo, {controllo: (x, larghezza)} in pixel alla larghezza min:
#      tra min e ref si passa linearmente da qui a items, così a cedere spazio
#      sono i controlli scelti e non tutti in proporzione.
LAYOUT_SPECS = {
    'COMPACT': {
        'ref': (626, 99), 'min': (500, 70), 'slider_vertical': False,
        'items': {
            'btnChangeLayout':  (10, 10, 28, 25),
            'btnPlay':          (44, 10, 80, 25),
            'btnStop':          (130, 10, 48, 25),
            'filename_label':   (184, 10, 114, 25),
            'lblRemainingTime': (304, 10, 136, 25),
            'lblVolume':        (446, 10, 28, 25),
            'slidVolume':       (480, 10, 65, 25),
            'btnRemove':        (551, 10, 65, 25),
            'progress_bar':     (10, 41, 606, 48),
        },
    },
    'TOUCH': {
        'ref': (961, 152), 'min': (516, 92), 'slider_vertical': True,
        'narrow': {
            'btnRemove': (5, 52), 'btnNorm': (5, 52), 'btnChangeLayout': (60, 30),
            'filename_label': (60, 98), 'lblElapsedTime': (93, 29), 'lblRemainingTime': (125, 33),
            'btnPlay': (161, 58), 'btnFadeIn': (222, 58),
            'spinboxFadeTime': (283, 44), 'fade_preset_widget': (283, 44),
            'btnFadeOut': (330, 58), 'btnStop': (391, 58),
            'lblVolume': (456, 33), 'spinboxGain': (452, 41),
            'progress_bar': (5, 488), 'slidVolume': (496, 15),
        },
        'items': {
            'btnRemove':          (10, 10, 67, 36),
            'btnNorm':            (10, 52, 67, 36),
            'btnChangeLayout':    (83, 52, 66, 36),
            'filename_label':     (83, 10, 330, 36),
            'lblElapsedTime':     (155, 52, 118, 36),
            'lblRemainingTime':   (279, 52, 134, 36),
            'btnPlay':            (419, 10, 84, 78),
            'btnFadeIn':          (509, 10, 84, 78),
            'spinboxFadeTime':    (599, 10, 80, 36),
            'fade_preset_widget': (599, 52, 80, 36),
            'btnFadeOut':         (685, 10, 84, 78),
            'btnStop':            (775, 10, 84, 78),
            'lblVolume':          (870, 10, 43, 36),
            'spinboxGain':        (865, 52, 52, 36),
            'progress_bar':       (10, 94, 907, 48),
            'slidVolume':         (923, 10, 28, 132),
        },
    },
    'STANDARD': {
        'ref': (818, 127), 'min': (510, 85), 'slider_vertical': False,
        'items': {
            'btnChangeLayout':    (10, 10, 105, 21),
            'filename_label':     (121, 10, 591, 21),
            'btnRemove':          (718, 10, 90, 21),
            'btnPlay':            (10, 37, 105, 26),
            'btnStop':            (121, 37, 65, 26),
            'btnFadeIn':          (192, 37, 75, 26),
            'spinboxFadeTime':    (273, 37, 75, 26),
            'fade_preset_widget': (354, 37, 58, 26),
            'btnFadeOut':         (418, 37, 92, 26),
            'btnNorm':            (516, 37, 72, 26),
            'spinboxGain':        (594, 37, 78, 26),
            'lblVolume':          (678, 37, 34, 26),
            'slidVolume':         (718, 37, 90, 26),
            'lblElapsedTime':     (10, 69, 105, 48),
            'progress_bar':       (121, 69, 591, 48),
            'lblRemainingTime':   (718, 69, 90, 48),
        },
    },
    'COMPACT_V': {
        'ref': (336, 113), 'min': (270, 96), 'slider_vertical': True,
        'items': {
            'btnRemove':        (10, 10, 150, 21),
            'btnChangeLayout':  (166, 10, 134, 21),
            'filename_label':   (10, 37, 290, 18),
            'btnPlay':          (10, 61, 82, 18),
            'btnFadeIn':        (98, 61, 64, 18),
            'btnFadeOut':       (168, 61, 76, 18),
            'btnStop':          (250, 61, 50, 18),
            'lblRemainingTime': (10, 85, 290, 18),
            'slidVolume':       (306, 10, 20, 93),
        },
    },
    'DENSE_A': {
        'ref': (982, 46), 'min': (680, 40), 'max': (QWIDGETSIZE_MAX, 46), 'slider_vertical': False,
        'items': {
            'btnChangeLayout':  (10, 10, 30, 26),
            'filename_label':   (46, 10, 169, 26),
            'progress_bar':     (221, 10, 209, 26),
            'lblElapsedTime':   (436, 10, 72, 26),
            'lblRemainingTime': (514, 10, 80, 26),
            'spinboxFadeTime':  (600, 10, 60, 26),
            'spinboxGain':      (666, 10, 64, 26),
            'slidVolume':       (736, 10, 64, 26),
            'lblVolume':        (806, 10, 30, 26),
            'btnPlay':          (842, 10, 28, 26),
            'btnStop':          (876, 10, 28, 26),
            'btnFadeIn':        (910, 10, 28, 26),
            'btnFadeOut':       (944, 10, 28, 26),
        },
    },
    'MIXER': {
        'ref': (157, 460), 'min': (89, 300), 'max': (176, QWIDGETSIZE_MAX), 'slider_vertical': True,
        'filename_vertical': True, 'progress_vertical': True, 'short_times': True,
        'band': ('filename_label', ('progress_bar', 'slidVolume')), 'gain_font_mid': True,
        'items': {
            'btnMore':          (10, 10, 137, 24),
            'lblElapsedTime':   (10, 40, 137, 20),
            'lblRemainingTime': (10, 64, 137, 20),
            'filename_label':   (10, 90, 20, 194),
            'progress_bar':     (36, 90, 79, 194),
            'slidVolume':       (121, 90, 26, 194),
            'spinboxGain':      (10, 290, 137, 22),
            'btnPlay':          (10, 318, 137, 30),
            'btnFadeIn':        (10, 352, 137, 30),
            'btnFadeOut':       (10, 386, 137, 30),
            'btnStop':          (10, 420, 137, 30),
        },
    },
}


class FluidLayout(QLayout):
    """Piazza ogni widget in un rettangolo scalato sulla dimensione reale.

    `on_geometry` viene chiamata dopo ogni piazzamento: a quel punto le
    geometrie dei figli sono definitive anche se il widget non è ancora visibile.
    """

    def __init__(self, on_geometry=None):
        super().__init__()
        self.setContentsMargins(0, 0, 0, 0)
        self._items = []
        self._rects = {}
        self._narrow = {}
        self._ref = (1, 1)
        self._min = (0, 0)
        self._band = None
        self._on_geometry = on_geometry

    def set_sizes(self, ref: tuple, minimum: tuple) -> None:
        self._ref = ref
        self._min = minimum
        self.invalidate()

    def set_band(self, fixed=None, flex=()) -> None:
        """`fixed` largo in proporzione all'altezza, `flex` si spartiscono il resto."""
        self._band = (fixed, tuple(flex)) if fixed is not None else None
        self.invalidate()

    def place(self, widget, rect: tuple, narrow: tuple = None) -> None:
        self.addWidget(widget)
        self._rects[widget] = rect
        self._narrow[widget] = narrow

    def placement(self, widget):
        """Rettangolo di riferimento del widget, None se non è nel layout."""
        return self._rects.get(widget)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        if not 0 <= index < len(self._items):
            return None
        item = self._items.pop(index)
        self._rects.pop(item.widget(), None)
        self._narrow.pop(item.widget(), None)
        return item

    def sizeHint(self):
        return QSize(*self._ref)

    def minimumSize(self):
        return QSize(*self._min)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        sx = rect.width() / self._ref[0]
        sy = rect.height() / self._ref[1]
        edges = {}
        for item in self._items:
            widget = item.widget()
            x, y, w, h = self._rects[widget]
            # Si arrotondano i bordi, non le dimensioni: la somma di larghezze
            # arrotondate farebbe sovrapporre o distanziare i vicini.
            edges[widget] = self._edges(widget, x, x + w, rect.width(), sx)
        if self._band is not None and self._band[0] in edges:
            self._apply_band(edges, sx, sy)
        for widget, (left, right) in edges.items():
            x, y, w, h = self._rects[widget]
            top = round(y * sy)
            widget.setGeometry(QRect(rect.x() + left, rect.y() + top,
                                     right - left, round((y + h) * sy) - top))
        if self._on_geometry is not None:
            self._on_geometry()

    def _apply_band(self, edges, sx, sy):
        fixed, flex = self._band
        fx, _, fw, _ = self._rects[fixed]
        left = edges[fixed][0]
        band_right = max(edges[f][1] for f in flex)
        ref_first = min(self._rects[f][0] for f in flex)
        ref_right = max(self._rects[f][0] + self._rects[f][2] for f in flex)
        width = min(round(fw * sy), (band_right - left) // 2)
        start = left + width + round((ref_first - fx - fw) * sx)
        k = (band_right - start) / (ref_right - ref_first)
        edges[fixed] = (left, left + width)
        for f in flex:
            x, _, w, _ = self._rects[f]
            edges[f] = (start + round((x - ref_first) * k), start + round((x + w - ref_first) * k))

    def _edges(self, widget, left, right, width, sx):
        narrow = self._narrow[widget]
        if narrow is None or width >= self._ref[0]:
            return round(left * sx), round(right * sx)
        t = max(0, (width - self._min[0]) / (self._ref[0] - self._min[0]))
        x, w = narrow
        return round(x + t * (left - x)), round(x + w + t * (right - x - w))
