import io
import os
import hashlib
import logging
import tempfile
import numpy as np
import soundfile as sf
from PIL import Image
from constants import WAVEFORM_WIDTH, WAVEFORM_HEIGHT

logger = logging.getLogger(__name__)

_WAVEFORM_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'mp3player_waveforms')


def _envelope_cache_path(file_name: str, width: int = WAVEFORM_WIDTH) -> str:
    """Return a unique, stable cache path for the envelope of file_name
    at the given width. The key includes mtime and size so the cache is
    invalidated when the file is replaced with different content.
    """
    os.makedirs(_WAVEFORM_CACHE_DIR, exist_ok=True)
    try:
        st = os.stat(file_name)
        stamp = f"{st.st_mtime_ns}_{st.st_size}"
    except OSError:
        stamp = "0_0"
    h = hashlib.md5(f"{os.path.abspath(file_name)}|{stamp}".encode()).hexdigest()
    return os.path.join(_WAVEFORM_CACHE_DIR, f"{h}_{width}.npz")


def _decode_mono(file_name: str) -> np.ndarray:
    """Decodifica il file in float32 mono. Prova soundfile (veloce, nativo);
    fallback su librosa (audioread/ffmpeg) per i formati che libsndfile non
    gestisce — AAC/M4A, WMA, ALAC, ecc. L'import di librosa è lazy perché
    costa ~1s di startup."""
    try:
        samples, _ = sf.read(file_name, dtype='float32', always_2d=False)
        if samples.ndim > 1:
            samples = samples.mean(axis=1)
        return samples
    except Exception as exc:
        logger.debug(f"soundfile decode failed ({exc}); falling back to librosa")
        import librosa  # lazy import — librosa is heavy
        samples, _ = librosa.load(file_name, sr=None, mono=True)
        return samples


def _envelope_from_samples(samples: np.ndarray, width: int) -> tuple[np.ndarray, np.ndarray]:
    """Envelope min/max per colonna. Al più `width` colonne: se il file ha
    meno campioni di `width`, l'envelope ha una colonna per campione (il
    rendering viene poi scalato dalla UI)."""
    n_cols = min(width, len(samples))
    if n_cols == 0:
        zero = np.zeros(1, dtype=np.float32)
        return zero, zero
    step = len(samples) // n_cols
    cols = samples[: step * n_cols].reshape(-1, step)
    return cols.min(axis=1), cols.max(axis=1)


def compute_envelope(file_name: str, width: int = WAVEFORM_WIDTH) -> tuple[np.ndarray, np.ndarray]:
    """Ritorna (min_vals, max_vals) dell'envelope, cachato su disco.

    Il decode è la parte costosa: l'envelope (2×width float) viene salvato
    in un .npz così i re-render (es. cambio gain) non ridecodificano nulla.
    """
    cache = _envelope_cache_path(file_name, width)
    if os.path.isfile(cache):
        try:
            data = np.load(cache)
            return data['min'], data['max']
        except Exception as exc:
            logger.debug(f"cache read failed, regenerating: {exc}")

    samples = _decode_mono(file_name)
    min_vals, max_vals = _envelope_from_samples(samples, width)

    try:
        np.savez(cache, min=min_vals, max=max_vals)
    except OSError as exc:
        logger.warning(f"cache write failed: {exc}")
    return min_vals, max_vals


def render_envelope(min_vals: np.ndarray, max_vals: np.ndarray,
                    height: int = WAVEFORM_HEIGHT, gain: float = 1.0) -> bytes:
    """Disegna l'envelope (scalato per `gain`) e ritorna JPEG bytes.
    Il canvas è largo len(min_vals): il loop è limitato dalla lunghezza
    reale degli array, quindi file più corti della width richiesta non
    possono causare accessi fuori range."""
    width = len(min_vals)
    canvas = np.ones((height, width, 3), dtype=np.uint8) * 255
    center = height // 2
    ys1 = np.clip((center + (min_vals * gain * center)).astype(np.int32), 0, height - 1)
    ys2 = np.clip((center + (max_vals * gain * center)).astype(np.int32), 0, height - 1)

    blue = np.array([0, 0, 255], dtype=np.uint8)
    for x in range(width):
        y1, y2 = ys1[x], ys2[x]
        if y1 <= y2:
            canvas[y1:y2 + 1, x] = blue
        else:
            canvas[y2:y1 + 1, x] = blue

    buf = io.BytesIO()
    Image.fromarray(canvas).save(buf, 'JPEG')
    return buf.getvalue()


def generate_waveform_mem(file_name, width=WAVEFORM_WIDTH,
                          height=WAVEFORM_HEIGHT, gain=1.0) -> bytes:
    """Decode (con cache envelope) + render in un colpo solo."""
    min_vals, max_vals = compute_envelope(file_name, width)
    return render_envelope(min_vals, max_vals, height, gain)


def generate_waveform_librosa(file_name, width=WAVEFORM_WIDTH,
                              height=WAVEFORM_HEIGHT, gain=1.0) -> bytes:
    """Come generate_waveform_mem ma forza il decode via librosa, senza cache.
    Mantenuta per i benchmark (bench_envelope.py) e come utilità di confronto."""
    import librosa  # lazy import — librosa is heavy
    samples, _ = librosa.load(file_name, sr=None, mono=True)
    min_vals, max_vals = _envelope_from_samples(samples, width)
    return render_envelope(min_vals, max_vals, height, gain)
