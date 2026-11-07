#!/usr/bin/env python3
"""Read-only: a TP1..TP5 testpointok teljes allapotja + maszk/silk
koruleti elemek a kornyukon. A 'atlathatosag' ellenorizesehez.
"""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
U = 1e6


def main():
    bd = pcbnew.LoadBoard(PCB)

    tps = []
    for fp in bd.GetFootprints():
        try:
            ref = fp.GetReference()
        except Exception:
            continue
        if ref.startswith('TP'):
            tps.append(fp)

    print('### TESTPOINT FOOTPRINTS ###')
    for fp in sorted(tps, key=lambda f: f.GetReference()):
        p = fp.GetPosition()
        print(f'\n{fp.GetReference()}  ({p.x/U:.3f},{p.y/U:.3f}) '
              f'rot={fp.GetOrientationDegrees()}  value={fp.GetValue()!r} '
              f'lib={fp.GetFPIDAsString()}')
        for pad in fp.Pads():
            pp = pad.GetPosition()
            bb = pad.GetBoundingBox()
            mm = pad.GetLocalSolderMaskMargin()
            mm = 0.0 if mm is None else mm / U
            print(f'    pad{pad.GetNumber()} net={pad.GetNetname()!r:<16} '
                  f'({pp.x/U:.3f},{pp.y/U:.3f}) sz={pad.GetSizeX()/U:.2f}x'
                  f'{pad.GetSizeY()/U:.2f} attr={pad.GetAttribute()} '
                  f'maskmargin={mm:.3f} '
                  f'bbox x {bb.GetX()/U:.3f}..{bb.GetRight()/U:.3f} '
                  f'y {bb.GetY()/U:.3f}..{bb.GetBottom()/U:.3f}')
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        if cy and cy.OutlineCount():
            cb = cy.BBox()
            print(f'    crtyd x {cb.GetX()/U:.3f}..{cb.GetRight()/U:.3f} '
                  f'y {cb.GetY()/U:.3f}..{cb.GetBottom()/U:.3f}')
        for f in fp.GetFields():
            if f.GetClass() != 'PCB_FIELD':
                continue
            fp2 = f.GetPosition()
            bb = f.GetBoundingBox()
            print(f'    field {f.GetName()!r}={f.GetText()!r:<8} '
                  f'layer={bd.GetLayerName(f.GetLayer()):<12} '
                  f'visible={f.IsVisible()} '
                  f'({fp2.x/U:.3f},{fp2.y/U:.3f}) '
                  f'bbox x {bb.GetX()/U:.3f}..{bb.GetRight()/U:.3f} '
                  f'y {bb.GetY()/U:.3f}..{bb.GetBottom()/U:.3f}')
        for g in fp.GraphicalItems():
            if g.GetClass() != 'PCB_SHAPE':
                continue
            bb = g.GetBoundingBox()
            print(f'    silk {g.GetShape()} layer={bd.GetLayerName(g.GetLayer())} '
                  f'bbox x {bb.GetX()/U:.3f}..{bb.GetRight()/U:.3f} '
                  f'y {bb.GetY()/U:.3f}..{bb.GetBottom()/U:.3f}')

    print('\n### MASZK APERTURA meretek (F.Mask gerberbol) ###')
    # a maszk nyilasok merete a pad merete + mask margin; itt a
    # solder mask minimum aperture szabályt ellenorizzuk
    ds = bd.GetDesignSettings()
    print(f'  solder_mask_min_width = {ds.m_SolderMaskMinWidth/U:.3f} mm')
    print(f'  solder_mask_margin    = {ds.m_SolderMaskMargin/U:.3f} mm')

    print('\n### A TP-k korneken levo MASZKKONYVONAL (F.Mask) elemek ###')
    # a F.Mask gerozin vonalak a padok korul
    for fp in sorted(tps, key=lambda f: f.GetReference()):
        p = fp.GetPosition()
        for pad in fp.Pads():
            pp = pad.GetPosition()
            print(f'  {fp.GetReference()} pad{pad.GetNumber()} '
                  f'({pp.x/U:.3f},{pp.y/U:.3f}) '
                  f'-> maszk nyilas várható '
                  f'{pad.GetSizeX()/U:.3f}x{pad.GetSizeY()/U:.3f} mm '
                  f'(margin {pad.GetLocalSolderMaskMargin()/U:.3f})')


if __name__ == '__main__':
    main()
