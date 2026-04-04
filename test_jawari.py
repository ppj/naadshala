#!/usr/bin/env python3
"""
Generate test files for jawari verification in multiple formats.
Creates 3 test cases (gs2_P, c3_P, a3_P) as:
  - Single-cycle OGG (what Android app plays)
  - Single-cycle CAF/AAC (what iOS app plays)
  - 5x-looped WAV (for direct listening comparison)
"""

import subprocess
import tempfile
import numpy as np
from pathlib import Path
import soundfile as sf
from generate_tanpura_files import (
    SA_FREQUENCIES,
    SAMPLE_RATE,
    generate_tanpura_cycle,
)

TEST_CASES = [
    ("gs2", "P"),  # Low end
    ("c3", "P"),   # Middle
    ("a3", "P"),   # High end
]
LOOP_COUNT = 5
OUTPUT_DIR = Path(__file__).parent / "output" / "test_jawari"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for sa_name, string1_note in TEST_CASES:
        sa_freq = SA_FREQUENCIES[sa_name]
        stem = f"{sa_name}_{string1_note}"

        print(f"Generating {stem} (Sa={sa_freq:.2f} Hz)...")
        cycle = generate_tanpura_cycle(sa_freq, string1_note)

        _, tmp_name = tempfile.mkstemp(suffix=".wav")
        tmp_path = Path(tmp_name)
        try:
            sf.write(tmp_path, cycle, SAMPLE_RATE, format="WAV", subtype="PCM_16")

            # Single-cycle OGG (matches Android app format)
            ogg_path = OUTPUT_DIR / f"{stem}.ogg"
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(tmp_path),
                 "-c:a", "libvorbis", "-q:a", "10", str(ogg_path)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print(f"  -> {ogg_path}")

            # Single-cycle CAF/ALAC (matches iOS app format, lossless)
            caf_path = OUTPUT_DIR / f"{stem}.caf"
            subprocess.run(
                ["afconvert", str(tmp_path), str(caf_path),
                 "-f", "caff", "-d", "alac"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print(f"  -> {caf_path}")
        finally:
            tmp_path.unlink(missing_ok=True)

        # 5x-looped WAV (for direct A/B listening on desktop)
        looped = np.tile(cycle, (LOOP_COUNT, 1))
        wav_path = OUTPUT_DIR / f"{stem}_x{LOOP_COUNT}.wav"
        sf.write(wav_path, looped, SAMPLE_RATE, format="WAV", subtype="PCM_16")
        print(f"  -> {wav_path} ({looped.shape[0] / SAMPLE_RATE:.1f}s)")

    print(f"\nDone. Files in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
