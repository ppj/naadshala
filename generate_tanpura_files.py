#!/usr/bin/env python3
"""
Generate pre-recorded audio files for tanpura playback.
Creates 45 files: 3 String 1 notes (P, m, N) × 15 Sa values (G#2 to A#3)

Outputs two formats:
  - OGG Vorbis → output/tanpura/          (Android / Swaramandal)
  - CAF/AAC    → output/tanpura_caf/       (iOS / iSwarmandal)
    Requires macOS afconvert (pre-installed on all Macs, not available on Linux).

Harmonic structure extracted from real Calcutta-standard male tanpura recording
via spectral analysis (FFT). Key finding: H7 is the dominant harmonic (1.00),
representing the authentic jawari effect, not H4/H11/H17 as commonly assumed.

Source: https://www.india-instruments.com/tanpura-details/calcutta-standard-male-tanpura.html
Analysis: Extracted String 2 (mid Sa - tonic) harmonics from stable 1-2s segment
Validation: C3 frequency detected at 131.25 Hz (0.3% deviation from 130.81 Hz)

DESIGN NOTE: Asset Generation Strategy
--------------------------------------
Currently, generated assets (45 OGG files, ~6MB) are committed to git.

Tradeoffs:
✅ Fast builds - no generation overhead
✅ Simple setup - no Python dependency for contributors/CI
✅ Guaranteed consistency across all builds
❌ ~6MB in git history (acceptable for now)
❌ Re-tweaking audio params requires re-committing all files

Alternative (future consideration):
- Move to Gradle build task that generates assets at build-time
- Only commit this script, not the generated assets
- Would require Python venv setup in CI/CD and for all contributors
- Consider if synthesis params change frequently or repo size becomes problematic
"""

import subprocess
import tempfile
import numpy as np
from pathlib import Path
import soundfile as sf

# Audio configuration
SAMPLE_RATE = 44100
SUSTAIN_DURATION = 10.0  # seconds per string (increased for smoother looping)
BEAT_INTERVAL = 0.6  # 100 BPM
CYCLE_BEATS = 6
CYCLE_DURATION = BEAT_INTERVAL * CYCLE_BEATS

# Just Intonation ratios
NOTE_RATIOS = {
    "S": 1.0,
    "r": 16.0 / 15.0,
    "R": 9.0 / 8.0,
    "g": 6.0 / 5.0,
    "G": 5.0 / 4.0,
    "m": 4.0 / 3.0,
    "M": 45.0 / 32.0,
    "P": 3.0 / 2.0,
    "d": 8.0 / 5.0,
    "D": 5.0 / 3.0,
    "n": 16.0 / 9.0,
    "N": 15.0 / 8.0,
}

# Sa values from G#2 to A#3 (15 semitones)
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

# String 1 notes to generate (most common)
STRING1_NOTES = ["P", "m", "N"]

# Harmonic structure extracted from real tanpura recording (String 2 - tonic Sa)
# Source: https://www.india-instruments.com/tanpura-details/calcutta-standard-male-tanpura.html
# Key finding: H7 is dominant (1.00) representing the authentic jawari effect
HARMONICS = [
    (1.0, 0.26),  # Fundamental
    (2.0, 0.26),  # Octave
    (3.0, 0.04),  # Fifth
    (4.0, 0.81),  # Jawari cluster
    (5.0, 0.49),
    (6.0, 0.49),
    (7.0, 1.00),  # Dominant jawari peak
    (8.0, 0.24),
    (9.0, 0.54),  # Secondary peak
    (10.0, 0.34),
    (11.0, 0.45),
    (12.0, 0.08),
    (13.0, 0.07),
    (14.0, 0.04),
    (15.0, 0.03),
    (16.0, 0.05),
    (17.0, 0.33),  # Tertiary peak
    (18.0, 0.05),
    (19.0, 0.28),
    (20.0, 0.09),
]


def generate_string_pluck(
    frequency, duration, amplitude_variation=1.0, attack_duration=0.8, volume=0.5
):
    """
    Generate a single string pluck with realistic tanpura timbre using additive synthesis.

    Envelope is multiplicative (sigmoid attack × exponential decay) so there is no
    amplitude discontinuity at the attack/decay join. Decay is intentionally slow
    (0.112) to allow string overlaps in the full cycle.

    Sinusoidal AM is omitted deliberately — per-harmonic amplitude modulation produced
    flangy/tremolo artefacts rather than authentic jawari. The jawari waxing/waning
    effect instead emerges from inter-harmonic beating driven by the inharmonicity term.
    """
    num_samples = int(SAMPLE_RATE * duration)
    t = np.arange(num_samples) / SAMPLE_RATE

    # Envelope: multiplicative sigmoid attack × exponential decay (no discontinuity)
    attack = 1.0 / (1.0 + np.exp(-10.0 * (t / attack_duration - 0.5)))
    decay = np.exp(-(t - attack_duration).clip(min=0) * 0.112)
    envelope = attack * decay

    inharmonicity_coeff = 0.0004

    samples = np.zeros(num_samples)
    for harmonic_num, amplitude in HARMONICS:
        # Inharmonicity: harmonics are slightly sharp
        inharmonic_factor = np.sqrt(
            1.0 + inharmonicity_coeff * harmonic_num * harmonic_num
        )
        harmonic_freq = frequency * harmonic_num * inharmonic_factor
        phase = 2.0 * np.pi * harmonic_freq * t

        # Frequency-dependent damping
        harmonic_decay = np.exp(-t * (0.112 + harmonic_num * harmonic_num * 0.003))

        # Phase variation
        harmonic_phase_shift = np.sin(harmonic_num * 0.7) * 0.05

        samples += amplitude * harmonic_decay * np.sin(phase + harmonic_phase_shift)

    # Apply envelope, amplitude variation, and volume
    amplitude_sum = sum(amp for _, amp in HARMONICS)
    samples *= envelope * amplitude_variation * volume / amplitude_sum
    samples = np.clip(samples, -1.0, 1.0)  # Soft clipping for natural saturation
    samples *= 0.8  # Scale to fuller amplitude

    return samples


def generate_tanpura_cycle(sa_frequency, string1_note):
    """Generate one complete 6-beat tanpura cycle as stereo audio."""
    ratio_note = string1_note  # Direct mapping: P, m, N

    # String frequencies: 1=variable lower octave, 2&3=tonic Sa, 4=lower Sa
    string1_freq = sa_frequency * NOTE_RATIOS[ratio_note] / 2.0
    string2_freq = sa_frequency
    string3_freq = sa_frequency
    string4_freq = sa_frequency / 2.0

    # Generate individual strings with different attack durations
    print(f"  Generating String 1 ({string1_note})...")
    string1_samples = generate_string_pluck(
        string1_freq, SUSTAIN_DURATION, amplitude_variation=0.98, attack_duration=0.63
    )

    print(f"  Generating String 2 (Sa)...")
    string2_samples = generate_string_pluck(
        string2_freq, SUSTAIN_DURATION, amplitude_variation=1.0, attack_duration=0.90
    )

    print(f"  Generating String 3 (Sa)...")
    string3_samples = generate_string_pluck(
        string3_freq, SUSTAIN_DURATION, amplitude_variation=1.0, attack_duration=0.90
    )

    print(f"  Generating String 4 (lower Sa)...")
    string4_samples = generate_string_pluck(
        string4_freq, SUSTAIN_DURATION, amplitude_variation=0.96, attack_duration=0.63
    )

    # Mix strings with traditional plucking pattern (beats: 1, -, 3, 4, 5, -)
    pluck_offsets = [0, 2, 3, 4]  # String1, String2, String3, String4
    all_strings = [string1_samples, string2_samples, string3_samples, string4_samples]

    # Create mono buffer for one complete cycle
    beat_interval_samples = int(SAMPLE_RATE * BEAT_INTERVAL)
    cycle_size = int(SAMPLE_RATE * CYCLE_DURATION)
    mono_buffer = np.zeros(cycle_size)

    # Mix all strings with their timing offsets
    for string_index, string_samples in enumerate(all_strings):
        offset = pluck_offsets[string_index] * beat_interval_samples
        for i in range(len(string_samples)):
            # Wrap around if string extends beyond cycle boundary
            buffer_index = (offset + i) % cycle_size
            mono_buffer[buffer_index] += string_samples[i]

    # Normalize mono buffer (leave headroom)
    max_amp = np.max(np.abs(mono_buffer))
    if max_amp > 0.85:
        mono_buffer *= 0.85 / max_amp

    # Create stereo with Haas effect (20ms delay)
    stereo_timing_offset = int(SAMPLE_RATE * 0.020)
    panning_l = 0.75
    panning_r = 0.75
    stereo_buffer = np.zeros((cycle_size, 2))

    for i in range(cycle_size):
        stereo_buffer[i, 0] = mono_buffer[i] * panning_l  # Left channel
        # Right channel with timing offset
        right_index = (i + stereo_timing_offset) % cycle_size
        stereo_buffer[i, 1] = mono_buffer[right_index] * panning_r

    return stereo_buffer


def main():
    """Generate all tanpura audio files (OGG for Android, CAF for iOS)."""
    ogg_dir = Path(__file__).parent / "output" / "tanpura"
    caf_dir = Path(__file__).parent / "output" / "tanpura_caf"
    ogg_dir.mkdir(parents=True, exist_ok=True)
    caf_dir.mkdir(parents=True, exist_ok=True)

    total_files = len(SA_FREQUENCIES) * len(STRING1_NOTES)
    print(f"Generating {total_files} tanpura files in OGG + CAF formats...")
    print(f"  OGG → {ogg_dir}")
    print(f"  CAF → {caf_dir}")
    print()

    file_count = 0

    # Generate all combinations
    for sa_name, sa_freq in SA_FREQUENCIES.items():
        for string1_note in STRING1_NOTES:
            file_count += 1
            stem = f"{sa_name}_{string1_note}"

            print(f"[{file_count}/{total_files}] Generating {stem}...")
            print(f"  Sa = {sa_freq:.2f} Hz, String 1 = {string1_note}")

            # Generate the audio once, write to both formats
            audio_data = generate_tanpura_cycle(sa_freq, string1_note)

            sf.write(ogg_dir / f"{stem}.ogg", audio_data, SAMPLE_RATE,
                     format="OGG", subtype="VORBIS")
            print(f"  ✓ OGG written")

            _, tmp_name = tempfile.mkstemp(suffix=".wav")
            tmp_path = Path(tmp_name)
            try:
                sf.write(tmp_path, audio_data, SAMPLE_RATE, format="WAV", subtype="PCM_16")
                subprocess.run(
                    [
                        "afconvert",
                        str(tmp_path),
                        str(caf_dir / f"{stem}.caf"),
                        "-f", "caff",   # CAF container
                        "-d", "aac",    # AAC codec
                        "-b", "128000", # 128 kbps
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            finally:
                tmp_path.unlink(missing_ok=True)
            print(f"  ✓ CAF written\n")

    print(f"\n{'=' * 60}")
    print(f"Generation complete! {total_files} × 2 formats.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
