# MultiPlayer

Un lettore audio multi-traccia con interfaccia grafica in Python, pensato per gestire e riprodurre più file MP3/audio contemporaneamente con controllo indipendente di volume, fade e posizione.

![Python](https://img.shields.io/badge/python-3.7%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Piattaforma](https://img.shields.io/badge/piattaforma-Windows%20%7C%20Linux-lightgrey)



## Funzionalità

- Riproduzione simultanea di più file audio
- Controllo volume indipendente per ogni traccia
- Fade in/out configurabile (basato sul tempo trascorso)
- Visualizzazione waveform con barra di avanzamento cliccabile
- Normalizzazione del gain (peak)
- Drag & drop per riordinare le tracce nella griglia
- Salvataggio e caricamento del progetto
- Più layout di widget (Standard, Compact, Touch, Compact verticale)
- Backend audio: QMediaPlayer (`qt`, predefinito — integrato in PyQt5, nessuna installazione extra), VLC, mpv o GStreamer; fallback UI-only senza backend

## Requisiti

- Python 3.11+
- Nessun player esterno: il backend predefinito (`qt`) è incluso in PyQt5.
  VLC/mpv/GStreamer servono solo se scegli quei backend.

## Installazione

```bash
pip install -r requirements.txt
```

Per l'output audio è necessario almeno uno dei backend:
- **QMediaPlayer** (`qt`, predefinito): nessuna installazione extra — usa
  PyQt5.QtMultimedia (WMF/DirectShow su Windows, GStreamer su Linux).
  Volume software per-player e curva percettiva.
- **VLC**: installa [VLC](https://www.videolan.org/) e `pip install python-vlc`
- **mpv**: installa mpv e `pip install python-mpv`
- **GStreamer**: installa `PyGObject` e i plugin gstreamer di sistema

Il backend si sceglie in `MultiPlayer/mainapp.py` (attributo `self.backend`).
Se quello scelto non è disponibile si ripiega su `_StubBackend`: la UI resta
funzionante ma senza audio.

## Avvio

```bash
python MultiPlayer/MultiPlayer.py
```

La versione applicativa è in `MultiPlayer/constants.py` (`APP_VERSION`) e
compare nel titolo della finestra.

## Test

Test di regressione sui bug già corretti: girano offscreen, senza finestre e
senza device audio, usando i file di `audio_test/`.

```bash
python tests/test_regressions.py     # runner autonomo
pytest tests/                        # oppure via pytest
```

## Struttura del progetto

| Percorso | Descrizione |
|---|---|
| `MultiPlayer/` | Codice sorgente dell'applicazione |
| `MultiPlayer/MultiPlayer.py` | Entry point |
| `MultiPlayer/mainapp.py` | Finestra principale e gestione layout |
| `MultiPlayer/mp3widget.py` | Widget per singolo file audio |
| `MultiPlayer/mp3file.py` | Wrapper backend audio (play/stop/volume/fade) |
| `MultiPlayer/waveform.py` | Decode audio, envelope (con cache) e rendering waveform |
| `MultiPlayer/waveform_service.py` | Servizio asincrono per la waveform (decode in thread, re-render su gain) |
| `MultiPlayer/grid_manager.py` | Gestione griglia widget con drag & drop |
| `MultiPlayer/project_manager.py` | Salvataggio/caricamento progetto |
| `MultiPlayer/constants.py` | Versione applicativa e costanti condivise (timing, dimensioni waveform) |
| `MultiPlayer/thread_registry.py` | Tiene vivi i QThread in volo senza wait() bloccanti |
| `tests/` | Test di regressione (offscreen, senza audio) |
| `audio_test/` | File MP3 di test e prova |
| `benchmarks/` | Benchmark (decode, envelope, rendering) |
| `docs/` | Documentazione e stato del progetto |
| `projects/` | Progetti `.mpp` di esempio |

## Dipendenze principali

```
PyQt5            # GUI + backend audio predefinito (QtMultimedia)
numpy
soundfile
librosa
Pillow
python-vlc       # opzionale, solo per il backend 'vlc'
```

## Licenza

MIT — vedere [LICENSE](LICENSE).
