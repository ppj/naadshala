#!/usr/bin/env python3
"""
Generate swarmandal-like plucks for training mode using Karplus-Strong algorithm.
Based on generate_reference_plucks.py but with longer sustain.
"""

import numpy as np
from pathlib import Path
import soundfile as sf

# Audio configuration
SAMPLE_RATE = 44100
PLUCK_DURATION = 3.0  # seconds - longer than guitar plucks

# Swarmandal parameters (vs guitar: decay=0.996, brightness=0.4)
DECAY = 0.997  # Slightly faster decay
BRIGHTNESS = 0.95  # Very bright/sharp

# Just Intonation ratios for all 12 swars
SWARS = [
    ("S", 1.0),
    ("r", 16.0 / 15.0),
    ("R", 9.0 / 8.0),
    ("g", 6.0 / 5.0),
    ("G", 5.0 / 4.0),
    ("m", 4.0 / 3.0),
    ("M", 45.0 / 32.0),
    ("P", 3.0 / 2.0),
    ("d", 8.0 / 5.0),
    ("D", 5.0 / 3.0),
    ("n", 16.0 / 9.0),
    ("N", 15.0 / 8.0),
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


def karplus_strong_pluck(frequency, duration, decay=DECAY, brightness=BRIGHTNESS):
    """
    Generate a pluck using Karplus-Strong algorithm.
    Same as guitar plucks but with configurable decay for longer sustain.
    """
    num_samples = int(SAMPLE_RATE * duration)
    delay_length = int(SAMPLE_RATE / frequency)

    # Initialize delay line with random noise
    delay_line = np.random.uniform(-1.0, 1.0, delay_length)

    output = np.zeros(num_samples)

    # Karplus-Strong feedback loop
    for i in range(num_samples):
        output[i] = delay_line[0]

        # Low-pass filter
        filtered = (delay_line[0] + delay_line[1]) / 2.0
        new_sample = brightness * delay_line[0] + (1.0 - brightness) * filtered
        new_sample *= decay

        delay_line = np.roll(delay_line, -1)
        delay_line[-1] = new_sample

    # Fade in/out to avoid clicks
    fade_in_samples = int(SAMPLE_RATE * 0.01)
    fade_out_samples = int(SAMPLE_RATE * 0.5)  # 500ms fade out for smooth decay
    output[:fade_in_samples] *= np.linspace(0.0, 1.0, fade_in_samples)
    output[-fade_out_samples:] *= np.linspace(1.0, 0.0, fade_out_samples)

    # Normalize
    max_amp = np.max(np.abs(output))
    if max_amp > 0:
        output = output / max_amp * 0.8

    return output


def main():
    """Generate all swarmandal pluck files."""
    output_dir = Path(__file__).parent / "output" / "swarmandal"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating swarmandal files in: {output_dir}")
    print(f"Total files: {len(SA_FREQUENCIES)} Sa x {len(SWARS)} swars + {len(SA_FREQUENCIES)} ati-taar Sa = {len(SA_FREQUENCIES) * len(SWARS) + len(SA_FREQUENCIES)}")
    print()

    file_count = 0
    total_files = len(SA_FREQUENCIES) * len(SWARS) + len(SA_FREQUENCIES)

    for sa_name, sa_freq in SA_FREQUENCIES.items():
        for swar_index, (swar_name, swar_ratio) in enumerate(SWARS, start=1):
            file_count += 1
            frequency = sa_freq * swar_ratio
            filename = f"{sa_name}_{swar_index}_{swar_name}.ogg"
            filepath = output_dir / filename

            print(f"[{file_count}/{total_files}] {filename} ({frequency:.2f} Hz)")

            audio_data = karplus_strong_pluck(frequency, PLUCK_DURATION)
            sf.write(filepath, audio_data, SAMPLE_RATE, format="OGG", subtype="VORBIS")

    # Generate ati-taar Sa (two octaves above)
    for sa_name, sa_freq in SA_FREQUENCIES.items():
        file_count += 1
        frequency = sa_freq * 4.0  # Two octaves up
        filename = f"{sa_name}_S2.ogg"
        filepath = output_dir / filename

        print(f"[{file_count}/{total_files}] {filename} ({frequency:.2f} Hz)")

        audio_data = karplus_strong_pluck(frequency, PLUCK_DURATION)
        sf.write(filepath, audio_data, SAMPLE_RATE, format="OGG", subtype="VORBIS")

    print(f"\nDone! {total_files} files in {output_dir}")


if __name__ == "__main__":
    main()
