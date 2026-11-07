#!/usr/bin/env python3
"""
The free room for the routes that are still missing.

The board has nets that are not connected yet.  Every one of them has
two or three pads, and a route has to be drawn from one to the other.
This script shows the pads of the nets that are not connected, and the
room around them: the copper of the other nets, the pads, and the
distance to the border of the board.

The picture is what a route is drawn on: a straight line on the front
copper where there is room, a via to the back copper where the front is
busy.

Run:  room.py [net name]
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
JSON = "/tmp/room_drc.json"

BX0, BX1, BY0, BY1 = 101.0, 199.0, 41.0, 139.0


def mm(v):
    return v / 1000000.0


def unconnected():
    if os.path.exists(JSON):
        os.remove(JSON)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", JSON, PCB],
                   capture_output=True, text=True)
    with open(JSON) as f:
        d = json.load(f)
    nets = {}
    for u in d.get("unconnected_items", []):
        for i in u.get("items", []):
            desc = i.get("description", "")
            if "[" not in desc:
                continue
            net = desc.split("[")[1].split("]")[0]
            nets.setdefault(net, set()).add(desc)
    return nets


def main():
    import pcbnew
    b = pcbnew.LoadBoard(PCB)

    only = sys.argv[1] if len(sys.argv) > 1 else None
    open_nets = unconnected()
    if only:
        open_nets = {k: v for k, v in open_nets.items() if k == only}
    if not open_nets:
        print("every net is connected")
        return

    # the pads of every net
    pads = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            net = p.GetNetname()
            if not net:
                continue
            pos = p.GetPosition()
            sz = p.GetSize()
            layers = []
            if p.IsOnLayer(pcbnew.F_Cu):
                layers.append("F")
            if p.IsOnLayer(pcbnew.B_Cu):
                layers.append("B")
            pads.setdefault(net, []).append(
                (fp.GetReference() + "." + p.GetNumber(),
                 mm(pos.x), mm(pos.y),
                 mm(sz.x) / 2, mm(sz.y) / 2, "".join(layers)))

    # the copper of every net, on both layers
    copper = {}
    for fp in b.GetFootprints():
        for p in fp.Pads():
            net = p.GetNetname()
            if not net:
                continue
            pos = p.GetPosition()
            sz = p.GetSize()
            hx, hy = mm(sz.x) / 2, mm(sz.y) / 2
            copper.setdefault(net, []).append(
                (mm(pos.x) - hx, mm(pos.y) - hy, mm(pos.x) + hx, mm(pos.y) + hy))
    for t in b.GetTracks():
        net = t.GetNetname()
        if not net:
            continue
        a, e = t.GetStart(), t.GetEnd()
        w = mm(t.GetWidth()) / 2
        ax, ay = mm(a.x), mm(a.y)
        ex, ey = mm(e.x), mm(e.y)
        copper.setdefault(net, []).append(
            (min(ax, ex) - w, min(ay, ey) - w, max(ax, ex) + w, max(ay, ey) + w))

    for net in sorted(open_nets):
        print("=" * 78)
        print(f"the net {net}")
        print("=" * 78)
        mine = pads.get(net, [])
        for (ref, x, y, hx, hy, lay) in mine:
            print(f"  {ref:10} at ({x:8.3f},{y:8.3f})"
                  f"  {2 * hx:5.2f} x {2 * hy:5.2f}  on {lay}")
        if not mine:
            print("  (no pad)")
            continue

        # the box around the pads, with room around them
        x0 = min(p[1] for p in mine) - 3.0
        x1 = max(p[1] for p in mine) + 3.0
        y0 = min(p[2] for p in mine) - 3.0
        y1 = max(p[2] for p in mine) + 3.0
        x0 = max(x0, BX0)
        x1 = min(x1, BX1)
        y0 = max(y0, BY0)
        y1 = min(y1, BY1)

        # the room on a grid of one millimetre
        step = 1.0
        print()
        print("  the room around the pads (the dot is free, the x is copper)")
        print(f"  {'x':>7} " + "".join(
            str(int(x0 + i * step) % 10) for i in range(int((x1 - x0) / step) + 1)))
        y = y0
        while y <= y1:
            line = ""
            x = x0
            while x <= x1:
                inside = False
                for (ax, ay, bx, by) in copper.get(net, []):
                    if ax <= x <= bx and ay <= y <= by:
                        inside = True
                        break
                if not inside:
                    for (ax, ay, bx, by) in copper.get("GND", []):
                        if ax <= x <= bx and ay <= y <= by:
                            inside = True
                            break
                line += "." if not inside else "#"
                x += step
            print(f"  {y:7.1f} {line}")
            y += step
        print()


if __name__ == "__main__":
    main()
