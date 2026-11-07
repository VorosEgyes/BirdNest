import pcbnew
import sys

b = pcbnew.LoadBoard('../BirdNestV3.kicad_pcb')
MM = 1e6


def fmt(v):
    return '%.3f' % (v / MM)


print('=== PADS D7 D8 (after move) ===')
for fp in b.GetFootprints():
    r = fp.GetReference()
    if r not in ('D7', 'D8'):
        continue
    print('%s centroid=(%s,%s) rot=%s' % (r, fmt(fp.GetPosition().x), fmt(fp.GetPosition().y),
                                         fp.GetOrientationDegrees()))
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        print('   pad %s net=%-14s pos=(%s,%s) size=(%.3f,%.3f) rot=%s layer=%s '
              'bb x %s..%s y %s..%s localclear=%s' % (
                  p.GetNumber(), p.GetNetname(), fmt(p.GetPosition().x), fmt(p.GetPosition().y),
                  p.GetSize().x / MM, p.GetSize().y / MM, p.GetOrientationDegrees(),
                  p.GetLayerName(), fmt(bb.GetX()), fmt(bb.GetX() + bb.GetWidth()),
                  fmt(bb.GetY()), fmt(bb.GetY() + bb.GetHeight()),
                  fmt(p.GetLocalClearance() if p.GetLocalClearance() is not None else 0)))

print()
print('=== COURTYARDS (bbox) ===')
for fp in b.GetFootprints():
    r = fp.GetReference()
    if r not in ('J1', 'J2', 'J3', 'D7', 'D8', 'D9', 'D10', 'R14', 'C25', 'C24', 'U11', 'TH1', 'R13', 'R12'):
        continue
    try:
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        cs = 'x %s..%s y %s..%s' % (fmt(bb.GetX()), fmt(bb.GetX() + bb.GetWidth()),
                                    fmt(bb.GetY()), fmt(bb.GetY() + bb.GetHeight()))
    except Exception as e:
        cs = 'ERR %s' % e
    print('%-5s pos=(%s,%s) rot=%-5s %s' % (r, fmt(fp.GetPosition().x), fmt(fp.GetPosition().y),
                                             fp.GetOrientationDegrees(), cs))

print()
print('=== BOARD EDGE ===')
for d in b.GetDrawings():
    if d.GetLayerName() == 'Edge.Cuts':
        bb = d.GetBoundingBox()
        print('edge x %s..%s y %s..%s' % (fmt(bb.GetX()), fmt(bb.GetX() + bb.GetWidth()),
                                          fmt(bb.GetY()), fmt(bb.GetY() + bb.GetHeight())))

print()
print('=== NET CLASS CLEARANCES ===')
nets = ('/CHG_STAT', '/DONE_STAT', 'Net-(D7-A)', '/BAT_PROT+', 'Net-(U11-TEMP)', 'GND', '/VIN_PROT')
for code, ni in b.GetNetsByNetcode().items():
    if ni.GetNetname() not in nets:
        continue
    nc = b.FindNetClass(ni.GetNetname())
    print('%-14s class=%-12s track=%.3f clearance=%.3f via=%.3f' % (
        ni.GetNetname(), nc.GetName(), nc.GetTrackWidth() / MM,
        nc.GetClearance() / MM, nc.GetViaDiameter() / MM))
