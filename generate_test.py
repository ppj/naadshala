#!/usr/bin/env python3
"""Generate test OGG files for gs2_P, c3_P, a3_P using the hybrid synthesizer."""

import subprocess
import tempfile
from pathlib import Path
import soundfile as sf
from generate_tanpura_hybrid import SA_FREQUENCIES, SAMPLE_RATE, generate_tanpura_cycle

TEST_CASES = [
    ("gs2", "P"),
    ("c3", "P"),
    ("a3", "P"),
]
OUTPUT_DIR = Path(__file__).parent / "output" / "tanpura"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for sa_name, note in TEST_CASES:
        sa_freq = SA_FREQUENCIES[sa_name]
        stem = f"{sa_name}_{note}"
        print(f"Generating {stem} (Sa={sa_freq:.2f} Hz)...")
        cycle = generate_tanpura_cycle(sa_freq, note)

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        try:
            sf.write(tmp_path, cycle, SAMPLE_RATE, format="WAV", subtype="PCM_16")
            ogg_path = OUTPUT_DIR / f"{stem}.ogg"
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(tmp_path),
                 "-c:a", "libvorbis", "-q:a", "10", str(ogg_path)],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            print(f"  -> {ogg_path}")
        finally:
            tmp_path.unlink(missing_ok=True)

    print("Done.")


if __name__ == "__main__":
    main()
