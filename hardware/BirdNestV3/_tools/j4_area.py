#!/usr/bin/env python3
"""A J4 panel-csatlakozo koruleti geometria: szabad hely a D9 TVS
elhelyezesere es a GND-visszavezetesre."""
import math

import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'


def mm(v):
    return pcbnew.ToMM(v)


b = pcbnew.LoadBoard(PCB)
fps = list(b.GetFootprints())

print("=== az összes elem a J4 koruleten (185..200, 100..125) ===")
X0, X1, Y0, Y1 = 185.0, 200.0, 100.0, 125.0


def inr(x1, y1, x2, y2):
    return not (max(x1, x2) < X0 or min(x1, x2) > X1
                or max(y1, y2) < Y0 or min(y1, y2) > Y1)


for fp in fps:
    ref = fp.GetReference()
    p = fp.GetPosition()
    if not (X0 <= mm(p.x) <= X1 and Y0 <= mm(p.y) <= Y1):
        continue
    print("  FOOTPRINT {} ({:.3f},{:.3f}) rot {} layers F={}".format(
        ref, mm(p.x), mm(p.y), fp.GetOrientationDegrees(),
        fp.GetLayerName() == 'F.Cu'))
    for g in list(fp.GraphicalItems()):
        if g.GetClass() == 'PCB_TEXT':
            q = g.GetPosition()
            print("      TEXT {} ({:.3f},{:.3f}) '{}'".format(
                g.GetLayerName(), mm(q.x), mm(q.y), g.GetText()))
            continue
        s, e = g.GetStart(), g.GetEnd()
        x1, y1, x2, y2 = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
        if inr(x1, y1, x2, y2):
            print("      {} {} ({:.3f},{:.3f})->({:.3f},{:.3f})".format(
                g.GetClass(), g.GetLayerName(), x1, y1, x2, y2))
    for pad in fp.Pads():
        q = pad.GetPosition()
        print("      PAD {} ({:.3f},{:.3f}) net={} size {:.2f}".format(
            pad.GetNumber(), mm(q.x), mm(q.y), pad.GetNetname(),
            mm(pad.GetSizeX())))

print("\n=== a trackek es zakok a teruleten ===")
for t in b.GetTracks():
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
    if inr(x1, y1, x2, y2):
        print("  {} {} ({:.3f},{:.3f})->({:.3f},{:.3f}) w={:.3f} net={}".format(
            t.GetClass(), t.GetLayerName(), x1, y1, x2, y2,
            mm(t.GetWidth()) if hasattr(t, 'GetWidth') else 0, t.GetNetname()))

print("\n=== a tabla szele (Edge.Cuts) ===")
for d in list(b.GetDrawings()):
    if d.GetLayerName() != 'Edge.Cuts':
        continue
    bb = d.GetBoundingBox()
    print("   bounding: ({:.2f},{:.2f})->({:.2f},{:.2f})".format(
        mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())))

print("\n=== GND-zona hatar a J4 koruleten ===")
for z in b.Zones():
    for lay in z.GetLayerSet().Seq():
        poly = z.GetFilledPolysList(lay)
        for i in range(poly.OutlineCount()):
            o = poly.Outline(i)
            pts = [(mm(o.CPoint(k).x), mm(o.CPoint(k).y)) for k in range(o.PointCount())]
            if any(X0 <= x <= X1 and Y0 <= y <= Y1 for x, y in pts):
                print("   {} poly{}: {}".format(
                    b.GetLayerName(lay), i,
                    " ".join("({:.1f},{:.1f})".format(x, y) for x, y in pts[:14])))
