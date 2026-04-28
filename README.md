# Naadshala

Audio generation tools for Hindustani classical music applications.

**Naadshala** (नादशाला) means "sound workshop" in Sanskrit - a place where sonic artifacts are crafted.

## Scripts

### generate_tanpura_files_v2.py _(primary)_

Generates loopable tanpura drone sounds using additive jawari synthesis.

- **Output:** OGG Vorbis → `output/tanpura_ogg/` (Android); CAF/ALAC → `output/tanpura_caf/` (iOS)
- **Coverage:** 15 Sa values (G#2 to A#3) × 3 String 1 options (P, m, N) = 45 files per format
- **Harmonic structure:** Derived from real Calcutta-standard tanpura spectral template
- **Key feature:** Per-string jawari buzz via asymmetric waveshaping + modal pluck transient
- **Looping:** Renders 6 cycles, extracts cycle 4, applies 150ms crossfade for seamless looping
- **Requirement:** CAF output requires macOS (`afconvert`, pre-installed); OGG output works on any platform
- **Sample rate:** 48 kHz stereo, ~3.6 seconds per file

> `generate_tanpura_files.py` is the previous Karplus-Strong waveguide implementation, kept for reference.

### generate_reference_plucks.py

Generates guitar-like reference pluck sounds using Karplus-Strong algorithm.

- **Output:** OGG Vorbis files (~1 second each)
- **Coverage:** 15 Sa values × 12 swars = 180 files
- **Use case:** Training mode reference notes for pitch matching

### generate_swarmandal_plucks.py

Generates swarmandal-like pluck sounds using Karplus-Strong algorithm.

- **Output:** OGG Vorbis files (~3 seconds each, 500ms fade out)
- **Coverage:** 15 Sa values × 13 swars (12 + ati-taar Sa) = 195 files
- **Character:** Brighter and longer sustain than reference plucks

## Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Generate tanpura files
python generate_tanpura_files_v2.py

# Generate pluck files
python generate_reference_plucks.py

# Generate swarmandal files
python generate_swarmandal_plucks.py
```

Output files are written to `./output/tanpura_ogg/`, `./output/tanpura_caf/`, `./output/plucks/`, and `./output/swarmandal/` by default.

## Audio Configuration

All scripts use:
- **Format:** OGG Vorbis (compressed, good quality)
- **Tuning:** Just Intonation ratios (not equal temperament)
- **Sample rate:** 48 kHz (tanpura v2); 44.1 kHz (plucks, swarmandal)

### Just Intonation Ratios

| Swar | Ratio |
|------|-------|
| S | 1/1 |
| r | 16/15 |
| R | 9/8 |
| g | 6/5 |
| G | 5/4 |
| m | 4/3 |
| M | 45/32 |
| P | 3/2 |
| d | 8/5 |
| D | 5/3 |
| n | 16/9 |
| N | 15/8 |

## License

MIT
