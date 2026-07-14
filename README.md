# MultiPlayer

Un lettore audio multi-traccia con interfaccia grafica in Python, pensato per gestire e riprodurre più file MP3/audio contemporaneamente con controllo indipendente di volume, fade e posizione.

## Funzionalità

- Riproduzione simultanea di più file audio
- Controllo volume indipendente per ogni traccia
- Fade in/out configurabile (basato sul tempo trascorso)
- Visualizzazione waveform con barra di avanzamento cliccabile
- Normalizzazione del gain (peak)
- Drag & drop per riordinare le tracce nella griglia
- Salvataggio e caricamento del progetto
- Più layout di widget (Standard, Compact, Touch, Compact verticale)
- Backend audio: VLC (predefinito), QMediaPlayer (`qt`, integrato in PyQt5 — nessuna installazione extra), mpv o GStreamer; fallback UI-only senza backend

## Requisiti

- Python 3.11+
- VLC installato nel sistema (consigliato)

## Installazione

```bash
pip install -r requirements.txt
```

Per l'output audio è necessario almeno uno dei backend:
- **QMediaPlayer** (`qt`): nessuna installazione extra — usa PyQt5.QtMultimedia
  (WMF/DirectShow su Windows, GStreamer su Linux). Volume con curva percettiva.
- **VLC** (predefinito): installa [VLC](https://www.videolan.org/) e `pip install python-vlc`
- **mpv**: installa mpv e `pip install python-mpv`
- **GStreamer**: installa `PyGObject` e i plugin gstreamer di sistema

## Avvio

```bash
python MultiPlayer/MultiPlayer.py
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
| `MultiPlayer/constants.py` | Costanti condivise (timing, dimensioni waveform) |
| `MultiPlayer/thread_registry.py` | Tiene vivi i QThread in volo senza wait() bloccanti |
| `audio_test/` | File MP3 di test e prova |
| `benchmarks/` | Benchmark (decode, envelope, rendering) |
| `docs/` | Documentazione e stato del progetto |
| `projects/` | Progetti `.mpp` di esempio |

## Dipendenze principali

```
PyQt5
numpy
soundfile
librosa
Pillow
python-vlc
```

## Licenza

Vedere [LICENSE](LICENSE).
