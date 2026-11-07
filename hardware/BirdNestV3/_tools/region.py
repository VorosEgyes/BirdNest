#!/usr/bin/env python3
"""Print V2 part bounding boxes, filtered by a region, for placement planning.

usage: region.py <x0> <y0> <x1> <y1>
"""
import pcbnew
import sys

v2 = pcbnew.LoadBoard("BirdNest_pcb/BirdNest_pcb.kicad_pcb")
x0, y0, x1, y1 = (float(v) for v in sys.argv[1:5])

print(f"=== V2 parts intersecting x {x0}..{x1}  y {y0}..{y1} ===")
for fp in sorted(v2.GetFootprints(), key=lambda f: f.GetReference()):
    if not fp.GetReference():
        continue
    bb = fp.GetBoundingBox(False, False)
    a, b = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetRight())
    c, d = pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetBottom())
    if b > x0 and a < x1 and d > y0 and c < y1:
        p = fp.GetPosition()
        print(f"  {fp.GetReference():6} {fp.GetValue():16} pos({pcbnew.ToMM(p.x):7.2f},{pcbnew.ToMM(p.y):7.2f}) "
              f"X {a:7.2f}..{b:7.2f}  Y {c:7.2f}..{d:7.2f}")

print()
print("=== all V2 parts (full list) ===")
for fp in sorted(v2.GetFootprints(), key=lambda f: f.GetReference()):
    if not fp.GetReference():
        continue
    bb = fp.GetBoundingBox(False, False)
    p = fp.GetPosition()
    print(f"  {fp.GetReference():6} X {pcbnew.ToMM(bb.GetLeft()):7.2f}..{pcbnew.ToMM(bb.GetRight()):7.2f}"
          f"  Y {pcbnew.ToMM(bb.GetTop()):7.2f}..{pcbnew.ToMM(bb.GetBottom()):7.2f}")
