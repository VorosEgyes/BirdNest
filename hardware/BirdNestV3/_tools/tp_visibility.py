#!/usr/bin/env python3
"""A testpointok mask/lathatovalaga es a kornyezetuk reszletes vizsgalata."""
import math

import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'


def mm(v):
    return pcbnew.ToMM(v)


b = pcbnew.LoadBoard(PCB)
fps = list(b.GetFootprints())

print("=== mi van a testpointok koruleten (100..120, 42..60) ===")
for fp in fps:
    p = fp.GetPosition()
    if not (100 <= mm(p.x) <= 120 and 42 <= mm(p.y) <= 60):
        continue
    print("  {} ({:.3f},{:.3f}) rot {}  {}".format(
        fp.GetReference(), mm(p.x), mm(p.y), fp.GetOrientationDegrees(),
        fp.GetFPIDAsString()))

print("\n=== a testpoint padok maszk- es zonadetailjai ===")
for ref in ('TP1', 'TP2', 'TP3', 'TP4', 'TP5'):
    fp = b.FindFootprintByReference(ref)
    for pad in fp.Pads():
        pp = pad.GetPosition()
        print("\n{} pad at ({:.3f},{:.3f}) net={}".format(
            ref, mm(pp.x), mm(pp.y), pad.GetNetname()))
        print("   F.Mask={} B.Mask={}  mask margin local={:.3f}mm  size={:.2f}".format(
            pad.IsOnLayer(pcbnew.F_Mask), pad.IsOnLayer(pcbnew.B_Mask),
            mm(pad.GetLocalSolderMaskMargin() or 0), mm(pad.GetSizeX())))
        # a GND zona fedi-e a pad teruletet?
        for z in b.Zones():
            for lay in z.GetLayerSet().Seq():
                poly = z.GetFilledPolysList(lay)
                for i in range(poly.OutlineCount()):
                    o = poly.Outline(i)
                    pts = [(mm(o.CPoint(k).x), mm(o.CPoint(k).y))
                           for k in range(o.PointCount())]
                    x, y = mm(pp.x), mm(pp.y)
                    inside = False
                    n = len(pts)
                    for k in range(n):
                        x1, y1 = pts[k]
                        x2, y2 = pts[(k + 1) % n]
                        if (y1 > y) != (y2 > y):
                            if x1 + (y - y1) * (x2 - x1) / (y2 - y1) > x:
                                inside = not inside
                    if inside:
                        print("   a {} zona poly{} LEFEDI a pad teruletet (net={})".format(
                            b.GetLayerName(lay), i, z.GetNetname()))

print("\n=== a testpointok silk koronek es cimkeinek helye ===")
for ref in ('TP1', 'TP2', 'TP3', 'TP4', 'TP5'):
    fp = b.FindFootprintByReference(ref)
    p = fp.GetPosition()
    for g in list(fp.GraphicalItems()):
        if g.GetClass() == 'PCB_TEXT':
            q = g.GetPosition()
            print("  {} TEXT ({:.3f},{:.3f}) '{}'".format(
                ref, mm(q.x), mm(q.y), g.GetText()))
        elif g.GetLayerName() in ('F.Silkscreen', 'B.Silkscreen'):
            s, e = g.GetStart(), g.GetEnd()
            print("  {} {} ({:.3f},{:.3f})->({:.3f},{:.3f})".format(
                ref, g.GetLayerName(), mm(s.x), mm(s.y), mm(e.x), mm(e.y)))
