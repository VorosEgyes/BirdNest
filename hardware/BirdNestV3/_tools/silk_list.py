#!/usr/bin/env python3
"""List the silkscreen of the board: the reference fields and the drawings.

Usage:  silk_list.py [layer]
"""
import sys
import pcbnew

b = pcbnew.LoadBoard('../BirdNestV3.kicad_pcb')
mm = pcbnew.ToMM
lay = sys.argv[1] if len(sys.argv) > 1 else 'F.Silkscreen'

print(f"=== reference fields on {lay} ===")
rows = []
for f in b.GetFootprints():
    r = f.Reference()
    if r.GetLayerName() != lay:
        continue
    pos = r.GetPosition()
    bb = r.GetBoundingBox()
    rows.append((f.GetReference(), mm(pos.x), mm(pos.y),
                 r.GetTextWidth() if hasattr(r, 'GetTextWidth') else 0,
                 r.GetTextHeight(), r.GetTextAngle().AsDegrees(), r.IsVisible(),
                 mm(bb.GetLeft()), mm(bb.GetTop()),
                 mm(bb.GetRight()), mm(bb.GetBottom())))
for r in sorted(rows):
    print(f"  {r[0]:6s} pos=({r[1]:8.3f},{r[2]:8.3f}) size={r[3]:.3f}x{r[4]:.3f}"
          f" ang={r[5]:.1f} vis={r[6]} bbox=({r[7]:.3f}..{r[9]:.3f}, {r[8]:.3f}..{r[10]:.3f})")

print(f"=== drawings of the board on {lay} (no footprint) ===")
for d in b.GetDrawings():
    if d.GetLayerName() != lay:
        continue
    bb = d.GetBoundingBox()
    print(f"  {d.GetClass():14s} bbox=({mm(bb.GetLeft()):8.3f}..{mm(bb.GetRight()):8.3f},"
          f" {mm(bb.GetTop()):8.3f}..{mm(bb.GetBottom()):8.3f})")
    if d.GetClass() == 'PCB_SHAPE':
        sh = d.GetShape()
        if sh == pcbnew.SHAPE_T_POLY:
            pts = d.GetPolyShape().Outline(0)
            n = pts.PointCount()
            print("      poly:", [(round(mm(pts.CPoint(i).x), 3),
                                  round(mm(pts.CPoint(i).y), 3))
                                 for i in range(n)])
        else:
            print(f"      start=({mm(d.GetStart().x):.3f},{mm(d.GetStart().y):.3f})"
                  f" end=({mm(d.GetEnd().x):.3f},{mm(d.GetEnd().y):.3f})"
                  f" w={mm(d.GetWidth()):.3f} shape={sh}")
