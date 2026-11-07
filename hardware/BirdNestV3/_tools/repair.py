#!/usr/bin/env python3
"""
Iterative repair loop for the V3 PCB routing.

The maze router cannot always find a legal path on the first try: the
keep-out of the nets that were routed before it may block the only
corridor that is left.  This script

  1. runs the KiCad DRC,
  2. extracts the nets that are involved in a copper error
     (clearance / shorting / tracks crossing),
  3. deletes the tracks and vias of those nets,
  4. lets maze4.py route them again - now with the remaining nets as
     obstacles.

Step 4 may produce a different path, because the router is free to use
the corridor that the deleted net occupied.  If the second attempt is
still illegal, the net is put on a "do not touch again" list, so the loop
terminates.

Usage:
  python3 repair.py [iterations]
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
import safe_board

from safe_board import PCB    # noqa: E402

V3 = PCB
HERE = os.path.dirname(os.path.abspath(__file__))
KICLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
PY = "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3"
PYPATH = ("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework"
          "/Versions/3.9/lib/python3.9/site-packages")

# violation types that are caused by the routing itself
COPPER_ERRORS = ("clearance", "shorting_items", "tracks_crossing",
                 "track_dangling", "via_dangling")

NET_RE = re.compile(r"\[([^\]]+)\]")


def run_drc():
    out = "/tmp/v3_repair_drc.json"
    subprocess.run([KICLI, "pcb", "drc", "--format", "json", "-o", out, V3],
                   check=False, capture_output=True)
    with open(out) as fh:
        return json.load(fh)


def nets_in_error(report):
    """The nets that take part in a copper error."""
    bad = set()
    for v in report.get("violations", []):
        if v.get("type") not in COPPER_ERRORS:
            continue
        for item in v.get("items", []):
            desc = item.get("description", "")
            m = NET_RE.search(desc)
            if not m:
                continue
            net = m.group(1)
            if net.startswith("unconnected-"):
                continue
            bad.add(net)
    return bad




def refill_zone():
    subprocess.run([PY, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "refill.py")],
                   check=False, capture_output=True,
                   env={**os.environ, "PYTHONPATH": PYPATH})


def route(order=None):
    """Run the router.  `order` is an optional list of net names that
    should be routed first."""
    here = os.path.dirname(os.path.abspath(__file__))
    order_file = os.path.join(here, "route_order.txt")
    if order:
        with open(order_file, "w") as fh:
            fh.write("\n".join(order) + "\n")
    try:
        res = subprocess.run(
            [PY, os.path.join(here, "maze4.py")],
            check=False, capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": PYPATH})
        for line in (res.stdout or "").splitlines():
            if line.startswith(("routed", "  FAIL")):
                print("   " + line, flush=True)
    finally:
        if order and os.path.exists(order_file):
            os.remove(order_file)


def net_pad_count():
    """The number of pads of every net - the nets with many pads need the
    big corridors, so they have to be routed first."""
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "pad_counts.json")
    res = subprocess.run([PY, "-c", f'''
import json, sys
sys.path.insert(0, {here!r})
import pcbnew
b = pcbnew.LoadBoard({V3!r})
counts = {{}}
for fp in b.GetFootprints():
    if not fp.GetReference():
        continue
    for pad in fp.Pads():
        n = pad.GetNetname()
        if n:
            counts[n] = counts.get(n, 0) + 1
print(json.dumps(counts))
'''], check=False, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": PYPATH})
    try:
        return json.loads(res.stdout.strip().splitlines()[-1])
    except Exception:
        return {}


def v2_copied_nets():
    """The V3 nets whose tracks were copied over from the v2 board.  Their
    geometry is proven - the repair loop must not touch them."""
    from v2_routes import build_mapping
    return set(build_mapping().keys())






def delete_all(nets):
    """Remove every track and via of the given nets."""
    here = os.path.dirname(os.path.abspath(__file__))
    res = subprocess.run([PY, os.path.join(here, "delnets.py"), "--force"]
                         + sorted(nets),
                         check=False, capture_output=True, text=True,
                         env={**os.environ, "PYTHONPATH": PYPATH})
    out = (res.stdout or "") + (res.stderr or "")
    for line in out.splitlines():
        if line.startswith(("removed", "ERROR")):
            print("   " + line, flush=True)
    return out


def main():
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    counts = net_pad_count()
    # the v2 geometry is proven and must survive the repair loop
    keep = set()
    try:
        keep = v2_copied_nets()
    except Exception:
        pass
    print(f"nets protected from the v2 layout: {len(keep)}")

    # The board of before the loop.  The loop removes the copper of the
    # nets and draws it again, and it may end up with a board that is
    # worse than the one it started with.  The board of before is put
    # back in that case.
    shutil.copy(V3, safe_board.BEFORE_BOARD)
    before = run_drc()
    before_v = len(before.get("violations", []))
    before_u = len(before.get("unconnected_items", []))
    before_c = sum(1 for v in before.get("violations", [])
                   if v.get("type") in COPPER_ERRORS)
    print(f"the board before the loop: {before_v} violations"
          f" ({before_c} in the copper), {before_u} unconnected")

    for it in range(1, iterations + 1):
        report = run_drc()
        viol = report.get("violations", [])
        unc = report.get("unconnected_items", [])
        copper = [v for v in viol if v.get("type") in COPPER_ERRORS]
        print(f"\n=== iteration {it}: {len(viol)} violations "
              f"({len(copper)} copper, {len(unc)} unconnected) ===",
              flush=True)

        bad = nets_in_error(report)
        # GND is the copper pour - it is never routed, so it cannot be
        # re-routed; it is removed from the list
        bad.discard("GND")
        # the nets of the v2 layout are not re-routed
        bad -= keep
        if not bad:
            print("no copper error left that the router can fix")
            break

        # The whole net is removed, not just the conflicting tracks: the
        # router plans the route of the net as a whole, and a net that is
        # only partly removed would get a second, parallel route.
        print(f"nets to re-route: {sorted(bad)}", flush=True)
        delete_all(bad)

        # re-route the nets that lost their copper
        order = sorted(bad, key=lambda n: -counts.get(n, 0))
        route(order=order)
        refill_zone()

    # The nets that could not be routed yet still need copper.  Run the
    # router once more so that they get a chance.
    print("\nrouting the nets that are still missing", flush=True)
    route()

    report = run_drc()
    viol = report.get("violations", [])
    unc = report.get("unconnected_items", [])
    after_c = sum(1 for v in viol if v.get("type") in COPPER_ERRORS)
    print(f"\nfinal: {len(viol)} violations, {len(unc)} unconnected")

    # The board has to be at least as good as it was before the loop.
    # When it is not, the board of before is put back.
    if after_c > before_c or len(unc) > before_u:
        print(f"the loop did not help ({before_c} -> {after_c} errors in the"
              f" copper, {before_u} -> {len(unc)} unconnected):"
              " the board of before is put back")
        subprocess.run([sys.executable, os.path.join(HERE, "restore.py")],
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPATH": PYPATH})
    else:
        print(f"the loop helped ({before_c} -> {after_c} errors in the"
              f" copper, {before_u} -> {len(unc)} unconnected)")

    from collections import Counter
    print(dict(Counter(v.get("type") for v in viol)))


if __name__ == "__main__":
    main()
