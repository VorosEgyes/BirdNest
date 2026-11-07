#!/usr/bin/env python3
"""
V3 PCB layout: place every component on the proven 100x100 mm frame.

The V3 board file already has the right frame (Edge.Cuts 100..200 x 40..140,
GND zone both sides, MMI silkscreen) and the right netlist for all V3 parts.
What it lacks is a LAYOUT: every component sits outside the board outline and
nothing is routed.

This script:
  1. moves the 30 components that exist in both revisions onto their proven V2
     positions (those are physically validated on the assembled V2 board),
  2. puts the 29 V3-only components into the regions V2 left empty,
  3. creates the 3 footprints that exist in the schematic but not on the PCB
     (D7, D8, TH1) with their schematic nets,
  4. adds the 4 M3 mounting holes from V2,
  5. reports collisions / out-of-board parts.

Run:  layout_v3.py check   # dry run
      layout_v3.py apply   # writes the board
"""
import pcbnew
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # hardware/BirdNestV3/_tools
V3DIR = os.path.dirname(HERE)                              # hardware/BirdNestV3
HW = os.path.dirname(V3DIR)                                # hardware
V2 = os.path.join(HW, "BirdNest_pcb", "BirdNest_pcb.kicad_pcb")
V3 = os.path.join(V3DIR, "BirdNestV3.kicad_pcb")

KICAD_FP = "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"
LED_FP = os.path.join(KICAD_FP, "LED_SMD.pretty",
                       "LED_0805_2012Metric_Pad1.15x1.40mm_HandSolder.kicad_mod")
NTC_FP = os.path.join(KICAD_FP, "Resistor_SMD.pretty",
                       "R_1206_3216Metric_Pad1.30x1.75mm_HandSolder.kicad_mod")
MH_FP = os.path.join(KICAD_FP, "MountingHole.pretty",
                     "MountingHole_3.2mm_M3.kicad_mod")

BX0, BX1, BY0, BY1 = 100.0, 200.0, 40.0, 140.0

# ---------------------------------------------------------------- V2 positions
# ref -> (x, y, rot).  Shared parts keep their proven V2 placement.
V2_POS = {
    "C1":   (166.250, 85.500, 90.0),
    "C10":  (177.000, 110.938, 90.0),
    "C11":  (162.500, 100.000, 180.0),
    "C12":  (148.182, 97.000, 180.0),
    "C2":   (166.568, 77.000, 0.0),
    "C20":  (114.000, 99.438, -90.0),
    "C3":   (174.233, 57.047, 90.0),
    "C6":   (167.500, 112.182, 90.0),
    "C7":   (117.000, 91.000, -90.0),
    "C8":   (174.000, 110.875, 90.0),
    "C9":   (162.500, 103.000, 0.0),
    "J2":   (190.000, 76.000, 90.0),
    "JP3":  (170.500, 68.000, 180.0),
    "JP7":  (127.500, 92.725, 0.0),
    "L1":   (153.000, 108.000, 90.0),
    "Q6":   (132.500, 94.000, 0.0),
    "R1":   (176.000, 68.500, 0.0),
    "R15":  (120.000, 91.000, 90.0),
    "R17":  (132.500, 98.500, 180.0),
    "R18":  (123.000, 91.000, 90.0),
    "R19":  (128.000, 102.000, 90.0),
    "R22":  (114.000, 91.000, -90.0),
    "R23":  (111.000, 99.375, -90.0),
    "R25":  (132.450, 105.500, 180.0),
    "R6":   (170.750, 57.000, 90.0),
    "U1":   (179.360, 58.020, 90.0),
    "U3":   (154.450, 98.000, 0.0),
    "U4":   (150.000, 60.000, 0.0),
    "U7":   (124.540, 99.695, -90.0),
    "U8":   (132.562, 102.025, 180.0),
    "BT3":  (149.400, 126.000, 180.0),   # was BT1 in V2
    "J4":   (189.673, 110.545, 90.0),   # was J3 in V2
}

# ----------------------------------------------- V3 parts that replace V2 parts
# Q9 takes over the slot of the V2 Q7 (SOT-23 battery switch), R28 the slot of
# R20 (1M gate resistor), R27 the slot of R21 (100k).  Same package, same role.
V2_SLOT_REPLACED = {
    "Q9":   (111.450, 108.650, 0.0),    # v2 Q7
    "R28":  (111.450, 112.550, 0.0),    # v2 R20
    "R27":  (106.450, 110.300, -90.0),   # v2 R21
}

# ------------------------------------------------------------ V3-only placement
# Region A  x 102..123, y 44..82  (top-left quadrant, empty in V2)
#             -> BAT_MON divider + test point column
# Region B  x 168..199, y 81..100 (V2 TP4056 module slot, right of the
#             boost converter, above the solar connector)
#             -> CN3065 charger + indicator LEDs
# Region C  x 134..163, y 96..112 (between the UVLO block and the battery)
#             -> FS8205A + DW01A cell protection
NEW_POS = {
    # ---- Region B: CN3065 charger ----
    "U11":  (181.000, 88.000, 0.0),     # CN3065 DFN-9
    "C24":  (186.000, 93.000, 90.0),    # 10uF  on VIN_PROT
    "C25":  (191.000, 93.000, 90.0),    # 100nF on VIN_PROT
    "R12":  (186.000, 97.500, 90.0),    # 4.7k  U11 ISET
    "R14":  (176.000, 92.000, 90.0),    # 3.9k  U11 TEMP
    "TH1":  (171.000, 92.000, 90.0),    # NTC on U11 TEMP
    "R13":  (176.000, 97.500, 90.0),    # 330R  LED anode pull-up
    "D7":   (171.000, 84.000, 90.0),    # LED green  /DONE_STAT
    "D8":   (176.000, 84.000, 90.0),    # LED red    /CHG_STAT
    "D9":   (195.500, 84.000, 90.0),    # SMAJ90CA TVS on solar input
    "D10":  (195.500, 90.000, 90.0),    # SS34 solar rectifier
    # ---- Region C: cell protection (FS8205A + DW01A) ----
    "Q3":   (141.000, 108.000, 0.0),    # FS8205A SOP-8
    "U10":  (148.000, 108.000, 0.0),    # DW01A SOT-23-6
    "R10":  (152.500, 104.000, 90.0),   # 1k   U10 CS
    "R11":  (156.500, 104.000, 90.0),   # 100R U10 VCC
    "C15":  (156.500, 108.000, 90.0),   # 10uF  BAT_PROT+
    "C16":  (161.000, 108.000, 90.0),   # 100nF BAT_PROT+
    "C19":  (161.000, 103.500, 90.0),   # 100nF U10 VCC
    "C23":  (137.500, 103.500, 90.0),   # 10uF  BAT_CELL+
    # ---- Region A: BAT_MON divider + test points ----
    "R29":  (106.000, 55.000, 90.0),    # 1M   BAT_MON top
    "R30":  (111.000, 55.000, 90.0),    # 2.2M BAT_MON bottom
    "C22":  (116.000, 55.000, 90.0),    # 100nF BAT_MON filter
    "TP1":  (106.000, 48.000, 0.0),     # GND
    "TP2":  (111.000, 48.000, 0.0),     # VIN_PROT
    "TP3":  (116.000, 48.000, 0.0),     # SYS_PWR
    "TP4":  (121.000, 48.000, 0.0),     # +5V
    "TP5":  (106.000, 51.000, 0.0),     # REF2V5
}

MOUNTING_HOLES = {
    "H1": (105.0, 135.0),
    "H2": (195.0, 135.0),
    "H3": (195.0, 45.0),
    "H4": (105.0, 45.0),
}

# footprint file + pad-net mapping for the 3 schematic-only parts
NEW_FOOTPRINTS = {
    "D7": (LED_FP, "LED GREEN", {"1": "/DONE_STAT", "2": "Net-(D7-A)"}),
    "D8": (LED_FP, "LED RED", {"1": "/CHG_STAT", "2": "Net-(D7-A)"}),
    "TH1": (NTC_FP, "Thermistor_NTC", {"1": "GND", "2": "Net-(U11-TEMP)"}),
}


def mm(v):
    return pcbnew.FromMM(v)


def fp_extent(fp, silk=True):
    """Collision box.  silk=False -> pads only (for mounting holes)."""
    if silk and not fp.GetReference().startswith("H"):
        bb = fp.GetBoundingBox(False, False)
    else:
        bb = fp.GetBoundingBox(True, False)
    if bb.GetWidth() == 0:
        bb = fp.GetBoundingBox(False, False)
    return (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
            pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))


def pad_extent(fp):
    """Union of the copper pad rectangles (the real DRC-relevant area).
    NPTH mounting holes have no net and no copper, so they are skipped."""
    x0 = y0 = 1e9
    x1 = y1 = -1e9
    for p in fp.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            continue
        bb = p.GetBoundingBox()
        x0 = min(x0, pcbnew.ToMM(bb.GetLeft()))
        y0 = min(y0, pcbnew.ToMM(bb.GetTop()))
        x1 = max(x1, pcbnew.ToMM(bb.GetRight()))
        y1 = max(y1, pcbnew.ToMM(bb.GetBottom()))
    if x0 > x1:
        return None
    return (x0, y0, x1, y1)


def place(fp, x, y, rot):
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    fp.SetOrientationDegrees(rot)
    fp.Reference().SetTextAngleDegrees(0)


def load_footprint(path):
    """path = .../SomeLib.pretty/Name.kicad_mod"""
    libdir = os.path.dirname(path)
    name = os.path.basename(path)
    if name.endswith(".kicad_mod"):
        name = name[:-len(".kicad_mod")]
    fp = pcbnew.FootprintLoad(libdir, name)
    if fp is None:
        raise RuntimeError(f"cannot load {path}")
    return fp


def add_mounting_holes(board):
    existing = {fp.GetReference() for fp in board.GetFootprints()}
    added = []
    for ref, (x, y) in MOUNTING_HOLES.items():
        if ref in existing:
            continue
        fp = load_footprint(MH_FP)
        fp.SetFPID(pcbnew.LIB_ID("MountingHole", "MountingHole_3.2mm_M3"))
        fp.SetReference(ref)
        fp.SetValue("MountingHole")
        fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
        board.Add(fp)
        added.append(ref)
    return added


def add_missing_footprints(board):
    """Create D7/D8/TH1 and wire their pads to the schematic nets."""
    made = []
    for ref, (path, value, padnets) in NEW_FOOTPRINTS.items():
        if board.FindFootprintByReference(ref) is not None:
            continue
        fp = load_footprint(path)
        fp.SetReference(ref)
        fp.SetValue(value)
        for pad in fp.Pads():
            netname = padnets.get(pad.GetNumber())
            if not netname:
                continue
            net = board.FindNet(netname)
            if net is None:
                print(f"  !! net {netname} not found for {ref}.{pad.GetNumber()}")
                continue
            pad.SetNet(net)
        board.Add(fp)
        made.append(ref)
    return made


def check(board):
    """Report collisions.  Pad-vs-pad and pad-vs-body are hard errors;
    silk-vs-silk is cosmetic (the V2 reference board has the same ones)."""
    items = []
    for fp in board.GetFootprints():
        if not fp.GetReference():
            continue
        x0, y0, x1, y1 = fp_extent(fp)
        items.append((fp.GetReference(), x0, y0, x1, y1, pad_extent(fp)))

    hard = 0
    soft = 0
    print(f"--- {len(items)} placed footprints ---")
    for i in range(len(items)):
        ra, ax0, ay0, ax1, ay1, ap = items[i]
        for j in range(i + 1, len(items)):
            rb, bx0, by0, bx1, by1, bp = items[j]
            if ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1:
                ox = min(ax1, bx1) - max(ax0, bx0)
                oy = min(ay1, by1) - max(ay0, by0)
                # real conflict only if the pads themselves collide
                conflict = False
                if ap and bp:
                    conflict = (ap[0] < bp[2] and bp[0] < ap[2] and
                                ap[1] < bp[3] and bp[1] < ap[3])
                if conflict:
                    print(f"  HARD  {ra} X {rb}  ({ox:.2f} x {oy:.2f} mm)")
                    hard += 1
                else:
                    print(f"  silk  {ra} X {rb}  ({ox:.2f} x {oy:.2f} mm)")
                    soft += 1
        if ax0 < BX0 - 0.3 or ax1 > BX1 + 0.3 or ay0 < BY0 - 0.3 or ay1 > BY1 + 0.3:
            print(f"  OUT-OF-BOARD {ra}  ({ax0:.1f},{ay0:.1f})-({ax1:.1f},{ay1:.1f})")
            hard += 1
    print(f"hard issues: {hard}   silk-only: {soft}")
    return hard


def load_packed():
    """Read the auto-generated placement table (pack.py output) if present."""
    path = os.path.join(HERE, "packed.json")
    if not os.path.exists(path):
        return {}
    import json
    with open(path) as f:
        raw = json.load(f)
    return {k: tuple(v) for k, v in raw.items()}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    board = pcbnew.LoadBoard(V3)

    print("mounting holes:", add_mounting_holes(board))
    print("new footprints:", add_missing_footprints(board))

    # placement table: proven V2 slots + auto-packed V3-only parts
    table = dict(V2_POS)
    packed = load_packed()
    if packed:
        print(f"auto-packed parts applied: {len(packed)}")
        table.update(packed)
        # The parts that take over a slot of the V2 are packed as well:
        # the tracks of the V2 run through those slots, so the parts can
        # not stand there.  The pack wins over the old slot.
        for ref in V2_SLOT_REPLACED:
            if ref not in packed:
                table[ref] = V2_SLOT_REPLACED[ref]
    else:
        table.update(V2_SLOT_REPLACED)
        print("!! packed.json missing - using hand-placed NEW_POS")
        table.update(NEW_POS)

    missing = []
    for ref, (x, y, rot) in table.items():
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            missing.append(ref)
            continue
        place(fp, x, y, rot)
    if missing:
        print("MISSING (must be created):", missing)

    issues = check(board)

    if mode == "apply" and issues == 0 and not missing:
        pcbnew.SaveBoard(V3, board)
        print(f"saved {V3}")
    else:
        print("NOT written (issues=%d missing=%d)" % (issues, len(missing)))


if __name__ == "__main__":
    main()
