#!/usr/bin/env python3
"""A stat-hálózatok (/CHG_STAT, /DONE_STAT, Net-(D7-A)) ujrarajzolasa
a BirdNestV3-on, plusz a /BAT_PROT+ hurk es a Net-(U11-TEMP) atvezetes
atiranyitasa, hogy a U11 jobb oszlopa kihorgadhasson.

Usage:  apply_stat.py <in.kicad_pcb> <out.kicad_pcb>
A script a bemeneti fajlbol dolgozik, es a kimeneti fajlba ir (teszthez).
"""
import sys
import pcbnew

F = pcbnew.F_Cu
B = pcbnew.B_Cu

# ---------------------------------------------------------------- remove
# (net, layer, x1, y1, x2, y2) -- a BAT_PROT+ hurk resze
REMOVE_SEG = [
    ('/BAT_PROT+', F, 182.375, 89.025, 183.300, 89.025),
    ('/BAT_PROT+', F, 183.300, 89.025, 183.300, 90.525),
    ('/BAT_PROT+', F, 183.300, 90.525, 182.375, 90.525),
]
# ezeket a neteket teljesen ujrarajzoljuk
REMOVE_NET_ALL = ['Net-(U11-TEMP)', 'Net-(D7-A)']

# ---------------------------------------------------------------- add
# (net, layer, width, x1, y1, x2, y2)
ADD_SEG = [
    # --- /BAT_PROT+: a 8-as pin es a B.Cu torony osszekotese via-n keresztul
    ('/BAT_PROT+', F, 0.2, 182.375, 89.025, 182.375, 88.400),
    ('/BAT_PROT+', F, 0.2, 182.375, 88.400, 183.100, 88.400),
    ('/BAT_PROT+', B, 0.2, 183.100, 88.400, 183.100, 91.500),
    # --- Net-(U11-TEMP): U11.1 -> R14.2 felett, TH1.2-re B.Cu-n
    ('Net-(U11-TEMP)', F, 0.2, 179.675, 89.025, 179.675, 86.600),
    ('Net-(U11-TEMP)', F, 0.2, 179.675, 86.600, 186.155, 86.600),
    ('Net-(U11-TEMP)', F, 0.2, 186.155, 86.600, 186.155, 88.425),
    ('Net-(U11-TEMP)', F, 0.2, 184.700, 86.600, 184.700, 88.850),
    ('Net-(U11-TEMP)', B, 0.2, 184.700, 88.850, 185.155, 93.200),
    ('Net-(U11-TEMP)', F, 0.2, 185.155, 93.200, 185.155, 94.425),
    # --- /CHG_STAT: U11.7 -> D8.1
    ('/CHG_STAT', F, 0.2, 182.375, 89.525, 187.600, 89.525),
    ('/CHG_STAT', F, 0.2, 187.600, 89.525, 187.600, 84.500),
    ('/CHG_STAT', F, 0.2, 187.600, 84.500, 185.900, 84.500),
    ('/CHG_STAT', F, 0.2, 185.900, 84.500, 185.900, 83.025),
    # --- /DONE_STAT: U11.6 -> D7.1
    ('/DONE_STAT', F, 0.2, 182.375, 90.025, 188.100, 90.025),
    ('/DONE_STAT', F, 0.2, 188.100, 90.025, 188.100, 83.025),
    # --- Net-(D7-A): D8.2 + D7.2 -> R13.1 (B.Cu-n a nyugati koridorban)
    ('Net-(D7-A)', F, 0.2, 185.900, 80.975, 185.900, 79.800),
    ('Net-(D7-A)', F, 0.2, 185.900, 79.800, 189.400, 79.800),
    ('Net-(D7-A)', F, 0.2, 188.100, 80.975, 188.100, 79.800),
    ('Net-(D7-A)', B, 0.2, 189.400, 79.800, 175.000, 79.800),
    ('Net-(D7-A)', B, 0.2, 175.000, 79.800, 175.000, 97.025),
    ('Net-(D7-A)', B, 0.2, 175.000, 97.025, 176.155, 97.025),
]

# (net, x, y)
ADD_VIA = [
    ('/BAT_PROT+', 183.100, 88.400),
    ('Net-(U11-TEMP)', 184.700, 88.850),
    ('Net-(U11-TEMP)', 185.155, 93.200),
    ('Net-(D7-A)', 189.400, 79.800),
    ('Net-(D7-A)', 176.155, 97.025),
]

VIA_D = 0.6
VIA_DRILL = 0.3
TOL = 2  # um


def key(x1, y1, x2, y2):
    a = (round(x1 * 1000), round(y1 * 1000))
    b = (round(x2 * 1000), round(y2 * 1000))
    return (min(a, b), max(a, b))


def main():
    src, dst = sys.argv[1], sys.argv[2]
    board = pcbnew.LoadBoard(src)
    mm = pcbnew.ToMM

    # --- remove segments
    rm_keys = {}
    for net, lay, x1, y1, x2, y2 in REMOVE_SEG:
        rm_keys.setdefault(net, set()).add((lay, key(x1, y1, x2, y2)))

    doomed = []
    for t in board.GetTracks():
        net = t.GetNetname()
        if net in REMOVE_NET_ALL:
            doomed.append(t)
            continue
        if net in rm_keys:
            a, c = t.GetStart(), t.GetEnd()
            k = (t.GetLayer(), key(mm(a.x), mm(a.y), mm(c.x), mm(c.y)))
            if k in rm_keys[net]:
                doomed.append(t)
    for t in doomed:
        board.Remove(t)
    print(f"removed {len(doomed)} copper items")

    # --- add tracks
    added = 0
    for net, lay, w, x1, y1, x2, y2 in ADD_SEG:
        tr = pcbnew.PCB_TRACK(board)
        tr.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))
        tr.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))
        tr.SetWidth(pcbnew.FromMM(w))
        tr.SetLayer(lay)
        tr.SetNetCode(board.GetNetcodeFromNetname(net))
        board.Add(tr)
        added += 1
    for net, x, y in ADD_VIA:
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        via.SetWidth(pcbnew.FromMM(VIA_D))
        via.SetDrill(pcbnew.FromMM(VIA_DRILL))
        via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(F, B)
        via.SetNetCode(board.GetNetcodeFromNetname(net))
        board.Add(via)
        added += 1
    print(f"added {added} copper items")

    # --- zone refill
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())

    board.Save(dst)
    print(f"saved {dst}")


if __name__ == '__main__':
    main()
