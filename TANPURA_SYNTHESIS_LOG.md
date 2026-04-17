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

## Waveguide Abandoned → Fresh Start with `generate_tanpura_v2.py`

User verdict on final waveguide state: *"sounds like something recorded with technology 70 or 80 years ago"*. Delay-line feedback artifacts are inherent to Karplus-Strong — no parameter tuning can fix the lo-fi quality. Decision: abandon waveguide entirely, start fresh with `generate_tanpura_v2.py`.

Waveguide script preserved as `generate_tanpura_files.py` (commit `1e03ce7`).

---

## V2 Experiments (Additive / Resonator Bank)

Target: match Tanpura Droid quality — warm, mellow, metallic jawari buzz, clear plucks, natural string vibration. Must sound good on both Bose QC 35 headphones and Galaxy S22 Ultra speakers.

### Experiment 1: Basic Additive Synthesis

**Approach:** Sum of 20 sinusoids with per-harmonic amplitude, decay rate, and AM rate. Per-string parameters. Random phases. Pitch drift per harmonic. Noise transient in attack. Global jawari swell envelope. Pluck suppression ramp.

**Parameters:**
- HARMONICS: 20 entries, (n, amplitude, decay_rate, am_rate)
- Decay rates: 0.3–3.0 per second
- AM depth: 0.15, AM rates: 0.3–1.6 Hz
- Attack tau: 50ms
- Pluck level: 0.4 (suppresses initial 60% of pluck, ramps over 150ms)
- Jawari swell: global gamma envelope (t² × exp(-2t/peak))

**Result:** *"Horrible. Much worse compared to where we got to in v1. Sounds very unnatural. More than strings being plucked and resonating, it sounds like some metal strip vibrating. Very lo-fi."*

**Diagnosis:** Pure sinusoids with smooth envelopes sound organ-like. AM at 0.3–1.6 Hz creates pulsating/throbbing. Random phases create diffuse onset (no pluck transient). Pluck suppression kills the attack.

### Experiment 2: Slower Decay Rates

**Change:** Decay rates reduced from 0.3–3.0 to 0.10–0.55 per second so harmonics sustain 5–10× longer.

**Result:** *"Still super synthetic. Very drony. Very lo-fi. No swells (almost zero drone on the 4th string)."*

**Diagnosis:** Slower decay helped sustain but didn't fix the fundamental synthetic character. AM still causing helicopter drone. No spectral evolution.

### Experiment 3: Per-Harmonic Jawari Growth + Inharmonicity + No AM

**Changes:**
- Restructured HARMONICS to (n, pluck_amp, jawari_amp, jawari_peak_s, decay_rate)
- Jawari harmonics (H4, H7, H9-H11) GROW after pluck via gaussian rise
- Added inharmonicity B=0.00004 (partials slightly sharp → metallic)
- Removed all AM (eliminated helicopter drone)
- Faster attack tau: 8ms
- Stronger noise transient: 0.08 level, 60ms

**Result:** *"Not at all an improvement. Now it sounds completely droney. The pluck sound initial attack is completely lost."*

**Diagnosis:** Jawari amplitudes too dominant vs pluck amplitudes (H7 jawari_amp=0.75 vs pluck_amp=0.15). Sound became dominated by growing jawari harmonics. Pluck suppression (pluck_shape at 0.5) still active, cutting initial attack by 50%.

### Experiment 4: Coherent Phases + Reduced Jawari + No Pluck Suppression

**Changes:**
- Phase = 0 for all harmonics (coherent pluck excitation)
- Boosted pluck_amp, reduced jawari_amp (H7: pluck 0.50, jawari 0.25)
- Removed pluck_shape entirely
- H1 pluck_amp = 1.00 (dominant at pluck)

**Result:** *"No. Still too monotonously drone-y. Not how real strings would vibrate and interact. Too synthetic. Plucks still not as clear."*

**Diagnosis:** Additive synthesis with smooth exponential envelopes is fundamentally organ-like regardless of phase coherence. Independent sinusoids don't interact — no energy transfer, no mode coupling, no physical string behavior.

### Experiment 5: Resonator Bank + Body IR (new engine)

**Major rewrite.** Replaced additive synthesis with physically-motivated resonator bank:
- Each harmonic is a 2nd-order IIR biquad filter
- Excitation: single-sample impulse + 12ms noise burst
- Body IR convolution: synthetic tanpura gourd response (6 modes at 180–2800 Hz)
- HARMONICS restructured to (n, gain, T60_seconds) where T60 = time to -60dB
- T60 values: 7.0s (H1) down to 0.25s (H26)
- Extended harmonics to H26 for HF shimmer
- Simplified STRING_PARAMS (removed AM, swell, pluck_level)

**Result:** *"The vibrations/resonance seem to have all but vanished. Can hear just the plucks mostly."*

**Diagnosis:** Single-sample impulse creates extremely sharp transient peak. Peak normalization then crushes the sustain to near-silence. The pluck-to-sustain ratio is too extreme with impulse excitation.

### Experiment 6: Shaped Excitation + Soft Compression

**Changes:**
- Excitation changed from single impulse to 20ms exponential burst (τ=3ms) — ~66× more energy
- Added tanh soft compression (knee=0.4) to reduce pluck-to-sustain ratio

**Result:** *"This one sounds like a distorted guitar now."*

**Diagnosis:** tanh compression IS a distortion/waveshaping effect — creates intermodulation products. Resonator bank + body IR already sounds guitar-like (because KS and resonator banks ARE guitar string models). Compression made it worse.

### Experiment 7: Remove Compression + RMS Normalization

**Changes:**
- Removed tanh compression entirely
- Reduced body_mix from 0.35 to 0.20 (less body coloring)
- Changed mono normalization from peak-based to RMS-based (target RMS=0.18)
- Hard clip safety at ±0.95

**Result:** *"Step back to the one where plucks were the only sound pretty much. Little bit of sustain but that's it. Not at all like a real tanpura's jawari, no metallic buzzing, no swells & drops."*

**Diagnosis:** RMS normalization helped sustain survive but the resonator bank fundamentally produces guitar-like pluck-and-ring, not tanpura-like jawari. The biquad resonators decay monotonically — there's no mechanism for harmonics to grow, swell, or trade energy. The body IR adds acoustic coloring but doesn't create jawari character. The core issue: resonator bank = plucked string without a bridge. Jawari requires nonlinear interaction (string buzzing against bridge) which neither additive nor linear resonator models can produce.

### Summary of What Doesn't Work

| Approach | Problem |
|----------|---------|
| Per-harmonic AM (0.15 depth, 0.3–1.6 Hz) | Helicopter drone |
| Pluck suppression (pluck_shape ramp) | Kills pluck transient |
| Random phases per harmonic | Diffuse organ-like onset, no pluck character |
| High jawari_amp vs low pluck_amp | Drowns pluck, creates monotonous drone |
| Single-sample impulse excitation | Extreme transient, sustain crushed by normalization |
| Peak normalization after sharp transients | Crushes sustain to silence |
| tanh compression | Distorted guitar sound |
| Large body_mix (0.35+) | Adds wrong character (guitar-like) |
| Fast decay rates (0.3–3.0/s) | Harmonics die too quickly, no sustain |
| Slow decay rates (0.08–0.55/s) with uniform amplitudes | Monotonous drone |
| Additive synthesis in general | Fundamentally organ-like; smooth envelopes ≠ physical string |

### Key Unsolved Problem

Every approach sounds either synthetic/organ-like (additive) or guitar-like (resonator bank). Neither captures the tanpura's unique character: a warm, sustained drone with metallic jawari buzz that sounds like a real acoustic instrument.

**The missing piece is jawari itself.** All approaches so far use linear models (sinusoids, biquad resonators) which can only decay monotonically. Real jawari requires nonlinear string-bridge interaction:
- String buzzes against the curved bridge surface
- This transfers energy between harmonics (H4↔H7 trading)
- Creates non-monotonic amplitude swells (harmonics GROW then decay)
- Produces the characteristic metallic buzzing texture

Linear synthesis cannot produce this. The waveguide DID model it (bridge reflection), but the delay-line artifacts made it sound lo-fi. The challenge: find a way to get jawari's nonlinear character without the waveguide's lo-fi artifacts.

Tanpura Droid almost certainly uses high-quality recorded samples, not synthesis.
