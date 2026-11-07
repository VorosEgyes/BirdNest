#!/usr/bin/env python3
"""
Check the routing against the router's own keep-out model.

For every track on the board the script rebuilds the keep-out mask of its
net and looks for cells that are inside the mask but carry the track's
copper.  Those are the places where the router violated its own model -
and they are the places the DRC complains about.

Run:  verify_route.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

import maze4


def main():
    board = pcbnew.LoadBoard(maze4.V3)
    r = maze4.Router(board)
    for net in r.nets.values():
        clr, width = r._params(net.name)
        net.clearance = clr
        net.halfwidth = width / 2

    # rebuild the masks the way the router did: net by net, in the order
    # it used, each mask built from the copper that existed at that time
    print("checking the routed tracks against the keep-out model\n")

    total = 0
    for net in r.nets.values():
        if not net.tracks[0] and not net.tracks[1]:
            continue
        masks = r.build_mask(net)
        # the net's own tracks are part of its own keep-out (that is what
        # keeps them from crossing), so they have to be excluded here
        own = [set() for _ in maze4.LAYERS]
        for li in range(len(maze4.LAYERS)):
            for y, rbits in enumerate(net.tracks[li]):
                if not rbits:
                    continue
                base = y * maze4.NX
                x = 0
                while rbits:
                    low = rbits & -rbits
                    x = low.bit_length() - 1
                    own[li].add(base + x)
                    rbits ^= low
        bad = 0
        detail = []
        for li in range(len(maze4.LAYERS)):
            rows = net.cu[li]
            for y, rbits in enumerate(rows):
                if not rbits:
                    continue
                m = masks[li]
                base = y * maze4.NX
                x = 0
                while rbits:
                    low = rbits & -rbits
                    x = low.bit_length() - 1
                    if m[base + x] and (base + x) not in own[li]:
                        bad += 1
                        if len(detail) < 3:
                            detail.append((x, y))
                    rbits ^= low
        if bad:
            total += bad
            print(f"  {net.name:24} {bad:5} cells inside the keep-out"
                  f"   e.g. {detail}")
    print(f"\ntotal: {total} cells of routed copper inside a keep-out")


if __name__ == "__main__":
    main()
