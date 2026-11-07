#!/usr/bin/env python3
"""
Plot the v2 reference board to SVG with component bboxes + labels, so placement
of the new V3 parts can be planned precisely.

usage: plot_ref.py <board.kicad_pcb> <out.svg>
"""
import pcbnew, sys

board_path, out = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(board_path)

# collect board bbox from edge cuts
bb = b.GetBoardEdgesBoundingBox()
X0, Y0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
X1, Y1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
W, H = X1 - X0, Y1 - Y0
M = 5.0  # margin mm
SC = 8.0  # px per mm

parts = []
for fp in b.GetFootprints():
    fb = fp.GetBoundingBox(False, False)
    parts.append((fp.GetReference() or "?", fp.GetValue(),
                  pcbnew.ToMM(fb.GetLeft()), pcbnew.ToMM(fb.GetTop()),
                  pcbnew.ToMM(fb.GetRight()), pcbnew.ToMM(fb.GetBottom()),
                  fp.GetPosition()))

def tx(x): return (x - X0 + M) * SC
def ty(y): return (y - Y0 + M) * SC

svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{int((W+2*M)*SC)}" height="{int((H+2*M)*SC)}" '
       f'viewBox="0 0 {(W+2*M)*SC:.1f} {(H+2*M)*SC:.1f}">',
       f'<rect width="100%" height="100%" fill="#1a1a1a"/>',
       f'<rect x="{tx(X0):.1f}" y="{ty(Y0):.1f}" width="{W*SC:.1f}" height="{H*SC:.1f}" '
       f'fill="#0d3b0d" stroke="#00ff00" stroke-width="2"/>']

# grid every 10mm
gx = X0 - (X0 % 10)
while gx <= X1:
    svg.append(f'<line x1="{tx(gx):.1f}" y1="{ty(Y0):.1f}" x2="{tx(gx):.1f}" y2="{ty(Y1):.1f}" '
               f'stroke="#2a5a2a" stroke-width="0.5"/>')
    svg.append(f'<text x="{tx(gx):.1f}" y="{ty(Y0)-4:.1f}" fill="#888" font-size="9">{gx:.0f}</text>')
    gx += 10
gy = Y0 - (Y0 % 10)
while gy <= Y1:
    svg.append(f'<line x1="{tx(X0):.1f}" y1="{ty(gy):.1f}" x2="{tx(X1):.1f}" y2="{ty(gy):.1f}" '
               f'stroke="#2a5a2a" stroke-width="0.5"/>')
    svg.append(f'<text x="{tx(X0)-16:.1f}" y="{ty(gy):.1f}" fill="#888" font-size="9">{gy:.0f}</text>')
    gy += 10

# tracks (thin)
for t in b.GetTracks():
    if t.GetClass() != "PCB_TRACK":
        continue
    svg.append(f'<line x1="{tx(pcbnew.ToMM(t.GetStart().x)):.1f}" y1="{ty(pcbnew.ToMM(t.GetStart().y)):.1f}" '
               f'x2="{tx(pcbnew.ToMM(t.GetEnd().x)):.1f}" y2="{ty(pcbnew.ToMM(t.GetEnd().y)):.1f}" '
               f'stroke="#00aa55" stroke-width="{max(0.8, pcbnew.ToMM(t.GetWidth())*SC):.2f}" opacity="0.9"/>')

# component boxes
for ref, val, x0, y0, x1, y1, pos in parts:
    cx, cy = tx(pos.x), ty(pos.y)
    svg.append(f'<rect x="{tx(x0):.1f}" y="{ty(y0):.1f}" width="{(x1-x0)*SC:.1f}" height="{(y1-y0)*SC:.1f}" '
               f'fill="#ffaa0033" stroke="#ffaa00" stroke-width="1"/>')
    svg.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="1.5" fill="#ff4444"/>')
    svg.append(f'<text x="{tx(x0)+2:.1f}" y="{ty(y0)+10:.1f}" fill="#ffddaa" font-size="9" '
               f'font-family="monospace">{ref}</text>')

svg.append('</svg>')
open(out, "w").write("\n".join(svg))
print(f"wrote {out}  ({len(parts)} parts, board {W:.1f} x {H:.1f} mm)")
