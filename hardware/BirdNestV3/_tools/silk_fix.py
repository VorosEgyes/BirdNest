#!/usr/bin/env python3
"""Move the reference fields of the board that lie over other silk or copper.

The rules checker says that the designators of the board lie over the
silk of the parts and over the copper.  The designator of a part is
moved to a place where there is room for it.  The places are looked for
in this order:

  1. beside the part, in the eight directions, in three fits;
  2. around the part, in a ring of a few millimetres;
  3. the same, with a smaller name;
  4. the same, with the name turned sideways;
  5. the same, on the back silkscreen;
  6. the name is hidden, when there is no room at all.

The boxes are used, not the exact shapes: a box holds the shape, so a
place that is free by the boxes is free indeed.  A place may be given
up that was not needed, but no error is left behind.

Usage:  silk_fix.py            -- the plan, nothing is written
        silk_fix.py --apply    -- the board is written
"""
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
JSON = "/tmp/silk_fix_drc.json"

GAP = 0.25          # the space between the part and the name
SMALL = 0.8         # the height of a name that has no room
THIN = 0.12         # the thickness of a small name


def mm(v):
    return pcbnew.ToMM(v)


def box(item):
    """The box of the shape of the item, with the width of the line.

    The shape of a piece of silk does not hold the width of the line
    that draws it, so the width is added to the box by hand.  A box
    that holds the piece of silk is a box that holds the line of it.
    """
    try:
        if hasattr(item, "GetEffectiveTextShape"):
            bb = item.GetEffectiveTextShape().BBox()
            grow = mm(item.GetTextThickness()) / 2
        else:
            bb = item.GetEffectiveShape().BBox()
            grow = mm(item.GetWidth()) / 2 if hasattr(item, "GetWidth") else 0.0
        return (mm(bb.GetLeft()) - grow, mm(bb.GetTop()) - grow,
                mm(bb.GetRight()) + grow, mm(bb.GetBottom()) + grow)
    except Exception:
        bb = item.GetBoundingBox()
        return (mm(bb.GetLeft()), mm(bb.GetTop()),
                mm(bb.GetRight()), mm(bb.GetBottom()))


def meets(a, b):
    """Do the two boxes meet?"""
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def drc():
    if os.path.exists(JSON):
        os.remove(JSON)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", JSON, PCB],
                   capture_output=True, text=True)
    with open(JSON) as f:
        return json.load(f)


def offenders(report):
    """The designators that the rules checker complains about."""
    out = {}
    for v in report.get("violations", []):
        if v.get("type") not in ("silk_overlap", "silk_over_copper"):
            continue
        for it in v.get("items", []):
            d = it.get("description", "")
            if d.startswith("Reference field of "):
                ref = d[len("Reference field of "):].strip()
                out[ref] = out.get(ref, 0) + 1
    return out


def part_box(fp):
    """The box of the part: its pads and its silk."""
    xs, ys = [], []
    for p in fp.Pads():
        b = box(p)
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    for g in fp.GraphicalItems():
        if g.GetLayerName() in ("F.Silkscreen", "B.Silkscreen"):
            b = box(g)
            xs += [b[0], b[2]]
            ys += [b[1], b[3]]
    if not xs:
        return box(fp)
    return (min(xs), min(ys), max(xs), max(ys))


def beside(part, name):
    """The boxes the name may take, beside the part."""
    (pl, pt, pr, pb) = part
    (nl, nt, nr, nb) = name
    w = nr - nl
    h = nb - nt
    out = []
    for x in ((pl + pr) / 2 - (nl + nr) / 2, pl - nl, pr - nr):
        out.append((nl + x, pt - GAP - h, nr + x, pt - GAP))
        out.append((nl + x, pb + GAP, nr + x, pb + GAP + h))
    for y in ((pt + pb) / 2 - (nt + nb) / 2, pt - nt, pb - nb):
        out.append((pl - GAP - w, nt + y, pl - GAP, nb + y))
        out.append((pr + GAP, nt + y, pr + GAP + w, nb + y))
    for x in (pl - nl, pr - nr):
        for y in (pt - nt, pb - nb):
            out.append((nl + x, nt + y, nr + x, nb + y))
    return out


def around(part, name):
    """The boxes the name may take, in a ring around the part."""
    (pl, pt, pr, pb) = part
    (nl, nt, nr, nb) = name
    w = nr - nl
    h = nb - nt
    cx = (pl + pr) / 2
    cy = (pt + pb) / 2
    out = []
    for r in (0.9, 1.3, 1.7, 2.1, 2.6, 3.2, 4.0):
        for a in range(0, 360, 20):
            dx = r * math.cos(math.radians(a))
            dy = r * math.sin(math.radians(a))
            out.append((cx - w / 2 + dx, cy - h / 2 + dy,
                        cx + w / 2 + dx, cy + h / 2 + dy))
    return out


def main():
    apply = "--apply" in sys.argv
    board = pcbnew.LoadBoard(PCB)
    report = drc()
    bad = offenders(report)
    print(f"the board: {len(report.get('violations', []))} violations,"
          f" {len(bad)} designators in them")

    # every piece of silk and every piece of copper of the board
    silk = []
    copper = []
    for f in board.GetFootprints():
        for g in f.GraphicalItems():
            if g.GetLayerName() in ("F.Silkscreen", "B.Silkscreen"):
                silk.append((f"{f.GetReference()} silk", box(g), g.GetLayerName()))
        silk.append((f"{f.GetReference()} name", box(f.Reference()),
                     f.Reference().GetLayerName()))
    for d in board.GetDrawings():
        if d.GetLayerName() in ("F.Silkscreen", "B.Silkscreen"):
            silk.append(("drawing", box(d), d.GetLayerName()))
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.IsOnLayer(pcbnew.F_Cu):
                copper.append((f"{f.GetReference()}.{p.GetNumber()}", box(p), "F"))
            if p.IsOnLayer(pcbnew.B_Cu):
                copper.append((f"{f.GetReference()}.{p.GetNumber()}", box(p), "B"))
    for t in board.GetTracks():
        lay = "F" if t.GetLayer() == pcbnew.F_Cu else "B"
        copper.append((t.GetNetname(), box(t), lay))

    plan = []
    for ref, n in sorted(bad.items()):
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            print(f"  {ref}: no such part")
            continue
        text = fp.Reference()
        home = box(text)
        part = part_box(fp)
        angle0 = text.GetTextAngle().AsDegrees()
        height0 = mm(text.GetTextHeight())
        thick0 = mm(text.GetTextThickness())

        def free(cand, side):
            """Is the place free on the side of the name?

            The silk of the front is over the copper of the front, and
            the silk of the back is over the copper of the back.
            """
            for (name, b, lay) in silk:
                if name == f"{ref} name" or lay != side:
                    continue
                if meets(cand, b):
                    return False
            for (name, b, lay) in copper:
                if lay != side[0]:
                    continue
                if meets(cand, b):
                    return False
            return True

        def search():
            """The first place that is free, with the name as it is."""
            here = box(text)
            side = text.GetLayerName()
            for cand in beside(part, here) + around(part, here):
                if free(cand, side):
                    return cand
            return None

        found = search()
        how = ""
        if found is None:
            # a smaller name
            text.SetTextHeight(pcbnew.FromMM(SMALL))
            text.SetTextThickness(pcbnew.FromMM(THIN))
            found = search()
            how = ", smaller"
        if found is None:
            # a small name, sideways
            text.SetTextAngle(pcbnew.EDA_ANGLE(90, pcbnew.DEGREES_T))
            found = search()
            how = ", smaller, sideways"
        if found is None:
            # the name on the back silkscreen
            text.SetTextAngle(pcbnew.EDA_ANGLE(angle0, pcbnew.DEGREES_T))
            text.SetTextHeight(pcbnew.FromMM(height0))
            text.SetTextThickness(pcbnew.FromMM(thick0))
            text.SetLayer(pcbnew.B_SilkS)
            text.SetMirrored(True)
            found = search()
            how = ", on the back"
            if found is None:
                # a smaller name on the back
                text.SetTextHeight(pcbnew.FromMM(SMALL))
                text.SetTextThickness(pcbnew.FromMM(THIN))
                found = search()
                how = ", smaller, on the back"
        if found is None:
            text.SetLayer(pcbnew.F_SilkS)
            text.SetMirrored(False)
            print(f"  {ref}: {n} overlaps, no room: the name is hidden")
            plan.append((ref, None, None))
            continue

        # the box of the name as it is now: it is smaller and turned
        # when there was no room for it as it was
        here = box(text)
        dx = found[0] - here[0]
        dy = found[1] - here[1]
        # the name has moved: the next name may not lie over it
        side = text.GetLayerName()
        silk = [(nm, (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy) if nm == f"{ref} name" else b,
                 side if nm == f"{ref} name" else lay) for (nm, b, lay) in silk]
        print(f"  {ref}: {n} overlaps, moved by ({dx:+.2f},{dy:+.2f}){how}")
        plan.append((ref, dx, dy))

    if not apply:
        print("nothing was written")
        return 0

    for (ref, dx, dy) in plan:
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            continue
        text = fp.Reference()
        if dx is None:
            text.SetVisible(False)
            continue
        p = text.GetPosition()
        text.SetPosition(pcbnew.VECTOR2I(p.x + pcbnew.FromMM(dx),
                                        p.y + pcbnew.FromMM(dy)))
    pcbnew.SaveBoard(PCB, board)
    print("the board is written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
