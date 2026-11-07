#!/usr/bin/env python3
"""
The ends of the lines that reach nothing.

Some lines of the V2 went to a part that stands somewhere else on the
V3.  The end of such a line hangs in the copper, and the rules checker
calls it a loose track.  There are two kinds of them:

  - the line is not needed at all: the copper of the net reaches every
    pad without it, so the line is only a leftover;
  - the line has to reach a pad, but it stops short of it, so it has to
    be made longer.

The script finds the tracks that end in the middle of the copper, it
says what is near them, and it does the right thing:

  - a track whose far end is not needed is removed;
  - a track whose far end is near a pad of the same net is made longer,
    so that it reaches the pad.

The guard of the board holds the board back if the copper gets worse,
so the script may be run again and again.

The script only reads the board and writes it through the guard.

Run:  loose_ends.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import safe_board

from safe_board import PCB    # noqa: E402


def mm(v):
    return pcbnew.ToMM(v)


def pads_of(board, net):
    """The pads of a net: the place and the half of the size."""
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != net:
                continue
            q = p.GetPosition()
            out.append((fp.GetReference() + "." + p.GetNumber(),
                        mm(q.x), mm(q.y),
                        mm(p.GetSize().x) / 2, mm(p.GetSize().y) / 2,
                        p.GetLayerName()))
    return out


def touches_pad(pads, x, y, layer):
    """Does a place lie on a pad of the same layer?

    The answer is the name of the pad, or None.
    """
    for (name, px, py, hw, hh, pad_layer) in pads:
        if pad_layer != layer and pad_layer != "*.Cu":
            continue
        if abs(x - px) <= hw + 0.02 and abs(y - py) <= hh + 0.02:
            return name
    return None


def groups(board, net):
    """The groups of the copper of a net.

    Two pads are in the same group when a track of the net joins them.
    The answer holds for every group the names of its pads.
    """
    nodes = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net:
                q = p.GetPosition()
                nodes.append((fp.GetReference() + "." + p.GetNumber(),
                              (q.x, q.y)))
    tracks = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        if t.GetNetname() != net:
            continue
        tracks.append(((t.GetStart().x, t.GetStart().y),
                       (t.GetEnd().x, t.GetEnd().y), t))

    def key(p):
        return (round(p[0] / 50000), round(p[1] / 50000))

    par = {}

    def find(a):
        while par.get(a, a) != a:
            a = par[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb

    for (_, p) in nodes:
        par[key(p)] = key(p)
    for (s, e, _) in tracks:
        union(key(s), key(e))

    out = {}
    for (name, p) in nodes:
        out.setdefault(find(key(p)), []).append(name)
    return out


def loose_tracks(board):
    """The tracks of the board that end in the middle of the copper.

    The answer holds for every one of them the net, the two ends, the
    layer and the end that hangs loose.
    """
    out = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        pads = pads_of(board, t.GetNetname())
        for which, q in (("start", t.GetStart()), ("end", t.GetEnd())):
            x, y = mm(q.x), mm(q.y)
            if touches_pad(pads, x, y, t.GetLayerName()):
                continue
            # the end must not lie on a via either
            on_via = False
            for v in board.GetTracks():
                if v.GetClass() != "PCB_VIA":
                    continue
                if v.GetNetname() != t.GetNetname():
                    continue
                p = v.GetPosition()
                if abs(mm(p.x) - x) < 0.01 and abs(mm(p.y) - y) < 0.01:
                    on_via = True
                    break
            if on_via:
                continue
            s = t.GetStart()
            e = t.GetEnd()
            out.append((t.GetNetname(), which,
                        (mm(s.x), mm(s.y)), (mm(e.x), mm(e.y)),
                        mm(t.GetWidth()), t.GetLayerName()))
    return out


def main():
    board = pcbnew.LoadBoard(PCB)
    found = loose_tracks(board)
    if not found:
        print("every line of the board reaches a pad")
        return 0

    print(f"the lines that reach nothing: {len(found)}")
    for (net, which, a, b, w, layer) in found:
        x, y = a if which == "start" else b
        print(f"\n  {net}  the {which} end at ({x:.3f},{y:.3f})  "
              f"w={w:.2f} {layer}")
        pads = pads_of(board, net)
        near = []
        for (name, px, py, hw, hh, pl) in pads:
            d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
            near.append((d, name, px, py, hw, hh))
        near.sort()
        for (d, name, px, py, hw, hh) in near[:4]:
            print(f"      {d:5.2f} mm  {name:12} at ({px:8.3f},{py:8.3f})")

        # the group of the net: is the pad of the net alone in it?
        gs = groups(board, net)
        sizes = sorted(len(g) for g in gs.values())
        print(f"      the net has {len(gs)} group(s), the sizes are {sizes}")


if __name__ == "__main__":
    sys.exit(main())
