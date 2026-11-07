#!/usr/bin/env python3
"""Profile the router: how long does the mask build vs. the A* take?"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

import maze4

board = pcbnew.LoadBoard(maze4.V3)
r = maze4.Router(board)
for net in r.nets.values():
    clr, width = r._params(net.name)
    net.clearance = clr
    net.halfwidth = width / 2

todo = sorted(r.nets.values(), key=lambda n: -len(n.pads))

for net in todo[:4]:
    t0 = time.time()
    masks = r.build_mask(net)
    t1 = time.time()
    # count blocked cells
    blocked = sum(sum(m) for m in masks)
    print(f"{net.name:22} pads={len(net.pads):2} mask={t1-t0:6.3f}s "
          f"blocked={blocked:7d}/{2*maze4.NX*maze4.NY}")

    pads = net.pads
    a = r.relax_start(pads[0], masks)
    b = r.relax_start(pads[1], masks)
    if a is None or b is None:
        print("   no start/goal")
        continue
    t2 = time.time()
    path = r.astar(a, b, masks)
    t3 = time.time()
    print(f"   astar(1 leg) = {t3-t2:6.3f}s  path={len(path) if path else None}")
