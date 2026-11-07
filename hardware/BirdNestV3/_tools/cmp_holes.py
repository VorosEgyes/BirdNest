#!/usr/bin/env python3
"""Compare the H1/BT3 pad geometry between the V2 reference and the V3 build."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_v3
import pcbnew


def show(board, tag, btref):
    print(f"=== {tag} ===")
    for ref in ("H1", "H2", btref):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            print(f"  {ref}: not found")
            continue
        print(f"  {ref}  fpid={fp.GetFPID().GetUniStringLibId()}")
        pe = layout_v3.pad_extent(fp)
        print(f"     pad-extent: {pe}")
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            print(f"     pad '{p.GetNumber()}' type={p.GetAttribute()} "
                  f"X {pcbnew.ToMM(bb.GetLeft()):7.2f}..{pcbnew.ToMM(bb.GetRight()):7.2f} "
                  f"Y {pcbnew.ToMM(bb.GetTop()):7.2f}..{pcbnew.ToMM(bb.GetBottom()):7.2f} "
                  f"net={p.GetNetname()}")
    print()


v2 = pcbnew.LoadBoard(layout_v3.V2)
show(v2, "V2 reference", "BT1")

v3 = pcbnew.LoadBoard(layout_v3.V3)
layout_v3.add_mounting_holes(v3)
show(v3, "V3 build (H from stock MountingHole lib)", "BT3")

print("=== stock MountingHole_3.2mm_M3.kicad_mod ===")
fp = layout_v3.load_footprint(layout_v3.MH_FP)
print("  pads:", len(list(fp.Pads())))
print("  graphics:", len(list(fp.GraphicalItems())))
for p in fp.Pads():
    bb = p.GetBoundingBox()
    print(f"  pad '{p.GetNumber()}' attr={p.GetAttribute()} "
          f"X {pcbnew.ToMM(bb.GetLeft()):.2f}..{pcbnew.ToMM(bb.GetRight()):.2f} "
          f"Y {pcbnew.ToMM(bb.GetTop()):.2f}..{pcbnew.ToMM(bb.GetBottom()):.2f}")

print()
print("=== V2 H1 footprint (custom) ===")
h1 = v2.FindFootprintByReference("H1")
print("  fpid:", h1.GetFPID().GetUniStringLibId())
print("  pads:", len(list(h1.Pads())))
print("  graphics:", len(list(h1.GraphicalItems())))
