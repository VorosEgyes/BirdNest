#!/usr/bin/env python3
"""
Put the board back.

The scripts that were thrown out may leave the board worse than they
found it.  They take a copy of the board before they start, and this
script puts that copy back.

The copy is in /tmp/repair_board_before.kicad_pcb.

Run:  restore.py
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from safe_board import BEFORE_BOARD, PCB    # noqa: E402


def main():
    if not os.path.exists(BEFORE_BOARD):
        print(f"there is no copy of the board: {BEFORE_BOARD}")
        return 1
    shutil.copy(BEFORE_BOARD, PCB)
    print(f"the board of before is back: {BEFORE_BOARD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
