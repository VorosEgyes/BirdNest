#!/usr/bin/env python3
"""
A survey of the board: where the parts are, where the copper is, and
what the design rules checker says about it.

The report is the base for the decisions about the layout: a part that
sits in the middle of the power tracks has to move, and the space that
is left tells where it can go.

Run:  survey.py
"""
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
JSON = "/tmp/survey_drc.json"


def mm(v):
    return v / 1000000.0


def drc():
    if os.path.exists(JSON):
        os.remove(JSON)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", JSON, PCB],
                   capture_output=True, text=True)
    with open(JSON) as f:
        return json.load(f)


def net_of(desc):
    """The net of a description like 'Track [/VIN_PROT] on F.Cu'."""
    if "[" in desc and "]" in desc:
        return desc.split("[")[1].split("]")[0]
    return ""


def main():
    import pcbnew
    b = pcbnew.LoadBoard(PCB)

    print("=" * 78)
    print("the parts and the room they take")
    print("=" * 78)
    boxes = []
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        if not fp.GetReference():
            continue
        bb = fp.GetBoundingBox()
        x0, y0 = mm(bb.GetLeft()), mm(bb.GetTop())
        x1, y1 = mm(bb.GetRight()), mm(bb.GetBottom())
        boxes.append((fp.GetReference(), x0, y0, x1, y1, fp.GetValue()))
    for (ref, x0, y0, x1, y1, val) in boxes:
        print(f"  {ref:6} ({x0:7.2f},{y0:7.2f}) - ({x1:7.2f},{y1:7.2f})"
              f"  {x1 - x0:6.2f} x {y1 - y0:6.2f}  {val[:20]}")

    # the free room, on a grid of two millimetres
    print()
    print("=" * 78)
    print("the free room on a 2 mm grid")
    print("=" * 78)
    # the room that the parts take
    blocked = []
    for (ref, x0, y0, x1, y1, val) in boxes:
        blocked.append((x0, y0, x1, y1))
    # the battery holder and the connectors are room as well
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if ref in ("BT3", "H1"):
            bb = fp.GetBoundingBox()
            blocked.append((mm(bb.GetLeft()), mm(bb.GetTop()),
                            mm(bb.GetRight()), mm(bb.GetBottom())))

    def free_at(x, y, w, h):
        for (a0, b0, a1, b1) in blocked:
            if x < a1 and a0 < x + w and y < b1 and b0 < y + h:
                return False
        # and no track of the board
        for t in b.GetTracks():
            ax, ay = mm(t.GetStart().x), mm(t.GetStart().y)
            ex, ey = mm(t.GetEnd().x), mm(t.GetEnd().y)
            lo_x, hi_x = min(ax, ex) - 0.6, max(ax, ex) + 0.6
            lo_y, hi_y = min(ay, ey) - 0.6, max(ay, ey) + 0.6
            if (lo_x < x + w and x < hi_x
                    and lo_y < y + h and y < hi_y):
                return False
        return True

    rows = []
    y = 42.0
    while y < 138.0:
        line = ""
        x = 102.0
        while x < 198.0:
            line += "." if free_at(x, y, 4.0, 4.0) else "#"
            x += 2.0
        rows.append((y, line))
        y += 2.0
    for (y, line) in rows:
        print(f"  {y:6.1f} |{line}|")

    print()
    print("=" * 78)
    print("what the design rules checker says")
    print("=" * 78)
    d = drc()
    viol = d.get("violations", [])
    unc = d.get("unconnected_items", [])
    c = Counter(v["type"] for v in viol)
    for k in sorted(c):
        print(f"  {k:28} {c[k]:4d}")
    print(f"  {'TOTAL':28} {len(viol):4d}")
    print(f"  {'unconnected':28} {len(unc):4d}")

    print()
    print("the shorting tracks, the worst nets first")
    pairs = Counter()
    for v in viol:
        if v.get("type") != "shorting_items":
            continue
        nets = set()
        for i in v.get("items", []):
            n = net_of(i.get("description", ""))
            if n:
                nets.add(n)
        if len(nets) == 2:
            pairs[tuple(sorted(nets))] += 1
    for (a, b_), n in pairs.most_common(14):
        print(f"  {n:3d}  {a:22} {b_}")

    print()
    print("the clearance errors")
    for v in viol:
        if v.get("type") != "clearance":
            continue
        for i in v.get("items", []):
            print(f"  {i.get('description', '')[:60]:62}"
                  f" @({mm(i.get('pos', {}).get('x', 0)):.2f},"
                  f"{mm(i.get('pos', {}).get('y', 0)):.2f})")

    print()
    print("the nets that are not connected")
    per = defaultdict(list)
    for u in unc:
        for i in u.get("items", []):
            dsc = i.get("description", "")
            n = net_of(dsc)
            if n:
                per[n].append(dsc[:58])
    for n in sorted(per):
        print(f"  {n:22} {len(per[n])} items")
        for x in per[n][:4]:
            print(f"      {x}")


if __name__ == "__main__":
    main()
