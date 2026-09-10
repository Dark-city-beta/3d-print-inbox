---
name: 3d-print-inbox
description: "Use when DARK asks Hermes to prepare, tune, slice, upload, monitor, or run 3D prints from the Freeman model inbox for the Flying Bear S1 printer. Prefer this Linux pipeline over controlling OrcaSlicer through Windows."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [3d-printing, slicer, klipper, moonraker, fluidd, flyingbear-s1, stl, obj, 3mf, filament]
    related_skills: [my-computer-helper-ai-project]
---

# 3D Print Inbox

This is DARK's main and only top-level 3D printing skill. Use it when a model is placed in the inbox, when a print needs to be prepared for the home Flying Bear S1, or when Hermes should manage slicing and Moonraker/Fluidd control from Freeman/Linux instead of driving OrcaSlicer on the Windows workstation.

Default operating chain:

    model in /mnt/city17/3d-print-inbox -> bin/print-helper inspect/prepare -> PrusaSlicer/OrcaSlicer CLI -> Moonraker at 192.168.31.128 -> Flying Bear S1

## Known Locations

    project root: /mnt/city17/Free project/My computer Helper AI
    print CLI: /mnt/city17/Free project/My computer Helper AI/bin/print-helper
    inbox: /mnt/city17/3d-print-inbox
    jobs: /mnt/city17/3d-print-jobs
    printer UI: Fluidd
    Moonraker API: http://192.168.31.128:7125
    printer profile: profiles/3d/printers/flyingbear_s1.json
    filament profiles: profiles/3d/filaments/*.json
    operator notes: docs/3D_PRINT_FACTORY.md
    project repo: https://github.com/Dark-city-beta/3d-print-inbox

Run commands from the project root unless an absolute path is clearer:

    cd "/mnt/city17/Free project/My computer Helper AI"
    bin/print-helper status

## Printer Facts

Observed from Moonraker/Klipper on 2026-09-09:

- Printer: Flying Bear S1 through Fluidd/Moonraker at 192.168.31.128:7125.
- Firmware stack: Klipper ready, Moonraker API available.
- Motion: CoreXY.
- Safe/calibrated slicer area from the JSON profile: X 3..213 mm, Y 3..213 mm (210 x 210 mm).
- Nominal bed is 220 x 220 x 250 mm, but this is not the safe printable/slicer area.
- Firmware travel observed: X -5.5..222, Y -5..225, Z -6..260; travel range is not print area. Use `build_volume_mm` + `bed_origin_mm` as the source of truth for slicing.
- Nozzle: 0.4 mm; filament: 1.75 mm.
- Hotend max: 310 C; bed max: 120 C.
- Pressure advance: 0.058.
- Input shaper: MZV, X 57.8 Hz and Y 57.6 Hz.
- Useful macros/API operations include pause, resume, cancel, file upload, history, webcam, timelapse, bed mesh, Z tilt, and KAMP-style helpers.

Before a real print, check live status. If the printer is not ready, report the blocker instead of starting.

Default generated G-code performs a manual nozzle check, pre-print calibration, and post-print presentation:

- Start: heat the bed and warm the nozzle only to filament standby temperature, home with G28, park at the front, then PAUSE before bed mesh so the operator can remove nozzle ooze or any blob on the plate.
- After RESUME: run Z_TILT_ADJUST when available, run BED_MESH_CALIBRATE, heat to first-layer temperature, then purge a line after mesh calibration.
- End: stop heaters/fan, move Z down to the presentation height, park XY inside the safe X/Y 3..213 profile, and disable X/Y/E motors so DARK can remove the plate/model more easily.
- Use --calibration off only when DARK explicitly asks to skip auto calibration for a known-good repeat print.
- Use --nozzle-check off only when the operator explicitly accepts the risk of bed mesh or first-layer contamination from ooze.
- Use --present-z N only when DARK asks for a different final bed-down height.

## User Contract

When DARK drops or names a model, do the smallest useful interrogation:

- Confirm the target size using one constraint if possible: height, width, length, exact scale, or original size. Preserve aspect ratio unless DARK asks otherwise.
- Ask what filament is currently loaded. If the brand/subtype is known, use it; otherwise start from the material profile.
- Offer only two modes: beautiful-strong and fast. Do not offer draft mode.
- Ask whether the job should be prepared only, uploaded, or uploaded and started. Start printing only when DARK explicitly asks to start/print now.
- Keep pre-print calibration enabled by default because the printer may have drifted. Mention if DARK asks to skip it.
- Keep the manual nozzle/bed clean check enabled by default. The print will pause before BED_MESH_CALIBRATE and wait for RESUME.
- Use automatic support judgment by default, then state whether supports/brim are expected and why.

If information is missing but a reasonable preview is still useful, inspect the model and create a prepare-only plan with assumptions clearly written in the job folder.

## Workflow

1. Initialize/check the environment:

    bin/print-helper init-dirs
    bin/print-helper status
    bin/print-helper filaments
    bin/print-helper modes

2. Inspect the model:

    bin/print-helper inspect /mnt/city17/3d-print-inbox/model.stl

3. Prepare a job:

    bin/print-helper prepare /mnt/city17/3d-print-inbox/model.stl --height 180 --filament PETG --mode beautiful-strong
    bin/print-helper prepare /mnt/city17/3d-print-inbox/model.stl --length 1500 --filament PETG --mode beautiful-strong
    bin/print-helper prepare /mnt/city17/3d-print-inbox/model.stl --scale 0.5 --filament PLA --mode fast
    bin/print-helper prepare /mnt/city17/3d-print-inbox/model.stl --height 180 --filament PETG --mode beautiful-strong --calibration off
    bin/print-helper prepare /mnt/city17/3d-print-inbox/model.stl --height 180 --filament PETG --mode beautiful-strong --nozzle-check off
    bin/print-helper prepare /mnt/city17/3d-print-inbox/model.stl --height 180 --filament PETG --mode beautiful-strong --present-z 245

4. Upload/start only when requested:

    bin/print-helper upload /path/to/job/file.gcode
    bin/print-helper upload /path/to/job/file.gcode --start
    bin/print-helper monitor --once
    bin/print-helper pause
    bin/print-helper resume
    bin/print-helper cancel

When starting a job, prefer upload --start on a G-code file generated by this helper. The upload command checks for AI START / AI END markers before starting. Direct start of an already-uploaded Moonraker filename bypasses local G-code inspection and should be used only as a manual override with --allow-direct-start.

The helper writes each prepared job under:

    /mnt/city17/3d-print-jobs/YYYYMMDD-HHMMSS_model/
      original/copy of model
      print_plan.md
      metadata.json
      *.gcode if slicing succeeded

## Print Modes

Use only these modes unless DARK explicitly changes the local profiles:

- beautiful-strong: default. Better surfaces and stronger walls for final parts, props, brackets, connectors, and visible objects.
- fast: faster useful print when appearance/detail is less important. This is not draft mode.

For filament tuning, prefer existing profiles for PETG, PLA, ABS, TPU, and SILK. If DARK names a specific vendor/color/subtype and the local profile is too generic, look up current material guidance and keep temperatures inside the printer limits.

## Large Models

If the final dimensions exceed the Flying Bear S1 profile:

- Produce a split plan instead of pretending the model is ready.
- Suggest assembly strategy based on geometry: pins, screw bosses, threaded inserts, dovetails, alignment keys, or hidden seams.
- For long props such as a 1.5 m sword, plan numbered sections and connector orientation so layer lines and loads make sense.
- Current helper can detect oversize and write a split/connectors plan, but it does not yet perform real boolean mesh cutting or connector generation. Use external mesh tooling or ask before doing that work.

## Fallbacks

- Use Linux CLI slicing first: prusa-slicer, PrusaSlicer, orca-slicer, OrcaSlicer, then slic3r.
- Use my-computer-helper-ai-project only as a Windows/Orca GUI fallback when the Linux pipeline cannot finish the job.
- Do not use browser/Fluidd clicks for operations available through Moonraker API unless API access fails and visual control is specifically needed.
- Legacy companion skills from the first install are not part of active routing. Treat this skill as the source of truth for Flying Bear S1 print work.

## Done Criteria

A prepared job is complete when the job folder has print_plan.md and metadata.json, the scale/dimensions/filament/mode are clear, and either a G-code file exists or the plan explains why slicing was not run. For sliced jobs, metadata.json must record nozzle_check_summary, calibration_summary, present_z_mm, start_gcode, and end_gcode, and the generated G-code should contain AI START / AI NOZZLE CHECK / AI END markers. A started job is complete only after Moonraker accepts the file and monitor --once confirms the printer is active, paused for nozzle cleaning, or queued.
