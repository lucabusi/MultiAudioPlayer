import os
import logging
import numpy as np
import matplotlib.pyplot as plt
import librosa
import librosa.display
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


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

    mp3WaveformImagePath = f'{os.path.basename(file_name)}.jpg'
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

    mp3WaveformImagePath = f'{os.path.basename(file_name)}.jpg'
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

    mp3WaveformImagePath = f'{os.path.basename(file_name)}.jpg'
    plt.savefig(mp3WaveformImagePath, format='jpeg', dpi=150)
    logger.info(f"{file_name}: Max: {audio.max():.4f}, Min: {audio.min():.4f}, Mean: {audio.mean()*1000:.8f}")
    plt.close()
    return mp3WaveformImagePath
