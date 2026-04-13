import os
import hashlib
import logging
import tempfile
import numpy as np
import matplotlib.pyplot as plt
import librosa
import librosa.display
import soundfile as sf
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

_WAVEFORM_CACHE_DIR = os.path.join(tempfile.gettempdir(), 'mp3player_waveforms')


def _waveform_cache_path(file_name: str) -> str:
    """Return a unique, stable cache path for the waveform of file_name.
    Uses an MD5 hash of the absolute path to avoid filename collisions.
    """
    os.makedirs(_WAVEFORM_CACHE_DIR, exist_ok=True)
    h = hashlib.md5(os.path.abspath(file_name).encode()).hexdigest()
    return os.path.join(_WAVEFORM_CACHE_DIR, h + '.jpg')


def generate_waveform(file_name, file_duration):
    """Generate a waveform image using matplotlib (legacy function).
    Returns the path to the generated JPEG file.
    """
    target_sr = 11025
    audio, _ = librosa.load(file_name, sr=target_sr, mono=True)
    plt.figure(figsize=(10, 0.5))
    plt.box(False)
    plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
    plt.margins(0, 0)
    plt.tick_params(left=False, right=False, labelleft=False, labelbottom=False, bottom=False)
    plt.plot(np.linspace(0, file_duration, len(audio)), audio, color='b', linewidth=0.1)
    plt.ylim(-1, 1)

    mp3WaveformImagePath = _waveform_cache_path(file_name)
    plt.savefig(mp3WaveformImagePath, format='jpeg', dpi=150)
    logger.info(f"{file_name}: Max: {audio.max():.4f}, Min: {audio.min():.4f}, Mean: {audio.mean()*1000:.8f}")
    plt.close()
    return mp3WaveformImagePath


def generate_waveform_pillow(file_name, file_duration, width=1500, height=75, target_sr=11025):
    """Generate a waveform image using Pillow. Returns path to JPEG file."""
    samples, _ = librosa.load(file_name, sr=target_sr, mono=True)
    step = max(1, len(samples) // width)
    samples = samples[: step * width]
    samples = samples.reshape(-1, step)
    min_vals = samples.min(axis=1)
    max_vals = samples.max(axis=1)

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    center = height // 2

    for x, (min_val, max_val) in enumerate(zip(min_vals, max_vals)):
        y1 = int(center + min_val * center)
        y2 = int(center + max_val * center)
        draw.line([(x, y1), (x, y2)], fill="blue")

    mp3WaveformImagePath = _waveform_cache_path(file_name)
    img.save(mp3WaveformImagePath, 'JPEG')
    return mp3WaveformImagePath


def generate_waveform_rosa(file_name, file_duration):
    """Generate waveform using librosa.display.waveshow and matplotlib."""
    target_sr = 11025
    try:
        audio, _ = librosa.load(file_name, sr=target_sr, mono=True)
    except Exception as e:
        logger.error(f"Error loading audio file {file_name}: {e}")
        raise

    plt.style.use('fast')
    plt.rcParams['agg.path.chunksize'] = 10000
    plt.figure(figsize=(10, 0.5), dpi=150)
    plt.box(False)
    plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
    plt.margins(0, 0)
    plt.tick_params(left=False, right=False, labelleft=False, labelbottom=False, bottom=False)

    librosa.display.waveshow(audio, sr=target_sr, axis=None, color='b', linewidth=0.1)
    plt.ylim(-1, 1)

    mp3WaveformImagePath = _waveform_cache_path(file_name)
    plt.savefig(mp3WaveformImagePath, format='jpeg', dpi=150)
    logger.info(f"{file_name}: Max: {audio.max():.4f}, Min: {audio.min():.4f}, Mean: {audio.mean()*1000:.8f}")
    plt.close()
    return mp3WaveformImagePath


def generate_waveform_HS(file_name, file_duration, width=1500, height=75, target_sr=11025, cache=True):
    """High-speed waveform generation using streaming envelope computation.
    Reads audio in blocks (no full-file load), computes per-pixel min/max envelope
    and renders with Pillow. Returns path to JPEG file.
    This version does NOT create or read any .npy cache files.
    """
    mp3WaveformImagePath = _waveform_cache_path(file_name)

    # streaming read to compute envelope per output pixel column
    try:
        with sf.SoundFile(file_name) as f:
            total_frames = len(f)
            frames_per_bin = max(1, int(np.ceil(total_frames / float(width))))

            min_vals = np.full(width, np.inf, dtype=np.float32)
            max_vals = np.full(width, -np.inf, dtype=np.float32)

            blocksize = 65536
            frame_idx = 0
            while True:
                block = f.read(blocksize, dtype='float32')
                if block is None or len(block) == 0:
                    break
                if block.ndim > 1:
                    block = block.mean(axis=1)

                start = frame_idx
                end = frame_idx + len(block)
                bins = ((np.arange(start, end) // frames_per_bin)).astype(np.int32)
                bins[bins >= width] = width - 1

                # aggregate per-bin min/max for this block
                for b in np.unique(bins):
                    mask = (bins == b)
                    seg = block[mask]
                    if seg.size:
                        mn = seg.min()
                        mx = seg.max()
                        if mn < min_vals[b]:
                            min_vals[b] = mn
                        if mx > max_vals[b]:
                            max_vals[b] = mx
                frame_idx = end

    except Exception as e:
        logger.error(f"Error computing envelope for {file_name}: {e}")
        # fallback to librosa full load
        samples, _ = librosa.load(file_name, sr=target_sr, mono=True)
        step = max(1, len(samples) // width)
        samples = samples[: step * width]
        samples = samples.reshape(-1, step)
        min_vals = samples.min(axis=1)
        max_vals = samples.max(axis=1)

    # fill empty bins
    min_vals[np.isinf(min_vals)] = 0.0
    max_vals[np.isneginf(max_vals)] = 0.0

    # Draw using a numpy canvas then convert to Pillow image (faster than many draw calls)
    canvas = np.ones((height, width, 3), dtype=np.uint8) * 255
    center = height // 2
    ys1 = (center + (min_vals * center)).astype(np.int32)
    ys2 = (center + (max_vals * center)).astype(np.int32)
    ys1 = np.clip(ys1, 0, height - 1)
    ys2 = np.clip(ys2, 0, height - 1)

    blue = np.array([0, 0, 255], dtype=np.uint8)
    for x in range(width):
        y1 = ys1[x]
        y2 = ys2[x]
        if y1 <= y2:
            canvas[y1:y2 + 1, x] = blue
        else:
            canvas[y2:y1 + 1, x] = blue

    img = Image.fromarray(canvas)
    img.save(mp3WaveformImagePath, 'JPEG')
    return mp3WaveformImagePath
