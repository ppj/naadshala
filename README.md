# Naadshala

Audio generation tools for Hindustani classical music applications.

**Naadshala** (नादशाला) means "sound workshop" in Sanskrit - a place where sonic artifacts are crafted.

## Scripts

### generate_tanpura_files.py

Generates realistic tanpura drone sounds using additive synthesis.

- **Output:** OGG Vorbis files (~10 seconds each)
- **Coverage:** 15 Sa values (G#2 to A#3) x 3 String 1 options (P, m, N) = 45 files
- **Harmonic structure:** Extracted from real Calcutta-standard male tanpura via spectral analysis
- **Key feature:** Authentic jawari effect with H7 as dominant harmonic

### generate_reference_plucks.py

Generates guitar-like reference pluck sounds using Karplus-Strong algorithm.

- **Output:** OGG Vorbis files (~1 second each)
- **Coverage:** 15 Sa values x 12 swars = 180 files
- **Use case:** Training mode reference notes for pitch matching

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
python generate_tanpura_files.py

# Generate pluck files
python generate_reference_plucks.py
```

Output files are written to `./output/tanpura/` and `./output/plucks/` by default.

## Audio Configuration

Both scripts use:
- **Sample rate:** 44.1 kHz
- **Format:** OGG Vorbis (compressed, good quality)
- **Tuning:** Just Intonation ratios (not equal temperament)

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
