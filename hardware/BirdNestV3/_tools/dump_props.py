#!/usr/bin/env python3
"""Read-only: kiirja a TP1..TP5, H1..H6, D9 tulajdonsagait a schematicban
es a PCB-n, plusz a GND-net copper adatait."""
import re
import sys

BASE = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3'
SCH = BASE + '/BirdNestV3.kicad_sch'
PCB = BASE + '/BirdNestV3.kicad_pcb'


def blocks(text, opener):
    """Visszaadja az osszes 'opener' blokkot a zarolajel-merlegeles alapjan."""
    out = []
    i = 0
    while True:
        i = text.find(opener, i)
        if i < 0:
            break
        d = 0
        j = i
        in_str = False
        while True:
            c = text[j]
            if in_str:
                if c == '\\':
                    j += 1
                elif c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d == 0:
                    break
            j += 1
        out.append((i, text[i:j + 1]))
        i = j + 1
    return out


def props(blk):
    """{nev: ertek} a '(property "N" "V" ...)' blokkokbol."""
    d = {}
    for m in re.finditer(r'\(property\s+"([^"]*)"\s+"([^"]*)"', blk):
        d[m.group(1)] = m.group(2)
    return d


def prop_layer(blk, name):
    m = re.search(r'\(property\s+"' + re.escape(name) +
                  r'"\s+"[^"]*"(.*?)\n\t\t\)', blk, re.S)
    if not m:
        return None
    lm = re.search(r'\(layer\s+"([^"]*)"\)', m.group(1))
    return lm.group(1) if lm else None


REFS = ['TP1', 'TP2', 'TP3', 'TP4', 'TP5',
        'H1', 'H2', 'H3', 'H4', 'H5', 'H6', 'D9']

print('=' * 72)
print('SCHEMATIC')
print('=' * 72)
s = open(SCH).read()
for off, blk in blocks(s, '\n\t(symbol\n'):
    pr = props(blk)
    ref = pr.get('Reference')
    if ref not in REFS:
        continue
    lid = re.search(r'\(lib_id\s+"([^"]*)"\)', blk)
    print(f'  {ref:5s} lib_id={lid.group(1) if lid else "?"}')
    for k in ('Value', 'Footprint', 'Description', 'Datasheet'):
        v = pr.get(k)
        if v is not None:
            print(f'          {k:12s} = {v!r}')

print()
print('=' * 72)
print('PCB')
print('=' * 72)
p = open(PCB).read()
for off, blk in blocks(p, '\n\t(footprint\n'):
    pr = props(blk)
    ref = pr.get('Reference')
    if ref not in REFS:
        continue
    fid = re.search(r'\(footprint\s+"([^"]*)"', blk)
    at = re.search(r'\n\t\t\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)', blk)
    print(f'  {ref:5s} fp={fid.group(1) if fid else "?"} '
          f'at=({at.group(1)},{at.group(2)},{at.group(3) or 0})')
    for k in ('Value', 'Description', 'Datasheet'):
        v = pr.get(k)
        if v is not None:
            print(f'          {k:12s} = {v!r}  layer={prop_layer(blk, k)}')
