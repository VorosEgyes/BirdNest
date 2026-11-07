#!/usr/bin/env python3
"""
The route of the battery pins of the U11.

The U11 is a DFN-9 with a 0.5 millimetre pin pitch.  The pins are in
two columns of four, the left one at x=179.675 and the right one at
x=182.375, and the big ground pad of the package sits between them.

The /BAT_PROT+ is on the pin 5 and on the pin 8 of the package, with
the pin 6 and the pin 7 between them.  The two pins can not be joined
on the front copper, because the escapes of the pin 6 and the pin 7
have to cross that route.  On the back copper they can be joined, but
a via of 0.6 millimetres does not fit on a pin of this package: it
would touch the pin next to it.  A via of 0.4 millimetres fits, but
the layout rules ask for 0.6.

The net has fifteen pads and it is a tree, not a path.  So the two
pins of the package can not be joined to the rest of the net on their
own either: the part of the net that reaches the battery has to be
routed as well.

Every attempt to draw the route made the board worse, so the script
does not draw anything.  It reports the state of the package, and the
removal of the copper of a net is in delitem.py.

Run:  fix_u11_escapes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"
# The pads of the /BAT_PROT+ that are on the package: the pin 5 and the
# pin 8.  They are in the right column of the package, with the pin 6
# and the pin 7 between them, so they cannot be joined on the outside
# of the package without crossing the escapes of the pin 6 and the pin 7.
#
# The two pins are joined on the back copper: the pins are surface
# mount pads, so the back copper is free under them.  A via of 0.6
# millimetres does not fit on a pin of this package, it would touch the
# pin next to it, so the vias sit next to the pins.
BAT_PROT_PINS = [(182.375, 84.525), (182.375, 83.025)]


def report(board):
    """The state of the package."""
    for (x, y) in BAT_PROT_PINS:
        pad = None
        for fp in board.GetFootprints():
            if fp.GetReference() != "U11":
                continue
            for p in fp.Pads():
                pos = p.GetPosition()
                if (abs(pcbnew.ToMM(pos.x) - x) < 0.01
                        and abs(pcbnew.ToMM(pos.y) - y) < 0.01):
                    pad = p
        if pad is None:
            print(f"the pad at ({x}, {y}) is not on the board")
            continue
        print(f"the pad at ({x}, {y}) is on the {pad.GetNetname()} net")


def main():
    print("the route of the battery pins of the U11 is not solved yet")
    report(pcbnew.LoadBoard(V3))
    return 1



if __name__ == "__main__":
    sys.exit(main())
