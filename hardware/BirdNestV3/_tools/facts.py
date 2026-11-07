#!/usr/bin/env python3
"""Kombinealt tenykep: D10/Net-(D10-A) bekotes + TP-zona teljes terkep.

Read-only.
"""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
U = 1e6


def main():
    bd = pcbnew.LoadBoard(PCB)

    print('=== zoned a PCB-ben ===')
    for z in bd.Zones():
        ls = [bd.GetLayerName(l) for l in z.GetLayerSet().Seq()]
        b = z.GetBoundingBox()
        print(f'  net={z.GetNetname()!r} layers={ls} '
              f'bbox=({b.GetLeft()/U:.2f},{b.GetTop()/U:.2f})-'
              f'({b.GetRight()/U:.2f},{b.GetBottom()/U:.2f}) '
              f'priority={z.GetAssignedPriority()}')

    print('\n=== Net-(D10-A) minden eleme ===')
    for t in bd.GetTracks():
        if t.GetNetname() == 'Net-(D10-A)':
            s, e = t.GetStart(), t.GetEnd()
            print(f'  TRK ({s.x/U:.3f},{s.y/U:.3f})->({e.x/U:.3f},'
                  f'{e.y/U:.3f}) {t.GetLayerName()} w={t.GetWidth()/U:.3f}')
    for fp in bd.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == 'Net-(D10-A)':
                pp = p.GetPosition()
                print(f'  PAD {fp.GetReference()}.{p.GetNumber()} '
                      f'({pp.x/U:.3f},{pp.y/U:.3f}) '
                      f'{p.GetSizeX()/U:.2f}x{p.GetSizeY()/U:.2f}')

    print('\n=== GND nyomok a J4 korul (x 185..200, y 95..116) ===')
    for t in bd.GetTracks():
        if t.GetNetname() != 'GND' or t.GetClass() == 'PCB_VIA':
            continue
        s, e = t.GetStart(), t.GetEnd()
        if not (185 <= s.x/U <= 200 and 95 <= s.y/U <= 116):
            continue
        print(f'  TRK ({s.x/U:.3f},{s.y/U:.3f})->({e.x/U:.3f},'
              f'{e.y/U:.3f}) {t.GetLayerName()} w={t.GetWidth()/U:.3f}')

    print('\n=== TP-zona: footprintek (x 95..125, y 38..65) ===')
    for fp in bd.GetFootprints():
        b = fp.GetBoundingBox()
        if b.GetRight() / U < 95 or b.GetLeft() / U > 125:
            continue
        if b.GetBottom() / U < 38 or b.GetTop() / U > 65:
            continue
        p = fp.GetPosition()
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        cb = ''
        if cy and cy.OutlineCount():
            c = cy.BBox()
            cb = (f'udvar=({c.GetLeft()/U:.2f},{c.GetTop()/U:.2f})-'
                  f'({c.GetRight()/U:.2f},{c.GetBottom()/U:.2f})')
        print(f'  {fp.GetReference():6} origo=({p.x/U:.3f},{p.y/U:.3f}) '
              f'rot={fp.GetOrientationDegrees():.0f} {cb}')
        for pad in fp.Pads():
            pp = pad.GetPosition()
            print(f'        pad{pad.GetNumber()}: ({pp.x/U:.3f},{pp.y/U:.3f}) '
                  f'{pad.GetSizeX()/U:.2f}x{pad.GetSizeY()/U:.2f} '
                  f'net={pad.GetNetname()!r}')
        for gr in fp.GraphicalItems():
            if gr.GetLayerName() in ('F.Silkscreen', 'B.Silkscreen'):
                gb = gr.GetBoundingBox()
                print(f'        silk {type(gr).__name__:12} '
                      f'({gb.GetLeft()/U:.2f},{gb.GetTop()/U:.2f})-'
                      f'({gb.GetRight()/U:.2f},{gb.GetBottom()/U:.2f})')
        r = fp.Reference()
        rb = r.GetBoundingBox()
        print(f'        ref  ({rb.GetLeft()/U:.2f},{rb.GetTop()/U:.2f})-'
              f'({rb.GetRight()/U:.2f},{rb.GetBottom()/U:.2f}) '
              f'pos=({r.GetPosition().x/U:.3f},{r.GetPosition().y/U:.3f}) '
              f'layer={r.GetLayerName()}')

    print('\n=== TP-zona: trackek/vias (x 95..125, y 38..65) ===')
    for t in bd.GetTracks():
        s = t.GetStart()
        if not (95 <= s.x/U <= 125 and 38 <= s.y/U <= 65):
            continue
        if t.GetClass() == 'PCB_VIA':
            print(f'  VIA ({s.x/U:.3f},{s.y/U:.3f}) net={t.GetNetname()!r}')
        else:
            e = t.GetEnd()
            print(f'  TRK ({s.x/U:.3f},{s.y/U:.3f})->({e.x/U:.3f},'
                  f'{e.y/U:.3f}) {t.GetLayerName()} w={t.GetWidth()/U:.2f} '
                  f'net={t.GetNetname()!r}')

    print('\n=== TP-zona: board-level szovegek ===')
    for d in bd.GetDrawings():
        b = d.GetBoundingBox()
        if b.GetRight() / U < 95 or b.GetLeft() / U > 125:
            continue
        if b.GetBottom() / U < 38 or b.GetTop() / U > 65:
            continue
        print(f'  {type(d).__name__:12} layer={d.GetLayerName():14} '
              f'({b.GetLeft()/U:.2f},{b.GetTop()/U:.2f})-'
              f'({b.GetRight()/U:.2f},{b.GetBottom()/U:.2f}) '
              f'{d.GetText() if hasattr(d, "GetText") else ""!r}')


if __name__ == '__main__':
    main()
