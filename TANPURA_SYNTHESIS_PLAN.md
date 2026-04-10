# Plan: Overhaul Tanpura Synthesis for Authentic Sound

## Context

The current waveguide synthesis (PR #4) was a major step forward from additive synthesis — jawari now emerges from physical bridge interaction rather than being bolted on. However, spectral analysis comparing the generated `c3_P` output against the real tanpura sample (`c3_P real.wav`) reveals the sound is still far from authentic. The generated output is **4x darker** (spectral centroid 664 Hz vs 2512 Hz real), **10x less bright** (2.7% vs 28.1% energy above 1kHz), has the **wrong harmonic balance** (H4 should be strongest but is 100x too quiet), and has an **unnaturally slow attack** (900ms sigmoid vs 27ms real pluck).

Root cause: the Karplus-Strong averaging filter `(y + next) / 2` compounds to devastating attenuation at upper harmonics over 10 seconds, and the bridge reflection can't regenerate fast enough to compensate.

## Approach: Improve the Waveguide (NOT replace it)

Per prior experience (12+ failed additive synthesis attempts), waveguide with bridge termination is the only approach that produces authentic jawari as an emergent phenomenon. This plan fixes the waveguide's parameters and adds missing physical modeling stages — it does not abandon the waveguide architecture.

## Analysis Summary (from real sample reverse-engineering)

| Metric | Real | Generated | Gap |
|--------|------|-----------|-----|
| Spectral centroid | 2512 Hz | 664 Hz | 4x darker |
| Brightness (>1kHz) | 28.1% | 2.7% | 10x less |
| H4 amplitude (normalized) | 1.000 | 0.013 | 100x too quiet |
| H7 amplitude | 0.985 | 0.161 | 6x too quiet |
| Attack time (10-90%) | 27ms | 900ms | 33x slower |
| Decay shape | Non-monotonic swells | Monotonic | Missing jawari swells |
| AM rate (overall) | 3.33 Hz | None | Missing modulation |
| Body resonances | 675, 1374, 2246, 4732 Hz | None | No body model |
| Inharmonicity B | 0.00005 | 0 | No string stiffness |
| Stereo width | 12.9% | ~50% | Too wide |
| Energy >5kHz | 0.45% | 0.00% | No HF content |

### Jawari Harmonic Oscillation (key finding)

In the real sample, H4 and H7 periodically trade dominance with ~250ms oscillation period:

```
  0ms: H7=1.000, H4=0.622  ← H7 dominates
 75ms: H4=1.000, H7=0.856  ← H4 takes over
225ms: H7=1.000, H4=0.923  ← H7 returns
500ms: H4=1.000, H7=0.911  ← H4 again
600ms: H7=1.000, H4=0.412  ← H7 dominant
```

This periodic trading IS the jawari character. Per-harmonic AM rates differ: H1/H4/H9 modulate at 0.95 Hz, H5/H7 at 2.86 Hz.

### Real sample decay is non-monotonic

The real tanpura shows periodic amplitude *increases* during decay (jawari swells):
- Pluck at t=1.0s: RMS starts 0.172, drops to 0.130 at +500ms, then **rises to 0.285** at +1250ms
- This is caused by energy transfer between harmonics via bridge interaction

## Steps

### Step 1: Replace the loop filter (fixes brightness — the #1 problem)

**File:** `generate_tanpura_files.py:174`

Replace the averaging filter `0.5 * (y + delay_line[next_pos])` with a tunable one-pole lowpass:

```python
# Old: delay_line[read_pos] = JAWARI_DAMPING * 0.5 * (y + delay_line[next_pos])
# New:
LOOP_FILTER_BLEND = 0.02  # 0.5 = original (dark), 0.02 = bright, preserves upper harmonics
...
delay_line[read_pos] = JAWARI_DAMPING * ((1 - LOOP_FILTER_BLEND) * y + LOOP_FILTER_BLEND * delay_line[next_pos])
```

**Why this works:** Per-pass gain at frequency f = `1 - blend * (1 - cos(2πf/fs))`. With blend=0.02 after one 3.6s cycle (~471 passes for C3):
- H1 (131 Hz): retains 98.8% → strong fundamental
- H4 (523 Hz): retains 96.0% → preserved (was being destroyed)
- H7 (916 Hz): retains 94.4% → preserved (was being destroyed)
- H17 (2224 Hz): retains 85.8% → now audible (was 0%)

Compare with current blend=0.5: H4 retains 72%, H7 retains 54%, H17 retains 9%.

Combined with JAWARI_DAMPING=0.999 (which gives ~62.5% overall at 3.6s), the harmonics now maintain reasonable levels within the audible cycle.

### Step 2: Fix the attack envelope (fixes pluck character)

**File:** `generate_tanpura_files.py:180-182`

Remove the 630-900ms sigmoid and replace with a fast natural pluck attack:

```python
# Old: attack = 1.0 / (1.0 + np.exp(-10.0 * (t / attack_duration - 0.5)))
# New: fast exponential onset matching measured 27ms (10-90%) rise time
attack_tau = 0.008  # ~8ms time constant → 27ms 10-90% rise
attack = 1.0 - np.exp(-t / attack_tau)
```

Also add a brief noise transient (first 30ms) to match the measured broadband attack spectrum (peaks at 500, 900, 1200, 2500 Hz):

```python
noise_duration = int(0.03 * SAMPLE_RATE)  # 30ms
noise = rng.randn(noise_duration) * 0.15
noise_env = np.exp(-np.arange(noise_duration) / (0.01 * SAMPLE_RATE))
output[:noise_duration] += noise * noise_env
```

Remove the `attack_duration` parameter from `generate_string_pluck` signature (all strings now get the natural fast attack).

### Step 3: Lower the bridge and add curved surface (fixes jawari strength)

**File:** `generate_tanpura_files.py:119, 164-170`

The current bridge height (0.3) is too high — less of the waveform crosses it, producing weak jawari. Lower it and add a curved bridge surface for richer harmonic interaction:

```python
JAWARI_BRIDGE_HEIGHT = 0.12    # Lower → more string-bridge contact → stronger jawari
JAWARI_BRIDGE_CURVE = 0.4      # Curvature of bridge surface (0 = flat, 1 = very curved)
```

Replace the hard reflection with a curved bridge model:

```python
# Old: if y < -bridge: y = -2.0 * bridge - y
# New: curved bridge with gradual wrapping
if y < -bridge:
    penetration = -(y + bridge)
    # Curved surface: reflection softens with deeper penetration
    reflected = penetration * (1.0 - JAWARI_BRIDGE_CURVE * min(penetration, 1.0))
    y = -bridge + reflected
```

The curved surface creates softer, frequency-dependent nonlinearity that produces the observed periodic H4↔H7 trading (measured ~250ms oscillation period in the real sample). Hard flat reflection creates harsh buzzing; curved reflection creates the shimmering jawari character.

### Step 4: Add body resonance filter (shapes spectral envelope)

**File:** `generate_tanpura_files.py` — new function, called from `generate_string_pluck`

The tanpura body (gourd + wood) acts as a resonant acoustic filter. Four resonance peaks were measured from the real sample's spectral envelope:

```python
from scipy.signal import iirpeak, lfilter

BODY_RESONANCES = [
    (675,  8,  6.0),   # (freq_hz, Q, gain_dB) — strongest, boosts H4-H5 region
    (1374, 10, 3.0),   # boosts H9-H11 region
    (2246, 12, 4.5),   # boosts H17 region
    (4732, 15, 2.0),   # adds air/presence
]

def apply_body_resonance(signal, sample_rate):
    """Apply tanpura body resonance (post-waveguide acoustic coloring)."""
    output = signal.copy()
    for freq, q, gain_db in BODY_RESONANCES:
        b, a = iirpeak(freq / (sample_rate / 2), q)
        gain = 10 ** (gain_db / 20)
        output += (gain - 1) * lfilter(b, a, signal)
    return output
```

Call at the end of `generate_string_pluck`, before normalization. This shapes the waveguide output into the characteristic tanpura spectral envelope — boosting the H4 region above H7, matching the real sample's balance.

### Step 5: Add string detuning for Sa-Sa beating (creates shimmer)

**File:** `generate_tanpura_files.py:199`

The real sample shows amplitude modulation at 0.95 Hz on H1 and 2.86 Hz on H7. Two Sa strings (Strings 2 & 3) with slight detuning produce beating at these rates:

```python
# Old: string3_freq = sa_frequency
# New: detune by 0.4 Hz for natural beating
STRINGS_2_3_DETUNE_HZ = 0.4
...
string3_freq = sa_frequency + STRINGS_2_3_DETUNE_HZ
```

This gives:
- H1 beating at 0.4 Hz (contributes to the 0.95 Hz AM along with bridge effects)
- H7 beating at 7 × 0.4 = 2.8 Hz (matches measured 2.86 Hz AM on H7)

### Step 6: Update the HARMONICS array from the new real sample

**File:** `generate_tanpura_files.py:91-112`

Update the initial excitation spectrum to match the real sample (currently based on a different recording). Key changes based on FFT analysis:

```python
HARMONICS = [
    (1.0, 0.20),   # was 0.26
    (2.0, 0.35),   # was 0.26 — real H2 is stronger
    (3.0, 0.06),   # was 0.04
    (4.0, 1.00),   # was 0.81 — H4 IS the strongest in real sample
    (5.0, 0.53),   # was 0.49
    (6.0, 0.41),   # was 0.49
    (7.0, 0.99),   # was 1.00 — H4 and H7 are nearly equal
    (8.0, 0.31),   # was 0.24
    (9.0, 0.30),   # was 0.54 — was overestimated
    (10.0, 0.15),  # was 0.34
    (11.0, 0.19),  # was 0.45
    (12.0, 0.07),  # was 0.08
    (13.0, 0.07),  # was 0.07
    (14.0, 0.01),  # was 0.04
    (15.0, 0.02),  # was 0.03
    (16.0, 0.05),  # was 0.05
    (17.0, 0.20),  # was 0.33 — still significant (jawari)
    (18.0, 0.02),  # was 0.05
    (19.0, 0.15),  # was 0.28
    (20.0, 0.02),  # was 0.09
    # Extended harmonics for HF content (real has 0.45% energy >5kHz)
    (25.0, 0.01),
    (30.0, 0.005),
]
```

### Step 7: Fix stereo imaging

**File:** `generate_tanpura_files.py:245-255`

Replace uniform 20ms Haas delay with narrower stereo:

```python
# Target: ~13% stereo width (measured 12.9% in real sample)
stereo_timing_offset = int(SAMPLE_RATE * 0.003)  # 3ms (was 20ms)
panning_l = 0.92   # was 0.75
panning_r = 0.88   # was 0.75 (slight L>R asymmetry like real recording)
```

### Step 8: Add scipy to requirements.txt

**File:** `requirements.txt`

Add `scipy` (needed for body resonance filters in Step 4).

### Step 9: Adjust pluck timing to better match real tanpura

**File:** `generate_tanpura_files.py:46-47`

The real sample shows faster plucking (~0.33s between rapid plucks) vs current 0.6s:

```python
BEAT_INTERVAL = 0.4    # was 0.6 — tighter rhythm matching real playing
```

This is a tuning parameter — may need ear-testing.

## Files to Modify

1. `generate_tanpura_files.py` — all synthesis changes (Steps 1-7, 9)
2. `requirements.txt` — add scipy (Step 8)

## Files to Preserve (interface unchanged)

- `test_jawari.py` — imports `SA_FREQUENCIES`, `SAMPLE_RATE`, `generate_tanpura_cycle`. All preserved.
- Output directory structure and file naming unchanged.

## Verification

After implementation, run this validation sequence:

1. **Generate test files:** `python test_jawari.py`
2. **A/B listen:** Compare `output/test_jawari/c3_P_x5.wav` with `c3_P real.wav`
3. **Spectral validation** (run inline or as a script):
   - Spectral centroid should be 2000-3000 Hz (was 664, target ~2500)
   - Brightness (>1kHz) should be 20-35% (was 2.7%, target ~28%)
   - H4 should be the strongest or near-strongest harmonic (was 100x too quiet)
   - H7 should be within 3dB of H4 (was 6x too quiet)
   - Attack time should be 20-40ms (was 900ms)
   - Energy above 5kHz should be >0.1% (was 0.00%)
4. **Generate full set:** `python generate_tanpura_files.py` — verify 45 OGG + 45 CAF files produced
5. **Regression check:** `python test_jawari.py` still works (preserved imports/signatures)

## Priority

- **Steps 1-3** address the biggest perceptual gaps (brightness, attack, jawari strength). These alone would be a massive improvement.
- **Steps 4-7** add realism layers (body resonance, beating, spectral balance, stereo).
- **Steps 8-9** are supporting changes.
- All parameter values are starting points derived from analysis — expect iterative tuning by ear after implementation.
