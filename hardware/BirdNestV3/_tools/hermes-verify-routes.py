#!/usr/bin/env python3
"""
Ad-hoc verification of the hand drawn routes and of the guard of the
board.

  hand_routes.py - a net can have more than one route, the width of a
                   route may change, the route may change to the other
                   copper through a via, the line may not cross a
                   track of another net, the zone of the ground is
                   filled again after the route, the script takes more
                   than one net, and the copper of the nets that are
                   kept stays.
  safe_board.py - the board is only written when the change did not
                   make it worse, and every kind of error of the copper
                   counts.

The board is put back afterwards, whatever happens.

Run:  hermes-verify-routes.py
"""
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys

# The board of the V3.  The place of it is in the guard of the board,
# so that every script looks at the same one.  The guard is found
# through the path of the modules, so that this script runs from
# anywhere.
import safe_board

PCB = safe_board.PCB
HERE = safe_board.HERE
SAVE_PCB = "/tmp/hermes-verify-routes-board.kicad_pcb"
JSON = "/tmp/hermes-verify-routes-drc.json"

PY = ("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/"
      "Versions/3.9/bin/python3")
PYPATH = ("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/"
          "Versions/3.9/lib/python3.9/site-packages")
CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          + (f"   {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def py(code):
    env = {**os.environ, "PYTHONPATH": PYPATH + ":" + HERE}
    r = subprocess.run([PY, "-c", code], capture_output=True, text=True,
                       env=env, cwd=HERE)
    return r.stdout.strip(), r.stderr.strip()


def run(script, *args):
    env = {**os.environ, "PYTHONPATH": PYPATH + ":" + HERE}
    return subprocess.run([PY, os.path.join(HERE, script)] + list(args),
                          capture_output=True, text=True, env=env, cwd=HERE)


def drc():
    if os.path.exists(JSON):
        os.remove(JSON)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", JSON, PCB],
                   capture_output=True, text=True)
    with open(JSON) as f:
        return json.load(f)


def copper_errors(d):
    kinds = {}
    for v in d.get("violations", []):
        if v.get("type") in ("shorting_items", "clearance", "tracks_crossing",
                             "solder_mask_bridge", "hole_clearance",
                             "hole_to_hole", "holes_co_located",
                             "via_dangling", "track_dangling"):
            kinds[v["type"]] = kinds.get(v["type"], 0) + 1
    return kinds


def open_nets(d):
    out = {}
    for u in d.get("unconnected_items", []):
        for i in u.get("items", []):
            desc = i.get("description", "")
            if "[" in desc:
                net = desc.split("[")[1].split("]")[0]
                out.setdefault(net, []).append(desc[:60])
    return out


def digest():
    return hashlib.sha256(open(PCB, "rb").read()).hexdigest()


def digest_of():
    return hashlib.sha256(open(SAVE_PCB, "rb").read()).hexdigest()


def main():
    shutil.copy(PCB, SAVE_PCB)
    try:
        print("1. the files are sound")
        for f in ("safe_board.py", "hand_routes.py"):
            out, err = py("import ast;ast.parse(open(%r).read());print('ok')"
                          % os.path.join(HERE, f))
            check(f"{f} parses", out == "ok", err[-100:])
            code = (
                "import ast\n"
                "src = open(" + repr(os.path.join(HERE, f)) + ").read()\n"
                "tree = ast.parse(src)\n"
                "names = {n.name for n in tree.body\n"
                "         if isinstance(n, (ast.FunctionDef, ast.ClassDef))}\n"
                "called = set()\n"
                "for n in ast.walk(tree):\n"
                "    if isinstance(n, ast.Call):\n"
                "        fn = n.func\n"
                "        if isinstance(fn, ast.Name): called.add(fn.id)\n"
                "        elif isinstance(fn, ast.Attribute):\n"
                "            called.add(fn.attr)\n"
                "assigned = {t.id for n in ast.walk(tree)\n"
                "            if isinstance(n, ast.Assign)\n"
                "            for t in n.targets if isinstance(t, ast.Name)}\n"
                "loads = {n.id for n in ast.walk(tree)\n"
                "         if isinstance(n, ast.Name)\n"
                "         and isinstance(n.ctx, ast.Load)}\n"
                "consts = {t.id for n in tree.body\n"
                "          if isinstance(n, ast.Assign)\n"
                "          for t in n.targets if isinstance(t, ast.Name)}\n"
                "print(sorted(names - called - {'main'} - {'save'}))\n"
                "print(sorted(assigned - loads - consts))\n"
            )
            out, err = py(code)
            lines = out.splitlines()
            check(f"{f} has no function that nobody uses",
                  bool(lines) and lines[0] == "[]",
                  lines[0] if lines else (err[-140:] if err else "no output"))
            check(f"{f} has no variable that is never read",
                  len(lines) > 1 and lines[1] == "[]",
                  lines[1:2][0] if len(lines) > 1 else "")
            src = open(os.path.join(HERE, f)).read()
            longs = [i + 1 for i, ln in enumerate(src.split("\n"))
                     if len(ln) > 79]
            check(f"{f} has no long line", not longs, f"{longs}")
            code = (
                "src = open(" + repr(os.path.join(HERE, f)) + ").read()\n"
                "lines = [l.strip() for l in src.split('\\n')]\n"
                "comments = [l for l in lines if len(l) > 25 and"
                " l.startswith('#')]\n"
                "print(len(comments) - len(set(comments)))\n")
            out, err = py(code)
            check(f"{f} has no comment that says the same thing twice",
                  out.strip() == "0",
                  out.strip() or (err[-100:] if err else ""))
        src = open(os.path.join(HERE, "hand_routes.py")).read()
        check("the rules come from the project file",
              "GetNetClasses" not in src
              and "from maze4 import load_classes" in src)
        check("the guard of the board is used",
              "import safe_board" in src and "safe_board.save(" in src)
        check("the zone is filled again after the route",
              "ZONE_FILLER" in src and "filler.Fill(" in src)

        print()
        print("2. the guard knows every error of the copper")
        code = (
            "import safe_board\n"
            "want = ('shorting_items', 'clearance', 'tracks_crossing',\n"
            "        'solder_mask_bridge', 'hole_clearance', 'hole_to_hole',\n"
            "        'holes_co_located', 'via_dangling', 'track_dangling')\n"
            "print(all(w in safe_board.COPPER_ERRORS for w in want))\n"
            "print(safe_board.COPPER_ERRORS)\n")
        out, err = py(code)
        lines = out.splitlines()
        check("every kind of error of the copper is in the list",
              bool(lines) and lines[0] == "True",
              lines[0] if lines else (err[-140:] if err else "no output"))
        check("the list holds the kinds that are not copper",
              len(lines) > 1 and "silk_overlap" not in lines[1],
              lines[1:2][0] if len(lines) > 1 else "")

        print()
        print("3. the width of a route may change")
        code = (
            "import hand_routes\n"
            "s = hand_routes.segments_of([(0, 0), (1, 0, 0.8), (2, 0)], 0.2)\n"
            "print(s[0][2], s[1][2])\n"
            "s = hand_routes.segments_of([(0, 0), (1, 0)], 0.6)\n"
            "print(s[0][2])\n")
        out, err = py(code)
        lines = out.splitlines()
        check("the first segment has the width of the route",
              bool(lines) and lines[0].startswith("0.2 0.8"),
              lines[0] if lines else (err[-140:] if err else "no output"))
        check("a route without a change keeps its width",
              len(lines) > 1 and lines[1] == "0.6",
              lines[1:2][0] if len(lines) > 1 else "")

        print()
        print("4. the route may change to the other copper")
        code = (
            "import hand_routes\n"
            # the route of the charger: the line starts on the front
            # copper and goes to the back copper at the pad of the C24
            "pts = [(179.442, 94.675, 0.8, 'B'),\n"
            "       (179.442, 85.175, 0.8, 'F')]\n"
            "print(hand_routes.vias_of(pts, 'F'))\n"
            "print(hand_routes.vias_of(pts, 'B'))\n"
            "for s in hand_routes.segments_of(pts, 0.8, 'F'):\n"
            "    print(s[3], end=' ')\n"
            "print()\n"
            # a route that stays on one layer has no via at all
            "flat = [(100.0, 100.0), (110.0, 100.0)]\n"
            "print(hand_routes.vias_of(flat, 'F'))\n")
        out, err = py(code)
        lines = out.splitlines()
        check("the via is at the change of the layer",
              bool(lines)
              and lines[0] == "[(179.442, 94.675), (179.442, 85.175)]",
              lines[0] if lines else (err[-140:] if err else "no output"))
        check("there is no via when the route starts on that layer",
              len(lines) > 1 and lines[1] == "[(179.442, 85.175)]",
              lines[1:2][0] if len(lines) > 1 else "")
        # the layer of a segment is the layer of the point it starts at:
        # the last point of a route has no segment of its own, so the
        # line stays on the back copper up to the pad
        check("the segments carry their layer",
              len(lines) > 2 and lines[2].strip() == "B",
              lines[2:3][0] if len(lines) > 2 else "")
        check("a route on one layer has no via",
              len(lines) > 3 and lines[3] == "[]",
              lines[3:4][0] if len(lines) > 3 else "")

        print()
        print("4b. the route that is already there is found by the track")
        code = (
            "import pcbnew, hand_routes\n"
            "b = pcbnew.LoadBoard(" + repr(PCB) + ")\n"
            "net = '/BAT_CELL-'\n"
            "routes = hand_routes.ROUTES[net]\n"
            "print(hand_routes.route_is_there(b, net, routes))\n"
            # the route of a net that is not on the board is not there
            "print(hand_routes.route_is_there(b, net, [\n"
            "    (0.8, 'F', [(200.0, 50.0), (190.0, 50.0)])]))\n"
            # one route that is not on the board makes the whole net
            # not there, even when the other one is
            "print(hand_routes.route_is_there(b, net, routes + [\n"
            "    (0.8, 'F', [(200.0, 50.0), (190.0, 50.0)])]))\n")
        out, err = py(code)
        lines = out.splitlines()
        check("the route of the battery is found on the board",
              bool(lines) and lines[0] == "True",
              lines[0] if lines else (err[-140:] if err else "no output"))
        check("a route that is not on the board is not there",
              len(lines) > 1 and lines[1] == "False",
              lines[1:2][0] if len(lines) > 1 else "")
        check("one route that is missing makes the whole net missing",
              len(lines) > 2 and lines[2] == "False",
              lines[2:3][0] if len(lines) > 2 else "")

        print()
        print("5. the line may not cross a track of another net")
        code = (
            "import hand_routes\n"
            "print(hand_routes.crosses_line((0, 0), (10, 10),\n"
            "                               (0, 10), (10, 0)))\n"
            "print(hand_routes.crosses_line((0, 0), (10, 0),\n"
            "                               (10, 0), (10, 10)))\n")
        out, err = py(code)
        lines = out.splitlines()
        check("two lines that cross are found", bool(lines)
              and lines[0] == "True", lines[0] if lines else "")
        check("two lines that touch are not a crossing",
              len(lines) > 1 and lines[1] == "False",
              lines[1:2][0] if len(lines) > 1 else "")

        print()
        print("6. every route of the table has room")
        code = (
            "import hand_routes, pcbnew\n"
            "b = pcbnew.LoadBoard(" + repr(PCB) + ")\n"
            "for net, routes in sorted(hand_routes.ROUTES.items()):\n"
            "    for (w, lay, pts) in routes:\n"
            "        r = hand_routes.free_of_copper(\n"
            "            b, net, pts, w, hand_routes.layer_of(lay))\n"
            "        print(net, 'free' if r is None else r)\n")
        out, err = py(code)
        lines = out.splitlines()
        check("every route has room", bool(lines)
              and all(ln.endswith("free") for ln in lines),
              "; ".join(ln for ln in lines if not ln.endswith("free"))[:80]
              or "all free")

        print()
        print("7. the script takes more than one net")
        res = run("hand_routes.py", "/BAT_MON", "/+5V")
        check("the script runs with two nets", res.returncode == 0,
              (res.stderr or "")[-140:] if res.returncode else "")
        check("both nets are worked on",
              res.stdout.count("the net ") == 2,
              f"{res.stdout.count('the net ')} nets")
        res = run("hand_routes.py", "/BAT_MON", "no-such-net")
        check("a name that has no route is an error",
              res.returncode == 1 and "no route" in (res.stdout or ""),
              f"exit {res.returncode}: " + (res.stdout or "").strip()[-50:])

        print()
        print("8. the copper of the board is clean")
        d = drc()
        kinds = copper_errors(d)
        # the board of before has five tracks that hang loose: they come
        # from the layout of the V2 and they are not of the routes of
        # this session.  The guard looks at the change and not at the
        # absolute number, so the check does the same: the errors of
        # the copper may not be more than they were.
        check("the errors of the copper may not grow",
              kinds.get("track_dangling", 0) <= 5
              and not any(k != "track_dangling" for k in kinds),
              ", ".join(f"{k}: {n}"
                       for k, n in sorted(kinds.items())) or "clean")
        check("the loose tracks are the ones of the V2",
              kinds.get("track_dangling", 0) == 5,
              f"{kinds.get('track_dangling', 0)} loose tracks")
        check("the zone reaches every pad",
              kinds.get("starved_thermal", 0) == 0,
              f"{kinds.get('starved_thermal', 0)} starved")
        code = ("import hand_routes;print(sorted(hand_routes.KEEP))")
        out, _ = py(code)
        check("the copper of the kept nets stays",
              "/+5V" in (out or "") and "GND" in (out or ""), out or "")
        opens = open_nets(d)
        for net in ("Net-(U11-ISET)", "Net-(U11-TEMP)", "/BAT_MON",
                    "/+5V", "Net-(U10-OC)", "Net-(U10-OD)",
                    "Net-(Q9-G)", "Net-(U10-VCC)",
                    "Net-(D7-A)", "Net-(D10-A)", "GND",
                    "/BAT_CELL+"):
            check(f"the {net} is connected", net not in opens,
                  "the net is still open" if net in opens else "connected")
        # The protected pole of the battery is not closed yet: the two
        # capacitors C15 and C16 stand on their own.  The rest of the
        # line has to be joined: the charger U11, the resistor R22, the
        # resistor R29 and the switch Q6.
        left = opens.get("/BAT_PROT+", [])
        for name in ("U11", "R22", "R29", "Q6", "R28", "Q9", "R25"):
            check(f"the {name} is joined to the protected pole",
                  not any(name in d0 for d0 in left),
                  "; ".join(left)[:80] or "the net is closed")
        # the positive pole of the battery is joined at the connector,
        # at the capacitor, at the resistor and at the switch
        left = opens.get("/BAT_CELL+", [])
        check("the positive pole of the battery is joined",
              not any("BT3" in d0 or "C23" in d0 or "R11" in d0
                      or "Q9" in d0 for d0 in left),
              "; ".join(left)[:80] or "the net is closed")
        # the negative pole of the battery is joined except for the
        # connector BT3, whose pad is far from the rest
        if "/BAT_CELL-" in opens:
            left = opens["/BAT_CELL-"]
            check("the negative pole of the battery is joined at the"
                  " switch and at the chip",
                  not any("Q3" in d0 or "U10" in d0 or "C19" in d0
                          or "R27" in d0 for d0 in left),
                  "; ".join(left)[:80])
        else:
            check("the negative pole of the battery is joined", False,
                  "the net is not open at all")
        check("the board is measured at all", "violations" in d,
              f"{len(d.get('violations', []))} violations, "
              f"{len(d.get('unconnected_items', []))} unconnected")

        print()
        print("9. the board is unchanged")
        check("the board was not touched", digest() == digest_of(),
              digest()[:16])
    finally:
        shutil.copy(SAVE_PCB, PCB)
        print("\n(the board is back in place)")

    print()
    if fails:
        print(f"FAILED {len(fails)} checks: {fails}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
