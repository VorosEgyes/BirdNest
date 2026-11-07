#!/usr/bin/env python3
"""
The guard of the board.

The board of the V3 is the only copy of a lot of work.  The scripts in
this directory write it, and some of them are the ones that were
thrown out: they draw tracks over the copper of the other nets, and the
board ends up with more errors than it had before.

So the board is only written when the result is not worse than the
state that is known to be good.  The guard measures the board before
and after the change, and it puts the good board back when the change
made it worse.

    import safe_board

    safe_board.save(board, "the route of the battery")

The copper may not get worse, and the number of the unconnected items
may not get worse.  The errors of the silk screen may grow: they are
not copper.

Run:  safe_board.py [board file]   -  measures the board and prints
       the state.  It never writes.
"""
import json
import os
import shutil
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

# The file that holds the measurement of the board.
JSON = "/tmp/safe_board_drc.json"

# The copy of the board that a script takes before it starts, so that
# it can put it back when the script did not help.
BEFORE_BOARD = "/tmp/repair_board_before.kicad_pcb"

# The errors that mean that the copper is wrong.
#
# A track that hangs loose is one of them when a new route draws it: a
# route that does not reach a pad is not a route.  The errors that the
# board of before already has do not matter, the guard looks at the
# change and not at the absolute number.
COPPER_ERRORS = ("shorting_items", "clearance", "tracks_crossing",
                 "solder_mask_bridge", "hole_clearance", "hole_to_hole",
                 "holes_co_located", "via_dangling", "track_dangling")


def measure(board=None):
    """The state of the board: the errors and the unconnected items.

    The answer is a dictionary with the number of the violations, the
    number of the unconnected items, the number of the errors in the
    copper, and the two lists.
    """
    board = board or PCB
    if os.path.exists(JSON):
        os.remove(JSON)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", JSON, board],
                   capture_output=True, text=True)
    with open(JSON) as f:
        d = json.load(f)
    viol = d.get("violations", [])
    unc = d.get("unconnected_items", [])
    copper = sum(1 for v in viol if v.get("type") in COPPER_ERRORS)
    return {"violations": len(viol), "unconnected": len(unc),
            "copper": copper, "viol": viol, "unc": unc}


def is_better(after, before):
    """Is the state after the change better than the one before it?

    The copper may not get worse, and the number of the unconnected
    items may not get worse.  The violations may grow, when they are
    the errors of the silk screen, but the copper and the unconnected
    items are what matter.
    """
    return (after["copper"] <= before["copper"]
            and after["unconnected"] <= before["unconnected"])


def report(what, before, after, kept):
    """Say what the guard did with the change."""
    verb = "keeps" if kept else "throws ... away"
    print(f"the guard {verb} {what}:"
          f" {before['copper']} -> {after['copper']} errors in the"
          f" copper, {before['unconnected']} -> {after['unconnected']}"
          f" unconnected")
    if not kept:
        # The kinds of the errors in the copper, so that the reason is
        # written down and not only the number of them.
        kinds = {}
        for v in after["viol"]:
            t = v.get("type")
            if t in COPPER_ERRORS:
                kinds[t] = kinds.get(t, 0) + 1
        for k in sorted(kinds):
            print(f"    {k}: {kinds[k]}")


def save(board, what="the change", force=False):
    """Write the board, but only when it did not get worse.

    The board is measured before and after the change.  When the change
    made the board worse, the board of before is put back, and the
    function returns False.  So a script that was thrown out can not
    destroy the work.

    The force argument skips the check.  It is for the scripts that
    remove the copper of a net on purpose: that always opens the net, so
    the check would always throw the change away.  It also skips the
    measurement, because a removal that is meant does not need to be
    measured: the script that removes the copper draws it again.
    """
    if force:
        pcbnew.SaveBoard(PCB, board)
        print(f"the guard lets {what} through, it was asked to")
        return True
    before = measure()
    backup = PCB + ".guard"
    shutil.copy(PCB, backup)
    try:
        pcbnew.SaveBoard(PCB, board)
        after = measure()
        if is_better(after, before):
            report(what, before, after, True)
            return True
        shutil.copy(backup, PCB)
        report(what, before, after, False)
        return False
    finally:
        if os.path.exists(backup):
            os.remove(backup)


def main():
    board = sys.argv[1] if len(sys.argv) > 1 else PCB
    m = measure(board)
    print(f"the board: {m['violations']} violations"
          f" ({m['copper']} of them in the copper),"
          f" {m['unconnected']} unconnected")
    kinds = {}
    for v in m["viol"]:
        kinds[v.get("type")] = kinds.get(v.get("type"), 0) + 1
    for k in sorted(kinds):
        print(f"  {k:28} {kinds[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
