#!/usr/bin/env python3
"""
Generate looped test WAVs for jawari verification.
Creates 3 files (gs2_P, c3_P, a3_P) each looped 5 times as a single WAV.
"""

import numpy as np
from pathlib import Path
import soundfile as sf
from generate_tanpura_files import (
    SA_FREQUENCIES,
    generate_tanpura_cycle,
)

TEST_CASES = [
    ("gs2", "P"),  # Low end
    ("c3", "P"),   # Middle
    ("a3", "P"),   # High end
]
LOOP_COUNT = 5
OUTPUT_DIR = Path(__file__).parent / "output" / "test_jawari"
SAMPLE_RATE = 44100


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for sa_name, string1_note in TEST_CASES:
        sa_freq = SA_FREQUENCIES[sa_name]
        stem = f"{sa_name}_{string1_note}"

        print(f"Generating {stem} (Sa={sa_freq:.2f} Hz)...")
        cycle = generate_tanpura_cycle(sa_freq, string1_note)

        # Loop 5 times
        looped = np.tile(cycle, (LOOP_COUNT, 1))
        out_path = OUTPUT_DIR / f"{stem}_x{LOOP_COUNT}.wav"
        sf.write(out_path, looped, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        print(f"  -> {out_path} ({looped.shape[0] / SAMPLE_RATE:.1f}s)")

    print(f"\nDone. Files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
