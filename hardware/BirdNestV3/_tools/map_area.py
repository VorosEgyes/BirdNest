"""Show the copper of a rectangle of the board as a map on the terminal.

A cell that holds copper of the net that is asked for holds the name of
the net, a cell that holds copper of another net holds a dash, and a
cell that holds a pad holds the name of the net of the pad.  The cells
are marked with the name of the net of the copper.

Run:  map_area.py <net> <x0> <y0> <x1> <y1> [step] [layer]
"""
import sys

import pcbnew

PCB = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"


def mm(v):
    return v / 1000000.0


def main():
    net = sys.argv[1]
    x0, y0, x1, y1 = (float(v) for v in sys.argv[2:6])
    step = float(sys.argv[6]) if len(sys.argv) > 6 else 0.25
    layer = sys.argv[7] if len(sys.argv) > 7 else "F"
    want = pcbnew.F_Cu if layer == "F" else pcbnew.B_Cu

    b = pcbnew.LoadBoard(PCB)
    cols = int((x1 - x0) / step) + 1
    rows = int((y1 - y0) / step) + 1
    grid = [[" "] * cols for _ in range(rows)]

    def cell(x, y):
        c = int(round((x - x0) / step))
        r = int(round((y - y0) / step))
        if 0 <= r < rows and 0 <= c < cols:
            return r, c
        return None

    def put(x, y, ch, over):
        at = cell(x, y)
        if at is None:
            return
        r, c = at
        if grid[r][c] == " " or over:
            grid[r][c] = ch

    for fp in b.GetFootprints():
        for p in fp.Pads():
            if not p.GetLayerSet().Contains(want):
                continue
            pos = p.GetPosition()
            sz = p.GetSize()
            w, h = mm(sz.x), mm(sz.y)
            if abs((p.GetOrientationDegrees() % 180) - 90) < 1:
                w, h = h, w
            cx, cy = mm(pos.x), mm(pos.y)
            ch = p.GetNetname()
            for gx in range(int((cx - w / 2 - x0) / step),
                           int((cx + w / 2 - x0) / step) + 2):
                for gy in range(int((cy - h / 2 - y0) / step),
                               int((cy + h / 2 - y0) / step) + 2):
                    put(x0 + gx * step, y0 + gy * step, ch, True)

    for t in b.GetTracks():
        s, e = t.GetStart(), t.GetEnd()
        ax, ay, bx, by = mm(s.x), mm(s.y), mm(e.x), mm(e.y)
        n = t.GetNetname()
        if t.GetClass() == "PCB_VIA":
            if t.GetLayerSet().Contains(want):
                for gx in range(int((ax - 0.3 - x0) / step),
                               int((ax + 0.3 - x0) / step) + 2):
                    for gy in range(int((ay - 0.3 - y0) / step),
                                   int((ay + 0.3 - y0) / step) + 2):
                        put(x0 + gx * step, y0 + gy * step, "O", True)
            continue
        if t.GetLayer() != want:
            continue
        ch = n if n == net else "-"
        length = max(abs(bx - ax), abs(by - ay))
        steps = max(2, int(length / (step / 2)) + 1)
        for i in range(steps + 1):
            f = i / steps
            put(ax + (bx - ax) * f, ay + (by - ay) * f, ch, False)

    print(f"the map of {net} on {layer}, from ({x0},{y0}) to ({x1},{y1}),"
          f" the step is {step}")
    print("      " + "".join(str(int(x0 + c * step) % 10) for c in range(cols)))
    for r in range(rows):
        print(f"{y0 + r * step:6.2f} " + "".join(grid[r]))


if __name__ == "__main__":
    main()
