#!/usr/bin/env python3
"""A schematic top-level symbol peldanyainak robustus kiolvasasa.

A parens-mérlegelésre épül, hogy a több soros (effects (font ...))
 blokkokat is kezelje.
"""
import re
import sys

SCH = '/Users/modmj/dev/BirdNest/hardware/BirdNestV3/BirdNestV3.kicad_sch'


def blocks(text, open_tok='(symbol'):
    """Visszaadja a top-level (symbol ...) blokkokat a (lib_symbols) resz kimaradva."""
    out = []
    for m in re.finditer(r'\n\t' + re.escape(open_tok) + r'\n', text):
        st = m.start()
        k = text.index('(', st)
        d = 0
        while True:
            c = text[k]
            if c == '"':
                k += 1
                while text[k] != '"':
                    k += 2 if text[k] == '\\' else 1
            elif c == '(':
                d += 1
            elif c == ')':
                d -= 1
                if d == 0:
                    break
            k += 1
        out.append(text[st:k + 1])
    return out


def prop(blk, name):
    m = re.search(r'\(property "' + re.escape(name) + r'" "([^"]*)"', blk)
    return m.group(1) if m else None


def main():
    text = open(SCH).read()
    # a top-level peldanyok a (lib_symbols ...) resz UTAN vannak; a lib
    # cache-be nem szabad belemenni
    li = text.index('\n\t(lib_symbols\n')
    # a lib_symbols blokk vege: a parens-mérleg alapjan
    k = text.index('(', li)
    d = 0
    while True:
        if text[k] == '(':
            d += 1
        elif text[k] == ')':
            d -= 1
            if d == 0:
                break
        k += 1
    body = text[k + 1:]
    rows = []
    for blk in blocks(body):
        ref = prop(blk, 'Reference')
        if not ref or ref.startswith('#'):
            continue
        lib = re.search(r'\(lib_id "([^"]*)"\)', blk)
        at = re.search(r'\n\t\t\(at ([-\d\.]+) ([-\d\.]+) ([-\d\.]+)\)', blk)
        rows.append({
            'ref': ref,
            'lib': lib.group(1) if lib else '?',
            'value': prop(blk, 'Value'),
            'footprint': prop(blk, 'Footprint'),
            'description': prop(blk, 'Description'),
            'datasheet': prop(blk, 'Datasheet'),
            'at': at.groups() if at else None,
            'block': blk,
        })
    rows.sort(key=lambda r: (r['ref'][0].isdigit(), r['ref']))
    for r in rows:
        print(f"{r['ref']:8} lib={r['lib']:32} val={r['value']:18} "
              f"fp={r['footprint']:40} descr={r['description']}")
    print(f'\nosszes peldany: {len(rows)}')

    # a keresett referenciak reszletes blokkja a fileba
    want = sys.argv[1:] or ['H1', 'H2', 'H3', 'H4', 'H5', 'H6',
                             'TP1', 'TP2', 'TP3', 'TP4', 'TP5', 'D9']
    for r in rows:
        if r['ref'] in want:
            open(f'/tmp/d9data/sch_inst_{r["ref"]}.txt', 'w').write(r['block'])
    print('reszletes blokkok: /tmp/d9data/sch_inst_<REF>.txt')


if __name__ == '__main__':
    main()
