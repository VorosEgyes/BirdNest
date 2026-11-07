#!/usr/bin/env python3
"""Remove every track and via of a net in one go, in a process of its own.

delitem.py removes one item at a time and writes the board after every
removal.  That is slow, and it confuses KiCad when the net has only one
pad left: the copper that is left over then changes its name, and the
new route does not fit any more.  This script takes the whole copper of
the net away at once and writes the board once.

Usage:  delall.py <net>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import safe_board

from safe_board import PCB    # noqa: E402


def main():
    if len(sys.argv) < 2:
        print("usage: delall.py <net>")
        return 1
    net = sys.argv[1]
    b = pcbnew.LoadBoard(PCB)
    victim = None
    n = 0
    for t in list(b.GetTracks()):
        if t.GetNetname() != net:
            continue
        if victim is None:
            victim = t
        b.Remove(t)
        n += 1
    if victim is None:
        print(f"there is no copper of the {net} net")
        return 0
    safe_board.save(b, f"the removal of the copper of the {net} net",
                    force=True)
    print(f"removed {n} items of the {net} net")
    return 0


if __name__ == "__main__":
    sys.exit(main())
