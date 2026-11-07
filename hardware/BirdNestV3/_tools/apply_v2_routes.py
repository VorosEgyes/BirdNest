#!/usr/bin/env python3
"""
Copy the routing of the v2 board over to v3.

The v2 board is a finished, DRC clean layout of the same circuit.  The 30
components that exist in both boards sit at the same place, so the track
geometry of the v2 board is still valid on the v3 board and does not have
to be routed again.

The two boards do not use the same net names: v2 called the battery rail
/BAT_RAW where v3 splits it into /BAT_CELL+ and /BAT_PROT+.  The mapping
is derived by comparing the pads that carry the net in both boards (see
v2_routes.py).

Before the tracks are copied, the tracks that are already on the v3 board
are removed, so that the v2 geometry is not mixed with a previous routing
attempt.  The nets that are not covered by the mapping are left to the
maze router.

Run:  apply_v2_routes.py
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

from v2_routes import V2, V3, build_mapping


def main():
    mapping = build_mapping()
    print(f"{len(mapping)} nets are mapped from v2 to v3")

    b2 = pcbnew.LoadBoard(V2)
    b3 = pcbnew.LoadBoard(V3)

    # the net objects of the v3 board
    v3nets = {}
    for code, ni in b3.GetNetsByNetcode().items():
        v3nets[ni.GetNetname()] = ni

    # remove the existing routing of the v3 board
    victims = [t for t in b3.GetTracks()]
    for t in victims:
        try:
            b3.Remove(t)
        except Exception:
            pass
    print(f"removed {len(victims)} existing tracks/vias")

    copied = 0
    skipped = defaultdict(int)
    for t in b2.GetTracks():
        v2net = t.GetNetname()
        # find the v3 net this track belongs to
        target = None
        for v3net, src in mapping.items():
            if src == v2net:
                target = v3net
                break
        if target is None:
            skipped[v2net] += 1
            continue
        ni = v3nets.get(target)
        if ni is None:
            skipped[v2net] += 1
            continue
        if t.GetClass() == "PCB_VIA":
            v = pcbnew.PCB_VIA(b3)
            v.SetPosition(t.GetPosition())
            v.SetWidth(t.GetWidth())
            v.SetDrill(t.GetDrill())
            v.SetViaType(t.GetViaType())
            v.SetLayerPair(t.TopLayer(), t.BottomLayer())
            v.SetNet(ni)
            b3.Add(v)
        else:
            nt = pcbnew.PCB_TRACK(b3)
            nt.SetStart(t.GetStart())
            nt.SetEnd(t.GetEnd())
            nt.SetWidth(t.GetWidth())
            nt.SetLayer(t.GetLayer())
            nt.SetNet(ni)
            b3.Add(nt)
        copied += 1

    print(f"copied {copied} tracks/vias from the v2 layout")
    if skipped:
        print("not copied (no unambiguous mapping):")
        for net, n in sorted(skipped.items()):
            print(f"  {net:24} {n:3}")

    pcbnew.SaveBoard(V3, b3)
    print("saved")


if __name__ == "__main__":
    main()
