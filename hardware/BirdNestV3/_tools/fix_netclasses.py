#!/usr/bin/env python3
"""
Rewrite the V3 netclass patterns so they match the actual V3 net names.

The project file still carried patterns from the V2 board (/BAT_RAW,
/SYS_BATT_SW, Net-(Q7-S), Net-(D1-A), Net-(J3-Pin_2), Net-(D6-A),
Net-(U7A-+)); those nets no longer exist in V3, so the power nets fell back
to the Default class (0.5 mm track, 0.2 mm clearance) and the real power
nets were unrouted with default widths.

This script:
  * lists every net actually on the V3 board,
  * assigns each one to the correct netclass,
  * writes the corrected netclass_patterns back into BirdNestV3.kicad_pro,
  * also updates the board-embedded net classes so kicad-cli DRC uses them.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V3DIR = os.path.dirname(HERE)
PRO = os.path.join(V3DIR, "BirdNestV3.kicad_pro")

# ---------------------------------------------------------------------------
# Netclass assignment rules.  Order matters: first match wins.
#   (netclass, regex)
# ---------------------------------------------------------------------------
RULES = [
    ("GND", r"^GND$"),
    ("Power_Battery", r"^/(BAT_CELL\+|BAT_CELL-|BAT_PROT\+|BAT_RAW|SYS_PWR|SYS_BATT_SW)$"),
    ("Power_Battery", r"^Net-\(Q9-S\)$"),
    ("Power_Battery", r"^Net-\(Q9-D\)$"),
    ("Power_Battery", r"^Net-\(D10-A\)$"),
    ("Power_Battery", r"^Net-\(D10-K\)$"),
    ("Power_Battery", r"^Net-\(J4-Pin_2\)$"),
    ("Power_Battery", r"^Net-\(J3-Pin_2\)$"),
    ("Power_Battery", r"^/VIN_PROT$"),
    ("Power_Battery", r"^\+BATT"),
    ("Power_5V_Out", r"^/\+5V$"),
    ("Power_5V_Out", r"^Net-\(U2-\)$"),
    ("Power_3V3", r"^/\+3V3$"),
    ("Power_3V3", r"^/REF2V5$"),
    ("Switching_Node", r"^Net-\(D9-A\)$"),
    ("Switching_Node", r"^Net-\(D6-A\)$"),
    ("Switching_Node", r"^/SW_NODE$"),
    ("Switching_Node", r"^Net-\(Q3-D\)$"),
    ("Signal", r"^/BAT_MON$"),
    ("Signal", r"^/UVLO_.*$"),
    ("Signal", r"^Net-\(U7A-\+\)$"),
    ("Signal", r"^Net-\(Q9-G\)$"),
    ("Signal", r"^Net-\(U11-.*$"),
    ("Signal", r"^Net-\(D7-A\)$"),
    ("Signal", r"^Net-\(D8-A\)$"),
    ("Signal", r"^/(DONE_STAT|CHG_STAT)$"),
]


def classify(netname):
    for cls, pat in RULES:
        if re.fullmatch(pat, netname):
            return cls
    # Everything that no rule covers keeps the default class.  The
    # default class is the one that the v2 board used for the same nets,
    # and the v2 layout is DRC clean with it.
    return "Default"


def main():
    import pcbnew
    board = pcbnew.LoadBoard(os.path.join(V3DIR, "BirdNestV3.kicad_pcb"))

    nets = sorted(n.GetNetname() for n in board.GetNetsByNetcode().values()
                  if n.GetNetname())

    assignment = {}
    for n in nets:
        assignment[n] = classify(n)

    print("=== net -> netclass ===")
    by_cls = {}
    for n in nets:
        by_cls.setdefault(assignment[n], []).append(n)
    for cls in sorted(by_cls):
        print(f"  [{cls}]")
        for n in by_cls[cls]:
            print(f"      {n}")

    # ---- write the patterns back to the project file ----------------------
    with open(PRO) as f:
        pro = json.load(f)

    patterns = []
    for cls in sorted(by_cls):
        if cls == "Default":
            continue
        for n in by_cls[cls]:
            # A rule with a wildcard covers a whole group of nets, and
            # the pattern is written with the same wildcard.
            # KiCad matches the netclass patterns with its own wildcard
            # syntax, not with the python regex engine: only '*' is
            # special, everything else is literal.  re.escape would put
            # backslashes into the pattern, and those do not match the
            # net names with a '(' or a ')' in them.
            patterns.append({"netclass": cls, "pattern": n})

    pro["net_settings"]["netclass_patterns"] = patterns
    pro["net_settings"]["netclass_assignments"] = None

    # The default class carried a differential pair gap from the v2 board.
    # Every net that is not a differential pair then reported a "differential
    # pair gap out of range" error.
    for cls in pro["net_settings"].get("classes", []):
        if cls.get("name") == "Default":
            # No net of this board is a differential pair.  A diff pair gap
            # in the default class made every net of the default class
            # report a "differential pair gap out of range" error.
            cls["diff_pair_gap"] = 0
            cls["diff_pair_width"] = 0
            cls["diff_pair_via_gap"] = 0
    # the board file has the same classes
    for cls in board.GetNetClasses().values():
        if str(cls.GetName()) == "Default":
            try:
                cls.SetDiffPairGap(pcbnew.FromMM(0))
                cls.SetDiffPairWidth(pcbnew.FromMM(0))
            except Exception:
                pass

    with open(PRO, "w") as f:
        json.dump(pro, f, indent=2)
    print(f"\nwrote {len(patterns)} netclass patterns to {PRO}")

    # ---- also set the net classes on the board itself ---------------------
    # GetNetClasses() returns a netclasses_map; use items() to index it.
    all_classes = {str(k): v for k, v in board.GetNetClasses().items()}
    default = all_classes.get("Default")
    for code, net in board.GetNetsByNetcode().items():
        name = net.GetNetname()
        if not name:
            continue
        cls = assignment[name]
        if cls == "Default":
            if default is not None:
                # reset the net to the default class first: SetNetClass
                # only adds a class, it does not replace the old one
                net.SetNetClass(default)
            continue
        nc = all_classes.get(cls)
        if nc is None:
            print(f"  !! netclass {cls} missing on board")
            continue
        if default is not None:
            net.SetNetClass(default)
        net.SetNetClass(nc)
    pcbnew.SaveBoard(os.path.join(V3DIR, "BirdNestV3.kicad_pcb"), board)
    print("board netclasses updated")


if __name__ == "__main__":
    main()
