"""
Benchmark dei metodi di generazione waveform.

Le 4 implementazioni "legacy" (mpl-plot, mpl-rosa, pil-librosa, sf-HS) vivono
qui come funzioni private — usate solo per confronto storico nel benchmark,
non in produzione. waveform.py espone solo `generate_waveform_mem` (pipeline
runtime, soundfile-based) e `generate_waveform_librosa` (fallback per formati
che soundfile non gestisce, audioread/ffmpeg-backed).

Metodi testati:
  _generate_waveform               librosa + matplotlib (plt.plot)         [legacy]
  _generate_waveform_rosa          librosa + librosa.display.waveshow      [legacy]
  _generate_waveform_pillow        librosa + PIL ImageDraw per-column      [legacy]
  _generate_waveform_HS            soundfile + numpy + PIL → path          [legacy]
  wf.generate_waveform_mem         soundfile + numpy + PIL → bytes         [produzione]
  wf.generate_waveform_librosa     librosa.load (audioread/ffmpeg) → bytes [fallback]

Uso:
    python bench_envelope.py
"""

import os
import time
import traceback
from pathlib import Path

import numpy as np
import soundfile as sf
import librosa
import librosa.display
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw

import waveform as wf

AUDIO_DIR = Path(__file__).parent / "audio_test"
RUNS = 3


# ── utilità ──────────────────────────────────────────────────────────────────

def _duration(file_path: str) -> float:
    with sf.SoundFile(file_path) as f:
        return len(f) / f.samplerate


def _run(fn, *args, runs: int = RUNS):
    """Esegue fn(*args) `runs` volte e restituisce (media_secondi, errore|None)."""
    times = []
    err = None
    for i in range(runs):
        try:
            t0 = time.perf_counter()
            fn(*args)
            times.append(time.perf_counter() - t0)
        except Exception as e:
            err = e
            break
    if not times:
        return None, err
    return sum(times) / len(times), None


# ── implementazioni legacy (solo per benchmark) ──────────────────────────────

def _setup_matplotlib_figure():
    """Helper matplotlib usato dalle implementazioni legacy plot/rosa."""
    plt.style.use('fast')
    plt.rcParams['agg.path.chunksize'] = 10000
    plt.figure(figsize=(10, 0.5), dpi=150)
    plt.box(False)
    plt.subplots_adjust(top=1, bottom=0, right=1, left=0, hspace=0, wspace=0)
    plt.margins(0, 0)
    plt.tick_params(left=False, right=False, labelleft=False,
                    labelbottom=False, bottom=False)


def _generate_waveform(file_name, file_duration):
    """Legacy: matplotlib plt.plot del segnale completo."""
    target_sr = 11025
    audio, _ = librosa.load(file_name, sr=target_sr, mono=True)
    _setup_matplotlib_figure()
    plt.plot(np.linspace(0, file_duration, len(audio)), audio,
             color='b', linewidth=0.1)
    plt.ylim(-1, 1)
    path = wf._waveform_cache_path(file_name)
    plt.savefig(path, format='jpeg', dpi=150)
    plt.close()
    return path


def _generate_waveform_rosa(file_name, file_duration):
    """Legacy: librosa.display.waveshow + matplotlib (vecchio fallback)."""
    target_sr = 11025
    audio, _ = librosa.load(file_name, sr=target_sr, mono=True)
    _setup_matplotlib_figure()
    librosa.display.waveshow(audio, sr=target_sr, axis=None,
                             color='b', linewidth=0.1)
    plt.ylim(-1, 1)
    path = wf._waveform_cache_path(file_name)
    plt.savefig(path, format='jpeg', dpi=150)
    plt.close()
    return path


def _generate_waveform_pillow(file_name, file_duration, width=1500,
                              height=75, target_sr=11025):
    """Legacy: librosa + PIL ImageDraw per-column draw loop."""
    samples, _ = librosa.load(file_name, sr=target_sr, mono=True)
    step = max(1, len(samples) // width)
    samples = samples[: step * width].reshape(-1, step)
    min_vals = samples.min(axis=1)
    max_vals = samples.max(axis=1)
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    center = height // 2
    for x, (min_val, max_val) in enumerate(zip(min_vals, max_vals)):
        y1 = int(center + min_val * center)
        y2 = int(center + max_val * center)
        draw.line([(x, y1), (x, y2)], fill="blue")
    path = wf._waveform_cache_path(file_name)
    img.save(path, 'JPEG')
    return path


def _generate_waveform_HS(file_name, file_duration, width=1500,
                          height=75, target_sr=11025):
    """Legacy: soundfile + numpy reshape + PIL canvas, restituisce path."""
    path = wf._waveform_cache_path(file_name)
    samples, _ = sf.read(file_name, dtype='float32', always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    step = max(1, len(samples) // width)
    samples = samples[: step * width].reshape(-1, step)
    min_vals = samples.min(axis=1)
    max_vals = samples.max(axis=1)
    canvas = np.ones((height, width, 3), dtype=np.uint8) * 255
    center = height // 2
    ys1 = np.clip((center + min_vals * center).astype(np.int32), 0, height - 1)
    ys2 = np.clip((center + max_vals * center).astype(np.int32), 0, height - 1)
    blue = np.array([0, 0, 255], dtype=np.uint8)
    for x in range(width):
        y1, y2 = ys1[x], ys2[x]
        if y1 <= y2:
            canvas[y1:y2 + 1, x] = blue
        else:
            canvas[y2:y1 + 1, x] = blue
    Image.fromarray(canvas).save(path, 'JPEG')
    return path


# ── definizione strategie ────────────────────────────────────────────────────

STRATEGIES = [
    ("mpl-plot",    "_generate_waveform",            lambda p, d: _generate_waveform(p, d)),
    ("mpl-rosa",    "_generate_waveform_rosa",       lambda p, d: _generate_waveform_rosa(p, d)),
    ("pil-librosa", "_generate_waveform_pillow",     lambda p, d: _generate_waveform_pillow(p, d)),
    ("sf-HS",       "_generate_waveform_HS",         lambda p, d: _generate_waveform_HS(p, d)),
    ("sf-mem",      "wf.generate_waveform_mem",      lambda p, d: wf.generate_waveform_mem(p)),
    ("lib-mem",     "wf.generate_waveform_librosa",  lambda p, d: wf.generate_waveform_librosa(p)),
]


# ── benchmark ────────────────────────────────────────────────────────────────

def bench_file(file_path: str) -> dict:
    duration = _duration(file_path)
    results = {}
    for short, full, fn in STRATEGIES:
        avg, err = _run(fn, file_path, duration)
        results[short] = {"time": avg, "error": type(err).__name__ if err else None, "full": full}
    return {
        "name": os.path.basename(file_path),
        "size_mb": os.path.getsize(file_path) / 1024 / 1024,
        "duration_s": duration,
        "results": results,
    }


# ── report ───────────────────────────────────────────────────────────────────

def _fmt(entry: dict) -> str:
    if entry["time"] is None:
        return f"  ERR({entry['error']})"
    return f"{entry['time']:>8.3f}s"


def main():
    files = sorted(AUDIO_DIR.glob("*.mp3"))
    if not files:
        print(f"Nessun file .mp3 trovato in {AUDIO_DIR}")
        return

    labels = [s[0] for s in STRATEGIES]
    col = 11  # larghezza colonna tempi

    # intestazione
    print()
    print("=" * 90)
    print("BENCHMARK METODI WAVEFORM - waveform.py")
    print(f"Directory: {AUDIO_DIR}   |   Runs per file: {RUNS}")
    print("=" * 90)

    # raccolta dati
    all_rows = []
    errors_seen = {}  # short_label → (full_name, primo errore)
    for f in files:
        row = bench_file(str(f))
        all_rows.append(row)
        for label, entry in row["results"].items():
            if entry["error"] and label not in errors_seen:
                errors_seen[label] = (entry["full"], entry["error"])

    # tabella per file
    header = f"{'File':<36} {'MB':>4}  {'dur':>5}" + "".join(f"  {l[:col]:>{col}}" for l in labels)
    print()
    print(header)
    print("-" * len(header))

    totals = {l: 0.0 for l in labels}
    valid_counts = {l: 0 for l in labels}

    for row in all_rows:
        line = f"{row['name']:<36} {row['size_mb']:>4.1f}  {row['duration_s']:>5.1f}"
        for label in labels:
            entry = row["results"][label]
            if entry["time"] is not None:
                t = entry["time"]
                totals[label] += t
                valid_counts[label] += 1
                line += f"  {t:>{col}.3f}"
            else:
                line += f"  {'N/A':>{col}}"
        print(line)

    print("-" * len(header))
    tot_line = f"{'TOTALE':<36} {'':>4}  {'':>5}"
    for label in labels:
        if valid_counts[label] > 0:
            tot_line += f"  {totals[label]:>{col}.3f}"
        else:
            tot_line += f"  {'N/A':>{col}}"
    print(tot_line)

    # speedup vs metodo piu lento disponibile
    available = {l: totals[l] for l in labels if valid_counts[l] == len(all_rows)}
    if available:
        slowest_label = max(available, key=lambda l: available[l])
        slowest_time = available[slowest_label]
        fastest_label = min(available, key=lambda l: available[l])

        print()
        print(f"Speedup vs '{slowest_label}' (piu lento tra i metodi disponibili):")
        for label in labels:
            if label not in available or label == slowest_label:
                continue
            sp = slowest_time / available[label]
            saved = slowest_time - available[label]
            print(f"  {label:<14}  {sp:5.2f}x  ({saved:+.3f}s risparmiati sul totale)")

        print()
        print(f"Metodo piu veloce: {fastest_label}  ({available[fastest_label]:.3f}s totale)")

    # errori
    if errors_seen:
        print()
        print("Metodi non disponibili:")
        for short, (full, err) in errors_seen.items():
            print(f"  {short:<12}  {full:<28}  {err}")

    print()
    print("=" * 90)


if __name__ == "__main__":
    main()
