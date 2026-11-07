#!/usr/bin/env python3
"""
The room between the pads of the parts that are close to each other.

The packer gives the pads of the parts with fine pads more room: the
DFN package of the U11 has its pins half a millimetre apart, and the
ground pad in the middle of the package is 1.6 millimetres wide.  A
track can not leave a pin when another part stands right next to it.

This script measures the room that the parts have on the board, so
that the rule of the packer can be checked.

Run:  pad_room.py [reference]
"""
import math
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")
sys.path.insert(0, HERE)
from pack import FINE        # noqa: E402  the parts with fine pads


def mm(v):
    return pcbnew.ToMM(v)


def gap(a, b):
    """The room between the rectangles of two pads."""
    (ax, ay, ahx, ahy) = a
    (bx, by, bhx, bhy) = b
    dx = max(0.0, abs(ax - bx) - (ahx + bhx))
    dy = max(0.0, abs(ay - by) - (ahy + bhy))
    return math.hypot(dx, dy)


def main():
    b = pcbnew.LoadBoard(PCB)
    only = sys.argv[1] if len(sys.argv) > 1 else None

    pads = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if not ref or (only and ref != only):
            continue
        for p in fp.Pads():
            pos = p.GetPosition()
            sz = p.GetSize()
            pads.append((ref, p.GetNumber(), p.GetNetname(),
                         mm(pos.x), mm(pos.y),
                         mm(sz.x) / 2, mm(sz.y) / 2))

    rows = []
    for i, a in enumerate(pads):
        for bpad in pads[i + 1:]:
            if a[0] == bpad[0]:
                continue
            d = gap(a[3:], bpad[3:])
            # the room that is needed: the escape room of the finer part
            need = max(FINE.get(a[0], 0.0), FINE.get(bpad[0], 0.0))
            if d < max(need, 1.0):
                rows.append((round(d, 3), need, a[0], a[1], a[2],
                             bpad[0], bpad[1], bpad[2]))
    rows.sort()
    print(f"{'gap':>7} {'need':>6}  the two pads")
    for (d, need, ar, an, anet, br, bn, bnet) in rows:
        mark = "  TOO CLOSE" if d < need else ""
        print(f"{d:7.3f} {need:6.2f}  {ar}.{an} ({anet}) <-> "
              f"{br}.{bn} ({bnet}){mark}")
    if not rows:
        print("no pair of pads is closer than a millimetre")


if __name__ == "__main__":
    main()
