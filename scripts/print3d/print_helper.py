#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, os, shutil, struct, subprocess, time, urllib.error, urllib.request, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
try:
    import requests
except Exception:
    requests = None

ROOT = Path(os.environ.get('PRINT_HELPER_ROOT', Path(__file__).resolve().parents[2]))
INBOX = Path(os.environ.get('PRINT_INBOX', ROOT / 'inbox'))
JOBS = Path(os.environ.get('PRINT_JOBS', ROOT / 'jobs'))
MOONRAKER_URL = os.environ.get('PRINT_MOONRAKER_URL', 'http://127.0.0.1:7125').rstrip('/')
DEFAULT_PRINTER = os.environ.get('PRINT_DEFAULT_PRINTER', 'flyingbear_s1')
DEFAULT_MODE = os.environ.get('PRINT_DEFAULT_MODE', 'beautiful-strong')
DEFAULT_FILAMENT = os.environ.get('PRINT_DEFAULT_FILAMENT', 'PETG')
DEFAULT_CALIBRATION = os.environ.get('PRINT_DEFAULT_CALIBRATION', 'auto')
DEFAULT_NOZZLE_CHECK = os.environ.get('PRINT_DEFAULT_NOZZLE_CHECK', 'manual')
DEFAULT_NOZZLE_STANDBY = os.environ.get('PRINT_DEFAULT_NOZZLE_STANDBY_C')
DEFAULT_PRESENT_Z = os.environ.get('PRINT_DEFAULT_PRESENT_Z')

MODES = {
  'beautiful-strong': dict(label='красиво+прочно', layer=0.16, first_layer=0.22, walls=4, top=5, bottom=5, infill=22, pattern='gyroid', support_angle=50, speed=70),
  'fast': dict(label='быстро', layer=0.24, first_layer=0.26, walls=3, top=4, bottom=4, infill=12, pattern='gyroid', support_angle=55, speed=120),
}

def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def printer_profile(name=DEFAULT_PRINTER):
    return load_json(ROOT / 'profiles' / '3d' / 'printers' / (name + '.json'))

def filaments():
    return [load_json(p) for p in sorted((ROOT / 'profiles' / '3d' / 'filaments').glob('*.json'))]

def filament_profile(name):
    n = name.lower()
    for f in filaments():
        if any(n == str(a).lower() for a in [f.get('id','')] + f.get('aliases', [])):
            return f
    raise SystemExit('Unknown filament: ' + name)

def http_json(path, method='GET', payload=None, timeout=10):
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(MOONRAKER_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8', 'replace'))
    except urllib.error.HTTPError as e:
        raise SystemExit('Moonraker HTTP %s: %s' % (e.code, e.read().decode('utf-8', 'replace')))
    except Exception as e:
        raise SystemExit('Moonraker request failed: %s' % e)

def status(_a):
    info = http_json('/printer/info').get('result', {})
    server = http_json('/server/info').get('result', {})
    q = '/printer/objects/query?toolhead&extruder&heater_bed&print_stats&virtual_sdcard&configfile'
    st = http_json(q).get('result', {}).get('status', {})
    cfg = st.get('configfile', {}).get('config', {})
    th, ex, bed, ps, vsd = st.get('toolhead',{}), st.get('extruder',{}), st.get('heater_bed',{}), st.get('print_stats',{}), st.get('virtual_sdcard',{})
    print('Printer: %s state=%s message=%s' % (info.get('hostname'), info.get('state'), info.get('state_message')))
    print('Moonraker: %s api=%s klippy=%s' % (server.get('moonraker_version'), server.get('api_version_string'), server.get('klippy_state')))
    print('Motion: %s max_velocity=%s max_accel=%s' % (cfg.get('printer',{}).get('kinematics'), cfg.get('printer',{}).get('max_velocity'), cfg.get('printer',{}).get('max_accel')))
    print('Axes: min=%s max=%s homed=%r' % (th.get('axis_minimum'), th.get('axis_maximum'), th.get('homed_axes')))
    print('Nozzle: diameter=%s filament=%s temp=%s/%sC' % (cfg.get('extruder',{}).get('nozzle_diameter'), cfg.get('extruder',{}).get('filament_diameter'), ex.get('temperature'), ex.get('target')))
    print('Bed: temp=%s/%sC' % (bed.get('temperature'), bed.get('target')))
    print('Print: state=%s file=%r progress=%s' % (ps.get('state'), ps.get('filename'), vsd.get('progress')))

def sync_printer(a):
    st = http_json('/printer/objects/query?toolhead&configfile').get('result', {}).get('status', {})
    cfg, th = st.get('configfile',{}).get('config',{}), st.get('toolhead',{})
    live = dict(id=a.printer, source='Moonraker %s captured %s' % (MOONRAKER_URL, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())),
                axis_minimum=th.get('axis_minimum'), axis_maximum=th.get('axis_maximum'),
                printer=cfg.get('printer',{}), extruder=cfg.get('extruder',{}), heater_bed=cfg.get('heater_bed',{}),
                features=sorted([k for k in cfg if k.startswith('bed_mesh') or k.startswith('gcode_macro')])[:120])
    out = ROOT / 'profiles' / '3d' / 'printers' / (a.printer + '.live.json')
    out.write_text(json.dumps(live, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Wrote live printer profile:', out)

def resolve_model(s):
    p = Path(s)
    candidates = [p] if p.is_absolute() else [Path.cwd()/p, INBOX/p, ROOT/p]
    for c in candidates:
        if c.exists(): return c.resolve()
    raise SystemExit('Model not found: %s' % s)

def tri_area(a,b,c):
    ux,uy,uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx,vy,vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx,ny,nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    return 0.5 * math.sqrt(nx*nx+ny*ny+nz*nz)

def norm_z(a,b,c):
    ux,uy,uz = b[0]-a[0], b[1]-a[1], b[2]-a[2]
    vx,vy,vz = c[0]-a[0], c[1]-a[1], c[2]-a[2]
    nx,ny,nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
    l = math.sqrt(nx*nx+ny*ny+nz*nz)
    return 0 if l == 0 else nz/l

def volume(a,b,c):
    return (a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6.0

def mesh_from_tris(path, fmt, tris):
    if not tris: raise SystemExit('No triangles found in %s' % path)
    verts = [v for t in tris for v in t]
    xs, ys, zs = [v[0] for v in verts], [v[1] for v in verts], [v[2] for v in verts]
    mn, mx = (min(xs),min(ys),min(zs)), (max(xs),max(ys),max(zs))
    area = vol = over = sev = 0.0
    for t in tris:
        a = tri_area(*t); area += a; vol += volume(*t)
        nz = norm_z(*t)
        if nz < -0.35: over += a
        if nz < -0.70: sev += a
    return dict(path=str(path), format=fmt, vertices=len(verts), triangles=len(tris), bbox_min=mn, bbox_max=mx, dimensions_mm=(mx[0]-mn[0], mx[1]-mn[1], mx[2]-mn[2]), surface_area_mm2=round(area,3), volume_mm3=round(abs(vol),3), overhang_ratio=round(over/area,4) if area else None, severe_overhang_ratio=round(sev/area,4) if area else None)

def inspect_stl(path):
    data = path.read_bytes(); tris = []
    binary = len(data) >= 84 and 84 + struct.unpack('<I', data[80:84])[0] * 50 == len(data)
    if binary:
        n, off = struct.unpack('<I', data[80:84])[0], 84
        for _ in range(n):
            vals = struct.unpack('<12fH', data[off:off+50]); off += 50
            tris.append(((vals[3],vals[4],vals[5]), (vals[6],vals[7],vals[8]), (vals[9],vals[10],vals[11])))
    else:
        verts = []
        for line in data.decode('utf-8','ignore').splitlines():
            p = line.strip().split()
            if len(p) == 4 and p[0].lower() == 'vertex':
                verts.append((float(p[1]),float(p[2]),float(p[3])))
                if len(verts) == 3:
                    tris.append(tuple(verts)); verts = []
    return mesh_from_tris(path, 'stl', tris)

def inspect_obj(path):
    verts, faces = [], []
    for line in path.read_text(encoding='utf-8', errors='ignore').splitlines():
        if line.startswith('v '):
            _,x,y,z,*_ = line.split(); verts.append((float(x),float(y),float(z)))
        elif line.startswith('f '):
            ids = [int(tok.split('/')[0]) - 1 for tok in line.split()[1:] if tok.split('/')[0]]
            if len(ids) >= 3: faces.append(ids)
    tris = []
    for f in faces:
        for i in range(1, len(f)-1): tris.append((verts[f[0]], verts[f[i]], verts[f[i+1]]))
    return mesh_from_tris(path, 'obj', tris)

def inspect_3mf(path):
    unit = {'micron':0.001, 'millimeter':1, 'centimeter':10, 'inch':25.4, 'foot':304.8, 'meter':1000}
    with zipfile.ZipFile(path) as z:
        name = next((n for n in z.namelist() if n.lower().endswith('.model')), None)
        if not name: raise SystemExit('No .model XML in 3MF')
        root = ET.fromstring(z.read(name))
    ns = {'m': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
    scale = unit.get(root.attrib.get('unit','millimeter'), 1)
    objs = root.findall('.//m:object', ns) if ns else root.findall('.//object')
    tris = []
    for obj in objs:
        vertices = [(float(v.attrib['x'])*scale, float(v.attrib['y'])*scale, float(v.attrib['z'])*scale) for v in (obj.findall('.//m:vertex', ns) if ns else obj.findall('.//vertex'))]
        for t in (obj.findall('.//m:triangle', ns) if ns else obj.findall('.//triangle')):
            tris.append((vertices[int(t.attrib['v1'])], vertices[int(t.attrib['v2'])], vertices[int(t.attrib['v3'])]))
    return mesh_from_tris(path, '3mf', tris)

def inspect_model(path):
    s = path.suffix.lower()
    if s == '.stl': return inspect_stl(path)
    if s == '.obj': return inspect_obj(path)
    if s == '.3mf': return inspect_3mf(path)
    raise SystemExit('Unsupported model format %s; use STL/OBJ/3MF' % s)

def scale_for(info, a):
    x,y,z = info['dimensions_mm']; targets = []
    if a.scale: return float(a.scale), 'explicit scale=%s' % a.scale
    if a.height: targets.append(('z', z, float(a.height)))
    if a.width: targets.append(('x', x, float(a.width)))
    if a.length: targets.append(('y' if y >= x else 'x', max(x,y), float(a.length)))
    if not targets: return 1.0, 'original size'
    ratios = [t/cur for _,cur,t in targets if cur > 0]
    return min(ratios), ', '.join('%s->%gmm' % (axis,t) for axis,_,t in targets)

def split_plan(dims, printer):
    lim = printer['conservative_limits']
    axes = [('x',dims[0],lim['max_part_x_mm']), ('y',dims[1],lim['max_part_y_mm']), ('z',dims[2],lim['max_part_z_mm'])]
    over = [(a,s,l,math.ceil(s/l)) for a,s,l in axes if s > l]
    if not over: return dict(required=False, reason='fits conservative part limits')
    axis,size,limit,count = max(over, key=lambda r: r[3])
    aspect = max(dims) / max(1, min(d for d in dims if d > 0))
    conn = ['alignment pins 4-6 mm', 'flat keyed lap joint']
    if aspect >= 4 or size > limit * 3:
        conn = ['central rod/channel', 'M6/M8 threaded rod if thickness allows', 'anti-rotation keyed sleeves', 'numbered segments']
    return dict(required=True, axis=axis, dimension_mm=round(size,2), safe_segment_mm=limit, segments=count, connectors=conn)

def find_slicer():
    for n in ['prusa-slicer','PrusaSlicer','orca-slicer','OrcaSlicer','slic3r']:
        p = shutil.which(n)
        if p: return p
    return None

def slicer_center_args(slicer, bed):
    center = '%g,%g' % (bed['x']/2, bed['y']/2)
    name = Path(slicer).name.lower()
    if 'prusa' in name or 'orca' in name:
        return ['--center', center]
    return ['--print-center', center]

def slicer_failure_reason(output, returncode):
    for line in output.splitlines():
        line = line.strip()
        if line and not line.startswith('PrusaSlicer-') and not line.startswith('https://'):
            return line[:300]
    return 'returncode %s' % returncode

def has_printer_feature(printer, needle):
    needle = needle.lower()
    return any(needle in str(v).lower() for v in printer.get('klipper_features', []))

def nozzle_standby_temp(filament):
    if DEFAULT_NOZZLE_STANDBY:
        return float(DEFAULT_NOZZLE_STANDBY)
    return float(filament.get('standby_nozzle_c') or max(150, min(180, float(filament['first_layer_nozzle_c']) - 50)))

def format_temp(value):
    return '%g' % float(value)

def build_nozzle_check_gcode(printer, standby_temp, nozzle_check):
    if nozzle_check == 'off':
        return []
    start = printer.get('print_start', {})
    x = float(start.get('nozzle_check_x_mm', 10))
    y = float(start.get('nozzle_check_y_mm', 10))
    z = float(start.get('nozzle_check_z_mm', 20))
    pause_command = start.get('nozzle_check_pause_command', 'PAUSE')
    lines = [
        '; AI NOZZLE CHECK: clean ooze before bed mesh',
        'G1 Z%.2f F3000' % z,
        'G1 X%.2f Y%.2f F6000' % (x, y),
        'M109 S%s' % format_temp(standby_temp),
        'M117 Clean nozzle and bed, then RESUME',
        'RESPOND TYPE=command MSG="Clean nozzle ooze and bed blob, then press RESUME"',
    ]
    if pause_command:
        lines.append(str(pause_command))
    lines += [
        'G90',
        'M82',
        '; AI NOZZLE CHECK END',
    ]
    return lines

def build_start_gcode(printer, filament, calibration, nozzle_check):
    standby_temp = nozzle_standby_temp(filament)
    bed_temp = filament.get('first_layer_bed_c', filament['bed_c'])
    lines = [
        '; AI START: 3d-print-inbox',
        'M140 S%s' % format_temp(bed_temp),
        'M104 S%s' % format_temp(standby_temp),
        'M190 S%s' % format_temp(bed_temp),
        'G90',
        'M82',
        'G28',
    ]
    lines += build_nozzle_check_gcode(printer, standby_temp, nozzle_check)
    if calibration != 'off':
        if has_printer_feature(printer, 'z_tilt'):
            lines += ['Z_TILT_ADJUST', 'G28 Z']
        if has_printer_feature(printer, 'bed_mesh'):
            lines += ['BED_MESH_CALIBRATE']
    lines += [
        'M109 S%s' % format_temp(filament['first_layer_nozzle_c']),
        'G92 E0',
        'G1 Z5 F3000',
        'G1 X5 Y10 F6000',
        'G1 Z0.28 F600',
        'G1 X200 E18 F900',
        'G1 Y12 F6000',
        'G1 X5 E18 F900',
        'G92 E0',
        'G1 Z2 F3000',
        '; AI START END',
    ]
    return '\n'.join(lines)

def present_z_for(printer, dims, override=None):
    axis = printer.get('firmware_axis_mm', {})
    z_max = float(axis.get('z_max') or printer.get('build_volume_mm', {}).get('z') or 250)
    clearance = float(printer.get('conservative_limits', {}).get('clearance_mm', 5))
    profile_present = printer.get('print_end', {}).get('present_z_mm')
    desired = float(override if override is not None else DEFAULT_PRESENT_Z if DEFAULT_PRESENT_Z else profile_present if profile_present is not None else z_max - 25)
    return round(min(z_max - clearance, max(float(dims[2]) + 10, desired)), 2)

def build_end_gcode(printer, dims, present_z):
    park = printer.get('print_end', {})
    park_x = float(park.get('park_x_mm', 10))
    park_y = float(park.get('park_y_mm', printer.get('build_volume_mm', {}).get('y', 220)))
    return '\n'.join([
        '; AI END: 3d-print-inbox',
        'M400',
        'G92 E0',
        'G1 E-1 F1800',
        'M104 S0',
        'M140 S0',
        'M106 S0',
        'G90',
        'G1 Z%.2f F600' % present_z,
        'G1 X%.2f Y%.2f F6000' % (park_x, park_y),
        'M84 X Y E',
        '; AI END END',
    ])

def calibration_summary(printer, calibration):
    if calibration == 'off':
        return 'off'
    steps = ['G28']
    if has_printer_feature(printer, 'z_tilt'):
        steps += ['Z_TILT_ADJUST', 'G28 Z']
    if has_printer_feature(printer, 'bed_mesh'):
        steps.append('BED_MESH_CALIBRATE')
    return 'auto (' + ', '.join(steps) + ')'

def nozzle_check_summary(nozzle_check, filament):
    if nozzle_check == 'off':
        return 'off'
    return 'manual pause before mesh at %s C standby' % format_temp(nozzle_standby_temp(filament))

def run_slicer(model, gcode, scale, printer, filament, mode, supports, start_gcode, end_gcode):
    slicer = find_slicer()
    if not slicer: return dict(ok=False, ran=False, reason='No CLI slicer found')
    bed = printer['build_volume_mm']
    cmd = [slicer, '--export-gcode', '--output', str(gcode), '--layer-height', str(mode['layer']), '--first-layer-height', str(mode['first_layer']), '--perimeters', str(mode['walls']), '--top-solid-layers', str(mode['top']), '--bottom-solid-layers', str(mode['bottom']), '--fill-density', str(mode['infill'])+'%', '--fill-pattern', mode['pattern'], '--temperature', str(filament['nozzle_c']), '--first-layer-temperature', str(filament['first_layer_nozzle_c']), '--bed-temperature', str(filament['bed_c']), '--first-layer-bed-temperature', str(filament['first_layer_bed_c']), '--filament-diameter', str(printer['filament']['diameter_mm']), '--nozzle-diameter', str(printer['nozzle']['diameter_mm']), '--brim-width', str(filament.get('brim_mm',0)), '--start-gcode', start_gcode, '--end-gcode', end_gcode] + slicer_center_args(slicer, bed) + ['--gcode-flavor', 'klipper']
    if abs(scale - 1.0) > 0.0001: cmd += ['--scale', '%g' % scale]
    if supports: cmd += ['--support-material', '--support-material-auto', '--support-material-threshold', str(mode['support_angle'])]
    cmd.append(str(model))
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1800)
    ok = p.returncode == 0 and gcode.exists()
    res = dict(ok=ok, ran=True, returncode=p.returncode, slicer=slicer, command=cmd, output_tail=p.stdout[-3000:], gcode=str(gcode) if gcode.exists() else None)
    if not ok:
        res['reason'] = slicer_failure_reason(p.stdout, p.returncode)
    return res

def create_job_dir(model):
    stem = ''.join(c if c.isalnum() or c in '._-' else '_' for c in model.stem)[:80]
    base = time.strftime('%Y%m%d-%H%M%S_') + stem
    for i in range(1000):
        name = base if i == 0 else '%s_%03d' % (base, i + 1)
        job = JOBS / name
        try:
            job.mkdir(parents=True, exist_ok=False)
            return job
        except FileExistsError:
            continue
    raise SystemExit('Could not create unique job directory for ' + model.name)

def inspect_cmd(a):
    model = resolve_model(a.model); info = inspect_model(model); scale, why = scale_for(info, a)
    dims = tuple(v*scale for v in info['dimensions_mm']); printer = printer_profile(a.printer)
    print(json.dumps(dict(info, scale=scale, scale_reason=why, scaled_dimensions_mm=dims, split=split_plan(dims, printer)), ensure_ascii=False, indent=2))

def prepare(a):
    model = resolve_model(a.model); printer = printer_profile(a.printer); filament = filament_profile(a.filament); mode = MODES[a.mode]
    info = inspect_model(model); scale, why = scale_for(info, a); dims = tuple(v*scale for v in info['dimensions_mm'])
    supports = (info.get('severe_overhang_ratio') or 0) > 0.04 or (info.get('overhang_ratio') or 0) > 0.12
    if a.supports == 'on': supports = True
    if a.supports == 'off': supports = False
    split = split_plan(dims, printer)
    job = create_job_dir(model); copied = job / model.name; shutil.copy2(model, copied)
    gcode = job / ('%s_%s_%s.gcode' % (model.stem, a.mode, filament['id']))
    present_z = present_z_for(printer, dims, a.present_z)
    start_gcode = build_start_gcode(printer, filament, a.calibration, a.nozzle_check)
    end_gcode = build_end_gcode(printer, dims, present_z)
    sres = dict(ok=False, ran=False, reason='split_required') if split.get('required') else (dict(ok=False, ran=False, reason='skipped') if a.no_slice else run_slicer(copied, gcode, scale, printer, filament, mode, supports, start_gcode, end_gcode))
    meta = dict(job_dir=str(job), source_model=str(model), copied_model=str(copied), mesh=info, scale=scale, scale_reason=why, scaled_dimensions_mm=dims, printer=printer, filament=filament, mode=a.mode, settings=mode, supports=supports, calibration=a.calibration, calibration_summary=calibration_summary(printer, a.calibration), nozzle_check=a.nozzle_check, nozzle_check_summary=nozzle_check_summary(a.nozzle_check, filament), present_z_mm=present_z, start_gcode=start_gcode, end_gcode=end_gcode, split=split, slicer_result=sres, moonraker_url=MOONRAKER_URL)
    (job/'metadata.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    plan = ['# Print Plan', '', '- Model: %s' % copied, '- Printer: %s' % printer['name'], '- Mode: %s (%s)' % (a.mode, mode['label']), '- Filament: %s' % filament['id'], '- Original XYZ: %.2f x %.2f x %.2f mm' % tuple(info['dimensions_mm']), '- Final XYZ: %.2f x %.2f x %.2f mm' % dims, '- Scale: %.5g (%s)' % (scale, why), '- Supports: %s' % ('yes' if supports else 'no'), '- Brim: %s mm' % filament.get('brim_mm',0), '- Nozzle/bed: %s/%s C' % (filament['nozzle_c'], filament['bed_c']), '- Walls: %s, infill: %s%% %s, layer: %s mm' % (mode['walls'], mode['infill'], mode['pattern'], mode['layer']), '- Nozzle check: %s' % nozzle_check_summary(a.nozzle_check, filament), '- Pre-print calibration: %s' % calibration_summary(printer, a.calibration), '- End presentation: bed down / Z %.2f mm' % present_z, '']
    if split.get('required'): plan += ['## Split required', '- Axis: %s' % split['axis'], '- Segments: %s' % split['segments'], '- Connectors: %s' % ', '.join(split['connectors']), '']
    plan += ['## Slicer', json.dumps(sres, ensure_ascii=False, indent=2)]
    (job/'print_plan.md').write_text('\n'.join(plan) + '\n', encoding='utf-8')
    print('Job:', job); print('Plan:', job/'print_plan.md'); print('Metadata:', job/'metadata.json')
    if sres.get('ok'):
        print('G-code:', sres['gcode'])
        if a.upload or a.start: print(json.dumps(upload_file(Path(sres['gcode']), a.start), ensure_ascii=False, indent=2))
    else:
        print('Slicer not completed:', sres.get('reason') or sres.get('returncode'))

def gcode_markers(path):
    found = {'ai_start': False, 'ai_end': False}
    with Path(path).open('r', encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            if 'AI START: 3d-print-inbox' in line:
                found['ai_start'] = True
            if 'AI END: 3d-print-inbox' in line:
                found['ai_end'] = True
            if found['ai_start'] and found['ai_end']:
                break
    return found

def upload_file(path, start=False, allow_untagged_start=False):
    if requests is None: raise SystemExit('python requests is required for upload')
    markers = gcode_markers(path)
    if start and not allow_untagged_start and not (markers['ai_start'] and markers['ai_end']):
        raise SystemExit('Refusing to start G-code without 3d-print-inbox AI START/AI END markers; prepare it with bin/print-helper or pass --allow-untagged-start')
    with Path(path).open('rb') as fh:
        r = requests.post(MOONRAKER_URL + '/server/files/upload', files={'file': (Path(path).name, fh, 'application/octet-stream')}, data={'root':'gcodes','path':'ai_jobs','print':'true' if start else 'false'}, timeout=60)
    try: body = r.json()
    except Exception: body = {'text': r.text}
    if not r.ok: raise SystemExit('Upload failed HTTP %s: %s' % (r.status_code, body))
    return dict(uploaded=True, start=start, markers=markers, response=body)

def upload(a): print(json.dumps(upload_file(Path(a.gcode).resolve(), a.start, a.allow_untagged_start), ensure_ascii=False, indent=2))
def start(a):
    if not a.allow_direct_start:
        raise SystemExit('Direct start bypasses local G-code preflight; use upload --start with a prepared G-code file or pass --allow-direct-start')
    print(json.dumps(http_json('/printer/print/start', 'POST', {'filename': a.filename}), ensure_ascii=False, indent=2))
def pause(_a): print(json.dumps(http_json('/printer/print/pause', 'POST', {}), ensure_ascii=False, indent=2))
def resume(_a): print(json.dumps(http_json('/printer/print/resume', 'POST', {}), ensure_ascii=False, indent=2))
def cancel(_a): print(json.dumps(http_json('/printer/print/cancel', 'POST', {}), ensure_ascii=False, indent=2))
def monitor(a):
    while True:
        st = http_json('/printer/objects/query?extruder&heater_bed&print_stats&virtual_sdcard').get('result',{}).get('status',{})
        ps, vs, ex, bed = st.get('print_stats',{}), st.get('virtual_sdcard',{}), st.get('extruder',{}), st.get('heater_bed',{})
        print('%s state=%s file=%r progress=%.1f%% nozzle=%s/%s bed=%s/%s' % (time.strftime('%H:%M:%S'), ps.get('state'), ps.get('filename'), 100*(vs.get('progress') or 0), ex.get('temperature'), ex.get('target'), bed.get('temperature'), bed.get('target')))
        if a.once: break
        time.sleep(a.interval)
def list_filaments(_a):
    for f in filaments(): print('%s: nozzle=%s bed=%s fan=%s brim=%s' % (f['id'], f['nozzle_c'], f['bed_c'], f['fan_percent'], f.get('brim_mm',0)))
def modes(_a):
    for k,v in MODES.items(): print('%s: %s layer=%s walls=%s infill=%s%%' % (k, v['label'], v['layer'], v['walls'], v['infill']))
def init_dirs(_a):
    for d in [INBOX,JOBS]: d.mkdir(parents=True, exist_ok=True); print('OK', d)

def parser():
    p = argparse.ArgumentParser(description='3D print helper for Flying Bear S1')
    p.add_argument('--moonraker', default=MOONRAKER_URL)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status').set_defaults(func=status)
    q = sub.add_parser('sync-printer-profile'); q.add_argument('--printer', default=DEFAULT_PRINTER); q.set_defaults(func=sync_printer)
    for name in ['inspect','prepare']:
        q = sub.add_parser(name); q.add_argument('model'); q.add_argument('--printer', default=DEFAULT_PRINTER); q.add_argument('--height', type=float); q.add_argument('--width', type=float); q.add_argument('--length', type=float); q.add_argument('--scale', type=float)
        if name == 'prepare':
            q.add_argument('--filament', default=DEFAULT_FILAMENT); q.add_argument('--mode', choices=sorted(MODES), default=DEFAULT_MODE); q.add_argument('--supports', choices=['auto','on','off'], default='auto'); q.add_argument('--calibration', choices=['auto','off'], default=DEFAULT_CALIBRATION); q.add_argument('--nozzle-check', choices=['manual','off'], default=DEFAULT_NOZZLE_CHECK); q.add_argument('--present-z', type=float); q.add_argument('--no-slice', action='store_true'); q.add_argument('--upload', action='store_true'); q.add_argument('--start', action='store_true'); q.set_defaults(func=prepare)
        else: q.set_defaults(func=inspect_cmd)
    q = sub.add_parser('upload'); q.add_argument('gcode'); q.add_argument('--start', action='store_true'); q.add_argument('--allow-untagged-start', action='store_true'); q.set_defaults(func=upload)
    q = sub.add_parser('start'); q.add_argument('filename'); q.add_argument('--allow-direct-start', action='store_true'); q.set_defaults(func=start)
    sub.add_parser('pause').set_defaults(func=pause); sub.add_parser('resume').set_defaults(func=resume); sub.add_parser('cancel').set_defaults(func=cancel)
    q = sub.add_parser('monitor'); q.add_argument('--once', action='store_true'); q.add_argument('--interval', type=float, default=10); q.set_defaults(func=monitor)
    sub.add_parser('filaments').set_defaults(func=list_filaments); sub.add_parser('modes').set_defaults(func=modes); sub.add_parser('init-dirs').set_defaults(func=init_dirs)
    return p

def main():
    global MOONRAKER_URL
    p = parser(); a = p.parse_args(); MOONRAKER_URL = a.moonraker.rstrip('/'); a.func(a)
if __name__ == '__main__': main()
