#!/usr/bin/env python3
"""
The room around the pins of the U11.

The U11 is a DFN package with nine pins.  The pins are half a
millimetre apart and only 0.35 millimetres wide, and the ground pad
in the middle of the package is 1.6 millimetres wide.  A track of 0.2
millimetres does not fit between the pins, and a via does not fit on a
pin either, so every pin has to be led out over the edge of the
package.

This script shows the pins, the other copper around them, and the room
that is left for a track of a given width.

Run:  u11_room.py [track width in millimetres]
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")

# the pins of the U11 and the net of every one of them
U11_PADS = {}


def mm(v):
    return pcbnew.ToMM(v)


def main():
    width = float(sys.argv[1]) if len(sys.argv) > 1 else 0.2
    b = pcbnew.LoadBoard(PCB)

    u11 = b.FindFootprintByReference("U11")
    if u11 is None:
        print("the U11 is not on the board")
        return

    # the box of the package
    bb = u11.GetBoundingBox()
    x0 = mm(bb.GetLeft()) - 1.0
    x1 = mm(bb.GetRight()) + 1.0
    y0 = mm(bb.GetTop()) - 1.0
    y1 = mm(bb.GetBottom()) + 1.0

    # the pins
    pins = []
    for p in u11.Pads():
        pos = p.GetPosition()
        sz = p.GetSize()
        pins.append((p.GetNumber(), p.GetNetname(),
                     mm(pos.x), mm(pos.y),
                     mm(sz.x) / 2, mm(sz.y) / 2))
    print(f"the U11 at ({mm(u11.GetPosition().x):.3f},"
          f"{mm(u11.GetPosition().y):.3f}), "
          f"{len(pins)} pins")
    print(f"the package is from {mm(bb.GetLeft()):.3f} to "
          f"{mm(bb.GetRight()):.3f} in x and from "
          f"{mm(bb.GetTop()):.3f} to {mm(bb.GetBottom()):.3f} in y")
    print()
    for (n, net, x, y, hx, hy) in sorted(pins, key=lambda p: (p[2], p[3])):
        print(f"  pin {n} {net:18} at ({x:8.3f},{y:8.3f})"
              f"  {2 * hx:5.2f} x {2 * hy:5.2f}"
              f"  from {x - hx:8.3f} to {x + hx:8.3f}")

    # the copper of the other parts that is near the package
    print()
    print("the copper of the other parts around the package")
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref == "U11":
            continue
        fbb = fp.GetBoundingBox()
        if (mm(fbb.GetRight()) < x0 or mm(fbb.GetLeft()) > x1
                or mm(fbb.GetBottom()) < y0 or mm(fbb.GetTop()) > y1):
            continue
        print(f"  {ref:6} from {mm(fbb.GetLeft()):8.3f} to "
              f"{mm(fbb.GetRight()):8.3f} in x and from "
              f"{mm(fbb.GetTop()):8.3f} to {mm(fbb.GetBottom()):8.3f} in y")
        for p in fp.Pads():
            pos = p.GetPosition()
            sz = p.GetSize()
            print(f"      pad {p.GetNumber():3} {p.GetNetname():18}"
                  f" at ({mm(pos.x):8.3f},{mm(pos.y):8.3f})"
                  f"  {mm(sz.x):5.2f} x {mm(sz.y):5.2f}")

    # the tracks that are near the package
    print()
    print("the tracks around the package")
    for t in b.GetTracks():
        a = t.GetStart()
        e = t.GetEnd()
        ax, ay = mm(a.x), mm(a.y)
        ex, ey = mm(e.x), mm(e.y)
        if (max(ax, ex) < x0 or min(ax, ex) > x1
                or max(ay, ey) < y0 or min(ay, ey) > y1):
            continue
        lay = "via " if t.GetClass() == "PCB_VIA" else t.GetLayerName()
        print(f"  {lay} {t.GetNetname():18} ({ax:8.3f},{ay:8.3f})"
              f" -> ({ex:8.3f},{ey:8.3f})  width {mm(t.GetWidth()):.2f}")

    # the room on a grid of a tenth of a millimetre
    print()
    print(f"the room for a track of {width:.2f} millimetres"
          f" (the x is copper, the dot is free)")
    step = 0.1
    nx = int((x1 - x0) / step)
    ny = int((y1 - y0) / step)
    head = "        "
    for i in range(0, nx + 1, 5):
        head += f"{int(x0 + i * step) % 100:3d}"
    print(head)
    for j in range(ny, -1, -1):
        y = y0 + j * step
        line = ""
        for i in range(nx + 1):
            x = x0 + i * step
            line += "#" if busy(b, x, y, width) else "."
        print(f"  {y:7.2f} {line}")


def busy(board, x, y, width):
    """Is there copper at the point that is too close for a track?"""
    half = width / 2
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for p in fp.Pads():
            pos = p.GetPosition()
            sz = p.GetSize()
            hx, hy = mm(sz.x) / 2, mm(sz.y) / 2
            px, py = mm(pos.x), mm(pos.y)
            # the pin of the U11 that the track leaves is free
            if ref == "U11":
                continue
            if (abs(px - x) <= hx + half and abs(py - y) <= hy + half):
                return True
    return False


if __name__ == "__main__":
    main()
