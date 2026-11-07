#!/usr/bin/env python3
"""Inspect zones, edge cuts and their bounding boxes on a board."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew


def dump(path, tag):
    board = pcbnew.LoadBoard(path)
    print(f"=== {tag} ({path}) ===")
    print(f"footprints: {len(list(board.GetFootprints()))}  tracks: {len(list(board.GetTracks()))}  zones: {len(list(board.Zones()))}")

    print("-- Edge.Cuts --")
    for d in board.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts:
            bb = d.GetBoundingBox()
            print(f"   {d.GetClass()} X {pcbnew.ToMM(bb.GetLeft()):8.2f}..{pcbnew.ToMM(bb.GetRight()):8.2f}"
                  f"  Y {pcbnew.ToMM(bb.GetTop()):8.2f}..{pcbnew.ToMM(bb.GetBottom()):8.2f}")

    print("-- Zones --")
    for z in board.Zones():
        bb = z.GetBoundingBox()
        net = z.GetNetname()
        lset = {z.GetLayer()}
        print(f"   net={net!r:22} layers={z.GetLayerSet().FmtHex()} "
              f"X {pcbnew.ToMM(bb.GetLeft()):8.2f}..{pcbnew.ToMM(bb.GetRight()):8.2f}"
              f"  Y {pcbnew.ToMM(bb.GetTop()):8.2f}..{pcbnew.ToMM(bb.GetBottom()):8.2f}")
        try:
            ol = z.GetLocalClearance()
            print(f"       local_clearance={pcbnew.ToMM(ol):.3f}  priority={z.GetPriority()}  filled={z.IsFilled()}")
        except Exception:
            pass
        # outline points
        try:
            outline = z.Outline()
            pts = outline.COutline(0).CPointCount()
            xs = [pcbnew.ToMM(outline.COutline(0).CPoint(i).x) for i in range(pts)]
            ys = [pcbnew.ToMM(outline.COutline(0).CPoint(i).y) for i in range(pts)]
            print(f"       outline pts={pts} X {min(xs):.2f}..{max(xs):.2f}  Y {min(ys):.2f}..{max(ys):.2f}")
        except Exception as e:
            print("       outline err:", e)

    print("-- other layers present --")
    layers = {}
    for d in board.GetDrawings():
        layers.setdefault(d.GetLayerName(), 0)
        layers[d.GetLayerName()] += 1
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():
            layers.setdefault(g.GetLayerName(), 0)
            layers[g.GetLayerName()] += 1
    print("  ", layers)
    print()


if __name__ == "__main__":
    HW = "/Users/modmj/dev/BirdNest/hardware"
    dump(os.path.join(HW, "BirdNest_pcb", "BirdNest_pcb.kicad_pcb"), "V2 reference")
    dump(os.path.join(HW, "BirdNestV3", "BirdNestV3.kicad_pcb"), "V3 current")
