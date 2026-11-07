#!/usr/bin/env python3
"""A D9 TVS dioda athelyezese a panel-csatlakozo melle, es a panel
bemeneti kornyezet ujjaroutingolasa.

Az eredeti allapot:
  D9  SMAJ90CA, 90V munkapont, a J4 csatlakozotol 22.8 mm-re
  D10 SS34 Schottky, 29.6 mm-re
  a Net-(D10-A) nyom 47 mm hosszusban fut az F.Cu-n a tabla szelen

Az uj allapot:
  D9  SMAJ6.0CA, 6V munkapont, a J4.1 labjan 4.6 mm-re
  a GND-lab a GND-zonahoz csatlakozik, solid kapcsolattal, hogy egy
    tranziens ne 4 db 0.4 mm-es szalon menjen at
  a Net-(D10-A) nyom a GND-zona belsejeben fut, nem a tabla szelen

A D9 tipusvaltasaval a symbol is cserelodik a schematicon: a Diode
konyvtarban a SMAJ6.0CA symbol ugyanazt a D_SMA footprintot hasznalja,
es ugyanazt a ket labjat (A1_1, A2_2) nevezi, ezert a netlista nem
valtozik.

    d9_move.py            -- a terv, nem irunk a tabla
    d9_move.py --apply    -- a tabla irva
"""
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew    # noqa: E402
import safe_board   # noqa: E402

# A pcbnew assert-je elnyeli a standard kimenetet, es a wx.App
# segfaultot okoz, ezert minden sajat print fajlba megy, amit a
# program vegen kiirunk.
_LOG = open("/tmp/d9_move.log", "w")


def say(*args):
    _LOG.write(" ".join(str(a) for a in args) + "\n")
    _LOG.flush()

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
JSON = "/tmp/d9_drc.json"

OLD_TYPE = "SMAJ90CA"
NEW_TYPE = "SMAJ6.0CA"

# --- az uj hely a J4 mellett ---
# J4.1 (Solarpanel +) a (189.673, 110.545) ponton van, a pad 2.6 mm.
# A D9 90 fokban fordulva 1.75 mm szeles, a J4 udvara (194.773) es a
# tabla szele (200.03) kozott fer.
# A D9.2 (panel oldali lab) a J4.1 mellett, a D9.1 (GND) alabb.
D9_X = 196.500
D9_Y = 112.800
D9_ROT = 90

# a Net-(D10-A) uj nyomai: J4.1 -> D9.2 -> D10.2
VIN_ROUTE = [
    ((189.673, 110.545), (196.500, 110.800)),   # J4.1 -> D9.2
    ((196.500, 110.800), (196.500, 81.275)),    # D9.2 -> D10.2 (a zona belsejeben)
    ((196.500, 81.275), (196.070, 81.275)),     # D10.2 -> a pad közeppontja
]


def mm(v):
    return pcbnew.ToMM(v)


def frommm(v):
    return pcbnew.FromMM(v)


def drc(board=PCB):
    if os.path.exists(JSON):
        os.remove(JSON)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", JSON, board],
                   capture_output=True, text=True)
    with open(JSON) as f:
        return json.load(f)


def net_code_of(board, ref, padnum):
    """A net kodja egy konkrét padrol.

    A board.GetFootprints() SWIG proxykat ad, amik a Remove() utan
    elvesztik a tipusukat, ezert a net kodot a TORLES ELOTT kell
    kiolvasni, egy konkrét alkatresz padjarol.
    """
    fp = board.FindFootprintByReference(ref)
    for pad in fp.Pads():
        if pad.GetNumber() == padnum:
            return pad.GetNetCode(), pad.GetNetname()
    return None, None


def remove_net(board, code):
    """A net minden rezet eltavolitja, egy processben."""
    victims = [t for t in list(board.GetTracks()) if t.GetNetCode() == code]
    for t in victims:
        board.Remove(t)
    say(f"  a netre {len(victims)} rezes darab torolve")


def add_track(board, code, p1, p2, width=0.25, layer=pcbnew.F_Cu):
    t = pcbnew.PCB_TRACK(board)
    t.SetNetCode(code)
    t.SetStart(pcbnew.VECTOR2I(frommm(p1[0]), frommm(p1[1])))
    t.SetEnd(pcbnew.VECTOR2I(frommm(p2[0]), frommm(p2[1])))
    t.SetWidth(frommm(width))
    t.SetLayer(layer)
    board.Add(t)
    return t


def move_d9(board):
    fp = board.FindFootprintByReference("D9")
    fp.SetPosition(pcbnew.VECTOR2I(frommm(D9_X), frommm(D9_Y)))
    fp.SetOrientationDegrees(D9_ROT)
    fp.Value().SetText(NEW_TYPE)
    p = fp.GetPosition()
    say(f"  D9 -> ({mm(p.x):.3f},{mm(p.y):.3f}) {D9_ROT} fok, tipus {NEW_TYPE}")
    for pad in fp.Pads():
        q = pad.GetPosition()
        say(f"     pad {pad.GetNumber()} ({mm(q.x):.3f},{mm(q.y):.3f}) net={pad.GetNetname()}")
    return fp


def plan():
    board = pcbnew.LoadBoard(PCB)
    before = drc()
    say(f"a tabla most: {len(before.get('violations', []))} violation, "
          f"{len(before.get('unconnected_items', []))} unconnected")

    # a net kodok ELORE, a torles elott
    vin_code, vin_name = net_code_of(board, "J4", "1")
    gnd_code, gnd_name = net_code_of(board, "D9", "1")
    say(f"\na net kodok: {vin_name}={vin_code}, {gnd_name}={gnd_code}")

    say("\n=== a terv ===")
    move_d9(board)

    say("\n=== az uj nyomok ===")
    remove_net(board, vin_code)
    for p1, p2 in VIN_ROUTE:
        add_track(board, vin_code, p1, p2)
        say(f"  {vin_name}: ({p1[0]:.3f},{p1[1]:.3f}) -> ({p2[0]:.3f},{p2[1]:.3f})")

    # A zona ujratoltese NEM itt tortenik: a Remove() utani SWIG
    # proxyk miatt a ZONE_FILLER a fillnel crashel.  A tabla mentese
    # utan, egy kulon processben tortenik (refill.py).
    return board


def main():
    apply = "--apply" in sys.argv
    board = plan()

    if not apply:
        say("\nnem irunk a tabla")
        return 0

    shutil.copy(PCB, "/tmp/pcb_pre_d9move.kicad_pcb")
    pcbnew.SaveBoard(PCB, board)
    say("\n  a tabla irva")
    # a zona ujratoltese egy kulon processben
    subprocess.run([sys.executable, os.path.join(HERE, "refill.py")],
                   capture_output=True, text=True)
    d = drc()
    say(f"\na tabla most: {len(d.get('violations', []))} violation, "
          f"{len(d.get('unconnected_items', []))} unconnected")
    for v in d.get("violations", []):
        say("  ", v.get("type"), "|", v.get("description"))
        for it in v.get("items", []):
            say("      ", it.get("description"), "@", it.get("pos"))
    for u in d.get("unconnected_items", []):
        say("   unconnected:", u.get("description"))
    return 0


if __name__ == "__main__":
    _rc = main()
    _LOG.close()
    sys.exit(_rc)
