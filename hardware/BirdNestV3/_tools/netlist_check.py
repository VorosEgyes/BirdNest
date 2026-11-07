#!/usr/bin/env python3
"""Compare the nets of the schematic with the nets of the board.

The board is measured on its own: the rule checker says that every
pad of the board is joined to the others of its net.  That says
nothing about the board and the schematic being the same circuit: a
net may be renamed, a pad may be given to another net, and the board
may still be perfect.

So the netlist of the schematic is written out and compared with the
nets of the board: every net must have the same pads on both sides.

    kicad-cli sch export netlist --format kicadsexpr -o /tmp/v3.net \\
        BirdNestV3.kicad_sch
    netlist_check.py /tmp/v3.net BirdNestV3.kicad_pcb

The name of a net that KiCad has made up is not the same on the
schematic and on the board (the board gets "_1" added to it when
there are two nets of that name), so the nets are compared by the pads
they hold and not by their name.
"""
import re
import sys

import pcbnew

NET = sys.argv[1] if len(sys.argv) > 1 else ''
PCB = sys.argv[2] if len(sys.argv) > 2 else ''


def nets_of_schematic(path):
    """The nets of the schematic, and the pins that are marked as not connected.

    A pin that is marked as not connected is put by KiCad into a net
    of its own ("unconnected-(...)"), and two such pins end up in the
    same net.  That net says nothing about the circuit: the pins are
    not meant to be joined.  So they are taken out of the comparison.
    """
    txt = open(path).read()
    out = {}
    nc = set()
    for m in re.finditer(r'\(net\s+\(code\s+"[^"]*"\)\s+\(name\s+"([^"]*)"'
                         r'(.*?)\n\t\t\)', txt, re.S):
        name = m.group(1)
        pads = set()
        for n in re.finditer(r'\(node\b(.*?)\n\t\t\t\)', m.group(2), re.S):
            block = n.group(1)
            ref = re.search(r'\(ref\s+"([^"]*)"\)', block)
            pin = re.search(r'\(pin\s+"([^"]*)"\)', block)
            typ = re.search(r'\(pintype\s+"([^"]*)"\)', block)
            if not (ref and pin):
                continue
            pad = (ref.group(1), pin.group(1))
            if typ and 'no_connect' in typ.group(1):
                nc.add(pad)
                continue
            pads.add(pad)
        if pads:
            out[name] = pads
    return out, nc


def nets_of_board(path):
    b = pcbnew.LoadBoard(path)
    out = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            name = p.GetNetname()
            if not name:
                continue
            out.setdefault(name, set()).add((f.GetReference(), p.GetNumber()))
    return out


def groups(nets):
    """The nets as groups of pads."""
    out = {}
    for name, pads in nets.items():
        out.setdefault(frozenset(pads), []).append(name)
    return out


def main():
    sch, nc = nets_of_schematic(NET)
    pcb = nets_of_board(PCB)
    # a pad that is marked as not connected may be a net of its own on
    # the board; that is not a difference of the circuit
    pcb = {n: (p - nc) for n, p in pcb.items()}
    pcb = {n: p for n, p in pcb.items() if p}
    a = groups(sch)
    b = groups(pcb)
    bad = 0
    for pads in sorted(a, key=lambda s: sorted(s)):
        if pads in b:
            if sorted(a[pads]) != sorted(b[pads]):
                print(f"  the net {sorted(a[pads])} is called "
                      f"{sorted(b[pads])} on the board")
            continue
        bad += 1
        print(f"  only in the schematic: {sorted(a[pads])}")
    for pads in sorted(b, key=lambda s: sorted(s)):
        if pads not in a:
            bad += 1
            print(f"  only on the board    : {sorted(b[pads])}")
    print(f"{len(sch)} nets in the schematic, {len(pcb)} on the board,"
          f" {bad} of them are not the same")
    print(f"{len(nc)} pins are marked as not connected and are not compared")
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
