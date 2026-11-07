#!/usr/bin/env python3
"""
Export the V3 board to a Specctra DSN for freerouting, and import a resulting
SES back into the board.

The board outline (Edge.Cuts) is copied into the DSN as a (keepout) boundary
and the board placement is baked in as absolute coordinates, so freerouting
works on the real 100x100 mm board with the parts where they are.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"


def export_dsn(board, out_path):
    """Write a DSN via the pcbnew exporter (uses the board's own outline)."""
    ok = pcbnew.ExportSpecctraDSN(board, out_path)
    return ok


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "export"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/v3_real.dsn"

    board = pcbnew.LoadBoard(V3)

    if mode == "export":
        ok = export_dsn(board, out)
        print(f"export -> {out}: {ok}")
        if os.path.exists(out):
            print(f"size: {os.path.getsize(out)} bytes")
        return

    if mode == "import":
        ses = sys.argv[2]
        ok = pcbnew.ImportSpecctraSES(board, ses)
        print(f"import {ses}: {ok}")
        tracks = [t for t in board.GetTracks()]
        print(f"tracks now: {len(tracks)}")
        pcbnew.SaveBoard(V3, board)
        print("saved")


if __name__ == "__main__":
    main()
