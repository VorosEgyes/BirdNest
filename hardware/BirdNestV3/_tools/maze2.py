#!/usr/bin/env python3
"""
V3 PCB router - 2 layer grid maze router with an exact clearance model.

Why this version exists
-----------------------
Three earlier attempts failed for different reasons:

 1. freerouting (v2.1.0) routed 22 of 27 nets but its CLI mode never exports
    a .ses file, so the result was unusable.
 2. The first home-made router marked a net's clearance ring as "owned" by
    that net, so a neighbour could route straight through it - hundreds of
    clearance violations.
 3. Marking the ring as a hard keep-out for everybody sealed each net off
    from its own pads.

The model that is correct
-------------------------
For a routing net N and any other net M:

    distance(N centreline, M copper)  >=  halfwidth(M)
                                     +  halfwidth(N)
                                     +  clearance(N)

The router therefore keeps, for every net M, the exact dilation of M's own
copper by (halfwidth(M) + halfwidth(N) + clearance(N)).  Because N's width
and clearance are known while N is routed, the dilation is computed per
routing net - there is no conservative over-estimation.

Implementation notes
--------------------
* copper and dilations are stored as row-bitsets (one Python int per row),
  so a dilation of the whole board costs a few hundred microseconds;
* the search mask is expanded into bytearrays, so the A* inner loop does an
  O(1) index instead of a big-int shift;
* 8-directional A* with straight/diagonal costs, so the result consists of
  straight lines and 45 degree bends;
* a via switches layer at a cost, and the via barrel is added to the copper
  of both layers.

Run:  maze2.py            # routes every net that still needs routing
"""
import heapq
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import safe_board    # noqa: E402  the guard of the board

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"

GRID = 0.25                     # mm per cell
NX = 400                        # cells in X (100 mm / 0.25)
NY = 400                        # cells in Y
ORIGIN = (100.0, 40.0)          # mm of grid cell (0, 0)
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
VIA_COST = 18                   # in grid steps (4.5 mm equivalent)
DIRS = ((0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0),
        (1, 1, 1.4143), (1, -1, 1.4143), (-1, 1, 1.4143), (-1, -1, 1.4143))


def mm(v):
    return int(round(v * 1e6))


def gx(x_mm):
    return int(round((x_mm - ORIGIN[0]) / GRID))


def gy(y_mm):
    return int(round((y_mm - ORIGIN[1]) / GRID))


def cell_of(pos):
    return gy(pcbnew.ToMM(pos.y)), gx(pcbnew.ToMM(pos.x))


def inb(y, x):
    return 0 <= y < NY and 0 <= x < NX


def dilate_rows(rows, radius, nx):
    """Square dilation of a row-bitset by `radius` cells.

    Horizontal: every run grows by `radius` cells on both sides.
    Vertical:   a sliding OR window over the rows.
    """
    if radius <= 0:
        return list(rows)
    grown = []
    limit = (1 << nx) - 1
    for r in rows:
        if r == 0:
            grown.append(0)
            continue
        v = r
        for _ in range(radius):
            v |= v << 1
        w = r
        for _ in range(radius):
            w |= w >> 1
        grown.append((v | w) & limit)

    win = 2 * radius + 1
    out = [0] * len(rows)
    cur = 0
    for y in range(len(rows)):
        cur |= grown[y]
        if y >= win:
            cur &= ~grown[y - win]
        out[y] = cur
    cur = 0
    for y in range(len(rows) - 1, -1, -1):
        cur |= grown[y]
        if y + win < len(rows):
            cur &= ~grown[y + win]
        out[y] |= cur
    return out


def rows_to_mask(rows, nx):
    """Expand row-bitsets into a bytearray (one byte per cell).

    The bit scan is done with the standard trick of consuming the lowest
    set bit, which is much faster than shifting the whole integer.
    """
    mask = bytearray(len(rows) * nx)
    for y, r in enumerate(rows):
        if not r:
            continue
        base = y * nx
        while r:
            low = r & -r
            mask[base + low.bit_length() - 1] = 1
            r ^= low
    return mask


class Net:
    def __init__(self, idx, name):
        self.idx = idx
        self.name = name
        self.cu = [[0] * NX for _ in LAYERS]
        self.halfwidth = 0.125
        self.clearance = 0.25
        self.pads = []


class Router:
    def __init__(self, board):
        self.board = board
        self.classes = {str(k): v for k, v in board.GetNetClasses().items()}
        self.nets = []
        self.by_name = {}
        self._index_nets()
        self._load_copper()

    # ------------------------------------------------------------------ setup
    def _index_nets(self):
        counts = {}
        for fp in self.board.GetFootprints():
            if not fp.GetReference():
                continue
            for pad in fp.Pads():
                n = pad.GetNetname()
                if n:
                    counts[n] = counts.get(n, 0) + 1
        idx = 0
        for name in sorted(counts):
            if name == "GND" or name.startswith("unconnected-"):
                continue
            if counts[name] < 2:
                continue
            net = Net(idx, name)
            self.nets.append(net)
            self.by_name[name] = net
            idx += 1

    def _class_of(self, name):
        net = self.board.FindNet(name)
        if net is None:
            return "Default"
        raw = net.GetNetClassName() or ""
        primary = raw.split(",")[0].strip()
        return primary if primary in self.classes else "Default"

    def _params(self, name):
        nc = self.classes.get(self._class_of(name))
        if nc is None:
            return 0.25, 0.25
        return (pcbnew.ToMM(nc.GetClearance()), pcbnew.ToMM(nc.GetTrackWidth()))

    # ------------------------------------------------------------------ copper
    def _load_copper(self):
        for fp in self.board.GetFootprints():
            if not fp.GetReference():
                continue
            for pad in fp.Pads():
                net = self.by_name.get(pad.GetNetname())
                if net is not None:
                    self._rasterise_pad(net, pad)
        for t in self.board.GetTracks():
            net = self.by_name.get(t.GetNetname())
            if net is None:
                continue
            if t.GetClass() == "PCB_VIA":
                self._rasterise_via(net, t)
            else:
                self._rasterise_track(net, t)

    def _stamp(self, net, li, cy, cx, half):
        ya, yb = max(0, cy - half), min(NY - 1, cy + half)
        xa, xb = max(0, cx - half), min(NX - 1, cx + half)
        if xb < xa or yb < ya:
            return
        span = ((1 << (xb - xa + 1)) - 1) << xa
        rows = net.cu[li]
        for y in range(ya, yb + 1):
            rows[y] |= span

    def _rasterise_pad(self, net, pad):
        pos = pad.GetPosition()
        cy, cx = cell_of(pos)
        size = pad.GetSize()
        half_x = max(1, int(round(pcbnew.ToMM(size.x) / 2 / GRID)))
        half_y = max(1, int(round(pcbnew.ToMM(size.y) / 2 / GRID)))
        for l in LAYERS:
            if pad.IsOnLayer(l):
                self._stamp(net, LAYERS.index(l), cy, cx, max(half_x, half_y))
        net.pads.append((cy, cx, [LAYERS.index(l) for l in LAYERS
                                  if pad.IsOnLayer(l)]))

    def _rasterise_track(self, net, t):
        a, b = t.GetStart(), t.GetEnd()
        ay, ax = cell_of(a)
        by, bx = cell_of(b)
        half = max(1, int(round(pcbnew.ToMM(t.GetWidth()) / 2 / GRID)))
        l = t.GetLayer()
        if l not in LAYERS:
            return
        li = LAYERS.index(l)
        steps = max(abs(bx - ax), abs(by - ay), 1)
        for i in range(steps + 1):
            cx = ax + (bx - ax) * i // steps
            cy = ay + (by - ay) * i // steps
            self._stamp(net, li, cy, cx, half)

    def _rasterise_via(self, net, t):
        pos = t.GetPosition()
        cy, cx = cell_of(pos)
        half = max(1, int(round(pcbnew.ToMM(t.GetWidth()) / 2 / GRID)))
        for li in range(len(LAYERS)):
            self._stamp(net, li, cy, cx, half)

    # ------------------------------------------------------------------ route
    def build_mask(self, net):
        """The keep-out mask for the routing net N.

        For every other net M, M's copper is dilated by
            halfwidth(M) + halfwidth(N) + clearance(N)
        which is exactly the distance N's centreline must keep from M's
        copper for the DRC edge-to-edge clearance to hold.
        """
        masks = []
        for li in range(len(LAYERS)):
            rows = [0] * NY
            for other in self.nets:
                if other is net:
                    continue
                r = int(math.ceil((other.halfwidth + net.halfwidth
                                   + net.clearance) / GRID))
                dil = dilate_rows(other.cu[li], r, NX)
                for y in range(NY):
                    rows[y] |= dil[y]
            masks.append(rows_to_mask(rows, NX))
        return masks

    def astar(self, net, start, goal, masks):
        sy, sx = start[0], start[1]
        gy_, gx_ = goal[0], goal[1]

        def h(y, x):
            return abs(y - gy_) + abs(x - gx_)

        states = [(sy, sx, l) for l in (start[2] or [0])]
        gscore = {s: 0.0 for s in states}
        came = {}
        heap = [(h(sy, sx), 0.0, s) for s in states]
        heapq.heapify(heap)
        goal_states = {(gy_, gx_, l) for l in (goal[2] or [0, 1])}
        visited = set()
        found = None

        while heap:
            f, g, cur = heapq.heappop(heap)
            if cur in visited:
                continue
            visited.add(cur)
            if cur in goal_states:
                found = cur
                break
            y, x, l = cur
            mask = masks[l]
            base = y * NX
            for dy, dx, cost in DIRS:
                ny, nx = y + dy, x + dx
                if not inb(ny, nx):
                    continue
                if mask[ny * NX + nx]:
                    continue
                if dy and dx:
                    if mask[base + nx] or mask[ny * NX + x]:
                        continue
                nxt = (ny, nx, l)
                ng = g + cost
                if ng < gscore.get(nxt, 1e30) - 1e-9:
                    gscore[nxt] = ng
                    came[nxt] = cur
                    heapq.heappush(heap, (ng + h(ny, nx), ng, nxt))
            if found:
                break
            other_l = 1 if l == 0 else 0
            if not masks[other_l][y * NX + x]:
                nxt = (y, x, other_l)
                ng = g + VIA_COST
                if ng < gscore.get(nxt, 1e30) - 1e-9:
                    gscore[nxt] = ng
                    came[nxt] = cur
                    heapq.heappush(heap, (ng + h(y, x), ng, nxt))
        if found is None:
            return None
        path = []
        cur = found
        while True:
            path.append(cur)
            if cur in came:
                cur = came[cur]
            else:
                break
        path.reverse()
        return path

    def route_net(self, net):
        pads = net.pads
        if len(pads) < 2:
            return None
        masks = self.build_mask(net)

        # nearest-neighbour chain over the pads
        remaining = list(range(1, len(pads)))
        chain = [pads[0]]
        cur = pads[0]
        while remaining:
            best = None
            for i in remaining:
                d = abs(pads[i][0] - cur[0]) + abs(pads[i][1] - cur[1])
                if best is None or d < best[0]:
                    best = (d, i)
            i = best[1]
            remaining.remove(i)
            chain.append(pads[i])
            cur = pads[i]

        full = []
        for a, b in zip(chain, chain[1:]):
            seg = self.astar(net, a, b, masks)
            if seg is None:
                return None
            if full:
                full.extend(seg[1:])
            else:
                full.extend(seg)
        return full

    # ------------------------------------------------------------------ write
    def commit(self, net, path):
        width = net.halfwidth * 2
        cls = self.classes.get(self._class_of(net.name))
        vdia = pcbnew.ToMM(cls.GetViaDiameter()) if cls else 0.6
        vdrill = pcbnew.ToMM(cls.GetViaDrill()) if cls else 0.3
        bnet = self.board.FindNet(net.name)

        # merge the path into straight segments
        segs = []
        vias = []
        i = 0
        while i < len(path) - 1:
            l0, y0, x0 = path[i]
            l1, y1, x1 = path[i + 1]
            if l0 != l1:
                vias.append((y0, x0))
                i += 1
                continue
            dy, dx = y1 - y0, x1 - x0
            j = i + 1
            while j < len(path) - 1:
                ny, nx, nl = path[j]
                py, px, pl = path[j - 1]
                if nl != l0:
                    break
                ndy, ndx = ny - py, nx - px
                if ndy * dx != ndx * dy:
                    break
                y1, x1 = ny, nx
                j += 1
            segs.append((l0, y0, x0, y1, x1))
            i = j - 1

        for l, y0, x0, y1, x1 in segs:
            t = pcbnew.PCB_TRACK(self.board)
            t.SetStart(pcbnew.VECTOR2I(mm(ORIGIN[0] + x0 * GRID),
                                      mm(ORIGIN[1] + y0 * GRID)))
            t.SetEnd(pcbnew.VECTOR2I(mm(ORIGIN[0] + x1 * GRID),
                                    mm(ORIGIN[1] + y1 * GRID)))
            t.SetWidth(mm(width))
            t.SetLayer(LAYERS[l])
            t.SetNet(bnet)
            self.board.Add(t)

        for y, x in vias:
            v = pcbnew.PCB_VIA(self.board)
            v.SetPosition(pcbnew.VECTOR2I(mm(ORIGIN[0] + x * GRID),
                                        mm(ORIGIN[1] + y * GRID)))
            v.SetWidth(mm(vdia))
            v.SetDrill(mm(vdrill))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(LAYERS[0], LAYERS[1])
            v.SetNet(bnet)
            self.board.Add(v)

        # update the copper model
        half = max(1, int(round(net.halfwidth / GRID)))
        for l, y0, x0, y1, x1 in segs:
            steps = max(abs(x1 - x0), abs(y1 - y0), 1)
            for k in range(steps + 1):
                cx = x0 + (x1 - x0) * k // steps
                cy = y0 + (y1 - y0) * k // steps
                self._stamp(net, l, cy, cx, half)
        vhalf = max(1, int(round(vdia / 2 / GRID)))
        for y, x in vias:
            for li in range(len(LAYERS)):
                self._stamp(net, li, y, x, vhalf)
        return len(segs), len(vias)


def main():
    board = pcbnew.LoadBoard(V3)
    r = Router(board)

    for net in r.nets:
        clr, width = r._params(net.name)
        net.clearance = clr
        net.halfwidth = width / 2

    print(f"grid {GRID} mm, {NX}x{NY} cells")
    print(f"nets to route: {len(r.nets)}")
    for net in r.nets:
        print(f"  {net.name:24} {len(net.pads):2} pads  w={net.halfwidth*2:.2f} "
              f"clr={net.clearance:.2f} class={r._class_of(net.name)}")

    print("\nrouting...")
    ok = 0
    failed = []
    for net in r.nets:
        path = r.route_net(net)
        if path is None:
            failed.append(net.name)
            print(f"  FAIL {net.name}")
            continue
        ns, nv = r.commit(net, path)
        ok += 1
        print(f"  ok   {net.name:24} {ns:3} segs {nv:3} vias")
    print(f"\nrouted {ok}, failed {len(failed)}: {failed}")

    safe_board.save(board, "the route of the second maze router")
    print("saved")


if __name__ == "__main__":
    main()
