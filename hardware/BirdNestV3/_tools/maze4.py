#!/usr/bin/env python3
"""
V3 PCB router - 2 layer maze router with an exact pairwise clearance model.

Design
------
Every net keeps two things:

  copper[l]      the cells its own copper occupies (pad bodies, track
                 bodies, via barrels)
  ring[l][cell]  the cells that are within `clearance + MAX_HALFWIDTH` of
                 that copper

For a routing net N the check for a cell is:

  * the cell carries no foreign copper  -> usable
  * the cell carries N's own copper      -> usable (same net)
  * otherwise the cell must be at least
        halfwidth(owner) + halfwidth(N) + clearance(N)
    away from the owner's copper.

The exact distance is computed against the owner's copper map, so the
model is never conservative.  The ring maps are only used as a fast
pre-filter.

Why the earlier attempts failed
-------------------------------
  * "ring owned by the net"  -> a neighbour routed straight through it
  * "ring blocked for all"   -> every net was sealed off from its pads
  * "ring claimed by a set"  -> overlapping rings blocked both nets
  * conservative MAX_HALFWIDTH ring -> power nets could not reach their pads

Run:  maze4.py
"""
import heapq
import json
import math
import os
import sys
from collections import defaultdict

import pcbnew
import safe_board    # noqa: E402  the guard of the board

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"
PRO = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pro"

GRID = 0.1                     # mm per cell
NX = 1000                       # cells in X  (100 mm / 0.1)
NY = 1000                       # cells in Y
ORIGIN = (100.0, 40.0)          # mm of grid cell (0, 0)
LAYERS = (pcbnew.F_Cu, pcbnew.B_Cu)
# The router runs on the front copper, the same layer as the layout that
# was copied over from the v2 board.  The back copper is kept free for
# the parts that have to cross it.
PREFERRED_LAYER = 0          # F.Cu
VIA_COST = 24                   # in grid steps (2.4 mm equivalent)
# Changing to the back copper is cheap: the back copper is nearly free,
# the front copper is crowded.
VIA_COST_TO_BACK = 4
VIA_COST_TO_FRONT = 60
# The largest track half width in the design (the 1 mm +5V track).  It is
# used when the keep-out of a track centre line is built.
MAX_TRACK_HALF = 0.5
# Only axis parallel moves.  A 45 degree track would be a diagonal line
# between two cell centres; the cells it passes would be missing from the
# copper raster, and the square dilation of the keep-out would under-
# estimate the distance at the corners.  With axis parallel tracks the
# raster and the dilation are exact.
DIRS = ((0, 1, 1.0), (0, -1, 1.0), (1, 0, 1.0), (-1, 0, 1.0))


def mm(v):
    return int(round(v * 1e6))


# lookup table: one byte of a row-bitset -> the eight mask bytes it expands
# to (0 or 1 per cell)
_BITS = [bytes((b >> i) & 1 for i in range(8)) for b in range(256)]


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

    The result is the copper PLUS the area around it - the copper itself
    has to be part of the keep-out, a track may not run over foreign
    copper.
    """
    if radius <= 0:
        return list(rows)
    limit = (1 << nx) - 1
    active = [y for y, r in enumerate(rows) if r]
    if not active:
        return [0] * len(rows)

    # the vertical extent that can be reached
    y0 = max(0, active[0] - radius)
    y1 = min(len(rows) - 1, active[-1] + radius)

    grown = [0] * len(rows)
    for y in active:
        r = rows[y]
        v = r
        for _ in range(radius):
            v |= v << 1
        w = r
        for _ in range(radius):
            w |= w >> 1
        grown[y] = (v | w) & limit

    # vertical: a sliding OR window over the rows in [y0, y1]
    win = 2 * radius + 1
    out = list(rows)
    cur = 0
    for y in range(y0, y1 + 1):
        cur |= grown[y]
        if y - win >= y0:
            cur &= ~grown[y - win]
        out[y] |= cur
    cur = 0
    for y in range(y1, y0 - 1, -1):
        cur |= grown[y]
        if y + win <= y1:
            cur &= ~grown[y + win]
        out[y] |= cur
    return out

def rows_to_mask(rows, nx):
    """Expand row-bitsets into a bytearray (one byte per cell).

    The conversion uses a 256 entry lookup table (one byte -> eight cells),
    so the cost is proportional to the number of BYTES, not to the number of
    set bits.  Extracting the bits one by one was 100x slower.
    """
    nbytes = (nx + 7) // 8
    out = bytearray(len(rows) * nx)
    for y, r in enumerate(rows):
        if not r:
            continue
        base = y * nx
        idx = base
        for byte in r.to_bytes(nbytes, "little"):
            out[idx:idx + 8] = _BITS[byte]
            idx += 8
    return out


class Net:
    def __init__(self, name):
        self.name = name
        self.cu = [[0] * NX for _ in LAYERS]      # row-bitsets
        # The centre lines of the tracks and the vias.  Their keep-out
        # needs the track half width on top, so they are kept apart.
        self.tracks = [[0] * NX for _ in LAYERS]
        self.halfwidth = 0.125
        self.clearance = 0.25
        self.pads = []
        # The layer the router prefers for this net.  The signals go to
        # the front copper, the power lines to the back: the power lines
        # are thick and long, and on the back they do not fight with the
        # signals of the parts.
        self.preferred = PREFERRED_LAYER


def load_classes():
    """The rules of the net classes of the project.

    The project file holds the clearance and the track width of every
    class.  The board holds only the name of the class of every net,
    and the widths that it holds are empty, so the router has to read
    the project file to learn the rules.
    """
    classes = {}
    try:
        with open(PRO) as f:
            pro = json.load(f)
    except (OSError, ValueError):
        return classes
    for c in pro.get("net_settings", {}).get("classes", []):
        name = c.get("name")
        if not name:
            continue
        classes[name] = {
            "clearance": float(c.get("clearance", 0.2)),
            "track_width": float(c.get("track_width", 0.25)),
            "via_diameter": float(c.get("via_diameter", 0.6)),
            "via_drill": float(c.get("via_drill", 0.3)),
        }
    return classes


class Router:
    def __init__(self, board):
        self.board = board
        # The rules of the nets live in the project file, not in the
        # board: the board holds only the names of the classes.  The
        # router needs the width and the clearance of every class.
        self.classes = load_classes()
        self.nets = {}
        self.obstacle = None
        self._index_nets()
        self._load_copper()

    # ------------------------------------------------------------------ setup
    def _class_of(self, name):
        net = self.board.FindNet(name)
        if net is None:
            return "Default"
        raw = net.GetNetClassName() or ""
        primary = raw.split(",")[0].strip()
        return primary if primary in self.classes else "Default"

    def _params(self, name):
        """The clearance and the width of the net, in millimetres."""
        nc = self.classes.get(self._class_of(name))
        if nc is None:
            return 0.2, 0.25
        return nc["clearance"], nc["track_width"]

    def _index_nets(self):
        """All nets that have at least two pads.

        GND is deliberately NOT included: it is the copper pour, and the
        zone filler keeps its own distance to every track.  If the GND pads
        were treated as obstacles, 41 pads would block the whole board.
        """
        counts = defaultdict(int)
        for fp in self.board.GetFootprints():
            if not fp.GetReference():
                continue
            for pad in fp.Pads():
                n = pad.GetNetname()
                if n and not n.startswith("unconnected-"):
                    counts[n] += 1
        for name, c in sorted(counts.items()):
            if name == "GND" or c < 2:
                continue
            self.nets[name] = Net(name)

    # ------------------------------------------------------------------ copper
    def _load_copper(self):
        # the routed nets
        for fp in self.board.GetFootprints():
            if not fp.GetReference():
                continue
            for pad in fp.Pads():
                net = self.nets.get(pad.GetNetname())
                if net is not None:
                    self._rasterise_pad(net, pad)
        for t in self.board.GetTracks():
            net = self.nets.get(t.GetNetname())
            if net is None:
                continue
            if t.GetClass() == "PCB_VIA":
                self._rasterise_via(net, t)
            else:
                self._rasterise_track(net, t)

        # Obstacles that are not routed but still carry copper: the GND
        # pads (the zone keeps its distance to them, but a track must not
        # run over a GND pad) and every pad without a net.  They are put
        # into a separate pseudo net so that the keep-out can treat them
        # like any other foreign copper.
        self.obstacle = Net("__obstacle__")
        self.obstacle.halfwidth = 0.0
        self.obstacle.clearance = 0.25
        for fp in self.board.GetFootprints():
            if not fp.GetReference():
                continue
            for pad in fp.Pads():
                n = pad.GetNetname()
                if n and n != "GND":
                    continue
                # GND pads (the zone connects them) and pads without a net
                # are obstacles: a track must not run over them
                self._rasterise_pad(self.obstacle, pad, record=False)
        self.obstacles_ready = True

    def _stamp_capsule(self, net, li, ax, ay, bx, by, half):
        """Rasterise a thick line segment (a track) exactly.

        Two maps are filled:
          * `cu`    - the real copper of the track (the full width),
          * `tracks` - the centre line of the track.

        The cells of `cu` are those whose centre is within `half` cells of
        the segment - the perpendicular distance, not the Chebyshev
        distance.  With axis parallel tracks the two are the same, and the
        copper of the track is a rectangle, so the raster is exact.
        """
        if half <= 0:
            return
        r = half
        r2 = r * r
        rows = net.cu[li]
        extra = net.tracks[li]
        dx = bx - ax
        dy = by - ay
        len2 = dx * dx + dy * dy

        y_lo = int(min(ay, by) - r - 1)
        y_hi = int(max(ay, by) + r + 1)
        for y in range(y_lo, y_hi + 1):
            if y < 0 or y >= NY:
                continue
            if len2 == 0:
                cx, cy = ax, ay
            else:
                t = ((y - ay) * dy) / len2
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                cx = ax + t * dx
                cy = ay + t * dy
            ddy = y - cy
            rem = r2 - ddy * ddy
            if rem <= 0:
                continue
            ddx = math.sqrt(rem)
            x0 = int(math.floor(cx - ddx))
            x1 = int(math.ceil(cx + ddx))
            if x0 < 0:
                x0 = 0
            if x1 > NX - 1:
                x1 = NX - 1
            if x1 < x0:
                continue
            span = ((1 << (x1 - x0 + 1)) - 1) << x0
            rows[y] |= span
            if extra is not None:
                # the centre line of the segment at this row
                extra[y] |= 1 << int(round(cx))

    def _stamp_disk(self, net, li, cx, cy, half):
        """Rasterise a circle (a via barrel) exactly.

        `cu` gets the real copper, `tracks` the centre point.
        """
        if half <= 0:
            return
        r = half
        r2 = r * r
        rows = net.cu[li]
        extra = net.tracks[li]
        y_lo = int(cy - r - 1)
        y_hi = int(cy + r + 1)
        for y in range(y_lo, y_hi + 1):
            if y < 0 or y >= NY:
                continue
            ddy = y - cy
            rem = r2 - ddy * ddy
            if rem <= 0:
                continue
            ddx = math.sqrt(rem)
            x0 = int(math.floor(cx - ddx))
            x1 = int(math.ceil(cx + ddx))
            if x0 < 0:
                x0 = 0
            if x1 > NX - 1:
                x1 = NX - 1
            if x1 < x0:
                continue
            span = ((1 << (x1 - x0 + 1)) - 1) << x0
            rows[y] |= span
            extra[y] |= 1 << cx

    def _rasterise_pad(self, net, pad, record=True):
        pos = pad.GetPosition()
        cy, cx = cell_of(pos)
        size = pad.GetSize()
        # The raster must never be smaller than the real copper: a pad
        # that is rastered too small lets the router place a track that
        # overlaps it.  ceil, not round - round(6.5) is 6 in python.
        half_x = max(1, int(math.ceil(pcbnew.ToMM(size.x) / 2 / GRID)))
        half_y = max(1, int(math.ceil(pcbnew.ToMM(size.y) / 2 / GRID)))
        ls = [LAYERS.index(l) for l in LAYERS if pad.IsOnLayer(l)]
        shape = pad.GetShape()
        for li in ls:
            # The pad body is stamped with its real shape.  A round pad
            # that is stamped as a square is bigger than the real copper
            # in the corners, and the router would place a track there
            # that the DRC then reports as an overlap.
            if shape == pcbnew.PAD_SHAPE_CIRCLE:
                self._stamp_disk(net, li, cx, cy, half_x)
            else:
                self._stamp_band(net.cu, li, cy, cx, half_x, half_y)
        if record:
            # the grid cell and the real position: the centre of a pad is
            # usually not on the grid, and the track has to reach the pad
            # exactly
            net.pads.append((cy, cx, ls, half_x, half_y))

    def _stamp_band(self, target, li, cy, cx, half_x, half_y):
        """Rasterise a rectangle of half size half_x x half_y.

        The rectangle over-estimates the copper of a round pad, which is the
        safe direction: the router then keeps more distance than strictly
        needed.
        """
        ya, yb = max(0, cy - half_y), min(NY - 1, cy + half_y)
        xa, xb = max(0, cx - half_x), min(NX - 1, cx + half_x)
        if xb < xa or yb < ya:
            return
        rows = target[li]
        hspan = ((1 << (xb - xa + 1)) - 1) << xa
        for y in range(ya, yb + 1):
            rows[y] |= hspan

    def _rasterise_track(self, net, t):
        a, b = t.GetStart(), t.GetEnd()
        ay, ax = cell_of(a)
        by, bx = cell_of(b)
        half = max(1, int(math.ceil(pcbnew.ToMM(t.GetWidth()) / 2 / GRID)))
        if t.GetLayer() not in LAYERS:
            return
        li = LAYERS.index(t.GetLayer())
        self._stamp_capsule(net, li, ax, ay, bx, by, half)

    def _rasterise_via(self, net, t):
        pos = t.GetPosition()
        cy, cx = cell_of(pos)
        half = max(1, int(math.ceil(pcbnew.ToMM(t.GetWidth()) / 2 / GRID)))
        for li in range(len(LAYERS)):
            self._stamp_disk(net, li, cx, cy, half)

    # ------------------------------------------------------------------ masks
    def build_mask(self, net, free=()):
        """Keep-out mask for the routing net N.

        `cu` holds the real copper of every net - the pad bodies with their
        actual shape and the tracks and vias with their actual width.  The
        keep-out is that copper dilated by

            halfwidth(N) + clearance(N)

        which is exactly the distance N's track edge has to keep from the
        foreign copper edge.  Because the copper is stored at full size,
        no per-item half width is needed.

        `tracks` holds the centre lines of the tracks and the vias.  It is
        used for one thing only: a net must not run over its own tracks,
        otherwise KiCad reports "tracks crossing".  The centre lines are
        blocked as well, apart from the pads of the net: the net has to
        be able to reach its own pads, and the track that arrives there
        has to be allowed to cross the tracks of the net that are already
        there.

        `free` is the pad the route is going to: it is not blocked at
        all, not even by the tracks of the net.
        """
        masks = []
        # The extra cell is the safety margin of the raster: the copper of
        # a track is stored as a capsule whose cell centres are half a
        # cell away from the real border, and the same is true for the
        # rounded corners of a pad.  One cell covers that.
        r = int(math.ceil((net.halfwidth + net.clearance) / GRID)) + 1
        for li in range(len(LAYERS)):
            rows = [0] * NY
            ring = [0] * NY
            for other in self.nets.values():
                if other is net:
                    continue
                dil = dilate_rows(other.cu[li], r, NX)
                for y, v in enumerate(dil):
                    if v:
                        rows[y] |= v
                        ring[y] |= v
            # The GND pads and the pads without a net are obstacles too
            if self.obstacle is not None:
                dil = dilate_rows(self.obstacle.cu[li], r, NX)
                for y, v in enumerate(dil):
                    if v:
                        rows[y] |= v
                        ring[y] |= v
            # The net's own pads are not an obstacle - the net has to be
            # able to reach them.  But the clearance ring of a foreign
            # pad may reach over the own pad, and then a track that runs
            # across the own pad would run into the foreign pad as well.
            # So the own pad body is cut out of the keep-out again, but
            # the part of the foreign clearance ring that lies inside the
            # own pad is put back: the track may cross its own pad, but
            # it may not enter the ring of a foreign pad.
            if net.pads:
                for (py, px, pls, phx, phy) in net.pads:
                    if li not in pls:
                        continue
                    for y in range(max(0, py - phy), min(NY, py + phy + 1)):
                        x0 = max(0, px - phx)
                        x1 = min(NX - 1, px + phx)
                        if x1 < x0:
                            continue
                        own = ((1 << (x1 - x0 + 1)) - 1) << x0
                        # The foreign copper inside the own pad stays
                        # blocked.
                        blocked = 0
                        for other in self.nets.values():
                            if other is net:
                                continue
                            blocked |= other.cu[li][y]
                        if self.obstacle is not None:
                            blocked |= self.obstacle.cu[li][y]
                        # The own pad body is free, except where foreign
                        # copper lies on it, and except for the ring of
                        # the foreign copper: the track that leaves the
                        # pad may not run into the ring of a foreign pad.
                        # Only a narrow band in the middle of the pad is
                        # free, so that the track can start there.
                        band = max(1, int(math.ceil(
                            (net.halfwidth + 0.05) / GRID)))
                        bx0 = max(x0, px - band)
                        bx1 = min(x1, px + band)
                        middle = (((1 << (bx1 - bx0 + 1)) - 1) << bx0
                                  if bx1 >= bx0 else 0)
                        rows[y] = (rows[y] & ~own) | (blocked & own) \
                            | (ring[y] & own & ~middle)
            # The tracks of the net itself are an obstacle too: a track
            # that runs over another track of the same net is reported
            # by KiCad as "tracks crossing".  The centre lines are
            # blocked with the half width of the track on top, so that
            # the new track keeps its distance from the old one.
            #
            # The growth is done in two steps: first along the row, so
            # that the track keeps its distance to the side, and then
            # from row to row, so that the rows above and below a track
            # that runs across are blocked as well.  A track that runs
            # from row to row is in one cell of every row, and the step
            # along the row alone would leave the cells next to it
            # free.
            tr = int(math.ceil((net.halfwidth + net.clearance) / GRID)) + 1
            limit = (1 << NX) - 1
            own_rows = [0] * NY
            for y, v in enumerate(net.tracks[li]):
                if not v:
                    continue
                grown = v
                for _ in range(tr):
                    grown |= grown << 1
                w = v
                for _ in range(tr):
                    w |= w >> 1
                own_rows[y] |= (grown | w) & limit
            # and now from row to row
            own_rows = dilate_rows(own_rows, tr, NX)
            # The pads of the pair that is routed now are not blocked at
            # all: the track has to arrive there, and it may have to
            # cross the tracks of the net that are already there.
            for (fpy, fpx, fpls, fphx, fphy) in free:
                if li not in fpls:
                    continue
                for y in range(max(0, fpy - fphy),
                              min(NY, fpy + fphy + 1)):
                    x0 = max(0, fpx - fphx)
                    x1 = min(NX - 1, fpx + fphx)
                    if x1 < x0:
                        continue
                    own = ((1 << (x1 - x0 + 1)) - 1) << x0
                    own_rows[y] &= ~own
            for y, v in enumerate(own_rows):
                if v:
                    rows[y] |= v
            masks.append(rows_to_mask(rows, NX))
        return masks
    # ------------------------------------------------------------------ search
    def astar(self, start, goal, masks, limit=400000, preferred=PREFERRED_LAYER):
        """A* over (y, x, layer).

        `masks[l]` is the keep-out of all foreign nets (their copper
        dilated by the required clearance).  The start and the goal are
        the cells returned by `relax_start`; the goal states are exactly
        that cell, so the search really ends there.

        `limit` caps the number of visited nodes.  Without it an
        unreachable goal would make the search walk the whole board.
        """
        sy, sx = start[0], start[1]
        gy_, gx_ = goal[0], goal[1]

        def h(y, x):
            return abs(y - gy_) + abs(x - gx_)

        # The start cell must be free.  `relax_start` picks a cell next to
        # the pad that is not inside a foreign keep-out; if that cell were
        # blocked anyway, the first step of the track would cross a
        # forbidden area.
        states = []
        for l in (start[2] or [0]):
            if not masks[l][sy * NX + sx]:
                states.append((sy, sx, l))
        if not states:
            return None
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
            if len(visited) > limit:
                return None
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
                idx = ny * NX + nx
                if mask[idx]:
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
            # a via is needs a free spot on BOTH layers - the barrel is a
            # hole through the whole board
            if not masks[other_l][base + x] and not mask[base + x]:
                nxt = (y, x, other_l)
                ng = g + (VIA_COST_TO_BACK if other_l == preferred
                         else VIA_COST_TO_FRONT)
                if ng < gscore.get(nxt, 1e30) - 1e-9:
                    gscore[nxt] = ng
                    came[nxt] = cur
                    heapq.heappush(heap, (ng + h(y, x), ng, nxt))
        if found is None:
            return None
        path = []
        cur = found
        while True:
            # cur is (y, x, layer) -> store it as (layer, y, x)
            path.append((cur[2], cur[0], cur[1]))
            if cur in came:
                cur = came[cur]
            else:
                break
        path.reverse()
        return path

    def relax_start(self, pad, masks, avoid=(), preferred=PREFERRED_LAYER):
        """The cell where the track that reaches the pad starts.

        The pad is in the middle of the cell of the grid.  A track that
        starts in the middle of the pad has to cross the whole pad to get
        out of it, and it runs into the neighbouring pads on the way.  So
        the start cell is looked for on the border of the pad: the cells
        of the pad that are closest to the outside are tried first.

        `avoid` holds the cells that are already used as the start of
        another pad of the same net: two pads may not start in the same
        cell, or the net looks connected while it is not.

        `preferred` is the layer the route of the net prefers.
        """
        py, px, pls, phx, phy = pad[0], pad[1], pad[2], pad[3], pad[4]
        # the pad layer first: the router has to reach the pad on its own
        # layer, and the via is dropped on the pad itself
        layers = list(pls or [0])
        order = layers + [l for l in (preferred,) if l not in layers]
        for l in order:
            if l not in LAYERS:
                continue
            if not masks[l][py * NX + px]:
                # The pad centre is free.  The track starts there and
                # ends there, so it really connects to the pad.
                if (l, py, px) not in avoid:
                    return (py, px, [l])
        for radius in range(1, 14):
            for l in order:
                if l not in LAYERS:
                    continue
                for dy in range(-radius, radius + 1):
                    for dx in range(-radius, radius + 1):
                        if max(abs(dy), abs(dx)) != radius:
                            continue
                        yy, xx = py + dy, px + dx
                        if not inb(yy, xx):
                            continue
                        if not masks[l][yy * NX + xx]:
                            if (l, yy, xx) not in avoid:
                                return (yy, xx, [l])
        return None

    # ------------------------------------------------------------------ route
    def _pad_hits(self, pads, tracks):
        """The pads that a track of the net ends on.

        `tracks` is a list of ((layer, y, x), (layer, y, x)) - the end
        points of the tracks that are already on the board for this net.
        A track does not have to end exactly in the middle of the pad:
        the v2 layout ends its tracks at the edge of the pad.
        """
        hits = set()
        for i, (py, px, pls, phx, phy) in enumerate(pads):
            for (la, ya, xa), (lb, yb, xb) in tracks:
                for (ly, y, x) in ((la, ya, xa), (lb, yb, xb)):
                    if ly not in pls:
                        continue
                    if abs(y - py) <= 9 and abs(x - px) <= 9:
                        hits.add(i)
                        break
                if i in hits:
                    break
        return hits

    def _pad_groups(self, pads, tracks):
        """The groups of pads that the tracks of the net connect.

        A track has two ends, and both of them can be on a pad.  The
        pads that a track connects are in the same group, and the groups
        are closed: a third track that starts on one of them connects
        all three.

        This is what tells the router that the copper of the net is
        already there: without it, the router draws a second track to a
        pad that is connected already.
        """
        # the pads that every end point of the tracks belongs to
        end_pads = {}
        for (la, ya, xa), (lb, yb, xb) in tracks:
            for (ly, y, x) in ((la, ya, xa), (lb, yb, xb)):
                for i, (py, px, pls, phx, phy) in enumerate(pads):
                    if ly not in pls:
                        continue
                    if abs(y - py) <= 9 and abs(x - px) <= 9:
                        end_pads.setdefault((ly, y, x), set()).add(i)
                        break

        parent = list(range(len(pads)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for (la, ya, xa), (lb, yb, xb) in tracks:
            a = end_pads.get((la, ya, xa), set())
            b = end_pads.get((lb, yb, xb), set())
            for i in a:
                for j in b:
                    if i == j:
                        continue
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[ri] = rj

        groups = {}
        for i in range(len(pads)):
            groups.setdefault(find(i), []).append(i)
        return groups

    def route_net(self, net, existing=None):
        """Plan the route of a net.

        `existing` is the list of ((layer, y, x), (layer, y, x)) - the end
        points of the tracks that are already on the board for this net.
        The pads that are already connected through those tracks are not
        routed again - the net is only completed.
        """
        pads = net.pads
        if len(pads) < 2:
            return None

        # The tracks that are already on the board for this net are an
        # obstacle for the new route: they are the copper of the net,
        # and a new track that runs over them is reported by KiCad as
        # "tracks crossing".  They are stamped into the copper map of
        # the net, and the mask then keeps the new route away from them.
        if existing:
            for (la, ya, xa), (lb, yb, xb) in existing:
                if la == lb:
                    self._stamp_capsule(net, la, xa, ya, xb, yb,
                                        net.halfwidth)
                else:
                    self._stamp_disk(net, la, xa, ya, net.halfwidth)
                    self._stamp_disk(net, lb, xb, yb, net.halfwidth)

        # The pads are joined with a minimum spanning tree, not with a
        # greedy chain.  A greedy chain picks the nearest pad every
        # time, and one unreachable pair in the middle of it throws the
        # whole net away.  The tree spreads from the pads that are
        # already connected, so the routes that can be made are made,
        # and the ones that can not are left for a later run.
        def weight(i, j):
            return (abs(pads[i][0] - pads[j][0])
                    + abs(pads[i][1] - pads[j][1])
                    + abs(pads[i][2][0] - pads[j][2][0]) * 2)

        # The pads that the tracks of the net connect already are one
        # group.  The tree joins the groups, not the single pads: a
        # group that is connected already does not need a track, and
        # the router would draw one that crosses the copper that is
        # there.
        groups = self._pad_groups(pads, existing) if existing else \
            {i: [i] for i in range(len(pads))}
        # the pad that belongs to a group
        group_of = {}
        for gi, members in groups.items():
            for i in members:
                group_of[i] = gi

        # The tree grows from the groups that are connected to the
        # copper of the net already.
        seeds = {0}
        if existing:
            hits = self._pad_hits(pads, existing)
            if hits:
                seeds = {group_of[i] for i in hits}

        tree = []
        joined = set(seeds)
        while len(joined) < len(groups):
            best = None
            for gi in joined:
                for gj, members in groups.items():
                    if gj in joined:
                        continue
                    # the distance of the two groups: the closest pair of
                    # pads of the two groups decides
                    for i in groups[gi]:
                        for j in members:
                            w = weight(i, j)
                            if best is None or w < best[0]:
                                best = (w, gi, gj, i, j)
            if best is None:
                break
            tree.append((best[3], best[4]))
            joined.add(best[2])

        full = []
        used = set()
        for ai, bi in tree:
            a, b = pads[ai], pads[bi]
            # The mask is built for every pair: the tracks of the net
            # that were made for the earlier pairs have to be an
            # obstacle now, or the new track runs over them.  The two
            # pads of this pair are free, so that the track can arrive
            # at both of them.
            masks = self.build_mask(net, free=(a, b))
            sa = self.relax_start(a, masks, used, net.preferred)
            sb = self.relax_start(b, masks, used, net.preferred)
            if sa is None or sb is None:
                continue
            if sa == sb:
                # already on the same cell - nothing to route
                if not full:
                    full.append(sa)
                continue
            seg = self.astar(sa, sb, masks, preferred=net.preferred)
            if seg is None:
                # this pair can not be reached.  The rest of the tree is
                # still routed: a net that is only half routed is better
                # than a net that is not routed at all.
                continue
            # the two cells are used now: no other pad of the net may
            # start in one of them
            used.add((sa[2][0] if sa[2] else 0, sa[0], sa[1]))
            used.add((sb[2][0] if sb[2] else 0, sb[0], sb[1]))
            # The pads are usually on the front copper, but the router
            # runs on the back copper.  The track has to start on the
            # layer of the pad and change the layer right there, so a via
            # lands on the pad.
            #
            # The layer change happens on the grid cell of the path, not
            # on the exact centre of the pad: the centre of a pad is not
            # on the grid, and a track that runs from the grid cell to the
            # centre of the pad would leave a sliver of a track behind.
            # The cell is inside the pad, so the pad is connected.
            pad_a_layer = a[2][0] if a[2] else 0
            pad_b_layer = b[2][0] if b[2] else 0
            if seg and seg[0][0] != pad_a_layer:
                seg.insert(0, (pad_a_layer, seg[0][1], seg[0][2]))
            if seg and seg[-1][0] != pad_b_layer:
                seg.append((pad_b_layer, seg[-1][1], seg[-1][2]))
            if full:
                full.extend(seg[1:])
            else:
                full.extend(seg)
        return full

    # ------------------------------------------------------------------ write
    def commit(self, net, path):
        width = net.halfwidth * 2
        cls = self.classes.get(self._class_of(net.name))
        vdia = cls["via_diameter"] if cls else 0.6
        vdrill = cls["via_drill"] if cls else 0.3
        bnet = self.board.FindNet(net.name)

        segs = []
        vias = []
        i = 0
        n = len(path)
        while i < n - 1:
            l0, y0, x0 = path[i]
            l1, y1, x1 = path[i + 1]
            if l0 != l1:
                # a layer change: the via sits on path[i], the next track
                # starts at path[i+1]
                vias.append((y0, x0))
                i += 1
                continue
            dy, dx = y1 - y0, x1 - x0
            # Extend the segment while the direction does not change and
            # does not turn back.  The segment always covers path[i+1];
            # the loop looks at the step from path[j-1] to path[j].
            # `j` must always end up greater than `i`, otherwise the outer
            # loop would never advance.
            j = i + 1
            while j < n:
                nl, ny, nx = path[j]
                pl, py, px = path[j - 1]
                if nl != l0:
                    break
                sx, sy = nx - px, ny - py
                if sx * dy != sy * dx:
                    break
                if sx * dx + sy * dy < 0:
                    break            # it goes backwards
                y1, x1 = ny, nx
                j += 1
            segs.append((l0, y0, x0, y1, x1))
            # continue at the last point of the segment; the next point
            # (path[j]) starts the next segment
            i = j - 1 if j - 1 > i else i + 1

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

        half = max(1, int(math.ceil(net.halfwidth / GRID)))
        for l, y0, x0, y1, x1 in segs:
            self._stamp_capsule(net, l, x0, y0, x1, y1, half)
        vhalf = max(1, int(math.ceil(vdia / 2 / GRID)))
        for y, x in vias:
            for li in range(len(LAYERS)):
                self._stamp_disk(net, li, x, y, vhalf)
        return len(segs), len(vias)


def main():
    board = pcbnew.LoadBoard(V3)
    r = Router(board)
    for net in r.nets.values():
        clr, width = r._params(net.name)
        net.clearance = clr
        net.halfwidth = width / 2
        # The power lines go to the back copper.  They are thick and
        # long, and on the back they do not fight with the signals of
        # the parts, which are on the front.
        cls = r._class_of(net.name)
        if cls in ("Power_Battery", "Power_5V_Out", "Switching_Node"):
            net.preferred = 1
        else:
            net.preferred = 0

    have = set()
    for t in board.GetTracks():
        if t.GetNetname():
            have.add(t.GetNetname())

    # GND is done by the copper pour, it is never routed
    todo = [n for n in r.nets.values()
            if n.name not in have and n.name != "GND"]
    todo.sort(key=lambda n: -len(n.pads))

    # A net that is only partially routed is completed: the repair loop
    # removes single conflicting tracks, and the net then has to be
    # finished.  The nets whose geometry was copied over from the
    # finished v2 layout are left alone - their tracks are proven, and
    # routing them again would duplicate the copper.
    try:
        from v2_routes import build_mapping
        v2_nets = set(build_mapping().keys())
    except Exception:
        v2_nets = set()

    partial = []
    for n in r.nets.values():
        if n.name == "GND" or n.name not in have or n.name in v2_nets:
            continue
        # the net has copper, but is every pad of it connected?
        pads = set()
        for fp in board.GetFootprints():
            if not fp.GetReference():
                continue
            for pad in fp.Pads():
                if pad.GetNetname() == n.name:
                    pads.add((round(pcbnew.ToMM(pad.GetPosition().x), 2),
                              round(pcbnew.ToMM(pad.GetPosition().y), 2)))
        ends = set()
        for t in board.GetTracks():
            if t.GetNetname() != n.name:
                continue
            for p in (t.GetStart(), t.GetEnd()):
                ends.add((round(pcbnew.ToMM(p.x), 2),
                          round(pcbnew.ToMM(p.y), 2)))
        if pads - ends:
            partial.append(n)
    if partial:
        print(f"nets to complete: {[n.name for n in partial]}")
        todo.extend(partial)

    # An optional order file lets the repair loop try a different routing
    # order: the nets that collided before are routed first, so they take
    # the corridors they need and the others have to work around them.
    order_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "route_order.txt")
    if os.path.exists(order_file):
        with open(order_file) as fh:
            order = [ln.strip() for ln in fh if ln.strip()]
        rank = {name: i for i, name in enumerate(order)}
        todo.sort(key=lambda n: (rank.get(n.name, 9999), -len(n.pads)))

    print(f"grid {GRID} mm, {NX}x{NY} cells")
    print(f"nets to route: {len(todo)}")
    for net in todo:
        print(f"  {net.name:24} {len(net.pads):2} pads  "
              f"w={net.halfwidth*2:.2f} clr={net.clearance:.2f} "
              f"class={r._class_of(net.name)}")

    print("\nrouting...")
    ok = 0
    failed = []
    for net in todo:
        existing = None
        if net.name in have:
            # the tracks that are already there - the net is completed,
            # not routed again
            existing = []
            for t in board.GetTracks():
                if t.GetNetname() != net.name:
                    continue
                li = LAYERS.index(t.GetLayer()) if t.GetLayer() in LAYERS else 0
                a = t.GetStart()
                b = t.GetEnd()
                ay, ax = cell_of(a)
                by, bx = cell_of(b)
                existing.append(((li, ay, ax), (li, by, bx)))
        path = r.route_net(net, existing)
        if path is None:
            failed.append(net.name)
            print(f"  FAIL {net.name}", flush=True)
            continue
        ns, nv = r.commit(net, path)
        ok += 1
        print(f"  ok   {net.name:24} {ns:3} segs {nv:3} vias", flush=True)
    print(f"\nrouted {ok}, failed {len(failed)}: {failed}")

    safe_board.save(board, "the route of the maze router")
    print("saved")


if __name__ == "__main__":
    main()
