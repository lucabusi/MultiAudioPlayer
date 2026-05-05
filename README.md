# MultiPlayer

Un lettore audio multi-traccia con interfaccia grafica in Python, pensato per gestire e riprodurre più file MP3/audio contemporaneamente con controllo indipendente di volume, fade e posizione.

## Funzionalità

- Riproduzione simultanea di più file audio
- Controllo volume indipendente per ogni traccia
- Fade in/out configurabile (basato sul tempo trascorso)
- Visualizzazione waveform con barra di avanzamento cliccabile
- Normalizzazione del gain (peak e RMS)
- Drag & drop per riordinare le tracce nella griglia
- Salvataggio e caricamento del progetto
- Più layout di widget (Standard, Compact, Touch, Compact verticale)
- Backend audio: VLC (predefinito), mpv o GStreamer; fallback UI-only senza backend

## Requisiti

- Python 3.11+
- VLC installato nel sistema (consigliato)

## Installazione

```bash
pip install -r requirements.txt
```

Per l'output audio è necessario almeno uno dei backend:
- **VLC** (consigliato): installa [VLC](https://www.videolan.org/) e `pip install python-vlc`
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
| `waveform.py` | Generazione waveform |
| `waveform_service.py` | Servizio asincrono per il rendering della waveform |
| `grid_manager.py` | Gestione griglia widget con drag & drop |
| `project_manager.py` | Salvataggio/caricamento progetto |

## Dipendenze principali

```
PyQt5
numpy
soundfile
librosa
matplotlib
Pillow
python-vlc
```

## Licenza

Vedere [LICENSE](LICENSE).
