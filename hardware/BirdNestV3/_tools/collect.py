#!/usr/bin/env python3
"""A szerkesztéshez szukseges pontos adatok kiirasa fajlokba."""
import json
import os
import re
import subprocess

D = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3'
OUT = '/tmp/d9data'
os.makedirs(OUT, exist_ok=True)


def w(name, text):
    p = os.path.join(OUT, name)
    open(p, 'w').write(text)
    print(f'  -> {p} ({len(text)} bajt)')


# ---------------------------------------------------------------- PCB
pcb = open(f'{D}/BirdNestV3.kicad_pcb').read()

for ref in ('D9', 'D10', 'J4', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5',
            'H1', 'H5', 'H6'):
    i = pcb.find(f'(property "Reference" "{ref}"')
    st = pcb.rfind('\n\t(footprint ', 0, i)
    d = 0
    k = pcb.index('(', st)
    while True:
        if pcb[k] == '(':
            d += 1
        elif pcb[k] == ')':
            d -= 1
            if d == 0:
                break
        k += 1
    w(f'pcb_{ref}.txt', pcb[st:k + 1])

# a Net-(D10-A) es GND nyomok
for net in ('Net-(D10-A)', 'GND', '/VIN_PROT'):
    segs = []
    for m in re.finditer(r'\n\t\(segment\n(?:\t\t[^\n]*\n)*?\t\)\n', pcb):
        if f'(net "{net}")' in m.group(0):
            s = re.search(r'\(start ([-\d\.]+) ([-\d\.]+)\)', m.group(0))
            e = re.search(r'\(end ([-\d\.]+) ([-\d\.]+)\)', m.group(0))
            l = re.search(r'\(layer "([^"]*)"\)', m.group(0))
            wd = re.search(r'\(width ([\d\.]+)\)', m.group(0))
            segs.append(f'{s.group(1)},{s.group(2)} -> {e.group(1)},{e.group(2)}'
                        f'  {l.group(1)} w={wd.group(1)}')
    w(f'pcb_net_{net.replace("/", "")}.txt', '\n'.join(segs))

# via-k
vias = []
for m in re.finditer(r'\n\t\(via\n(?:\t\t[^\n]*\n)*?\t\)\n', pcb):
    s = re.search(r'\(at ([-\d\.]+) ([-\d\.]+)\)', m.group(0))
    n = re.search(r'\(net "([^"]*)"\)', m.group(0))
    sz = re.search(r'\(size ([\d\.]+)\)', m.group(0))
    dr = re.search(r'\(drill ([\d\.]+)\)', m.group(0))
    vias.append(f'{s.group(1)},{s.group(2)} net={n.group(1)} '
                f'size={sz.group(1)} drill={dr.group(1)}')
w('pcb_vias.txt', '\n'.join(vias))

# ---------------------------------------------------------- SCHEMATIC
sch = open(f'{D}/BirdNestV3.kicad_sch').read()

# a symbol instance-ek (top-level, indent 4)
inst = []
for m in re.finditer(r'\n\t\(symbol\n(?:\t\t[^\n]*\n|\t\t\t[^\n]*\n)*?\t\)\n',
                     sch):
    blk = m.group(0)
    if '(lib_id "' not in blk or '(in_bom' not in blk:
        continue
    lib = re.search(r'\(lib_id "([^"]*)"\)', blk)
    ref = re.search(r'\(property "Reference" "([^"]*)"', blk)
    val = re.search(r'\(property "Value" "([^"]*)"', blk)
    des = re.search(r'\(property "Description" "([^"]*)"', blk)
    fp = re.search(r'\(property "Footprint" "([^"]*)"', blk)
    at = re.search(r'\n\t\t\(at ([-\d\.]+) ([-\d\.]+) ([-\d\.]+)\)', blk)
    inst.append(
        f'{ref.group(1) if ref else "?":6} lib={lib.group(1) if lib else "?":35} '
        f'val={val.group(1) if val else "":16} '
        f'fp={fp.group(1) if fp else "":32} '
        f'descr={des.group(1) if des else ""} '
        f'at={at.group(1) if at else "?"},{at.group(2) if at else "?"}')
w('sch_instances.txt', '\n'.join(sorted(inst)))

# a D9 symbol teljes blokkja
i = sch.find('(property "Reference" "D9"')
st = sch.rfind('\n\t(symbol\n', 0, i)
d = 0
k = sch.index('(', st)
while True:
    if sch[k] == '(':
        d += 1
    elif sch[k] == ')':
        d -= 1
        if d == 0:
            break
    k += 1
w('sch_D9.txt', sch[st:k + 1])

# a lib_symbols cache blokkok a D9 es a TP-k symboljaihoz
names = set()
for m in re.finditer(r'\n\t\(symbol "([^"]*)"', sch):
    names.add(m.group(1))
w('sch_libsymbol_names.txt', '\n'.join(sorted(names)))

for want in ('Diode:SMAJ90CA', 'Diode:SMAJ6.0CA'):
    m = re.search(r'\n\t\(symbol "' + re.escape(want) + r'"[\s\S]*?\n\t\)\n',
                  sch)
    if m:
        w(f'sch_lib_{want.replace(":", "_")}.txt', m.group(0))
    else:
        w(f'sch_lib_{want.replace(":", "_")}.txt', 'NINCS a cache-ben')

# ---------------------------------------------------------- LIBRARY
libs = subprocess.run(
    ['grep', '-n', '-A', '60', 'SMAJ6.0CA',
     '/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/Diode.kicad_sym'],
    capture_output=True, text=True).stdout
w('lib_SMAJ6.0CA.txt', libs)

libs = subprocess.run(
    ['grep', '-n', '-A', '60', 'SMAJ90CA',
     '/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/Diode.kicad_sym'],
    capture_output=True, text=True).stdout
w('lib_SMAJ90CA.txt', libs)

print('kesz')
