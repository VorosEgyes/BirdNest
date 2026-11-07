#!/usr/bin/env python3
"""A hat lyuk maszk-allapotának ellenorzese a PCB-n."""
import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'


def mm(v):
    return pcbnew.ToMM(v)


b = pcbnew.LoadBoard(PCB)
for ref in ('H1', 'H2', 'H3', 'H4', 'H5', 'H6'):
    fp = b.FindFootprintByReference(ref)
    for p in fp.Pads():
        pos = p.GetPosition()
        print("{}: pad ({:.3f},{:.3f}) drill {:.2f} size {:.2f}  F.Mask={}  B.Mask={}  NPTH={}".format(
            ref, mm(pos.x), mm(pos.y), mm(p.GetDrillSizeX()), mm(p.GetSizeX()),
            p.IsOnLayer(pcbnew.F_Mask), p.IsOnLayer(pcbnew.B_Mask),
            p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH))
