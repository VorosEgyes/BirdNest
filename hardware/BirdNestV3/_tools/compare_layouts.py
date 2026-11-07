#!/usr/bin/env python3
"""
The comparison of the v2 layout and the V3 layout.

The v2 layout is the reference: it is finished, it has no errors and it
is the physical design of the board.  Its tracks can only be used when
the parts sit where they sat in the v2.  A part that moved makes every
track of the v2 that ended on it land somewhere else.

This script shows, for every part that the two layouts have in
common, where it is in the v2 and where it is in the V3, and it tells
how many of the v2 tracks can still be used.

Run:  compare_layouts.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = "/Users/modmj/dev/BirdNest/hardware/BirdNest_pcb/BirdNest_pcb.kicad_pcb"
V3 = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")


def mm(v):
    return v / 1000000.0


def load(path):
    import pcbnew
    b = pcbnew.LoadBoard(path)
    parts = {}
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        if not ref:
            continue
        pos = fp.GetPosition()
        parts[ref] = (mm(pos.x), mm(pos.y),
                      fp.GetOrientationDegrees(),
                      str(fp.GetFPID().GetLibItemName()))
    tracks = []
    for t in b.GetTracks():
        a, e = t.GetStart(), t.GetEnd()
        tracks.append((t.GetNetname(),
                       mm(a.x), mm(a.y), mm(e.x), mm(e.y),
                       mm(t.GetWidth()),
                       "VIA" if t.GetClass() == "PCB_VIA" else t.GetLayerName()))
    return parts, tracks


def main():
    v2p, v2t = load(V2)
    v3p, v3t = load(V3)

    common = sorted(set(v2p) & set(v3p))
    only_v2 = sorted(set(v2p) - set(v3p))
    only_v3 = sorted(set(v3p) - set(v2p))

    print(f"the v2 has {len(v2p)} parts, the V3 has {len(v3p)}")
    print(f"in both: {len(common)}   only in the v2: {only_v2}")
    print(f"only in the V3: {only_v3}")
    print()

    print("the parts that are in both layouts")
    print(f"  {'part':7} {'v2':>19} {'V3':>19}  {'shift':>7}")
    moved = []
    for ref in common:
        x2, y2, r2, fp2 = v2p[ref]
        x3, y3, r3, fp3 = v3p[ref]
        d = ((x3 - x2) ** 2 + (y3 - y2) ** 2) ** 0.5
        same_fp = fp2 == fp3
        flag = "" if d < 0.05 else ("  footprint differs" if not same_fp else "")
        if d >= 0.05:
            moved.append((ref, x2, y2, x3, y3, d, same_fp))
        print(f"  {ref:7} ({x2:7.2f},{y2:7.2f}) ({x3:7.2f},{y3:7.2f})"
              f"  {d:7.2f}{flag}")

    print()
    print(f"{len(moved)} of {len(common)} parts moved")
    print()

    # the v2 tracks that end on a part that moved are lost
    print("the v2 tracks that are lost")
    moved_refs = {m[0] for m in moved}
    lost = 0
    for (net, ax, ay, bx, by, w, lay) in v2t:
        if lay == "VIA":
            continue
        for (x, y) in ((ax, ay), (bx, by)):
            for ref in moved_refs:
                x2, y2, r2, fp2 = v2p[ref]
                if abs(x - x2) < 1.5 and abs(y - y2) < 1.5:
                    lost += 1
                    break
    print(f"  {lost} of {len(v2t)} tracks end on a part that moved")
    print(f"  {len(v2t) - lost} can still be used")


if __name__ == "__main__":
    main()
