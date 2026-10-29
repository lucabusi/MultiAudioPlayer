"""Servizio globale di sessione: tiene sveglio l'endpoint audio.

Non ha nulla a che vedere con il singolo file audio (`mp3file.py`): è un
servizio applicativo istanziato una volta da `MainApp` e fermato alla
chiusura.
"""
import logging

from PySide6.QtCore import QObject, QTimer

logger = logging.getLogger(__name__)


class AudioWarmup(QObject):
    """Tiene aperto l'endpoint audio con uno stream di silenzio continuo.

    Su Windows il primo stream dopo che il dispositivo è andato in idle
    (tipico: HDMI, Bluetooth, USB) impiega 1-2 secondi ad aprirsi e l'inizio
    della traccia va perso — inaccettabile per una cue teatrale. Uno stream
    PCM di zeri (CPU trascurabile, via QAudioSink di Qt6) mantiene la
    sessione WASAPI e l'endpoint attivi per tutta la durata della sessione.

    Se il dispositivo audio non è disponibile fallisce in silenzio: è solo
    un'ottimizzazione, la riproduzione vera non dipende da questo oggetto.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._out = None
        self._io = None
        self._timer = None
        try:
            from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
            device = QMediaDevices.defaultAudioOutput()
            if device.isNull():
                raise RuntimeError('nessun device audio di output')
            # 8 kHz mono: il minimo che tiene aperta la sessione — il mixer
            # di sistema resample, a noi interessa solo che l'endpoint resti
            # attivo. Non tutti i device lo accettano in Qt6 (verificato:
            # Realtek no): in quel caso si usa il formato nativo del device.
            fmt = QAudioFormat()
            fmt.setSampleRate(8000)
            fmt.setChannelCount(1)
            fmt.setSampleFormat(QAudioFormat.Int16)
            if not device.isFormatSupported(fmt):
                fmt = device.preferredFormat()
            self._out = QAudioSink(device, fmt, self)
            self._out.setBufferSize(fmt.bytesForDuration(2_000_000))  # ~2s di margine
            self._io = self._out.start()  # push mode
            if self._io is None:
                raise RuntimeError('QAudioSink.start() ha restituito None')
            # Silenzio = byte a zero per tutti i formati PCM interi/float.
            self._silence = bytes(fmt.bytesForDuration(500_000))  # 0.5 s per feed
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._feed)
            self._timer.start(250)
            self._feed()
            logger.info('audio warmup attivo (stream di silenzio)')
        except Exception as exc:
            logger.warning(f'audio warmup non disponibile: {exc}')
            self.stop()

    def _feed(self):
        if self._io is None or self._out is None:
            return
        try:
            free = self._out.bytesFree()
            while free >= len(self._silence):
                self._io.write(self._silence)
                free -= len(self._silence)
        except Exception as exc:
            logger.warning(f'audio warmup interrotto: {exc}')
            self.stop()

    def stop(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self._out is not None:
            try:
                self._out.stop()
            except Exception:
                pass
            self._out = None
        self._io = None
