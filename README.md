# MultiPlayer

Lettore audio **multi-traccia** con interfaccia grafica in Python (PyQt5), pensato per la
regia audio di spettacoli teatrali: più cue caricate insieme in una griglia, ognuna con
play/stop, fade, volume e gain indipendenti.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Piattaforma](https://img.shields.io/badge/piattaforma-Windows%20%7C%20Linux-lightgrey)

## Perché esiste

In uno spettacolo le cue audio devono partire al momento esatto, spesso sovrapposte, con
dissolvenze decise dal vivo. I player generalisti sono a coda singola e non danno controllo
simultaneo su più tracce. MultiPlayer mette ogni file in un widget indipendente dentro una
griglia riordinabile, così l'operatore ha davanti tutta la scaletta e può agire su qualsiasi
traccia in qualsiasi momento.

## Funzionalità

- Riproduzione simultanea di più file audio, ognuno con backend indipendente
- Volume e gain separati per traccia, con normalizzazione automatica a picco
- Fade in/out lineari a durata configurabile, con preset rapidi
- Waveform di sfondo alla progress bar, con seek al click
- Griglia con drag & drop per riordinare le tracce
- Quattro layout per widget: Touch, Standard, Compact, Compact-V (stile mixer)
- Salvataggio e caricamento del progetto in formato `.mpp`
- Backend audio intercambiabili: QMediaPlayer (default, nessuna installazione extra),
  VLC, mpv o GStreamer — con fallback UI-only se nessuno è disponibile

## Requisiti

- Python 3.10+
- Windows o Linux
- Nessun player esterno obbligatorio: il backend predefinito è incluso in PyQt5

## Installazione e avvio

```bash
git clone https://github.com/lucabusi/MultiAudioPlayer.git
cd MultiAudioPlayer
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python MultiPlayer/MultiPlayer.py
```

## Documentazione

Guida all'uso, configurazione, formato progetto, backend e risoluzione problemi:
**[user_manual.md](user_manual.md)**.

## Architettura in breve

```
MultiPlayer.py  →  mainapp.MainApp (QMainWindow)
                     ├── GridManager       posizionamento e drag & drop
                     ├── ProjectManager    serializzazione .mpp
                     ├── AudioWarmup       anti-latenza del primo play
                     ├── QTimer 50 ms      poll globale della UI
                     └── Mp3Widget[]       un widget per traccia
                           ├── Mp3File            volume, gain, fade, stato
                           │     └── backend      qt | vlc | mpv | gstreamer | stub
                           └── WaveformService    envelope in thread, render su gain
```

Decodifica, analisi del picco e calcolo della waveform girano sempre in thread separati: il
main thread non fa mai lavoro pesante. Un errore su una traccia viene segnalato sul suo widget
senza fermare le altre.

## Struttura del progetto

| Percorso | Descrizione |
|---|---|
| `MultiPlayer/` | Codice sorgente dell'applicazione |
| `tests/` | Test di regressione (offscreen, senza device audio) |
| `audio_test/` | File MP3 di prova per test e benchmark |
| `benchmarks/` | Benchmark di decode, envelope e rendering |
| `docs/` | Note di architettura e piani implementativi |
| `MultiPlayer.spec` | Specifica PyInstaller |

## Sviluppo

```bash
python tests/test_regressions.py   # test di regressione (o: pytest tests/)
pyinstaller MultiPlayer.spec       # build eseguibile
```

## Licenza

MIT — Copyright (c) 2023-2026 Luca Busi. Vedere [LICENSE](LICENSE).
