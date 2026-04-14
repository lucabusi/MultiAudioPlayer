# TODO — Miglioramenti da implementare

Generato il 2026-04-14. Continuazione dell'analisi e refactoring in corso.

---

## Priorità MEDIA

### 1. Estrarre `ProjectManager` da `MainApp`
**File:** `mainapp.py` → nuovo `project_manager.py`  
`save_project()` e `load_project()` sono ~110 righe di logica di serializzazione
dentro la finestra principale. Mescolano stato di view (posizioni grid) con stato
di model (volume, fade time).

**Interfaccia proposta:**
```python
class ProjectManager:
    def save(self, widgets: list[Mp3Widget], grid_layout, window_geometry, path: str)
    def load(self, path: str) -> list[dict]  # restituisce dati grezzi, non widget
```
`MainApp` crea i widget dai dati restituiti da `load()`.

---

### 2. Estrarre `GridManager` da `MainApp`
**File:** `mainapp.py` → nuovo `grid_manager.py`  
`find_next_available_cell()`, `find_nearest_free_cell()`, `_update_column_stretches()`,
`get_cell_at_pos()` sono ~60 righe di logica grid dentro la finestra principale.

**Interfaccia proposta:**
```python
class GridManager:
    def __init__(self, grid_layout: QGridLayout, initial_cols: int)
    def find_next_available_cell(self) -> tuple[int, int]
    def find_nearest_free_cell(self, row: int, col: int) -> tuple[int, int]
    def get_cell_at_pos(self, pos) -> tuple[int, int]
    def update_column_stretches(self)
```

---


## Priorità BASSA

### 4. Rimuovere attributi inutilizzati
**File:** `mainapp.py`, `mp3widget.py`

| Attributo | File | Riga | Problema |
|---|---|---|---|
| `self.mp3_audio_files = []` | `mainapp.py` | ~48 | Dichiarato, mai usato |
| `self.playerState` | `mp3widget.py` | ~133 | Assegnato una volta, mai aggiornato né letto |
| `self.elapsed_time = 0` | `mp3widget.py` | ~127 | Mai usato |
| `self.remaining_time = 0` | `mp3widget.py` | ~128 | Mai usato |

---

### 5. Cleanup cache waveform
**File:** `waveform.py`  
I file `.jpg` in `_WAVEFORM_CACHE_DIR` non vengono mai rimossi.
100 sessioni = 100 file in `/tmp/mp3player_waveforms/`.

**Fix proposto:** in `Mp3File.cleanup()` o in `WaveformService.cancel()`,
eliminare il file cache associato al file corrente:
```python
def _clear_cache(file_name: str):
    path = _waveform_cache_path(file_name)
    if os.path.exists(path):
        os.remove(path)
```

---

### 7. Limite massimo righe nella griglia
**File:** `mainapp.py`, `find_next_available_cell()` e `find_nearest_free_cell()`  
Il grid cresce infinitamente: viene mostrato "Grid Full" ma non esiste un limite reale.

**Fix proposto:** definire `MAX_ROWS = 20` e rispettarlo in `find_next_available_cell()`.

---

### 8. Rinominare metodi con prefisso `w_` e notazione ungherese
**File:** `mp3widget.py`  
I metodi `w_play_pause`, `w_stop`, `w_fade_in`, `w_fade_out`, `w_remove_file`
e gli attributi `btnPlay`, `lblVolume`, `slidVolume` usano convenzioni inconsistenti.

**Rinomina proposta:**
| Prima | Dopo |
|---|---|
| `w_play_pause()` | `on_play_pause_clicked()` |
| `w_stop()` | `on_stop_clicked()` |
| `w_fade_in()` | `on_fade_in_clicked()` |
| `w_fade_out()` | `on_fade_out_clicked()` |
| `w_remove_file()` | `on_remove_clicked()` |
| `btnPlay` | `play_button` |
| `lblVolume` | `volume_label` |
| `slidVolume` | `volume_slider` |

---

### 9. Eliminare duplicazione setup matplotlib in `waveform.py`
**File:** `waveform.py`  
`generate_waveform()` (righe 26-44) e `generate_waveform_rosa()` (righe 70-94)
condividono 5 righe identiche di setup matplotlib.

**Fix proposto:**
```python
def _setup_matplotlib_figure():
    plt.style.use('fast')
    plt.rcParams['agg.path.chunksize'] = 10000
    plt.figure(figsize=(10, 0.5), dpi=150)
    plt.box(False)
    plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
    plt.margins(0, 0)
    plt.tick_params(left=False, right=False, labelleft=False, labelbottom=False, bottom=False)
```

---

## Note architetturali (refactoring a lungo termine)

- **MVC**: `Mp3Widget` mescola View e Controller. Separare in
  `AudioPlayerController` (logica) + widget puri (solo UI).
- **Testabilità**: nessun componente è testabile in isolamento.
  Introdurre dependency injection per `Mp3File` in `Mp3Widget`.
- **`FadeController`**: non valida che `end_volume > start_volume`,
  e non gestisce `duration=0`. Aggiungere guard clause.
- **`fade_in()`**: se la traccia è già in play la funzione non fa nulla silenziosamente.
  Valutare se loggare un warning.
