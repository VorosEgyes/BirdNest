#!/usr/bin/env python3
"""Ground truth a J4/D9/zona koruletekre pcbnew-vel (read-only)."""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
b = pcbnew.LoadBoard(PCB)

def mm(v):
    return v / 1e6

def net_of(item):
    n = item.GetNetname()
    return n

print("=" * 70)
print("TABLA SZEL")
bb = b.GetBoardEdgesBoundingBox()
print(f"  x {mm(bb.GetLeft()):.3f} .. {mm(bb.GetRight()):.3f}")
print(f"  y {mm(bb.GetTop()):.3f} .. {mm(bb.GetBottom()):.3f}")

print("\n" + "=" * 70)
print("J4, D9, D10, BT3 PADOK")
for ref in ('J4', 'D9', 'D10', 'BT3', 'J2'):
    fp = b.FindFootprintByReference(ref)
    if fp is None:
        print(f"  {ref}: NINCS")
        continue
    p = fp.GetPosition()
    print(f"\n  {ref} ({fp.GetFPIDAsString()}) at ({mm(p.x):.3f},{mm(p.y):.3f}) "
          f"orient={fp.GetOrientationDegrees():.0f} value='{fp.GetValue()}'")
    for pad in fp.Pads():
        pp = pad.GetPosition()
        bb2 = pad.GetBoundingBox()
        print(f"    pad '{pad.GetNumber()}' net='{net_of(pad)}' "
              f"at ({mm(pp.x):.3f},{mm(pp.y):.3f}) "
              f"size {mm(pad.GetSizeX()):.2f}x{mm(pad.GetSizeY()):.2f} "
              f"bbox x {mm(bb2.GetLeft()):.3f}..{mm(bb2.GetRight()):.3f} "
              f"y {mm(bb2.GetTop()):.3f}..{mm(bb2.GetBottom()):.3f}")
    # courtyard
    try:
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        poly = cy.Outline()
        xs = [mm(poly.CPoint(i).x) for i in range(poly.PointCount())]
        ys = [mm(poly.CPoint(i).y) for i in range(poly.PointCount())]
        print(f"    udvar: x {min(xs):.3f}..{max(xs):.3f}  y {min(ys):.3f}..{max(ys):.3f}")
    except Exception as e:
        print(f"    udvar hiba: {e}")

print("\n" + "=" * 70)
print("ZONAK a teruleten (x 182..200, y 92..126)")
def in_zone(z, x, y):
    px = pcbnew.VECTOR2I(int(x * 1e6), int(y * 1e6))
    try:
        return z.HitTestFilledArea(px)
    except Exception:
        return None

for z in b.Zones():
    if z.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
        continue
    lay = 'F.Cu' if z.GetLayer() == pcbnew.F_Cu else 'B.Cu'
    bb3 = z.GetBoundingBox()
    if mm(bb3.GetRight()) < 182 or mm(bb3.GetLeft()) > 200:
        continue
    if mm(bb3.GetBottom()) < 92 or mm(bb3.GetTop()) > 126:
        continue
    print(f"  zóna net='{z.GetNetname()}' layer={lay} "
          f"bbox x {mm(bb3.GetLeft()):.2f}..{mm(bb3.GetRight()):.2f} "
          f"y {mm(bb3.GetTop()):.2f}..{mm(bb3.GetBottom()):.2f} "
          f"pad_connect={z.GetPadConnection()}")
    for (tx, ty) in ((196.9, 110.5), (196.9, 114.5), (196.9, 118.5),
                      (197.5, 108.0), (195.0, 110.5), (194.0, 108.0)):
        r = in_zone(z, tx, ty)
        print(f"      pont ({tx},{ty}) benne van: {r}")

print("\n" + "=" * 70)
print("MINDEN FOOTPRINT a x 190..200, y 92..126 sávban")
for fp in b.GetFootprints():
    p = fp.GetPosition()
    if 190 <= mm(p.x) <= 200 and 92 <= mm(p.y) <= 126:
        print(f"  {fp.GetReference():6s} ({mm(p.x):.3f},{mm(p.y):.3f}) {fp.GetFPIDAsString()}")

print("\n" + "=" * 70)
print("SILK gr_text globalis koordinatak (F.SilkS)")
for d in b.GetDrawings():
    if d.GetClass() == 'PTEXT':
        p = d.GetPosition()
        if 190 <= mm(p.x) <= 200 and 92 <= mm(p.y) <= 126:
            print(f"  '{d.GetText()}' at ({mm(p.x):.3f},{mm(p.y):.3f}) "
                  f"orient={d.GetTextAngleDegrees():.0f} size={mm(d.GetTextWidth()):.2f}")
