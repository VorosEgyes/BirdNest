#!/usr/bin/env python3
"""A J4/D9/D10 korner teljes objektumterkepe hálózatonkent (read-only)."""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
U = 1e6

X0, X1 = 176.0, 201.0
Y0, Y1 = 78.0, 116.0


def main():
    bd = pcbnew.LoadBoard(PCB)

    print('=== footprintek a teruleten (x 176..201, y 78..116) ===')
    for fp in bd.GetFootprints():
        b = fp.GetBoundingBox()
        if b.GetRight() / U < X0 or b.GetLeft() / U > X1:
            continue
        if b.GetBottom() / U < Y0 or b.GetTop() / U > Y1:
            continue
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        cb = ''
        if cy and cy.OutlineCount():
            c = cy.BBox()
            cb = (f'udvar=({c.GetLeft()/U:.2f},{c.GetTop()/U:.2f})-'
                  f'({c.GetRight()/U:.2f},{c.GetBottom()/U:.2f})')
        p = fp.GetPosition()
        print(f'  {fp.GetReference():5} origo=({p.x/U:.3f},{p.y/U:.3f}) '
              f'rot={fp.GetOrientationDegrees():.0f} {cb}')
        for pad in fp.Pads():
            pp = pad.GetPosition()
            print(f'      pad{pad.GetNumber()}: ({pp.x/U:.3f},{pp.y/U:.3f}) '
                  f'{pad.GetSizeX()/U:.2f}x{pad.GetSizeY()/U:.2f} '
                  f'net={pad.GetNetname()!r}')

    print('\n=== trackek/vias a teruleten ===')
    rows = []
    for t in bd.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            p = t.GetPosition()
            if X0 <= p.x / U <= X1 and Y0 <= p.y / U <= Y1:
                rows.append(f'  VIA  ({p.x/U:.3f},{p.y/U:.3f}) '
                            f'net={t.GetNetname()!r} '
                            f'sz={t.GetWidth()/U:.2f} '
                            f'drill={t.GetDrillValue()/U:.2f}')
            continue
        s, e = t.GetStart(), t.GetEnd()
        if not (X0 <= s.x / U <= X1 and Y0 <= s.y / U <= Y1):
            continue
        rows.append(f'  TRK  ({s.x/U:.3f},{s.y/U:.3f})->({e.x/U:.3f},'
                    f'{e.y/U:.3f}) {t.GetLayerName()} w={t.GetWidth()/U:.2f} '
                    f'net={t.GetNetname()!r}')
    print('\n'.join(rows))

    print('\n=== board-level grafikak (szoveg/line) a teruleten ===')
    for d in bd.GetDrawings():
        b = d.GetBoundingBox()
        if b.GetRight() / U < X0 or b.GetLeft() / U > X1:
            continue
        if b.GetBottom() / U < Y0 or b.GetTop() / U > Y1:
            continue
        txt = d.GetText() if hasattr(d, 'GetText') else ''
        print(f'  {d.GetClassName():14} layer={d.GetLayerName():14} '
              f'bbox=({b.GetLeft()/U:.2f},{b.GetTop()/U:.2f})-'
              f'({b.GetRight()/U:.2f},{b.GetBottom()/U:.2f}) {txt!r}')

    print('\n=== D_SMA footprint courtyard ket D9 helyen (rot 0) ===')
    # a D_SMA udvar: x -3.5..3.5, y -1.75..1.75 (origin-hoz kepest)
    for cx, cy in ((189.75, 100.25), (189.75, 99.75), (188.75, 100.25)):
        print(f'  origo ({cx},{cy}): udvar '
              f'({cx-3.5},{cy-1.75})-({cx+3.5},{cy+1.75})  '
              f'pad1=({cx-2},{cy}) pad2=({cx+2},{cy})')


if __name__ == '__main__':
    main()
