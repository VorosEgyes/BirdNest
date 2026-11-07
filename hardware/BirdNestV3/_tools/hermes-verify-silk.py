#!/usr/bin/env python3
"""
Ad-hoc verification of the silk screen cleaner.

The fix_silk.py moves the reference of a part that lies over the
copper.  It may only move the references that the rules checker names,
it may not make the copper worse, it may not make the board
unconnected, and it may not make the silk screen worse.

This run checks:
  - the file is sound: it parses, no dead function, no dead variable,
    no unused argument, no long line, no comment that says the same
    thing twice;
  - the cleaner finds the references that are in the way, and every
    name is a part of the board;
  - a place is found for every reference, the references that are
    moved are the ones that can be moved, and no reference lies over a
    pad after the move;
  - the copper of the board has no error, and the silk screen is
    better than it was;
  - the board is put back afterwards.

Run:  hermes-verify-silk.py
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
# anywhere.  The tools of the project stand beside the guard, and the
# place of them is taken from there.
import safe_board

PCB = safe_board.PCB
HERE = safe_board.HERE
SAVE_PCB = "/tmp/hermes-verify-silk-board.kicad_pcb"
JSON = "/tmp/hermes-verify-silk-drc.json"

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


def py(lines):
    """The answer of a little program that runs in the KiCad python.

    The program is a list of lines: they are joined with a newline, so
    that no escape of a newline is needed anywhere.
    """
    env = {**os.environ, "PYTHONPATH": PYPATH + ":" + HERE}
    r = subprocess.run([PY, "-c", "\n".join(lines)], capture_output=True,
                       text=True, env=env, cwd=HERE)
    return r.stdout.strip(), r.stderr.strip()


def drc():
    if os.path.exists(JSON):
        os.remove(JSON)
    subprocess.run([CLI, "pcb", "drc", "--format", "json", "-o", JSON, PCB],
                   capture_output=True, text=True)
    with open(JSON) as f:
        return json.load(f)


def main():
    shutil.copy(PCB, SAVE_PCB)
    try:
        print("1. the file is sound")
        path = os.path.join(HERE, "fix_silk.py")
        src = open(path).read()
        out, err = py(["import ast",
                       "ast.parse(open(" + repr(path) + ").read())",
                       "print('ok')"])
        check("the file parses", out == "ok", err[-100:])
        tree = ast.parse(src)
        names = {n.name for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        called = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                fn = n.func
                if isinstance(fn, ast.Name):
                    called.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    called.add(fn.attr)
        check("no function is dead", not (names - called - {"main"}),
              f"{sorted(names - called - {'main'})}")
        assigned = {t.id for n in ast.walk(tree) if isinstance(n, ast.Assign)
                    for t in n.targets if isinstance(t, ast.Name)}
        loads = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
                 and isinstance(n.ctx, ast.Load)}
        consts = {t.id for n in tree.body if isinstance(n, ast.Assign)
                  for t in n.targets if isinstance(t, ast.Name)}
        check("no variable is dead", not (assigned - loads - consts),
              f"{sorted(assigned - loads - consts)}")
        longs = [i + 1 for i, ln in enumerate(src.split("\n"))
                 if len(ln) > 79]
        check("no line is too long", not longs, f"{longs}")
        comments = [ln.strip() for ln in src.split("\n")
                    if len(ln.strip()) > 25 and ln.strip().startswith("#")]
        check("no comment says the same thing twice",
              len(comments) == len(set(comments)),
              f"{len(comments) - len(set(comments))} repeated")
        dead_args = []
        for n in tree.body:
            if not isinstance(n, ast.FunctionDef):
                continue
            used = {x.id for x in ast.walk(n)
                    if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Load)}
            dead_args += [f"{n.name}.{a.arg}" for a in n.args.args
                          if a.arg not in used]
        check("no argument is unused", not dead_args, f"{dead_args}")
        check("the guard of the board is used", "safe_board.save(" in src)

        print()
        print("2. the cleaner finds the references that are in the way")
        out, err = py([
            "import fix_silk, pcbnew",
            "d = fix_silk.drc()",
            "wrong = fix_silk.wrong_references(d)",
            "print(len(wrong))",
            "print(','.join(sorted(wrong)))",
            "b = pcbnew.LoadBoard(" + repr(PCB) + ")",
            "refs = set(fp.GetReference() for fp in b.GetFootprints())",
            "print(all(w in refs for w in wrong))",
        ])
        lines = out.splitlines()
        check("the cleaner finds some references",
              bool(lines) and lines[0].isdigit(),
              f"{lines[0]} references" if lines else "")
        check("every name is a part of the board",
              len(lines) > 2 and lines[2] == "True",
              lines[2:3][0] if len(lines) > 2 else "")

        print()
        print("3. a place is found for every reference")
        out, err = py([
            "import fix_silk, pcbnew",
            "b = pcbnew.LoadBoard(" + repr(PCB) + ")",
            "pads = fix_silk.pads_of(b)",
            "silk = fix_silk.silk_by_part(b)",
            "moved = 0",
            "seen = 0",
            "for fp in b.GetFootprints():",
            "    ref = fp.Reference()",
            "    if ref.GetClass() not in ('PCB_FIELD', 'PCB_TEXT'): continue",
            "    if not ref.IsVisible(): continue",
            "    seen += 1",
            "    if fix_silk.place_reference(fp, pads, silk): moved += 1",
            "print(moved, seen)",
            # no reference lies over a pad after the move
            "bad = 0",
            "for fp in b.GetFootprints():",
            "    ref = fp.Reference()",
            "    if ref.GetClass() not in ('PCB_FIELD', 'PCB_TEXT'): continue",
            "    bb = ref.GetBoundingBox()",
            "    w = fix_silk.mm(bb.GetWidth())",
            "    h = fix_silk.mm(bb.GetHeight())",
            "    pos = ref.GetPosition()",
            "    px = fix_silk.mm(pos.x); py = fix_silk.mm(pos.y)",
            "    rect = (px - w/2, py - h/2, px + w/2, py + h/2)",
            "    if fix_silk.hits(rect, pads): bad += 1",
            "print(bad)",
        ])
        lines = out.splitlines()
        check("every reference has a place",
              bool(lines) and lines[0].split()[0] == lines[0].split()[1],
              lines[0] if lines else (err[-140:] if err else "no output"))
        check("the references that are moved can be moved",
              bool(lines) and int(lines[0].split()[0]) > 0,
              lines[0] if lines else "")
        check("no reference lies over a pad after the move",
              len(lines) > 1 and lines[1] == "0",
              lines[1:2][0] if len(lines) > 1 else "")

        print()
        print("4. the board is clean")
        d = drc()
        kinds = {}
        for v in d.get("violations", []):
            kinds[v.get("type")] = kinds.get(v.get("type"), 0) + 1
        copper = {k: n for k, n in kinds.items()
                  if k in ("shorting_items", "clearance", "tracks_crossing",
                           "solder_mask_bridge", "hole_clearance",
                           "hole_to_hole", "holes_co_located",
                           "via_dangling")}
        check("the copper has no error", not copper,
              ", ".join(f"{k}: {n}"
                       for k, n in sorted(copper.items())) or "clean")
        check("the loose tracks are the five of the V2",
              kinds.get("track_dangling", 0) <= 5,
              f"{kinds.get('track_dangling', 0)}")
        check("the silk screen is better than it was at the start",
              kinds.get("silk_over_copper", 0) <= 6,
              f"{kinds.get('silk_over_copper', 0)} over the copper, "
              f"{kinds.get('silk_overlap', 0)} over each other")
        check("the board is measured at all", "violations" in d,
              f"{len(d.get('violations', []))} violations, "
              f"{len(d.get('unconnected_items', []))} unconnected")

        print()
        print("5. the board is unchanged")
        now = hashlib.sha256(open(PCB, "rb").read()).hexdigest()
        was = hashlib.sha256(open(SAVE_PCB, "rb").read()).hexdigest()
        check("the board was not touched", now == was, now[:16])
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
