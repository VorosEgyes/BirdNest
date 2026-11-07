#!/usr/bin/env python3
"""Szem vizualis szabadhely-térkep a J4 kornerre es a TP-zonara.

Minden cella 0,25 mm. A cella 'foglalt', ha:
  - footprint udvar (courtyard) fedi,
  - pad vagy via fedi,
  - F.Cu/B.Cu nyom fedi,
  - F.SilkS/B.SilkS vonal vagy szoveg fedi.

A nyom es a pad 0,2 mm clearance-rel marad, ezert a raszter a
nyomok melletti keskeny sávot is foglaltnak jelzi.
"""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
U = 1e6
CELL = 0.25
CLR = 0.20          # a copper clearance, amit a raszter betart


class Grid:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = x0, y0
        self.nx = int((x1 - x0) / CELL)
        self.ny = int((y1 - y0) / CELL)
        self.c = {}

    def put(self, xa, ya, xb, yb, ch):
        i0 = int((min(xa, xb) - self.x0) / CELL)
        i1 = int((max(xa, xb) - self.x0) / CELL)
        j0 = int((min(ya, yb) - self.y0) / CELL)
        j1 = int((max(ya, yb) - self.y0) / CELL)
        for j in range(max(0, j0), min(self.ny, j1 + 1)):
            for i in range(max(0, i0), min(self.nx, i1 + 1)):
                self.c[(i, j)] = ch

    def get(self, x, y):
        return self.c.get((int((x - self.x0) / CELL),
                           int((y - self.y0) / CELL)), '.')

    def free_rect(self, xa, ya, xb, yb, chars):
        """True, ha a téglalap minden cellaja szabad"""
        for j in range(int((ya - self.y0) / CELL),
                       int((yb - self.y0) / CELL) + 1):
            for i in range(int((xa - self.x0) / CELL),
                           int((xb - self.x0) / CELL) + 1):
                if self.get(self.x0 + i * CELL, self.y0 + j * CELL) in chars:
                    return False
        return True


def bb(item, grow=0.0):
    b = item if isinstance(item, pcbnew.BOX2I) else item.GetBoundingBox()
    return (b.GetLeft() / U - grow, b.GetTop() / U - grow,
            b.GetRight() / U + grow, b.GetBottom() / U + grow)


def main():
    bd = pcbnew.LoadBoard(PCB)

    g = Grid(172.0, 76.0, 201.0, 118.0)

    # udvarok
    for fp in bd.GetFootprints():
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy and cy.OutlineCount():
            b = bb(cy.BBox())
            g.put(b[0], b[1], b[2], b[3], 'C')
    # padok es vias
    for fp in bd.GetFootprints():
        for p in fp.Pads():
            b = bb(p, CLR)
            g.put(b[0], b[1], b[2], b[3], 'P')
    for t in bd.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            p = t.GetPosition()
            g.put(p.x / U - 0.6, p.y / U - 0.6,
                  p.x / U + 0.6, p.y / U + 0.6, 'V')
        else:
            s, e = t.GetStart(), t.GetEnd()
            b = bb(t, CLR + t.GetWidth() / U / 2)
            g.put(b[0], b[1], b[2], b[3], 'T')
    # silk
    for fp in bd.GetFootprints():
        for gr in fp.GraphicalItems():
            if gr.GetLayerName() in ('F.Silkscreen', 'B.Silkscreen'):
                b = bb(gr, 0.1)
                g.put(b[0], b[1], b[2], b[3], 'S')
        if fp.Reference().IsVisible():
            b = bb(fp.Reference(), 0.1)
            g.put(b[0], b[1], b[2], b[3], 'R')
    for d in bd.GetDrawings():
        if d.GetLayerName() in ('F.Silkscreen', 'B.Silkscreen'):
            b = bb(d, 0.1)
            g.put(b[0], b[1], b[2], b[3], 'S')

    print('### J4 korner (x 172..201, y 76..118) ###')
    header = []
    for i in range(g.nx):
        x = g.x0 + i * CELL
        header.append(str(int(x // 10) % 10) if abs(x % 10) < 0.13 else ' ')
    print('    ' + ''.join(header))
    for j in range(g.ny):
        row = ''.join(g.get(g.x0 + i * CELL, g.y0 + j * CELL)
                      for i in range(g.nx))
        if j % 2 == 0:
            print(f'{g.y0 + j * CELL:6.1f} {row}')

    # a D9 helyeinek keresese
    print('\n### A D9 (D_SMA, 7.0 x 3.5 mm udvar) lehetséges helyei ###')
    print('  (a nyomok es a padok mellett tartott clearance is szamit)')
    for rot, (w, h) in ((0, (7.0, 3.5)), (90, (3.5, 7.0))):
        best = []
        y = 78.0
        while y < 117.0:
            x = 176.0
            while x < 200.0:
                if g.free_rect(x, y, x + w, y + h, 'CPVT'):
                    d1 = ((x + w / 2 - 189.673) ** 2
                          + (y + h / 2 - 110.545) ** 2) ** 0.5
                    d2 = ((x + w / 2 - 189.673) ** 2
                          + (y + h / 2 - 105.465) ** 2) ** 0.5
                    best.append((min(d1, d2), max(d1, d2), x, y, rot))
                x += 0.25
            y += 0.25
        best.sort()
        print(f'  rot {rot}:')
        for d in best[:6]:
            print(f'    origo ({d[2]:.2f},{d[3]:.2f})  '
                  f'kozeli pad {d[0]:.2f} mm, tavoli pad {d[1]:.2f} mm')

    # a TP-k koruli szabad hely a feliratokhoz
    print('\n### TP1..TP5 koruleti szabad hely (0,8 mm-es felirat) ###')
    for ref in ('TP1', 'TP2', 'TP3', 'TP4', 'TP5'):
        fp = bd.FindFootprintByReference(ref)
        p = fp.GetPosition()
        px, py = p.x / U, p.y / U
        print(f'  {ref} pad ({px:.3f},{py:.3f}) net={fp.Pads()[0].GetNetname()!r}')
        for name, w, h in (('netnev 1.0mm', 5.0, 1.0), ('netnev 0.8mm', 4.0, 0.8)):
            spots = []
            for ang in (0, 90):
                ww, hh = (w, h) if ang == 0 else (h, w)
                for ang2 in range(0, 360, 30):
                    dx = 4.0 * __import__('math').cos(
                        __import__('math').radians(ang2))
                    dy = 4.0 * __import__('math').sin(
                        __import__('math').radians(ang2))
                    cx, cy = px + dx, py + dy
                    xa, ya = cx - ww / 2, cy - hh / 2
                    if g.free_rect(xa, ya, xa + ww, ya + hh, 'CPVTS'):
                        spots.append((ang2, round(cx, 2), round(cy, 2)))
            if spots:
                print(f'    {name}: ' + ', '.join(
                    f'{a}deg ({x},{y})' for a, x, y in spots[:6]))
            else:
                print(f'    {name}: nincs hely 5 mm-re')


if __name__ == '__main__':
    main()
