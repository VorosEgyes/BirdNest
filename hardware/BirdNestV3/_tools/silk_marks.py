#!/usr/bin/env python3
"""Move the silkscreen of the connector that stands on the test points.

The silkscreen of the connector in the corner of the board is drawn by
hand: the outline, the marks of the pins and the two slots.  The test
point TP4 stands on its edge, and the rules checker says that the
silk of the test point and the silk of the connector lie over each
other, and that the copper of the test point is under the silk of the
connector.

The whole drawing is moved a little to the right and up, so that the
test points are clear of it.  The marks of the pins keep their place
on the edge of the connector.

Usage:  silk_marks.py [--apply]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")

# the drawing of the connector, and where it goes
AREA = (112.0, 42.5, 128.5, 51.5)
MOVE = (2.5, -1.0)


def mm(v):
    return pcbnew.ToMM(v)


def main():
    apply = "--apply" in sys.argv
    board = pcbnew.LoadBoard(PCB)
    done = 0
    for d in board.GetDrawings():
        if d.GetLayerName() != "F.Silkscreen":
            continue
        bb = d.GetBoundingBox()
        box = (mm(bb.GetLeft()), mm(bb.GetTop()),
               mm(bb.GetRight()), mm(bb.GetBottom()))
        if (box[0] < AREA[0] or box[2] > AREA[2]
                or box[1] < AREA[1] or box[3] > AREA[3]):
            continue
        d.Move(pcbnew.VECTOR2I(pcbnew.FromMM(MOVE[0]), pcbnew.FromMM(MOVE[1])))
        done += 1
    print(f"{done} pieces of the drawing of the connector moved by "
          f"({MOVE[0]:+.2f},{MOVE[1]:+.2f})")
    if not apply:
        print("nothing was written")
        return 0
    pcbnew.SaveBoard(PCB, board)
    print("the board is written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
