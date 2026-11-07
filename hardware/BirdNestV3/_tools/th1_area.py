#!/usr/bin/env python3
"""A TH1 koruleti silk/copper terkep a szabad tervszam-helyek megkeresesere."""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
X0, X1, Y0, Y1 = 172.0, 194.0, 104.0, 119.0

SILK = ('F.Silkscreen', 'B.Silkscreen')


def mm(v):
    return pcbnew.ToMM(v)


def inr(x1, y1, x2, y2):
    return not (max(x1, x2) < X0 or min(x1, x2) > X1
                or max(y1, y2) < Y0 or min(y1, y2) > Y1)


b = pcbnew.LoadBoard(PCB)
fps = list(b.GetFootprints())

out = []
for fp in fps:
    ref = fp.GetReference()
    for g in list(fp.GraphicalItems()):
        ln = g.GetLayerName()
        if ln not in SILK:
            continue
        s = g.GetStart()
        e = g.GetEnd()
        x1, y1, x2, y2 = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
        if inr(x1, y1, x2, y2):
            txt = g.GetText() if g.GetClass() == 'PCB_TEXT' else ''
            out.append("  {:6s} {:9s} {:13s} ({:8.3f},{:8.3f})->({:8.3f},{:8.3f}) {}".format(
                ref, g.GetClass(), ln, x1, y1, x2, y2, txt))
print("--- silk a teruleten ({}) ---".format(len(out)))
print("\n".join(out))

cop = []
for t in b.GetTracks():
    s = t.GetStart()
    e = t.GetEnd()
    x1, y1, x2, y2 = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
    if inr(x1, y1, x2, y2):
        cop.append("  {:9s} {:6s} ({:8.3f},{:8.3f})->({:8.3f},{:8.3f}) net={}".format(
            t.GetClass(), t.GetLayerName(), x1, y1, x2, y2, t.GetNetname()))
print("--- copper ({}) ---".format(len(cop)))
print("\n".join(cop))

pads = []
for fp in fps:
    for p in fp.Pads():
        pp = p.GetPosition()
        if X0 <= mm(pp.x) <= X1 and Y0 <= mm(pp.y) <= Y1:
            pads.append("  pad {}.{} ({:.3f},{:.3f}) net={} mask={}".format(
                fp.GetReference(), p.GetNumber(), mm(pp.x), mm(pp.y),
                p.GetNetname(), p.IsOnLayer(pcbnew.F_Mask)))
print("--- pads ---")
print("\n".join(pads))

zones = []
for z in b.Zones():
    bb = z.GetBoundingBox()
    if not (mm(bb.GetRight()) < X0 or mm(bb.GetLeft()) > X1
            or mm(bb.GetBottom()) < Y0 or mm(bb.GetTop()) > Y1):
        zones.append("  zone {} net={} layers={}".format(
            z.GetZoneName(), z.GetNetname(),
            [b.GetLayerName(l) for l in z.GetLayerSet().Seq()]))
print("--- zones ---")
print("\n".join(zones))
