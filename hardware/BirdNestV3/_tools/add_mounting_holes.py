#!/usr/bin/env python3
"""Take the holes of the board into the schematic.

The holes of the board that have no symbol in the schematic are taken
away by the next "Update PCB from Schematic": the program sees
footprints that belong to no symbol and deletes them.  The mounting
holes were lost that way twice.

So the holes are put into the schematic as symbols of
`Mechanical:MountingHole`, and the board gets the footprints with the
same identifiers.  After that the update keeps them, because they
belong to a symbol.

    add_mounting_holes.py                 # the six holes of this board
    add_mounting_holes.py --dry           # only show what would be done

The holes:

    H1  MountingHole_3.2mm_M3   105.000 135.000
    H2  MountingHole_3.2mm_M3   195.000 135.000
    H3  MountingHole_3.2mm_M3   195.000  45.000
    H4  MountingHole_3.2mm_M3   105.000  45.000
    H5  MountingHole_5.3mm_M5   153.500 119.500
    H6  MountingHole_5.3mm_M5   153.500 136.250

H1 to H4 are the corners of the board, the same place as the holes of
the V2.  H5 and H6 are for the cable ties, for the case that the
battery holder is not used.

The symbol is taken from the library of the program
(`Mechanical.kicad_sym`), so that the drawing has the same definition
as the library has.
"""
import os
import re
import shutil
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, '..', 'BirdNestV3.kicad_pcb')
SCH = os.path.join(HERE, '..', 'BirdNestV3.kicad_sch')
LIB = '/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols/Mechanical.kicad_sym'
PROJECT = 'BirdNestV3'

# the holes: reference, footprint, x, y
HOLES = [
    ('H1', 'MountingHole:MountingHole_3.2mm_M3', 105.000, 135.000),
    ('H2', 'MountingHole:MountingHole_3.2mm_M3', 195.000, 135.000),
    ('H3', 'MountingHole:MountingHole_3.2mm_M3', 195.000, 45.000),
    ('H4', 'MountingHole:MountingHole_3.2mm_M3', 105.000, 45.000),
    ('H5', 'MountingHole:MountingHole_5.3mm_M5', 153.500, 119.500),
    ('H6', 'MountingHole:MountingHole_5.3mm_M5', 153.500, 136.250),
]


def block_of(txt, start):
    """The text of the s-expression that starts at `start`, with its end."""
    depth = 0
    j = start
    in_str = False
    while j < len(txt):
        c = txt[j]
        if in_str:
            if c == '\\':
                j += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return txt[start:j + 1]
        j += 1
    raise ValueError('unclosed expression')


def symbol_of_library():
    """The MountingHole symbol of the library, with the name of the library."""
    txt = open(LIB).read()
    i = txt.index('\t(symbol "MountingHole"')
    blk = block_of(txt, i)
    # in the drawing the name of the symbol carries the library
    blk = blk.replace('(symbol "MountingHole"', '(symbol "Mechanical:MountingHole"', 1)
    # one more tab: the library has the symbols at one tab, the
    # drawing keeps them at two
    return '\n'.join('\t' + l for l in blk.split('\n'))


def instance(ref, footprint, x, y, uid):
    """The symbol in the drawing."""
    return f'''\t(symbol
\t\t(lib_id "Mechanical:MountingHole")
\t\t(at {x} {y} 0)
\t\t(unit 1)
\t\t(body_style 1)
\t\t(exclude_from_sim no)
\t\t(in_bom no)
\t\t(on_board yes)
\t\t(in_pos_files yes)
\t\t(dnp no)
\t\t(fields_autoplaced yes)
\t\t(uuid "{uid}")
\t\t(property "Reference" "{ref}"
\t\t\t(at {x} {y + 5.08} 0)
\t\t\t(show_name no)
\t\t\t(do_not_autoplace no)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(property "Value" "MountingHole"
\t\t\t(at {x} {y + 3.175} 0)
\t\t\t(show_name no)
\t\t\t(do_not_autoplace no)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(property "Footprint" "{footprint}"
\t\t\t(at {x} {y} 0)
\t\t\t(hide yes)
\t\t\t(show_name no)
\t\t\t(do_not_autoplace no)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(property "Datasheet" ""
\t\t\t(at {x} {y} 0)
\t\t\t(hide yes)
\t\t\t(show_name no)
\t\t\t(do_not_autoplace no)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(property "Description" "Mounting Hole without connection"
\t\t\t(at {x} {y} 0)
\t\t\t(hide yes)
\t\t\t(show_name no)
\t\t\t(do_not_autoplace no)
\t\t\t(effects
\t\t\t\t(font
\t\t\t\t\t(size 1.27 1.27)
\t\t\t\t)
\t\t\t)
\t\t)
\t\t(instances
\t\t\t(project "{PROJECT}"
\t\t\t\t(path "/89abeaff-1b65-4d32-a0bb-ec0f19967e6e"
\t\t\t\t\t(reference "{ref}")
\t\t\t\t\t(unit 1)
\t\t\t\t)
\t\t\t)
\t\t)
\t)'''


def add_to_schematic(dry=False):
    txt = open(SCH).read()
    uuids = {}
    for ref, fp, x, y in HOLES:
        uuids[ref] = str(uuid.uuid4())

    # 1. the definition of the symbol, if it is not there yet
    if '"Mechanical:MountingHole"' not in txt:
        lib = symbol_of_library()
        # the library symbols of the drawing end before the first text box
        anchor = txt.index('\n\t(text_box')
        # the end of the lib_symbols section is the last "\t)" before that
        cut = txt.rindex('\n\t)', 0, anchor)
        txt = txt[:cut + 1] + lib + '\n' + txt[cut + 1:]
        print("the symbol was added to the library of the drawing")

    # 2. the symbols themselves, before the sheet instances
    blocks = []
    for ref, fp, x, y in HOLES:
        if f'(reference "{ref}")' in txt:
            print(f"  {ref} is already in the drawing")
            continue
        blocks.append(instance(ref, fp, x, y, uuids[ref]))
    if blocks:
        anchor = txt.index('\n\t(sheet_instances')
        txt = txt[:anchor] + '\n' + '\n'.join(blocks) + txt[anchor:]
        print(f"{len(blocks)} symbols were added to the drawing")

    if not dry:
        open(SCH, 'w').write(txt)
    return uuids


def add_to_board(uuids, dry=False):
    """The footprints of the board: the ones that are missing are taken
    from the library of the program, and every one of them gets the
    path of its symbol, so that the update keeps it."""
    import pcbnew

    libdir = ('/Applications/KiCad/KiCad.app/Contents/SharedSupport/'
              'footprints/MountingHole.pretty')
    board = pcbnew.LoadBoard(PCB)
    for ref, fp, x, y in HOLES:
        lib, name = fp.split(':')
        f = board.FindFootprintByReference(ref)
        if f is None:
            f = pcbnew.FootprintLoad(libdir, name)
            f.SetFPID(pcbnew.LIB_ID(lib, name))
            f.SetReference(ref)
            f.SetValue('MountingHole')
            f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
            f.SetAttributes(f.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM)
            f.Reference().SetVisible(False)
            board.Add(f)
            print(f"  {ref} was put on the board at ({x}, {y})")
        else:
            print(f"  {ref} is on the board already")
        # the link with the symbol of the drawing: the update keeps the
        # footprints that have one, and takes the others away
        f.SetPath(pcbnew.KIID_PATH('/' + uuids[ref]))
        print(f"  {ref} is linked with its symbol")

    if not dry:
        pcbnew.SaveBoard(PCB, board)


def main():
    dry = '--dry' in sys.argv
    if not dry:
        shutil.copy(SCH, '/tmp/BirdNestV3_before_holes.kicad_sch')
        shutil.copy(PCB, '/tmp/BirdNestV3_before_holes.kicad_pcb')
    uuids = add_to_schematic(dry)
    add_to_board(uuids, dry)
    print("the identifiers of the symbols:")
    for ref, u in uuids.items():
        print(f"   {ref}: {u}")


if __name__ == '__main__':
    main()
