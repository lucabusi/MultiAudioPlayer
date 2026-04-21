"""
Benchmark completo di tutti i metodi di generazione waveform presenti in waveform.py.

Metodi testati:
  generate_waveform          librosa + matplotlib (plt.plot)
  generate_waveform_rosa     librosa + librosa.display.waveshow + matplotlib
  generate_waveform_pillow   librosa + PIL ImageDraw (per-column draw loop)
  generate_waveform_HS       soundfile full-load + numpy reshape + PIL canvas  → restituisce path
  generate_waveform_mem      soundfile full-load + numpy reshape + PIL canvas  → restituisce bytes

Uso:
    python bench_envelope.py
"""

import os
import time
import traceback
from pathlib import Path

import numpy as np
import soundfile as sf

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


# ── definizione strategie ────────────────────────────────────────────────────

STRATEGIES = [
    ("mpl-plot",    "generate_waveform",        lambda p, d: wf.generate_waveform(p, d)),
    ("mpl-rosa",    "generate_waveform_rosa",   lambda p, d: wf.generate_waveform_rosa(p, d)),
    ("pil-librosa", "generate_waveform_pillow", lambda p, d: wf.generate_waveform_pillow(p, d)),
    ("sf-HS",       "generate_waveform_HS",     lambda p, d: wf.generate_waveform_HS(p, d)),
    ("sf-mem",      "generate_waveform_mem",    lambda p, d: wf.generate_waveform_mem(p, d)),
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
