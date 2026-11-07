#!/usr/bin/env python3
"""Map the v2 reference board: zones, edge cuts, silk graphics, all footprint geometry."""
import pcbnew, sys

path = sys.argv[1]
b = pcbnew.LoadBoard(path)

print(f"=== {path} ===")
print(f"Title: {b.GetTitleBlock().GetTitle()}  rev: {b.GetTitleBlock().GetRevision()}")
print(f"Thickness: {pcbnew.ToMM(b.GetDesignSettings().GetBoardThickness())} mm")

print("\n--- Edge.Cuts ---")
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts:
        print(f"  {d.GetShapeStr():8} ({pcbnew.ToMM(d.GetStart().x):8.2f},{pcbnew.ToMM(d.GetStart().y):8.2f}) -> "
              f"({pcbnew.ToMM(d.GetEnd().x):8.2f},{pcbnew.ToMM(d.GetEnd().y):8.2f})  w={pcbnew.ToMM(d.GetWidth()):.3f}")

print("\n--- Zones (with outline, clearance, fill) ---")
for z in b.Zones():
    pts = []
    try:
        for p in z.Outline().Outline(0).CPoints():
            pts.append((pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))
    except Exception as e:
        pass
    print(f"  layer={b.GetLayerName(z.GetLayer()):5} net={z.GetNetname():12} filled={z.IsFilled()} "
          f"clearance={pcbnew.ToMM(z.GetLocalClearance()):.3f} minwidth={pcbnew.ToMM(z.GetMinThickness()):.3f}")
    for i in range(len(pts)):
        print(f"      ({pts[i][0]:8.2f},{pts[i][1]:8.2f})")

print("\n--- Keepout zones ---")
for z in b.Zones():
    if z.GetIsRuleArea():
        try:
            pts = [(pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)) for p in z.Outline().Outline(0).CPoints()]
            print(f"  RULE AREA layer={b.GetLayerName(z.GetLayer())} keepout={z.GetDoNotAllowTracks()}/{z.GetDoNotAllowVias()}/{z.GetDoNotAllowPads()}")
            for p in pts: print(f"      ({p[0]:8.2f},{p[1]:8.2f})")
        except Exception as e:
            print("  RULE AREA (outline err)", e)

print("\n--- Silkscreen graphics (board level) ---")
for d in b.GetDrawings():
    if d.GetClass() == "PCB_SHAPE" and d.GetLayer() != pcbnew.Edge_Cuts:
        print(f"  {b.GetLayerName(d.GetLayer()):12} {d.GetShapeStr():8} "
              f"({pcbnew.ToMM(d.GetStart().x):8.2f},{pcbnew.ToMM(d.GetStart().y):8.2f}) -> "
              f"({pcbnew.ToMM(d.GetEnd().x):8.2f},{pcbnew.ToMM(d.GetEnd().y):8.2f}) w={pcbnew.ToMM(d.GetWidth()):.3f}")
    elif d.GetClass() == "PCB_TEXT":
        p = d.GetPosition()
        print(f"  TEXT {b.GetLayerName(d.GetLayer()):12} '{d.GetText()}' at ({pcbnew.ToMM(p.x):8.2f},{pcbnew.ToMM(p.y):8.2f}) "
              f"rot={d.GetTextAngleDegrees():.0f} h={pcbnew.ToMM(d.GetTextHeight()):.2f} thick={pcbnew.ToMM(d.GetTextThickness()):.3f}")

print("\n--- Footprint courtyard/silk extents (v2) ---")
for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    if not fp.GetReference():
        continue
    bb = fp.GetBoundingBox(False, False)
    p = fp.GetPosition()
    print(f"  {fp.GetReference():6} {fp.GetValue():20} pos({pcbnew.ToMM(p.x):8.2f},{pcbnew.ToMM(p.y):8.2f}) "
          f"rot={fp.GetOrientationDegrees():7.1f} bbox X {pcbnew.ToMM(bb.GetLeft()):7.2f}..{pcbnew.ToMM(bb.GetRight()):7.2f} "
          f"Y {pcbnew.ToMM(bb.GetTop()):7.2f}..{pcbnew.ToMM(bb.GetBottom()):7.2f}")
