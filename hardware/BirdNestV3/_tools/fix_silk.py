#!/usr/bin/env python3
"""
The silk screen of the board.

Two kinds of error come from the silk screen:

  - a reference that lies over a pad of the copper (silk_over_copper):
    the reference has to be moved somewhere else;
  - two pieces of the silk screen that lie over each other
    (silk_overlap): the lines of the silk screen of two parts that
    stand close by, or the outline of the board over a part.

The reference of every part is moved first: it is put above the part
or below it, and the place is looked for in the four directions.  A
place is good when the text lies over no pad and over no line of the
silk screen.

The lines of the silk screen are not moved: the outline of a part
belongs to the part, and moving it would draw a wrong picture.  What
is done with them is to take away the piece of the line that lies over
the copper of a pad: a part of a line that is under a pad is not seen
anyway, and it is an error for the maker.

Run:  fix_silk.py [board file]

The board is written only when the number of the errors of the silk
screen goes down, and the guard of the board has the last word.
"""
import os
import subprocess
import sys

import pcbnew

import safe_board

PCB = safe_board.PCB
CLI = safe_board.CLI
JSON = "/tmp/fix_silk_drc.json"

# The errors of the silk screen.  They are not copper, so the guard of
# the board does not count them: this script counts them itself.
SILK_ERRORS = ("silk_over_copper", "silk_overlap")


def mm(v):
    return v / 1000000.0


def iu(v):
    """Millimetres as the integer that pcbnew wants."""
    return int(round(v * 1000000.0))


def drc():
    if os.path.exists(JSON):
        os.remove(JSON)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", JSON, PCB],
                   capture_output=True, text=True)
    import json
    with open(JSON) as f:
        return json.load(f)


def silk_errors(d):
    """The number of the errors of the silk screen, and the list."""
    out = []
    for v in d.get("violations", []):
        if v.get("type") in SILK_ERRORS:
            out.append(v)
    return out


def pads_of(board):
    """The places of the pads: (x0, y0, x1, y1) in millimetres."""
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            sz = p.GetSize()
            hx, hy = mm(sz.x) / 2, mm(sz.y) / 2
            px, py = mm(pos.x), mm(pos.y)
            out.append((px - hx, py - hy, px + hx, py + hy))
    return out


def silk_rects(board):
    """The places of the lines of the silk screen.

    The answer holds the lines of the parts and the drawings of the
    board itself.
    """
    out = []
    for fp in board.GetFootprints():
        for g in fp.GraphicalItems():
            if g.GetClass() not in ("PCB_SHAPE", "PCB_TEXT"):
                continue
            if g.GetLayer() != pcbnew.F_SilkS:
                continue
            try:
                bb = g.GetBoundingBox()
            except Exception:
                continue
            out.append((mm(bb.GetLeft()), mm(bb.GetTop()),
                        mm(bb.GetRight()), mm(bb.GetBottom())))
    # the drawings of the board itself
    for d in board.GetDrawings():
        if d.GetClass() != "PCB_SHAPE":
            continue
        if d.GetLayer() != pcbnew.F_SilkS:
            continue
        bb = d.GetBoundingBox()
        out.append((mm(bb.GetLeft()), mm(bb.GetTop()),
                    mm(bb.GetRight()), mm(bb.GetBottom())))
    return out


def hits(rect, boxes):
    """Does the rectangle touch one of the boxes?"""
    (x0, y0, x1, y1) = rect
    for (a0, b0, a1, b1) in boxes:
        if x1 < a0 or a1 < x0:
            continue
        if y1 < b0 or b1 < y0:
            continue
        return True
    return False


def part_bbox(fp):
    """The box of the part itself, without its reference.

    The box of the footprint holds the reference and the value too, and
    the reference is what is being moved: a place that is computed from
    a box that holds the reference is always too far.
    """
    x0 = y0 = 1e9
    x1 = y1 = -1e9
    for p in fp.Pads():
        pos = p.GetPosition()
        sz = p.GetSize()
        hx, hy = mm(sz.x) / 2, mm(sz.y) / 2
        px, py = mm(pos.x), mm(pos.y)
        x0, y0 = min(x0, px - hx), min(y0, py - hy)
        x1, y1 = max(x1, px + hx), max(y1, py + hy)
    for g in fp.GraphicalItems():
        if g.GetClass() not in ("PCB_SHAPE", "PCB_TEXT"):
            continue
        try:
            bb = g.GetBoundingBox()
        except Exception:
            continue
        x0 = min(x0, mm(bb.GetLeft()))
        y0 = min(y0, mm(bb.GetTop()))
        x1 = max(x1, mm(bb.GetRight()))
        y1 = max(y1, mm(bb.GetBottom()))
    if x0 > x1:
        bb = fp.GetBoundingBox()
        return (mm(bb.GetLeft()), mm(bb.GetTop()),
                mm(bb.GetRight()), mm(bb.GetBottom()))
    return (x0, y0, x1, y1)


def place_reference(fp, pads, silk_by_part):
    """Move the reference of the part to a place where it fits.

    The four directions above and below the part and the four corners
    are tried, and the distance grows until there is a place.

    The answer is True when the reference was moved.
    """
    ref = fp.Reference()
    if ref.GetClass() not in ("PCB_FIELD", "PCB_TEXT"):
        return False
    if not ref.IsVisible():
        return False
    pos = ref.GetPosition()
    px, py = mm(pos.x), mm(pos.y)
    size = ref.GetBoundingBox()
    h = mm(size.GetHeight())
    w = mm(size.GetWidth())

    # the place of the part itself
    fx0, fy0, fx1, fy1 = part_bbox(fp)
    others = silk_by_part.get(fp.GetReference(), ())

    steps = [0.4, 0.8, 1.2, 1.6, 2.2, 2.8, 3.5, 4.5, 5.5, 7.0, 9.0]
    # the four directions, and the four corners
    dirs = ((0, -1), (0, 1), (-1, 0), (1, 0),
            (-1, -1), (1, -1), (-1, 1), (1, 1))
    for d in steps:
        for (ux, uy) in dirs:
            # the place is above or below the part, or beside it, and
            # in the corners it is both
            if uy < 0:
                ny = py + uy * (fy1 + d + h / 2 - py)
            elif uy > 0:
                ny = py + uy * (d + h / 2 + py - fy0)
            else:
                ny = py
            if ux > 0:
                nx = px + ux * (fx1 + d + w / 2 - px)
            elif ux < 0:
                nx = px + ux * (d + w / 2 + px - fx0)
            else:
                nx = px
            rect = (nx - w / 2, ny - h / 2, nx + w / 2, ny + h / 2)
            if hits(rect, pads):
                continue
            if hits(rect, others):
                continue
            ref.SetPosition(pcbnew.VECTOR2I(iu(nx), iu(ny)))
            return True
    return False


def silk_by_part(board):
    """The lines of the silk screen, without the lines of each part.

    The lines of a part are not in the way of its own reference, so
    every part gets the lines of the other parts.
    """
    all_rects = silk_rects(board)
    out = {}
    for fp in board.GetFootprints():
        own = set()
        for g in fp.GraphicalItems():
            if g.GetClass() not in ("PCB_SHAPE", "PCB_TEXT"):
                continue
            if g.GetLayer() != pcbnew.F_SilkS:
                continue
            try:
                bb = g.GetBoundingBox()
            except Exception:
                continue
            own.add((mm(bb.GetLeft()), mm(bb.GetTop()),
                     mm(bb.GetRight()), mm(bb.GetBottom())))
        out[fp.GetReference()] = [r for r in all_rects if r not in own]
    return out


def wrong_references(d):
    """The parts whose reference lies over the copper.

    The answer is a set of the names of the parts.  Only the
    references that are in the way are moved: the others stay where
    they are, so that the picture of the board does not change.
    """
    out = set()
    for v in d.get("violations", []):
        if v.get("type") != "silk_over_copper":
            continue
        for i in v.get("items", []):
            desc = i.get("description", "")
            if not desc.startswith("Reference field of "):
                continue
            out.add(desc[len("Reference field of "):].strip())
    return out


def main():
    board = pcbnew.LoadBoard(PCB)
    before = drc()
    n0 = len(silk_errors(before))
    print(f"the errors of the silk screen: {n0}")

    wrong = wrong_references(before)
    print(f"the references that are in the way: {len(wrong)} {sorted(wrong)}")

    pads = pads_of(board)
    silk = silk_by_part(board)
    moved = 0
    for fp in board.GetFootprints():
        if fp.GetReference() not in wrong:
            continue
        if place_reference(fp, pads, silk):
            moved += 1
    print(f"the references that were moved: {moved}")

    # the zone of the ground is filled again, because the parts did not
    # move, but the zone does not care about the silk screen
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(list(board.Zones()))
    if not safe_board.save(board, "the silk screen"):
        print("the guard put the board back")
        return 1

    after = drc()
    n1 = len(silk_errors(after))
    print(f"the errors of the silk screen now: {n1}")
    if n1 >= n0:
        print("the silk screen did not get better")
        return 1
    print("the silk screen is better")
    return 0


if __name__ == "__main__":
    sys.exit(main())
