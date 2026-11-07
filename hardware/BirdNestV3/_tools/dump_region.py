import pcbnew
import sys

path = sys.argv[1] if len(sys.argv) > 1 else '../BirdNestV3.kicad_pcb'
x0, y0, x1, y1 = 176.0, 71.0, 197.0, 100.0
M = 1e6
b = pcbnew.LoadBoard(path)


def f(v):
    return '%8.3f' % (v / M)


print('=== PADS in x %.1f..%.1f y %.1f..%.1f ===' % (x0, y0, x1, y1))
rows = []
for fp in b.GetFootprints():
    r = fp.GetReference()
    for p in fp.Pads():
        bb = p.GetBoundingBox()
        px0, py0 = bb.GetX() / M, bb.GetY() / M
        px1, py1 = px0 + bb.GetWidth() / M, py0 + bb.GetHeight() / M
        if px1 < x0 or px0 > x1 or py1 < y0 or py0 > y1:
            continue
        rows.append((py0, '%-5s.%-2s %-15s %-5s x %7.3f..%7.3f y %7.3f..%7.3f ctr(%7.3f,%7.3f)'
                     % (r, p.GetNumber(), p.GetNetname(), p.GetLayerName(),
                        px0, px1, py0, py1, p.GetPosition().x / M, p.GetPosition().y / M)))
for _, t in sorted(rows):
    print(t)

print()
print('=== TRACKS / VIAS in region ===')
for t in sorted(b.GetTracks(), key=lambda t: (t.GetLayer(), t.GetStart().y)):
    a, e = t.GetStart(), t.GetEnd()
    ax, ay, ex, ey = a.x / M, a.y / M, e.x / M, e.y / M
    if max(ax, ex) < x0 or min(ax, ex) > x1 or max(ay, ey) < y0 or min(ay, ey) > y1:
        continue
    lay = 'F' if t.GetLayer() == pcbnew.F_Cu else ('B' if t.GetLayer() == pcbnew.B_Cu else t.GetLayerName())
    if t.GetClass() == 'PCB_VIA':
        print('VIA %s %-15s (%7.3f,%7.3f) d=%.3f' % (lay, t.GetNetname(), ax, ay, t.GetWidth() / M))
    else:
        print('TRK %s %-15s (%7.3f,%7.3f)->(%7.3f,%7.3f) w=%.3f'
              % (lay, t.GetNetname(), ax, ay, ex, ey, t.GetWidth() / M))

print()
print('=== FOOTPRINT POSITIONS in region ===')
for fp in b.GetFootprints():
    p = fp.GetPosition()
    if not (x0 <= p.x / M <= x1 and y0 <= p.y / M <= y1):
        continue
    print('%-6s (%8.3f,%8.3f) rot=%5.1f  %s' % (fp.GetReference(), p.x / M, p.y / M,
                                                fp.GetOrientationDegrees(), fp.GetValue()))
