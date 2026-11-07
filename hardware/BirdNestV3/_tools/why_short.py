#!/usr/bin/env python3
"""
Find out WHY the router violated the clearance.

For every track on the board the script rebuilds the keep-out mask of its
net and reports the cells of the track that lie inside the mask.  For
each such cell it then reports

  * which foreign net owns the copper that blocks the cell,
  * whether the cell is inside the mask of that net at all.

If the blocking net is not found, the mask is wrong.  If it is found but
the cell is not inside its mask, the mask of that net is incomplete.

Run:  why_short.py [net name]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

import maze4


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    board = pcbnew.LoadBoard(maze4.V3)
    r = maze4.Router(board)
    for net in r.nets.values():
        clr, width = r._params(net.name)
        net.clearance = clr
        net.halfwidth = width / 2

    # the copper of every net, cell by cell, for the reverse lookup
    owner = [dict() for _ in maze4.LAYERS]
    for net in r.nets.values():
        for li in range(len(maze4.LAYERS)):
            for y, rbits in enumerate(net.cu[li]):
                if not rbits:
                    continue
                x = 0
                while rbits:
                    low = rbits & -rbits
                    x = low.bit_length() - 1
                    owner[li][(y, x)] = net.name
                    rbits ^= low
    for y, rbits in enumerate(r.obstacle.cu[0]):
        if not rbits:
            continue
        x = 0
        while rbits:
            low = rbits & -rbits
            x = low.bit_length() - 1
            owner[0][(y, x)] = "GND-pad"
            rbits ^= low

    for net in r.nets.values():
        if only and net.name != only:
            continue
        if not net.tracks[0] and not net.tracks[1]:
            continue
        masks = r.build_mask(net)

        # the centre lines of this net's own tracks
        own = [set(), set()]
        for li in range(len(maze4.LAYERS)):
            for y, rbits in enumerate(net.tracks[li]):
                if not rbits:
                    continue
                x = 0
                while rbits:
                    low = rbits & -rbits
                    x = low.bit_length() - 1
                    own[li].add((y, x))
                    rbits ^= low

        reported = 0
        for li in range(len(maze4.LAYERS)):
            for y, rbits in enumerate(net.cu[li]):
                if not rbits:
                    continue
                x = 0
                while rbits:
                    low = rbits & -rbits
                    x = low.bit_length() - 1
                    cell = (y, x)
                    if not masks[li][y * maze4.NX + x]:
                        rbits ^= low
                        continue
                    if cell in own[li]:
                        rbits ^= low
                        continue
                    # who is the foreign copper around here?
                    blockers = set()
                    for dy in range(-6, 7):
                        for dx in range(-6, 7):
                            other = owner[li].get((y + dy, x + dx))
                            if other and other != net.name:
                                blockers.add(other)
                    print(f"  {net.name:22} cell {cell} layer {li} "
                          f"blocked by {sorted(blockers)}")
                    reported += 1
                    if reported >= 4:
                        break
                    rbits ^= low
                if reported >= 4:
                    break
            if reported >= 4:
                break
        if reported:
            print()


if __name__ == "__main__":
    main()
