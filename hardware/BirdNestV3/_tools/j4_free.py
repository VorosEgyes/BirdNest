#!/usr/bin/env python3
"""Read-only: a J4 korner minden eleme egy szabadelmes boxban, hogy a
D9 uj helyet tervezni lehessen. Kiirja a szabad teruleteket is.
"""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
BOX = (160.0, 90.0, 200.5, 118.0)     # xmin, ymin, xmax, ymax


def main():
    bd = pcbnew.LoadBoard(PCB)
    U = 1e6

    def inbox(x, y):
        return BOX[0] <= x <= BOX[2] and BOX[1] <= y <= BOX[3]

    print('### FOOTPRINTS ###')
    for fp in bd.GetFootprints():
        p = fp.GetPosition()
        if not inbox(p.x / U, p.y / U):
            continue
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        cbb = cy.BBox() if cy and cy.OutlineCount() else None
        c = ''
        if cbb:
            c = (f"crtyd x {cbb.GetX()/U:7.3f}..{cbb.GetRight()/U:7.3f}"
                 f" y {cbb.GetY()/U:7.3f}..{cbb.GetBottom()/U:7.3f}")
        print(f'  {fp.GetReference():<6} ({p.x/U:8.3f},{p.y/U:8.3f}) '
              f'rot={fp.GetOrientationDegrees():5.1f} {c}')
        for pad in fp.Pads():
            pp = pad.GetPosition()
            print(f'      pad{pad.GetNumber():<3} net={pad.GetNetname()!r:<18} '
                  f'({pp.x/U:8.3f},{pp.y/U:8.3f}) '
                  f'sz={pad.GetSizeX()/U:.2f}x{pad.GetSizeY()/U:.2f} '
                  f'{pad.GetAttribute()}')

    print('\n### F.Cu / B.Cu TRACKS es VIAS ###')
    for t in bd.GetTracks():
        s = t.GetStart()
        e = t.GetEnd()
        if t.GetClass() == 'PCB_VIA':
            if inbox(s.x / U, s.y / U):
                print(f'  VIA  ({s.x/U:8.3f},{s.y/U:8.3f}) net={t.GetNetname()!r}')
            continue
        if inbox(s.x / U, s.y / U) or inbox(e.x / U, e.y / U):
            print(f'  TRK {bd.GetLayerName(t.GetLayer()):<6} '
                  f'({s.x/U:8.3f},{s.y/U:8.3f})->({e.x/U:8.3f},{e.y/U:8.3f}) '
                  f'w={t.GetWidth()/U:.2f} net={t.GetNetname()!r}')

    print('\n### SILK GRAPHICS es TEXTEK ###')
    for d in bd.GetDrawings():
        cls = d.GetClass()
        if cls not in ('PCB_TEXT', 'PCB_SHAPE'):
            continue
        p = d.GetPosition()
        if not inbox(p.x / U, p.y / U):
            continue
        bb = d.GetBoundingBox()
        extra = ''
        if cls == 'PCB_TEXT':
            extra = f'text={d.GetText()!r}'
        else:
            extra = f'shape={d.GetShape()}'
        print(f'  {cls:<9} {extra:<22} layer={bd.GetLayerName(d.GetLayer()):<12} '
              f'at ({p.x/U:8.3f},{p.y/U:8.3f}) '
              f'bbox x {bb.GetX()/U:7.3f}..{bb.GetRight()/U:7.3f} '
              f'y {bb.GetY()/U:7.3f}..{bb.GetBottom()/U:7.3f}')

    print('\n### ZONES ###')
    for z in bd.Zones():
        zbb = z.GetBoundingBox()
        if zbb.GetRight() / U < BOX[0] or zbb.GetX() / U > BOX[2]:
            continue
        print(f'  ZONE net={z.GetNetname()!r} layers={z.GetLayerSet().FmtHex()} '
              f'x {zbb.GetX()/U:.2f}..{zbb.GetRight()/U:.2f} '
              f'y {zbb.GetY()/U:.2f}..{zbb.GetBottom()/U:.2f} '
              f'filled={z.IsFilled()}')

    print('\n### NETCLASS (clearance) ###')
    nc = bd.GetDesignSettings().m_NetSettings
    for n in nc.GetDefaultNetclass():
        print(f'  default: clearance={n.GetClearance()/U:.3f} '
              f'trackw={n.GetTrackWidth()/U:.3f} '
              f'via={n.GetViaDiameter()/U:.3f}/{n.GetViaDrill()/U:.3f}')
    for n in nc.GetNetClasses():
        print(f'  netclass {n.GetName()!r}: '
              f'clearance={n.GetClearance()/U:.3f} trackw={n.GetTrackWidth()/U:.3f}')


if __name__ == '__main__':
    main()
