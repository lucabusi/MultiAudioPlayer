import io
import os
import hashlib
import logging
import tempfile
import numpy as np
import soundfile as sf
from PIL import Image
from __init__ import WAVEFORM_WIDTH

logger = logging.getLogger(__name__)

_WAVEFORM_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'mp3player_waveforms')


def _waveform_cache_path(file_name: str, width: int = WAVEFORM_WIDTH) -> str:
    """Return a unique, stable cache path for the waveform of file_name
    at the given width. Width is part of the key because waveforms rendered
    at different widths are visually different.
    """
    os.makedirs(_WAVEFORM_CACHE_DIR, exist_ok=True)
    h = hashlib.md5(os.path.abspath(file_name).encode()).hexdigest()
    return os.path.join(_WAVEFORM_CACHE_DIR, f"{h}_{width}.jpg")


def clear_waveform_cache(file_name: str, width: int = WAVEFORM_WIDTH) -> None:
    """Delete the cached waveform image for file_name at the given width."""
    path = _waveform_cache_path(file_name, width)
    try:
        os.remove(path)
        logger.debug(f"Removed waveform cache: {path}")
    except FileNotFoundError:
        pass


def _render_envelope_jpeg(samples, width: int, height: int, gain: float = 1.0) -> bytes:
    """Compute min/max envelope per column from samples and render as JPEG bytes.
    Shared core di tutte le funzioni `generate_waveform_*`."""
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    step = max(1, len(samples) // width)
    samples = samples[: step * width].reshape(-1, step)
    min_vals = samples.min(axis=1) * gain
    max_vals = samples.max(axis=1) * gain

    canvas = np.ones((height, width, 3), dtype=np.uint8) * 255
    center = height // 2
    ys1 = np.clip((center + (min_vals * center)).astype(np.int32), 0, height - 1)
    ys2 = np.clip((center + (max_vals * center)).astype(np.int32), 0, height - 1)

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
                          height=75, gain=1.0) -> bytes:
    """Pipeline principale: soundfile + numpy + PIL → JPEG bytes.
    Cachata su disco quando gain == 1.0; per gain ≠ 1.0 viene rigenerata in
    memoria (gain è un trasformo visivo runtime, non vale la pena cacharlo
    per ogni valore distinto).

    Solleva eccezione se soundfile non riesce a decodificare il file
    (formato non supportato da libsndfile, header rotto, ecc.). I chiamanti
    che vogliono robustezza su formati esotici devono catturare e riprovare
    con `generate_waveform_librosa`.
    """
    use_cache = abs(gain - 1.0) < 1e-6
    cache = _waveform_cache_path(file_name, width) if use_cache else None
    if cache is not None and os.path.isfile(cache):
        try:
            with open(cache, 'rb') as fh:
                return fh.read()
        except OSError:
            pass

    samples, _ = sf.read(file_name, dtype='float32', always_2d=False)
    data = _render_envelope_jpeg(samples, width, height, gain)

    if cache is not None:
        try:
            with open(cache, 'wb') as fh:
                fh.write(data)
        except OSError as exc:
            logger.warning(f"cache write failed: {exc}")
    return data


def generate_waveform_librosa(file_name, width=WAVEFORM_WIDTH,
                              height=75, gain=1.0) -> bytes:
    """Fallback: usa librosa.load (audioread/ffmpeg backend) per decodificare
    formati che soundfile non gestisce nativamente — AAC/M4A, WMA, ALAC,
    AC-3, AMR, ecc.

    Più lento di `generate_waveform_mem` (un fattore 2-5x tipico, dato che
    audioread spawna ffmpeg in subprocess) ma copre molti più formati.
    Non usa la cache su disco: i casi d'uso sono file in formati esotici,
    raramente ricaricati nello stesso progetto.

    L'import di librosa è lazy: viene fatto solo se il fallback è davvero
    necessario, evitando ~1s di startup time all'avvio dell'app.
    """
    import librosa  # lazy import — librosa is heavy
    samples, _ = librosa.load(file_name, sr=None, mono=True)
    return _render_envelope_jpeg(samples, width, height, gain)
