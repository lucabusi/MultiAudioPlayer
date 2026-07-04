"""Costanti condivise dal progetto.

Importate dai moduli con `from constants import ...`.
"""

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
