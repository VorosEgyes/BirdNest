#!/usr/bin/env python3
"""A D9 TVS athelyezese a J4 napelem-bemenet melle, SMAJ6.0CA tipusra valtasval.

A J4 (Phoenix MKDS-1,5-2-5.08) pad1 = Solarpanel+ a (189.673, 110.545),
pad2 = GND a (189.673, 105.465); az udvara x 183.938..194.798, y 102.390..113.610.
A D9 a J4 felett, a csatlakozohoz kozel (x 187..194, y 97.25..100.75) kerul:
  - panel pad (pad2) a J4 pad1-hez megy, egy rovid visszahajlo nyommal;
  - GND pad (pad1) a J4 GND tuskerehez megy (azonos csonk: a TVS visszater
    a csatlakozo GND labjan keresztul folyik a GND zoneba);
  - a D9 masik labja a D10 (SS34) anode felole megy.
Azas szalagban (x 194.8..200) a napelem vezeteke fut, oda nem kerul alkatresz.
"""
import re
import uuid

PCB = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb'

# --- uj helyek ---
D9_AT = (191.0, 99.5)          # a D9 footprinte uj origója, rot 0
D9_ROT = 0
J4_PANEL = (189.673, 110.545)  # J4.1 Solarpanel+
J4_GND = (189.673, 105.465)    # J4.2 GND
D10_A = (196.07, 81.275)       # D10 pad2 (panel oldal)
D9_PANEL = (193.0, 99.5)       # D9 pad2 globalis helye
D9_GND = (189.0, 99.5)         # D9 pad1 globalis helye
STUB_X = 196.07                # a D10 felett meno panel nyom

NEW_VALUE = 'SMAJ6.0CA'
NEW_DESC = '400W bidirectional Transient Voltage Suppressor, 6.0Vr, SMA(DO-214AC)'


def uid():
    return str(uuid.uuid4())


def segment(start, end, net, width=0.25, layer='F.Cu'):
    return (f'\n\t(segment\n'
            f'\t\t(start {start[0]} {start[1]})\n'
            f'\t\t(end {end[0]} {end[1]})\n'
            f'\t\t(width {width})\n'
            f'\t\t(layer "{layer}")\n'
            f'\t\t(net "{net}")\n'
            f'\t\t(uuid "{uid()}")\n'
            f'\t)\n')


def main():
    txt = open(PCB).read()
    orig = txt

    # ------------------------------------------------------------------
    # 1. a regi Net-(D10-A) nyomok torlese
    # ------------------------------------------------------------------
    removed = 0
    for m in list(re.finditer(r'\n\t\(segment\n(?:\t\t[^\n]*\n)*?\t\)\n', txt)):
        if '(net "Net-(D10-A)")' in m.group(0):
            txt = txt[:m.start()] + txt[m.end():]
            removed += 1
    print(f"  torolt Net-(D10-A) nyom: {removed}")

    # ------------------------------------------------------------------
    # 2. a D9 footprint athelyezese es a tipus frissitese
    # ------------------------------------------------------------------
    m = re.search(r'\n\t\(footprint "Diode_SMD:D_SMA"[\s\S]*?\n\t\)\n', txt)
    assert m, 'a D9 footprint nem talalhato'
    d9 = m.group(0)
    new = d9

    # az at ... (a footprint orientacioja)
    new, n = re.subn(r'\(at [-\d\.]+ [-\d\.]+ [-\d\.]+\)',
                     f'(at {D9_AT[0]} {D9_AT[1]} {D9_ROT})', new, count=1)
    assert n == 1, 'a D9 at nem modosult'

    # a Value es a Description
    new, n1 = re.subn(r'\(property "Value" "[^"]*"', f'(property "Value" "{NEW_VALUE}"', new, count=1)
    new, n2 = re.subn(r'\(property "Description" "[^"]*"',
                      f'(property "Description" "{NEW_DESC}"', new, count=1)
    assert n1 == 1 and n2 == 1, 'a D9 property nem modosult'

    # a referencia szoveg helye: a footprint-hoz kepest balra, hogy a
    # szomszedos Net-(U11-TEMP) nyomtól (x=185.155) tavol legyen
    new = new.replace('(at -4.575181 -0.02381 0)', '(at -4.575181 -0.02381 0)')

    txt = txt[:m.start()] + new + txt[m.end():]
    print(f"  D9 -> ({D9_AT[0]}, {D9_AT[1]}) rot {D9_ROT}, value {NEW_VALUE}")

    # ------------------------------------------------------------------
    # 3. az uj nyomok
    # ------------------------------------------------------------------
    panel = 'Net-(D10-A)'
    segs = [
        # J4.1 (Solarpanel+) -> D9 pad2 (panel oldal)
        segment(J4_PANEL, (D9_PANEL[0], J4_PANEL[1]), panel),
        # D9 pad2 -> D10 anode felole
        segment(D9_PANEL, (STUB_X, D9_PANEL[1]), panel),
        segment((STUB_X, D9_PANEL[1]), (STUB_X, D10_A[1]), panel),
    ]
    gnd = [
        # D9 pad1 (GND) -> J4.2 GND tuske: a TVS a csatlakozo GND labjan
        # keresztul folyik a GND zoneba (nagyon kis hurk)
        segment(D9_GND, J4_GND, 'GND'),
    ]
    add = ''.join(segs) + ''.join(gnd)

    # a szakaszokat a zonet blokk elott, a trackek kozott tesszuk be
    anchor = '\n\t(segment\n'
    idx = txt.index(anchor)
    txt = txt[:idx] + add + txt[idx:]
    print(f"  uj nyom: {len(segs)} panel + {len(gnd)} GND")

    assert txt != orig
    open(PCB, 'w').write(txt)
    print(f"  kiirva: {PCB} ({len(txt)} bajt)")


if __name__ == '__main__':
    main()
