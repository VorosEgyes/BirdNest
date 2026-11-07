#!/usr/bin/env python3
"""A TP-zona szabadhely-térkep: hol lehet a TP-k feliratot (netnev) elhelyezni.

A 'netnev' egy 1.0 mm-es, 5.0 mm szeles felirat (a hosszu netnevek,
pl. /VIN_PROT, /SYS_PWR, /REF2V5 ehhez ilyen hosszusra jonnek).
A 'ref' a TP sajat tervszama, 1.0 mm magas.
A 'pad' a 3 mm-es maszk-nyilas, ezt egyetlen semmi nem takarhatja.
"""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
U = 1e6
CELL = 0.25
CLR = 0.20

BOX = (98.0, 38.0, 122.0, 62.0)


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

    def free(self, xa, ya, xb, yb, chars):
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
    g = Grid(*BOX)

    for fp in bd.GetFootprints():
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy and cy.OutlineCount():
            b = bb(cy.BBox())
            g.put(b[0], b[1], b[2], b[3], 'C')
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
            b = bb(t, CLR + t.GetWidth() / U / 2)
            g.put(b[0], b[1], b[2], b[3], 'T')
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

    print('### TP-zona (x 98..122, y 38..62) ###')
    hdr = []
    for i in range(g.nx):
        x = g.x0 + i * CELL
        hdr.append(str(int(x // 10) % 10) if abs(x % 10) < 0.13 else ' ')
    print('    ' + ''.join(hdr))
    for j in range(g.ny):
        row = ''.join(g.get(g.x0 + i * CELL, g.y0 + j * CELL)
                      for i in range(g.nx))
        if j % 2 == 0:
            print(f'{g.y0 + j * CELL:6.1f} {row}')
    print('  C=udvar P=pad V=via T=nyom S=silk R=terv')

    print('\n### a netnev felirat helyei ###')
    for ref in ('TP1', 'TP2', 'TP3', 'TP4', 'TP5'):
        fp = bd.FindFootprintByReference(ref)
        p = fp.GetPosition()
        px, py = p.x / U, p.y / U
        net = fp.Pads()[0].GetNetname()
        print(f'\n  {ref} pad ({px:.3f},{py:.3f}) net={net!r}')
        # a maszk-nyilas (3 mm-es kor) semmit nem takarhat
        ok = []
        for ang in range(0, 360, 15):
            import math
            for r in (3.6, 4.2, 5.0, 5.8):
                dx = r * math.cos(math.radians(ang))
                dy = r * math.sin(math.radians(ang))
                cx, cy = px + dx, py + dy
                xa, ya = cx - 2.5, cy - 0.5
                if g.free(xa, ya, xa + 5.0, ya + 1.0, 'CPVTS'):
                    ok.append((ang, r, round(cx, 2), round(cy, 2)))
        # a legkisebb sugaru, legkisebb szognel levo helyek
        seen = {}
        for ang, r, cx, cy in ok:
            if r not in seen:
                seen[r] = []
            seen[r].append((ang, cx, cy))
        for r in sorted(seen):
            lst = seen[r][:8]
            print(f'    r={r}: ' + ', '.join(
                f'{a}deg({x},{y})' for a, x, y in lst))

    print('\n### a TP sajat tervszamainak helye ###')
    for ref in ('TP1', 'TP2', 'TP3', 'TP4', 'TP5'):
        fp = bd.FindFootprintByReference(ref)
        p = fp.GetPosition()
        t = fp.Reference()
        tp = t.GetPosition()
        dist = (((tp.x - p.x) / U) ** 2 + ((tp.y - p.y) / U) ** 2) ** 0.5
        print(f'  {ref}: pad ({p.x/U:.3f},{p.y/U:.3f}) '
              f'ref ({tp.x/U:.3f},{tp.y/U:.3f}) '
              f'tavolsag {dist:.2f} mm')


if __name__ == '__main__':
    main()
