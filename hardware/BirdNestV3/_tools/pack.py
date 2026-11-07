#!/usr/bin/env python3
"""
Automatic placement packer for the V3 board.

The proven V2 geometry is fixed: board outline (100..200 x 40..140), the 30
parts that exist in both revisions at their V2 positions, and the 4 M3
mounting holes.  This script packs the 29 V3-only parts into the free space.

Placement is connectivity-aware: parts are grouped into functional blocks
(charger, solar protection, cell protection, BAT_MON divider, test points)
and the packer minimises the distance of every part to its block anchor, so
related parts end up together and the routing stays short.

Algorithm: greedy best-fit over a 0.5 mm grid, exact footprint bounding
boxes, both rotations tried, full collision test against everything already
placed.  Output is a ref -> (x, y, rot) table for layout_v3.py.

The tracks of the V2 layout are obstacles as well.  They are the physical
design of the board: a part that stands on one of them can not be
soldered, because the track runs under the part and shorts the pads.  The
packs that ignored the tracks put the Q9 on the /BAT_RAW track and the D9
on the track of the old J3.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V3DIR = os.path.dirname(HERE)
V2 = "/Users/modmj/dev/BirdNest/hardware/BirdNest_pcb/BirdNest_pcb.kicad_pcb"

BX0, BX1, BY0, BY1 = 101.0, 199.0, 41.0, 139.0
GRID = 0.5
CLEAR = 0.35          # min gap between component bodies
EDGE_KEEP = 0.8       # min distance from the board edge
TRACK_CLEAR = 0.3     # min gap between a part and a track of the V2

# The clearance that the pads of two parts need, and the parts whose
# pads need more of it.  A part with fine pads needs room around its
# pads: the track that leaves a pad has to get away from the pad before
# it comes to the next part.  The DFN package of the U11 has its pads
# half a millimetre apart, and the ground pad in the middle of the
# package is 1.6 millimetres wide, so a line can not leave the pins at
# all when another part stands right next to them.
PAD_CLEAR = 0.4
ESCAPE_ROOM = 1.2
FINE = {"U11": 1.2, "U10": 1.0, "Q3": 1.0}

# functional blocks: group -> (anchor_x, anchor_y, [parts])
# The Q9, the R27 and the R28 take over the slots of the V2 Q7, R21 and
# R20.  They can not stay there: the tracks of the V2 layout that run
# through those slots are the tracks of the /BAT_PROT+ and of the
# Net-(Q9-G), and they would stand on them.  So they are packed like
# the other new parts.
GROUPS = [
    ("chg",    181.0, 90.0, ["U11", "R12", "R14", "TH1", "C24", "C25", "D7", "D8", "R13"]),
    ("solar",  194.0, 87.0, ["D9", "D10"]),
    ("prot",   143.0, 107.0, ["Q3", "U10", "R10", "R11", "C15", "C16", "C19", "C23"]),
    ("cell",   112.0, 108.0, ["Q9", "R27", "R28"]),
    ("batmon", 108.0, 60.0, ["R29", "R30", "C22"]),
    ("tp",     104.0, 50.0, ["TP1", "TP2", "TP3", "TP4", "TP5"]),
]

# preferred rotation (0 = landscape, 90 = portrait)
PREF_ROT = {}
for r in ["R10", "R11", "C15", "C16", "C19", "C23", "R29", "R30", "C22",
          "R12", "R14", "D7", "D8", "R13", "TH1", "D9", "D10"]:
    PREF_ROT[r] = 90
for r in ["U11", "U10", "Q3"]:
    PREF_ROT[r] = 0


def pad_track_gap(px0, py0, px1, py1, tx0, ty0, tx1, ty1):
    """The distance between the rectangle of a pad and a track segment.

    The rectangle is (px0, py0, px1, py1), the segment is from
    (tx0, ty0) to (tx1, ty1).  The distance is zero when they touch.

    The rectangle is a solid: the distance is measured from the inside
    of it, so a track that runs through the pad has the distance zero
    and not the distance to the corner of the pad.
    """
    # the closest point of the segment to the rectangle: the segment is
    # clipped to the rectangle, and the distance of the two parts that
    # are left is taken
    dx, dy = tx1 - tx0, ty1 - ty0
    L = dx * dx + dy * dy
    if L == 0:
        # a via: the distance of the point from the rectangle
        cx = min(max(tx0, px0), px1)
        cy = min(max(ty0, py0), py1)
        return ((tx0 - cx) ** 2 + (ty0 - cy) ** 2) ** 0.5

    # the parameter of the point of the segment that is closest to the
    # centre of the rectangle: the minimum of a convex function over
    # the segment is found at the point where the derivative changes
    # its sign, or at an end of the segment
    cx, cy = (px0 + px1) / 2, (py0 + py1) / 2
    t = ((cx - tx0) * dx + (cy - ty0) * dy) / L
    t = max(0.0, min(1.0, t))
    sx, sy = tx0 + t * dx, ty0 + t * dy
    # the point of the segment inside the rectangle?  then the distance
    # is zero
    if px0 <= sx <= px1 and py0 <= sy <= py1:
        return 0.0
    # the distance of the segment from the rectangle: the smallest
    # distance of the four edges and of the two ends
    best = float("inf")
    for (ex, ey) in ((tx0, ty0), (tx1, ty1)):
        cx = min(max(ex, px0), px1)
        cy = min(max(ey, py0), py1)
        best = min(best, ((ex - cx) ** 2 + (ey - cy) ** 2) ** 0.5)
    # the corners of the rectangle to the segment
    for (cpx, cpy) in ((px0, py0), (px1, py0), (px1, py1), (px0, py1)):
        tt = ((cpx - tx0) * dx + (cpy - ty0) * dy) / L
        tt = max(0.0, min(1.0, tt))
        best = min(best, ((cpx - tx0 - tt * dx) ** 2
                          + (cpy - ty0 - tt * dy) ** 2) ** 0.5)
    return best


def main():
    import pcbnew
    import layout_v3

    # The packer needs a clean board: the parts that were packed before
    # would be obstacles for the parts that are packed now.  The
    # original board of the V3 is the starting point of every pack.
    source = os.path.join(V3DIR, "BirdNestV3.kicad_pcb")
    original = "/tmp/BirdNestV3_ORIGINAL_backup.kicad_pcb"
    if os.path.exists(original):
        source = original
        print(f"packing from the original board: {source}")

    board = pcbnew.LoadBoard(source)

    # --- first bring the board to the V2 frame: mounting holes + shared parts
    layout_v3.add_mounting_holes(board)
    layout_v3.add_missing_footprints(board)
    for ref, (x, y, rot) in list(layout_v3.V2_POS.items()):
        fp = board.FindFootprintByReference(ref)
        if fp is not None:
            layout_v3.place(fp, x, y, rot)

    # The parts that take over a slot of the V2 are moved away before the
    # pack runs: the tracks of the V2 run through those slots, and the
    # parts would be in the way of the parts that are packed now.
    for ref in layout_v3.V2_SLOT_REPLACED:
        fp = board.FindFootprintByReference(ref)
        if fp is not None:
            # out of the way, in the corner that nothing uses
            layout_v3.place(fp, 102.0, 42.0, 0)
    print("the parts that take over a V2 slot were moved out of the way")

    # ---------------- obstacles: everything already on the board -----------
    obstacles = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        bb = fp.GetBoundingBox(False, False)
        obstacles.append([ref,
                          pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                          pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())])
    print(f"obstacles on board: {len(obstacles)}")

    # ---------------- the tracks of the V2 layout -------------------------
    # The tracks of the finished V2 layout are the physical design of the
    # board.  The body of a part may stand over a track - the body is
    # not copper - but a pad may not: a track that runs under a pad
    # shorts it.  Every track is therefore an obstacle for the pads of
    # the parts, grown by its own width and by the clearance.
    #
    # Every obstacle is (x0, y0, x1, y1, halfwidth, ax, ay, bx, by): the
    # box of the track first, so that the cheap test is cheap, and the
    # segment after it, so that the exact test has it at hand.
    v2 = pcbnew.LoadBoard(V2)
    v2_tracks = []
    for t in v2.GetTracks():
        a = t.GetStart()
        e = t.GetEnd()
        w = pcbnew.ToMM(t.GetWidth())
        ax, ay = pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)
        ex, ey = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
        if t.GetClass() == "PCB_VIA":
            # a via is a hole with a barrel of copper around it
            ex, ey = ax, ay
        v2_tracks.append((min(ax, ex), min(ay, ey),
                           max(ax, ex), max(ay, ey),
                           w / 2, ax, ay, ex, ey))
    print(f"tracks of the V2 layout as obstacles for the pads: "
          f"{len(v2_tracks)}")

    # ---------------- part sizes ------------------------------------------
    sizes = {}
    for _, _, _, parts in GROUPS:
        for ref in parts:
            fp = board.FindFootprintByReference(ref)
            if fp is None:
                print(f"  !! {ref} missing from board")
                continue
            bb = fp.GetBoundingBox(False, False)
            sizes[ref] = (pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()))

    print("\npart sizes (landscape):")
    for ref in sorted(sizes):
        w, h = sizes[ref]
        print(f"  {ref:5} {w:6.2f} x {h:6.2f}   (portrait {h:6.2f} x {w:6.2f})")

    # ---------------- pack -------------------------------------------------
    placed = []          # (ref, x0, y0, x1, y1)
    placed_pads = []     # the pad rectangles of the parts that are placed
    results = {}

    # The pads of the parts that are already on the board are obstacles
    # as well.  The clearance that matters is the distance between the
    # pads of two different parts - the bodies may be close to each
    # other, but their pads must keep the copper clearance, otherwise
    # the router has no way out between them.

    # the pads of every part, with the net they belong to
    board_pads = []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        for p in fp.Pads():
            pp = p.GetPosition()
            sz = p.GetSize()
            px = pcbnew.ToMM(pp.x)
            py = pcbnew.ToMM(pp.y)
            pw = pcbnew.ToMM(sz.x)
            ph = pcbnew.ToMM(sz.y)
            board_pads.append((ref, p.GetNetname(),
                               px - pw / 2, py - ph / 2,
                               px + pw / 2, py + ph / 2))
    print(f"\n{len(board_pads)} pads on the board")

    def pad_clear(ref):
        """The clearance that the pads of the part need.

        A part with fine pads needs more room around its pads than the
        plain copper clearance.
        """
        return max(PAD_CLEAR, FINE.get(ref, 0.0))

    def pad_free(pads, placed_pads, ref=""):
        """Do the pads of the part keep the clearance to the pads of the
        board?  `pads` is a list of (net, x0, y0, x1, y1) tuples, one
        per pad of the part that is being placed.  `placed_pads` holds
        the pads of the parts that were placed before, with the
        reference of the part.

        The tracks of the V2 layout are in the way as well: a track
        that runs under a pad shorts it.  The body of the part may
        stand over a track, but the pad may not.
        """
        need = pad_clear(ref)
        for (pnet, px0, py0, px1, py1) in pads:
            for (oref, onet, ox0, oy0, ox1, oy1) in board_pads:
                gap = max(need, pad_clear(oref))
                if (px0 < ox1 + gap and ox0 - gap < px1 and
                        py0 < oy1 + gap and oy0 - gap < py1):
                    return False
            for (pref, px0b, py0b, px1b, py1b) in placed_pads:
                gap = max(need, pad_clear(pref))
                if (px0 < px1b + gap and px0b - gap < px1 and
                        py0 < py1b + gap and py0b - gap < py1):
                    return False
            for (bx0, by0, bx1, by1, thr,
                 tx0, ty0, tx1, ty1) in v2_tracks:
                # the cheap test first: the boxes of the pad and of the
                # track have to be near each other at all
                if (px1 < bx0 - 2.0 or px0 > bx1 + 2.0
                        or py1 < by0 - 2.0 or py0 > by1 + 2.0):
                    continue
                # the distance of the pad from the track has to be more
                # than the half width of the track and the clearance
                if pad_track_gap(px0, py0, px1, py1,
                                 tx0, ty0, tx1, ty1) < thr + TRACK_CLEAR:
                    return False
        return True

    def free(x0, y0, x1, y1):
        if x0 < BX0 + EDGE_KEEP or x1 > BX1 - EDGE_KEEP:
            return False
        if y0 < BY0 + EDGE_KEEP or y1 > BY1 - EDGE_KEEP:
            return False
        for (orx0, ory0, orx1, ory1) in [(o[1], o[2], o[3], o[4]) for o in obstacles] + placed:
            if (x0 < orx1 + CLEAR and orx0 - CLEAR < x1 and
                    y0 < ory1 + CLEAR and ory0 - CLEAR < y1):
                return False
        return True

    for gname, ax, ay, parts in GROUPS:
        # place the group's parts: the ones with fine pads first, then
        # the biggest ones.  A part with fine pads needs a room around
        # itself, and that room is taken as soon as the part is placed,
        # so it has to be placed before the parts that would stand in
        # that room.
        ordered = sorted(parts,
                         key=lambda r: (0 if FINE.get(r) else 1,
                                        -max(sizes.get(r, (1, 1)))))
        for ref in ordered:
            w, h = sizes.get(ref, (2.0, 2.0))
            best = None
            for rot in ([PREF_ROT.get(ref, 0), 0, 90] if PREF_ROT.get(ref, 0) == 0
                        else [PREF_ROT.get(ref, 90), 90, 0]):
                if rot == 90:
                    pw, ph = h, w
                else:
                    pw, ph = w, h
                # search outward from the anchor
                rings = [
                    (ax, ay),
                ]
                cand = []
                # generate candidate centres in expanding squares around anchor
                step = GRID
                r = 0
                while r <= 90:
                    if r == 0:
                        cand.append((ax, ay))
                    else:
                        n = int(r / step)
                        for k in range(n):
                            cand.append((ax + k * step, ay + r * step))
                            cand.append((ax + k * step, ay - r * step))
                            cand.append((ax + r * step, ay + k * step))
                            cand.append((ax - r * step, ay + k * step))
                    r += step
                for (cx, cy) in cand:
                    x0 = round((cx - pw / 2) / GRID) * GRID
                    y0 = round((cy - ph / 2) / GRID) * GRID
                    x1, y1 = x0 + pw, y0 + ph
                    if not free(x0, y0, x1, y1):
                        continue
                    # the pads of the part have to keep their distance to
                    # the pads of the other parts as well
                    fp = board.FindFootprintByReference(ref)
                    if fp is not None:
                        cxr = x0 + (x1 - x0) / 2
                        cyr = y0 + (y1 - y0) / 2
                        own_pads = []
                        for pad in fp.Pads():
                            pp = pad.GetPosition()
                            sz = pad.GetSize()
                            dx = pcbnew.ToMM(pp.x) - pcbnew.ToMM(fp.GetPosition().x)
                            dy = pcbnew.ToMM(pp.y) - pcbnew.ToMM(fp.GetPosition().y)
                            pw2 = pcbnew.ToMM(sz.x)
                            ph2 = pcbnew.ToMM(sz.y)
                            if rot == 90:
                                dx, dy = -dy, dx
                                pw2, ph2 = ph2, pw2
                            own_pads.append((pad.GetNetname(),
                                             cxr + dx - pw2 / 2, cyr + dy - ph2 / 2,
                                             cxr + dx + pw2 / 2, cyr + dy + ph2 / 2))
                        if not pad_free(own_pads, placed_pads, ref):
                            continue
                    # cost: distance to group anchor + penalty for rotation change
                    d = math.hypot(x0 + pw / 2 - ax, y0 + ph / 2 - ay)
                    pen = 0.0 if rot == PREF_ROT.get(ref, 0) else 3.0
                    score = d + pen
                    if best is None or score < best[0]:
                        best = (score, x0, y0, rot, x1, y1)
                    if d < 2.0 and rot == PREF_ROT.get(ref, 0):
                        break
                if best is not None and best[0] < 1.0:
                    break
            if best is None:
                print(f"  !! NO ROOM for {ref}")
                continue
            _, x0, y0, rot, x1, y1 = best
            # The room that the part needs around itself: the track that
            # leaves a pin goes through it, so no pad of another part
            # may stand in it.  The room is around the pads of the
            # part, not around its body, because the body may be close
            # to the other parts.
            zone = None
            fp = board.FindFootprintByReference(ref)
            if fp is not None and FINE.get(ref):
                # The room is around the whole package, not around the
                # pads: the track that leaves a pin goes around the
                # package, and the parts that are next to the package
                # have to stay away from it.
                cxr = x0 + (x1 - x0) / 2
                cyr = y0 + (y1 - y0) / 2
                room = FINE[ref]
                zw, zh = (h, w) if rot == 90 else (w, h)
                zone = (cxr - zw / 2 - room, cyr - zh / 2 - room,
                        cxr + zw / 2 + room, cyr + zh / 2 + room)
            # The table holds the position of the origin of the
            # footprint, because that is what place() sets.  The packer
            # finds the room for the box of the part, and the origin is
            # not in the middle of that box when the pads of the part
            # are not symmetric around it.
            cx = x0 + (x1 - x0) / 2
            cy = y0 + (y1 - y0) / 2
            ox, oy = 0.0, 0.0
            if fp is not None:
                obb = fp.GetBoundingBox(False, False)
                ocx = pcbnew.ToMM((obb.GetLeft() + obb.GetRight()) / 2)
                ocy = pcbnew.ToMM((obb.GetTop() + obb.GetBottom()) / 2)
                op = fp.GetPosition()
                ox = pcbnew.ToMM(op.x) - ocx
                oy = pcbnew.ToMM(op.y) - ocy
                if rot == 90:
                    ox, oy = -oy, ox
            results[ref] = (round(cx + ox, 3), round(cy + oy, 3), rot)
            # The room that the part needs around itself is taken as
            # well, so that the parts that come after it keep away from
            # the pins: the track that leaves a pin goes through that
            # room.
            if zone is not None:
                placed.append(zone)
            else:
                placed.append((x0, y0, x1, y1))
            # the pads of the part that was just placed are obstacles for
            # the parts that come after it
            if fp is not None:
                for pad in fp.Pads():
                    pp = pad.GetPosition()
                    sz = pad.GetSize()
                    # the pad position is relative to the footprint, so
                    # the footprint position has to be taken into account
                    dx = pcbnew.ToMM(pp.x) - pcbnew.ToMM(fp.GetPosition().x)
                    dy = pcbnew.ToMM(pp.y) - pcbnew.ToMM(fp.GetPosition().y)
                    if rot == 90:
                        dx, dy = -dy, dx
                    pw = pcbnew.ToMM(sz.x)
                    ph = pcbnew.ToMM(sz.y)
                    if rot == 90:
                        pw, ph = ph, pw
                    px = cx + dx
                    py = cy + dy
                    placed_pads.append((ref,
                                        px - pw / 2, py - ph / 2,
                                        px + pw / 2, py + ph / 2))

    print("\n=== packed placement ===")
    for gname, ax, ay, parts in GROUPS:
        print(f"-- {gname} (anchor {ax},{ay})")
        for ref in parts:
            if ref in results:
                x, y, rot = results[ref]
                print(f"   {ref:5} ({x:8.3f},{y:8.3f}) rot={rot}")
            else:
                print(f"   {ref:5} -- NOT PLACED")

    out = os.path.join(HERE, "packed.json")
    with open(out, "w") as f:
        json.dump(results, f, indent=1)
    print(f"\nwrote {out}  ({len(results)} parts)")


import math

if __name__ == "__main__":
    main()
