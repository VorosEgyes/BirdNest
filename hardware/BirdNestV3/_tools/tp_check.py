#!/usr/bin/env python3
"""A testpointok maszk-allapotának, cimkeinek és kornyezetenek vizsgalata,
plusz a D9 uj tipusának konyvtaradatai."""
import os

import pcbnew

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'
SYM = '/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/Diode.kicad_sym'


def mm(v):
    return pcbnew.ToMM(v)


b = pcbnew.LoadBoard(PCB)

print("=== a testpointok padjai es cimkeik ===")
for ref in ('TP1', 'TP2', 'TP3', 'TP4', 'TP5'):
    fp = b.FindFootprintByReference(ref)
    pos = fp.GetPosition()
    rf = fp.Reference()
    rpos = rf.GetPosition()
    print("\n{} at ({:.3f},{:.3f})  net={}".format(
        ref, mm(pos.x), mm(pos.y),
        [p.GetNetname() for p in fp.Pads()]))
    print("   cimke: '{}' layer={} lathato={} at ({:.3f},{:.3f}) magassag={:.2f}".format(
        rf.GetText(), rf.GetLayerName(), rf.IsVisible(),
        mm(rpos.x), mm(rpos.y), mm(rf.GetTextHeight())))
    for p in fp.Pads():
        pp = p.GetPosition()
        print("   pad {} at ({:.3f},{:.3f}) size {:.2f} F.Mask={} B.Mask={}".format(
            p.GetNumber(), mm(pp.x), mm(pp.y), mm(p.GetSizeX()),
            p.IsOnLayer(pcbnew.F_Mask), p.IsOnLayer(pcbnew.B_Mask)))
    # a sajat silk koron
    for g in list(fp.GraphicalItems()):
        if g.GetLayerName() in ('F.Silkscreen', 'B.Silkscreen'):
            s = g.GetStart()
            print("   silk {} at ({:.3f},{:.3f})".format(
                g.GetClass(), mm(s.x), mm(s.y)))

print("\n=== a SMAJ szimbulumok a KiCad konyvtaraban ===")
txt = open(SYM).read()
import re
names = re.findall(r'\(symbol "([^"]*SMAJ[^"]*)"', txt)
print("   ", sorted(set(names)))
