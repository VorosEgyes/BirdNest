#!/usr/bin/env python3
"""Diagnose a specific DRC conflict: where are the items and how far apart."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"


def main():
    d = json.load(open("/tmp/v3_drcD.json"))
    board = pcbnew.LoadBoard(V3)

    # find the +5V tracks near U3
    u3 = board.FindFootprintByReference("U3")
    print(f"U3 at {pcbnew.ToMM(u3.GetPosition().x):.2f},"
          f"{pcbnew.ToMM(u3.GetPosition().y):.2f}")
    for pad in u3.Pads():
        p = pad.GetPosition()
        print(f"  pad {pad.GetNumber():3} net={pad.GetNetname()!r:24} "
              f"@({pcbnew.ToMM(p.x):7.2f},{pcbnew.ToMM(p.y):7.2f}) "
              f"size={pcbnew.ToMM(pad.GetSize().x):.2f}x"
              f"{pcbnew.ToMM(pad.GetSize().y):.2f}")

    print()
    print("=== +5V tracks and vias ===")
    for t in board.GetTracks():
        if t.GetNetname() != "/+5V":
            continue
        a, b = t.GetStart(), t.GetEnd()
        cls = t.GetClass()
        if cls == "PCB_VIA":
            print(f"  VIA  @({pcbnew.ToMM(a.x):7.2f},{pcbnew.ToMM(a.y):7.2f})")
        else:
            print(f"  TRK  ({pcbnew.ToMM(a.x):7.2f},{pcbnew.ToMM(a.y):7.2f}) -> "
                  f"({pcbnew.ToMM(b.x):7.2f},{pcbnew.ToMM(b.y):7.2f}) "
                  f"w={pcbnew.ToMM(t.GetWidth()):.2f} layer={t.GetLayerName()}")

    print()
    print("=== the DRC-violating +5V track (0.7 mm long) ===")
    for x in d.get("violations", []):
        if x["type"] not in ("clearance", "shorting_items"):
            continue
        descs = [i.get("description", "") for i in x.get("items", [])]
        if not any("[/+5V]" in s for s in descs):
            continue
        if "U3-LX" not in " ".join(descs):
            continue
        for i in x.get("items", []):
            print(f"  {i.get('description','')[:60]} @ {i.get('pos')}")
        print(f"  -> {x.get('description','')}")
        print()


if __name__ == "__main__":
    main()
