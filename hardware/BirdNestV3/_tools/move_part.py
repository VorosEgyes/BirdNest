#!/usr/bin/env python3
"""
Move a component to a new place on the board.

The maze router cannot route a net of a fine pitch package when the
neighbouring parts stand in the way of the pins.  This script moves a
part out of the way and reports the free space around it.

Run:  move_part.py <ref> <x> <y> [<rotation>]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"


def to_mm(v):
    return pcbnew.ToMM(v)


def mm(v):
    return int(round(v * 1e6))


def main():
    if len(sys.argv) < 4:
        print("usage: move_part.py <ref> <x> <y> [rot]")
        return 1
    ref = sys.argv[1]
    x = float(sys.argv[2])
    y = float(sys.argv[3])
    rot = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0

    b = pcbnew.LoadBoard(V3)
    fp = b.FindFootprintByReference(ref)
    if fp is None:
        print(f"{ref} not found")
        return 1

    old = fp.GetPosition()
    print(f"{ref}: ({to_mm(old.x):.3f},{to_mm(old.y):.3f}) rot="
          f"{fp.GetOrientationDegrees():.1f} -> ({x:.3f},{y:.3f}) rot={rot}")
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    fp.SetOrientationDegrees(rot)

    b.BuildListOfNets()
    pcbnew.SaveBoard(V3, b)
    print("saved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
