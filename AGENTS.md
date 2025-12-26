# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Naadshala ("sound workshop" in Sanskrit) generates audio assets for Hindustani classical music applications. It produces tanpura drone sounds and reference pluck notes using digital synthesis.

## Commands

```bash
# Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Generate tanpura files (45 OGG files → output/tanpura/)
python generate_tanpura_files.py

# Generate pluck files (180 OGG files → output/plucks/)
python generate_reference_plucks.py

# Generate swarmandal files (195 OGG files → output/swarmandal/)
python generate_swarmandal_plucks.py
```

## Architecture

**Three independent audio generators:**

1. **generate_tanpura_files.py** - Additive synthesis for tanpura drones
   - Creates 45 files: 15 Sa frequencies × 3 String 1 options (P, m, N)
   - Uses harmonic structure extracted from real Calcutta-standard tanpura
   - Stereo output with Haas effect, ~10 seconds per file

2. **generate_reference_plucks.py** - Karplus-Strong algorithm for guitar-like plucks
   - Creates 180 files: 15 Sa frequencies × 12 swars
   - Mono output, ~1 second per file

3. **generate_swarmandal_plucks.py** - Karplus-Strong algorithm for swarmandal-like plucks
   - Creates 195 files: 15 Sa frequencies × (12 swars + ati-taar Sa)
   - Brighter (0.95) and longer sustain (0.997) than guitar plucks
   - Mono output, ~3 seconds per file with 500ms fade out

**Audio conventions:**
- Sample rate: 44.1 kHz
- Format: OGG Vorbis
- Tuning: Just Intonation ratios (not equal temperament)
- Sa range: G#2 (103.83 Hz) to A#3 (233.08 Hz)

**Filename patterns:**
- Tanpura: `{sa}_{string1}.ogg` (e.g., `c3_P.ogg`)
- Plucks/Swarmandal: `{sa}_{swar_number}_{swar}.ogg` (e.g., `c3_1_S.ogg`)
- Swarmandal ati-taar Sa: `{sa}_S2.ogg` (e.g., `c3_S2.ogg`)

## Domain Knowledge

- **Swars** are named using case to indicate komal/shuddh variants: lowercase = komal (flat), uppercase = shuddh (natural) or teevra (sharp for Ma)
- **Jawari** is the characteristic buzzing timbre of tanpura created by the bridge; H7 harmonic is dominant
- Both scripts are designed for pre-generating assets to commit (fast builds, no Python needed at runtime)
