#!/usr/bin/env python3
"""Dump the pads, the tracks and the vias of an area of the board.

Usage: dump_area.py X0 Y0 X1 Y1 [layer]
The layer may be F, B or A (all).
"""

import sys

import pcbnew

BOARD = "../BirdNestV3.kicad_pcb"


def main():
    x0, y0, x1, y1 = (float(a) for a in sys.argv[1:5])
    want = sys.argv[5].upper() if len(sys.argv) > 5 else "A"

    board = pcbnew.LoadBoard(BOARD)
    to_mm = pcbnew.ToMM

    print("=== pads ===")
    for foot in board.GetFootprints():
        ref = str(foot.GetReference())
        for pad in foot.Pads():
            pos = pad.GetPosition()
            x = to_mm(pos.x)
            y = to_mm(pos.y)
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            net = pad.GetNetname()
            size = pad.GetSize()
            print(
                "%-6s.%-3s %-14s x=%8.3f y=%8.3f size=%5.3fx%5.3f rot=%5.1f layer=%s"
                % (
                    ref,
                    str(pad.GetNumber()),
                    net,
                    x,
                    y,
                    to_mm(size.x),
                    to_mm(size.y),
                    pad.GetOrientationDegrees(),
                    board.GetLayerName(pad.GetLayer()),
                )
            )

    print("=== tracks ===")
    for track in board.GetTracks():
        ttype = track.Type()
        if ttype == pcbnew.PCB_TRACE_T:
            layer = "F" if track.GetLayer() == pcbnew.F_Cu else "B"
            start = track.GetStart()
            end = track.GetEnd()
            sx, sy = to_mm(start.x), to_mm(start.y)
            ex, ey = to_mm(end.x), to_mm(end.y)
            if not (
                x0 <= sx <= x1 and y0 <= sy <= y1
                or x0 <= ex <= x1 and y0 <= ey <= y1
            ):
                continue
            print(
                "%s %-14s (%8.3f,%8.3f)->(%8.3f,%8.3f) w=%.3f"
                % (layer, track.GetNetname(), sx, sy, ex, ey, to_mm(track.GetWidth()))
            )
        elif ttype == pcbnew.PCB_VIA_T:
            pos = track.GetPosition()
            x, y = to_mm(pos.x), to_mm(pos.y)
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            print(
                "via %-14s (%8.3f,%8.3f) d=%.3f" % (
                    track.GetNetname(), x, y, to_mm(track.GetWidth())
                )
            )


main()
