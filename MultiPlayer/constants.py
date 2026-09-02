"""Costanti condivise dal progetto.

Importate dai moduli con `from constants import ...`.
"""

# --- Versione applicativa ---
# Da incrementare ad ogni modifica funzionale. NON è la versione del formato
# di progetto `.mpp`, che vive in project_manager.CURRENT_VERSION e si muove
# solo quando cambia lo schema del file salvato.
APP_VERSION = '3.2.0'

# --- Audio ---
# Backend usato al primo avvio e come fallback quando la preferenza salvata
# dal menu "Configura → Backend audio" non è più tra quelli registrati in
# mp3file._BACKENDS. Deve restare allineato al default di Mp3File.__init__.
DEFAULT_BACKEND = 'qt'            # 'qt' | 'vlc' | 'gstreamer' | 'mpv'

# --- Preferenze persistenti (QSettings) ---
SETTINGS_ORG = 'MultiPlayer'
SETTINGS_APP = 'MultiPlayer'
SETTINGS_BACKEND_KEY = 'audio/backend'

# --- UI ---
PROGRESS_BAR_HEIGHT = 48          # altezza in px della progress bar di ogni widget

# --- Timing ---
POLL_INTERVAL_MS = 50             # tick del timer globale di poll della UI
FADE_TICK_MS = 100                # intervallo di step del FadeController
FADE_STARTUP_DELAY_MS = 100       # delay tra play() e inizio del fade-in
WAVEFORM_DEBOUNCE_MS = 300        # debounce per refresh waveform su gain

# --- Waveform rendering ---
WAVEFORM_WIDTH = 1500             # larghezza default del rendering high-res (px)
WAVEFORM_HEIGHT = 75              # altezza del rendering (px)
