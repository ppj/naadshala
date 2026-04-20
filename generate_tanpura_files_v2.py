#!/usr/bin/env python3
"""
Tanpura asset generator v2 — additive jawari synthesis engine.

Generates 45 loopable single-cycle OGG + CAF files:
  15 tonics (G#2–A#3) × 3 string-1 intervals (Pa / Ma / Ni)

Algorithm: ports the jawari additive engine from tanpura/tanpura_synth.py.
Renders 5 cycles, extracts cycle 4 (has residual harmonics from cycles 1–3),
applies 150 ms crossfade at the loop boundary for seamless AudioTrack looping.

Output:
  output/tanpura/{name}_{interval}.ogg   (Android)
  output/tanpura_caf/{name}_{interval}.caf  (iOS, macOS only)

Dependencies: numpy, scipy, soundfile, ffmpeg CLI, afconvert (macOS)
"""

import os
import subprocess
import tempfile
import time

import numpy as np
from scipy import signal as sig
import soundfile as sf

# ---------------------------------------------------------------------------
# Audio configuration
# ---------------------------------------------------------------------------
SAMPLE_RATE = 48000
BIT_DEPTH   = 24
OGG_QUALITY = 10

# ---------------------------------------------------------------------------
# Tanpura cycle timing  (must match tanpura_synth.py)
# ---------------------------------------------------------------------------
SHORT_GAP    = 0.6   # seconds
LONG_GAP     = 1.2   # seconds
NUM_CYCLES   = 6
SUSTAIN_TAIL = 3.0

# ---------------------------------------------------------------------------
# Synthesis parameters  (must match tanpura_synth.py)
# ---------------------------------------------------------------------------
SA_DETUNE_CENTS  = 2.0
MAX_HARMONICS    = 80
FREQ_JITTER      = 0.0003
JAWARI_REF_HZ    = 165.0   # Pa of A3 (highest tonic) — jawari_strength scales down below this

# ---------------------------------------------------------------------------
# Tonics: G#2 → A#3 (15 semitones)
# ---------------------------------------------------------------------------
SA_FREQUENCIES = {
    "gs2": 103.83,
    "a2":  110.00,
    "as2": 116.54,
    "b2":  123.47,
    "c3":  130.81,
    "cs3": 138.59,
    "d3":  146.83,
    "ds3": 155.56,
    "e3":  164.81,
    "f3":  174.61,
    "fs3": 185.00,
    "g3":  196.00,
    "gs3": 207.65,
    "a3":  220.00,
    "as3": 233.08,
}

# ---------------------------------------------------------------------------
# String-1 intervals  (must match app file naming: P, m, N)
# ---------------------------------------------------------------------------
STRING1_NOTES = ["P", "m", "N"]

STRING1_RATIOS = {
    "P": 3.0 / 2.0,    # shuddha Pancham  (Pa)
    "m": 4.0 / 3.0,    # shuddha Madhyam  (Ma)
    "N": 15.0 / 8.0,   # shuddha Nishad   (Ni)
}

# ---------------------------------------------------------------------------
# Output directories
# ---------------------------------------------------------------------------
OUTPUT_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
OGG_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "tanpura")
CAF_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "tanpura_caf")

STRING_PARAMS = {
    1: {  # ── Pa (mandra saptak) ──────────────────────────────────────
        # Pa string: thick steel — strong bridge contact → prominent jawari
        "jawari_strength":    0.75,
        "jawari_shift_db":    0.0,
        "jawari_h3_extra_db": 0.0,
        "jawari_peak_shift":  0,
        "sustain":            6.0,
        "swell_amount":       0.85,
        "swell_center_s":     0.25,
        "attack_ms":          2.0,
        "transient_db":       -25.0,
        "level":              0.88,
        "pan":                0.35,
        "jawari_buzz":        0.10,
        "buzz_gate_s":        2.25,    # buzz/shimmer fade to ~5% by this time
        "ks_level":           0.40,
        "pluck_decay_scale":  0.2,
    },
    2: {  # ── Sa (madhya saptak) ──────────────────────────────────────
        # Primary Sa: thinner steel → lighter bridge contact
        "jawari_strength":    0.70,
        "jawari_shift_db":    0.0,
        "jawari_h3_extra_db": 0.0,
        "jawari_peak_shift":  0,
        "sustain":            3.5,
        "swell_amount":       0.65,
        "swell_center_s":     0.35,
        "attack_ms":          1.5,
        "transient_db":       -23.0,
        "level":              0.65,
        "pan":                0.48,
        "jawari_buzz":        0.14,
        "buzz_gate_s":        1.50,
        "ks_level":           0.25,
        "pluck_decay_scale":  0.2,
    },
    3: {  # ── Sa (madhya saptak, micro-detuned) ───────────────────────
        "jawari_strength":    0.68,
        "jawari_shift_db":    -1.0,
        "jawari_h3_extra_db": 0.0,
        "jawari_peak_shift":  0,
        "sustain":            3.0,
        "swell_amount":       0.62,
        "swell_center_s":     0.35,
        "attack_ms":          1.5,
        "transient_db":       -24.0,
        "level":              0.87,
        "pan":                0.55,
        "jawari_buzz":        0.12,
        "buzz_gate_s":        1.50,
        "ks_level":           0.25,
        "pluck_decay_scale":  0.2,
    },
    4: {  # ── Sa (mandra saptak — brass/bronze) ───────────────────────
        # Thickest string, deepest contact with bridge → strongest jawari
        "jawari_strength":    0.20,
        "jawari_shift_db":    -2.0,
        "jawari_h3_extra_db": 0.0,
        "jawari_peak_shift":  0,
        "sustain":            6.0,
        "swell_amount":       0.85,
        "swell_center_s":     0.30,
        "attack_ms":          2.5,
        "transient_db":       -22.0,
        "level":              0.85,
        "pan":                0.62,
        "jawari_buzz":        0.01,
        "buzz_gate_s":        0.35,
        "ks_level":           0.55,
        "pluck_decay_scale":  0.7,
    },
}

# ---- Reference-derived spectral template (dB relative to H1) ----
# Measured from a real Calcutta male C3 tanpura, Pa-Sa-Sa-Sa(low) tuning,
# sped up to match our 3.6 s cycle (0.6 s × 6 beats).
# The real tanpura jawari creates a characteristic shape:
#   • H1-H2 strong (fundamental region well-represented)
#   • H4, H7 dominant twin peaks (~+12 dB above H1)
#   • H3, H8, H12 are bridge-geometry notches
#   • Steady decay above H10 with bumps at H16-H17, H19

_REF_SPECTRUM_DB = {
    1:   0.0,
    2:   2.4,
    3: -15.7,
    4:  12.0,
    5:   5.1,
    6:   5.6,
    7:  12.1,
    8:  -2.1,
    9:   3.6,
    10: -4.4,
    11: -2.6,
    12: -15.4,
    13: -17.1,
    14: -25.7,
    15: -23.8,
    16: -16.9,
    17:  -1.9,
    18: -21.0,
    19:  -4.4,
    20: -25.0,
    # H21–H30: continuation of the alternating notch/peak pattern.
    # Recovery peaks — present for shimmer but kept quiet to avoid harshness.
    21: -12.0,
    22: -22.0,
    23: -14.0,
    24: -23.0,
    25: -15.0,
    26: -24.0,
    27: -16.0,
    28: -24.0,
    29: -17.0,
    30: -25.0,
}

def jawari_harmonic_amplitude(h, params):
    """
    Return the linear amplitude for harmonic number `h` (1-based)
    based on the jawari spectral model.

    Uses a reference-derived spectral template as the base shape,
    then adjusts per-string via:
      • jawari_strength : 0–1, how closely to follow the reference shape
      • jawari_shift    : shift the whole curve up/down in dB
      • h3_boost_extra  : additional boost around H3 (on top of reference)
      • peak_shift      : shift the peak harmonic number relative to ref

    The reference template captures the complex two-peak structure
    (H3 warmth peak + H13 jawari peak + H15 cliff + H17 partial recovery)
    that simple parametric models cannot reproduce.
    """
    strength   = params.get("jawari_strength", 0.85)
    shift_db   = params.get("jawari_shift_db", 0.0)
    h3_extra   = params.get("jawari_h3_extra_db", 0.0)
    peak_shift = params.get("jawari_peak_shift", 0)

    # --- interpolate from reference template ---
    h_shifted = h - peak_shift  # allows shifting the peak position
    if h_shifted < 1:
        h_shifted = 1

    # interpolate between reference points for non-integer shifted values
    if h_shifted in _REF_SPECTRUM_DB:
        ref_db = _REF_SPECTRUM_DB[h_shifted]
    elif h_shifted <= 30:
        lo = int(np.floor(h_shifted))
        hi = int(np.ceil(h_shifted))
        lo = max(1, min(lo, 30))
        hi = max(1, min(hi, 30))
        frac = h_shifted - lo
        ref_db = _REF_SPECTRUM_DB[lo] * (1 - frac) + _REF_SPECTRUM_DB[hi] * frac
    else:
        # beyond H30: steeper decay to avoid harshness
        ref_db = _REF_SPECTRUM_DB[30] - 3.5 * (h_shifted - 30)

    # --- blend between flat (0 dB) and reference shape ---
    shaped_db = strength * ref_db

    # --- per-string shift ---
    shaped_db += shift_db

    # --- extra H3 boost if needed ---
    h3 = h3_extra * np.exp(-0.5 * ((h - 3.0) / 1.2) ** 2)
    shaped_db += h3

    return 10.0 ** (max(shaped_db, -60.0) / 20.0)


def harmonic_envelope(t, h, params):
    """
    Time-varying amplitude envelope for harmonic `h`.

    Models three phases:
      1. Attack — quick onset from the pluck
      2. Swell  — harmonics bloom as the string settles onto the bridge
      3. Decay  — very slow exponential decay (tanpura strings ring long)

    Higher harmonics swell slightly later and decay slightly faster,
    creating the characteristic "living" quality of the drone.
    """
    sustain_s    = params["sustain"]
    swell_amount = params["swell_amount"]
    swell_center = params["swell_center_s"]

    # 1. Attack — slow onset so the sustain fades in behind the modal pluck.
    # The pluck signal provides the fast transient; the sustain should emerge
    # gradually (reaching ~95% by ~300 ms for H1).
    attack_tau = 0.10 + 0.005 * h
    attack = 1.0 - np.exp(-t / attack_tau)

    # 2. Swell  (jawari bloom — mid-upper harmonics swell the most)
    h_swell_factor = 1.0 + 0.7 * np.exp(-0.5 * ((h - 10) / 5) ** 2)
    swell_t   = swell_center * (1.0 + 0.04 * h)   # later for higher h
    swell_w   = swell_t * 0.50
    swell     = 1.0 + swell_amount * h_swell_factor * np.exp(
        -0.5 * ((t - swell_t) / max(swell_w, 0.01)) ** 2
    )

    # 3. Decay  (upper harmonics fade significantly faster than fundamental)
    decay_rate = (1.0 / sustain_s) * (1.0 + 0.06 * h)
    decay = np.exp(-decay_rate * t)

    return attack * swell * decay


def synthesize_string(frequency, duration_s, sr, params):
    """
    Synthesise one tanpura string via additive synthesis with jawari
    spectral envelope and per-harmonic temporal envelopes.

    Normalisation is energy-based (RMS = 1) so that the jawari spectral
    shape is preserved correctly when multiple strings are mixed.

    Returns 1-D float64 array.
    """
    n_samples  = int(duration_s * sr)
    t          = np.arange(n_samples, dtype=np.float64) / sr
    signal     = np.zeros(n_samples, dtype=np.float64)
    attack_ms  = params["attack_ms"]

    max_h = min(MAX_HARMONICS, int(sr * 0.45 / frequency))
    rng   = np.random.default_rng()

    # ---- pre-compute all harmonic amplitudes (NO energy pre-normalisation) ----
    # The jawari model returns amplitudes in dB-derived linear scale.
    # We do NOT normalise them here — this preserves the full dynamic range
    # of the spectral shape (H1 being ~40 dB below H13-H15).
    # The final signal is RMS-normalised below, and the `level` parameter
    # controls relative loudness in the mix.
    raw_amps = []
    for h in range(1, max_h + 1):
        if frequency * h >= sr * 0.47:
            break
        raw_amps.append(jawari_harmonic_amplitude(h, params))
    raw_amps = np.array(raw_amps)

    # ---- additive synthesis with per-harmonic envelopes ----
    for i, h in enumerate(range(1, len(raw_amps) + 1)):
        f_h = frequency * h
        amp = raw_amps[i]

        # per-harmonic time envelope
        env = harmonic_envelope(t, h, params)

        # Frequency jitter — scales up for higher harmonics to simulate the
        # inharmonic beating and shimmer of real steel string / bridge contact.
        jitter_depth = FREQ_JITTER * (1.0 + 0.2 * max(0, h - 8))
        jitter_rate  = 0.3 + h * 0.08
        jitter_phase = rng.uniform(0, 2 * np.pi)
        f_mod = f_h * (1.0 + jitter_depth * np.sin(
            2.0 * np.pi * jitter_rate * t + jitter_phase
        ))

        # accumulate instantaneous phase (handles FM correctly)
        phase_0    = rng.uniform(0, 2 * np.pi)
        inst_phase = phase_0 + 2.0 * np.pi * np.cumsum(f_mod) / sr

        signal += amp * env * np.sin(inst_phase)

    # ---- fade-in to avoid onset click ----
    attack_samples = int(attack_ms / 1000.0 * sr)
    if 0 < attack_samples < n_samples:
        signal[:attack_samples] *= np.linspace(0.0, 1.0, attack_samples)

    # ---- RMS normalisation (preserves spectral shape in the mix) ----
    rms = np.sqrt(np.mean(signal ** 2))
    if rms > 0:
        signal /= rms

    return signal


def _synthesize_pluck_modal(frequency, sr, params):
    """
    Modal synthesis pluck — models acoustic gourd/body excitation.

    A real tanpura pluck sounds like the gourd body being excited, not a
    clean string resonance.  This models it as:
      1. A brief broadband noise burst (nail/finger contact, ~3 ms)
      2. A set of exponentially decaying sinusoids at the body's acoustic
         resonance modes (sub-octave, fundamental coupling, upper modes)

    Each mode decays in 15–30 ms, giving a short "dhum" that fades into
    the additive sustain.  No sustained pitched loop → no electric-guitar
    character.
    """
    pluck_dur_s = 0.22
    n_samples   = int(pluck_dur_s * sr)
    t           = np.arange(n_samples) / sr
    rng    = np.random.default_rng()
    signal = np.zeros(n_samples)

    # 1. String release noise — narrow-band noise burst centered at the
    # string frequency. Models the brief "buzz" of the string as it springs
    # off the fingernail. Soft attack, decays in ~20 ms.
    bw       = frequency * 0.6
    lo_hz    = max(frequency - bw, 20.0)
    hi_hz    = min(frequency + bw, sr * 0.45)
    lo       = lo_hz / (sr / 2)
    hi       = hi_hz / (sr / 2)
    if lo >= hi:
        lo = max(lo * 0.5, 1e-4)
    b_n, a_n = sig.butter(3, [lo, hi], btype='band')
    noise    = rng.standard_normal(n_samples)
    noise    = sig.lfilter(b_n, a_n, noise)
    decay_scale = params.get("pluck_decay_scale", 1.0)
    noise_env = (1.0 - np.exp(-t / 0.003)) * np.exp(-t / (0.025 * decay_scale))
    signal   += 0.4 * noise_env * noise

    # 2. Body resonance modes — soft attack, exponential decay.
    # (freq, attack_tau_s, decay_tau_s, relative_amplitude)
    body_modes = [
        (frequency,       0.006, 0.050, 1.0),   # fundamental
        (frequency * 1.5, 0.005, 0.035, 0.55),  # second body mode
        (frequency * 2.0, 0.004, 0.025, 0.28),  # third body mode
        (frequency * 3.0, 0.003, 0.016, 0.14),  # upper body mode
    ]
    for f_mode, atk_tau, dec_tau, amp in body_modes:
        if f_mode >= sr * 0.45:
            continue
        mode_phase = rng.uniform(0, 2 * np.pi)
        env = (1.0 - np.exp(-t / atk_tau)) * np.exp(-t / (dec_tau * decay_scale))
        signal += amp * env * np.sin(2 * np.pi * f_mode * t + mode_phase)

    # 3. Metallic string harmonics — bright upper partials present only
    # at the attack, decaying very fast (5–10 ms). Adds the brief "zing"
    # of a metal string without affecting the sustained drone character.
    metal_harmonics = [
        (4,  0.009, 0.30),
        (5,  0.007, 0.22),
        (6,  0.006, 0.16),
        (7,  0.005, 0.11),
        (8,  0.004, 0.07),
    ]
    for h, dec_tau, amp in metal_harmonics:
        f_h = frequency * h
        if f_h >= sr * 0.45:
            break
        phase = rng.uniform(0, 2 * np.pi)
        env   = np.exp(-t / dec_tau)
        signal += amp * env * np.sin(2 * np.pi * f_h * t + phase)

    # High-pass blend to reduce bass thump on the pluck.
    # Cutoff at 3× fundamental so all strings lose a similar fraction of
    # pluck energy regardless of pitch (fixed 500 Hz stripped low strings).
    shelf_hz   = min(frequency * 3.0, 500.0)
    shelf_freq = min(shelf_hz / (sr / 2), 0.99)
    b_shelf, a_shelf = sig.butter(2, shelf_freq, btype='high')
    signal_hi = sig.lfilter(b_shelf, a_shelf, signal)
    signal = signal * 0.25 + signal_hi * 0.75

    # Peak-normalise so ks_level in the mix is a predictable ratio of the
    # pluck's peak amplitude to sustain_rms.  RMS-normalisation inflates the
    # peak unpredictably for fast-decaying transients (high crest factor).
    peak = np.max(np.abs(signal))
    if peak > 0:
        signal /= peak

    return signal


def _body_resonance(audio, sr):
    """Gourd/toomba body resonance EQ."""
    # high-pass 25 Hz  (remove sub-bass rumble, preserve pluck thump)
    b, a  = sig.butter(2, 25.0 / (sr / 2), btype="high")
    audio = sig.lfilter(b, a, audio)

    # peaking EQ bands — shape the body resonance
    for f0, Q, gain_db in [(180.0, 0.8, 2.0),     # body warmth
                            (800.0, 1.0, 2.0),     # midrange
                            (1500.0, 0.9, 3.0),    # jawari presence
                            (1800.0, 0.7, 2.0),    # metallic upper-mid presence
                            (3000.0, 0.8, 4.0),    # shimmer / upper jawari
                            (5500.0, 1.0, 3.5),    # air / brilliance
                            (8000.0, 1.2, 2.5)]:   # sparkle
        w0    = 2 * np.pi * f0 / sr
        A     = 10 ** (gain_db / 40.0)
        alpha = np.sin(w0) / (2 * Q)
        b_eq  = np.array([1 + alpha * A, -2 * np.cos(w0), 1 - alpha * A])
        a_eq  = np.array([1 + alpha / A, -2 * np.cos(w0), 1 - alpha / A])
        audio = sig.lfilter(b_eq, a_eq, audio)

    # low-pass 10 kHz — rolls off harsh high-frequency content
    b, a  = sig.butter(2, 10000.0 / (sr / 2), btype="low")
    audio = sig.lfilter(b, a, audio)
    return audio


def _apply_jawari_waveshaping(mono, sr, buzz_strength, gate_s=None):
    """
    Derive metallic jawari buzz from the string signal via waveshaping.

    Physical model: the string grazes the curved bridge asymmetrically —
    only on the downswing toward the bridge surface — causing soft clipping
    that generates inharmonic distortion products with a metallic timbre.

    gate_s: if set, the buzz+shimmer fade out exponentially with tau=gate_s/3,
    reaching ~5% by gate_s seconds. This confines the metallic character to the
    attack, letting the sustain ring clean — matching how real jawari settles.
    """
    if buzz_strength <= 0:
        return mono

    # Asymmetric soft-clipper — positive half (toward bridge) is clipped,
    # negative half (away from bridge) passes with mild attenuation.
    drive = 2.0
    shaped = np.where(
        mono > 0,
        np.tanh(mono * drive) / np.tanh(drive),
        mono * 0.85,
    )

    # Buzz is purely the distortion product — not the carrier itself
    buzz = shaped - mono

    # Band-pass to metallic shimmer range.
    # Lower cutoff at 1200 Hz captures more of the metallic mid-range.
    # Upper cutoff at 8000 Hz adds extra shimmer/metallicity.
    lo = max(1500.0 / (sr / 2), 0.01)
    hi = min(8000.0 / (sr / 2), 0.99)
    b, a = sig.butter(3, [lo, hi], btype='band')
    buzz = sig.lfilter(b, a, buzz)

    # Normalise buzz relative to carrier RMS, then scale by buzz_strength
    mono_rms = np.sqrt(np.mean(mono ** 2))
    buzz_rms = np.sqrt(np.mean(buzz ** 2))
    if buzz_rms > 0 and mono_rms > 0:
        buzz *= (mono_rms * buzz_strength) / buzz_rms

    # --- High-frequency shimmer layer ---
    # Hard clip at higher drive generates richer high harmonics (closer to
    # the impulse-train behaviour of string-bridge contact).  Bandpassed to
    # the 5–16 kHz metallic shimmer range only; mixed at ~40% of the main buzz.
    shimmer_drive = 6.0
    shimmer = np.tanh(mono * shimmer_drive) / np.tanh(shimmer_drive) - mono
    sh_lo = max(3000.0 / (sr / 2), 0.01)
    sh_hi = min(16000.0 / (sr / 2), 0.99)
    if sh_lo < sh_hi:
        b_sh, a_sh = sig.butter(3, [sh_lo, sh_hi], btype='band')
        shimmer = sig.lfilter(b_sh, a_sh, shimmer)
        shimmer_rms = np.sqrt(np.mean(shimmer ** 2))
        if shimmer_rms > 0 and mono_rms > 0:
            # Scale shimmer with buzz_strength so strings with low buzz
            # (e.g. S4) don't get a disproportionately harsh shimmer layer.
            shimmer *= (mono_rms * buzz_strength * 2.0) / shimmer_rms
    else:
        shimmer = np.zeros_like(mono)

    # Time-gate: exponential decay so buzz/shimmer fade out after the attack
    if gate_s is not None and gate_s > 0:
        t = np.arange(len(mono)) / sr
        gate = np.exp(-t / (gate_s / 3.0))
        buzz    *= gate
        shimmer *= gate

    return mono + buzz + shimmer


def _spectral_match_eq(stereo, sr, tonic_hz):
    """
    Post-mix harmonic correction EQ.

    Measures the actual harmonic power of the combined signal and applies
    narrow-band corrections at each harmonic to match the reference
    spectral template.  This compensates for cross-string overlap that
    causes certain harmonics to be boosted/suppressed relative to the
    per-string target.
    """
    # ---- Frequency-domain spectral correction ----
    # Directly scale the FFT bins around each harmonic to match the
    # reference template.  This avoids the resonance/interaction issues
    # of cascaded IIR parametric EQ filters.
    for ch in range(stereo.shape[1]):
        signal = stereo[:, ch]
        n = len(signal)
        S = np.fft.rfft(signal)
        freqs = np.fft.rfftfreq(n, 1/sr)
        mag = np.abs(S)

        # measure H1 power
        h1_mask = np.abs(freqs - tonic_hz) < 5.0
        h1_power = np.max(mag[h1_mask]) if np.any(h1_mask) else 1e-12

        for h in range(2, 21):
            fh = tonic_hz * h
            if fh >= sr * 0.45:
                break

            target_rel_db = _REF_SPECTRUM_DB.get(h, -30.0)

            # measure actual power at this harmonic
            h_mask = np.abs(freqs - fh) < 5.0
            if not np.any(h_mask):
                continue
            actual_power = np.max(mag[h_mask])
            if actual_power < 1e-12:
                continue

            actual_rel_db = 20 * np.log10(actual_power / h1_power + 1e-12)
            correction_db = target_rel_db - actual_rel_db

            # clamp correction
            correction_db = np.clip(correction_db, -10.0, 10.0)

            if abs(correction_db) < 1.0:
                continue

            # apply correction as a smooth Gaussian gain window around fh
            correction_linear = 10 ** (correction_db / 20.0)
            # Gaussian window width: narrow enough to affect only this harmonic
            sigma_hz = tonic_hz * 0.15   # ~15% of fundamental spacing
            gain_window = 1.0 + (correction_linear - 1.0) * np.exp(
                -0.5 * ((freqs - fh) / sigma_hz) ** 2
            )
            S *= gain_window

        stereo[:, ch] = np.fft.irfft(S, n=n)

    return stereo


def _pan_stereo(mono, pan):
    angle = pan * (np.pi / 2.0)
    return mono * np.cos(angle), mono * np.sin(angle)


def cents_to_ratio(c):
    return 2.0 ** (c / 1200.0)


def get_string_frequencies(tonic_hz, interval):
    """Return the 4 string frequencies for a given tonic and string-1 interval."""
    ratio     = STRING1_RATIOS[interval]
    mandra_sa = tonic_hz / 2.0
    detune    = cents_to_ratio(SA_DETUNE_CENTS)
    return {
        1: mandra_sa * ratio,
        2: tonic_hz,
        3: tonic_hz * detune,
        4: mandra_sa,
    }


def synthesize_tanpura(tonic_hz, interval, sr):
    """Render a full multi-cycle tanpura and return stereo float64 array.

    Identical to tanpura_synth.synthesize_tanpura() except:
      - accepts `interval` ('P'/'m'/'N') instead of reading a global
      - no fade-out applied (cycle extraction doesn't need it)
    """
    freqs = get_string_frequencies(tonic_hz, interval)

    cycle_dur = 2 * LONG_GAP + 2 * SHORT_GAP          # 3.6 s
    total_dur = NUM_CYCLES * cycle_dur + SUSTAIN_TAIL  # 24 s
    n_samples = int(total_dur * sr)

    single_cycle_onsets = [
        (1, 0.0),
        (2, LONG_GAP),
        (3, LONG_GAP + SHORT_GAP),
        (4, LONG_GAP + 2 * SHORT_GAP),
    ]

    rendered = {}
    for snum in (1, 2, 3, 4):
        sp       = dict(STRING_PARAMS[snum])   # copy — we may mutate jawari_strength
        ring_dur = sp["sustain"] + 3.0
        freq     = freqs[snum]

        if snum in (1, 4):
            # Lower pitches get softer jawari peaks — less bridge contact at lower tension.
            jaw_scale = np.clip((freq / JAWARI_REF_HZ) ** 0.5, 0.4, 1.0)
            sp["jawari_strength"] = sp["jawari_strength"] * jaw_scale

        sustain  = synthesize_string(freq, ring_dur, sr, sp)

        if snum == 4:
            # Thick brass/bronze string has naturally weak high harmonics.
            # Low-pass at ~8× fundamental preserves warmth without high-harmonic shred.
            lp_hz  = min(freq * 8.0, 600.0)
            b_lp, a_lp = sig.butter(2, lp_hz / (sr / 2), btype='low')
            sustain = sig.lfilter(b_lp, a_lp, sustain)

        # Scale jawari buzz with string frequency: lower strings get less buzz
        # to prevent harshness. Full buzz at/above ~E3 (165 Hz), cubic rolloff below.
        # G#2→25%, A#2→36%, C#3→60%, E3→100%
        buzz_freq_scale = np.clip((freq / 165.0) ** 3, 0.1, 1.0)
        buzz_strength   = sp.get("jawari_buzz", 0.0) * buzz_freq_scale
        sustain  = _apply_jawari_waveshaping(sustain, sr, buzz_strength,
                                              gate_s=sp.get("buzz_gate_s"))
        sustain *= sp["level"]

        ks       = _synthesize_pluck_modal(freq, sr, sp)
        ks_level = sp.get("ks_level", 2.0)

        mono = sustain.copy()
        n_ks = len(ks)
        mono[:n_ks] += ks_level * ks
        rendered[snum] = mono

    mix_L = np.zeros(n_samples, dtype=np.float64)
    mix_R = np.zeros(n_samples, dtype=np.float64)

    for cycle_idx in range(NUM_CYCLES):
        cycle_base = cycle_idx * cycle_dur
        for snum, onset_in_cycle in single_cycle_onsets:
            sp        = STRING_PARAMS[snum]
            onset_s   = cycle_base + onset_in_cycle
            onset_idx = int(onset_s * sr)
            if onset_idx >= n_samples:
                continue
            mono   = rendered[snum]
            L, R   = _pan_stereo(mono, sp["pan"])
            end    = min(onset_idx + len(L), n_samples)
            length = end - onset_idx
            mix_L[onset_idx:end] += L[:length]
            mix_R[onset_idx:end] += R[:length]

    mix_L = _body_resonance(mix_L, sr)
    mix_R = _body_resonance(mix_R, sr)

    stereo = np.column_stack([mix_L, mix_R])
    stereo = _spectral_match_eq(stereo, sr, tonic_hz)

    rms = np.sqrt(np.mean(stereo ** 2))
    if rms > 0:
        stereo *= 0.22 / rms  # target ~-13.1 dBFS RMS
    peak = np.max(np.abs(stereo))
    if peak > 0.95:
        stereo *= 0.95 / peak

    return stereo


def extract_loopable_cycle(stereo, cycle_dur, sr, cycle_idx=3, xfade_s=0.15):
    """Extract one loopable cycle from a multi-cycle stereo render.

    Args:
        stereo:     Full render, shape (N, 2), float64.
        cycle_dur:  Duration of one cycle in seconds (3.6 s for standard tanpura).
        sr:         Sample rate.
        cycle_idx:  0-based index of the cycle to extract (default 3 = cycle 4 of 5).
        xfade_s:    Crossfade length in seconds (default 0.15 = 150 ms).

    Returns:
        Stereo array of shape (cycle_size, 2).

    The crossfade blends the *beginning* of the extracted cycle with the
    corresponding tail from the *next* cycle.  At t=0 the output is 100%
    next-cycle continuation, fading to 100% extracted cycle by t=xfade_s.
    This means the hard position-reset loop (Android AudioTrack) transitions
    smoothly: end-of-file → beginning-of-file plays through the crossfade region.
    """
    cycle_size = int(cycle_dur * sr)
    xfade_len  = int(xfade_s * sr)

    start = cycle_idx * cycle_size
    end   = start + cycle_size

    cycle = stereo[start:end].copy()

    tail_start = end
    tail_end   = tail_start + xfade_len
    tail = stereo[tail_start:tail_end].copy()

    fade_in = np.linspace(0.0, 1.0, xfade_len).reshape(-1, 1)
    cycle[:xfade_len] = cycle[:xfade_len] * fade_in + tail * (1.0 - fade_in)

    return cycle


# ============================================================================
# EXPORT
# ============================================================================

def export_ogg(stereo, sr, filepath):
    """Export stereo float64 array to OGG Vorbis via ffmpeg."""
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    subtype = "PCM_24" if BIT_DEPTH == 24 else "PCM_16"
    sf.write(wav_path, stereo, sr, subtype=subtype)
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", wav_path,
                "-codec:a", "libvorbis",
                "-qscale:a", str(OGG_QUALITY),
                filepath,
            ],
            check=True,
        )
    finally:
        os.remove(wav_path)
    size_kb = os.path.getsize(filepath) / 1024
    print(f"    OGG → {os.path.basename(filepath)}  ({size_kb:.0f} KB)")


def export_caf(stereo, sr, filepath):
    """Export stereo float64 array to CAF/ALAC via macOS afconvert."""
    fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(wav_path, stereo, sr, subtype="PCM_16")
    try:
        subprocess.run(
            ["afconvert", wav_path, filepath, "-f", "caff", "-d", "alac"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    finally:
        os.remove(wav_path)
    size_kb = os.path.getsize(filepath) / 1024
    print(f"    CAF → {os.path.basename(filepath)}  ({size_kb:.0f} KB)")


# ============================================================================
# MAIN
# ============================================================================

def main():
    os.makedirs(OGG_OUTPUT_DIR, exist_ok=True)
    os.makedirs(CAF_OUTPUT_DIR, exist_ok=True)

    cycle_dur   = 2 * LONG_GAP + 2 * SHORT_GAP   # 3.6 s
    total_files = len(SA_FREQUENCIES) * len(STRING1_NOTES)
    t0 = time.time()

    print(f"Generating {total_files} tanpura files (OGG + CAF) at {SAMPLE_RATE} Hz ...")
    print(f"  OGG → {OGG_OUTPUT_DIR}")
    print(f"  CAF → {CAF_OUTPUT_DIR}")
    print()

    count = 0
    for sa_name, sa_freq in SA_FREQUENCIES.items():
        for interval in STRING1_NOTES:
            count += 1
            stem = f"{sa_name}_{interval}"
            print(f"[{count}/{total_files}] {stem}  (Sa={sa_freq:.2f} Hz, str1={interval})")

            stereo = synthesize_tanpura(sa_freq, interval, SAMPLE_RATE)
            cycle  = extract_loopable_cycle(stereo, cycle_dur, SAMPLE_RATE, cycle_idx=3)

            export_ogg(cycle, SAMPLE_RATE, os.path.join(OGG_OUTPUT_DIR, f"{stem}.ogg"))
            export_caf(cycle, SAMPLE_RATE, os.path.join(CAF_OUTPUT_DIR, f"{stem}.caf"))
            print()

    elapsed = time.time() - t0
    print(f"Done — {total_files} × 2 formats in {elapsed:.0f} s")


if __name__ == "__main__":
    main()
