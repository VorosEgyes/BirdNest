#!/usr/bin/env python3
"""A D9 TVS foldlabjanak ellenorzese: zone, track vagy valami mas?"""
import math

import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'


def mm(v):
    return pcbnew.ToMM(v)


b = pcbnew.LoadBoard(PCB)

d9 = b.FindFootprintByReference('D9')
p1 = [p for p in d9.Pads() if p.GetNetname() == 'GND'][0]
pp = p1.GetPosition()
print("D9 GND pad: ({:.3f},{:.3f})".format(mm(pp.x), mm(pp.y)))

print("\n=== a GND zona, es hogy a pad benne van-e ===")
for z in b.Zones():
    print("  zona net={} layers={}".format(
        z.GetNetname(), [b.GetLayerName(l) for l in z.GetLayerSet().Seq()]))
    if z.IsFilled():
        for lay in z.GetLayerSet().Seq():
            poly = z.GetFilledPolysList(lay)
            for i in range(poly.OutlineCount()):
                o = poly.Outline(i)
                pts = [(mm(o.CPoint(k).x), mm(o.CPoint(k).y)) for k in range(o.PointCount())]
                inside = False
                x, y = mm(pp.x), mm(pp.y)
                n = len(pts)
                for k in range(n):
                    x1, y1 = pts[k]
                    x2, y2 = pts[(k + 1) % n]
                    if (y1 > y) != (y2 > y):
                        xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                        if xin > x:
                            inside = not inside
                print("    {} poly{}: a GND pad benne van: {}".format(
                    b.GetLayerName(lay), i, inside))

print("\n=== minden GND-track a D9 pad koreben (3 mm) ===")
cnt = 0
for t in b.GetTracks():
    if t.GetNetname() != 'GND':
        continue
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        continue
    tp = max(0.0, min(1.0, ((mm(pp.x) - x1) * dx + (mm(pp.y) - y1) * dy) / L2))
    qx, qy = x1 + tp * dx, y1 + tp * dy
    d = math.hypot(mm(pp.x) - qx, mm(pp.y) - qy)
    if d < 3.0:
        cnt += 1
        print("  GND {} ({:.3f},{:.3f})->({:.3f},{:.3f}) tavez {:.3f}".format(
            t.GetLayerName(), x1, y1, x2, y2, d))
if cnt == 0:
    print("  nincs GND track 3 mm-en belul -> a pad a GND zonan keresztul kapcsolodik")

print("\n=== a J4 csatlakozo GND labja (J4.2) hogyan van bekotve ===")
j4 = b.FindFootprintByReference('J4')
for p in j4.Pads():
    q = p.GetPosition()
    print("  J4 pad {} at ({:.3f},{:.3f}) net={}".format(
        p.GetNumber(), mm(q.x), mm(q.y), p.GetNetname()))
    for t in b.GetTracks():
        if t.GetNetname() != p.GetNetname():
            continue
        s, e = t.GetStart(), t.GetEnd()
        x1, y1, x2, y2 = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 == 0:
            continue
        tp = max(0.0, min(1.0, ((mm(q.x) - x1) * dx + (mm(q.y) - y1) * dy) / L2))
        qx, qy = x1 + tp * dx, y1 + tp * dy
        d = math.hypot(mm(q.x) - qx, mm(q.y) - qy)
        if d < 1.5:
            print("       {} ({:.3f},{:.3f})->({:.3f},{:.3f}) tavez {:.3f}".format(
                t.GetLayerName(), x1, y1, x2, y2, d))
