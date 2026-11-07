#!/usr/bin/env python3
"""Show the parts and the copper of a net in another board file.

Usage: net_in_board.py <board.kicad_pcb> <net name>
"""

import sys

import pcbnew

BOARD = sys.argv[1]
NET = sys.argv[2]


def main():
    board = pcbnew.LoadBoard(BOARD)
    to_mm = pcbnew.ToMM

    print("=== pads of the net ===")
    for foot in board.GetFootprints():
        ref = str(foot.GetReference())
        value = str(foot.GetValue())
        for pad in foot.Pads():
            if pad.GetNetname() != NET:
                continue
            pos = pad.GetPosition()
            print(
                "%-6s.%-3s %-8s x=%8.3f y=%8.3f size=%5.3fx%5.3f rot=%5.1f"
                % (
                    ref,
                    str(pad.GetNumber()),
                    value,
                    to_mm(pos.x),
                    to_mm(pos.y),
                    to_mm(pad.GetSize().x),
                    to_mm(pad.GetSize().y),
                    pad.GetOrientationDegrees(),
                )
            )

    print("=== copper of the net ===")
    for track in board.GetTracks():
        if track.GetNetname() != NET:
            continue
        ttype = track.Type()
        if ttype == pcbnew.PCB_TRACE_T:
            layer = "F" if track.GetLayer() == pcbnew.F_Cu else "B"
            start = track.GetStart()
            end = track.GetEnd()
            print(
                "%s (%8.3f,%8.3f)->(%8.3f,%8.3f) w=%.3f"
                % (
                    layer,
                    to_mm(start.x),
                    to_mm(start.y),
                    to_mm(end.x),
                    to_mm(end.y),
                    to_mm(track.GetWidth()),
                )
            )
        elif ttype == pcbnew.PCB_VIA_T:
            pos = track.GetPosition()
            print(
                "via (%8.3f,%8.3f) d=%.3f"
                % (to_mm(pos.x), to_mm(pos.y), to_mm(track.GetWidth()))
            )


main()
