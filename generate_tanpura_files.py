#!/usr/bin/env python3
"""
DEPRECATED: Use generate_tanpura_files_v2.py instead.

This script uses a Karplus-Strong waveguide model with bridge termination. While
it was the first implementation to produce convincing jawari, the delay-line
feedback creates lo-fi artifacts that the additive synthesis in v2 avoids.
Kept for reference only — do not use for asset generation.

---

Generate pre-recorded audio files for tanpura playback.
Creates 45 files: 3 String 1 notes (P, m, N) × 15 Sa values (G#2 to A#3)

Outputs two formats:
  - OGG Vorbis → output/tanpura_ogg/       (Android / Swaramandal)
  - CAF/ALAC   → output/tanpura_caf/       (iOS / iSwarmandal, lossless)
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
from scipy.signal import iirpeak, lfilter
from pathlib import Path
import soundfile as sf

# Audio configuration
SAMPLE_RATE = 44100
SUSTAIN_DURATION = 10.0  # seconds per string (used by non-tanpura generators if needed)
BEAT_INTERVAL = 0.6  # seconds between plucks
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
    (1.0, 0.20),   # Fundamental (was 0.26)
    (2.0, 0.35),   # Octave — real H2 is stronger (was 0.26)
    (3.0, 0.06),   # Fifth (was 0.04)
    (4.0, 1.00),   # H4 IS the strongest in real sample (was 0.81)
    (5.0, 0.53),   # (was 0.49)
    (6.0, 0.41),   # (was 0.49)
    (7.0, 0.99),   # Nearly equal to H4 — jawari peak (was 1.00)
    (8.0, 0.31),   # (was 0.24)
    (9.0, 0.30),   # Was overestimated (was 0.54)
    (10.0, 0.15),  # (was 0.34)
    (11.0, 0.19),  # (was 0.45)
    (12.0, 0.07),  # (was 0.08)
    (13.0, 0.07),
    (14.0, 0.01),  # (was 0.04)
    (15.0, 0.02),  # (was 0.03)
    (16.0, 0.05),
    (17.0, 0.20),  # Jawari tertiary peak (was 0.33)
    (18.0, 0.02),  # (was 0.05)
    (19.0, 0.15),  # (was 0.28)
    (20.0, 0.02),  # (was 0.09)
    # Extended harmonics for HF content (real has 0.45% energy >5kHz)
    (25.0, 0.01),
    (30.0, 0.005),
]

# Per-string waveguide parameters.
# Each string can be tuned independently for bridge height, damping, stiffness, etc.
# String 1: variable (P/m/N at lower octave)
# String 2: madhya Sa (tonic)
# String 3: madhya Sa (detuned for beating)
# String 4: mandra Sa (lower octave)
STRING_PARAMS = {
    1: {
        "bridge_height": 1.0,      # bridge distance from rest (lower = more jawari)
        "jiva_height": 1.0,        # upper bridge (jiva thread)
        "bridge_curve": 0.7,       # curvature of bridge surface
        "damping": 0.999,          # feedback coefficient (higher = longer sustain)
        "stiffness": 0.7,          # allpass dispersion (0 = nylon, higher = metallic)
        "loop_filter": 0.06,       # brightness (0.5 = dark, 0.02 = harsh)
        "sustain": 5.0,            # seconds
        "amplitude": 0.98,         # relative amplitude
        "pluck_level": 0.4,        # initial pluck volume (0 = silent, 1 = full)
        "swell_peak": 1.0,         # jawari swell peak time (seconds)
        "swell_depth": 0.6,        # jawari swell strength
    },
    2: {
        "bridge_height": 1.0,
        "jiva_height": 1.0,
        "bridge_curve": 0.7,
        "damping": 0.999,
        "stiffness": 0.7,
        "loop_filter": 0.06,
        "sustain": 5.0,
        "amplitude": 1.0,
        "pluck_level": 0.4,
        "swell_peak": 1.0,
        "swell_depth": 0.6,
    },
    3: {
        "bridge_height": 1.0,
        "jiva_height": 1.0,
        "bridge_curve": 0.7,
        "damping": 0.999,
        "stiffness": 0.7,
        "loop_filter": 0.06,
        "sustain": 5.0,
        "amplitude": 1.0,
        "pluck_level": 0.4,
        "swell_peak": 1.0,
        "swell_depth": 0.6,
    },
    4: {
        "bridge_height": 1.0,
        "jiva_height": 1.0,
        "bridge_curve": 0.7,
        "damping": 0.999,
        "stiffness": 0.7,
        "loop_filter": 0.06,
        "sustain": 5.0,
        "amplitude": 0.96,
        "pluck_level": 0.4,
        "swell_peak": 1.0,
        "swell_depth": 0.6,
    },
}

# String 3 detuning — real tanpura Sa strings are never perfectly in tune.
# Slight detuning creates beating that produces the characteristic shimmer.
SA_STRINGS_DETUNE_HZ = 0.15

# Body resonance — tanpura gourd + wood body shapes the waveguide output.
# The body acts as an acoustic filter: gentle high-frequency rolloff (wood/gourd
# absorption) plus subtle resonance peaks at body modes.
# Measured rolloff: -20.6 dB/decade above 3kHz in real sample.
BODY_ROLLOFF_FREQ = 1800       # lowpass cutoff
BODY_ROLLOFF_ORDER = 1         # gentle 1st order — waveguide is already smooth
BODY_HIGHPASS_FREQ = 300       # gentle bass reduction — steep filters cause phase artifacts
BODY_HIGHPASS_ORDER = 1        # 1st order (-6 dB/oct)

# Jawari swell — per-string non-monotonic decay envelope.
# Real tanpura waveform shows: pluck → amplitude dip → energy buildup from
# bridge interaction → swell peak → gradual decay. This creates the visible
# amplitude undulations that distinguish a real tanpura from a static drone.
# Energy transfers between harmonics through bridge nonlinearity, building up
# at jawari frequencies amplified by body resonances.
JAWARI_SWELL_PEAK = 1.0       # seconds after pluck when swell peaks
JAWARI_SWELL_DEPTH = 0.6      # strength of dip-then-rise (0 = flat, 1 = max)
BODY_RESONANCES = [
    # (center_freq_hz, Q, gain_dB) — jawari metallic ring on smooth base
    (1000, 5,  5.0),   # jawari buzz
    (1400, 6,  7.0),   # metallic shimmer
]


def apply_body_resonance(signal):
    """Apply tanpura body resonance: highpass → resonance peaks → lowpass."""
    from scipy.signal import butter
    # 1. Highpass to remove sub-bass and excess bass energy
    b_hp, a_hp = butter(BODY_HIGHPASS_ORDER, BODY_HIGHPASS_FREQ / (SAMPLE_RATE / 2), btype='high')
    output = lfilter(b_hp, a_hp, signal)
    # 2. Add resonance peaks to boost jawari buzz region (1000-1800 Hz)
    for freq, q, gain_db in BODY_RESONANCES:
        w0 = freq / (SAMPLE_RATE / 2)
        if w0 >= 1.0:
            continue
        b, a = iirpeak(w0, q)
        gain = 10 ** (gain_db / 20)
        output += (gain - 1) * lfilter(b, a, output)
    # 3. Lowpass LAST — acts as ceiling to prevent resonance bleed into 2+ kHz
    b_lp, a_lp = butter(BODY_ROLLOFF_ORDER, BODY_ROLLOFF_FREQ / (SAMPLE_RATE / 2))
    output = lfilter(b_lp, a_lp, output)
    return output


def generate_string_pluck(frequency, params, volume=0.5, seed_frequency=None):
    """
    Generate a single string pluck using waveguide synthesis with bridge termination.

    Args:
        frequency: string frequency in Hz
        params: dict from STRING_PARAMS with per-string waveguide settings
        volume: overall volume multiplier
        seed_frequency: if set, use this for random seed (e.g., base Sa for detuned string 3)
    """
    duration = params["sustain"]
    num_samples = int(SAMPLE_RATE * duration)
    t = np.arange(num_samples) / SAMPLE_RATE

    period = max(2, int(round(SAMPLE_RATE / frequency)))
    rng = np.random.RandomState(int((seed_frequency or frequency) * 100))

    # Shape initial excitation to match measured harmonic spectrum
    delay_line = np.zeros(period)
    for harmonic_num, amplitude in HARMONICS:
        if harmonic_num * frequency < SAMPLE_RATE / 2:
            phase = rng.uniform(0, 2 * np.pi)
            idx = np.arange(period)
            delay_line += amplitude * np.sin(
                2.0 * np.pi * harmonic_num * idx / period + phase
            )
    dl_peak = np.max(np.abs(delay_line))
    if dl_peak > 0:
        delay_line /= dl_peak

    # Per-string waveguide parameters
    bridge = params["bridge_height"]
    jiva = params["jiva_height"]
    bridge_curve = params["bridge_curve"]
    damping = params["damping"]
    stiffness = params["stiffness"]
    blend = params["loop_filter"]
    pluck_level = params["pluck_level"]
    amplitude_variation = params["amplitude"]

    # Waveguide with bridge termination (jawari)
    output = np.zeros(num_samples)
    read_pos = 0
    allpass_state = 0.0

    for i in range(num_samples):
        y = delay_line[read_pos]
        output[i] = y

        # Bridge termination: curved surface reflection (lower side)
        if y < -bridge:
            penetration = -(y + bridge)
            reflected = penetration * (1.0 - bridge_curve * min(penetration, 1.0))
            y = -bridge + reflected

        # Jiva thread: upper bridge contact generates even harmonics
        if y > jiva:
            penetration = y - jiva
            reflected = penetration * (1.0 - bridge_curve * min(penetration, 1.0))
            y = jiva - reflected

        # Allpass dispersion — string stiffness (metallic inharmonicity)
        if stiffness > 0:
            ap_out = stiffness * y + allpass_state
            allpass_state = y - stiffness * ap_out
            y = ap_out

        # Tunable lowpass + damping (modified Karplus-Strong)
        next_pos = (read_pos + 1) % period
        delay_line[read_pos] = damping * ((1 - blend) * y + blend * delay_line[next_pos])
        read_pos = next_pos

    # Remove DC offset
    output -= np.mean(output)

    # Jawari swell: per-string non-monotonic amplitude envelope
    swell_depth = params["swell_depth"] * min((130.0 / frequency) ** 0.5, 1.5)
    swell_b = 2.0 / params["swell_peak"]
    swell_shape = (t ** 2) * np.exp(-swell_b * t)
    swell_max = np.max(swell_shape)
    if swell_max > 0:
        swell_shape /= swell_max
    jawari_envelope = (1.0 - swell_depth) + swell_depth * swell_shape
    output *= jawari_envelope

    # Gentle exponential attack
    attack_tau = 0.08
    attack = 1.0 - np.exp(-t / attack_tau)

    # Pluck suppression: dims initial transient, rises to 1.0 over ~300ms
    pluck_shape = pluck_level + (1.0 - pluck_level) * (1.0 - np.exp(-t / 0.15))

    output *= attack * pluck_shape * amplitude_variation * volume

    return output


def generate_tanpura_cycle(sa_frequency, string1_note):
    """Generate one complete 6-beat tanpura cycle as stereo audio."""
    ratio_note = string1_note  # Direct mapping: P, m, N

    # String frequencies: 1=variable lower octave, 2&3=tonic Sa, 4=lower Sa
    # String 3 is detuned slightly for natural beating (shimmer)
    string1_freq = sa_frequency * NOTE_RATIOS[ratio_note] / 2.0
    string2_freq = sa_frequency
    string3_freq = sa_frequency + SA_STRINGS_DETUNE_HZ
    string4_freq = sa_frequency / 2.0

    print(f"  Generating String 1 ({string1_note})...")
    string1_samples = generate_string_pluck(string1_freq, STRING_PARAMS[1])

    print(f"  Generating String 2 (Sa)...")
    string2_samples = generate_string_pluck(string2_freq, STRING_PARAMS[2])

    print(f"  Generating String 3 (Sa)...")
    string3_samples = generate_string_pluck(
        string3_freq, STRING_PARAMS[3], seed_frequency=sa_frequency,
    )

    print(f"  Generating String 4 (lower Sa)...")
    string4_samples = generate_string_pluck(string4_freq, STRING_PARAMS[4])

    # Mix strings with traditional plucking pattern (beats: 1, -, 3, 4, 5, -)
    pluck_offsets = [0, 2, 3, 4]  # String1, String2, String3, String4
    all_strings = [string1_samples, string2_samples, string3_samples, string4_samples]

    beat_interval_samples = int(SAMPLE_RATE * BEAT_INTERVAL)
    cycle_size = int(SAMPLE_RATE * CYCLE_DURATION)

    # Mix into a 3-cycle buffer WITHOUT modular wrapping.
    # String tails naturally extend across cycle boundaries, creating the
    # continuous drone bed that makes plucks blend in naturally.
    # (Old approach wrapped via % cycle_size, causing harmonic-dependent
    # self-interference that destroyed H4.)
    mix_size = cycle_size * 3
    mix_buffer = np.zeros(mix_size)

    for cycle_num in range(3):
        for string_index, string_samples in enumerate(all_strings):
            offset = cycle_num * cycle_size + pluck_offsets[string_index] * beat_interval_samples
            end = min(offset + len(string_samples), mix_size)
            length = end - offset
            if length > 0:
                mix_buffer[offset:end] += string_samples[:length]

    # Use the SECOND cycle as output — it has the drone bed from cycle 1's
    # string tails underneath its own plucks.
    mono_buffer = mix_buffer[cycle_size:cycle_size * 2].copy()

    # Cross-fade for seamless looping: blend the beginning of our cycle
    # with what naturally follows after our cycle ends (cycle 3's start).
    # This way, when the loop wraps (end → beginning), the transition is
    # smooth because the beginning already contains the "continuation."
    xfade_len = int(0.15 * SAMPLE_RATE)  # 150ms
    tail = mix_buffer[cycle_size * 2:cycle_size * 2 + xfade_len].copy()
    fade_in = np.linspace(0.0, 1.0, xfade_len)
    mono_buffer[:xfade_len] = mono_buffer[:xfade_len] * fade_in + tail * (1.0 - fade_in)

    # Apply body resonance to the mixed signal (gourd + wood acoustic coloring)
    # Applied post-mix because the body colors the combined string sound
    mono_buffer = apply_body_resonance(mono_buffer)

    # Normalize mono buffer (leave headroom)
    max_amp = np.max(np.abs(mono_buffer))
    if max_amp > 0.85:
        mono_buffer *= 0.85 / max_amp

    # Create stereo with Haas effect (3ms delay, ~13% width matching real sample)
    # Old 20ms delay created a comb filter that destroyed H4 in mono sum
    stereo_timing_offset = int(SAMPLE_RATE * 0.003)
    panning_l = 0.92
    panning_r = 0.88  # slight L>R asymmetry like real recording
    stereo_buffer = np.zeros((cycle_size, 2))

    for i in range(cycle_size):
        stereo_buffer[i, 0] = mono_buffer[i] * panning_l  # Left channel
        # Right channel with timing offset
        right_index = (i + stereo_timing_offset) % cycle_size
        stereo_buffer[i, 1] = mono_buffer[right_index] * panning_r

    # Final peak normalization (leave 10% headroom for DAC)
    actual_peak = np.max(np.abs(stereo_buffer))
    if actual_peak > 0:
        stereo_buffer *= 0.9 / actual_peak

    return stereo_buffer


def main():
    """Generate all tanpura audio files (OGG for Android, CAF for iOS)."""
    print("WARNING: This script is deprecated.")
    print("Use generate_tanpura_files_v2.py instead.")
    print()
    answer = input("Continue anyway? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    ogg_dir = Path(__file__).parent / "output" / "tanpura_ogg"
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

            audio_data = generate_tanpura_cycle(sa_freq, string1_note)

            _, tmp_name = tempfile.mkstemp(suffix=".wav")
            tmp_path = Path(tmp_name)
            try:
                sf.write(tmp_path, audio_data, SAMPLE_RATE, format="WAV", subtype="PCM_16")

                # OGG Vorbis via ffmpeg (max quality for spectrally dense waveguide output)
                subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", str(tmp_path),
                        "-c:a", "libvorbis",
                        "-q:a", "10",
                        str(ogg_dir / f"{stem}.ogg"),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"  ✓ OGG written")

                # CAF/ALAC (lossless) via macOS afconvert
                subprocess.run(
                    [
                        "afconvert",
                        str(tmp_path),
                        str(caf_dir / f"{stem}.caf"),
                        "-f", "caff",   # CAF container
                        "-d", "alac",   # Apple Lossless
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"  ✓ CAF written\n")
            finally:
                tmp_path.unlink(missing_ok=True)

    print(f"\n{'=' * 60}")
    print(f"Generation complete! {total_files} × 2 formats.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
