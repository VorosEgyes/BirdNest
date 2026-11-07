#!/usr/bin/env python3
"""Read-only ground truth: a J4 / D9 / D10 korner teljes terkepe + a TP-k allapotja.

Kitartja a foldereket, vonalakat, zonzakat, silk elemeket es a footprint
udvarakat egy bounding box-ban, hogy a helyre tetele tervezheto legyen.
"""
import sys
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'

BOX = (178.0, 76.0, 200.5, 118.0)   # xmin, ymin, xmax, ymax


def in_box(x, y, b=BOX):
    return b[0] <= x <= b[2] and b[1] <= y <= b[3]


def near(bb, b=BOX):
    if bb is None:
        return False
    x1, y1 = bb.GetX(), bb.GetY()
    x2, y2 = bb.GetRight(), bb.GetBottom()
    return not (x2 < b[0] or x1 > b[2] or y2 < b[1] or y1 > b[3])


def main():
    bd = pcbnew.LoadBoard(PCB)

    print('=' * 78)
    print('BOARD EDGE (bbox):', bd.GetBoardEdgesBoundingBox())
    print('=' * 78)

    # ---- footprint-ek a boxban, udvarral ---------------------------
    print('\n### FOOTPRINTS a boxban (ref, pos, orient, courtyard) ###')
    fps = []
    for fp in bd.GetFootprints():
        try:
            ref = fp.GetReference()
        except Exception:
            continue
        pos = fp.GetPosition()
        if not (in_box(pos.x / 1e6, pos.y / 1e6, BOX)):
            continue
        cy = fp.GetCourtyard(pcbnew.F_CrtYd)
        cbb = None
        if cy and cy.OutlineCount() > 0:
            cbb = cy.BBox()
        fps.append((ref, pos, fp, cbb))
    for ref, pos, fp, cbb in sorted(fps, key=lambda t: (t[1].y, t[1].x)):
        cy = ''
        if cbb:
            cy = (f"  crtyd x {cbb.GetX()/1e6:7.3f}..{cbb.GetRight()/1e6:7.3f}"
                  f"  y {cbb.GetY()/1e6:7.3f}..{cbb.GetBottom()/1e6:7.3f}")
        print(f'  {ref:<8} ({pos.x/1e6:8.3f},{pos.y/1e6:8.3f}) '
              f'rot={fp.GetOrientationDegrees():5.1f}{cy}')

    # ---- a D9 és D10 footprint definicioja -------------------------
    print('\n### D9 (D_SMA) padok ###')
    for fp in bd.GetFootprints():
        if fp.GetReference() not in ('D9', 'D10'):
            continue
        p = fp.GetPosition()
        print(f'  {fp.GetReference()}  ({p.x/1e6:.3f},{p.y/1e6:.3f}) '
              f'rot={fp.GetOrientationDegrees()}  value={fp.GetValue()!r}')
        for pad in fp.Pads():
            pp = pad.GetPosition()
            print(f'      pad {pad.GetNumber()!r} net={pad.GetNetname()!r:<18} '
                  f'local=({pp.x/1e6:.3f},{pp.y/1e6:.3f}) '
                  f'size={pad.GetSizeX()/1e6:.3f}x{pad.GetSizeY()/1e6:.3f} '
                  f'shape={pad.GetShape()}')

    # ---- trackek, vias, zonzak -------------------------------------
    print('\n### TRACKS / VIAS a boxban ###')
    for t in bd.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            p = t.GetPosition()
            if in_box(p.x / 1e6, p.y / 1e6):
                print(f'  VIA   ({p.x/1e6:8.3f},{p.y/1e6:8.3f}) '
                      f'net={t.GetNetname()!r}')
            continue
        s = t.GetStart()
        e = t.GetEnd()
        if in_box(s.x / 1e6, s.y / 1e6) or in_box(e.x / 1e6, e.y / 1e6):
            print(f'  TRK {bd.GetLayerName(t.GetLayer()):<6} '
                  f'({s.x/1e6:8.3f},{s.y/1e6:8.3f})->({e.x/1e6:8.3f},{e.y/1e6:8.3f}) '
                  f'w={t.GetWidth()/1e6:.2f} net={t.GetNetname()!r}')

    print('\n### ZONES a boxban ###')
    for z in bd.Zones():
        zbb = z.GetBoundingBox()
        if near(zbb):
            print(f'  ZONE net={z.GetNetname()!r} layers={z.GetLayerSet().FmtHex()} '
                  f'bbox x {zbb.GetX()/1e6:.2f}..{zbb.GetRight()/1e6:.2f} '
                  f'y {zbb.GetY()/1e6:.2f}..{zbb.GetBottom()/1e6:.2f} '
                  f'filled={z.IsFilled()}')

    # ---- silk elemek (szovegek) a boxban --------------------------
    print('\n### SILK TEXTEK a boxban ###')
    for d in bd.GetDrawings():
        try:
            if d.GetClass() != 'PCB_TEXT':
                continue
        except Exception:
            continue
        p = d.GetPosition()
        if not in_box(p.x / 1e6, p.y / 1e6):
            continue
        bb = d.GetBoundingBox()
        print(f'  TEXT {d.GetText()!r:<12} at ({p.x/1e6:7.3f},{p.y/1e6:7.3f}) '
              f'ang={d.GetTextAngleDegrees():5.1f} '
              f'layer={bd.GetLayerName(d.GetLayer())} '
              f'bbox x {bb.GetX()/1e6:.3f}..{bb.GetRight()/1e6:.3f} '
              f'y {bb.GetY()/1e6:.3f}..{bb.GetBottom()/1e6:.3f}')

    # ---- maszk aperturak a TP-k kornyeken -------------------------
    print('\n### TESTPOINT-ok allapotja ###')
    for fp in bd.GetFootprints():
        try:
            ref = fp.GetReference()
        except Exception:
            continue
        if not ref.startswith('TP'):
            continue
        p = fp.GetPosition()
        print(f'  {ref:<5} ({p.x/1e6:8.3f},{p.y/1e6:8.3f}) '
              f'rot={fp.GetOrientationDegrees():5.1f} value={fp.GetValue()!r}')
        for pad in fp.Pads():
            pp = pad.GetPosition()
            print(f'      pad {pad.GetNumber()!r} net={pad.GetNetname()!r:<18} '
                  f'size={pad.GetSizeX()/1e6:.3f}x{pad.GetSizeY()/1e6:.3f} '
                  f'mask={pad.GetLocalSolderMaskMargin()/1e6:.3f}')
        for f in fp.GetFields():
            if f.GetClass() != 'PCB_FIELD':
                continue
            fp2 = f.GetPosition()
            bb = f.GetBoundingBox()
            print(f'      field {f.GetName()!r}={f.GetText()!r:<8} '
                  f'layer={bd.GetLayerName(f.GetLayer())} '
                  f'visible={f.IsVisible()} '
                  f'at ({fp2.x/1e6:.3f},{fp2.y/1e6:.3f}) '
                  f'bbox x {bb.GetX()/1e6:.3f}..{bb.GetRight()/1e6:.3f} '
                  f'y {bb.GetY()/1e6:.3f}..{bb.GetBottom()/1e6:.3f}')


if __name__ == '__main__':
    main()
