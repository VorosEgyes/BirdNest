#!/usr/bin/env python3
"""Compare v2 vs v3: footprint lib compat for shared refs, and compute free space on the 100x100 board."""
import pcbnew

v2 = pcbnew.LoadBoard("BirdNest_pcb/BirdNest_pcb.kicad_pcb")
v3 = pcbnew.LoadBoard("BirdNestV3/BirdNestV3.kicad_pcb")

libs2 = {fp.GetReference(): fp.GetFPID().GetUniStringLibId() for fp in v2.GetFootprints() if fp.GetReference()}
libs3 = {fp.GetReference(): fp.GetFPID().GetUniStringLibId() for fp in v3.GetFootprints() if fp.GetReference()}

shared = sorted(set(libs2) & set(libs3))
print("=== SHARED refs: footprint lib compatibility ===")
for r in shared:
    same = "OK " if libs2[r] == libs3[r] else "DIFF"
    print(f"  {same} {r:6} v2={libs2[r]:55} v3={libs3[r]}")
print(f"\nshared={len(shared)}  v2only={sorted(set(libs2)-set(libs3))}  v3only={sorted(set(libs3)-set(libs2))}")

# ---- free space computation on board 100..200 x 40..140 ----
BX0, BX1, BY0, BY1 = 100.0, 200.0, 40.0, 140.0
obst = []
for fp in v2.GetFootprints():
    if not fp.GetReference() or fp.GetReference().startswith("H"):  # skip blank + mounting holes
        continue
    if fp.GetReference() not in shared:
        continue
    bb = fp.GetBoundingBox(False, False)
    obst.append((fp.GetReference(), pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                 pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
# mounting holes as obstacles too
for fp in v2.GetFootprints():
    if fp.GetReference().startswith("H"):
        bb = fp.GetBoundingBox(False, False)
        obst.append((fp.GetReference(), pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                     pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))

print(f"\n=== Obstacles from v2 (shared parts kept) : {len(obst)} ===")

# rasterize into 1mm grid, mark free cells
GRID = 1.0
W = int((BX1 - BX0) / GRID)
H = int((BY1 - BY0) / GRID)
free = [[True] * H for _ in range(W)]

def mark(x0, y0, x1, y1, pad=0.0):
    gx0 = max(0, int((x0 - BX0 - pad) / GRID))
    gx1 = min(W, int((x1 - BX0 + pad) / GRID) + 1)
    gy0 = max(0, int((y0 - BY0 - pad) / GRID))
    gy1 = min(H, int((y1 - BY0 + pad) / GRID) + 1)
    for gx in range(gx0, gx1):
        for gy in range(gy0, gy1):
            free[gx][gy] = False

for name, x0, y0, x1, y1 in obst:
    mark(x0, y0, x1, y1, pad=0.3)

# find maximal free rectangles (greedy: largest free rect containing seed)
best = []
for gx in range(W):
    for gy in range(H):
        if not free[gx][gy]:
            continue
        # only start from top-left-most of a free region to reduce dupes
        if gx > 0 and free[gx - 1][gy]:
            continue
        if gy > 0 and free[gx][gy - 1]:
            continue
        # expand
        x = gx
        while x < W and free[x][gy]:
            x += 1
        w = x - gx
        h = 1
        y = gy
        while y < H:
            ok = all(free[gx + k][y] for k in range(w))
            if not ok:
                break
            y += 1
            h = y - gy
        best.append((w * h, w, h, gx, gy))
best.sort(reverse=True)
print("\n=== Top free rectangles (w x h mm, at X,Y) ===")
seen = set()
n = 0
for area, w, h, gx, gy in best:
    if area < 40:
        break
    key = (gx // 5, gy // 5, w // 5, h // 5)
    if key in seen:
        continue
    seen.add(key)
    print(f"  {w:5.0f} x {h:5.0f} mm  at ({BX0 + gx * GRID:7.1f},{BY0 + gy * GRID:7.1f})   area {w*h:6.0f}")
    n += 1
    if n > 25:
        break
