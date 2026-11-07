#!/usr/bin/env python3
"""
The groups of the copper of a net.

A group is a piece of copper that reaches itself: the pads, the tracks
and the vias of the net, joined where they touch.  The answer is the
list of the groups, and for every group the pads that are in it.

Two lines that only meet at their ends belong to the same group: the
rules checker joins them.  But it says that such a line hangs loose,
when nothing else reaches the place where they meet.  So a line that
ends where another line ends has to go on, or a via has to stand in
the place.

The script only reads, it does not change anything.

Run:  copper_groups.py <net>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

import safe_board

from safe_board import PCB    # noqa: E402


def mm(v):
    return pcbnew.ToMM(v)


def key(p):
    """The place of a point, in the unit of the board.

    The unit is a nanometre, so two points that are the same place have
    the same key and two points that are a hair apart do not.
    """
    return (p.x, p.y)


def on_segment(p, a, b):
    """Does a point lie on a segment?"""
    (px, py) = p
    (ax, ay) = a
    (bx, by) = b
    cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
    if abs(cross) > 1000:
        return False
    dot = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    if dot < 0:
        return False
    length = (bx - ax) ** 2 + (by - ay) ** 2
    return dot <= length


def groups(board, net):
    """The groups of the copper of a net.

    The answer is a list of (the pads in the group, the number of the
    tracks in it).
    """
    par = {}

    def find(a):
        while par.get(a, a) != a:
            a = par[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb

    pads = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != net:
                continue
            q = p.GetPosition()
            k = key(q)
            par[k] = k
            pads.append((fp.GetReference() + "." + p.GetNumber(),
                         k, mm(q.x), mm(q.y)))

    tracks = 0
    segs = []
    for t in board.GetTracks():
        if t.GetNetname() != net:
            continue
        if t.GetClass() == "PCB_VIA":
            # the via stands at one place: it joins whatever ends
            # there
            k = key(t.GetPosition())
            if k not in par:
                par[k] = k
            tracks += 1
            continue
        a = key(t.GetStart())
        c = key(t.GetEnd())
        for k in (a, c):
            if k not in par:
                par[k] = k
        union(a, c)
        segs.append((a, c, t.GetLayer()))
        tracks += 1

    # A track that ends in the middle of another track is joined to it:
    # the rules checker joins them, and so does this script.
    for (a, c, layer) in segs:
        for (b, d, other) in segs:
            if other != layer:
                continue
            if b == a or b == c or d == a or d == c:
                continue
            if on_segment(a, b, d) or on_segment(c, b, d):
                union(a, b)
            if on_segment(b, a, c) or on_segment(d, a, c):
                union(a, b)

    out = {}
    for (name, k, x, y) in pads:
        out.setdefault(find(k), []).append(name)
    return out, tracks


def main():
    net = sys.argv[1] if len(sys.argv) > 1 else "/BAT_PROT+"
    board = pcbnew.LoadBoard(PCB)
    gs, tracks = groups(board, net)
    print(f"the net {net}: {len(gs)} group(s), {tracks} tracks")
    for g, pads in sorted(gs.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(pads):2} pad(s): {', '.join(sorted(pads))}")
    if len(gs) > 1:
        print("\n  the net is not closed: the groups above have to be joined")


if __name__ == "__main__":
    main()
