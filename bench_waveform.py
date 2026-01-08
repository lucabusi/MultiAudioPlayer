import os
import time
import glob
import statistics
from waveform import generate_waveform_rosa, generate_waveform_HS

TEST_DIR = os.path.join(os.path.dirname(__file__), 'audio_test')
MP3S = [
    os.path.join(TEST_DIR, 'dtmf_Audacity_1.0.mp3'),
    os.path.join(TEST_DIR, 'mitra.mp3'),
    os.path.join(TEST_DIR, 'occhi_di_gatto.mp3'),
    os.path.join(TEST_DIR, 'pink_panther.mp3'),
    os.path.join(TEST_DIR, 'Santo-Poi.mp3'),
    os.path.join(TEST_DIR, 'Sigla_lunga.mp3'),
    os.path.join(TEST_DIR, 'The_Lyre_of_Orpheus.mp3')
]

REPEATS = 3

def run_benchmark(func, path):
    times = []
    for i in range(REPEATS):
        # remove output file if exists
        out = os.path.basename(path) + '.jpg'
        if os.path.exists(out):
            try:
                os.remove(out)
            except Exception:
                pass
        t0 = time.perf_counter()
        try:
            func(path, None)
        except Exception as e:
            print(f"Error running {func.__name__} on {path}: {e}")
            return None
        t1 = time.perf_counter()
        times.append(t1 - t0)
    return statistics.mean(times), statistics.stdev(times) if len(times) > 1 else 0.0

if __name__ == '__main__':
    print('Benchmarking waveform generation')
    for mp3 in MP3S:
        if not os.path.exists(mp3):
            print(f"Skipping missing {mp3}")
            continue
        size = os.path.getsize(mp3)
        print(f"\nFile: {mp3} (size {size/1024:.1f} KB)")
        for func in (generate_waveform_rosa, generate_waveform_HS):
            name = func.__name__
            print(f" Running {name}...")
            result = run_benchmark(func, mp3)
            if result is None:
                print(f"  {name}: error")
            else:
                mean, stdev = result
                print(f"  {name}: mean {mean:.3f}s, stdev {stdev:.3f}s (n={REPEATS})")
    print('\nDone')
