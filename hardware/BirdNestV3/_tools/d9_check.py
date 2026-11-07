#!/usr/bin/env python3
"""A D9 TVS, a D10 Schottky és a J4 panel-csatlakozó elhelyezésének és
routingjának vizsgálata: mennyire van a TVS a csatlakozóhoz közel, és
meddig fut a földi visszavezetés."""
import math

import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'


def mm(v):
    return pcbnew.ToMM(v)


b = pcbnew.LoadBoard(PCB)
fps = list(b.GetFootprints())


def at(ref):
    fp = b.FindFootprintByReference(ref)
    p = fp.GetPosition()
    return mm(p.x), mm(p.y), fp.GetOrientationDegrees()


print("=== a panel bemeneti ag elhelyezkedese ===")
for ref in ('J4', 'D10', 'D9'):
    x, y, r = at(ref)
    print(f"  {ref:4s} ({x:8.3f}, {y:8.3f})  rot {r}")

jx, jy, _ = at('J4')
dx9, dy9, _ = at('D9')
d10x, d10y, _ = at('D10')
print(f"\n  J4 -> D9  tavez: {math.hypot(dx9 - jx, dy9 - jy):.2f} mm")
print(f"  J4 -> D10 tavez: {math.hypot(d10x - jx, d10y - jy):.2f} mm")
print(f"  D10 -> D9 tavez: {math.hypot(dx9 - d10x, dy9 - d10y):.2f} mm")

print("\n=== a Net-(D10-A) nyomkovetese (J4.1, D10.2, D9.2) ===")
segs = []
for t in b.GetTracks():
    if t.GetNetname() != 'Net-(D10-A)':
        continue
    s, e = t.GetStart(), t.GetEnd()
    segs.append((mm(s.x), mm(s.y), mm(e.x), mm(e.y), t.GetLayerName(),
                 t.GetWidth() if hasattr(t, 'GetWidth') else 0))
for s in segs:
    print(f"  {s[4]:6s} ({s[0]:8.3f},{s[1]:8.3f})->({s[2]:8.3f},{s[3]:8.3f}) "
          f"szelesseg {mm(s[5]):.3f}")
total = sum(math.hypot(s[2] - s[0], s[3] - s[1]) for s in segs)
print(f"  oszes hossz: {total:.2f} mm, szakaszok: {len(segs)}")

print("\n=== a D9 GND-labjanak nyomkovetese (melyik GND track-et erinti) ===")
d9 = b.FindFootprintByReference('D9')
for p in d9.Pads():
    pp = p.GetPosition()
    print(f"  D9 pad {p.GetNumber()} at ({mm(pp.x):.3f},{mm(pp.y):.3f}) net={p.GetNetname()}")
    near = []
    for t in b.GetTracks():
        if t.GetNetname() != 'GND':
            continue
        s, e = t.GetStart(), t.GetEnd()
        x1, y1, x2, y2 = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
        # a pont szakasz-vonalhoz meretes tavez
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 == 0:
            continue
        tpar = ((pp.x - x1) * dx + (pp.y - y1) * dy) / L2
        tpar = max(0.0, min(1.0, tpar))
        px, py = x1 + tpar * dx, y1 + tpar * dy
        dist = math.hypot(pp.x - px, pp.y - py)
        if dist < 1.2:
            near.append((dist, t.GetLayerName(), x1, y1, x2, y2))
    for dist, lay, x1, y1, x2, y2 in sorted(near)[:4]:
        print(f"     GND {lay:6s} ({x1:8.3f},{y1:8.3f})->({x2:8.3f},{y2:8.3f}) "
              f"tavez a padtol {dist:.3f} mm")
