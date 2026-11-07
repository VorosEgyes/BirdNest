#!/usr/bin/env python3
"""Board inspection: footprints, pads, nets, board outline, tracks, zones."""
import pcbnew, sys, os

pcb_path = sys.argv[1] if len(sys.argv) > 1 else "BirdNestV3.kicad_pcb"
b = pcbnew.LoadBoard(pcb_path)

print(f"=== FILE: {pcb_path} ===")
print(f"Footprints: {len(b.GetFootprints())}")
print(f"Tracks (F.Cu/B.Cu): {len(b.GetTracks())}")
print(f"Zones: {b.Zones().GetCount() if hasattr(b.Zones(),'GetCount') else len(list(b.Zones()))}")
print(f"Nets: {b.GetNetCount()}")
print(f"Drawings (Edge.Cuts etc): {len(b.GetDrawings())}")

print("\n=== NETS ===")
netinfo = b.GetNetInfo()
for code, net in netinfo.NetsByNetcode().items():
    print(f"{code:>4}  {net.GetNetname()}")

print("\n=== BOARD OUTLINE / DRAWINGS ===")
for d in b.GetDrawings():
    try:
        layer = b.GetLayerName(d.GetLayer())
    except Exception:
        layer = "?"
    try:
        st = d.GetShapeStr()
    except Exception:
        st = "?"
    extra = ""
    if d.GetClass() == "PCB_SHAPE":
        extra = f"start={d.GetStart()} end={d.GetEnd()} w={d.GetWidth()}"
    print(f"  {d.GetClass():20} layer={layer:12} {st} {extra}")

print("\n=== FOOTPRINTS ===")
for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
    pos = fp.GetPosition()
    p = pcbnew.ToMM(pos.x); q = pcbnew.ToMM(pos.y)
    orient = fp.GetOrientationDegrees()
    layer = "F" if fp.GetLayer() == pcbnew.F_Cu else "B"
    pads = []
    for pad in fp.Pads():
        n = pad.GetNetname()
        px, py = pcbnew.ToMM(pad.GetPosition().x), pcbnew.ToMM(pad.GetPosition().y)
        pads.append(f"{pad.GetNumber()}[{n}]({px:.2f},{py:.2f})")
    print(f"  {fp.GetReference():6} {fp.GetValue():22} {layer} at({p:8.2f},{q:8.2f}) rot={orient:6.1f}  {' '.join(pads)}")
