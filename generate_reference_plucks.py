#!/usr/bin/env python3
"""
Generate reference note plucks for training mode using Karplus-Strong algorithm.
This script creates guitar-like pluck sounds to help users match target notes.

DESIGN NOTE: Asset Generation Strategy
--------------------------------------
Currently, generated assets (180 OGG files, ~2.1MB) are committed to git.

Tradeoffs:
✅ Fast builds - no generation overhead
✅ Simple setup - no Python dependency for contributors/CI
✅ Guaranteed consistency across all builds
❌ 2.1MB in git history (acceptable for now)
❌ Re-tweaking audio params requires re-committing all files

Alternative (future consideration):
- Move to Gradle build task that generates assets at build-time
- Only commit this script, not the generated assets
- Would require Python venv setup in CI/CD and for all contributors
- Consider if synthesis params change frequently or repo size becomes problematic
"""

import numpy as np
from pathlib import Path
import soundfile as sf

# Audio configuration
SAMPLE_RATE = 44100
PLUCK_DURATION = 1.0  # seconds - quick reference pluck for training

# Just Intonation ratios for all 12 swars (in chromatic order)
# Ordered list to maintain numbering: 1-12
SWARS = [
    ("S", 1.0),           # 1
    ("r", 16.0 / 15.0),   # 2 - komal Re
    ("R", 9.0 / 8.0),     # 3 - shuddh Re
    ("g", 6.0 / 5.0),     # 4 - komal Ga
    ("G", 5.0 / 4.0),     # 5 - shuddh Ga
    ("m", 4.0 / 3.0),     # 6 - shuddh Ma
    ("M", 45.0 / 32.0),   # 7 - teevra Ma
    ("P", 3.0 / 2.0),     # 8
    ("d", 8.0 / 5.0),     # 9 - komal Dha
    ("D", 5.0 / 3.0),     # 10 - shuddh Dha
    ("n", 16.0 / 9.0),    # 11 - komal Ni
    ("N", 15.0 / 8.0),    # 12 - shuddh Ni
]

# All 15 Sa values from G#2 to A#3
SA_FREQUENCIES = {
    "gs2": 103.83,
    "a2": 110.00,
    "as2": 116.54,
    "b2": 123.47,
    "c3": 130.81,
    "cs3": 138.59,
    "d3": 146.83,
    "ds3": 155.56,
    "e3": 164.81,
    "f3": 174.61,
    "fs3": 185.00,
    "g3": 196.00,
    "gs3": 207.65,
    "a3": 220.00,
    "as3": 233.08,
}


def karplus_strong_pluck(frequency, duration, decay=0.996, brightness=0.5):
    """
    Generate a guitar-like pluck using Karplus-Strong algorithm.

    Parameters:
    - frequency: Fundamental frequency in Hz
    - duration: Duration in seconds
    - decay: Damping factor (0.99-0.999 for realistic decay)
    - brightness: Filter amount (0=dark/mellow, 1=bright/harsh)
    """
    num_samples = int(SAMPLE_RATE * duration)

    # Calculate delay line length (buffer size)
    delay_length = int(SAMPLE_RATE / frequency)

    # Initialize delay line with random noise (simulates initial pluck)
    delay_line = np.random.uniform(-1.0, 1.0, delay_length)

    # Output buffer
    output = np.zeros(num_samples)

    # Karplus-Strong feedback loop
    for i in range(num_samples):
        # Output current sample
        output[i] = delay_line[0]

        # Simple low-pass filter: average of first two samples
        # brightness controls the mix between filtered and unfiltered
        filtered = (delay_line[0] + delay_line[1]) / 2.0
        new_sample = brightness * delay_line[0] + (1.0 - brightness) * filtered

        # Apply decay and feedback
        new_sample *= decay

        # Shift delay line and add new sample at end
        delay_line = np.roll(delay_line, -1)
        delay_line[-1] = new_sample

    # Apply gentle envelope to avoid clicks at start/end
    fade_in_samples = int(SAMPLE_RATE * 0.01)  # 10ms fade in
    fade_out_samples = int(SAMPLE_RATE * 0.1)  # 100ms fade out

    # Fade in
    output[:fade_in_samples] *= np.linspace(0.0, 1.0, fade_in_samples)

    # Fade out
    output[-fade_out_samples:] *= np.linspace(1.0, 0.0, fade_out_samples)

    # Normalize to prevent clipping
    max_amp = np.max(np.abs(output))
    if max_amp > 0:
        output = output / max_amp * 0.8  # Leave some headroom

    return output


def main():
    """Generate all reference pluck files for training mode."""
    # Create output directory
    output_dir = Path(__file__).parent / "output" / "plucks"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating reference pluck files in: {output_dir}")
    print(f"Total files: {len(SA_FREQUENCIES)} Sa values × {len(SWARS)} swars = {len(SA_FREQUENCIES) * len(SWARS)}")
    print()

    file_count = 0
    total_files = len(SA_FREQUENCIES) * len(SWARS)

    # Generate all Sa × Swar combinations
    for sa_name, sa_freq in SA_FREQUENCIES.items():
        for swar_index, (swar_name, swar_ratio) in enumerate(SWARS, start=1):
            file_count += 1

            # Calculate actual frequency using Just Intonation
            frequency = sa_freq * swar_ratio

            # Filename format: <sa>_<number>_<swar>.ogg
            # Example: cs3_1_S.ogg, cs3_2_r.ogg, cs3_3_R.ogg, etc.
            filename = f"{sa_name}_{swar_index}_{swar_name}.ogg"
            filepath = output_dir / filename

            print(f"[{file_count}/{total_files}] {filename}")
            print(f"  Sa={sa_name} ({sa_freq:.2f} Hz), Swar={swar_index}={swar_name} ({swar_ratio:.4f})")
            print(f"  → Frequency={frequency:.2f} Hz")

            # Generate the pluck using Karplus-Strong
            audio_data = karplus_strong_pluck(
                frequency=frequency,
                duration=PLUCK_DURATION,
                decay=0.996,      # Moderate decay for realistic sustain
                brightness=0.4    # Slightly mellow tone
            )

            # Save as OGG Vorbis (mono)
            sf.write(filepath, audio_data, SAMPLE_RATE, format="OGG", subtype="VORBIS")
            print(f"  ✓ Saved\n")

    print(f"\n{'=' * 60}")
    print(f"Generation complete! {total_files} files created.")
    print(f"Output directory: {output_dir}")
    print(f"Total size: ~{total_files * 10 // 1024} MB (estimated)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
