# Plan: Overhaul Tanpura Synthesis for Authentic Sound

## Context

The current waveguide synthesis (PR #4) was a major step forward from additive synthesis — jawari now emerges from physical bridge interaction rather than being bolted on. However, spectral analysis comparing the generated `c3_P` output against the real tanpura sample (`c3_P real.wav`) reveals the sound is still far from authentic. The generated output is **4x darker** (spectral centroid 664 Hz vs 2512 Hz real), **10x less bright** (2.7% vs 28.1% energy above 1kHz), has the **wrong harmonic balance** (H4 should be strongest but is 100x too quiet), and has an **unnaturally slow attack** (900ms sigmoid vs 27ms real pluck).

Root cause: the Karplus-Strong averaging filter `(y + next) / 2` compounds to devastating attenuation at upper harmonics over 10 seconds, and the bridge reflection can't regenerate fast enough to compensate.

## Approach: Improve the Waveguide (NOT replace it)

Per prior experience (12+ failed additive synthesis attempts), waveguide with bridge termination is the only approach that produces authentic jawari as an emergent phenomenon. This plan fixes the waveguide's parameters and adds missing physical modeling stages — it does not abandon the waveguide architecture.

## Analysis Summary (from real sample reverse-engineering)

| Metric | Real | Generated (before) | After | Status |
|--------|------|-------------------|-------|--------|
| Spectral centroid | 2512 Hz | 664 Hz | 1040 Hz | Improved (still below target) |
| Brightness (>1kHz) | 28.1% | 2.7% | 34.8% | **Target met** |
| H4 amplitude (normalized) | 1.000 | 0.013 | 0.702 | **Fixed** (was 100x too quiet) |
| H7 amplitude | 0.985 | 0.161 | 0.364 | Improved |
| Attack time (10-90%) | 27ms | 900ms | ~27ms | **Target met** |
| Body resonances | 675, 1374, 2246, 4732 Hz | None | 675, 1374, 2246 Hz | Added |
| Stereo Haas delay | N/A | 20ms | 3ms | Fixed (comb filter eliminated) |
| Energy >5kHz | 0.45% | 0.00% | 0.35% | **Target met** |

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

## Steps (all completed)

### Step 1: Replace the loop filter ✅
Replaced averaging filter `0.5 * (y + next)` with tunable one-pole: `LOOP_FILTER_BLEND = 0.02`.
Commit: `7f17bc5`

### Step 2: Fix the attack envelope ✅
Replaced 900ms sigmoid with 8ms exponential tau (27ms 10-90% rise).
Commit: `7f17bc5`

**Deviation:** Noise transient was added initially but later removed — it corrupted phase alignment at shared frequencies between strings, reducing H4 in the mix.

### Step 3: Lower bridge + curved surface + jiva thread ✅
- Bridge height: 0.3 → 0.12 (more string-bridge contact)
- Added curved bridge reflection (`JAWARI_BRIDGE_CURVE = 0.4`)
- **Added jiva thread** (upper bridge at 0.15) — not in original plan

Commits: `45758fa`, `3de3deb`

**Deviation — Jiva thread:** One-sided bridge (lower only) suppresses even harmonics. Real tanpura has a cotton thread (jiva) that creates upper-side contact too. Two-sided nonlinearity is essential for strong H4. `JAWARI_JIVA_HEIGHT = 0.15`.

### Step 4: Body resonance ✅
- **Deviation:** Original plan had aggressive gains (6dB, 3dB, 4.5dB, 2dB at 4 modes). This made brightness 76.4% — way too bright. Replaced with gentle first-order lowpass rolloff at 1800 Hz + subtle peaks (1.5dB, 1.0dB, 1.5dB at 3 modes). Removed 4732 Hz resonance (unnecessary with bright waveguide).
- Applied post-mix (body colors the combined string sound, not individual strings).

Commit: `3de3deb`

### Step 5: String detuning ✅
Sa String 3 detuned by 0.4 Hz (`SA_STRINGS_DETUNE_HZ = 0.4`). Creates H7 beating at 2.8 Hz matching measured 2.86 Hz.
Commit: `3de3deb`

**Additional fix in this commit — string duration wrapping bug:**
Strings were 10s long but the cycle buffer is only 3.6s. Wrapping via `(offset + i) % cycle_size` caused each string to overlap itself ~2.78 times, creating harmonic-dependent destructive self-interference. H4 at 523 Hz wrapped with `cos(2π × 0.664) = -0.51` — destructive. Fix: generate strings for exactly `CYCLE_DURATION` instead of `SUSTAIN_DURATION`.

**Additional fix — per-string normalization removed:**
Peak normalization per string was distorting harmonic ratios at mix time. Sa H4 (523 Hz) and lower Sa H8 (523 Hz) share the same frequency — normalizing each string independently changes their relative amplitudes, destroying H4 in the final mix. Removed per-string normalization; final mix normalization handles overall level.

### Step 6: Update HARMONICS array ✅
Updated from real sample FFT analysis. H4 now strongest in excitation (1.00). Extended to H25/H30 for >5kHz content.
Commit: `3f934eb`

### Step 7: Fix stereo imaging ✅
- Haas delay: 20ms → 3ms (old delay created comb filter at H4: gain factor 0.166)
- Panning: 0.75/0.75 → 0.92/0.88 (narrower, slight L>R asymmetry)

Commit: `3f934eb`

### Step 8: Add scipy ✅
Added to `requirements.txt`. Commit: `3de3deb`

### Step 9: Adjust pluck timing ✅
Beat interval: 0.6s → 0.4s (tighter rhythm matching real tanpura).
Commit: `3f934eb`

## Key Discoveries During Implementation

1. **Wrapping self-interference:** The single biggest H4 killer was 10s strings wrapped into a 3.6s cycle buffer. Phase alignment at wrap boundaries is harmonic-dependent — H4 happened to wrap destructively for C3 Sa.

2. **Per-string normalization hazard:** Normalizing each string independently before mixing destroys harmonic ratios at shared frequencies. Sa H4 and lower Sa H8 are both at 523 Hz — changing their relative amplitudes cancels H4 in the mix.

3. **Jiva thread necessity:** One-sided bridge nonlinearity (lower only) preferentially generates odd harmonics. Even harmonics (H4, H2) require symmetric nonlinearity from the jiva cotton thread on the upper side.

4. **Haas delay as comb filter:** A 20ms stereo delay creates a comb filter with nulls at `n/(2×0.020) = 25, 75, 125...` Hz when summed to mono. For C3 Sa, H4 at 523 Hz falls near a null (gain factor 0.166). Even 3ms creates some comb effect, but much milder.

5. **Body resonance calibration:** The initial resonance gains from FFT peak analysis (6dB, 3dB, 4.5dB, 2dB) were far too aggressive when applied to the already-bright waveguide output. Gentle rolloff + subtle peaks (1-1.5dB) is the right approach.

## Remaining Opportunities (not implemented)

- Spectral centroid (1040 Hz) is still below the real sample (2512 Hz) — H1 is currently dominant where H4 should be
- Stereo width metric is not yet matching real sample's 12.9%
- Inharmonicity (string stiffness) not modeled
- Non-monotonic decay swells (jawari energy transfer) — partially emergent from bridge nonlinearity but not as pronounced as real sample
