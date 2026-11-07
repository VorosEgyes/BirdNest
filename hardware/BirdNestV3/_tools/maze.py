#!/usr/bin/env python3
"""
Grid maze router (A*) for the V3 board.

Routes the connections that the auto-router could not solve, plus (optionally)
everything else, on a 2-layer grid that honours:
  * per-net track width and clearance (taken from the netclass),
  * the board outline,
  * existing copper (pads of other nets, tracks),
  * vias between the layers.

The power path (GND / +5V / SYS_PWR) is routed by hand afterwards, because a
grid router produces technically valid but electrically poor power traces.
"""
import heapq
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import safe_board    # noqa: E402  the guard of the board

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"

GRID = 0.1             # mm per grid cell
VIA_COST = 12          # in grid steps
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
# The largest half track width in the design (the 1 mm +5V trace).  A net's
# centreline must keep
#     clearance + halfwidth(other)
# away from foreign copper, so every keep-out ring has to be that much
# wider than the bare clearance.
MAX_HALFWIDTH = 0.5


def gx(x):
    return int(round(x / GRID))


def to_mm(iu):
    return iu / 1e6


def mm(v):
    return int(round(v * 1e6))


class Router:
    def __init__(self, board):
        self.board = board
        self.classes = {str(k): v for k, v in board.GetNetClasses().items()}
        self.occupied = {l: set() for l in LAYERS}
        self.owner = {l: {} for l in LAYERS}
        # hard copper: pads, track bodies, via barrels.  Only the owning net
        # may touch these cells at all.
        self.hard = {l: set() for l in LAYERS}
        # board bounds
        bb = None
        for d in board.GetDrawings():
            if d.GetLayer() == pcbnew.Edge_Cuts:
                bb = d.GetBoundingBox()
        self.x0 = gx(pcbnew.ToMM(bb.GetLeft()))
        self.x1 = gx(pcbnew.ToMM(bb.GetRight()))
        self.y0 = gx(pcbnew.ToMM(bb.GetTop()))
        self.y1 = gx(pcbnew.ToMM(bb.GetBottom()))

    # ------------------------------------------------------------------ util
    def net_params(self, netname):
        """(clearance mm, track width mm) for a net.

        NETINFO_ITEM.GetNetClassName() returns "primary,secondary", so only
        the first name is used.  GetNetClass() returns an opaque SWIG pointer
        that cannot be compared with the objects of GetNetClasses().
        """
        net = self.board.FindNet(netname)
        if net is None:
            return 0.25, 0.25
        raw = net.GetNetClassName() or ""
        primary = raw.split(",")[0].strip()
        nc = self.classes.get(primary)
        if nc is None:
            return 0.25, 0.25
        return pcbnew.ToMM(nc.GetClearance()), pcbnew.ToMM(nc.GetTrackWidth())

    def class_of(self, netname):
        net = self.board.FindNet(netname)
        if net is None:
            return "Default"
        raw = net.GetNetClassName() or ""
        primary = raw.split(",")[0].strip()
        return primary if primary in self.classes else "Default"

    # ----------------------------------------------------------------- build
    def build(self):
        for l in LAYERS:
            self.occupied[l].clear()
            self.owner[l].clear()
            self.hard[l].clear()

        for fp in self.board.GetFootprints():
            if not fp.GetReference():
                continue
            for pad in fp.Pads():
                net = pad.GetNetname()
                if not net:
                    continue
                clr, _ = self.net_params(net)
                self._mark_pad(pad, net, clr)

        for t in self.board.GetTracks():
            net = t.GetNetname()
            if not net:
                continue
            clr, _ = self.net_params(net)
            if t.GetClass() == "PCB_VIA":
                p = t.GetPosition()
                self._mark_via_box(net, clr, pcbnew.ToMM(t.GetWidth()),
                                   pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))
            else:
                self._mark_track(t, net, clr)

    def _claim(self, l, cell, netname):
        """Record that `netname` claims the cell with its clearance ring.

        The first net to claim a cell keeps it; a later net cannot take it
        over, because that would let a net route through the clearance of
        foreign copper.  The real copper (pad body, track body, via barrel)
        always wins over a clearance ring - it is written to `self.hard`.
        """
        if cell in self.hard[l] and self.owner[l].get(cell) != {netname}:
            # foreign copper here - do not claim it
            return
        s = self.owner[l].get(cell)
        if s is None:
            self.owner[l][cell] = {netname}
        elif netname in s:
            pass
        elif s and len(s) == 1:
            # another net already owns this ring cell - it stays blocked
            s.add(netname)
        else:
            s.add(netname)

    def _mark_pad(self, pad, netname, clr):
        """Mark the pad body and its clearance ring.

        The clearance ring is claimed by the pad's own net, so the net can
        still reach its own pad.  Other nets are blocked by it, because
        `free()` only lets a cell through when the claim belongs to this net
        alone.
        """
        bb = pad.GetBoundingBox()
        px0 = gx(pcbnew.ToMM(bb.GetLeft()))
        px1 = gx(pcbnew.ToMM(bb.GetRight()))
        py0 = gx(pcbnew.ToMM(bb.GetTop()))
        py1 = gx(pcbnew.ToMM(bb.GetBottom()))
        cl = int((clr + MAX_HALFWIDTH) / GRID) + 1
        layers = [l for l in LAYERS if pad.IsOnLayer(l)]
        for l in layers:
            # clearance ring: claimed by this net
            for gy in range(py0 - cl, py1 + cl + 1):
                for gxx in range(px0 - cl, px1 + cl + 1):
                    cell = (gxx, gy)
                    self.occupied[l].add(cell)
                    self._claim(l, cell, netname)
            # the pad body is hard copper of this net
            for gy in range(py0, py1 + 1):
                for gxx in range(px0, px1 + 1):
                    cell = (gxx, gy)
                    # a pad body always belongs to its own net; overlapping
                    # pad clearances are resolved in favour of the pad
                    self.owner[l][cell] = {netname}
                    self.hard[l].add(cell)

    def _mark_track(self, t, netname, clr):
        a, b = t.GetStart(), t.GetEnd()
        ax, ay = gx(pcbnew.ToMM(a.x)), gx(pcbnew.ToMM(a.y))
        bx, by = gx(pcbnew.ToMM(b.x)), gx(pcbnew.ToMM(b.y))
        width = pcbnew.ToMM(t.GetWidth())
        l = t.GetLayer()
        self._mark_track_box(l, netname, clr, width,
                             pcbnew.ToMM(a.x), pcbnew.ToMM(a.y),
                             pcbnew.ToMM(b.x), pcbnew.ToMM(b.y))

    def _mark_via_box(self, netname, clr, vdia, ax, ay):
        cx, cy = gx(ax), gx(ay)
        half = max(1, int(round((vdia / 2) / GRID)))
        cl = int((clr + MAX_HALFWIDTH) / GRID) + 1
        r = half + cl
        for l in LAYERS:
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    cell = (cx + dx, cy + dy)
                    self.occupied[l].add(cell)
                    if abs(dx) <= half and abs(dy) <= half:
                        self.owner[l][cell] = {netname}
                        self.hard[l].add(cell)
                    else:
                        self._claim(l, cell, netname)

    def free(self, x, y, l, netname):
        """Can the path of `netname` use cell (x, y) on layer l?

        `self.owner[l]` maps a cell to the SET of nets that claim it: the
        net whose copper sits there and every net whose clearance ring
        reaches into the cell.  A cell may be used when

          * no net claims it, or
          * the only net that claims it is this net.

        A cell claimed by two different nets is blocked for everybody -
        that is the case where two clearance rings overlap.
        """
        if not (self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1):
            return False
        claim = self.owner[l].get((x, y))
        if not claim:
            return True
        if len(claim) == 1:
            return netname in claim
        return False

    def free_pad(self, x, y, l, netname):
        """A pad's own cell is blocked by its own clearance ring; the pad
        itself belongs to our net, so allow it."""
        if not (self.x0 <= x <= self.x1 and self.y0 <= y <= self.y1):
            return False
        claim = self.owner[l].get((x, y))
        return bool(claim) and netname in claim

    def relax_start(self, x, y, layers, netname):
        """The path may start ON the pad: the track's first segment then
        overlaps the pad, which is legal (same net).  Prefer a cell that is
        free of everything, fall back to the pad cell itself."""
        best = None
        for l in layers:
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1),
                           (1, 1), (-1, -1), (1, -1), (-1, 1)):
                nx, ny = x + dx, y + dy
                if self.free(nx, ny, l, netname):
                    d = abs(dx) + abs(dy)
                    if best is None or d < best[0]:
                        best = (d, nx, ny, l)
                    break
        if best is not None:
            return (best[1], best[2], [best[3]])
        # fall back to the pad cell (hard copper of our own net)
        for l in layers:
            claim = self.owner[l].get((x, y))
            if claim and netname in claim:
                return (x, y, [l])
        return None

    # ----------------------------------------------------------------- route
    def astar(self, start, goal, netname, via_allowed=True):
        """start/goal = (x, y, layers).  Returns list of (layer, x, y)."""
        sx, sy, slayers = start
        tx, ty, tlayers = goal

        def h(x, y):
            return abs(x - tx) + abs(y - ty)

        start_states = [(sx, sy, slayers[0])]
        if len(slayers) > 1:
            start_states.append((sx, sy, slayers[1]))
        goal_states = set((tx, ty, l) for l in tlayers)

        gscore = {s: 0 for s in start_states}
        came = {}
        heap = [(h(sx, sy), 0, s) for s in start_states]
        heapq.heapify(heap)
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
            x, y, l = cur
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not self.free(nx, ny, l, netname):
                    continue
                nxt = (nx, ny, l)
                ng = g + 1
                if nxt in goal_states:
                    came[nxt] = cur
                    found = nxt
                    break
                if ng < gscore.get(nxt, 1 << 30):
                    gscore[nxt] = ng
                    came[nxt] = cur
                    heapq.heappush(heap, (ng + h(nx, ny), ng, nxt))
            if found:
                break
            if via_allowed:
                other = LAYERS[1] if l == LAYERS[0] else LAYERS[0]
                if self.free(x, y, other, netname):
                    nxt = (x, y, other)
                    ng = g + VIA_COST
                    if ng < gscore.get(nxt, 1 << 30):
                        gscore[nxt] = ng
                        came[nxt] = cur
                        heapq.heappush(heap, (ng + h(x, y), ng, nxt))
        if found is None:
            return None
        path = []
        cur = found
        while True:
            path.append((cur[2], cur[0], cur[1]))
            if cur in came:
                cur = came[cur]
            else:
                break
        path.reverse()
        return path

    def route_net(self, netname, via_allowed=True):
        """Route a net; returns the list of waypoints or None."""
        pads = []
        for fp in self.board.GetFootprints():
            if not fp.GetReference():
                continue
            for pad in fp.Pads():
                if pad.GetNetname() == netname:
                    pads.append(pad)
        if len(pads) < 2:
            return []

        def cell(pad):
            p = pad.GetPosition()
            ls = [l for l in LAYERS if pad.IsOnLayer(l)]
            if not ls:
                ls = [LAYERS[0]]
            return (gx(pcbnew.ToMM(p.x)), gx(pcbnew.ToMM(p.y)), ls)

        # group pads that sit on the same net and build a spanning chain
        pts = [cell(p) for p in pads]
        # start from the pad that is most isolated (fewest neighbours)
        remaining = list(range(1, len(pts)))
        start_idx = 0
        chain = [pts[0]]
        cur = pts[0]
        while remaining:
            best = None
            for i in remaining:
                d = abs(pts[i][0] - cur[0]) + abs(pts[i][1] - cur[1])
                if best is None or d < best[0]:
                    best = (d, i)
            i = best[1]
            remaining.remove(i)
            chain.append(pts[i])
            cur = pts[i]

        result = []
        prev = chain[0]
        for target in chain[1:]:
            s = self.relax_start(prev[0], prev[1], prev[2], netname)
            g = self.relax_start(target[0], target[1], target[2], netname)
            if s is None or g is None:
                return None
            seg = self.astar(s, g, netname, via_allowed)
            if seg is None:
                return None
            if result:
                result.extend(seg[1:])
            else:
                result.extend(seg)
            prev = target
        return result

    # ------------------------------------------------------------------ write
    def commit(self, netname, path):
        """Turn a grid path into tracks + vias on the board.

        After writing, the obstacle map is refreshed so that the next net
        sees this net's copper - otherwise a later net would be routed
        straight through an already routed trace.
        """
        net = self.board.FindNet(netname)
        clr, width = self.net_params(netname)
        cls = self.classes.get(self.class_of(netname))
        vdia = pcbnew.ToMM(cls.GetViaDiameter()) if cls else 0.6
        vdrill = pcbnew.ToMM(cls.GetViaDrill()) if cls else 0.3

        # collapse collinear points
        simple = []
        for p in path:
            if simple and simple[-1] == p:
                continue
            simple.append(p)

        # merge collinear segments into as few tracks as possible
        # each entry: (layer, start_xy, end_xy)
        merged = []
        for i in range(1, len(simple)):
            l0, x0, y0 = simple[i - 1]
            l1, x1, y1 = simple[i]
            if merged and merged[-1][0] == l0:
                pl, sa, sb = merged[-1]
                # direction of the previous segment vs the new one
                d0 = (sb[0] - sa[0], sb[1] - sa[1])
                d1 = (x1 - x0, y1 - y0)
                if d0[0] * d1[1] == d0[1] * d1[0] and \
                        d0[0] * d1[0] + d0[1] * d1[1] > 0:
                    merged[-1] = (pl, sa, (x1, y1))
                    continue
            merged.append((l0, (x0, y0), (x1, y1)))

        # rebuild the waypoint list from the merged segments
        simple = []
        for pl, sa, sb in merged:
            simple.append((pl, sa[0], sa[1]))
            simple.append((pl, sb[0], sb[1]))

        out = []
        for i in range(1, len(simple)):
            (l0, x0, y0), (l1, x1, y1) = simple[i - 1], simple[i]
            if l0 == l1 and (x0, y0) != (x1, y1):
                t = pcbnew.PCB_TRACK(self.board)
                t.SetStart(pcbnew.VECTOR2I(mm(x0 * GRID), mm(y0 * GRID)))
                t.SetEnd(pcbnew.VECTOR2I(mm(x1 * GRID), mm(y1 * GRID)))
                t.SetWidth(mm(width))
                t.SetLayer(l0)
                t.SetNet(net)
                self.board.Add(t)
                out.append(("T", l0, x0 * GRID, y0 * GRID, x1 * GRID, y1 * GRID))
            elif l0 != l1 and (x0, y0) == (x1, y1):
                v = pcbnew.PCB_VIA(self.board)
                v.SetPosition(pcbnew.VECTOR2I(mm(x0 * GRID), mm(y0 * GRID)))
                v.SetWidth(mm(vdia))
                v.SetDrill(mm(vdrill))
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(LAYERS[0], LAYERS[1])
                v.SetNet(net)
                self.board.Add(v)
                out.append(("V", l0, x0 * GRID, y0 * GRID, x1 * GRID, y1 * GRID))

        # refresh the obstacle map with what we just wrote
        for kind, l, ax, ay, bx, by in out:
            if kind == "T":
                self._mark_track_box(l, netname, clr, width,
                                     ax, ay, bx, by)
            else:
                self._mark_via(netname, clr, vdia, ax, ay)
        return out
    def _mark_track_box(self, l, netname, clr, width, ax, ay, bx, by):
        """Block the corridor around a track.

        A track of width W centred on the line occupies +-W/2.  Another net
        must keep a clearance C from its EDGE, so the band extends to
        W/2 + C on each side.

        Two kinds of cells are created:
          * the track body (-+W/2): HARD copper, nobody but this net may
            touch it,
          * the clearance band: also blocked for everybody else, but owned by
            this net so that this net can still run parallel to its own
            track (e.g. two branches of the same net).
        """
        axg, ayg = gx(ax), gx(ay)
        bxg, byg = gx(bx), gx(by)
        half = max(1, int(round(width / 2 / GRID)))
        cl = int((clr + MAX_HALFWIDTH) / GRID) + 1
        steps = max(abs(bxg - axg), abs(byg - ayg), 1)
        for i in range(steps + 1):
            cx = axg + (bxg - axg) * i // steps
            cy = ayg + (byg - ayg) * i // steps
            # the track body belongs to this net and is hard copper
            for dy in range(-half, half + 1):
                for dx in range(-half, half + 1):
                    cell = (cx + dx, cy + dy)
                    self.occupied[l].add(cell)
                    self.owner[l][cell] = {netname}
                    self.hard[l].add(cell)
            # the clearance band is claimed by this net as well
            for dy in range(-(half + cl), half + cl + 1):
                for dx in range(-(half + cl), half + cl + 1):
                    if abs(dx) > half or abs(dy) > half:
                        cell = (cx + dx, cy + dy)
                        self.occupied[l].add(cell)
                        self._claim(l, cell, netname)

    def _mark_via(self, netname, clr, vdia, ax, ay):
        """Via keep-out.

        The via barrel is HARD copper: only its own net may touch it.  The
        clearance ring around it is blocked for everybody else.
        """
        cx, cy = gx(ax), gx(ay)
        half = max(1, int(round((vdia / 2) / GRID)))
        cl = int((clr + MAX_HALFWIDTH) / GRID) + 1
        r = half + cl
        for l in LAYERS:
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    cell = (cx + dx, cy + dy)
                    self.occupied[l].add(cell)
                    if abs(dx) <= half and abs(dy) <= half:
                        # the barrel itself is hard copper
                        self.owner[l][cell] = {netname}
                        self.hard[l].add(cell)
                    else:
                        self._claim(l, cell, netname)


def main():
    board = pcbnew.LoadBoard(V3)
    r = Router(board)
    r.build()
    print(f"grid {GRID}mm  bounds x {r.x0}..{r.x1} y {r.y0}..{r.y1}")
    print(f"occupied F.Cu={len(r.occupied[pcbnew.F_Cu])} B.Cu={len(r.occupied[pcbnew.B_Cu])}")

    # list the nets that need routing
    need = []
    seg = defaultdict(int)
    for t in board.GetTracks():
        seg[t.GetNetname()] += 1
    for fp in board.GetFootprints():
        if not fp.GetReference():
            continue
        for pad in fp.Pads():
            n = pad.GetNetname()
            if n and not n.startswith("unconnected-") and n != "GND":
                if seg[n] == 0 and n not in [x[0] for x in need]:
                    need.append((n, fp.GetReference() + "." + pad.GetNumber()))

    print(f"\nnets needing routing: {len(need)}")
    for n, p in need:
        print(f"  {n:24} (e.g. {p})")

    # try routing them all
    print("\nrouting...")
    ok = 0
    failed = []
    for n, _ in need:
        path = r.route_net(n)
        if path is None:
            failed.append(n)
            print(f"  FAIL {n}")
            continue
        r.commit(n, path)
        ok += 1
        print(f"  ok   {n}  ({len(path)} waypoints)")
    print(f"\nrouted {ok}, failed {len(failed)}: {failed}")

    safe_board.save(board, "the route of the maze router")
    print("saved")


if __name__ == "__main__":
    main()
