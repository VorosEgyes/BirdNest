#!/usr/bin/env python3
"""
Copy the routing of the v2 board over to v3.

The v2 board is a finished, DRC clean layout of the same circuit.  The 30
components that exist in both boards sit at the same place, so the track
geometry of the v2 board is still valid on the v3 board and does not have
to be routed again.

The two boards do not use the same net names: v2 called the battery rail
/BAT_RAW where v3 splits it into /BAT_CELL+ and /BAT_PROT+.  The mapping
is derived by comparing the pads that carry the net in both boards.

Only the nets whose mapping is unambiguous are copied.  Everything else is
left to the maze router.

Run:  v2_routes.py            # report the mapping
      apply_v2_routes.py      # copy the tracks into the v3 board
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V2 = "/Users/modmj/dev/BirdNest/hardware/BirdNest_pcb/BirdNest_pcb.kicad_pcb"
V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"


def pad_map(board):
    out = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        for pad in fp.Pads():
            out[(ref, pad.GetNumber())] = pad.GetNetname()
    return out


def build_mapping():
    """v3 net name -> the v2 net whose tracks can be copied for it."""
    b2 = pcbnew.LoadBoard(V2)
    b3 = pcbnew.LoadBoard(V3)
    m2 = pad_map(b2)
    m3 = pad_map(b3)

    v2_pads = defaultdict(list)
    for (ref, num), net in m2.items():
        if net and not net.startswith("unconnected-"):
            v2_pads[net].append((ref, num))

    mapping = {}
    for net, pads in sorted(v2_pads.items()):
        v3nets = defaultdict(list)
        for (ref, num) in pads:
            n3 = m3.get((ref, num))
            if n3 and not n3.startswith("unconnected-"):
                v3nets[n3].append((ref, num))
        if not v3nets:
            continue
        ranked = sorted(v3nets.items(), key=lambda kv: -len(kv[1]))
        best, bestpads = ranked[0]
        others = [(n, len(p)) for n, p in ranked[1:]]
        # accept when the names are identical, or when the best match has
        # strictly more pads than the runner up
        if best == net or not others or others[0][1] < len(bestpads):
            mapping[best] = net
    return mapping


def main():
    mapping = build_mapping()
    b2 = pcbnew.LoadBoard(V2)
    b3 = pcbnew.LoadBoard(V3)

    # how many tracks does every mapping bring?
    counts = defaultdict(int)
    for t in b2.GetTracks():
        counts[t.GetNetname()] += 1

    print("v3 net                 <- v2 net           tracks")
    total = 0
    for v3net, v2net in sorted(mapping.items()):
        n = counts.get(v2net, 0)
        total += n
        print(f"{v3net:24} <- {v2net:18} {n:4}")
    print(f"\n{total} tracks can be copied")

    with open("/tmp/v2_routes.json", "w") as fh:
        json.dump(mapping, fh, indent=1)


if __name__ == "__main__":
    main()
