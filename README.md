# 3d-print-inbox

Hermes/Codex skill and Linux helper for preparing 3D-print jobs without driving a slicer through a remote Windows GUI.

The project is built around a Flying Bear S1 running Klipper + Moonraker + Fluidd, but the paths and Moonraker URL are configurable.

## What It Does

- Accepts STL, OBJ, and 3MF models from a local inbox.
- Inspects model dimensions, bounding box, triangle count, surface area, approximate volume, and overhang ratios.
- Scales by target height, width, length, or explicit scale while preserving proportions.
- Uses two operator-facing modes: `beautiful-strong` and `fast`.
- Selects filament profiles for PETG, PLA, ABS, TPU, and Silk PLA.
- Slices through CLI slicers on Linux, preferring PrusaSlicer/Orca-compatible flows.
- Uploads, starts, pauses, resumes, cancels, and monitors prints through Moonraker.
- Adds pre-print calibration G-code by default: heat, `G28`, `Z_TILT_ADJUST`, `BED_MESH_CALIBRATE`, and purge line.
- Adds post-print presentation G-code: heaters/fan off, Z moves down to the presentation height, XY parks, X/Y/E motors disable.
- Blocks accidental `upload --start` for G-code without `AI START` / `AI END` markers unless explicitly overridden.

## Layout

```text
skill/3d-print-inbox/SKILL.md        Hermes skill instructions
bin/print-helper                     CLI wrapper
scripts/print3d/print_helper.py      Python helper
configs/print_factory.example.env    Local config template
profiles/3d/printers/                Printer profiles
profiles/3d/filaments/               Filament profiles
docs/3D_PRINT_FACTORY.md             Operator notes
```

## Setup

Install a CLI slicer and Python requests:

```bash
sudo apt install prusa-slicer python3-requests
```

Copy the config template and edit the local paths and printer URL:

```bash
cp configs/print_factory.example.env configs/print_factory.env
$EDITOR configs/print_factory.env
```

Create the inbox/jobs folders:

```bash
bin/print-helper init-dirs
```

Optional Hermes install:

```bash
mkdir -p ~/.codex/skills/productivity/3d-print-inbox
cp skill/3d-print-inbox/SKILL.md ~/.codex/skills/productivity/3d-print-inbox/SKILL.md
```

## Common Commands

```bash
bin/print-helper status
bin/print-helper filaments
bin/print-helper modes
bin/print-helper inspect /path/to/model.stl
bin/print-helper prepare /path/to/model.stl --height 180 --filament PETG --mode beautiful-strong
bin/print-helper prepare /path/to/model.stl --height 180 --filament PETG --mode beautiful-strong --present-z 245
bin/print-helper upload /path/to/file.gcode
bin/print-helper upload /path/to/file.gcode --start
bin/print-helper monitor --once
```

## Current Limits

- Oversized models produce a split/connectors plan, but real boolean mesh cutting and connector generation are not implemented yet.
- Printer profiles should be checked against the live machine before production printing.
- The default print profile is tuned as a practical starting point, not a replacement for filament-specific calibration towers.

## License

MIT
