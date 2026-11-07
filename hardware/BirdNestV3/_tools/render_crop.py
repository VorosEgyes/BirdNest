#!/usr/bin/env python3
"""Kivágja a 3D render J4 és TP regioit (kalibrált koordinata-lekepes)."""
from PIL import Image
import sys

SRC = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/3D_view_2026-11-06_top.png'
im = Image.open(SRC)
W, H = im.size
print("render size:", W, H)

# PCB koordinatak -> pixel. A saroklyukakon kalibralva:
# X: 99.975..200.025 ; Y: 39.975..140.025 (Y lefelen novel a PCB-vel)
X0, X1 = 99.975, 200.025
Y0, Y1 = 39.975, 140.025

def px(x, y, flip=True):
    sx = (x - X0) / (X1 - X0) * W
    sy = (Y1 - y) / (Y1 - Y0) * H if flip else (y - Y0) / (Y1 - Y0) * H
    return int(sx), int(sy)

def crop(name, xa, xb, ya, yb, flip=True, scale=3):
    p1 = px(xa, yb, flip)
    p2 = px(xb, ya, flip)
    box = (min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1]))
    c = im.crop(box)
    c = c.resize((c.width * scale, c.height * scale), Image.LANCZOS)
    out = f'/tmp/{name}.png'
    c.save(out)
    print(f"  {name}: PCB x {xa}..{xb}, y {ya}..{yb} -> {out} ({c.width}x{c.height})")

print("\n=== vagasok ===")
crop('r_j4', 182, 200.1, 99, 118, flip=True, scale=6)
crop('r_tp', 99.9, 120, 40, 60, flip=True, scale=4)
crop('r_tp2', 99.9, 120, 40, 60, flip=False, scale=4)
