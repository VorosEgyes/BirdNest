#!/usr/bin/env python3
"""
Merge the track fragments of the board.

The maze router plans the route as a list of grid cells, and the track
is written as the segments between the corners of that path.  A turn in
the path leaves a short piece behind - the tracks of a corner are two
segments that meet in a point, and the piece between them is shorter than
a tenth of a millimetre.

Those fragments are legal, but they are ugly: the manufacturer sees a
lot of tiny tracks, and the DRC reports some of them as dangling.

This script merges the tracks that lie on a straight line: two tracks of
the same net, on the same layer, that meet in a point and that continue
in the same direction become one track.  It runs over and over until
nothing changes any more.

CAUTION: the layout of the v2 board is copied over into the v3 board
with its track geometry, and that geometry is DRC clean.  Merging it can
only make it worse - the long track covers the whole length of both
tracks, and it may run over a third one.  So the merge is only useful on
a board that was routed from scratch.

Removing an item invalidates the SWIG wrapper of the board, so every
round works on a fresh copy of the board.

Run:  merge_tracks.py
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"

# tracks shorter than this are not worth merging
MIN_LEN = 0.2


def key(pt):
    return (pt.x, pt.y)


def direction(t):
    a = t.GetStart()
    b = t.GetEnd()
    dx = b.x - a.x
    dy = b.y - a.y
    if dx == 0 and dy == 0:
        return None
    return (0 if dx == 0 else (1 if dx > 0 else -1),
            0 if dy == 0 else (1 if dy > 0 else -1))


def overlaps(a, b, half):
    """Do the two tracks lie on top of each other?

    Two tracks of the same net may overlap - that is the same copper.
    But when they are merged, the long track covers the whole length of
    both, and it may run over a third one.
    """
    ax, ay = a.GetStart().x, a.GetStart().y
    bx, by = a.GetEnd().x, a.GetEnd().y
    cx, cy = b.GetStart().x, b.GetStart().y
    dx, dy = b.GetEnd().x, b.GetEnd().y
    # the distance between the two segments
    def dist(p, q, r):
        px, py = p
        qx, qy = q
        rx, ry = r
        vx, vy = qx - px, qy - py
        wx, wy = rx - px, ry - py
        c1 = vx * wx + vy * wy
        if c1 <= 0:
            return (px - rx) ** 2 + (py - ry) ** 2
        c2 = vx * vx + vy * vy
        if c2 <= c1:
            return (px - rx) ** 2 + (py - ry) ** 2
        t = c1 / c2
        return (px + t * vx - rx) ** 2 + (py + t * vy - ry) ** 2
    d2 = min(dist((ax, ay), (bx, by), (cx, cy)),
             dist((ax, ay), (bx, by), (dx, dy)),
             dist((cx, cy), (dx, dy), (ax, ay)),
             dist((cx, cy), (dx, dy), (bx, by)))
    return d2 < half * half


def hits_pad(track, pads):
    """Does the track run over a pad of another net?

    The distance between the segment and the rectangle of the pad has to
    be smaller than the half width of the track: then the copper of the
    track touches the copper of the pad.
    """
    a, e = track.GetStart(), track.GetEnd()
    ax, ay = pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)
    ex, ey = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
    half = pcbnew.ToMM(track.GetWidth()) / 2
    for (pnet, x0, y0, x1, y1) in pads:
        if pnet == track.GetNetname():
            continue
        # the closest point of the segment to the centre of the rectangle
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = ex - ax, ey - ay
        len2 = dx * dx + dy * dy
        if len2 == 0:
            t = 0.0
        else:
            t = ((cx - ax) * dx + (cy - ay) * dy) / len2
            t = max(0.0, min(1.0, t))
        px, py = ax + t * dx, ay + t * dy
        # the distance from the point to the rectangle
        ddx = max(x0 - px, 0, px - x1)
        ddy = max(y0 - py, 0, py - y1)
        if (ddx * ddx + ddy * ddy) ** 0.5 <= half:
            return True
    return False


def merge_round():
    """One round of merging.  Returns the number of merged tracks."""
    b = pcbnew.LoadBoard(V3)
    tracks = [t for t in b.GetTracks() if t.GetClass() != "PCB_VIA"]

    # the pads of the board, so that a merged track does not run over the
    # pad of another net
    pads = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            w = pcbnew.ToMM(p.GetSize().x)
            h = pcbnew.ToMM(p.GetSize().y)
            pads.append((p.GetNetname(),
                         pcbnew.ToMM(pos.x) - w / 2, pcbnew.ToMM(pos.y) - h / 2,
                         pcbnew.ToMM(pos.x) + w / 2, pcbnew.ToMM(pos.y) + h / 2))

    by_end = {}
    by_start = {}
    for t in tracks:
        by_end.setdefault(key(t.GetEnd()), []).append(t)
        by_start.setdefault(key(t.GetStart()), []).append(t)

    merged = 0
    dead = set()
    for t in tracks:
        if id(t) in dead:
            continue
        net = t.GetNetname()
        layer = t.GetLayer()
        width = t.GetWidth()
        d = direction(t)
        if d is None:
            continue
        # the track that continues at the end of this one
        for nxt in by_end.get(key(t.GetEnd()), []):
            if nxt is t or id(nxt) in dead:
                continue
            if nxt.GetNetname() != net or nxt.GetLayer() != layer:
                continue
            if nxt.GetWidth() != width:
                continue
            if direction(nxt) != d:
                continue
            # the merged track must not run over another track of another
            # net - that would be a short
            clash = False
            for other in tracks:
                if other is t or other is nxt or id(other) in dead:
                    continue
                if other.GetNetname() == net or other.GetLayer() != layer:
                    continue
                if overlaps(t, other, width / 2) or overlaps(nxt, other, width / 2):
                    clash = True
                    break
            if clash:
                continue
            # and it must not run over a pad of another net
            end = nxt.GetEnd()
            t.SetEnd(end)
            if hits_pad(t, pads):
                t.SetEnd(nxt.GetStart())
                continue
            dead.add(id(nxt))
            merged += 1
            break
        # and the track that continues at the start of this one
        if id(t) not in dead:
            for prv in by_start.get(key(t.GetStart()), []):
                if prv is t or id(prv) in dead:
                    continue
                if prv.GetNetname() != net or prv.GetLayer() != layer:
                    continue
                if prv.GetWidth() != width:
                    continue
                if direction(prv) != d:
                    continue
                clash = False
                for other in tracks:
                    if other is t or other is prv or id(other) in dead:
                        continue
                    if other.GetNetname() == net or other.GetLayer() != layer:
                        continue
                    if overlaps(prv, other, width / 2) or overlaps(t, other, width / 2):
                        clash = True
                        break
                if clash:
                    continue
                end = t.GetEnd()
                prv.SetEnd(end)
                if hits_pad(prv, pads):
                    prv.SetEnd(t.GetStart())
                    continue
                dead.add(id(t))
                merged += 1
                break

    if not merged:
        return 0

    # the tracks are collected again before the removal, because removing
    # an item invalidates the wrapper of the board
    victims = [t for t in b.GetTracks()
               if t.GetClass() != "PCB_VIA" and id(t) in dead]
    for t in victims:
        try:
            b.Remove(t)
        except Exception:
            pass
    pcbnew.SaveBoard(V3, b)
    return merged


def drop_slivers():
    """Remove the tracks that lie completely inside a pad.

    The centre of a pad is usually not on the grid of the router, so the
    track that leaves the pad starts a fraction of a millimetre next to
    the centre.  That sliver is of no use: the pad is connected by the
    track that leads away from it.
    """
    b = pcbnew.LoadBoard(V3)
    pads = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            pos = p.GetPosition()
            w = pcbnew.ToMM(p.GetSize().x)
            h = pcbnew.ToMM(p.GetSize().y)
            pads.append((p.GetNetname(),
                         pcbnew.ToMM(pos.x) - w / 2, pcbnew.ToMM(pos.y) - h / 2,
                         pcbnew.ToMM(pos.x) + w / 2, pcbnew.ToMM(pos.y) + h / 2))
    victims = []
    for t in b.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        if pcbnew.ToMM(t.GetLength()) >= 0.05:
            continue
        net = t.GetNetname()
        a = t.GetStart()
        b2 = t.GetEnd()
        ax, ay = pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)
        bx, by = pcbnew.ToMM(b2.x), pcbnew.ToMM(b2.y)
        inside = False
        for (pnet, x0, y0, x1, y1) in pads:
            if pnet != net:
                continue
            if (x0 <= ax <= x1 and y0 <= ay <= y1
                    and x0 <= bx <= x1 and y0 <= by <= y1):
                inside = True
                break
        if inside:
            victims.append(t)
    if not victims:
        return 0
    for t in victims:
        try:
            b.Remove(t)
        except Exception:
            pass
    pcbnew.SaveBoard(V3, b)
    return len(victims)


def main():
    total = 0
    for _ in range(20):
        n = merge_round()
        print(f"  merged {n} tracks")
        total += n
        if not n:
            break

    print(f"merged {total} tracks in total")

    # The slivers are dropped in a separate process: removing an item
    # invalidates the SWIG wrapper of the board, and the module keeps
    # handing out the broken wrapper afterwards.
    res = subprocess.run(
        [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "drop_slivers.py")],
        capture_output=True, text=True)
    for line in (res.stdout or "").splitlines():
        if line.startswith("dropped"):
            print(f"  {line}")

    b2 = pcbnew.LoadBoard(V3)
    short = [(t.GetNetname(), round(pcbnew.ToMM(t.GetLength()), 3))
             for t in list(b2.GetTracks())
             if t.GetClass() != "PCB_VIA"
             and 0 < pcbnew.ToMM(t.GetLength()) < MIN_LEN]
    print(f"{len(short)} tracks shorter than {MIN_LEN} mm are left:")
    for net, ln in short[:12]:
        print(f"   {net:18} {ln:.3f} mm")


if __name__ == "__main__":
    main()
