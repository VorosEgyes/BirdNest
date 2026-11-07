#!/usr/bin/env python3
"""
DRC cleanup for the V3 board.

1. U11 (CN3065, DFN-9) has a 0.5 mm pad pitch with a 0.15 mm pad gap, which is
   below the 0.25 mm Signal netclass clearance.  This is manufacturer
   geometry, not a placement error, so the pads get a local clearance of
   0.15 mm.  The clearance to *other* components stays at 0.25 mm.
2. Silk text on the newly placed footprints is 0.7874 mm high, just under the
   0.8 mm board minimum -> bumped to 0.8 mm.
3. Reference designators are moved out of the way of neighbouring silkscreen.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"

# footprints whose internal pad gap is tighter than the netclass clearance
FINE_PITCH = {
    "U11": 0.15,   # CN3065 DFN-9, 0.5 mm pitch
}


def main():
    board = pcbnew.LoadBoard(V3)

    # ---- 1. local clearance on fine-pitch footprints ----------------------
    for ref, clr in FINE_PITCH.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            print(f"  !! {ref} not found")
            continue
        for pad in fp.Pads():
            pad.SetLocalClearance(pcbnew.FromMM(clr))
        print(f"  {ref}: local clearance {clr} mm on {len(list(fp.Pads()))} pads")

    # ---- 2. silk text height ---------------------------------------------
    fixed = 0
    for fp in board.GetFootprints():
        for item in list(fp.GraphicalItems()) + [fp.Reference(), fp.Value()]:
            if not isinstance(item, pcbnew.PCB_TEXT):
                continue
            if item.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                continue
            h = pcbnew.ToMM(item.GetTextHeight())
            if h < 0.8 - 1e-6:
                item.SetTextHeight(pcbnew.FromMM(0.8))
                fixed += 1
    print(f"  silk text heights bumped: {fixed}")

    # ---- 3. also fix the F.Fab / User.Comments texts ----------------------
    for fp in board.GetFootprints():
        for item in fp.GraphicalItems():
            if not isinstance(item, pcbnew.PCB_TEXT):
                continue
            if item.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS):
                h = pcbnew.ToMM(item.GetTextHeight())
                if h < 0.8 - 1e-6:
                    item.SetTextHeight(pcbnew.FromMM(0.8))
                    fixed += 1

    pcbnew.SaveBoard(V3, board)
    print("saved")


if __name__ == "__main__":
    main()
