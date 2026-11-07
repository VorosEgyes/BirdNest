#!/usr/bin/env python3
"""Reszletes localis terkep a J4 koruleteire: zona, silk, copper, pad, via."""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
b = pcbnew.LoadBoard(PCB)

X0, X1 = 180.0, 200.03
Y0, Y1 = 96.0, 126.0

def mm(v):
    return v / 1e6

def inb(x, y):
    return X0 <= x <= X1 and Y0 <= y <= Y1

print("=" * 72)
print("OSSZES ZONA (net, layer, bbox)")
for z in b.Zones():
    bb = z.GetBoundingBox()
    ls = z.GetLayerSet()
    lays = [b.GetLayerName(l) for l in ls.Seq()]
    print(f"  net='{z.GetNetname()}' layers={lays} "
          f"x {mm(bb.GetLeft()):.2f}..{mm(bb.GetRight()):.2f} "
          f"y {mm(bb.GetTop()):.2f}..{mm(bb.GetBottom()):.2f} "
          f"pad_conn={z.GetPadConnection()} fill={z.IsFilled()}")

print("\n" + "=" * 72)
print("ZONA-TARTALOM a J4 koruleten (van-e GND pour a stripben?)")
for z in b.Zones():
    for lay in z.GetLayerSet().Seq():
        filled = z.GetFilledPolysList(lay)
        if filled.OutlineCount() == 0:
            continue
        hits = []
        for (tx, ty) in ((196.0, 110.5), (196.0, 114.0), (196.0, 117.5), (197.5, 112.5),
                          (195.5, 108.0), (193.0, 110.5), (194.5, 112.5), (197.0, 120.0),
                          (198.5, 112.5), (198.9, 110.5)):
            p = pcbnew.VECTOR2I(int(tx * 1e6), int(ty * 1e6))
            try:
                r = filled.HitTest(p)
            except Exception as ex:
                r = 'err:' + str(ex)[:30]
            hits.append(f"({tx},{ty})={r}")
        print(f"  net='{z.GetNetname()}' {b.GetLayerName(lay)}: {' '.join(hits)}")

print("\n" + "=" * 72)
print("SILK ELEMEK (footprint + board) a teruleten")
for fp in b.GetFootprints():
    for it in fp.GraphicalItems():
        if it.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
            continue
        bb = it.GetBoundingBox()
        if mm(bb.GetRight()) < X0 or mm(bb.GetLeft()) > X1:
            continue
        if mm(bb.GetBottom()) < Y0 or mm(bb.GetTop()) > Y1:
            continue
        l = b.GetLayerName(it.GetLayer())
        if it.GetClass() == 'PTEXT':
            p = it.GetPosition()
            print(f"  TEXT '{it.GetText()}' at ({mm(p.x):.3f},{mm(p.y):.3f}) "
                  f"or={it.GetTextAngleDegrees():.0f} layer={l} "
                  f"bbox x {mm(bb.GetLeft()):.2f}..{mm(bb.GetRight()):.2f} "
                  f"y {mm(bb.GetTop()):.2f}..{mm(bb.GetBottom()):.2f}")
        else:
            print(f"  {it.GetShapeStr():8s} layer={l} bbox x {mm(bb.GetLeft()):.2f}..{mm(bb.GetRight()):.2f} "
                  f"y {mm(bb.GetTop()):.2f}..{mm(bb.GetBottom()):.2f} ({fp.GetReference()})")
for d in b.GetDrawings():
    if d.GetLayer() not in (pcbnew.F_SilkS, pcbnew.B_SilkS):
        continue
    bb = d.GetBoundingBox()
    if mm(bb.GetRight()) < X0 or mm(bb.GetLeft()) > X1:
        continue
    if mm(bb.GetBottom()) < Y0 or mm(bb.GetTop()) > Y1:
        continue
    l = b.GetLayerName(d.GetLayer())
    if d.GetClass() == 'PTEXT':
        p = d.GetPosition()
        print(f"  BOARD TEXT '{d.GetText()}' at ({mm(p.x):.3f},{mm(p.y):.3f}) "
              f"or={d.GetTextAngleDegrees():.0f} layer={l} "
              f"bbox x {mm(bb.GetLeft()):.2f}..{mm(bb.GetRight()):.2f} "
              f"y {mm(bb.GetTop()):.2f}..{mm(bb.GetBottom()):.2f}")
    else:
        l = b.GetLayerName(d.GetLayer())
        if d.GetClass() == 'PCB_TEXT':
            p = d.GetPosition()
            print(f"  BOARD TEXT '{d.GetText()}' at ({mm(p.x):.3f},{mm(p.y):.3f}) "
                  f"or={d.GetTextAngleDegrees():.0f} layer={l} "
                  f"bbox x {mm(bb.GetLeft()):.2f}..{mm(bb.GetRight()):.2f} "
                  f"y {mm(bb.GetTop()):.2f}..{mm(bb.GetBottom()):.2f}")
        else:
            print(f"  BOARD {d.GetShapeStr():8s} layer={l} bbox x {mm(bb.GetLeft()):.2f}..{mm(bb.GetRight()):.2f} "
                  f"y {mm(bb.GetTop()):.2f}..{mm(bb.GetBottom()):.2f}")

print("\n" + "=" * 72)
print("COPPER (track/via/pad) a teruleten")
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA':
        p = t.GetPosition()
        if inb(mm(p.x), mm(p.y)):
            print(f"  VIA ({mm(p.x):.3f},{mm(p.y):.3f}) "
                  f"dia={mm(t.GetWidth()):.2f} net='{t.GetNetname()}'")
        continue
    s = t.GetStart(); e = t.GetEnd()
    if inb(mm(s.x), mm(s.y)) or inb(mm(e.x), mm(e.y)):
        print(f"  TRACK {b.GetLayerName(t.GetLayer()):6s} "
              f"({mm(s.x):.3f},{mm(s.y):.3f}) -> ({mm(e.x):.3f},{mm(e.y):.3f}) "
              f"w={mm(t.GetWidth()):.2f} net='{t.GetNetname()}'")

print("\n" + "=" * 72)
print("PAD-ek a teruleten")
for fp in b.GetFootprints():
    for pad in fp.Pads():
        p = pad.GetPosition()
        if inb(mm(p.x), mm(p.y)):
            bb = pad.GetBoundingBox()
            print(f"  {fp.GetReference():6s} pad'{pad.GetNumber()}' "
                  f"({mm(p.x):.3f},{mm(p.y):.3f}) net='{pad.GetNetname()}' "
                  f"bbox x {mm(bb.GetLeft()):.3f}..{mm(bb.GetRight()):.3f} "
                  f"y {mm(bb.GetTop()):.3f}..{mm(bb.GetBottom()):.3f}")
