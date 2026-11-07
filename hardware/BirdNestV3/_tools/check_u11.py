#!/usr/bin/env python3
"""
Check the tracks around the U11.

The U11 is a DFN-9 with a 0.5 millimetre pin pitch.  Between two pins
there is room for 0.15 millimetres of copper, and a 0.2 millimetre
track does not fit there.  A track that leaves the package therefore has
to leave it on the outer side of the pins: the pins of the left column
on the left, the pins of the right column on the right.

For every pin of the U11 this reports

  - whether a track or a via lands on it,
  - the smallest distance between the pin and the copper of the board
    that belongs to another net.

The pins of the GND net are connected by the pour, so they are only
reported when a foreign track runs too close to them.

Run:  check_u11.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew

V3 = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_pcb"
U11 = "U11"
DEFAULT_CLEARANCE = 0.2      # mm, the default class of the board


def point_seg_dist(p, a, b):
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    len2 = dx * dx + dy * dy
    if len2 == 0:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / len2))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def point_rect_dist(p, r):
    px, py = p
    x0, y0, x1, y1 = r
    dx = max(x0 - px, 0.0, px - x1)
    dy = max(y0 - py, 0.0, py - y1)
    return (dx * dx + dy * dy) ** 0.5


def seg_seg_hit(a, b, c, d):
    """Do the two segments cross?"""
    def cross(o, p, q):
        return ((p[0] - o[0]) * (q[1] - o[1]) -
                (p[1] - o[1]) * (q[0] - o[0]))
    d1 = cross(c, d, a)
    d2 = cross(c, d, b)
    d3 = cross(a, b, c)
    d4 = cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return True
    return False


def seg_rect_dist(a, b, r):
    """The distance between a segment and a rectangle, 0 when they touch."""
    x0, y0, x1, y1 = r
    corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for p in (a, b):
        if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
            return 0.0
    for i in range(4):
        if seg_seg_hit(a, b, corners[i], corners[(i + 1) % 4]):
            return 0.0
    d = min(point_seg_dist(c, a, b) for c in corners)
    d = min(d, point_rect_dist(a, r), point_rect_dist(b, r))
    return d


def main():
    b = pcbnew.LoadBoard(V3)
    fp = b.FindFootprintByReference(U11)
    if fp is None:
        print(f"{U11} not found")
        return 1

    classes = {str(k): v for k, v in b.GetNetClasses().items()}

    def net_clearance(netname):
        cls = classes.get(netname, classes.get("Default"))
        if cls is None:
            return DEFAULT_CLEARANCE
        return pcbnew.ToMM(cls.GetClearance())

    # the pins of the package
    pins = []
    for p in fp.Pads():
        pos = p.GetPosition()
        w = pcbnew.ToMM(p.GetSize().x)
        h = pcbnew.ToMM(p.GetSize().y)
        x = pcbnew.ToMM(pos.x)
        y = pcbnew.ToMM(pos.y)
        local = p.GetLocalClearance()
        pins.append({
            "num": p.GetNumber(),
            "net": p.GetNetname(),
            "rect": (x - w / 2, y - h / 2, x + w / 2, y + h / 2),
            "clearance": (pcbnew.ToMM(local) if local else None),
        })

    # the copper of the board
    tracks = []
    for t in list(b.GetTracks()):
        a = t.GetStart()
        e = t.GetEnd()
        if t.GetClass() == "PCB_VIA":
            radius = pcbnew.ToMM(t.GetWidth()) / 2
            tracks.append({
                "net": t.GetNetname(),
                "a": (pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)),
                "b": (pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)),
                "radius": radius,
                "via": True,
            })
            continue
        if not t.IsOnLayer(pcbnew.F_Cu):
            continue
        tracks.append({
            "net": t.GetNetname(),
            "a": (pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)),
            "b": (pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)),
            "radius": pcbnew.ToMM(t.GetWidth()) / 2,
            "via": False,
        })

    def lands_on(track, rect):
        """Does the track end on the pin?"""
        x0, y0, x1, y1 = rect
        for p in (track["a"], track["b"]):
            if x0 <= p[0] <= x1 and y0 <= p[1] <= y1:
                return True
        return False

    print(f"{U11}: {len(pins)} pins")
    open_pins = []
    too_close = []
    for pin in pins:
        rect = pin["rect"]
        connected = False
        nearest = None
        for t in tracks:
            d = seg_rect_dist(t["a"], t["b"], rect) - t["radius"]
            if t["net"] == pin["net"]:
                if lands_on(t, rect):
                    connected = True
                continue
            if nearest is None or d < nearest[0]:
                nearest = (d, t["net"])
        # the pour connects the GND pins
        if pin["net"] == "GND":
            connected = True
        need = pin["clearance"]
        if need is None:
            need = net_clearance(pin["net"])
        state = "connected" if connected else "OPEN"
        if not connected:
            open_pins.append(pin["num"])
        mark = ""
        if nearest and nearest[0] < need:
            mark = f"  TOO CLOSE to {nearest[1]} ({nearest[0]:.3f} mm < {need:.3f})"
            too_close.append((pin["num"], nearest))
        print(f"  {pin['num']:>2} {pin['net']:<18} {state:<10}"
              f" nearest foreign copper {nearest[0]:.3f} mm{mark}"
              if nearest else
              f"  {pin['num']:>2} {pin['net']:<18} {state}")

    print()
    if open_pins:
        print(f"pins without a track: {', '.join(open_pins)}")
    if too_close:
        print(f"{len(too_close)} pins are too close to a foreign track:")
        for num, (d, net) in too_close:
            print(f"  pin {num}: {d:.3f} mm to the {net} net")
    else:
        print("no track runs too close to a pin of another net")
    return 0


if __name__ == "__main__":
    sys.exit(main())
