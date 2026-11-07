"""Move the R14 up a little and move the copper of the VIN_PROT with it.

The two status signals of the charger have to come to the pins 6 and 7
of the U11 from the right, between the pins and the R14.  The pad of
the R14 is only 0.125 millimetres above the line of the CHG_STAT, so
the R14 goes up a little, and the copper of the VIN_PROT that stands on
its pad goes with it.

The removal of the copper is done in a fresh board every time: the
wrapper of the board is broken by the removal of an item, and the
module keeps handing out the broken wrapper afterwards.
"""

import sys

import pcbnew

HERE = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/_tools"
PCB = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"

UP = 0.2          # how much the R14 goes up, in millimetres
NET = "/VIN_PROT"

# the copper of the VIN_PROT that stands on the pad of the R14: the
# via, the line to the D10 and the line down to the C25
VICTIMS = [
    ("via", 186.155, 91.525),
    ("track", 186.155, 91.525, 189.500, 91.525),
    ("track", 189.500, 91.525, 189.500, 81.275),
    ("track", 186.155, 85.175, 186.155, 91.525),
]


def move_r14():
    """Move the R14 up, and report where its pads are."""
    b = pcbnew.LoadBoard(PCB)
    for fp in b.GetFootprints():
        if fp.GetReference() != "R14":
            continue
        pos = fp.GetPosition()
        fp.SetPosition(pcbnew.VECTOR2I(pos.x, pos.y - pcbnew.FromMM(UP)))
    b.Save(PCB)
    b = pcbnew.LoadBoard(PCB)
    for fp in b.GetFootprints():
        if fp.GetReference() != "R14":
            continue
        for p in fp.Pads():
            q = p.GetPosition()
            print(f"   R14.{p.GetNumber()} now at "
                  f"({pcbnew.ToMM(q.x):.3f},{pcbnew.ToMM(q.y):.3f}) "
                  f"{p.GetNetname()}")


def remove_one(victim):
    """Remove one item of the VIN_PROT, in a board of its own."""
    kind = victim[0]
    b = pcbnew.LoadBoard(PCB)
    for t in list(b.GetTracks()):
        if t.GetNetname() != NET:
            continue
        if kind == "via":
            if t.GetClass() != "PCB_VIA":
                continue
            q = t.GetPosition()
            x, y = pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
            if abs(x - victim[1]) < 0.01 and abs(y - victim[2]) < 0.01:
                b.Remove(t)
                b.Save(PCB)
                print(f"   removed the via at ({x:.3f},{y:.3f})")
                return True
            continue
        if t.GetClass() == "PCB_VIA":
            continue
        s, e = t.GetStart(), t.GetEnd()
        xs = (pcbnew.ToMM(s.x), pcbnew.ToMM(s.y))
        xe = (pcbnew.ToMM(e.x), pcbnew.ToMM(e.y))
        want = ((victim[1], victim[2]), (victim[3], victim[4]))
        hit = any(abs(xs[0] - w[0]) < 0.01 and abs(xs[1] - w[1]) < 0.01
                  for w in want) and \
            any(abs(xe[0] - w[0]) < 0.01 and abs(xe[1] - w[1]) < 0.01
                for w in want)
        if not hit:
            continue
        b.Remove(t)
        b.Save(PCB)
        print(f"   removed the track from ({xs[0]:.3f},{xs[1]:.3f}) to "
              f"({xe[0]:.3f},{xe[1]:.3f})")
        return True
    print(f"   nothing of the {NET} net at {victim}")
    return False


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "all"
    if step in ("all", "move"):
        print("the R14 goes up:")
        move_r14()
    if step in ("all", "remove"):
        print("the copper of the VIN_PROT on the R14 goes away:")
        for v in VICTIMS:
            remove_one(v)
