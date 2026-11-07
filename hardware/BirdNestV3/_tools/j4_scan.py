#!/usr/bin/env python3
"""Teljes feltérképezés a J4 környezetében: minden pad, track, zóna-szegély, silk és szöveg.
Cél: szabad helyet találni a D9 TVS számára a J4 mellett, DRC-ütközés nélkül."""
import re, math, sys

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
X0, X1 = 178.0, 200.5
Y0, Y1 = 96.0, 128.0

pt = open(PCB).read()

def num(s):
    try: return float(s)
    except: return None

def inb(x, y):
    return X0 <= x <= X1 and Y0 <= y <= Y1

print("=" * 78)
print(f"J4 KORNYEZET: x {X0}..{X1}, y {Y0}..{Y1}")
print("=" * 78)

# --- footprint-ek -----------------------------------------------
print("\n--- FOOTPRINT-ek (pad-ek, udvar) ---")
fp_re = re.compile(r'\n\t\(footprint "([^"]*)"(.*?)\n\t\)\n', re.S)
for m in fp_re.finditer(pt):
    name = m.group(1)
    body = m.group(2)
    ref = re.search(r'\(property "Reference" "([^"]*)"', body)
    ref = ref.group(1) if ref else '?'
    at = re.search(r'\n\t\t\(at ([-\d\.]+) ([-\d\.]+) ([-\d\.]+)\)', body)
    if not at: continue
    ox, oy, rot = float(at.group(1)), float(at.group(2)), float(at.group(3))
    pads = []
    for pm in re.finditer(r'\(pad "([^"]*)" (\w+) (\w+)\s*\(at ([-\d\.]+) ([-\d\.]+)[^)]*\)', body):
        ps = re.search(r'\(size ([-\d\.]+) ([-\d\.]+)\)', pm.group(0))
        pads.append((pm.group(1), pm.group(2), float(pm.group(4)), float(pm.group(5)),
                     float(ps.group(1)) if ps else 0, float(ps.group(2)) if ps else 0))
    # global pad poz (rot 0/90/180/270)
    def gpos(lx, ly):
        if rot == 90:   return (ox - ly, oy + lx)
        if rot == 180:  return (ox - lx, oy - ly)
        if rot == 270:  return (ox + ly, oy - lx)
        return (ox + lx, oy + ly)
    gp = []
    for (pn, ptype, lx, ly, sx, sy) in pads:
        gx, gy = gpos(lx, ly)
        gp.append((pn, ptype, gx, gy, sx, sy))
    hit = [p for p in gp if inb(p[2], p[3])]
    # udvar
    cy = None
    cr = re.search(r'\(fp_rect\s*\(start ([-\d\.]+) ([-\d\.]+)\)\s*\(end ([-\d\.]+) ([-\d\.]+)\)', body)
    if cr:
        lx1, ly1, lx2, ly2 = (float(cr.group(i)) for i in (1,2,3,4))
        a = gpos(lx1, ly1); b = gpos(lx2, ly2)
        cy = (min(a[0],b[0]), min(a[1],b[1]), max(a[0],b[0]), max(a[1],b[1]))
    if hit or (cy and not (cy[2] < X0 or cy[0] > X1 or cy[3] < Y0 or cy[1] > Y1)):
        print(f"\n  {ref:8s} {name}")
        print(f"      orig=({ox},{oy}) rot={rot:.0f}")
        if cy: print(f"      udvar global: x {cy[0]:.3f}..{cy[2]:.3f}  y {cy[1]:.3f}..{cy[3]:.3f}")
        for (pn, ptype, gx, gy, sx, sy) in hit:
            print(f"      pad{pn} {ptype:8s} ({gx:.3f},{gy:.3f}) size {sx}x{sy}")

# --- track-ek ---------------------------------------------------
print("\n--- TRACK-ek (F.Cu / B.Cu) ---")
for m in re.finditer(r'\n\t\(segment\s*\(start ([-\d\.]+) ([-\d\.]+)\)\s*\(end ([-\d\.]+) ([-\d\.]+)\)\s*\(width ([-\d\.]+)\)\s*\(layer "([^"]*)"\)', pt):
    x1, y1, x2, y2, w = (float(m.group(i)) for i in (1,2,3,4,5))
    lay = m.group(6)
    if inb(x1, y1) or inb(x2, y2):
        print(f"  {lay:8s} ({x1:8.3f},{y1:8.3f}) -> ({x2:8.3f},{y2:8.3f})  w={w}")

# --- zóna-elpolás ----------------------------------------------
print("\n--- ZONA-elpolás pontok a teruleten ---")
for m in re.finditer(r'\n\t\(zone\s*\(net (\d+)\)\s*\(net_name "([^"]*)"\)(.*?)\n\t\)\n', pt, re.S):
    net, nn, body = m.group(1), m.group(2), m.group(3)
    lay = re.search(r'\(layer "([^"]*)"\)', body)
    lay = lay.group(1) if lay else '?'
    pts = [(float(a), float(b)) for a, b in re.findall(r'\(xy ([-\d\.]+) ([-\d\.]+)\)', body)]
    inside = [p for p in pts if inb(*p)]
    if inside:
        allx = [p[0] for p in pts]; ally = [p[1] for p in pts]
        print(f"  net {net} '{nn}' layer {lay}: {len(pts)} pont, bbox x {min(allx):.2f}..{max(allx):.2f} y {min(ally):.2f}..{max(ally):.2f}")
        print(f"     pontok a teruleten: {[(round(p[0],2),round(p[1],2)) for p in inside][:20]}")

# --- gr_text (PCB szintu feliratok) -----------------------------
print("\n--- PCB-szintu SZO-VEG (gr_text) ---")
for m in re.finditer(r'\n\t\(gr_text "([^"]*)"\s*\n\s*\(at ([-\d\.]+) ([-\d\.]+) ([-\d\.]+)\)\s*\n\s*\(layer "([^"]*)"\)', pt):
    t, x, y, a, lay = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4)), m.group(5)
    if inb(x, y):
        print(f"  '{t}' at ({x:.3f},{y:.3f}) angle={a:.0f} layer={lay}")
