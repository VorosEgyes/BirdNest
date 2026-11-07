#!/usr/bin/env python3
"""Ground truth a napelem-bemenet korul: D9, D10, J4, Net-(D10-A).

Read-only: nem modosit semmit.
"""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
U = 1e6


def main():
    bd = pcbnew.LoadBoard(PCB)

    print('=== D9 / D10 / J4 padok ===')
    for ref in ('D9', 'D10', 'J4'):
        fp = bd.FindFootprintByReference(ref)
        if fp is None:
            print(f'  {ref}: NINCS')
            continue
        pos = fp.GetPosition()
        print(f'\n  {ref} origo ({pos.x/U:.3f},{pos.y/U:.3f}) '
              f'rot {fp.GetOrientationDegrees()}')
        for p in fp.Pads():
            pp = p.GetPosition()
            print(f'    pad{p.GetNumber()}: ({pp.x/U:.3f},{pp.y/U:.3f}) '
                  f'size {p.GetSizeX()/U:.3f}x{p.GetSizeY()/U:.3f} '
                  f'net={p.GetNetname()!r} '
                  f'maskmargin={p.GetLocalSolderMaskMargin()}')

    print('\n=== Net-(D10-A) trackek/vias/padok ===')
    net = None
    for n in bd.GetNetsByName():
        if n.GetNetname() == 'Net-(D10-A)':
            net = n
    print('  net kod:', net.GetNetCode() if net else 'NINCS')
    for t in bd.GetTracks():
        if t.GetNetname() != 'Net-(D10-A)':
            continue
        if t.GetClass() == 'PCB_VIA':
            p = t.GetPosition()
            print(f'    VIA ({p.x/U:.3f},{p.y/U:.3f})')
        else:
            s, e = t.GetStart(), t.GetEnd()
            print(f'    TRACK ({s.x/U:.3f},{s.y/U:.3f}) -> '
                  f'({e.x/U:.3f},{e.y/U:.3f}) {t.GetLayerName()} '
                  f'w={t.GetWidth()/U:.3f}')

    print('\n=== minden zoned (net, layer, bbox) ===')
    for z in bd.Zones():
        ns = z.GetLayerSet().Seq()
        names = [bd.GetLayerName(l) for l in ns]
        b = z.GetBoundingBox()
        nn = z.GetNetname()
        print(f'  net={nn!r} layers={names} '
              f'bbox=({b.GetLeft()/U:.2f},{b.GetTop()/U:.2f})-'
              f'({b.GetRight()/U:.2f},{b.GetBottom()/U:.2f})')

    print('\n=== a D10 padjaihoz kozeli nyomok (x 190..200, y 76..88) ===')
    for t in bd.GetTracks():
        if t.GetClass() == 'PCB_VIA':
            continue
        s, e = t.GetStart(), t.GetEnd()
        if not (188 <= s.x/U <= 202 and 74 <= s.y/U <= 90):
            continue
        print(f'    {t.GetNetname()!r} {t.GetLayerName()} '
              f'({s.x/U:.3f},{s.y/U:.3f})->({e.x/U:.3f},{e.y/U:.3f}) '
              f'w={t.GetWidth()/U:.3f}')

    print('\n=== GND zonalapanyag a D9 kornyeken (x 184..200, y 95..115) ===')
    for z in bd.Zones():
        if z.GetNetname() != 'GND':
            continue
        b = z.GetBoundingBox()
        print(f'  GND zone bbox=({b.GetLeft()/U:.2f},{b.GetTop()/U:.2f})-'
              f'({b.GetRight()/U:.2f},{b.GetBottom()/U:.2f}) '
              f'layers={[bd.GetLayerName(l) for l in z.GetLayerSet().Seq()]}')


if __name__ == '__main__':
    main()
