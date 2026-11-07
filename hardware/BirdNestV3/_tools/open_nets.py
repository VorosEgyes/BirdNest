#!/usr/bin/env python3
"""
What is still open on the board, and what did the V2 do about it.

The script looks at the board of the V3 and at the board of the V2,
and it writes for every net that is still open:

  - the pads of it and where they stand,
  - the pieces of track that it has, and which pads they reach,
  - the pieces of track of the V2 of the same net, if the net has the
    same name there, because the V2 is a board that works.

It writes the tracks that hang loose too, with the pads that are near
them, because they are the ends of the lines of the V2 that no longer
reach anything.

The script only reads, it does not change anything.

Run:  open_nets.py
"""
import os
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
V3 = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")
V2 = os.path.join(os.path.dirname(HERE), "..", "BirdNest_pcb",
                   "BirdNest_pcb.kicad_pcb")
V2 = os.path.abspath(V2)


def mm(v):
    return pcbnew.ToMM(v)


def pads_of(board, net):
    """The pads of a net: the name of the part, the place and the size."""
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() != net:
                continue
            q = p.GetPosition()
            out.append((fp.GetReference() + "." + p.GetNumber(),
                        mm(q.x), mm(q.y),
                        mm(p.GetSize().x), mm(p.GetSize().y),
                        p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH,
                        p.GetLayerName()))
    return out


def tracks_of(board, net):
    """The tracks of a net: the two ends and the width."""
    out = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        if t.GetNetname() != net:
            continue
        s = t.GetStart()
        e = t.GetEnd()
        out.append((mm(s.x), mm(s.y), mm(e.x), mm(e.y),
                    mm(t.GetWidth()), t.GetLayerName()))
    return out


def vias_of(board, net):
    out = []
    for t in board.GetTracks():
        if t.GetClass() != "PCB_VIA":
            continue
        if t.GetNetname() != net:
            continue
        q = t.GetPosition()
        out.append((mm(q.x), mm(q.y), mm(t.GetWidth())))
    return out


def net_names(board):
    names = []
    for n in board.GetNetInfo().NetsByNetcode().keys():
        names.append(board.FindNet(n).GetNetname())
    return set(names)


def near_pads(board, x, y, limit=4.0):
    """The pads that are near a place."""
    out = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            q = p.GetPosition()
            d = ((mm(q.x) - x) ** 2 + (mm(q.y) - y) ** 2) ** 0.5
            if d < limit:
                out.append((d, fp.GetReference() + "." + p.GetNumber(),
                            p.GetNetname()))
    return sorted(out)


def loose_tracks(board):
    """The tracks of the board that reach no pad at one of their ends.

    A track that ends in the middle of the copper is a leftover of the
    layout of the V2: it went to a part that stands elsewhere now.
    """
    out = []
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            continue
        for which, q in (("start", t.GetStart()), ("end", t.GetEnd())):
            x, y = mm(q.x), mm(q.y)
            pads = near_pads(board, x, y, 0.5)
            if not pads:
                s = t.GetStart()
                e = t.GetEnd()
                out.append((t.GetNetname(), which,
                            mm(s.x), mm(s.y), mm(e.x), mm(e.y),
                            mm(t.GetWidth()), t.GetLayerName(),
                            near_pads(board, x, y, 6.0)))
    return out


def near(a, b, limit):
    """Are two places within the limit of each other?"""
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 < limit


def main():
    v3 = pcbnew.LoadBoard(V3)
    v2 = pcbnew.LoadBoard(V2) if os.path.exists(V2) else None
    names2 = net_names(v2) if v2 else set()

    # the nets that are open: they are found from the report of the
    # rules checker, if it is there, and from the pads that no track
    # reaches
    open_nets = []
    for net in sorted(net_names(v3)):
        pads = pads_of(v3, net)
        if not pads:
            continue
        tracks = tracks_of(v3, net)
        # a pad that no track reaches: the net is open
        for (name, px, py, w, h, thru, layer) in pads:
            reached = False
            for (ax, ay, bx, by, tw, tl) in tracks:
                if near((ax, ay), (px, py), 0.35) or \
                   near((bx, by), (px, py), 0.35):
                    reached = True
                    break
            if not reached:
                open_nets.append(net)
                break

    print("the nets that are open on the V3:")
    for net in open_nets:
        print(f"\n=== {net} ===")
        print("  the pads:")
        for (name, x, y, w, h, thru, layer) in pads_of(v3, net):
            kind = "PTH" if thru else layer
            print(f"    {name:10} ({x:8.3f},{y:8.3f}) {w:5.2f}x{h:5.2f} {kind}")
        print("  the tracks:")
        for (ax, ay, bx, by, w, layer) in tracks_of(v3, net):
            print(f"    ({ax:8.3f},{ay:8.3f}) -> ({bx:8.3f},{by:8.3f}) "
                  f"w={w:.2f} {layer}")
        for (x, y, w) in vias_of(v3, net):
            print(f"    a via at ({x:8.3f},{y:8.3f}) w={w:.2f}")
        if v2 and net in names2:
            print("  the tracks of the V2:")
            for (ax, ay, bx, by, w, layer) in tracks_of(v2, net):
                print(f"    ({ax:8.3f},{ay:8.3f}) -> ({bx:8.3f},{by:8.3f}) "
                      f"w={w:.2f} {layer}")
            print("  the pads of the V2:")
            for (name, x, y, w, h, thru, layer) in pads_of(v2, net):
                print(f"    {name:10} ({x:8.3f},{y:8.3f})")

    print("\n\nthe tracks that hang loose:")
    for (net, which, ax, ay, bx, by, w, layer, pads) in loose_tracks(v3):
        print(f"  {net:16} the {which} end of "
              f"({ax:8.3f},{ay:8.3f}) -> ({bx:8.3f},{by:8.3f}) w={w:.2f} {layer}")
        for (d, name, n) in pads[:5]:
            print(f"      {d:5.2f} mm  {name:12} ({n})")


if __name__ == "__main__":
    main()
