#!/usr/bin/env python3
"""
Remove the tracks and the vias that match a net and a place.

Removing an item invalidates the SWIG wrapper of the board, and the
module keeps handing out the broken wrapper afterwards.  The only way
around it is a fresh process for every removal, so that is what this
script does: it takes the board, a net name and a point, removes the
tracks and the vias of that net that touch the point, and exits.

The work is saved after every removal, so the script can be stopped at
any time without leaving the board in a half written state.

The removal is meant: the copper of the net is drawn again afterwards.
So the guard of the board does not hold it back.

Usage:  delitem.py <net> <x> <y> [x2 y2]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import safe_board

from safe_board import PCB    # noqa: E402


def near(p, x, y):
    return (abs(pcbnew.ToMM(p.x) - x) < 0.01
            and abs(pcbnew.ToMM(p.y) - y) < 0.01)


def save(board, net, kind):
    """Write the board.

    The removal is meant: the copper of the net is drawn again
    afterwards.  So the guard of the board does not hold it back.
    """
    safe_board.save(board, f"the removal of a {kind} of the {net} net",
                    force=True)


def main():
    if len(sys.argv) < 2:
        print("usage: delitem.py <net> <x> <y> [x2 y2]")
        print("       delitem.py <net> next [x0 y0 x1 y1]")
        print("         next removes the first item of the net that is inside")
        print("         the box, the box is optional")
        return 1
    net = sys.argv[1]

    if len(sys.argv) >= 3 and sys.argv[2] == "next":
        # Remove the first track or via of the net.  The removal is done
        # in a process of its own: removing an item invalidates the
        # wrapper of the board, and the module keeps handing out the
        # broken wrapper afterwards.  So this script finds the item in
        # a fresh board, removes it there, and the caller repeats the
        # call until there is nothing left.
        #
        # The box limits the search to a part of the board: a net can
        # have tracks far away, and those have to stay.
        box = None
        if len(sys.argv) >= 7:
            box = tuple(float(v) for v in sys.argv[3:7])

        b = pcbnew.LoadBoard(PCB)
        victim = None
        for t in list(b.GetTracks()):
            if t.GetNetname() != net:
                continue
            if box is not None:
                inside = False
                for p in (t.GetStart(), t.GetEnd()):
                    px, py = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
                    if (box[0] <= px <= box[2] and box[1] <= py <= box[3]):
                        inside = True
                        break
                if not inside:
                    continue
            victim = t
            break
        if victim is None:
            return 0
        kind = victim.GetClass()
        a = victim.GetStart()
        e = victim.GetEnd()
        b.Remove(victim)
        # the removal is meant: the copper of the net is drawn again
        # afterwards, so the guard does not hold the board back
        save(b, net, kind)
        if kind == "PCB_VIA":
            print(f"removed a via of the {net} net at "
                  f"({pcbnew.ToMM(a.x):.4f},{pcbnew.ToMM(a.y):.4f})")
        else:
            print(f"removed a track of the {net} net from "
                  f"({pcbnew.ToMM(a.x):.4f},{pcbnew.ToMM(a.y):.4f}) to "
                  f"({pcbnew.ToMM(e.x):.4f},{pcbnew.ToMM(e.y):.4f})")
        return 1

    if len(sys.argv) < 4:
        print("usage: delitem.py <net> <x> <y> [x2 y2]")
        return 1
    pts = [(float(sys.argv[2]), float(sys.argv[3]))]
    if len(sys.argv) >= 6:
        pts.append((float(sys.argv[4]), float(sys.argv[5])))

    b = pcbnew.LoadBoard(PCB)
    victim = None
    # When two points are named, the vias come first: a via stands at
    # one place, and a track may end at the same place.  When a via is
    # wanted, the track that ends there has to stay.  With one point
    # the tracks come first, because a point names a track better
    # than a via.
    for want_via in ((True, False) if len(pts) > 1 else (False, True)):
        for t in list(b.GetTracks()):
            if t.GetNetname() != net:
                continue
            is_via = t.GetClass() == "PCB_VIA"
            if is_via != want_via:
                continue
            ends = [t.GetStart()]
            if not is_via:
                ends.append(t.GetEnd())
            if len(pts) > 1 and not is_via:
                # both ends of the track have to be named, so that the
                # track that is wanted and not another one at the same
                # place is removed
                if not (any(near(p, *pts[0]) for p in ends)
                        and any(near(p, *pts[1]) for p in ends)):
                    continue
            elif not any(near(p, x, y) for p in ends for (x, y) in pts):
                continue
            victim = t
            break
        if victim is not None:
            break
    if victim is None:
        print(f"nothing of the {net} net at {pts}")
        return 0

    kind = victim.GetClass()
    b.Remove(victim)
    save(b, net, kind)
    print(f"removed a {kind} of the {net} net")
    return 1        # something was removed, so the caller repeats


if __name__ == "__main__":
    sys.exit(main())
