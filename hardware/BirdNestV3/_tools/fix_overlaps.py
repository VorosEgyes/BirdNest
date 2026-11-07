#!/usr/bin/env python3
"""
Move the tracks that run over a pad of another net.

The maze router cannot always find a way around a pad that is only a
millimetre wide - the track has to cross the pad to get out of it, and
the DRC then reports an overlap.

This script does the same by hand.  For every track that runs over a
foreign pad it tries to shift the track parallel to itself until it
clears the pad.  The shift is tried in both directions and in steps of a
tenth of a millimetre, and the first shift that clears the pad and keeps
the clearance to the other copper is taken.

The track is only moved when the whole track can be moved - a track that
has to be shortened would break the net.

Run:  fix_overlaps.py [--dry]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import safe_board    # noqa: E402  the guard of the board

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"


def to_mm(v):
    return pcbnew.ToMM(v)


def mm(v):
    return int(round(v * 1e6))


def pad_rect(pad):
    pos = pad.GetPosition()
    w = to_mm(pad.GetSize().x)
    h = to_mm(pad.GetSize().y)
    x = to_mm(pos.x)
    y = to_mm(pos.y)
    return (x - w / 2, y - h / 2, x + w / 2, y + h / 2)


def segment_hits_rect(a, b, r, half):
    """Does the segment a-b with the half width `half` touch the
    rectangle r?"""
    x0, y0, x1, y1 = r
    # the rectangle grown by the half width
    x0 -= half
    y0 -= half
    x1 += half
    y1 += half
    # the segment as a slab: use the bounding box of the segment and the
    # rectangle, then check the distance from the segment to the centre
    ax, ay = a
    bx, by = b
    dx = bx - ax
    dy = by - ay
    len2 = dx * dx + dy * dy
    cx = min(max((x0 + x1) / 2, min(ax, bx)), max(ax, bx))
    cy = min(max((y0 + y1) / 2, min(ay, by)), max(ay, by))
    if len2 == 0:
        d = ((ax - cx) ** 2 + (ay - cy) ** 2) ** 0.5
    else:
        t = ((cx - ax) * dx + (cy - ay) * dy) / len2
        t = max(0.0, min(1.0, t))
        px = ax + t * dx
        py = ay + t * dy
        d = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
    # the distance from the segment to the rectangle
    dxr = max(x0 - cx, 0, cx - x1)
    dyr = max(y0 - cy, 0, cy - y1)
    dist = (dxr * dxr + dyr * dyr) ** 0.5
    return dist <= half + 1e-9, dist


def main():
    dry = "--dry" in sys.argv
    b = pcbnew.LoadBoard(V3)

    pads = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        for p in fp.Pads():
            pls = set()
            for l in (pcbnew.F_Cu, pcbnew.B_Cu):
                if p.IsOnLayer(l):
                    pls.add(l)
            pads.append((ref, p.GetNumber(), p.GetNetname(),
                         pad_rect(p), pls))

    # the copper of every net, for the clearance check
    other = []
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        for p in fp.Pads():
            pls = set()
            for l in (pcbnew.F_Cu, pcbnew.B_Cu):
                if p.IsOnLayer(l):
                    pls.add(l)
            other.append((p.GetNetname(), pad_rect(p), pls))
    for t in b.GetTracks():
        a = t.GetStart()
        e = t.GetEnd()
        ax, ay = to_mm(a.x), to_mm(a.y)
        ex, ey = to_mm(e.x), to_mm(e.y)
        half = to_mm(t.GetWidth()) / 2
        other.append((t.GetNetname(),
                      (min(ax, ex) - half, min(ay, ey) - half,
                       max(ax, ex) + half, max(ay, ey) + half),
                      {t.GetLayer()}))

    # the pads of every net, by their end points
    pad_ends = {}
    for (ref, num, pnet, r, pls) in pads:
        pad_ends.setdefault(pnet, []).append(
            ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, r))

    def on_pad(x, y, pnet):
        """Is the point on a pad of the net?  A track that is shifted has
        to keep touching its own pad, otherwise the net is broken."""
        for (px, py, r) in pad_ends.get(pnet, []):
            if r[0] - 0.3 <= x <= r[2] + 0.3 and r[1] - 0.3 <= y <= r[3] + 0.3:
                return True
        return False

    # the biggest shift that keeps the track on its own pads
    MAX_SHIFT = 0.35

    moved = 0
    for t in list(b.GetTracks()):
        net = t.GetNetname()
        if not net or t.GetClass() == "PCB_VIA":
            continue
        a = t.GetStart()
        e = t.GetEnd()
        ax, ay = to_mm(a.x), to_mm(a.y)
        ex, ey = to_mm(e.x), to_mm(e.y)
        half = to_mm(t.GetWidth()) / 2
        layer = t.GetLayer()

        # the foreign pads the track runs over
        hits = []
        for (ref, num, pnet, r, pls) in pads:
            if pnet == net or layer not in pls:
                continue
            bad, dist = segment_hits_rect((ax, ay), (ex, ey), r, half)
            if bad:
                hits.append((ref, num, pnet, r, dist))
        if not hits:
            continue

        # the track has to touch its own pads at both ends, otherwise it
        # cannot be shifted
        if not (on_pad(ax, ay, net) and on_pad(ex, ey, net)):
            print(f"{net}: track ({ax:.2f},{ay:.2f})->({ex:.2f},{ey:.2f}) "
                  f"over {hits[0][0]}.{hits[0][1]} [{hits[0][2]}] "
                  f"- not anchored on its own pads")
            continue

        # try to shift the track parallel to itself
        dx = ex - ax
        dy = ey - ay
        length = (dx * dx + dy * dy) ** 0.5
        if length < 0.05:
            continue
        # the normal of the segment
        nx, ny = -dy / length, dx / length

        best = None
        steps = int(MAX_SHIFT / 0.1)
        for step in range(1, steps + 1):
            for sign in (1, -1):
                off = step * 0.1 * sign
                na = (ax + nx * off, ay + ny * off)
                ne = (ex + nx * off, ey + ny * off)
                # does it still hit one of the pads?
                still = False
                for (ref, num, pnet, r, dist) in hits:
                    bad, _ = segment_hits_rect(na, ne, r, half)
                    if bad:
                        still = True
                        break
                if still:
                    continue
                # does it still touch its own pads?
                if not (on_pad(na[0], na[1], net)
                        and on_pad(ne[0], ne[1], net)):
                    continue
                # does it hit any other copper?
                clash = False
                for (onet, r2, pls2) in other:
                    if onet == net or layer not in pls2:
                        continue
                    bad, _ = segment_hits_rect(na, ne, r2, half)
                    if bad:
                        clash = True
                        break
                if clash:
                    continue
                best = (na, ne, off)
                break
            if best:
                break

        if not best:
            print(f"{net}: track ({ax:.2f},{ay:.2f})->({ex:.2f},{ey:.2f}) "
                  f"over {hits[0][0]}.{hits[0][1]} [{hits[0][2]}] "
                  f"- no free shift found")
            continue

        na, ne, off = best
        print(f"{net}: track ({ax:.2f},{ay:.2f})->({ex:.2f},{ey:.2f}) "
              f"over {hits[0][0]}.{hits[0][1]} [{hits[0][2]}] "
              f"-> shifted by {off:+.2f} mm")
        t.SetStart(pcbnew.VECTOR2I(mm(na[0]), mm(na[1])))
        t.SetEnd(pcbnew.VECTOR2I(mm(ne[0]), mm(ne[1])))
        moved += 1

    print(f"\nshifted {moved} tracks")
    if not dry:
        safe_board.save(b, "the fix of the overlaps")
        print("saved")


if __name__ == "__main__":
    main()
