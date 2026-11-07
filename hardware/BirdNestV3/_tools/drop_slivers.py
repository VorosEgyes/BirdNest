#!/usr/bin/env python3
"""
Remove the tracks that lie completely inside a pad.

The centre of a pad is usually not on the grid of the router, so the
track that leaves the pad starts a fraction of a millimetre next to the
centre.  That sliver is of no use: the pad is connected by the track
that leads away from it.

This runs as its own process because removing an item invalidates the
SWIG wrapper of the board.

Run:  drop_slivers.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"
MAX_LEN = 0.05


def main():
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
    for t in list(b.GetTracks()):
        if t.GetClass() == "PCB_VIA":
            continue
        if pcbnew.ToMM(t.GetLength()) >= MAX_LEN:
            continue
        net = t.GetNetname()
        a = t.GetStart()
        e = t.GetEnd()
        ax, ay = pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)
        bx, by = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
        for (pnet, x0, y0, x1, y1) in pads:
            if pnet != net:
                continue
            if (x0 <= ax <= x1 and y0 <= ay <= y1
                    and x0 <= bx <= x1 and y0 <= by <= y1):
                victims.append(t)
                break

    for t in victims:
        try:
            b.Remove(t)
        except Exception:
            pass
    pcbnew.SaveBoard(V3, b)
    print(f"dropped {len(victims)} slivers inside the pads")


if __name__ == "__main__":
    main()
