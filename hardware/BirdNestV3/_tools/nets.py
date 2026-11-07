#!/usr/bin/env python3
"""
List the V3 nets and compare them against the netclass patterns in the
project file, so stale V2 patterns can be corrected.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
V3DIR = os.path.dirname(HERE)
PRO = os.path.join(V3DIR, "BirdNestV3.kicad_pro")

with open(PRO) as f:
    pro = json.load(f)

netclasses = pro.get("net_settings", {})
print("=== netclass patterns in the project file ===")
for key in ("classes",):
    for name, cls in netclasses.get(key, {}).items():
        print(f"  [{name}]  clearance={cls.get('clearance')}  track_width={cls.get('track_width')}")
        for pat in cls.get("nets", []):
            print(f"      pattern: {pat}")

print()
print("=== nets actually on the V3 board ===")
import pcbnew
board = pcbnew.LoadBoard(os.path.join(V3DIR, "BirdNestV3.kicad_pcb"))
nets = []
for code, net in board.GetNetsByNetcode().items():
    name = net.GetNetname()
    if name:
        nets.append(name)
for n in sorted(nets):
    print(f"  {n}")

print()
print("=== which netclass does each net match? ===")
pats = []
for name, cls in netclasses.get("classes", {}).items():
    for pat in cls.get("nets", []):
        pats.append((name, pat))
for n in sorted(nets):
    hits = []
    for cname, pat in pats:
        try:
            if re.fullmatch(pat, n):
                hits.append(cname)
        except re.error:
            pass
    print(f"  {n:32} -> {hits if hits else '(Default)'}")
