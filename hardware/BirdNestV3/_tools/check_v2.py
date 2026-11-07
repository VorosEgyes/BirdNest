#!/usr/bin/env python3
"""Run the same collision check on the V2 reference board for comparison."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layout_v3
import pcbnew

board = pcbnew.LoadBoard(layout_v3.V2)
print("=== V2 reference board ===")
print("footprints:", len(list(board.GetFootprints())))
print("tracks:", len(list(board.GetTracks())))
print("zones:", len(list(board.Zones())))
issues = layout_v3.check(board)
print("V2 issues:", issues)

# what exactly overlaps BT1 <-> H1/H2 ?
print()
print("=== BT1 vs mounting holes (silk vs silk?) ===")
bt = board.FindFootprintByReference("BT1")
for ref in ("H1", "H2", "H3", "H4"):
    h = board.FindFootprintByReference(ref)
    if h is None:
        continue
    hb = h.GetBoundingBox(True, False)
    bb = bt.GetBoundingBox(False, False)
    print(f"  {ref} pads-bbox X {pcbnew.ToMM(hb.GetLeft()):.2f}..{pcbnew.ToMM(hb.GetRight()):.2f}"
          f"  Y {pcbnew.ToMM(hb.GetTop()):.2f}..{pcbnew.ToMM(hb.GetBottom()):.2f}")
    print(f"  BT1 silk-bbox X {pcbnew.ToMM(bb.GetLeft()):.2f}..{pcbnew.ToMM(bb.GetRight()):.2f}"
          f"  Y {pcbnew.ToMM(bb.GetTop()):.2f}..{pcbnew.ToMM(bb.GetBottom()):.2f}")
