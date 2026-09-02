# MultiPlayer — Manuale utente

Guida operativa completa. Per la panoramica del progetto vedere il [README](README.md).

## Indice

- [Installazione](#installazione)
- [Avvio](#avvio)
- [Interfaccia](#interfaccia)
- [Guida all'uso](#guida-alluso)
- [Controlli del widget](#controlli-del-widget)
- [Layout dei widget](#layout-dei-widget)
- [Volume, gain e normalizzazione](#volume-gain-e-normalizzazione)
- [Dissolvenze](#dissolvenze)
- [Waveform](#waveform)
- [Gestione della griglia](#gestione-della-griglia)
- [Progetti `.mpp`](#progetti-mpp)
- [Backend audio](#backend-audio)
- [Configurazione avanzata](#configurazione-avanzata)
- [Test](#test)
- [Benchmark](#benchmark)
- [Build eseguibile](#build-eseguibile)
- [Risoluzione problemi](#risoluzione-problemi)
- [Limiti noti](#limiti-noti)

---

## Installazione

Requisiti: **Python 3.10+** (il codice usa la sintassi `X | Y` nelle annotazioni e i generics
builtin), **Windows o Linux**.

```bash
git clone https://github.com/lucabusi/MultiAudioPlayer.git
cd MultiAudioPlayer
python -m venv venv
# Windows:  venv\Scripts\activate
# Linux:    source venv/bin/activate
pip install -r requirements.txt
```

Dipendenze installate:

| Pacchetto | Ruolo |
|---|---|
| `PyQt5` | GUI + backend audio predefinito (`QtMultimedia`) |
| `numpy` | Calcolo envelope della waveform |
| `soundfile` | Decodifica audio nativa (libsndfile) |
| `Pillow` | Rendering della waveform in JPEG |
| `librosa` | Fallback di decodifica per formati non gestiti da libsndfile (AAC, WMA, ALAC…) |
| `python-vlc` | *Opzionale* — solo per il backend `vlc` |

Nessun player esterno è obbligatorio: il backend predefinito (`qt`) è incluso in PyQt5.
VLC, mpv e GStreamer servono solo se si sceglie esplicitamente quel backend.

---

## Avvio

```bash
python MultiPlayer/MultiPlayer.py
```

Su Linux/macOS è disponibile anche lo script di comodo:

```bash
./MultiPlayer.sh
```

La versione applicativa (`APP_VERSION` in `MultiPlayer/constants.py`) compare nel titolo della
finestra.

---

## Interfaccia

La finestra è composta da:

- **Barra menu** — `File` (Open MP3 Files, Save Project, Load Project, Exit) e
  `Strumenti` (Normalize All)
- **Griglia scorrevole** — 5 righe × 2 colonne all'avvio, espandibile fino a 20 righe.
  Ogni cella ospita al massimo un widget-traccia; le celle vuote restano visibili come
  bersaglio di drop.

---

## Guida all'uso

1. **Caricare le tracce** — `File → Open MP3 Files`, selezione multipla consentita. Ogni file
   occupa la prima cella libera della griglia.
2. **Riordinare** — trascinare un widget su un'altra cella. Se la destinazione è occupata, il
   widget che c'era viene spostato nella cella libera più vicina.
3. **Regolare i livelli** — slider per il volume, spinbox `G:` per il gain, `Norm` per la
   normalizzazione automatica.
4. **Impostare le dissolvenze** — spinbox del tempo di fade (o preset 1/3/5), poi `FadeIn` o
   `Fade Out`.
5. **Cambiare layout** — il pulsante con l'icona a destra apre il menu dei quattro layout,
   impostabile per singola traccia.
6. **Salvare** — `File → Save Project` produce un `.mpp` con file, posizioni, volumi, gain,
   tempi di fade, layout e geometria della finestra.

Alla chiusura, se ci sono tracce aperte, viene chiesto se salvare; annullando il salvataggio la
chiusura viene interrotta invece di perdere il lavoro.

---

## Controlli del widget

| Controllo | Funzione |
|---|---|
| `Play/Pause` | Avvia o mette in pausa. A fine traccia riparte dall'inizio. La pausa manuale interrompe un fade in corso e riallinea il volume allo slider |
| `Stop` | Ferma e riporta a inizio traccia |
| `FadeIn` | Parte da volume 0 e sale fino al valore dello slider nel tempo impostato |
| `Fade Out` | Scende dal volume corrente a 0, poi ferma la traccia |
| Spinbox fade | Durata della dissolvenza, 0–10 s, passo 0,5 s |
| `1` `3` `5` | Preset rapidi del tempo di fade |
| Slider volume | Volume 0–100 |
| Spinbox `G:` | Gain 0,00–5,00, passo 0,05 |
| `Norm` | Normalizzazione a picco della traccia |
| `Remove` | Rimuove la traccia dalla griglia |
| Pulsante layout | Menu di scelta del layout del widget |
| Progress bar | Click per fare seek nel punto corrispondente |

I bottoni cambiano colore per segnalare lo stato: riproduzione in corso, fade in attivo,
fade out attivo.

---

## Layout dei widget

Ogni traccia può usare un layout diverso, scelto dal menu del pulsante in alto a destra del
widget. Il layout viene salvato nel progetto.

| Layout | Descrizione |
|---|---|
| `TOUCH` (default) | Bottoni grandi, fader verticale a destra, 4 righe — touchscreen e tablet |
| `STANDARD` | Tutti i controlli compatti su 3 righe, slider orizzontale — mouse e tastiera |
| `COMPACT` | Solo Play/Stop, nome file, tempo e volume su 2 righe — playlist dense |
| `COMPACT_V` | Canale verticale stile mixer, fader alto, senza progress bar né waveform |

---

## Volume, gain e normalizzazione

Il volume udibile è il prodotto **`volume slider × gain`**, clampato tra 0 e 100. I due
controlli hanno ruoli distinti: lo slider è la regolazione operativa dal vivo, il gain è la
compensazione fissa del livello del file.

**Normalizzazione a picco.** Il pulsante `Norm` avvia in background l'analisi del file e calcola
il gain che porta il picco massimo a 1.0. Il picco è misurato su tutti i canali, non sul downmix
mono: mediare i canali può cancellare i picchi (segnali in controfase) e produrre un gain troppo
alto, con clipping in riproduzione.

`Strumenti → Normalize All` esegue la stessa operazione su tutte le tracce aperte, in parallelo.

**Comportamento al cambio di gain.** Modificando il gain, il volume dello slider viene
ricalcolato per lasciare **invariato il volume udibile**: se lo slider è a 100 con gain 1.0 e la
normalizzazione porta il gain a 2.0, lo slider scende a 50. Fa eccezione il gain nullo: in quel
caso lo slider resta dov'è, altrimenti tornando a gain 1.0 la traccia resterebbe muta.

---

## Dissolvenze

Le rampe sono lineari e la durata è impostabile tra 0 e 10 secondi.

- Il **fade in** silenzia la traccia prima di avviarla, così non si sente un burst iniziale,
  poi sale fino al valore dello slider. È un no-op se la traccia è già in riproduzione.
- Il **fade out** scende dal volume corrente a 0, ferma la traccia e ripristina il volume di
  partenza come valore memorizzato per il play successivo. È un no-op se la traccia non è in
  riproduzione.
- Qualsiasi interruzione (stop, pausa, nuovo fade) lascia volume e slider coerenti tra loro.
- Il progresso è calcolato sul tempo reale trascorso, non sul numero di tick: se il sistema
  rallenta, il fade recupera invece di dilatarsi.

---

## Waveform

La forma d'onda del file è disegnata come sfondo della progress bar, con un overlay verde che
indica l'avanzamento. Il calcolo avviene in un thread separato: finché non è pronta, la barra
mostra un fondo piatto.

L'envelope min/max viene **cachato su disco** in `.npz`, nella cartella
`mp3player_waveforms` dentro la directory temporanea di sistema. La chiave di cache include
percorso, data di modifica e dimensione del file, quindi sostituire il file invalida
automaticamente la cache.

Cambiando il gain la waveform viene ri-renderizzata senza ridecodificare l'audio, con un
debounce di 300 ms per assorbire le raffiche dello spinbox.

---

## Gestione della griglia

- La griglia parte con 5 righe × 2 colonne e cresce fino a un massimo di **20 righe**.
- I nuovi file occupano la prima cella libera in ordine riga-colonna.
- **Drag & drop**: tutto il corpo del widget è maniglia di trascinamento, tranne bottoni,
  slider, spinbox e progress bar, che continuano a ricevere il click normalmente. Durante il
  trascinamento la cella di destinazione viene evidenziata in verde.
- Se si rilascia su una cella occupata, il widget che vi si trovava viene spostato nella cella
  libera più vicina; se non ce ne sono, il drop viene annullato.
- Le colonne occupate si espandono, quelle vuote restano visibili con una larghezza minima come
  bersaglio di drop.
- A griglia piena, l'apertura di nuovi file viene rifiutata con un avviso.

---

## Progetti `.mpp`

Il progetto è un file JSON con schema versionato (attualmente `1.2`, indipendente dalla versione
dell'applicazione).

```json
{
    "version": "1.2",
    "saved_date": "2026-07-04 21:15:03",
    "window_state": { "x": 100, "y": 100, "width": 1080, "height": 600 },
    "grid_state": { "rows": 5, "cols": 2 },
    "files": [
        {
            "file_path": "/percorso/assoluto/sigla.mp3",
            "volume": 85,
            "fade_time": 3.0,
            "gain": 1.42,
            "layout": "TOUCH",
            "row": 0,
            "col": 1
        }
    ]
}
```

Note sul comportamento:

- **Caricamento best-effort**: i campi mancanti vengono ignorati e i progetti di versioni diverse
  vengono comunque aperti, con un avviso nei log.
- **File non trovati**: raccolti e segnalati in un unico messaggio finale, non un popup per file
  — un progetto spostato tra macchine può avere decine di percorsi rotti.
- **Celle mancanti, duplicate o fuori griglia**: il widget viene ricollocato nella prima cella
  libera, così due tracce non finiscono sovrapposte.
- **Volume salvato**: è quello dello slider, non il volume istantaneo, quindi salvare a metà di
  un fade non congela il valore della rampa.
- **Geometria finestra**: ripristinata ma limitata all'area utile dello schermo, per evitare che
  un progetto salvato su un altro monitor apra la finestra fuori campo.
- I percorsi sono **assoluti**: spostando i file audio, il progetto va rifatto o modificato a mano.

---

## Backend audio

L'output audio è astratto dietro un'interfaccia comune, con quattro implementazioni più un
fallback.

| Nome | Requisiti | Note |
|---|---|---|
| `qt` **(default)** | Nessuno, incluso in PyQt5 | `QMediaPlayer`. Su Windows usa WMF/DirectShow, su Linux GStreamer. Volume software per-player con curva percettiva logaritmica |
| `vlc` | VLC di sistema + `pip install python-vlc` | |
| `mpv` | mpv di sistema + `pip install python-mpv` | |
| `gstreamer` (alias `gst`) | `PyGObject` + plugin GStreamer di sistema | |
| *stub* | — | Fallback automatico: simula la riproduzione avanzando un timer. La UI resta pienamente funzionante ma **senza audio** |

Il backend si sceglie in `MultiPlayer/mainapp.py`, attributo `self.backend` della classe
`MainApp`:

```python
self.backend = 'qt'   # 'vlc' | 'qt' | 'gstreamer' | 'mpv'
```

Se la libreria scelta non è disponibile, l'applicazione ripiega automaticamente sullo stub e lo
segnala nei log, invece di terminare.

---

## Configurazione avanzata

Costanti regolabili in `MultiPlayer/constants.py`:

| Costante | Default | Effetto |
|---|---|---|
| `APP_VERSION` | `3.1.0` | Versione mostrata nel titolo |
| `PROGRESS_BAR_HEIGHT` | `48` px | Altezza della progress bar/waveform |
| `POLL_INTERVAL_MS` | `50` | Periodo del poll globale della UI (20 Hz) |
| `FADE_TICK_MS` | `100` | Passo di aggiornamento del volume durante un fade |
| `FADE_STARTUP_DELAY_MS` | `100` | Attesa tra l'avvio e l'inizio del fade in |
| `WAVEFORM_DEBOUNCE_MS` | `300` | Debounce del re-render waveform al cambio gain |
| `WAVEFORM_WIDTH` / `WAVEFORM_HEIGHT` | `1500` × `75` | Risoluzione del rendering waveform |

Altri punti di configurazione:

- `MainApp.backend` — backend audio
- `MainApp.initial_rows` / `initial_cols` — dimensione iniziale della griglia
- `grid_manager.MAX_ROWS` — limite massimo di righe (20)

---

## Test

La suite è composta da **test di regressione**: ogni test corrisponde a un difetto realmente
osservato e corretto. Girano offscreen, senza finestre né device audio, usando i file di
`audio_test/`.

```bash
python tests/test_regressions.py     # runner autonomo
pytest tests/                        # oppure via pytest
```

---

## Benchmark

Tre script di misura usati per motivare le scelte di implementazione (decoder, downmix,
strategia di envelope):

```bash
python benchmarks/bench_decode.py     # soundfile full-load vs streaming vs miniaudio
python benchmarks/bench_envelope.py   # strategie di calcolo envelope
python benchmarks/bench_render.py     # rendering della waveform
```

Alcuni richiedono dipendenze extra non incluse in `requirements.txt` (es. `miniaudio`,
`matplotlib`).

---

## Build eseguibile

È incluso uno spec PyInstaller con i moduli locali e gli import lazy già dichiarati:

```bash
pip install pyinstaller
pyinstaller MultiPlayer.spec
```

Il binario esce in `dist/MultiPlayer`. Per vedere i log a runtime, impostare `console=True`
nello spec.

---

## Risoluzione problemi

**L'interfaccia funziona ma non si sente nulla.**
Il backend scelto non è disponibile e l'applicazione ha ripiegato sullo stub. Controllare i log
all'avvio: compare un avviso con il motivo. Verificare l'installazione del backend, o tornare al
default `qt`.

**Il primo play parte in ritardo.**
All'avvio l'applicazione attiva uno stream di silenzio (*audio warmup*) proprio per evitarlo: su
uscite HDMI, Bluetooth o USB il primo stream dopo un periodo di inattività può impiegare 1–2
secondi ad aprirsi. Se il warmup non riesce ad attivarsi lo segnala nei log senza bloccare
l'applicazione.

**Una traccia mostra un errore e i controlli sono disattivati.**
Il file non è riproducibile dal backend corrente (formato non supportato, tag ID3 malformato,
file corrotto). Le altre tracce continuano a funzionare normalmente.

**Il seek non ha effetto mentre la traccia è in pausa.**
Quirk noto del backend `qt` con DirectShow su Windows: il seek richiesto in pausa può essere
applicato solo alla ripresa della riproduzione. In riproduzione è affidabile.

**La waveform resta piatta.**
Il calcolo è ancora in corso, oppure la decodifica è fallita. Nel secondo caso compare un avviso
nei log; l'audio continua comunque a funzionare.

**Un progetto caricato segnala file mancanti.**
I percorsi salvati sono assoluti. Se i file audio sono stati spostati, vanno ricaricati a mano o
il `.mpp` va modificato con i nuovi percorsi.

---

## Limiti noti

- **Solo MP3 dal dialog.** Il file dialog filtra `*.mp3`; il resto della pipeline gestisce anche
  altri formati, ma non sono selezionabili dall'interfaccia.
- **Griglia limitata a 20 righe.** Raggiunto il limite i nuovi file vengono rifiutati, e i
  widget in eccesso caricati da progetto vengono scartati con un avviso.
- **Percorsi assoluti nei progetti.** Un `.mpp` spostato su un'altra macchina segnala i file
  mancanti ma non li ricerca.
- **Nessun controllo remoto.** L'integrazione OSC è allo stato di studio in
  `docs/OSC_integration_report.md`, non implementata.
- **Nessuna scorciatoia da tastiera** per play/stop delle singole cue.
- **Seek in pausa** non affidabile sul backend `qt` con DirectShow (Windows).
