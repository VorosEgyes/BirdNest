#!/usr/bin/env python3
"""
Report which nets still need routing, grouped by net and by the pads that
have to be connected.  This tells us what the auto-router could not solve
and therefore what has to be routed by hand.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"


def main():
    board = pcbnew.LoadBoard(V3)

    # collect pads per net
    pads = defaultdict(list)
    for fp in board.GetFootprints():
        if not fp.GetReference():
            continue
        for pad in fp.Pads():
            net = pad.GetNetname()
            if not net:
                continue
            p = pad.GetPosition()
            pads[net].append((fp.GetReference(), pad.GetNumber(),
                              pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)))

    # collect track endpoints per net
    seg = defaultdict(list)
    for t in board.GetTracks():
        net = t.GetNetname()
        if not net:
            continue
        a = t.GetStart()
        b = t.GetEnd()
        seg[net].append((pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                          pcbnew.ToMM(b.x), pcbnew.ToMM(b.y)))

    print("=== nets with pads but no routing ===")
    total = 0
    for net in sorted(pads):
        if net.startswith("unconnected-"):
            continue
        if net == "GND":
            continue          # GND is carried by the zone
        if seg.get(net):
            continue
        pl = pads[net]
        total += len(pl)
        coords = ", ".join(f"{r}.{n}@({x:.1f},{y:.1f})" for r, n, x, y in pl)
        print(f"  {net:24} {len(pl):2} pads: {coords}")
    print(f"\ntotal un-routed pad count (non-GND): {total}")


if __name__ == "__main__":
    main()
