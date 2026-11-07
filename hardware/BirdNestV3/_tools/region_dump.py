#!/usr/bin/env python3
"""Reszletes objektumtérkep egy PCB-rectangelben (read-only).

Kiirja: footprint-ek (udvar, pad), track-ek, viak, zónák, silk, board text.
"""
import sys
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
U = 1e6


def bb(item):
    b = item.GetBoundingBox()
    return (b.GetLeft() / U, b.GetTop() / U, b.GetRight() / U, b.GetBottom() / U)


def inr(x0, y0, x1, y1, X0, Y0, X1, Y1):
    return not (x1 < X0 or x0 > X1 or y1 < Y0 or y0 > Y1)


def main():
    X0, Y0, X1, Y1 = (float(v) for v in sys.argv[1:5])
    bd = pcbnew.LoadBoard(PCB)
    print(f'REGION x {X0}..{X1}  y {Y0}..{Y1}\n')

    print('--- FOOTPRINTS (udvar / padok) ---')
    for fp in bd.GetFootprints():
        p = fp.GetPosition()
        px, py = p.x / U, p.y / U
        if not (X0 - 12 <= px <= X1 + 12 and Y0 - 12 <= py <= Y1 + 12):
            continue
        cb = (0.0, 0.0, 0.0, 0.0)
        try:
            cy = fp.GetCourtyard(pcbnew.F_CrtYd)
            bb2 = cy.Outline(0).BBox()
            cb = (bb2.GetLeft() / U, bb2.GetTop() / U,
                  bb2.GetRight() / U, bb2.GetBottom() / U)
        except Exception:
            for gr in fp.GraphicalItems():
                if gr.GetLayerName() == 'F.Courtyard':
                    b = bb(gr)
                    cb = (min(cb[0], b[0]), min(cb[1], b[1]),
                          max(cb[2], b[2]), max(cb[3], b[3]))
        inreg = inr(*cb, X0, Y0, X1, Y1)
        print(f'{fp.GetReference():8s} lib={fp.GetFPIDAsString():38s} '
              f'orig=({px:.3f},{py:.3f}) rot={fp.GetOrientationDegrees()} '
              f'crtyd=({cb[0]:.2f},{cb[1]:.2f})-({cb[2]:.2f},{cb[3]:.2f})'
              f'{"  <== A TERULETEN" if inreg else ""}')
        for pad in fp.Pads():
            b = bb(pad)
            if not inr(*b, X0, Y0, X1, Y1):
                continue
            n = pad.GetNetname()
            print(f'    pad{pad.GetNumber():>3s} {pad.GetShape():2d} '
                  f'({b[0]:.2f},{b[1]:.2f})-({b[2]:.2f},{b[3]:.2f}) '
                  f'sz={pad.GetSize().x/U:.2f}x{pad.GetSize().y/U:.2f} '
                  f'net={n!r} layer={pad.GetLayerSet().FmtHex()}')

    print('\n--- TRACKS ---')
    for t in bd.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            b = bb(t)
            if not inr(*b, X0, Y0, X1, Y1):
                continue
            print(f'  VIA   ({b[0]:.3f},{b[1]:.3f})-({b[2]:.3f},{b[3]:.3f}) '
                  f'd={t.GetWidth()/U:.2f} net={t.GetNetname()!r} '
                  f'layers={t.GetLayerSet().FmtHex()}')
            continue
        s = t.GetStart()
        e = t.GetEnd()
        x0, y0 = s.x / U, s.y / U
        x1, y1 = e.x / U, e.y / U
        if not inr(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1),
                   X0, Y0, X1, Y1):
            continue
        print(f'  TRK   ({x0:.3f},{y0:.3f})->({x1:.3f},{y1:.3f}) '
              f'w={t.GetWidth()/U:.2f} net={t.GetNetname()!r} '
              f'layer={t.GetLayerName()}')

    print('\n--- ZONES ---')
    for z in bd.Zones():
        b = z.GetBoundingBox()
        if not inr(b.GetLeft() / U, b.GetTop() / U, b.GetRight() / U,
                   b.GetBottom() / U, X0, Y0, X1, Y1):
            continue
        print(f'  ZONE net={z.GetNetname()!r} layers={z.GetLayerSet().FmtHex()} '
              f'bbox=({b.GetLeft()/U:.2f},{b.GetTop()/U:.2f})-'
              f'({b.GetRight()/U:.2f},{b.GetBottom()/U:.2f}) filled={z.IsFilled()}')

    print('\n--- BOARD DRAWINGS (silk / text) ---')
    for d in bd.GetDrawings():
        b = bb(d)
        if not inr(*b, X0, Y0, X1, Y1):
            continue
        txt = ''
        if hasattr(d, 'GetText'):
            txt = f' text={d.GetText()!r}'
        print(f'  {type(d).__name__:14s} ({b[0]:.2f},{b[1]:.2f})-'
              f'({b[2]:.2f},{b[3]:.2f}) layer={d.GetLayerName()}{txt}')

    print('\n--- FOOTPRINT SILK GRAPHICS ---')
    for fp in bd.GetFootprints():
        p = fp.GetPosition()
        px, py = p.x / U, p.y / U
        if not (X0 - 12 <= px <= X1 + 12 and Y0 - 12 <= py <= Y1 + 12):
            continue
        for gr in fp.GraphicalItems():
            b = bb(gr)
            if not inr(*b, X0, Y0, X1, Y1):
                continue
            if gr.GetLayerName() not in ('F.Silkscreen', 'B.Silkscreen'):
                continue
            print(f'  {fp.GetReference():6s} {type(gr).__name__:12s} '
                  f'({b[0]:.2f},{b[1]:.2f})-({b[2]:.2f},{b[3]:.2f}) '
                  f'layer={gr.GetLayerName()}')


if __name__ == '__main__':
    main()
