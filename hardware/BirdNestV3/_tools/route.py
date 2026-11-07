#!/usr/bin/env python3
"""
Hand-routing helper for the V3 board.

Adds a track segment (with vias when the two pads are on different layers)
between two pads given by reference + pad number.  Tracks get the width of
their netclass, vias the standard 0.6/0.3 mm.

usage:
  route.py <ref1>.<pad1> <ref2>.<pad2> [layer]
  route.py --list
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import safe_board    # noqa: E402  the guard of the board

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"


def parse(ref):
    if "." not in ref:
        raise SystemExit(f"bad pad ref {ref!r}, use REF.PAD")
    r, p = ref.rsplit(".", 1)
    return r, p


def find_pad(board, ref):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        raise SystemExit(f"footprint {ref} not found")
    return fp


def main():
    board = pcbnew.LoadBoard(V3)

    if len(sys.argv) < 3 or sys.argv[1] == "--list":
        print("usage: route.py REF.PAD REF.PAD [layer]")
        print("\npads of the board:")
        for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
            if not fp.GetReference():
                continue
            for pad in fp.Pads():
                net = pad.GetNetname()
                pos = pad.GetPosition()
                print(f"  {fp.GetReference():5}.{pad.GetNumber():4} net={net!r:26} "
                      f"@({pcbnew.ToMM(pos.x):7.2f},{pcbnew.ToMM(pos.y):7.2f}) "
                      f"layer={pad.GetLayerName()}")
        return

    r1, p1 = parse(sys.argv[1])
    r2, p2 = parse(sys.argv[2])
    forced_layer = sys.argv[3] if len(sys.argv) > 3 else None

    fp1, fp2 = find_pad(board, r1), find_pad(board, r2)
    pad1 = fp1.FindPadByNumber(p1)
    pad2 = fp2.FindPadByNumber(p2)
    if pad1 is None or pad2 is None:
        raise SystemExit("pad not found")

    net = pad1.GetNet()
    if net.GetNetname() != pad2.GetNetname():
        raise SystemExit(f"net mismatch: {pad1.GetNetname()} vs {pad2.GetNetname()}")

    nc = net.GetNetClass()
    width = nc.GetTrackWidth()
    vdia = nc.GetViaDiameter()
    vdrill = nc.GetViaDrill()

    l1 = pad1.GetLayerSet()
    l2 = pad2.GetLayerSet()

    if forced_layer:
        layer = pcbnew.F_Cu if forced_layer.upper().startswith("F") else pcbnew.B_Cu
    elif l1.Contains(pcbnew.F_Cu) and l2.Contains(pcbnew.F_Cu):
        layer = pcbnew.F_Cu
    elif l1.Contains(pcbnew.B_Cu) and l2.Contains(pcbnew.B_Cu):
        layer = pcbnew.B_Cu
    else:
        layer = pcbnew.B_Cu if l2.Contains(pcbnew.B_Cu) else pcbnew.F_Cu

    a = pad1.GetPosition()
    b = pad2.GetPosition()

    t = pcbnew.PCB_TRACK(board)
    t.SetStart(a)
    t.SetEnd(b)
    t.SetWidth(width)
    t.SetLayer(layer)
    t.SetNet(net)
    board.Add(t)

    # via if the pads are not both on the chosen layer
    need_via = not (l1.Contains(layer) and l2.Contains(layer))
    if need_via:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(a)
        v.SetWidth(vdia)
        v.SetDrill(vdrill)
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(net)
        board.Add(v)

    print(f"track {r1}.{p1} -> {r2}.{p2} net={net.GetNetname()} "
          f"layer={board.GetLayerName(layer)} width={pcbnew.ToMM(width):.2f}mm"
          + (" +via" if need_via else ""))

    safe_board.save(board, "the route")
    print("saved")


if __name__ == "__main__":
    main()
