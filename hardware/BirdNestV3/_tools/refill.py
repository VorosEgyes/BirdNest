#!/usr/bin/env python3
"""Refill all copper zones on the V3 board and report the result."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"


def main():
    board = pcbnew.LoadBoard(V3)
    zones = list(board.Zones())
    print(f"zones: {len(zones)}")
    for z in zones:
        print(f"  net={z.GetNetname()!r} filled_before={z.IsFilled()}")

    filler = pcbnew.ZONE_FILLER(board)
    ok = filler.Fill(zones)
    print(f"fill returned: {ok}")

    for z in board.Zones():
        print(f"  net={z.GetNetname()!r} filled_after={z.IsFilled()} "
              f"area={z.GetFilledArea() / 1e12:.1f} mm2")

    pcbnew.SaveBoard(V3, board)
    print("saved")


if __name__ == "__main__":
    main()
