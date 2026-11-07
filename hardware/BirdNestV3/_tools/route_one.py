#!/usr/bin/env python3
"""
The routes that are made one net at a time, and only the ones that the
design rules checker accepts.

The router draws a route for every net at once, and the routes fight
each other: a route that is drawn later runs over the copper of the
route that was drawn before.  The whole board then has more errors than
it had before.

So the nets are routed one at a time.  For every net:

  1.  the copper of the net is removed,
  2.  the router draws a route for the net alone,
  3.  the zones are filled again,
  4.  the design rules checker measures the board.

If the board gets worse, the route is thrown away and the board goes
back to what it was.  If the board gets better, the route stays.

The result is a board where every net that can be routed cleanly is
routed, and the nets that can not are left open.

Run:  route_one.py [net name]
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(os.path.dirname(HERE), "BirdNestV3.kicad_pcb")
BACKUP = "/tmp/route_one_backup.kicad_pcb"
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
JSON = "/tmp/route_one_drc.json"

sys.path.insert(0, HERE)
import pcbnew          # noqa: E402
import maze4           # noqa: E402

LAYER = {"F": pcbnew.F_Cu, "B": pcbnew.B_Cu}


def measure():
    """The number of the violations and of the unconnected items."""
    if os.path.exists(JSON):
        os.remove(JSON)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", JSON, PCB],
                   capture_output=True, text=True)
    with open(JSON) as f:
        d = json.load(f)
    viol = d.get("violations", [])
    unc = d.get("unconnected_items", [])
    # the errors that mean a broken board
    broken = 0
    for v in viol:
        if v.get("type") in ("shorting_items", "clearance", "tracks_crossing",
                             "solder_mask_bridge", "hole_clearance",
                             "hole_to_hole", "track_dangling"):
            broken += 1
    return len(viol), len(unc), broken, viol, unc


def open_nets():
    """The nets that have a pad that is not connected."""
    _, _, _, _, unc = measure()
    nets = {}
    for u in unc:
        for i in u.get("items", []):
            desc = i.get("description", "")
            if "[" not in desc:
                continue
            net = desc.split("[")[1].split("]")[0]
            nets.setdefault(net, set()).add(desc)
    return nets


def remove_copper(net):
    """The tracks and the vias of the net, in a process of its own."""
    env = {**os.environ,
           "PYTHONPATH": os.environ.get("PYTHONPATH", "") + ":" + HERE}
    while True:
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "delitem.py"), net, "next"],
            capture_output=True, text=True, env=env, cwd=HERE)
        if r.returncode != 1:
            return


def route_net(net_name):
    """The router draws a route for the net alone."""
    b = pcbnew.LoadBoard(PCB)
    r = maze4.Router(b)
    net = r.nets.get(net_name)
    if net is None:
        return 0, 0
    clr, width = r._params(net_name)
    net.clearance = clr
    net.halfwidth = width / 2
    cls = r._class_of(net_name)
    net.preferred = 1 if cls in ("Power_Battery", "Power_5V_Out",
                                 "Switching_Node") else 0

    # the tracks that are already there for the net
    existing = []
    for t in b.GetTracks():
        if t.GetNetname() != net_name:
            continue
        li = (maze4.LAYERS.index(t.GetLayer())
              if t.GetLayer() in maze4.LAYERS else 0)
        a, e = t.GetStart(), t.GetEnd()
        ay, ax = maze4.cell_of(a)
        by, bx = maze4.cell_of(e)
        existing.append(((li, ay, ax), (li, by, bx)))

    path = r.route_net(net, existing)
    if not path or len(path) < 2:
        return 0, 0
    ns, nv = r.commit(net, path)
    pcbnew.SaveBoard(PCB, b)
    return ns, nv


def refill():
    env = {**os.environ,
           "PYTHONPATH": os.environ.get("PYTHONPATH", "") + ":" + HERE}
    subprocess.run([sys.executable, os.path.join(HERE, "refill.py")],
                   capture_output=True, text=True, env=env, cwd=HERE)


def main():
    before_v, before_u, before_b, _, _ = measure()
    print(f"the board now: {before_v} violations, {before_u} unconnected,"
          f" {before_b} of them broken")

    nets = open_nets()
    if len(sys.argv) > 1:
        nets = {k: v for k, v in nets.items() if k == sys.argv[1]}
    # the nets with few pads first: they are the ones that can be
    # routed cleanly, and they give the router room for the others
    order = sorted(nets, key=lambda n: (len(nets[n]), n))

    kept = []
    for net in order:
        shutil.copy(PCB, BACKUP)
        v0, u0, b0, _, _ = measure()
        remove_copper(net)
        ns, nv = route_net(net)
        if not ns:
            shutil.copy(BACKUP, PCB)
            print(f"  {net:22} the router drew nothing")
            continue
        refill()
        v1, u1, b1, _, _ = measure()
        # the route has to bring the board forward: fewer unconnected
        # items and no more errors
        if u1 <= u0 and b1 <= b0:
            kept.append(net)
            print(f"  {net:22} {ns} segments {nv} vias:"
                  f" {b0} -> {b1} errors, {u0} -> {u1} unconnected   KEPT")
        else:
            shutil.copy(BACKUP, PCB)
            print(f"  {net:22} {ns} segments {nv} vias:"
                  f" {b0} -> {b1} errors, {u0} -> {u1} unconnected   dropped")

    v, u, b, _, _ = measure()
    print()
    print(f"the board now: {v} violations, {u} unconnected, {b} broken")
    print(f"the routes that were kept: {kept}")


if __name__ == "__main__":
    main()
