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
python MultiPlayer.py
```

## Struttura del progetto

| File | Descrizione |
|---|---|
| `MultiPlayer.py` | Entry point |
| `mainapp.py` | Finestra principale e gestione layout |
| `mp3widget.py` | Widget per singolo file audio |
| `mp3file.py` | Wrapper backend audio (play/stop/volume/fade) |
| `waveform.py` | Decode audio, envelope (con cache) e rendering waveform |
| `waveform_service.py` | Servizio asincrono per la waveform (decode in thread, re-render su gain) |
| `grid_manager.py` | Gestione griglia widget con drag & drop |
| `project_manager.py` | Salvataggio/caricamento progetto |
| `constants.py` | Costanti condivise (timing, dimensioni waveform) |
| `thread_registry.py` | Tiene vivi i QThread in volo senza wait() bloccanti |

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
