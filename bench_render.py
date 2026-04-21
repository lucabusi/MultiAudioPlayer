"""
Benchmark end-to-end di strategie di rendering per la waveform su file MP3 reali.

Ogni strategia misura l'intera pipeline: sf.read → envelope → render → JPEG bytes.

Strategie:
  current    loop Python per colonne  + PIL JPEG     (generate_waveform_mem attuale)
  vec-mask   numpy broadcast (H,W)    + PIL JPEG
  mpl-fill   matplotlib fill_between  + JPEG BytesIO

Il benchmark riporta:
  - tempi end-to-end per file
  - breakdown: I/O+envelope vs solo rendering
  - speedup relativo

Uso:
    python bench_render.py
"""

import io
import os
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

AUDIO_DIR = Path(__file__).parent / "audio_test"
WIDTH  = 1500
HEIGHT = 75
RUNS   = 5


# ── pipeline I/O + envelope (identica per tutte) ─────────────────────────────

def _load_envelope(file_path: str):
    samples, _ = sf.read(file_path, dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    step = max(1, len(samples) // WIDTH)
    samples = samples[: step * WIDTH].reshape(-1, step)
    return samples.min(axis=1).astype(np.float32), samples.max(axis=1).astype(np.float32)


# ── rendering: strategia 1 — loop Python (attuale) ───────────────────────────

def _render_current(min_v, max_v) -> bytes:
    canvas = np.ones((HEIGHT, WIDTH, 3), dtype=np.uint8) * 255
    center = HEIGHT // 2
    ys1 = np.clip((center + min_v * center).astype(np.int32), 0, HEIGHT - 1)
    ys2 = np.clip((center + max_v * center).astype(np.int32), 0, HEIGHT - 1)
    blue = np.array([0, 0, 255], dtype=np.uint8)
    for x in range(WIDTH):
        y1, y2 = ys1[x], ys2[x]
        if y1 <= y2:
            canvas[y1:y2 + 1, x] = blue
        else:
            canvas[y2:y1 + 1, x] = blue
    buf = io.BytesIO()
    Image.fromarray(canvas).save(buf, "JPEG")
    return buf.getvalue()


# ── rendering: strategia 2 — numpy vectorized mask ───────────────────────────

def _render_vec_mask(min_v, max_v) -> bytes:
    canvas = np.ones((HEIGHT, WIDTH, 3), dtype=np.uint8) * 255
    center = HEIGHT // 2
    ys1 = np.clip((center + min_v * center).astype(np.int32), 0, HEIGHT - 1)
    ys2 = np.clip((center + max_v * center).astype(np.int32), 0, HEIGHT - 1)
    lo = np.minimum(ys1, ys2)
    hi = np.maximum(ys1, ys2)
    y_idx = np.arange(HEIGHT, dtype=np.int32)[:, None]   # (H, 1)
    mask = (y_idx >= lo) & (y_idx <= hi)                  # (H, W) bool
    canvas[mask] = [0, 0, 255]
    buf = io.BytesIO()
    Image.fromarray(canvas).save(buf, "JPEG")
    return buf.getvalue()


# ── rendering: strategia 3 — matplotlib fill_between ─────────────────────────

def _render_mpl_fill(min_v, max_v) -> bytes:
    dpi = 100
    fig, ax = plt.subplots(figsize=(WIDTH / dpi, HEIGHT / dpi), dpi=dpi)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.set_axis_off()
    ax.set_xlim(0, WIDTH - 1)
    ax.set_ylim(-1, 1)
    ax.fill_between(np.arange(WIDTH), min_v, max_v, color="blue", linewidth=0)
    buf = io.BytesIO()
    fig.savefig(buf, format="jpeg", dpi=dpi, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    return buf.getvalue()


# ── pipeline completa per ogni strategia ─────────────────────────────────────

def pipeline_current(file_path: str) -> bytes:
    return _render_current(*_load_envelope(file_path))

def pipeline_vec_mask(file_path: str) -> bytes:
    return _render_vec_mask(*_load_envelope(file_path))

def pipeline_mpl_fill(file_path: str) -> bytes:
    return _render_mpl_fill(*_load_envelope(file_path))


STRATEGIES = [
    ("current",  pipeline_current,  _render_current),
    ("vec-mask", pipeline_vec_mask, _render_vec_mask),
    ("mpl-fill", pipeline_mpl_fill, _render_mpl_fill),
]


# ── benchmark ─────────────────────────────────────────────────────────────────

def _time_fn(fn, *args, runs=RUNS):
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn(*args)
        times.append(time.perf_counter() - t0)
    return sum(times) / runs


def bench_file(file_path: str) -> dict:
    t_io = _time_fn(_load_envelope, file_path)
    envelope = _load_envelope(file_path)

    end_to_end = {}
    render_only = {}
    for label, full_fn, render_fn in STRATEGIES:
        end_to_end[label]  = _time_fn(full_fn, file_path)
        render_only[label] = _time_fn(render_fn, *envelope)

    return {
        "name":        os.path.basename(file_path),
        "size_mb":     os.path.getsize(file_path) / 1024 / 1024,
        "t_io":        t_io,
        "end_to_end":  end_to_end,
        "render_only": render_only,
    }


# ── report ────────────────────────────────────────────────────────────────────

def _sep(width): print("-" * width)

def _speedup_block(totals, labels, base):
    print(f"\nSpeedup vs '{base}':")
    for l in labels:
        if l == base:
            continue
        sp   = totals[base] / totals[l]
        diff = totals[base] - totals[l]
        flag = "  <-- migliore" if totals[l] == min(totals[l2] for l2 in labels if l2 != base) else ""
        print(f"  {l:<12}  {sp:5.2f}x  ({diff:+.4f}s){flag}")
    best = min(totals, key=lambda l: totals[l])
    print(f"Piu veloce: {best}  ({totals[best]:.4f}s totale)")


def main():
    files = sorted(AUDIO_DIR.glob("*.mp3"))
    if not files:
        print(f"Nessun file .mp3 trovato in {AUDIO_DIR}")
        return

    labels = [s[0] for s in STRATEGIES]
    col = 11

    print()
    print("=" * 90)
    print("BENCHMARK WAVEFORM END-TO-END  (file MP3 reali)")
    print(f"Risoluzione: {WIDTH}x{HEIGHT}px  |  Runs per file: {RUNS}")
    print("=" * 90)

    all_rows = []
    tot_e2e    = {l: 0.0 for l in labels}
    tot_render = {l: 0.0 for l in labels}
    tot_io = 0.0

    for f in files:
        row = bench_file(str(f))
        all_rows.append(row)
        tot_io += row["t_io"]
        for l in labels:
            tot_e2e[l]    += row["end_to_end"][l]
            tot_render[l] += row["render_only"][l]

    # ── tabella 1: end-to-end ────────────────────────────────────────────────
    hdr = f"{'File':<38} {'MB':>4}  {'I/O+env':>9}" + "".join(f"  {l:>{col}}" for l in labels)
    print(f"\n--- Pipeline completa (I/O + envelope + render) ---\n")
    print(hdr)
    _sep(len(hdr))
    for row in all_rows:
        line = f"{row['name']:<38} {row['size_mb']:>4.1f}  {row['t_io']:>9.4f}"
        for l in labels:
            line += f"  {row['end_to_end'][l]:>{col}.4f}"
        print(line)
    _sep(len(hdr))
    tot_line = f"{'TOTALE':<38} {'':>4}  {tot_io:>9.4f}"
    for l in labels:
        tot_line += f"  {tot_e2e[l]:>{col}.4f}"
    print(tot_line)
    _speedup_block(tot_e2e, labels, "current")

    # ── tabella 2: solo rendering ─────────────────────────────────────────────
    hdr2 = f"{'File':<38} {'MB':>4}" + "".join(f"  {l:>{col}}" for l in labels)
    print(f"\n--- Solo rendering (envelope gia calcolato, I/O escluso) ---\n")
    print(hdr2)
    _sep(len(hdr2))
    for row in all_rows:
        line = f"{row['name']:<38} {row['size_mb']:>4.1f}"
        for l in labels:
            line += f"  {row['render_only'][l]:>{col}.4f}"
        print(line)
    _sep(len(hdr2))
    tot_line2 = f"{'TOTALE':<38} {'':>4}"
    for l in labels:
        tot_line2 += f"  {tot_render[l]:>{col}.4f}"
    print(tot_line2)
    _speedup_block(tot_render, labels, "current")

    # ── breakdown tempi medi ──────────────────────────────────────────────────
    n = len(all_rows)
    print(f"\n--- Breakdown tempo medio per file ---\n")
    print(f"  {'I/O + envelope':<20}  {tot_io/n*1000:>7.2f} ms")
    for l in labels:
        r_ms  = tot_render[l] / n * 1000
        e2e_ms = tot_e2e[l]  / n * 1000
        pct   = r_ms / e2e_ms * 100 if e2e_ms else 0
        print(f"  render [{l}]{'':<8}  {r_ms:>7.2f} ms  ({pct:.0f}% del totale end-to-end)")

    print()
    print("=" * 90)


if __name__ == "__main__":
    main()
