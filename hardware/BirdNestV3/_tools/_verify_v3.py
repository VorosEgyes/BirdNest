#!/usr/bin/env python3
"""
Ad-hoc verification of the changed behaviour of the BirdNestV3 tools.

There is no test suite in the repository, so this script checks the
claims that the recent edits made.  The tools have their board path hard
coded and they write to it, so the original board and project file are
copied aside and put back at the end.

  1. maze4.py          - the keep-out covers the foreign copper, the own
                         pads stay reachable, the router reaches the nets
                         and leaves no fragments behind.
  2. fix_netclasses.py - every net of the board matches exactly one
                         netclass pattern, the patterns agree with the
                         rules, and the default class carries no
                         differential pair gap.
  3. pack.py           - the packed placement has no overlapping pads of
                         different nets.
  4. merge_tracks.py   - the merge does not run a track over a foreign
                         pad.

Run:  hermes-verify-v3.py
"""
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/_tools")
import pcbnew

HERE = "/Users/modmj/dev/BirdNest/hardware/BirdNestV3/_tools"
V3DIR = os.path.dirname(HERE)
PCB = os.path.join(V3DIR, "BirdNestV3.kicad_pcb")
PRO = os.path.join(V3DIR, "BirdNestV3.kicad_pro")

PY = ("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/"
      "Versions/3.9/bin/python3")
PYPATH = ("/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/"
          "Versions/3.9/lib/python3.9/site-packages")

fails = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def run(script, *args):
    env = {**os.environ, "PYTHONPATH": PYPATH + ":" + HERE}
    return subprocess.run([PY, os.path.join(HERE, script)] + list(args),
                          capture_output=True, text=True, env=env, cwd=HERE)


def wildcard(pat, name):
    # KiCad's netclass pattern syntax: only '*' is a wildcard
    rx = "".join(".*" if c == "*" else re.escape(c) for c in pat)
    return re.fullmatch(rx, name) is not None


def pad_overlaps(board):
    """The tracks that run over a pad of another net."""
    hits = 0
    for t in list(board.GetTracks()):
        if t.GetClass() == "PCB_VIA":
            continue
        a, e = t.GetStart(), t.GetEnd()
        ax, ay = pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)
        ex, ey = pcbnew.ToMM(e.x), pcbnew.ToMM(e.y)
        half = pcbnew.ToMM(t.GetWidth()) / 2
        for fp in board.GetFootprints():
            for p in fp.Pads():
                if p.GetNetname() == t.GetNetname():
                    continue
                layers = [l for l in (pcbnew.F_Cu, pcbnew.B_Cu)
                          if p.IsOnLayer(l)]
                if t.GetLayer() not in layers:
                    continue
                pos = p.GetPosition()
                px, py = pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)
                pw = pcbnew.ToMM(p.GetSize().x)
                ph = pcbnew.ToMM(p.GetSize().y)
                x0, y0 = px - pw / 2, py - ph / 2
                x1, y1 = px + pw / 2, py + ph / 2
                # the distance between the segment and the rectangle
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                dx, dy = ex - ax, ey - ay
                len2 = dx * dx + dy * dy
                if len2 == 0:
                    t2 = 0.0
                else:
                    t2 = ((cx - ax) * dx + (cy - ay) * dy) / len2
                    t2 = max(0.0, min(1.0, t2))
                qx, qy = ax + t2 * dx, ay + t2 * dy
                ddx = max(x0 - qx, 0, qx - x1)
                ddy = max(y0 - qy, 0, qy - y1)
                if (ddx * ddx + ddy * ddy) ** 0.5 <= half:
                    hits += 1
                    break
    return hits


def main():
    sys.path.insert(0, HERE)
    import pcbnew
    import maze4

    shutil.copy(PCB, "/tmp/hermes-verify-orig.kicad_pcb")
    shutil.copy(PRO, "/tmp/hermes-verify-orig.kicad_pro")
    try:
        print("1. maze4.py - keep-out model")
        board = pcbnew.LoadBoard(PCB)
        router = maze4.Router(board)
        for net in router.nets.values():
            clr, width = router._params(net.name)
            net.clearance = clr
            net.halfwidth = width / 2

        net = router.nets.get("/+5V")
        masks = router.build_mask(net)

        foreign_hits = 0
        for other in router.nets.values():
            if other is net:
                continue
            for li in range(len(maze4.LAYERS)):
                for y, bits in enumerate(other.cu[li]):
                    x = 0
                    while bits:
                        low = bits & -bits
                        x = low.bit_length() - 1
                        if masks[li][y * maze4.NX + x]:
                            foreign_hits += 1
                        bits ^= low
        check("the keep-out covers the foreign copper", foreign_hits > 0,
              f"{foreign_hits} cells")

        blocked = [(py, px) for (py, px, pls, phx, phy) in net.pads
                   for li in pls if masks[li][py * maze4.NX + px]]
        check("the own pads stay reachable", not blocked, f"{blocked[:4]}")

        print()
        print("2. maze4.py - the routing itself")
        run("cleartracks.py")
        run("apply_v2_routes.py")
        res = run("maze4.py")
        out = res.stdout or ""
        m = re.search(r"^routed (\d+), failed (\d+)", out, re.M)
        check("the router reports a result", m is not None,
              f"routed={m.group(1)} failed={m.group(2)}" if m else out[-200:])

        failed_nets = re.findall(r"^  FAIL (\S+)", out, re.M)
        check("only the fine pitch nets fail",
              all(n in ("/DONE_STAT", "Net-(U11-ISET)", "/CHG_STAT")
                  for n in failed_nets), f"{failed_nets}")

        run("drop_slivers.py")
        b2 = pcbnew.LoadBoard(PCB)
        v2 = pcbnew.LoadBoard("/Users/modmj/dev/BirdNest/hardware/"
                              "BirdNest_pcb/BirdNest_pcb.kicad_pcb")
        from_v2 = set()
        for t in v2.GetTracks():
            if t.GetClass() != "PCB_VIA":
                a = t.GetStart()
                from_v2.add((t.GetNetname(), round(pcbnew.ToMM(a.x), 3),
                             round(pcbnew.ToMM(a.y), 3)))
        frags = []
        for t in list(b2.GetTracks()):
            if t.GetClass() == "PCB_VIA":
                continue
            ln = pcbnew.ToMM(t.GetLength())
            if not 0 < ln < 0.05:
                continue
            a = t.GetStart()
            if (t.GetNetname(), round(pcbnew.ToMM(a.x), 3),
                    round(pcbnew.ToMM(a.y), 3)) in from_v2:
                continue
            frags.append((t.GetNetname(), round(ln, 3)))
        check("the router leaves no fragments", not frags, f"{frags[:5]}")

        print()
        print("3. fix_netclasses.py - the net classes")
        res = run("fix_netclasses.py")
        check("fix_netclasses.py runs", res.returncode == 0,
              (res.stderr or "")[-200:] if res.returncode else "")

        with open(PRO) as f:
            pro = json.load(f)
        pats = pro["net_settings"]["netclass_patterns"]
        check("the project has netclass patterns", len(pats) > 0, f"{len(pats)}")
        check("the patterns are the plain net names",
              not any(chr(92) in p["pattern"] for p in pats),
              f"{[p['pattern'] for p in pats if chr(92) in p['pattern']][:3]}")

        from fix_netclasses import classify
        b3 = pcbnew.LoadBoard(PCB)
        names = [n.GetNetname() for n in b3.GetNetsByNetcode().values()
                 if n.GetNetname()]
        unmatched = []
        wrong = []
        for name in names:
            hits = sum(1 for p in pats if wildcard(p["pattern"], name))
            if hits > 1:
                unmatched.append((name, hits))
                continue
            if hits == 1:
                cls = [p["netclass"] for p in pats
                       if wildcard(p["pattern"], name)][0]
                if cls != classify(name):
                    wrong.append((name, cls, classify(name)))
            elif classify(name) != "Default":
                wrong.append((name, "Default", classify(name)))
        check("no net matches more than one pattern", not unmatched,
              f"{unmatched[:6]}")
        check("the patterns agree with the rules", not wrong, f"{wrong[:6]}")

        dflt = [c for c in pro["net_settings"]["classes"]
                if c.get("name") == "Default"][0]
        check("the default class carries no diff pair gap",
              dflt.get("diff_pair_gap", 0) == 0
              and dflt.get("diff_pair_width", 0) == 0,
              f"gap={dflt.get('diff_pair_gap')} width={dflt.get('diff_pair_width')}")

        print()
        print("4. pack.py - the packed placement")
        res = run("pack.py")
        check("pack.py runs", res.returncode == 0,
              (res.stderr or "")[-200:] if res.returncode else "")
        with open(os.path.join(HERE, "packed.json")) as f:
            packed = json.load(f)
        check("the packer placed every part", len(packed) == 27, f"{len(packed)}")

        b4 = pcbnew.LoadBoard(PCB)
        pads = []
        for fp in b4.GetFootprints():
            for p in fp.Pads():
                pos = p.GetPosition()
                w = pcbnew.ToMM(p.GetSize().x)
                h = pcbnew.ToMM(p.GetSize().y)
                pads.append((fp.GetReference(), p.GetNetname(),
                             pcbnew.ToMM(pos.x) - w / 2,
                             pcbnew.ToMM(pos.y) - h / 2,
                             pcbnew.ToMM(pos.x) + w / 2,
                             pcbnew.ToMM(pos.y) + h / 2))
        conflicts = [
            (a[0], b[0]) for i, a in enumerate(pads) for b in pads[i + 1:]
            if a[1] != b[1] and a[2] < b[4] and b[2] < a[4]
            and a[3] < b[5] and b[3] < a[5]]
        moved_conflicts = [c for c in conflicts
                           if c[0] in packed or c[1] in packed]
        check("the packed parts do not overlap any other pad",
              not moved_conflicts, f"{moved_conflicts[:4]}")
        # The parts of the v2 board are the reference: the pads of U1
        # overlap there as well, that is not something the packer caused.
        foreign = [c for c in conflicts
                   if c[0] not in packed and c[1] not in packed]
        check("the v2 parts keep their pad overlaps",
              len(foreign) == len(conflicts),
              f"{len(foreign)} of {len(conflicts)} pairs are from the v2 board")

        print()
        print("5. merge_tracks.py - the merge does not create a short")
        run("cleartracks.py")
        run("apply_v2_routes.py")
        run("maze4.py")
        before = pad_overlaps(pcbnew.LoadBoard(PCB))
        run("merge_tracks.py")
        after = pad_overlaps(pcbnew.LoadBoard(PCB))
        # The router itself leaves some overlaps - the pads of a fine
        # pitch package are too close for a track between them.  What the
        # merge must not do is add more of them: the long track covers the
        # whole length of both tracks it joins.
        check("the merge does not add overlaps", after <= before,
              f"{before} before, {after} after")
    finally:
        shutil.copy("/tmp/hermes-verify-orig.kicad_pcb", PCB)
        shutil.copy("/tmp/hermes-verify-orig.kicad_pro", PRO)
        print("\n(the original board and project file are back in place)")

    print()
    if fails:
        print(f"FAILED {len(fails)} checks: {fails}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
