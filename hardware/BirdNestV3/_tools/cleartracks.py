#!/usr/bin/env python3
"""
Remove all tracks and vias from the V3 board (keeps footprints, zones, pads).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import safe_board    # noqa: E402  the guard of the board

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"

board = pcbnew.LoadBoard(V3)
n = 0
for t in list(board.GetTracks()):
    board.Remove(t)
    n += 1
print(f"removed {n} tracks/vias")
safe_board.save(board, "the removal of the tracks")
print("saved")
