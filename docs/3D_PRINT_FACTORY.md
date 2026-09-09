# 3D Print Factory

Цель: готовить модели для Flying Bear S1 на Linux без управления OrcaSlicer через Windows UI.

## Printer

- Model: Flying Bear S1
- Address: set in PRINT_MOONRAKER_URL
- Web UI: Fluidd at http://YOUR_PRINTER_IP/
- Moonraker API: http://YOUR_PRINTER_IP:7125
- Klipper state when checked: ready
- Kinematics: CoreXY
- Safe print volume: 220 x 220 x 250 mm
- Firmware axis max observed: X 222, Y 225, Z 260
- Nozzle: 0.4 mm
- Filament: 1.75 mm

## Folders

```text
PRINT_INBOX      # сюда оператор кладет модели
PRINT_JOBS       # сюда helper пишет job-папки
```

## Modes

Оставлены только два режима:

- beautiful-strong: красиво+прочно, 0.16 mm layer, 4 walls, 22 percent gyroid infill.
- fast: быстро, 0.24 mm layer, 3 walls, 12 percent gyroid infill.

Draft mode убран.

## Calibration and Presentation

По умолчанию каждый подготовленный G-code включает ручную проверку сопла перед mesh и стартовую автоподготовку принтера:

- нагрев стола и сопла только до standby-температуры филамента;
- G28 homing;
- парковку головы у переднего края;
- PAUSE с просьбой убрать соплю/каплю пластика с сопла и стола;
- продолжение только после RESUME;
- Z_TILT_ADJUST, если он доступен в профиле;
- BED_MESH_CALIBRATE, если он доступен в профиле;
- полный нагрев сопла и purge line уже после калибровки стола.

После завершения печати helper встраивает финальный блок: выключает нагрев/обдув, уводит Z вниз на presentation height, паркует XY и отключает X/Y/E моторы, чтобы проще снять подложку с моделью.

Defaults:

    PRINT_DEFAULT_CALIBRATION=auto
    PRINT_DEFAULT_NOZZLE_CHECK=manual
    PRINT_DEFAULT_PRESENT_Z=235

Отключать автокалибровку стоит только явно:

    bin/print-helper prepare model.stl --height 180 --filament PETG --mode beautiful-strong --calibration off

Отключать ручную проверку сопла/стола перед mesh стоит только явно и осознанно:

    bin/print-helper prepare model.stl --height 180 --filament PETG --mode beautiful-strong --nozzle-check off

## Basic Flow

```bash
cd /path/to/3d-print-inbox
bin/print-helper init-dirs
bin/print-helper status
bin/print-helper filaments
bin/print-helper modes
bin/print-helper inspect model.stl --height 180
bin/print-helper prepare model.stl --height 180 --filament PETG --mode beautiful-strong
bin/print-helper prepare model.stl --height 180 --filament PETG --mode beautiful-strong --nozzle-check off
bin/print-helper prepare model.stl --height 180 --filament PETG --mode beautiful-strong --present-z 245
```

Если модель лежит в inbox, достаточно имени файла:

```bash
bin/print-helper prepare sword.stl --length 1500 --filament PETG --mode beautiful-strong
```

## Output

Каждый prepare создает job-папку:

```text
PRINT_JOBS/YYYYMMDD-HHMMSS_model/
  original model copy
  metadata.json
  print_plan.md
  *.gcode                 # если slicer успешно отработал
```

## Printer Control

```bash
bin/print-helper monitor --once
bin/print-helper upload /path/to/file.gcode
bin/print-helper upload /path/to/file.gcode --start
bin/print-helper start ai_jobs/file.gcode --allow-direct-start
bin/print-helper pause
bin/print-helper resume
bin/print-helper cancel
```

По умолчанию helper только готовит G-code. Печать начинается только отдельной командой upload --start для подготовленного G-code с AI START / AI END маркерами. Прямой start оставлен как ручной аварийный обход и требует --allow-direct-start, потому что он не может проверить локальный файл перед запуском.

## Installed Skills

Main Hermes routing skill:

```text
/mnt/storage2/hermes-home/skills/productivity/3d-print-inbox/SKILL.md
```

Use `skill/3d-print-inbox/SKILL.md` as the main Hermes routing skill. Older companion-skill fragments should stay out of active routing so 3D print requests resolve to one clear skill.

## Current MVP Limits

- STL/OBJ/3MF inspection works in Python.
- Moonraker status/upload/start/pause/resume/cancel works through API.
- Slicing uses the first available CLI slicer: prusa-slicer, OrcaSlicer, or slic3r.
- Generated G-code includes manual nozzle/bed clean PAUSE before mesh, auto calibration by default, and post-print bed-down presentation.
- Actual boolean mesh cutting/connectors are planned but not yet implemented; oversized models currently produce a split/connectors plan.
