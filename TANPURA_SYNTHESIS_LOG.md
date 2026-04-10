# Tanpura Synthesis: Development Log

## Starting Point (PR #4, commit 00caecf)

Karplus-Strong waveguide with bridge termination. First successful jawari implementation after 12+ failed additive synthesis attempts.

**Parameters:**
- Loop filter blend: 0.5 (standard KS averaging)
- Bridge height: 0.3 (one-sided, lower only)
- Attack: 900ms sigmoid
- String duration: 10s, wrapped into 3.6s cycle via `% cycle_size`
- Per-string peak normalization
- Stereo: 20ms Haas delay, 0.75/0.75 panning
- Beat interval: 0.6s

**Sound character:** Warm, smooth drone. Plucks blended into continuous texture. Too dark spectrally but pleasant to listen to.

## Real Sample Analysis

Compared generated c3_P against `c3_P real.wav` (real Calcutta-standard tanpura, C3 tonic, Pa string). Key measurements:

| Metric | Real | Generated |
|--------|------|-----------|
| Spectral centroid | 2512 Hz | 664 Hz |
| Brightness (>1kHz) | 28.1% | 2.7% |
| H4 amplitude | 1.000 | 0.013 |
| Attack time | 27ms | 900ms |
| Energy >5kHz | 0.45% | 0.00% |

These numbers drove the improvement plan. In hindsight, chasing spectral metrics was a mistake — the real sample's brightness comes from the specific instrument, room, and microphone, not from the synthesis algorithm.

## Changes Made (Steps 1-9)

### What worked (keep)

1. **Jiva thread (upper bridge):** Two-sided nonlinearity is essential for even harmonics (H4). One-sided bridge suppresses them. `JAWARI_JIVA_HEIGHT` parameter added. **Keep this.**

2. **Body resonance filter:** Gentle lowpass rolloff at 1800 Hz + subtle IIR peaks at body modes (675, 1374, 2246 Hz). Applied post-mix. Adds warmth. **Keep this** (with the reduced gains: 1.5, 1.0, 1.5 dB — the original plan's 6, 3, 4.5 dB were far too aggressive).

3. **Sa string detuning:** 0.4 Hz between strings 2 and 3 creates beating shimmer. H7 beats at 2.8 Hz matching measured 2.86 Hz. **Keep this.**

4. **Updated HARMONICS array:** Better initial excitation spectrum from real sample FFT. H4 as strongest. Extended to H25/H30 for HF content. **Keep this.**

5. **Curved bridge reflection:** Softer nonlinearity than hard reflection. Produces shimmering jawari rather than harsh buzz. **Keep this.**

### What didn't work (revert or adjust)

1. **Loop filter blend 0.02:** Way too bright. Made the sound harsh and metallic. The waveguide preserved too many upper harmonics, creating an unnatural, tinny quality. **Revert toward ~0.15** — warm but not as dark as original 0.5.

2. **Attack tau 8ms:** Too fast. Pluck transients punched through the drone. Even 30ms was too fast. The original 900ms sigmoid was too slow, but the right value is somewhere around 100-200ms. **Set to ~150ms.**

3. **Bridge height 0.12:** Too aggressive. Created percussive "plop" sounds, especially on lower strings. 0.25 eliminated the plop. **Set to ~0.20** (compromise between jawari strength and smoothness).

4. **String duration = cycle duration (3.6s):** Fixed the wrapping H4 bug but created a worse problem — each cycle is dominated by attack transients because strings don't sustain long enough to form a continuous drone bed. **Revert to 10s strings, fix looping with cross-fade instead of wrapping.**

5. **Noise transient (30ms broadband):** Corrupted phase alignment between strings at shared frequencies. Removed early on. **Stay removed.**

6. **Per-string normalization removal:** Removing it was correct — per-string peak normalization distorts harmonic ratios at shared frequencies (Sa H4 = lower Sa H8 at 523 Hz). **Stay removed.**

7. **Stereo 20ms Haas delay:** Created comb filter destroying H4 in mono sum (gain factor 0.166 at 523 Hz for C3). Reduced to 3ms. **Keep at 3ms.**

8. **Beat interval 0.4s:** Too fast. Original 0.6s was better. **Revert to 0.6s** (or tune by ear).

### Key discoveries

1. **Wrapping self-interference:** 10s strings wrapped into 3.6s buffer via `% cycle_size` causes each string to overlap itself ~2.78 times. Phase alignment at wrap boundaries is harmonic-dependent — H4 wraps destructively (cos=-0.51) for C3 Sa. **Fix: cross-fade looping instead of modular wrapping.**

2. **Normalization undoes volume:** Two normalization steps (mono buffer and final stereo) scale output to fixed peak regardless of `volume` parameter. Must choose: either normalize (consistent level) or manual volume control (not both).

3. **tanh compression doesn't help:** With high drive, both peaks and sustain saturate equally. With low drive, not enough compression. Envelope-aware compression would work but adds complexity.

4. **Spectral metrics ≠ perceptual quality:** A spectrally "accurate" synthesis can sound worse than a less accurate but more musical one. The original warm, dark sound was perceptually closer to a real tanpura than the spectrally "correct" harsh bright version.

## Current Pivot: Reset with Lessons Learned

### Approach

Keep the waveguide engine and the additions that genuinely improved it (jiva, body resonance, detuning, updated harmonics, curved bridge). Revert the parameters that made it sound worse (extreme brightness, fast attack, low bridge, short strings). Fix the looping strategy properly.

### Target parameters

| Parameter | Original | Over-corrected | New target |
|-----------|----------|----------------|------------|
| Loop filter blend | 0.5 | 0.02 | 0.15 |
| Bridge height | 0.3 | 0.12 | 0.20 |
| Jiva height | (none) | 0.15 | 0.25 |
| Bridge curve | (none) | 0.4 | 0.4 |
| Attack | 900ms sigmoid | 8ms exp | ~150ms exp |
| String duration | 10s (wrapped) | 3.6s | 10s (cross-fade) |
| Beat interval | 0.6s | 0.4s | 0.6s |
| Stereo delay | 20ms | 3ms | 3ms |
| Volume | 0.5 + normalize | 0.5 + normalize | 0.5 + normalize |

### Looping strategy

Old: generate strings for cycle duration, wrap via `(offset + i) % cycle_size`.
Problem: either self-interference (long strings) or no drone bed (short strings).

New: generate strings for full sustain (10s), mix into 2-cycle buffer without wrapping, cross-fade second cycle over first to create seamless single-cycle loop. String tails from cycle 1 naturally extend into cycle 2, so the loop point always has continuous drone.
