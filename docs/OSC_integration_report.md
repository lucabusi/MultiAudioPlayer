# Report — Valutazione integrazione OSC (Open Sound Control 1.0) client/server

**Data:** 2026-05-10
**Autore:** Analisi codice esistente
**Scope:** Aggiungere supporto OSC bidirezionale a MultiPlayer (server per ricezione comandi remoti, client per notifica stato verso sistemi esterni).
**Riferimento spec:** [OSC 1.0](https://opensoundcontrol.stanford.edu/spec-1_0.html)

---

## 1. Sintesi esecutiva

L'aggiunta di OSC è **fattibile a costo medio** (stima MVP 3–4 giornate, integrazione robusta 8–12 giornate). Il codice è già ben strutturato per l'innesto: la separazione tra `Mp3File` (logica audio) e `Mp3Widget` (UI), e l'uso pervasivo di **segnali Qt** per gli eventi di playback, offrono punti di aggancio puliti sia per i comandi in ingresso (server) sia per le notifiche in uscita (client).

I rischi principali **non sono tecnologici** ma di design:
1. **Schema di indirizzamento delle tracce** (indici instabili a causa di drag&drop / remove).
2. **Threading**: il server OSC gira su un thread proprio, i comandi vanno marshallati sul main thread Qt.
3. **Stato condiviso** durante operazioni concorrenti (es. fade in corso + comando OSC che cambia volume).

---

## 2. Architettura proposta

### 2.1 Libreria
**Raccomandazione:** [`python-osc`](https://pypi.org/project/python-osc/) (modulo `pythonosc`).
- Pure Python, MIT, attivamente mantenuta.
- Supporta UDP + (sperimentale) TCP/SLIP.
- Implementa pattern matching OSC 1.0 (`*`, `?`, `[]`, `{}`).
- Supporta bundle con timetag.
- Server async (`AsyncIOOSCUDPServer`), threading (`ThreadingOSCUDPServer`), blocking (`BlockingOSCUDPServer`).

Alternativa: `oscpy` (più veloce, meno feature). Sconsigliato per spec 1.0 completa.

### 2.2 Nuovo modulo `osc_service.py`
Singleton legato a `MainApp`. Responsabilità:
- Avvio/arresto server UDP su porta configurabile (default 9000).
- Avvio client UDP verso host:porta destinazione (default 9001).
- Mapping bidirezionale `address pattern ↔ azione su widget/file`.
- Marshalling delle callback dal thread del server al main thread Qt
  (via `QMetaObject.invokeMethod` con `Qt.QueuedConnection` o segnali Qt).

### 2.3 Schema indirizzi proposto

Indirizzo **stabile per traccia** basato su uno **slot ID** (riga/colonna o UUID stabile, vedi §4.1):

```
# Globali
/mp3player/transport/play_all              ; nessun arg
/mp3player/transport/stop_all              ; nessun arg
/mp3player/normalize_all                   ; nessun arg
/mp3player/project/save        s           ; path
/mp3player/project/load        s           ; path

# Per traccia (ID = slot stabile o indice)
/mp3player/track/{id}/play                 ; toggle play/pause
/mp3player/track/{id}/stop
/mp3player/track/{id}/volume    f          ; 0.0..1.0
/mp3player/track/{id}/gain      f          ; 0.0..5.0
/mp3player/track/{id}/position  f          ; 0.0..1.0 (seek)
/mp3player/track/{id}/fade_in   f          ; durata in secondi
/mp3player/track/{id}/fade_out  f          ; durata in secondi
/mp3player/track/{id}/normalize
/mp3player/track/{id}/load      s          ; carica nuovo file in slot

# Wildcard supportati dalla spec (es. tutte le tracce in colonna 0)
/mp3player/track/*/stop
/mp3player/track/[0-3]/play
```

### 2.4 Notifiche client (in uscita)

Sfruttando i segnali già esistenti in [mp3file.py:518-525](mp3file.py#L518-L525):

| Segnale Qt esistente | Messaggio OSC emesso |
|---|---|
| `playback_state_changed(str)` | `/mp3player/track/{id}/state s` |
| `fade_in_started` | `/mp3player/track/{id}/fade_in/started` |
| `fadeInFinished` | `/mp3player/track/{id}/fade_in/finished` |
| `fadeOutFinished` | `/mp3player/track/{id}/fade_out/finished` |
| `normalize_ready(float)` | `/mp3player/track/{id}/gain f` |
| `loaded` / `load_error(str)` | `/mp3player/track/{id}/loaded` / `.../error s` |
| `_tick_progress` ([mainapp.py:102](mainapp.py#L102)) | `/mp3player/track/{id}/position f` (rate-limited) |

---

## 3. Parti del codice da modificare

| File | Tipo modifica | Descrizione |
|---|---|---|
| **`osc_service.py`** *(nuovo)* | Nuovo file | Server + client OSC, dispatcher, mapping address→callback. |
| [`__init__.py`](__init__.py) | Aggiunta costanti | `OSC_DEFAULT_RX_PORT`, `OSC_DEFAULT_TX_HOST`, `OSC_DEFAULT_TX_PORT`, `OSC_PROGRESS_RATE_HZ`. |
| [`mainapp.py`](mainapp.py) | Modifica `MainApp.__init__` e `init_ui` | Istanziare `OscService`, registrare handlers globali, aggiungere menu "OSC Settings", chiamare `osc.start()/stop()` in close. Track ID assignment al `open_files`/`load_project`. |
| [`mp3file.py`](mp3file.py) | Nessuna modifica strutturale | I segnali esistenti sono già sufficienti. Eventuale aggiunta di `track_id` come attributo. |
| [`mp3widget.py`](mp3widget.py) | Aggiunta minore | Espose un `track_id` stabile (non l'indice nella griglia). Forward dei segnali a `OscService` (alternativa: collegamento diretto in `MainApp`). |
| [`project_manager.py`](project_manager.py) | Schema progetto | Salvare `track_id` per ogni file nel `.mpp`. Bumpare `CURRENT_VERSION` a `'1.3'`, aggiungere migrazione che assegna ID a file vecchi. |
| [`requirements.txt`](requirements.txt) | Aggiunta dipendenza | `python-osc>=1.8`. |
| [`README.md`](README.md) | Aggiornamento doc | Sezione "OSC Control" con tabella indirizzi e configurazione. |
| `tests/` *(nuovo)* | Test isolati | Mock OSC client che invia comandi, assert sullo stato di `Mp3File` (stub backend). |

**Stima righe codice nuove:** ~600–800 (servizio + UI settings + test).
**Modifiche a codice esistente:** ~50–100 righe (principalmente in `mainapp.py` e `project_manager.py`).

---

## 4. Problematiche principali

### 4.1 ⚠️ Indirizzamento stabile delle tracce (CRITICO)

Il problema più insidioso. Attualmente le tracce sono identificate dall'indice in `self.mp3_widgets` (mainapp.py:85), che cambia con:
- **Remove** ([mainapp.py:333-338](mainapp.py#L333-L338)) — riduce la lista, gli indici scalano.
- **Drag&drop** ([mainapp.py:168-200](mainapp.py#L168-L200)) — la cella cambia ma l'indice nell'array no, però la posizione spaziale sì.
- **Load project** ([mainapp.py:232-282](mainapp.py#L232-L282)) — riassegna tutto.

**Tre opzioni:**

| Opzione | Pro | Contro |
|---|---|---|
| **(A) Indice array** (`/track/0`, `/track/1`...) | Semplice | Gli indici remoti si "sfasano" dopo un remove → utente OSC controlla la traccia sbagliata |
| **(B) Coordinate griglia** (`/track/r0/c1`) | Stabile alla rimozione, coerente con UI visiva | Cambia con drag&drop |
| **(C) UUID per slot** assegnato a `open_files` | Veramente stabile, persistito nel `.mpp` | L'utente non sa che `/track/abc-123` corrisponde a "song.mp3" → serve `/mp3player/list` per discovery |

**Raccomandazione:** ibrida — opzione **(C)** come canonica + alias **(B)** per usabilità + endpoint `/mp3player/track/by_name/{filename}` per scenari live.

### 4.2 ⚠️ Threading: server OSC ↔ main thread Qt

`python-osc` ServerThread usa `socketserver`, le callback girano nel thread del server. **Toccare widget Qt da quel thread crasha** (Qt non è thread-safe sui QObject UI).

**Pattern obbligatorio:**
```python
def _osc_play_handler(self, address, *args):
    # Questo handler gira nel thread del server OSC
    QMetaObject.invokeMethod(
        self._main_app, "osc_play_track",
        Qt.QueuedConnection,
        Q_ARG(str, address), Q_ARG(list, list(args))
    )
```

In alternativa: emettere un segnale Qt dal thread server (auto-marshal grazie a `Qt.AutoConnection`).

### 4.3 ⚠️ Conflitto fade ↔ comando OSC volume

[`Mp3File.fade_in/fade_out`](mp3file.py#L623-L672) installa un `FadeController` che continua a chiamare `set_volume`. Se durante un fade arriva un OSC `/track/0/volume 0.5`:
- O il fade override l'utente (visibile come "non funziona").
- O il volume cancella il fade (visibile come "interrotto").

**Decisione di design da prendere:** documentare che un comando volume cancella il fade in corso (consigliato — chiamando `_stop_active_fade()`), oppure ignorare i comandi volume durante un fade.

### 4.4 ⚠️ Backpressure su `/track/{id}/position` in uscita

Il timer `POLL_INTERVAL_MS=50` ([\_\_init\_\_.py:13](__init__.py#L13)) tickera 20×/s su N tracce. Inviare 20×N pacchetti UDP/s satura facilmente reti deboli e i client (TouchOSC su WiFi).

**Mitigazione:** rate-limit dei messaggi OSC outbound (es. 5–10 Hz), usare bundle per raggruppare per tick, escludere tracce non in playback.

### 4.5 Validazione argomenti

Lo spec OSC 1.0 ammette type tags `i`, `f`, `s`, `b`, `T`/`F`/`N`/`I` (1.1+). I client (TouchOSC, Lemur, Reaper) inviano tipicamente `f` per slider, ma alcuni inviano `i`. Serve coercion robusta: `volume = float(args[0])` con try/except + log invece di assert.

### 4.6 Sicurezza / esposizione di rete

OSC su UDP **non ha autenticazione**. Chiunque sulla LAN può fermare la riproduzione. In ambito teatro/installazione di solito è ok, ma:
- **Default sicuro:** bind su `127.0.0.1`, non `0.0.0.0`.
- Settings UI deve esplicitare l'opzione "Allow remote control on LAN".
- Documentare che endpoint come `/mp3player/project/load s` con path arbitrario è un **path traversal vector** → whitelist directory o conferma utente.

### 4.7 Pattern matching OSC 1.0 e bundle

Lo spec 1.0 richiede:
- **Pattern matching** per `*`, `?`, `[a-z]`, `{foo,bar}`. python-osc lo implementa già nel `Dispatcher`, ma serve testarlo (es. `/track/[0-3]/stop`).
- **Bundle con timetag**: messaggi schedulati in futuro. python-osc accetta bundle ma applica timetag solo se l'app lo gestisce esplicitamente. Se si vuole la sincronizzazione precisa (utile per "play di 4 tracce esattamente alle 18:00:00"), serve uno scheduler. **Suggerimento:** ignorare le timetag in v1, documentarlo come limitazione.

### 4.8 Backend VLC e burst di volume

[`_VlcBackend.NEEDS_VOLUME_REAPPLY_ON_PLAY`](mp3file.py#L205) usa un delay di 100ms dopo `play()`. Un comando OSC `play` seguito immediato da `volume 0.3` può cadere nel buco di 100ms e venir sovrascritto dal reapply automatico. Va testato — eventuale fix: il volume OSC **dopo** play deve essere riapplicato dopo lo stesso `FADE_STARTUP_DELAY_MS`.

### 4.9 Settings UI e persistenza configurazione

Serve un dialog "OSC Settings" (porta RX, host TX, porta TX, enable inbound/outbound, bind interface). Va persistito **fuori** dal `.mpp` (è una preferenza globale, non di progetto): introdurre un `~/.config/multiplayer/settings.json` o un file analogo. Ad oggi nel repo **non esiste un settings store globale** — va creato.

### 4.10 Test

Testabile in unit test con `_StubBackend` ([mp3file.py:125](mp3file.py#L125)) — non serve VLC. Setup:
1. `Mp3File("dummy.mp3", backend='vlc')` → stub fallback se VLC assente in CI.
2. Test client OSC che invia su `127.0.0.1:9000`.
3. Asserzioni su `mp3file.actual_volume`, `is_playing()`, etc.

Allineato con la mancanza generale di test rilevata in [TODO.md:40-46](TODO.md#L40-L46).

---

## 5. Stima effort

| Fase | Giornate (1 dev FT) | Output |
|---|---|---|
| **Phase 1 — MVP server inbound** | 2–3 | Server UDP, address scheme base, play/stop/volume/fade per indice traccia, marshalling Qt |
| **Phase 2 — Client outbound** | 1–2 | State notifications collegate ai segnali esistenti, rate-limit position |
| **Phase 3 — ID stabile traccia** | 1–2 | Track UUID, persistenza in `.mpp` v1.3, migrazione, endpoint `by_name` |
| **Phase 4 — Settings UI + config globale** | 1–2 | Dialog QSettings o JSON, bind safe-by-default, restart server al cambio porta |
| **Phase 5 — Robustezza** | 1–2 | Conflitto fade/volume, validazione args, gestione errori porta in uso, IPv6, pattern matching |
| **Phase 6 — Test & docs** | 1–2 | Suite test con stub backend, README + tabella endpoints, esempi TouchOSC layout |
| **TOTALE realistico** | **8–12 gg** | Implementazione production-ready |
| **MVP minimale (no Phase 3-5-6)** | **3–4 gg** | Funzionante, ma fragile in scenari live |

### 5.1 Variabili che alzano la stima
- Supporto **TCP/SLIP** (raro ma in spec): +1 giorno.
- **Discovery via mDNS/Zeroconf** (Bonjour-style, utile per TouchOSC auto-detect): +1–2 giorni (richiede `zeroconf`).
- **OSC Query** (proposed extension, introspection di endpoint): +2–3 giorni, sconsigliato.
- **Bundle scheduling con timetag** preciso: +1–2 giorni e ha implicazioni di latency/jitter.

---

## 6. Raccomandazioni per la roadmap

1. **Iniziare dall'MVP** (Phase 1+2 inbound/outbound con indici array). Genera valore subito: già controllabile da TouchOSC/Reaper/Lemur in <1 settimana.
2. **Fissare lo schema indirizzi presto** e comunicarlo come "stabile" prima che ci siano utenti esterni con preset OSC scritti — cambiarlo dopo è doloroso.
3. **Affrontare il track-ID stabile (Phase 3) prima del primo rilascio pubblico**, altrimenti gli utenti scriveranno preset basati su indici e si lamenteranno dopo il primo remove.
4. **Bind su `127.0.0.1` di default** sempre. Usabilità < sicurezza qui.
5. Considerare l'allineamento con il TODO architetturale **A2** ([TODO.md:30-34](TODO.md#L30-L34)): un `QThreadPool` condiviso può ospitare anche il dispatch OSC → main e ridurre la frammentazione thread del progetto.

---

## 7. Riferimenti nel codebase

- Punto di aggancio principale per i comandi: [`Mp3File`](mp3file.py#L518) — API già completa (play_pause/stop/fade_in/fade_out/set_volume/set_gain/set_position/normalize).
- Segnali già pronti per il client outbound: [mp3file.py:519-525](mp3file.py#L519-L525).
- Lista tracce e ciclo principale: [`MainApp.mp3_widgets`](mainapp.py#L85), [`_tick_progress`](mainapp.py#L102).
- Persistenza progetto da estendere: [`ProjectManager`](project_manager.py#L10), [`CURRENT_VERSION`](project_manager.py#L7).
- Stub backend per i test: [`_StubBackend`](mp3file.py#L125).
