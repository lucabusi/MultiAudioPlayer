"""Test di regressione per i bug corretti.

Ogni test corrisponde a un difetto realmente osservato: se torna rosso, il
bug è rientrato. Girano offscreen (nessuna finestra, nessun audio) usando i
file di `audio_test/`, quindi non serve un device audio.

    python tests/test_regressions.py     # runner autonomo
    pytest tests/                        # oppure via pytest
"""
import os
import subprocess
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'MultiPlayer')
AUD = os.path.join(ROOT, 'audio_test')
if SRC not in sys.path:
    sys.path.insert(0, SRC)


_APP = None
_ARGV: list = []


def _app():
    """QApplication condivisa dai test (Qt ne ammette una sola per processo).

    Il riferimento è tenuto a livello di modulo: se lo perdessimo, PyQt5
    distruggerebbe la QApplication mentre i widget sono ancora vivi e il
    processo abortirebbe. Anche `_ARGV` va tenuto in vita, non passato inline.
    """
    global _APP
    if _APP is None:
        from PyQt5.QtWidgets import QApplication
        _APP = QApplication.instance() or QApplication(_ARGV)
    return _APP


def _pump(ms=200):
    """Fa girare l'event loop per `ms` senza bloccare: i backend caricano il
    media in modo asincrono e i fade avanzano su QTimer."""
    from PyQt5.QtCore import QTimer
    app = _app()
    done = []
    QTimer.singleShot(ms, lambda: done.append(1))
    while not done:
        app.processEvents()


def _is_green(btn):
    return 'green' in btn.styleSheet()


# ---------------------------------------------------------------------------
# bug 1 — un'eccezione che esce da uno slot Qt fa abortire l'intero processo
# (PyQt5 la trasforma in qFatal()). Serve un subprocess: se il bug rientra,
# questo processo morirebbe senza poter riportare il fallimento.
# ---------------------------------------------------------------------------
_CRASH_SNIPPET = r'''
import os, sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r"{src}")
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from mp3file import Mp3File
from mp3widget import Mp3Widget

app = QApplication([])
w = Mp3Widget(Mp3File(r"{f1}", backend='qt'))
done = []
QTimer.singleShot(300, lambda: done.append(1))
while not done:
    app.processEvents()

def boom(*a, **k):
    raise RuntimeError('audio device lost')

w.mp3file._backend.play = boom
w.mp3file._backend.stop = boom
QTimer.singleShot(20, w.on_play_pause_clicked)
QTimer.singleShot(80, w.on_stop_clicked)
QTimer.singleShot(400, app.quit)
app.exec_()
print('SURVIVED')
'''


def test_errore_backend_non_abbatte_app():
    """Un errore del backend su Play/Stop va segnalato, non propagato."""
    code = _CRASH_SNIPPET.format(src=SRC, f1=os.path.join(AUD, 'pink_panther.mp3'))
    p = subprocess.run([sys.executable, '-u', '-c', code],
                       capture_output=True, text=True, cwd=ROOT, timeout=180)
    assert 'SURVIVED' in p.stdout, (
        f"l'app e' morta (exit={p.returncode}); "
        f"stdout={p.stdout!r} stderr={p.stderr[-400:]!r}")


# ---------------------------------------------------------------------------
# bug 2 — a griglia piena addWidget(w, -1, -1) scarta il widget in silenzio:
# restava in mp3_widgets, invisibile e con il backend audio aperto.
# ---------------------------------------------------------------------------
def test_load_progetto_griglia_piena_non_perde_file():
    import json
    from PyQt5 import QtWidgets
    from grid_manager import MAX_ROWS
    import mainapp as MA

    _app()
    capienza = MAX_ROWS * 2  # MainApp.initial_cols
    proj = {
        'version': '1.2',
        # entry senza row/col: formato più vecchio o progetto scritto a mano
        'files': [{'file_path': os.path.join(AUD, 'pink_panther.mp3'),
                   'volume': 100, 'fade_time': 5.0, 'gain': 1.0,
                   'layout': 'TOUCH'} for _ in range(capienza + 3)],
    }
    path = os.path.join(ROOT, 'tests', '_tmp_full_grid.mpp')
    with open(path, 'w') as fh:
        json.dump(proj, fh)

    warnings = []
    orig_warning = QtWidgets.QMessageBox.warning
    orig_dialog = QtWidgets.QFileDialog.getOpenFileName
    QtWidgets.QMessageBox.warning = staticmethod(
        lambda *a, **k: warnings.append(a[2] if len(a) > 2 else ''))
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (path, ''))
    try:
        m = MA.MainApp()
        m.hide()
        m.load_project()
        _pump(300)
        in_griglia = m.grid_layout.count()
        in_lista = len(m.mp3_widgets)
        for w in list(m.mp3_widgets):
            w.shutdown()
        m.mp3_widgets.clear()
        m.close()
    finally:
        QtWidgets.QMessageBox.warning = orig_warning
        QtWidgets.QFileDialog.getOpenFileName = orig_dialog
        if os.path.exists(path):
            os.remove(path)

    assert in_lista == in_griglia, (
        f"{in_lista - in_griglia} widget tenuti in mp3_widgets ma mai piazzati "
        f"nella griglia (invisibili, con il backend audio aperto)")
    assert in_griglia == capienza, f"piazzati {in_griglia} widget invece di {capienza}"
    assert warnings, "nessun avviso all'utente per i file non caricati"


# ---------------------------------------------------------------------------
# bug 3 — to_state() leggeva mp3file.actual_volume, che durante un fade è il
# volume istantaneo della rampa: salvare a metà fade corrompeva il progetto.
# ---------------------------------------------------------------------------
def test_salvataggio_durante_fade_usa_volume_utente():
    from mp3file import Mp3File
    from mp3widget import Mp3Widget

    _app()
    w = Mp3Widget(Mp3File(os.path.join(AUD, 'pink_panther.mp3'), backend='qt'))
    _pump(400)
    w.set_volume(90)
    w.set_fade_time(8)
    w.on_fade_in_clicked()
    _pump(500)  # a metà rampa
    assert w.mp3file.actual_volume < 50, "il fade non sta salendo: test non valido"
    saved = w.to_state()['volume']
    w.shutdown()
    assert saved == 90, f"salvato {saved} invece di 90 (volume istantaneo del fade)"


# ---------------------------------------------------------------------------
# bug 4 — il verde del Fade Out veniva acceso dal click e non dal fade reale:
# restava acceso per sempre se il fade non partiva o veniva messo in pausa.
# ---------------------------------------------------------------------------
def test_indicatore_fadeout_a_traccia_ferma():
    from mp3file import Mp3File
    from mp3widget import Mp3Widget

    _app()
    w = Mp3Widget(Mp3File(os.path.join(AUD, 'pink_panther.mp3'), backend='qt'))
    _pump(400)
    assert not w.mp3file.is_playing()
    w.on_fade_out_clicked()   # no-op: la traccia non suona
    _pump(300)
    green = _is_green(w.btnFadeOut)
    w.shutdown()
    assert not green, "btnFadeOut verde anche se nessun fade e' partito"


def test_indicatore_fadeout_spento_dalla_pausa():
    from mp3file import Mp3File
    from mp3widget import Mp3Widget

    _app()
    w = Mp3Widget(Mp3File(os.path.join(AUD, 'mitra.mp3'), backend='qt'))
    _pump(600)
    w.set_fade_time(8)
    w.on_play_pause_clicked()
    _pump(400)
    assert w.mp3file.is_playing(), "la traccia non suona: test non valido"
    w.on_fade_out_clicked()
    _pump(300)
    assert _is_green(w.btnFadeOut), "btnFadeOut non verde durante un fade out reale"
    w.on_play_pause_clicked()  # la pausa annulla il fade
    _pump(300)
    green = _is_green(w.btnFadeOut)
    w.shutdown()
    assert not green, "btnFadeOut resta verde dopo la pausa che ha annullato il fade"


# ---------------------------------------------------------------------------
# bug 5 — QGridLayout non rimpicciolisce mai columnCount(): le colonne di un
# layout precedente restavano prenotate a 60px per sempre.
# ---------------------------------------------------------------------------
def test_nessuna_colonna_fantasma_dopo_drag():
    from mp3file import Mp3File
    from mp3widget import Mp3Widget
    import mainapp as MA

    _app()
    m = MA.MainApp()
    m.hide()
    w = Mp3Widget(Mp3File(os.path.join(AUD, 'pink_panther.mp3'), backend='qt'))
    m.mp3_widgets.append(w)
    m.grid_layout.addWidget(w, 0, 0)
    m.grid_manager.update_column_stretches()

    for cella in ((0, 5), (0, 0)):  # drag su colonna alta e ritorno
        m.grid_layout.removeWidget(w)
        m.grid_layout.addWidget(w, *cella)
        m.grid_manager.update_column_stretches()

    mins = [m.grid_layout.columnMinimumWidth(c)
            for c in range(m.grid_layout.columnCount())]
    w.shutdown()
    m.mp3_widgets.clear()
    m.close()
    # colonne 0..1 = griglia corrente (initial_cols); oltre devono collassare
    sprecati = sum(mins[2:])
    assert sprecati == 0, f"colonne fantasma prenotate: {mins} ({sprecati}px sprecati)"


# ---------------------------------------------------------------------------
# bug 6 — set_gain ricostruiva actual_volume dal volume effettivo: con gain 0
# l'effettivo è 0 per definizione, quindi tornare a gain 1 lasciava il volume
# incollato a 0 (traccia muta senza motivo visibile).
# ---------------------------------------------------------------------------
def test_gain_a_zero_non_blocca_il_volume():
    from mp3file import Mp3File

    _app()
    f = Mp3File(os.path.join(AUD, 'pink_panther.mp3'), backend='qt')
    _pump(400)
    f.set_volume(100)
    f.set_gain(0.0)
    muto = f._effective_volume()
    f.set_gain(1.0)
    vol, eff = f.actual_volume, f._effective_volume()
    f.cleanup()
    assert muto == 0, f"gain 0 deve azzerare l'audio, effective={muto}"
    assert (vol, eff) == (100, 100), (
        f"dopo gain 0 -> 1 il volume resta a {vol} (effective {eff}) invece di 100")


# ---------------------------------------------------------------------------
# bug 7 — row/col letti dal .mpp non erano validati: due entry sulla stessa
# cella producevano due widget sovrapposti, uno invisibile sotto l'altro.
# ---------------------------------------------------------------------------
def test_celle_duplicate_nel_progetto_non_sovrappongono_widget():
    import json
    from PyQt5 import QtWidgets
    import mainapp as MA

    _app()
    entry = {'file_path': os.path.join(AUD, 'pink_panther.mp3'), 'volume': 100,
             'fade_time': 5.0, 'gain': 1.0, 'layout': 'TOUCH', 'row': 0, 'col': 0}
    proj = {'version': '1.2', 'files': [dict(entry), dict(entry)]}
    path = os.path.join(ROOT, 'tests', '_tmp_dup_cells.mpp')
    with open(path, 'w') as fh:
        json.dump(proj, fh)

    orig_warning = QtWidgets.QMessageBox.warning
    orig_dialog = QtWidgets.QFileDialog.getOpenFileName
    QtWidgets.QMessageBox.warning = staticmethod(lambda *a, **k: None)
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (path, ''))
    try:
        m = MA.MainApp()
        m.hide()
        m.load_project()
        _pump(300)
        celle = [m.grid_layout.getItemPosition(i)[:2]
                 for i in range(m.grid_layout.count())]
        for w in list(m.mp3_widgets):
            w.shutdown()
        m.mp3_widgets.clear()
        m.close()
    finally:
        QtWidgets.QMessageBox.warning = orig_warning
        QtWidgets.QFileDialog.getOpenFileName = orig_dialog
        if os.path.exists(path):
            os.remove(path)

    assert len(celle) == 2, f"caricati {len(celle)} widget invece di 2"
    assert len(set(celle)) == 2, f"widget sovrapposti nella stessa cella: {celle}"


# ---------------------------------------------------------------------------
# bug 8 — con una durata dichiarata più corta della riproduzione reale (VBR
# mal taggati) remaining_seconds andava negativo e la label mostrava "-1:59".
# ---------------------------------------------------------------------------
def test_tempo_rimanente_mai_negativo():
    from mp3file import Mp3File, PlaybackState
    from mp3widget import Mp3Widget

    class _BackendOltreLaFine:
        """Backend che riferisce una posizione oltre la durata dichiarata."""
        def get_state(self): return PlaybackState.PLAYING
        def get_time_ms(self): return 125_000
        def get_duration_ms(self): return 120_000
        def set_volume(self, v): pass

    _app()
    w = Mp3Widget(Mp3File(os.path.join(AUD, 'pink_panther.mp3'), backend='qt'))
    _pump(400)
    w.mp3file._backend = _BackendOltreLaFine()
    w.mp3file.mp3_total_duration = 120_000
    rimanenti = w.mp3file.get_playback_info()['remaining_seconds']
    w.update_progress_bar()
    testo = w.lblRemainingTime.text()
    w.shutdown()
    assert rimanenti >= 0, f"remaining_seconds negativo: {rimanenti}"
    assert '-' not in testo, f"label con tempo negativo: {testo!r}"


# ---------------------------------------------------------------------------
# bug 9 — il QMessageBox dei file mancanti era dentro il loop di caricamento:
# un progetto spostato tra macchine apriva un popup per ogni file.
# ---------------------------------------------------------------------------
def test_file_mancanti_un_solo_avviso():
    import json
    from PyQt5 import QtWidgets
    import mainapp as MA

    _app()
    proj = {'version': '1.2',
            'files': [{'file_path': os.path.join(AUD, f'inesistente_{i}.mp3'),
                       'volume': 100, 'fade_time': 5.0, 'gain': 1.0,
                       'layout': 'TOUCH', 'row': 0, 'col': i} for i in range(3)]}
    path = os.path.join(ROOT, 'tests', '_tmp_missing.mpp')
    with open(path, 'w') as fh:
        json.dump(proj, fh)

    avvisi = []
    orig_warning = QtWidgets.QMessageBox.warning
    orig_dialog = QtWidgets.QFileDialog.getOpenFileName
    QtWidgets.QMessageBox.warning = staticmethod(
        lambda *a, **k: avvisi.append(a[2] if len(a) > 2 else ''))
    QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (path, ''))
    try:
        m = MA.MainApp()
        m.hide()
        m.load_project()
        _pump(200)
        m.close()
    finally:
        QtWidgets.QMessageBox.warning = orig_warning
        QtWidgets.QFileDialog.getOpenFileName = orig_dialog
        if os.path.exists(path):
            os.remove(path)

    assert len(avvisi) == 1, f"{len(avvisi)} popup per 3 file mancanti, atteso 1"
    for i in range(3):
        assert f'inesistente_{i}.mp3' in avvisi[0], (
            f"l'avviso non elenca inesistente_{i}.mp3: {avvisi[0]!r}")


# ---------------------------------------------------------------------------
# bug 10 — il drag&drop nella griglia si armava solo se il click cadeva
# esattamente sulla label del nome file: afferrando il widget in qualunque
# altro punto (il frame, le label dei tempi) non partiva alcun QDrag e il
# widget sembrava inamovibile.
# ---------------------------------------------------------------------------
def test_drag_si_arma_da_tutto_il_corpo_del_widget():
    from PyQt5.QtCore import Qt, QPoint
    from PyQt5.QtGui import QMouseEvent
    from mp3file import Mp3File
    from mp3widget import Mp3Widget

    app = _app()
    w = Mp3Widget(Mp3File(os.path.join(AUD, 'pink_panther.mp3'), backend='qt'))
    w.resize(700, 220)
    w.show()
    _pump(300)

    def premi(pos):
        w._drag_armed = False
        app.sendEvent(w, QMouseEvent(QMouseEvent.MouseButtonPress, pos,
                                     Qt.LeftButton, Qt.LeftButton, Qt.NoModifier))
        return w._drag_armed

    def centro(child):
        return child.mapTo(w, child.rect().center())

    afferrabili = {'nome file': centro(w.filename_label),
                   'label tempo trascorso': centro(w.lblElapsedTime),
                   'angolo del frame': QPoint(2, 2)}
    controlli = {'btnPlay': centro(w.btnPlay),
                 'btnStop': centro(w.btnStop),
                 'slider volume': centro(w.slidVolume),
                 'spinbox gain': centro(w.spinboxGain),
                 'progress bar': centro(w.progress_bar)}

    armati = {nome: premi(p) for nome, p in afferrabili.items()}
    rubati = {nome: premi(p) for nome, p in controlli.items()}
    w.shutdown()

    non_afferrabili = [n for n, ok in armati.items() if not ok]
    assert not non_afferrabili, (
        f"drag non armato afferrando: {non_afferrabili} (il widget non si sposta)")
    scippati = [n for n, ok in rubati.items() if ok]
    assert not scippati, f"il drag ruba il click ai controlli: {scippati}"


def main():
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith('test_') and callable(o)]
    falliti = 0
    for name, fn in tests:
        try:
            fn()
            print(f'PASS  {name}')
        except Exception as e:
            falliti += 1
            print(f'FAIL  {name}\n      {type(e).__name__}: {e}')
    print(f'\n{len(tests) - falliti}/{len(tests)} verdi')
    return 1 if falliti else 0


if __name__ == '__main__':
    sys.exit(main())
