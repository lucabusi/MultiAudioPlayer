"""
Benchmark lettura + decodifica MP3 su file reali in audio_test/.

Ogni metodo produce un array float32 mono normalizzato [-1, 1],
pronto per il calcolo dell'envelope.

Metodi:
  sf-fullload    soundfile.read()  — full-load in una sola chiamata (decoder: mpg123)
  sf-stream      soundfile streaming a blocchi + array pre-allocato (stesso decoder,
                 pattern I/O diverso: evita np.concatenate)
  miniaudio      miniaudio.mp3_read_file_f32()  — decoder dr_mp3 (C puro, diverso da mpg123)

Uso:
    python bench_decode.py
"""

import os
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import miniaudio
import librosa

AUDIO_DIR  = Path(__file__).parent / "audio_test"
BLOCK_SIZE = 262144   # frames per blocco in sf-stream (ottimale da benchmark precedente)
RUNS       = 5


# ── metodi di decodifica ──────────────────────────────────────────────────────

def decode_sf_fullload(file_path: str) -> np.ndarray:
    """soundfile: carica tutto in memoria in una chiamata."""
    samples, _ = sf.read(file_path, dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return samples


def decode_sf_stream(file_path: str) -> np.ndarray:
    """soundfile: streaming a blocchi con array pre-allocato (no np.concatenate)."""
    with sf.SoundFile(file_path) as f:
        total   = len(f)
        out     = np.empty(total, dtype=np.float32)
        pos     = 0
        while True:
            block = f.read(BLOCK_SIZE, dtype="float32")
            if len(block) == 0:
                break
            if block.ndim > 1:
                block = block.mean(axis=1)
            n = len(block)
            out[pos : pos + n] = block
            pos += n
    return out[:pos]


def decode_miniaudio(file_path: str) -> np.ndarray:
    """miniaudio: decoder dr_mp3, decodifica + downmix a mono in C."""
    decoded = miniaudio.mp3_read_file_f32(file_path)
    samples = np.frombuffer(decoded.samples, dtype=np.float32)
    if decoded.nchannels > 1:
        samples = samples.reshape(-1, decoded.nchannels).mean(axis=1)
    return samples


def decode_librosa_srNone(file_path: str) -> np.ndarray:
    """librosa: carica e decodifica con resampling opzionale, output float32 mono."""
    samples, _ = librosa.load(file_path, sr=None, mono=True, dtype=np.float32)
    return samples

def decode_librosa_sr11(file_path: str) -> np.ndarray:
    """librosa: carica e decodifica con resampling opzionale, output float32 mono."""
    samples, _ = librosa.load(file_path, sr=11025, mono=True, dtype=np.float32)
    return samples


DECODERS = [
    ("sf-fullload", decode_sf_fullload),
    ("sf-stream",   decode_sf_stream),
    ("miniaudio",   decode_miniaudio),
    ("librosa_srNone", decode_librosa_srNone),
    ("librosa_sr11", decode_librosa_sr11),
]


# ── benchmark ─────────────────────────────────────────────────────────────────

def _time_runs(fn, arg, runs=RUNS):
    times = []
    result = None
    for _ in range(runs):
        t0 = time.perf_counter()
        result = fn(arg)
        times.append(time.perf_counter() - t0)
    return sum(times) / runs, min(times), result


def bench_file(file_path: str) -> dict:
    size_mb  = os.path.getsize(file_path) / 1024 / 1024
    timings  = {}
    minimums = {}
    outputs  = {}
    for label, fn in DECODERS:
        avg, mn, samples = _time_runs(fn, file_path)
        timings[label]  = avg
        minimums[label] = mn
        outputs[label]  = samples
    return {
        "name":    os.path.basename(file_path),
        "size_mb": size_mb,
        "timings": timings,
        "minimums": minimums,
        "outputs": outputs,
    }


# ── verifica coerenza output ──────────────────────────────────────────────────

def _check_consistency(outputs: dict) -> str:
    """Controlla che tutti i decoder producano lo stesso numero di campioni (±1%)."""
    lengths = {l: len(s) for l, s in outputs.items()}
    ref = next(iter(lengths.values()))
    ok = all(abs(v - ref) / ref < 0.01 for v in lengths.values())
    lens = "  ".join(f"{l}:{v}" for l, v in lengths.items())
    return ("OK" if ok else "DIFF") + f"  [{lens}]"


# ── report ────────────────────────────────────────────────────────────────────

def main():
    files = sorted(AUDIO_DIR.glob("*.mp3"))
    if not files:
        print(f"Nessun file .mp3 trovato in {AUDIO_DIR}")
        return

    labels = [d[0] for d in DECODERS]
    col    = 13

    print()
    print("=" * 85)
    print("BENCHMARK DECODIFICA MP3  --  lettura + decode -> float32 mono")
    print(f"Runs per file: {RUNS}  |  Block size sf-stream: {BLOCK_SIZE} frames")
    print(f"sf-fullload / sf-stream: decoder mpg123 (libsndfile)")
    print(f"miniaudio:               decoder dr_mp3  (C puro)")
    print(f"librosa:                 audioread/soundfile backend, sr=None mono")
    print("=" * 85)

    all_rows  = []
    tot_avg   = {l: 0.0 for l in labels}
    tot_min   = {l: 0.0 for l in labels}

    for f in files:
        row = bench_file(str(f))
        all_rows.append(row)
        for l in labels:
            tot_avg[l] += row["timings"][l]
            tot_min[l] += row["minimums"][l]

    # ── tabella tempi medi ───────────────────────────────────────────────────
    hdr = f"{'File':<38} {'MB':>4}" + "".join(f"  {l:>{col}}" for l in labels) + "  consistenza"
    print(f"\nTempi medi ({RUNS} runs):\n")
    print(hdr)
    print("-" * len(hdr))
    for row in all_rows:
        line = f"{row['name']:<38} {row['size_mb']:>4.1f}"
        best = min(row["timings"], key=lambda l: row["timings"][l])
        for l in labels:
            t = row["timings"][l]
            marker = "*" if l == best else " "
            line += f"  {t:>{col-1}.3f}{marker}"
        line += f"  {_check_consistency(row['outputs'])}"
        print(line)
    print("-" * len(hdr))
    tot_line = f"{'TOTALE':<38} {'':>4}"
    best_tot = min(tot_avg, key=lambda l: tot_avg[l])
    for l in labels:
        marker = "*" if l == best_tot else " "
        tot_line += f"  {tot_avg[l]:>{col-1}.3f}{marker}"
    print(tot_line)

    # ── tabella best-of (min run) ────────────────────────────────────────────
    print(f"\nTempi migliori (best of {RUNS} runs — meno rumore da OS/cache):\n")
    hdr2 = f"{'File':<38} {'MB':>4}" + "".join(f"  {l:>{col}}" for l in labels)
    print(hdr2)
    print("-" * len(hdr2))
    for row in all_rows:
        line = f"{row['name']:<38} {row['size_mb']:>4.1f}"
        best = min(row["minimums"], key=lambda l: row["minimums"][l])
        for l in labels:
            t = row["minimums"][l]
            marker = "*" if l == best else " "
            line += f"  {t:>{col-1}.3f}{marker}"
        print(line)
    print("-" * len(hdr2))
    tot_min_line = f"{'TOTALE':<38} {'':>4}"
    best_tot_min = min(tot_min, key=lambda l: tot_min[l])
    for l in labels:
        marker = "*" if l == best_tot_min else " "
        tot_min_line += f"  {tot_min[l]:>{col-1}.3f}{marker}"
    print(tot_min_line)

    # ── speedup ──────────────────────────────────────────────────────────────
    base = "sf-fullload"
    print(f"\nSpeedup vs '{base}' (tempi medi):")
    for l in labels:
        if l == base:
            continue
        sp   = tot_avg[base] / tot_avg[l]
        diff = tot_avg[base] - tot_avg[l]
        flag = "  <-- migliore" if tot_avg[l] == min(tot_avg[l2] for l2 in labels if l2 != base) else ""
        print(f"  {l:<14}  {sp:5.2f}x  ({diff:+.3f}s sul totale){flag}")

    best_label = min(tot_avg, key=lambda l: tot_avg[l])
    print(f"\nDecoder piu veloce (media): {best_label}  ({tot_avg[best_label]:.3f}s totale)")
    best_label_min = min(tot_min, key=lambda l: tot_min[l])
    print(f"Decoder piu veloce (best):  {best_label_min}  ({tot_min[best_label_min]:.3f}s totale)")

    # ── throughput MB/s ──────────────────────────────────────────────────────
    total_mb = sum(r["size_mb"] for r in all_rows)
    print(f"\nThroughput (totale {total_mb:.1f} MB):")
    for l in labels:
        tput = total_mb / tot_avg[l]
        print(f"  {l:<14}  {tput:5.1f} MB/s")

    print()
    print("* = migliore per riga")
    print("=" * 85)


if __name__ == "__main__":
    main()
