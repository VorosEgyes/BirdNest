#!/usr/bin/env python3
"""
The rules of the nets of the board.

The rules of the nets live in the project file, not in the board: the
board holds only the name of the class of every net, and the widths
that it holds are empty.  The router reads the rules from the project
file, and this script shows them, so that the router and the board
agree.

Run:  net_rules.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pcbnew        # noqa: E402
from maze4 import load_classes    # noqa: E402

PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")


def main():
    b = pcbnew.LoadBoard(PCB)
    classes = load_classes()
    print(f"{'net':22} {'class':18} {'width':>6} {'clear':>6}  the pads")
    for (code, ni) in sorted(b.GetNetInfo().NetsByNetcode().items()):
        net = ni.GetNetname()
        if not net:
            continue
        # the class of the net: the board holds a list of names, the
        # first one is the class itself
        raw = ni.GetNetClassName() or ""
        name = raw.split(",")[0].strip()
        rule = classes.get(name, classes.get("Default", {}))
        # the pads of the net
        pads = []
        for fp in b.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() == net:
                    pads.append(f"{fp.GetReference()}.{p.GetNumber()}")
        if not pads:
            continue
        print(f"{net:22} {name:18} "
              f"{rule.get('track_width', 0.0):6.2f} "
              f"{rule.get('clearance', 0.0):6.2f}  "
              f"{len(pads)}: {', '.join(pads[:8])}")


if __name__ == "__main__":
    main()
