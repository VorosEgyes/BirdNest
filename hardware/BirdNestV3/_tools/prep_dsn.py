#!/usr/bin/env python3
"""
Post-process the KiCad DSN export for freerouting:

  * add (net_class ...) blocks so the auto-router uses the real track widths
    instead of the 0.5 mm default for every net,
  * drop the GND "plane" from the structure section - a plane is a
    conduction area that the router must not treat as a routeable copper
    area, and it was blocking 22 connections.
"""
import re
import sys

DSN = sys.argv[1] if len(sys.argv) > 1 else "/tmp/v3_real.dsn"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/tmp/v3_fr.dsn"

# netclass name -> (clearance um, track width um, via dia um, via drill um)
CLASSES = {
    "Power_Battery": (200, 800, 600, 300),
    "Power_5V_Out": (200, 1000, 600, 300),
    "Power_3V3": (200, 400, 600, 300),
    "Switching_Node": (300, 1000, 600, 300),
    "Signal": (250, 200, 600, 300),
}

# net name pattern -> class
RULES = [
    ("Power_Battery", r"^/(BAT_CELL\+|BAT_PROT\+|BAT_CELL-|BAT_RAW|SYS_PWR|VIN_PROT)$"),
    ("Power_Battery", r"^Net-\((Q9-S|Q9-D|D10-A|D10-K|J4-Pin_2)\)$"),
    ("Power_5V_Out", r"^/\+5V$"),
    ("Power_3V3", r"^/(\+3V3|REF2V5)$"),
    ("Switching_Node", r"^Net-\((D9-A|D6-A|Q3-D)\)$"),
    ("Signal", r"^/(BAT_MON|CHG_STAT|DONE_STAT|UVLO_.*|PIR\. SIG\.|TEMP\. SIG\.)$"),
    ("Signal", r"^Net-\((D7-A|Q9-G|U7A-\+|U11-.*|U10-.*|U3-LX|JP3-C)\)$"),
]


def classify(name):
    for cls, pat in RULES:
        if re.fullmatch(pat, name):
            return cls
    return None


def main():
    with open(DSN) as f:
        s = f.read()

    # ---- 1. remove the GND planes from the structure --------------------
    # (the board keeps its own GND zone in KiCad; freerouting only needs the
    #  outline + a keepout to know where the copper is)
    before = s
    s = re.sub(r"\n\s*\(plane GND \(polygon [FB]\.Cu[^\n]*\n[^\)]*\)", "", s)
    print(f"planes removed: {before != s}")

    # ---- 2. collect the nets from the wiring section ---------------------
    nets = re.findall(r"\(net\s+(\S+)\s", s)
    nets = sorted(set(nets))
    print(f"nets in dsn: {len(nets)}")

    by_class = {}
    for n in nets:
        c = classify(n)
        if c:
            by_class.setdefault(c, []).append(n)
    for c in by_class:
        print(f"  {c}: {len(by_class[c])} nets")

    # ---- 3. build the net_class blocks -----------------------------------
    blocks = []
    for cname, (clr, width, via, drill) in CLASSES.items():
        members = by_class.get(cname)
        if not members:
            continue
        body = " ".join(f'"{m}"' for m in members)
        blocks.append(
            f"    (net_class {cname}\n"
            f"      (clearance {clr})\n"
            f"      (trace_width {width})\n"
            f"      (via_dia {via})\n"
            f"      (via_drill {drill})\n"
            f"      (pcb_color rgba(0, 0, 0, 0.000))\n"
            f"      (nets {body})\n"
            f"    )"
        )

    nc_text = "\n".join(blocks)
    if "(net_class" in s:
        s = re.sub(r"\(net_class.*?\n    \)", nc_text, s, flags=re.S)
    else:
        # net classes must be the first children of the structure block
        m = re.search(r"\(structure\n", s)
        insert_at = m.end()
        s = s[:insert_at] + "    " + nc_text + "\n" + s[insert_at:]

    with open(OUT, "w") as f:
        f.write(s)
    print(f"wrote {OUT} ({len(s)} bytes) with {len(blocks)} net classes")


if __name__ == "__main__":
    main()
