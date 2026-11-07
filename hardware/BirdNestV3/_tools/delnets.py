#!/usr/bin/env python3
"""
Remove every track and via of the given nets from the v3 board.

This runs as its own process on purpose: removing an item from a board
invalidates the SWIG wrapper of that board, and in KiCad 9 a second
LoadBoard in the same process then returns an unusable object.  Running
the removal in a fresh interpreter avoids the problem completely.

Usage:  delnets.py <net> [<net> ...] [--force]

The guard holds the board back when the removal made it worse.  The
removal of the copper of a net always opens the net, so the guard
throws it away.  The scripts that remove the copper on purpose, to
draw it again, say --force.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import safe_board

from safe_board import PCB    # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv[1:]
    nets = set(args)
    if not nets:
        print("no net given")
        return 1

    board = pcbnew.LoadBoard(PCB)
    victims = []
    for t in list(board.GetTracks()):
        if t.GetNetname() in nets:
            victims.append(t)
    for t in victims:
        try:
            board.Remove(t)
        except Exception:
            pass
    # The guard puts the board back when the removal made it worse.
    # The removal of the copper of a net always opens the net, so the
    # guard throws it away; --force says that the removal is meant.
    kept = safe_board.save(board,
                            f"the removal of the tracks of {sorted(nets)}",
                            force=force)
    print(f"removed {len(victims)} tracks/vias")
    if not kept:
        print("the guard put the board back: the removal was thrown away")
        return 0

    # verify - a fresh process is not needed here, the file was written
    check = pcbnew.LoadBoard(PCB)
    left = [t for t in list(check.GetTracks()) if t.GetNetname() in nets]
    if left:
        print(f"ERROR: {len(left)} tracks survived")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
