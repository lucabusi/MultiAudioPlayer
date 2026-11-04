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
import unittest

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

    Il riferimento è tenuto a livello di modulo: se lo perdessimo, PySide6
    distruggerebbe la QApplication mentre i widget sono ancora vivi e il
    processo abortirebbe. Anche `_ARGV` va tenuto in vita, non passato inline.
    """
    global _APP
    if _APP is None:
        from PySide6.QtWidgets import QApplication
        _APP = QApplication.instance() or QApplication(_ARGV)
    return _APP


def _pump(ms=200):
    """Fa girare l'event loop per `ms` senza bloccare: i backend caricano il
    media in modo asincrono e i fade avanzano su QTimer."""
    from PySide6.QtCore import QTimer
    app = _app()
    done = []
    QTimer.singleShot(ms, lambda: done.append(1))
    while not done:
        app.processEvents()


def _is_green(btn):
    return 'green' in btn.styleSheet()


# ---------------------------------------------------------------------------
# bug 1 — un'eccezione che esce da uno slot Qt fa abortire l'intero processo
# (con PyQt5 un'eccezione che esce da uno slot Qt faceva abortire il processo
# (qFatal()); con PySide6 non aborta più, ma il test resta come guardia:
# Play/Stop non devono propagare l'errore). Serve un subprocess: se il bug
# rientra, questo processo morirebbe senza poter riportare il fallimento.
# ---------------------------------------------------------------------------
_CRASH_SNIPPET = r'''
import os, sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, r"{src}")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
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
app.exec()
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
    from PySide6 import QtWidgets
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
    if not w.mp3file.is_playing():
        # serve un device audio reale (es. runner CI headless non ne ha)
        w.shutdown()
        raise unittest.SkipTest("la traccia non suona: nessun device audio")
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
    from PySide6 import QtWidgets
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
    from PySide6 import QtWidgets
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
    from PySide6.QtCore import Qt, QPoint, QPointF, QEvent
    from PySide6.QtGui import QMouseEvent
    from mp3file import Mp3File
    from mp3widget import Mp3Widget

    app = _app()
    w = Mp3Widget(Mp3File(os.path.join(AUD, 'pink_panther.mp3'), backend='qt'))
    w.resize(700, 220)
    w.show()
    _pump(300)

    def premi(pos):
        w._drag_armed = False
        app.sendEvent(w, QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(pos),
                                     QPointF(w.mapToGlobal(pos)),
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


# ---------------------------------------------------------------------------
# bug 9 — il default del costruttore Mp3File era 'vlc' mentre README,
# requirements.txt e mainapp.py dichiarano 'qt' come backend predefinito.
# Ogni call-site che ometteva l'argomento (script, servizi futuri) otteneva
# in silenzio VLC, cioe' il backend con l'accoppiamento dei volumi via
# sessione audio Windows documentato in docs/lessons.md.
# ---------------------------------------------------------------------------
def test_default_backend_e_quello_documentato():
    import inspect
    from mp3file import Mp3File

    default = inspect.signature(Mp3File.__init__).parameters['backend'].default
    assert default == 'qt', (
        f"default del costruttore '{default}' invece di 'qt': "
        "diverge da README/requirements/mainapp")

    from constants import DEFAULT_BACKEND
    assert DEFAULT_BACKEND == 'qt', (
        f"DEFAULT_BACKEND e' '{DEFAULT_BACKEND}': allineare il default di Mp3File")


# ---------------------------------------------------------------------------
# feature 3.2.0 — il backend si sceglieva solo modificando il sorgente. Il menu
# "Configura -> Backend audio" deve esporre tutti i backend registrati, cambiare
# quello usato dai file aperti dopo e ricordare la scelta al riavvio.
# ---------------------------------------------------------------------------
def test_menu_configura_seleziona_e_ricorda_il_backend():
    import tempfile
    from PySide6.QtCore import QSettings
    from mp3file import available_backends
    import mainapp as MA

    _app()
    # QSettings dirottato su un file temporaneo: i test non devono sporcare la
    # configurazione reale dell'utente. QSettings.setPath() non basta (su Unix
    # NativeFormat e IniFormat condividono il percorso), quindi si sostituisce
    # la classe nel namespace di mainapp.
    ini = os.path.join(tempfile.mkdtemp(prefix='mp_settings_'), 'test.ini')
    orig_qsettings = MA.QSettings
    MA.QSettings = lambda *a, **k: orig_qsettings(ini, QSettings.IniFormat)

    m = MA.MainApp()
    m.hide()
    try:
        menus = {a.text(): a for a in m.menuBar().actions()}
        assert 'Configura' in menus, f"menu Configura assente: {list(menus)}"

        voci = {a.text(): a for a in menus['Configura'].menu().actions()}
        assert 'Backend audio' in voci, f"sottomenu backend assente: {list(voci)}"

        azioni = {a.text(): a for a in voci['Backend audio'].menu().actions()}
        assert set(azioni) == set(available_backends()), (
            f"voci {sorted(azioni)} != backend registrati {sorted(available_backends())}")
        assert azioni[m.backend].isChecked(), "backend corrente non spuntato nel menu"

        target = next(n for n in available_backends() if n != m.backend)
        azioni[target].trigger()
        assert m.backend == target, f"backend non cambiato: {m.backend}"
    finally:
        m.close()

    # Nuova istanza: la preferenza deve essere riletta da QSettings.
    m2 = MA.MainApp()
    m2.hide()
    try:
        assert m2.backend == target, (
            f"backend non persistito: riavvio con '{m2.backend}' invece di '{target}'")
    finally:
        m2.close()
        MA.QSettings = orig_qsettings


# ---------------------------------------------------------------------------
# migrazione PySide6 — in Qt6 QMediaPlayer non ha più setVolume: senza un
# QAudioOutput collegato resta MUTO senza alcun errore. Il volume per-player
# (requisito: volumi indipendenti) deve passare dal suo QAudioOutput con la
# stessa curva logaritmica di prima.
# ---------------------------------------------------------------------------
def test_backend_qt_volume_passa_da_audio_output():
    from mp3file import Mp3File

    _app()
    f = Mp3File(os.path.join(AUD, 'mitra.mp3'), backend='qt')
    _pump(300)
    try:
        out = f._backend._player.audioOutput()
        assert out is not None, "QMediaPlayer senza QAudioOutput: in Qt6 resta muto"
        f._backend.set_volume(50)
        assert abs(out.volume() - 0.1505) < 0.01, (
            f"volume {out.volume():.4f}: attesa curva log (50 -> 0.1505)")
    finally:
        f.cleanup()


# ---------------------------------------------------------------------------
# migrazione PySide6 — QAudioOutput di Qt5 (stream PCM) è diventato QAudioSink
# in Qt6, e il formato fisso 8 kHz mono non è supportato da tutti i device
# (Realtek: isFormatSupported False). Il warmup deve restare attivo, non
# degradare in silenzio a "non disponibile" — altrimenti torna il ritardo di
# 1-2 s sul primo play dopo l'idle dell'endpoint.
# ---------------------------------------------------------------------------
def test_audio_warmup_attivo_se_esiste_un_device():
    from PySide6.QtMultimedia import QMediaDevices
    from audio_warmup import AudioWarmup

    _app()
    if QMediaDevices.defaultAudioOutput().isNull():
        raise unittest.SkipTest("nessun device audio di output")
    w = AudioWarmup()
    try:
        _pump(300)
        assert w._io is not None, "warmup non partito: stream di silenzio assente"
    finally:
        w.stop()


# ---------------------------------------------------------------------------
# bug 15 — l'exe includeva librosa (+ scipy, sklearn, numba, llvmlite) per un
# fallback di decode mai utile: l'app apre solo *.mp3, che libsndfile decodifica
# nativamente, e su Windows audioread non ha ffmpeg. Guardia: con bloccati i
# moduli che MultiPlayer.spec esclude dall'exe (EXCLUDED_MODULES) l'app si
# importa, decodifica gli mp3, usa la cache envelope e renderizza il JPEG.
# ---------------------------------------------------------------------------
_NO_HEAVY_SNIPPET = r'''
import glob, os, sys
for m in {excluded!r} + ['sklearn', 'numba']:
    sys.modules[m] = None   # import bloccato: ImportError se qualcuno lo usa
sys.path.insert(0, {src!r})
import mainapp, waveform
for f in glob.glob(os.path.join({aud!r}, '*.mp3')):
    assert len(waveform._decode_mono(f)) > 0, f
    waveform.generate_waveform_mem(f, width=64)   # scrive la cache .npz
    waveform.generate_waveform_mem(f, width=64)   # la rilegge con np.load
'''


def _spec_excluded_modules():
    import ast
    with open(os.path.join(ROOT, 'MultiPlayer.spec'), encoding='utf-8') as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', None) == 'EXCLUDED_MODULES':
            return ast.literal_eval(node.value)
    raise AssertionError('EXCLUDED_MODULES non trovato in MultiPlayer.spec')


def test_app_funziona_senza_moduli_esclusi_dall_exe():
    code = _NO_HEAVY_SNIPPET.format(excluded=_spec_excluded_modules(), src=SRC, aud=AUD)
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-800:]


# ---------------------------------------------------------------------------
# nuovi layout per-widget (DENSE_A, STRIP_A):
# devono comporsi, non lasciare residui sui 4 layout storici, sopravvivere al
# salvataggio .mpp e tenere sincronizzati i controlli aggiunti.
# ---------------------------------------------------------------------------
_COMUNI = ['filename_label', 'progress_bar', 'btnPlay', 'btnStop', 'btnFadeIn',
           'btnFadeOut', 'slidVolume', 'lblVolume', 'spinboxGain']
_NUOVI_LAYOUT = {
    # layout: (widget attesi nel grid, widget che NON devono esserci)
    'DENSE_A': (_COMUNI + ['lblElapsedTime', 'lblRemainingTime', 'spinboxFadeTime',
                           'btnChangeLayout'], ['btnRemove']),
    'STRIP_A': (_COMUNI + ['btnMore', 'lblRemainingTime'],
                ['btnChangeLayout', 'btnRemove', 'btnNorm']),
}
_VECCHI_LAYOUT = ['COMPACT', 'COMPACT_V', 'TOUCH', 'STANDARD']
_ATTRS_POS = sorted({a for e, n in _NUOVI_LAYOUT.values() for a in e + n}
                    | {'btnNorm', 'btnChangeLayout', 'btnRemove', 'lblElapsedTime',
                       'lblRemainingTime', 'spinboxFadeTime', 'fade_preset_widget'})


def _nuovo_widget(layout='STANDARD', fname='pink_panther.mp3'):
    from mp3file import Mp3File
    from mp3widget import Mp3Widget, WidgetLayout
    _app()
    return Mp3Widget(Mp3File(os.path.join(AUD, fname), backend='qt'), layout=WidgetLayout[layout])


def _posizioni(w):
    g = w.widget_file_frame_layout
    out = {}
    for a in _ATTRS_POS:
        out[a] = g.placement(getattr(w, a))
    return out


def test_nuovi_layout_si_compongono_con_tutti_i_controlli_visibili():
    for name, (attesi, assenti) in _NUOVI_LAYOUT.items():
        w = _nuovo_widget(name)
        pos = _posizioni(w)
        w.show()
        _pump(50)
        mancanti = [a for a in attesi if pos[a] is None]
        presenti = [a for a in assenti if pos[a] is not None]
        nascosti = [a for a in attesi if getattr(w, a).isHidden()]
        righe = {p[1] for p in pos.values() if p}  # y nel riferimento
        w.shutdown()
        assert not mancanti, f"{name}: non nel grid {mancanti}"
        assert not presenti, f"{name}: non devono essere nel grid {presenti}"
        assert not nascosti, f"{name}: nascosti {nascosti}"
        if name == 'DENSE_A':
            assert len(righe) == 1, f"{name}: righe {righe}"


def test_geometrie_specifiche_dei_nuovi_layout():
    from PySide6.QtCore import Qt
    w = _nuovo_widget('DENSE_A')
    w.show(); _pump(50)
    assert w.btnPlay.text() == ''   # solo icona del tema
    assert w.maximumHeight() == 46
    assert w.progress_bar.receivers("2clicked(double)") >= 1   # seek ancora collegato
    w.set_layout(type(w.widgetLayout).STRIP_A); _pump(50)
    assert w.slidVolume.orientation() == Qt.Vertical
    assert w.btnFadeIn.text() == 'IN' and w.btnPlay.text() == ''
    assert w.maximumWidth() == 176 and w.maximumHeight() == 16777215
    w.shutdown()


def test_nuovi_layout_non_lasciano_residui_sui_vecchi():
    from mp3widget import WidgetLayout
    base = {n: _posizioni(_nuovo_widget(n)) for n in _VECCHI_LAYOUT}
    w = _nuovo_widget('STANDARD')
    for n in list(_NUOVI_LAYOUT) + _VECCHI_LAYOUT:
        w.set_layout(WidgetLayout[n])
    for n in _VECCHI_LAYOUT:
        w.set_layout(WidgetLayout[n])
        assert _posizioni(w) == base[n], f"{n}: posizioni diverse da widget fresco"
    w.set_layout(WidgetLayout.STANDARD)
    w.show(); _pump(50)
    esito = (w.btnPlay.text(), w.progress_bar.maximumHeight(), w.progress_bar.maximumWidth(),
             w.maximumWidth(), w.lblRemainingTime.styleSheet(), w.filename_label.wordWrap(),
             w.slidVolume.minimumHeight())
    w.shutdown()
    assert esito == ('Play/Pause', 16777215, 16777215, 16777215, '', False, 0), esito


def test_nuovi_layout_salvati_e_ricaricati_nel_progetto():
    import project_manager
    from mp3widget import WidgetLayout
    for name in _NUOVI_LAYOUT:
        w = _nuovo_widget('STANDARD')
        w.set_layout(WidgetLayout[name])
        state = w.to_state()
        f = w.mp3file.file_name
        w.shutdown()
        assert state['layout'] == name
        w2 = _nuovo_widget('STANDARD')
        w2.apply_state(state)
        assert w2.widgetLayout.name == name
        w2.shutdown()
    w3 = _nuovo_widget('STANDARD')
    w3.apply_state({'layout': 'NON_ESISTE'})   # layout sconosciuto: resta quello attuale
    assert w3.widgetLayout.name == 'STANDARD'
    w3.shutdown()
    assert project_manager.CURRENT_VERSION == '1.2'


def test_menu_layout_ha_una_voce_per_ogni_layout():
    from mp3widget import WidgetLayout
    w = _nuovo_widget('STRIP_A')
    voci = [a.text() for a in w.btnChangeLayout.menu().actions()]
    w.shutdown()
    assert len(voci) == len(WidgetLayout) == 6, voci


def test_strip_a_menu_piu_fade_e_sottomenu_layout():
    w = _nuovo_widget('STRIP_A')
    menu = w.btnMore.menu()
    sottomenu = [a for a in menu.actions() if a.menu() is w.layout_menu]
    fade3 = [a for a in menu.actions() if a.text() == 'Fade 3s']
    assert sottomenu and fade3, [a.text() for a in menu.actions()]
    w.set_fade_time(5)
    fade3[0].trigger()
    esito = w.fade_time
    w.set_layout(type(w.widgetLayout).STANDARD)
    w.show(); _pump(50)
    ripristino = (w.maximumWidth(), w.filename_label.wordWrap())
    w.shutdown()
    assert esito == 3
    assert ripristino == (16777215, False)


# ---------------------------------------------------------------------------
# layout proporzionale: il widget segue la cella della griglia esterna, senza
# vincoli rigidi su altezza, larghezza dei testi e font.
# ---------------------------------------------------------------------------
_TUTTI_I_LAYOUT = _VECCHI_LAYOUT + list(_NUOVI_LAYOUT)


def _ridimensiona(w, width, height):
    w.resize(width, height)
    _pump(30)


def _piazzati(w):
    g = w.widget_file_frame_layout
    return [g.itemAt(i).widget() for i in range(g.count())]


def test_controlli_dentro_il_frame_e_senza_sovrapposizioni_a_ogni_scala():
    from fluid_layout import LAYOUT_SPECS
    for name in _TUTTI_I_LAYOUT:
        spec = LAYOUT_SPECS[name]
        w = _nuovo_widget(name)
        w.show()
        meta = ((spec['min'][0] + spec['ref'][0]) // 2, (spec['min'][1] + spec['ref'][1]) // 2)
        taglie = (spec['min'], meta, spec['ref'], (spec['ref'][0] * 2, spec['ref'][1] * 2))
        for taglia in taglie:
            _ridimensiona(w, *taglia)
            area = w.widget_main_frame.rect()
            figli = _piazzati(w)
            fuori = [type(c).__name__ for c in figli if not area.contains(c.geometry())]
            nascosti = [type(c).__name__ for c in figli if c.isHidden()]
            sovrapposti = [(type(a).__name__, type(b).__name__, a.geometry().getRect(), b.geometry().getRect())
                           for i, a in enumerate(figli) for b in figli[i + 1:]
                           if a.geometry().intersects(b.geometry())]
            assert not (fuori or nascosti or sovrapposti), (name, taglia, fuori, nascosti, sovrapposti)
        w.shutdown()


def test_touch_stretto_cedono_le_label_non_i_pulsanti():
    # Per stare in due colonne a 1080 px lo spazio va tolto alle label, non ai pulsanti.
    from fluid_layout import LAYOUT_SPECS
    spec = LAYOUT_SPECS['TOUCH']
    assert spec['min'][0] <= 518, spec['min']
    w = _nuovo_widget('TOUCH')
    w.show()
    pulsanti = (w.btnPlay, w.btnFadeIn, w.btnFadeOut, w.btnStop)
    larghezze = {}
    for taglia in (spec['min'], spec['ref']):
        _ridimensiona(w, *taglia)
        misure = [p.width() for p in pulsanti]
        assert max(misure) - min(misure) <= 1, (taglia, misure)
        larghezze[taglia] = (misure[0], w.filename_label.width())
    w.shutdown()
    stretto, pieno = larghezze[spec['min']], larghezze[spec['ref']]
    assert stretto[0] / pieno[0] > 2 * stretto[1] / pieno[1], larghezze


def test_rettangoli_proporzionali_alla_cella():
    from fluid_layout import LAYOUT_SPECS
    for name in _TUTTI_I_LAYOUT:
        spec = LAYOUT_SPECS[name]
        w = _nuovo_widget(name)
        w.show()
        _ridimensiona(w, spec['ref'][0] * 2, spec['ref'][1] * 2)
        g = w.widget_file_frame_layout
        sx = g.geometry().width() / spec['ref'][0]
        sy = g.geometry().height() / spec['ref'][1]
        for c in _piazzati(w):
            x, y, cw, ch = g.placement(c)
            attesi = (x * sx, y * sy, cw * sx, ch * sy)
            reali = c.geometry().getRect()
            assert all(abs(a - b) <= 2 for a, b in zip(attesi, reali)), (name, attesi, reali)
        w.shutdown()


def test_nessuna_dimensione_fissa_residua():
    for name in _TUTTI_I_LAYOUT:
        w = _nuovo_widget(name)
        w.show()
        _ridimensiona(w, 2000, 800)
        esito = (w.width(), w.height())
        attesa = (min(2000, w.maximumWidth()), min(800, w.maximumHeight()))
        w.shutdown()
        assert esito == attesa, (name, esito, attesa)


def test_font_segue_la_scala_entro_i_limiti():
    from fluid_layout import LAYOUT_SPECS, MIN_FONT_PT
    w = _nuovo_widget('TOUCH')
    spec = LAYOUT_SPECS['TOUCH']
    w.show()
    _ridimensiona(w, *spec['ref'])
    base = w.btnPlay.font().pointSizeF()
    _ridimensiona(w, *spec['min'])
    piccolo = w.btnPlay.font().pointSizeF()
    _ridimensiona(w, spec['ref'][0] * 2, spec['ref'][1] * 2)
    grande = w.btnPlay.font().pointSizeF()
    _ridimensiona(w, spec['ref'][0] * 20, spec['ref'][1] * 20)
    enorme = w.btnPlay.font().pointSizeF()
    grassetto = w.filename_label.font().bold()
    w.shutdown()
    assert MIN_FONT_PT <= piccolo < base < grande, (piccolo, base, grande)
    assert enorme <= base * 2.5, (enorme, base)
    assert grassetto


def test_font_scalato_anche_sui_controlli_del_nuovo_layout():
    # I controlli fuori dal layout precedente non sono figli del frame: senza
    # riapplicare il font dopo set_layout resterebbero alla dimensione base.
    from mp3widget import WidgetLayout
    w = _nuovo_widget('COMPACT')
    w.show()
    _ridimensiona(w, 1800, 300)
    w.set_layout(WidgetLayout.TOUCH)
    _pump(50)
    pt = (w.btnPlay.font().pointSizeF(), w.btnFadeIn.font().pointSizeF())
    w.shutdown()
    assert pt[0] == pt[1] and pt[0] > 9, pt


def test_nome_file_lungo_non_allarga_il_widget():
    w = _nuovo_widget('TOUCH')
    w.show()
    _ridimensiona(w, 900, 160)
    minimo = w.minimumSizeHint()
    nome = 'x' * 200 + '.mp3'
    w.set_filename_text(nome)
    _pump(30)
    esito = (w.minimumSizeHint() == minimo, w.width(), w.filename_label.text())
    w.shutdown()
    assert esito[0] and esito[1] == 900, esito
    assert len(esito[2]) < len(nome), "nome non eliso"


def test_tempi_in_forma_breve_quando_non_entrano():
    from fluid_layout import LAYOUT_SPECS
    w = _nuovo_widget('TOUCH')
    w.show()
    _pump(400)  # il caricamento asincrono riscrive il tempo rimanente
    w._set_time_labels(5, 65)
    _ridimensiona(w, *LAYOUT_SPECS['TOUCH']['min'])
    stretto = (w.lblElapsedTime.text(), w.lblRemainingTime.text())
    _ridimensiona(w, 4000, 152)
    largo = (w.lblElapsedTime.text(), w.lblRemainingTime.text())
    w.shutdown()
    assert stretto == ('00:05', '-01:05'), stretto
    assert largo == ('Elapsed: 00:05', 'Remaining: 01:05'), largo


def test_etichette_brevi_in_tutti_i_layout():
    from mp3widget import WidgetLayout
    w = _nuovo_widget('TOUCH')
    w.show()
    _pump(400)  # il caricamento asincrono riscrive il tempo rimanente
    w._set_time_labels(5, 65)
    testi = {}
    for layout in WidgetLayout:
        w.set_layout(layout)
        _ridimensiona(w, 4000, 460)
        testi[layout.name] = w.lblRemainingTime.text()
    w.set_layout(WidgetLayout.STANDARD)
    _ridimensiona(w, 4000, 127)
    trascorso = w.lblElapsedTime.text()
    w.shutdown()
    assert all(t == 'Remaining: 01:05' for t in testi.values()), testi
    assert trascorso == 'Elapsed: 00:05', trascorso


def test_touch_pulsante_layout_accanto_a_norm():
    from fluid_layout import LAYOUT_SPECS
    spec = LAYOUT_SPECS['TOUCH']
    w = _nuovo_widget('TOUCH')
    w.show()
    misure = []
    for taglia in (spec['min'], spec['ref']):
        _ridimensiona(w, *taglia)
        misure.append((taglia, w.btnNorm.geometry().getRect(), w.btnChangeLayout.geometry().getRect()))
    w.shutdown()
    for taglia, norm, layout in misure:
        assert layout[1] == norm[1] and layout[3] == norm[3], (taglia, norm, layout)
        assert 0 <= layout[0] - (norm[0] + norm[2]) <= 8, (taglia, norm, layout)


def test_touch_tempi_leggibili_alla_larghezza_minima():
    # Il pulsante layout in seconda riga toglie spazio alle label: i tempi,
    # anche oltre i 100 minuti, devono entrare comunque.
    from fluid_layout import LAYOUT_SPECS
    w = _nuovo_widget('TOUCH')
    w.show()
    _ridimensiona(w, *LAYOUT_SPECS['TOUCH']['min'])
    misure = [(testo, label.fontMetrics().horizontalAdvance(testo), label.width())
              for label, testo in ((w.lblElapsedTime, '100:05'), (w.lblRemainingTime, '-100:05'))]
    w.shutdown()
    assert all(testo <= spazio for _, testo, spazio in misure), misure


def test_preset_fade_alti_come_norm():
    from fluid_layout import LAYOUT_SPECS
    from mp3widget import WidgetLayout
    w = _nuovo_widget('TOUCH')
    w.show()
    misure = []
    for nome in ('TOUCH', 'STANDARD'):  # gli unici layout con i preset
        spec = LAYOUT_SPECS[nome]
        w.set_layout(WidgetLayout[nome])
        for taglia in (spec['min'], spec['ref']):
            _ridimensiona(w, *taglia)
            misure.append((nome, taglia, w.btnNorm.height(),
                           [b.height() for b in (w.btnFadePreset1, w.btnFadePreset2, w.btnFadePreset3)]))
    w.shutdown()
    for nome, taglia, norm, preset in misure:
        assert all(abs(h - norm) <= 1 for h in preset), (nome, taglia, norm, preset)


def test_allineamenti_uguali_in_tutti_i_layout():
    from PySide6.QtCore import Qt
    from mp3widget import WidgetLayout
    w = _nuovo_widget('TOUCH')
    esiti = {}
    for layout in WidgetLayout:
        w.set_layout(layout)
        esiti[layout.name] = (
            w.filename_label.alignment(), w.lblElapsedTime.alignment(), w.lblRemainingTime.alignment(),
            w.lblVolume.alignment(),
            w.spinboxGain.alignment() & Qt.AlignHorizontal_Mask,
            w.spinboxFadeTime.alignment() & Qt.AlignHorizontal_Mask)
    w.shutdown()
    a_sinistra = Qt.AlignLeft | Qt.AlignVCenter
    atteso = (a_sinistra, a_sinistra, a_sinistra, Qt.AlignCenter, Qt.AlignHCenter, Qt.AlignRight)
    assert all(esito == atteso for esito in esiti.values()), esiti


def test_tempi_sempre_nella_stessa_forma():
    # Una larghezza intermedia faceva convivere "Elapsed: 00:00" e "-02:28".
    w = _nuovo_widget('DENSE_A')
    w.show()
    forme = []
    for larghezza in range(700, 4000, 20):
        _ridimensiona(w, larghezza, 46)
        forme.append(('Elapsed' in w.lblElapsedTime.text(), 'Remaining' in w.lblRemainingTime.text()))
    w.shutdown()
    assert all(a == b for a, b in forme), forme


def test_seek_corretto_dopo_il_resize():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    w = _nuovo_widget('TOUCH')
    w.show()
    _ridimensiona(w, 1500, 300)
    seek = []
    w.progress_bar.clicked.connect(seek.append)
    bar = w.progress_bar
    QTest.mouseClick(bar, Qt.LeftButton, Qt.NoModifier, QPoint(bar.width() // 4, bar.height() // 2))
    w.shutdown()
    assert seek and abs(seek[0] - 0.25) < 0.01, seek


def test_due_touch_entrano_nella_finestra_di_default():
    from mp3file import Mp3File
    from mp3widget import Mp3Widget
    import mainapp as MA
    _app()
    m = MA.MainApp()
    m.resize(1080, 600)
    widgets = [Mp3Widget(Mp3File(os.path.join(AUD, 'pink_panther.mp3'), backend='qt'))
               for _ in range(2)]
    for col, w in enumerate(widgets):
        m.mp3_widgets.append(w)
        m.grid_layout.addWidget(w, 0, col)
    m.grid_manager.update_column_stretches()
    _pump(100)
    scroll = m.centralWidget().horizontalScrollBar().maximum()
    alto = widgets[0].height()
    m.resize(1600, 900)
    _pump(100)
    cresciuto = (widgets[0].width(), widgets[0].height())
    for w in widgets:
        w.shutdown()
    m.mp3_widgets.clear()
    m.close()
    assert scroll == 0, f"scroll orizzontale {scroll}"
    assert cresciuto[1] > alto, (alto, cresciuto)


_TESTI_ENTRANO_SNIPPET = """
import os, sys
sys.path.insert(0, {src!r})
from PySide6.QtWidgets import QApplication, QAbstractButton, QAbstractSpinBox, QLabel, QToolButton
from PySide6.QtCore import Qt
from fluid_layout import LAYOUT_SPECS
from mp3file import Mp3File
from mp3widget import Mp3Widget, WidgetLayout
app = QApplication([])
w = Mp3Widget(Mp3File(os.path.join({aud!r}, 'pink_panther.mp3'), backend='qt'))
w.setAttribute(Qt.WA_DontShowOnScreen)
w.show()
errori = []
for L in WidgetLayout:
    w.set_layout(L)
    app.processEvents()  # fino all'attivazione vale il minimo del layout precedente
    w.resize(*LAYOUT_SPECS[L.name]['min'])
    for _ in range(5):
        app.processEvents()
    g = w.widget_file_frame_layout
    for i in range(g.count()):
        c = g.itemAt(i).widget()
        fm = c.fontMetrics()
        if isinstance(c, QToolButton) and not c.icon().isNull():
            continue  # solo icona: il testo non viene disegnato
        if isinstance(c, QAbstractButton) and c.text():
            icon = c.iconSize().width() + 4 if not c.icon().isNull() else 0
            need = fm.horizontalAdvance(c.text()) + icon + 4
        elif isinstance(c, QLabel) and c is not w.filename_label:
            need = fm.horizontalAdvance(c.text())
        elif isinstance(c, QAbstractSpinBox):
            need = fm.horizontalAdvance(c.text()) + 4
        else:
            continue
        if need > c.width():
            errori.append((L.name, c.text(), need, c.width()))
    # A ogni taglia le frecce di una spinbox non devono coprire il valore.
    ref = LAYOUT_SPECS[L.name]['ref']
    for taglia in (ref, (ref[0] * 3 // 2, ref[1] * 3 // 2)):
        w.resize(*taglia)
        for _ in range(5):
            app.processEvents()
        for spin in (w.spinboxFadeTime, w.spinboxGain):
            spazio = spin.width() - spin.fontMetrics().horizontalAdvance(spin.text())
            if spin.parent() is not None and spin.buttonSymbols() != QAbstractSpinBox.NoButtons and spazio < 67:
                errori.append((L.name, 'frecce', spin.text(), spin.width(), spazio))
w.shutdown()
print(errori)
sys.exit(1 if errori else 0)
"""


def test_testi_entrano_alla_dimensione_minima_su_font_reali():
    # Solo con le metriche font vere: offscreen i testi misurano molto di più.
    if sys.platform != 'win32':
        return
    env = dict(os.environ, QT_QPA_PLATFORM='windows')
    code = _TESTI_ENTRANO_SNIPPET.format(src=SRC, aud=AUD)
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                       timeout=60, env=env)
    assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-300:]


# ---------------------------------------------------------------------------
# DENSE_A = righe compatte, STRIP_A = channel strip da mixer: la griglia esterna
# non deve spaziare i widget che hanno una dimensione massima.
# ---------------------------------------------------------------------------
def _finestra(*layout_e_cella):
    from PySide6.QtWidgets import QFileDialog
    from mp3widget import WidgetLayout
    import mainapp as MA
    _app()
    m = MA.MainApp()
    m.resize(1500, 900)
    _pump(50)
    originale = QFileDialog.getOpenFileNames
    QFileDialog.getOpenFileNames = staticmethod(
        lambda *a, **k: ([os.path.join(AUD, 'pink_panther.mp3')] * len(layout_e_cella), ''))
    try:
        m.open_files()
    finally:
        QFileDialog.getOpenFileNames = originale
    for w, (layout, cella) in zip(m.mp3_widgets, layout_e_cella):
        m.grid_layout.removeWidget(w)
    for w, (layout, cella) in zip(m.mp3_widgets, layout_e_cella):
        m.grid_layout.addWidget(w, *cella)
        w.set_layout(WidgetLayout[layout])
    m.grid_manager.update_column_stretches()
    _pump(100)
    return m


def _chiudi(m):
    for w in m.mp3_widgets:
        w.shutdown()
    m.mp3_widgets.clear()
    m.close()


def test_righe_dense_impacchettate():
    m = _finestra(('DENSE_A', (0, 0)), ('DENSE_A', (1, 0)), ('DENSE_A', (2, 0)))
    geo = [w.geometry() for w in m.mp3_widgets]
    spazio = m.grid_layout.verticalSpacing()
    _chiudi(m)
    assert all(g.height() == 46 for g in geo), [g.height() for g in geo]
    salti = [geo[i + 1].y() - geo[i].bottom() - 1 for i in range(2)]
    assert salti == [spazio, spazio], salti


def test_dense_impacchettate_anche_con_tutte_le_righe_iniziali_occupate():
    m = _finestra(*[('DENSE_A', (r, 0)) for r in range(6)])
    geo = [w.geometry() for w in m.mp3_widgets]
    spazio = m.grid_layout.verticalSpacing()
    _chiudi(m)
    salti = [geo[i + 1].y() - geo[i].bottom() - 1 for i in range(5)]
    assert salti == [spazio] * 5, salti


def test_strip_affiancate_strette_e_alte():
    m = _finestra(('STRIP_A', (0, 0)), ('STRIP_A', (0, 1)), ('STRIP_A', (0, 2)))
    geo = [w.geometry() for w in m.mp3_widgets]
    spazio = m.grid_layout.horizontalSpacing()
    alto_finestra = m.height()
    m.resize(1500, 600)
    _pump(100)
    piu_bassa = m.mp3_widgets[0].height()
    _chiudi(m)
    assert all(g.width() <= 176 for g in geo), [g.width() for g in geo]
    salti = [geo[i + 1].x() - geo[i].right() - 1 for i in range(2)]
    assert salti == [spazio, spazio], salti
    assert geo[0].height() > alto_finestra * 0.75, (geo[0].height(), alto_finestra)
    assert piu_bassa < geo[0].height(), (piu_bassa, geo[0].height())


def test_cambio_layout_a_caldo_aggiorna_la_griglia():
    # Il widget deve avvisare la griglia: senza, la riga resta quella del layout
    # precedente fino alla prossima operazione su file o drag.
    from mp3widget import WidgetLayout
    m = _finestra(('TOUCH', (0, 0)))
    w = m.mp3_widgets[0]
    g = m.grid_layout
    w.set_layout(WidgetLayout.DENSE_A)
    compatta = g.rowStretch(0)
    w.set_layout(WidgetLayout.STRIP_A)
    mixer = (g.columnStretch(0), g.rowStretch(0))
    w.set_layout(WidgetLayout.TOUCH)
    normale = (g.columnStretch(0), g.rowStretch(0))
    _chiudi(m)
    assert compatta == 0, compatta
    assert mixer[0] == 0 and mixer[1] > 1, mixer
    assert normale == (1, 1), normale


def test_riga_compatta_rimossa_torna_drop_target():
    m = _finestra(('DENSE_A', (0, 0)), ('DENSE_A', (1, 0)))
    w = m.mp3_widgets[1]
    m.remove_widget(w)
    w.shutdown()
    w.setParent(None)
    stretch = m.grid_layout.rowStretch(1)
    _chiudi(m)
    assert stretch == 1, stretch


def test_griglia_invariata_senza_widget_limitati():
    m = _finestra(('TOUCH', (0, 0)), ('TOUCH', (0, 1)), ('STANDARD', (1, 0)))
    g = m.grid_layout
    esito = ([g.columnStretch(c) for c in range(g.columnCount())],
             [g.rowStretch(r) for r in range(2)], g.columnCount())
    _chiudi(m)
    assert esito == ([1, 1], [1, 1], 2), esito


def main():
    tests =[(n, o) for n, o in sorted(globals().items())
             if n.startswith('test_') and callable(o)]
    falliti = 0
    for name, fn in tests:
        try:
            fn()
            print(f'PASS  {name}')
        except unittest.SkipTest as e:
            print(f'SKIP  {name}: {e}')
        except Exception as e:
            falliti += 1
            print(f'FAIL  {name}\n      {type(e).__name__}: {e}')
    print(f'\n{len(tests) - falliti}/{len(tests)} verdi')
    return 1 if falliti else 0


if __name__ == '__main__':
    sys.exit(main())
