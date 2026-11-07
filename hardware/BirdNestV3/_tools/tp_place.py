#!/usr/bin/env python3
"""A TP-k feliratainak (netnev + tervszam) helykerese, valodi bbox-meresel.

A maszk-nyilas (kitett rez) es a meglevo silk felgrafikak az utkozesek;
az udvar NEM utkozes (csak a maszk-nyilas es a maszk feletti silk szamit).

Read-only.
"""
import json
import math
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
U = 1e6
PAD_CLR = 0.20      # silk -> maszk-nyilas
SILK_CLR = 0.15     # silk -> silk
HOLE_CLR = 0.25     # silk -> furat

NET_LABEL_SIZE = 0.8
REF_SIZE = 1.0

NETS = {
    'TP1': 'GND',
    'TP2': 'VIN_PROT',
    'TP3': 'SYS_PWR',
    'TP4': '+5V',
    'TP5': 'REF2V5',
}


class Ob:
    def __init__(self):
        self.b = []

    def add(self, x0, y0, x1, y1, kind):
        self.b.append((x0, y0, x1, y1, kind))

    def hit(self, x0, y0, x1, y1):
        for a0, b0, a1, b1, kind in self.b:
            g = {'PAD': PAD_CLR, 'HOLE': HOLE_CLR}.get(kind, SILK_CLR)
            if (x0 - g < a1 and x1 + g > a0 and
                    y0 - g < b1 and y1 + g > b0):
                return kind
        return None


def bbox(item):
    b = item.GetBoundingBox()
    return (b.GetLeft() / U, b.GetTop() / U, b.GetRight() / U, b.GetBottom() / U)


def measure(bd, text, size, x, y):
    t = pcbnew.PCB_TEXT(bd)
    t.SetText(text)
    t.SetTextSize(pcbnew.VECTOR2I(int(size * U), int(size * U)))
    t.SetTextThickness(int(0.12 * U))
    t.SetLayer(pcbnew.F_SilkS)
    t.SetPosition(pcbnew.VECTOR2I(int(x * U), int(y * U)))
    bd.Add(t)
    b = t.GetBoundingBox()
    bb = (b.GetLeft() / U, b.GetTop() / U, b.GetRight() / U, b.GetBottom() / U)
    bd.Remove(t)
    return bb


def center(bb):
    return ((bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2)


def main():
    bd = pcbnew.LoadBoard(PCB)
    ob = Ob()

    # a tabla hatarai (silk nem mehet le a szelere)
    for d in bd.GetDrawings():
        if d.GetLayerName() == 'Edge.Cuts':
            b = bbox(d)
            ob.add(b[0] - 0.2, b[1] - 0.2, b[2] + 0.2, b[3] + 0.2, 'EDGE')
            break

    # maszk-nyilasok
    for fp in bd.GetFootprints():
        for p in fp.Pads():
            b = bbox(p)
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
                ob.add(b[0], b[1], b[2], b[3], 'HOLE')
            else:
                ob.add(b[0], b[1], b[2], b[3], 'PAD')

    # meglevo silk
    for fp in bd.GetFootprints():
        for gr in fp.GraphicalItems():
            if gr.GetLayerName() in ('F.Silkscreen', 'B.Silkscreen'):
                b = bbox(gr)
                ob.add(b[0], b[1], b[2], b[3], 'SILK')
        for fld in (fp.Reference(), fp.Value()):
            if fld.IsVisible():
                b = bbox(fld)
                ob.add(b[0], b[1], b[2], b[3], 'SILKTEXT')
    for d in bd.GetDrawings():
        if d.GetLayerName() in ('F.Silkscreen', 'B.Silkscreen'):
            b = bbox(d)
            ob.add(b[0], b[1], b[2], b[3], 'SILKTEXT')

    out = {}
    for ref in ('TP1', 'TP2', 'TP3', 'TP4', 'TP5'):
        fp = bd.FindFootprintByReference(ref)
        p = fp.GetPosition()
        px, py = p.x / U, p.y / U
        net = NETS[ref]

        # a TP sajat regi feliratait nem tekintjuk utkozesnek
        own = []
        for fld in (fp.Reference(), fp.Value()):
            if fld.IsVisible():
                own.append(bbox(fld))

        def free(bb, skip_own=True):
            for a0, b0, a1, b1 in own:
                if (bb[0] < a1 and bb[2] > a0 and bb[1] < b1 and bb[3] > b0):
                    if not skip_own:
                        return False
            return ob.hit(bb[0], bb[1], bb[2], bb[3]) is None

        # --- netnev ---
        best = None
        for ang in range(0, 360, 5):
            for r in [x / 2 for x in range(6, 15)]:
                cx = px + r * math.cos(math.radians(ang))
                cy = py + r * math.sin(math.radians(ang))
                bb = measure(bd, net, NET_LABEL_SIZE, cx, cy)
                ccx, ccy = center(bb)
                bb = measure(bd, net, NET_LABEL_SIZE, ccx, ccy)
                if not free(bb):
                    continue
                d = ((ccx - px) ** 2 + (ccy - py) ** 2) ** 0.5
                if best is None or d < best[0]:
                    best = (d, ccx, ccy, bb)
        # --- tervszam (a pad kozeleben) ---
        bestr = None
        for ang in range(0, 360, 5):
            for r in (2.4, 2.6, 2.8, 3.0, 3.2, 3.4):
                cx = px + r * math.cos(math.radians(ang))
                cy = py + r * math.sin(math.radians(ang))
                bb = measure(bd, ref, REF_SIZE, cx, cy)
                ccx, ccy = center(bb)
                bb = measure(bd, ref, REF_SIZE, ccx, ccy)
                if not free(bb):
                    continue
                if best is None or r < bestr[0] if bestr else True:
                    bestr = (r, ccx, ccy, bb)
        if bestr is not None and best is not None:
            # a ketto ne menjen egymasba
            _, rx, ry, rbb = bestr
            _, nx, ny, nbb = best
            if (rbb[0] < nbb[2] and rbb[2] > nbb[0] and
                    rbb[1] < nbb[3] and rbb[3] > nbb[1]):
                bestr = None

        print(f'{ref}: netnev={net!r} '
              f'@ ({best[1]:.3f},{best[2]:.3f}) d={best[0]:.2f} '
              f'bbox=({best[3][0]:.2f},{best[3][1]:.2f})-({best[3][2]:.2f},{best[3][3]:.2f})')
        if bestr:
            print(f'      tervszam @ ({bestr[1]:.3f},{bestr[2]:.3f}) '
                  f'd={bestr[0]:.2f} '
                  f'bbox=({bestr[3][0]:.2f},{bestr[3][1]:.2f})-'
                  f'({bestr[3][2]:.2f},{bestr[3][3]:.2f})')
        else:
            print('      tervszam: NINCS HELY a pad mellett')

        out[ref] = {
            'origin': (px, py),
            'net_text': net,
            'net_pos': (best[1], best[2]),
            'net_bbox': best[3],
            'ref_pos': (bestr[1], bestr[2]) if bestr else None,
            'ref_bbox': bestr[3] if bestr else None,
        }
        if bestr:
            ob.add(bestr[3][0], bestr[3][1], bestr[3][2], bestr[3][3], 'SILKTEXT')
        ob.add(best[3][0], best[3][1], best[3][2], best[3][3], 'SILKTEXT')

    json.dump(out, open('/tmp/tp_places.json', 'w'), indent=2)
    print('\n-> /tmp/tp_places.json')


if __name__ == '__main__':
    main()
