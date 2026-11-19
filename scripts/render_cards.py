#!/usr/bin/env python3
"""Render the profile README cards into cards/.

    python scripts/render_cards.py          animated cards
    STATIC=1 python scripts/render_cards.py final frame only, for screenshots

Inputs: data/profile.json (copy, links, tiles) and data/contributions.json
(refreshed daily by scripts/fetch_data.py). Needs: pip install fonttools.

Authoring rule: every element is written in its final state. Hidden start
frames exist only inside the keyframes (fill-mode "both"), so STATIC output,
reduced-motion output and renderers that ignore animation all show a complete
card. SMIL is used only for the pulse ring on the open-to-work dot, which is
hidden under prefers-reduced-motion.

Type: Instrument Serif for display, Inter for body, IBM Plex Mono for labels.
"""
import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import urlparse
from xml.dom import minidom

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cards"
STATIC = os.environ.get("STATIC") == "1"

# Palette sampled from the design reference: off-white cards, ink, and a blue/red/yellow trio.
C = dict(card="#f3f3f1", ink="#111111", body="#3d3d39", muted="#6e6e69", faint="#c8c8c2",
         line="#dcdcd6", blue="#3057ff", red="#ef3b2d", yellow="#ffc61a", white="#ffffff")
HEAT = ["#e4e4e0", "#c9d3fb", "#8fa2f7", "#4f6df5", "#2640e8"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

FONT_FILES = {
    ("serif", 400, "normal"): "InstrumentSerif-400-normal", ("serif", 400, "italic"): "InstrumentSerif-400-italic",
    ("sans", 400, "normal"): "Inter-400-normal", ("sans", 500, "normal"): "Inter-500-normal",
    ("sans", 600, "normal"): "Inter-600-normal",
    ("mono", 400, "normal"): "IBMPlexMono-400-normal", ("mono", 500, "normal"): "IBMPlexMono-500-normal",
}
CSS_FAMILY = {"serif": "CardSerif", "sans": "CardSans", "mono": "CardMono"}  # never "Serif": that is the generic keyword
FALLBACK = {"serif": "Georgia,serif", "sans": "system-ui,sans-serif", "mono": "ui-monospace,monospace"}

ANIM_CSS = """
@keyframes rise{from{opacity:0;transform:translateY(10px)}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes glint{0%{opacity:0;transform:translateX(-150px) skewX(-20deg)}25%,75%{opacity:.4}100%{opacity:0;transform:translateX(470px) skewX(-20deg)}}
.r{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
.b{transform-box:fill-box;transform-origin:50% 100%;animation:grow .8s cubic-bezier(.2,.7,.2,1) both}
.gl{opacity:0;animation:glint 1.6s ease-in-out both}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.smil{display:none}}
""".strip()


def font_path(face):
    return ROOT / "fonts" / f"{FONT_FILES[face]}.woff"


@lru_cache(None)
def metrics(face):
    f = TTFont(font_path(face))
    return f.getBestCmap(), f["hmtx"], f["head"].unitsPerEm


def width(fam, weight, italic, text, size, ls=0.0):
    cmap, hmtx, upm = metrics((fam, weight, "italic" if italic else "normal"))
    return sum(hmtx[cmap[ord(ch)]][0] for ch in text) * size / upm + ls * len(text)


def subset_b64(face, chars):
    cmap = metrics(face)[0]
    missing = sorted(ch for ch in chars if ord(ch) not in cmap)
    if missing:
        raise SystemExit(f"{face} has no glyph for {missing}; draw it as a path instead")
    with tempfile.TemporaryDirectory() as td:
        txt, out = Path(td, "t.txt"), Path(td, "o.woff")
        txt.write_text("".join(sorted(chars)), "utf-8")
        subprocess.run([sys.executable, "-m", "fontTools.subset", str(font_path(face)), f"--text-file={txt}",
                        "--flavor=woff", "--no-hinting", f"--output-file={out}"], check=True)
        return base64.b64encode(out.read_bytes()).decode()


def wrap(text, fam, size, maxw, weight=400):
    lines, cur = [], ""
    for word in text.split():
        nxt = f"{cur} {word}".strip()
        if width(fam, weight, False, nxt, size) <= maxw:
            cur = nxt
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def arrow(x, y, color, k=1.0):
    return (f'<path transform="translate({x} {y}) scale({k})" d="M0 7H15M9 1l6 6-6 6" fill="none" '
            f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>')


class Card:
    def __init__(self, name, w, h, label, fill=None, border=True, radius=24):
        self.name, self.w, self.h, self.label = name, w, h, label
        self.fill, self.border, self.radius = fill or C["card"], border, radius
        self.body, self.defs, self.chars, self.css = [], "", {}, ""

    def add(self, raw, d=None):
        self.body.append(raw if STATIC or d is None else f'<g class="r" style="animation-delay:{d:.2f}s">{raw}</g>')

    def te(self, x, y, runs, fam="mono", size=14, weight=400, italic=False, fill=None, anchor="start", ls=0.0):
        if isinstance(runs, str):
            runs = [(runs, weight, italic, fill or C["ink"])]
        spans = []
        for txt, w, it, f in runs:
            face = (fam, w, "italic" if it else "normal")
            self.chars.setdefault(face, set()).update(txt)
            weight_attr = f' font-weight="{w}"' if w != 400 else ""
            style_attr = ' font-style="italic"' if it else ""
            spans.append(f'<tspan{weight_attr}{style_attr} fill="{f}">{escape(txt)}</tspan>')
        extra = (f' letter-spacing="{ls:.2f}"' if ls else "") + (f' text-anchor="{anchor}"' if anchor != "start" else "")
        return (f'<text x="{x}" y="{y}" font-family="{CSS_FAMILY[fam]},{FALLBACK[fam]}" '
                f'font-size="{size}"{extra}>{"".join(spans)}</text>')

    def t(self, x, y, runs, *a, d=None, **kw):
        self.add(self.te(x, y, runs, *a, **kw), d)

    def svg(self):
        css = "".join(
            f"@font-face{{font-family:{CSS_FAMILY[fam]};font-weight:{w};font-style:{s};"
            f"src:url(data:font/woff;base64,{subset_b64((fam, w, s), chars | {' '})}) format('woff')}}"
            for (fam, w, s), chars in sorted(self.chars.items()))
        css += self.css
        if not STATIC:
            css += ANIM_CSS
        stroke = f' stroke="{C["line"]}"' if self.border else ""
        frame = (f'<rect x=".5" y=".5" width="{self.w - 1}" height="{self.h - 1}" rx="{self.radius}" '
                 f'fill="{self.fill}"{stroke}/>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" role="img" '
                f'aria-label="{escape(self.label)}">'
                f'<title>{escape(self.label)}</title><style>{css}</style><defs>{self.defs}</defs>'
                f'{frame}{"".join(self.body)}</svg>')


def glint(card, delay):
    if STATIC:
        return
    card.defs += f'<clipPath id="k"><rect width="{card.w}" height="{card.h}" rx="{card.radius}"/></clipPath>'
    card.body.append(f'<g clip-path="url(#k)"><rect class="gl" x="0" y="-20" width="70" height="{card.h + 40}" '
                     f'fill="#fff" style="animation-delay:{delay:.2f}s"/></g>')


def label(c, x, y, text, fill=None, anchor="start", d=None):
    c.t(x, y, text.upper(), "mono", 13, fill=fill or C["muted"], anchor=anchor, ls=1.6, d=d)


# ---------------------------------------------------------------- hero
def hero(P):
    first, last = (w.capitalize() for w in P["name"])
    c = Card("hero", 1000, 500, f"{first} {last}. {P['tagline']}")
    c.add(f'<rect x="44" y="44" width="10" height="10" rx="2.5" fill="{C["blue"]}"/>', 0.0)
    label(c, 64, 54, P["role"], d=0.0)
    if P.get("open_to_work"):
        text = "OPEN TO WORK"
        cx = 956 - width("mono", 400, False, text, 13, 1.6) - 16
        dot = f'<circle cx="{cx:.1f}" cy="49" r="4" fill="{C["blue"]}"/>'
        if not STATIC:
            dot += (f'<circle class="smil" cx="{cx:.1f}" cy="49" r="4" fill="none" stroke="{C["blue"]}" opacity="0">'
                    '<animate attributeName="r" values="4;11" dur="2.4s" begin="0s" repeatCount="indefinite"/>'
                    '<animate attributeName="opacity" values="0.8;0" dur="2.4s" begin="0s" repeatCount="indefinite"/></circle>')
        c.add(dot, 0.1)
        label(c, 956, 54, text, fill=C["blue"], anchor="end", d=0.1)
    # stacked name with tight leading, as in the reference
    c.t(38, 200, first, "serif", 160, fill=C["ink"], ls=-1.5, d=0.15)
    c.t(38, 330, last, "serif", 160, italic=True, fill=C["ink"], ls=-1.5, d=0.25)
    for i, line in enumerate(wrap(P["tagline"], "sans", 21, 600)):
        c.t(44, 400 + i * 30, line, "sans", 21, fill=C["body"], d=0.4)
    host = urlparse(P["links"][0][1]).netloc
    c.add(c.te(44, 468, host, "mono", 14, fill=C["ink"])
          + arrow(44 + width("mono", 400, False, host, 14) + 12, 456, C["blue"], 0.75), 0.5)
    art = ROOT / "data/portrait.txt"
    if art.exists():  # a character halftone, drawn in top to bottom (made by scripts/make_portrait.py)
        lines = art.read_text("utf-8").splitlines()
        fs, lh = 5, 5  # Plex Mono advances 0.6em, so 5px type is 3px per column
        x0 = 956 - max(len(l) for l in lines) * fs * 0.6
        y0 = 96
        for i, line in enumerate(lines):
            if line.strip():
                c.chars.setdefault(("mono", 400, "normal"), set()).update(line)
                lead = len(line) - len(line.lstrip())  # indent by position, so no leading spaces to preserve
                row = (f'<text x="{x0 + lead * fs * 0.6:.1f}" y="{y0 + i * lh}" font-family="{CSS_FAMILY["mono"]},monospace" '
                       f'font-size="{fs}" fill="{C["ink"]}" xml:space="preserve">{escape(line.lstrip())}</text>')
                c.add(row, 0.2 + i * 0.02)
    return c


# ---------------------------------------------------------------- tiles
def tile(spec, i):
    base = 1.9 + i * 0.12
    col = C[spec["color"]]
    ink = C["ink"] if spec["color"] == "yellow" else C["white"]  # text on the tile
    c = Card(f"tile-{i + 1}", 320, 270, f"{spec['big']} {spec['word']}: {spec['body']}", fill=col, border=False)
    label(c, 28, 52, spec["label"], fill=ink, d=base)
    c.add(arrow(277, 42, ink), base)
    size = min(66, 264 / width("serif", 400, False, f"{spec['big']} {spec['word']}", 1))
    c.t(26, 150, [(spec["big"], 400, False, ink), (" " + spec["word"], 400, True, ink)], "serif", size,
        ls=-0.005 * size, d=base + 0.1)
    for j, line in enumerate(wrap(spec["body"], "sans", 16, 264)[:3]):
        c.t(28, 192 + j * 24, line, "sans", 16, fill=ink, d=base + 0.2)
    glint(c, base + 0.5)
    return c


# ---------------------------------------------------------------- stats
def load(P):
    D = json.loads((ROOT / "data/contributions.json").read_text("utf-8"))
    days = [(dt.date.fromisoformat(d), n, lv) for d, n, lv in D["days"]]
    counts = [n for _, n, _ in days]
    longest = run = 0
    for n in counts:
        run = run + 1 if n else 0
        longest = max(longest, run)
    i, current = len(counts) - 1, 0
    if counts[i] == 0:  # a quiet "today" does not break the streak
        i -= 1
    while i >= 0 and counts[i]:
        current += 1
        i -= 1
    last = days[-1][0]
    keys = []
    y, m = last.year, last.month
    for _ in range(12):
        keys.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    keys.reverse()  # last 12 calendar months, current (partial) month last
    month_totals = [sum(n for d, n, _ in days if (d.year, d.month) == k) for k in keys]
    return dict(D=D, days=days, total=D["total"], longest=longest, current=current,
                active=sum(1 for n in counts if n), span=len(days), best=max(counts),
                keys=keys, months=month_totals)


# ---------------------------------------------------------------- heatmap
def heatmap(S):
    c = Card("graph", 1000, 330, f"Contribution graph for the last year, {S['total']:,} contributions")
    base = 0.6
    c.t(40, 76, [("Every day, ", 400, False, C["ink"]), ("in blue", 400, True, C["blue"])],
        "serif", 48, ls=-0.5, d=base)
    label(c, 960, 62, "refreshed daily", anchor="end", d=base)
    cols, col = [], []
    for d, n, lv in S["days"]:
        if (d.weekday() + 1) % 7 == 0 and col:  # weeks start on Sunday
            cols.append(col)
            col = []
        col.append((d, n, lv))
    cols.append(col)
    gap, gx, gy = 3.0, 40.0, 108
    pitch = (920 + gap) / len(cols)  # grid spans exactly the content width, 40..960
    cell = pitch - gap
    labelled = -9
    labels = []
    for ci, wk in enumerate(cols):
        cells = [f'<rect x="{gx + ci * pitch:.2f}" y="{gy + ((d.weekday() + 1) % 7) * pitch:.2f}" width="{cell:.2f}" '
                 f'height="{cell:.2f}" rx="3.5" fill="{HEAT[lv]}"/>' for d, n, lv in wk]
        grp = "".join(cells)
        c.body.append(grp if STATIC else f'<g class="r" style="animation-delay:{base + 0.2 + ci * 0.01:.3f}s">{grp}</g>')
        first = wk[0][0]
        prev = cols[ci - 1][0][0] if ci else None
        if (prev is None or prev.month != first.month) and ci - labelled >= 4 and ci >= 1:
            labels.append(c.te(gx + ci * pitch, 268, MONTHS[first.month - 1], "mono", 12, fill=C["muted"]))
            labelled = ci
    c.add("".join(labels), base + 0.5)
    step, ly = 18, 302  # legend on its own row: the month labels run to the right edge
    lx = 839  # 5 squares + 8px + the 4-char word 'more' end exactly at x=960
    leg = c.te(lx - 8, ly, "less", "mono", 12, fill=C["muted"], anchor="end")
    leg += "".join(f'<rect x="{lx + k * step}" y="{ly - 11}" width="12" height="12" rx="3" fill="{HEAT[k]}"/>' for k in range(5))
    leg += c.te(960, ly, "more", "mono", 12, fill=C["muted"], anchor="end")
    c.add(leg, base + 0.6)
    return c


# ---------------------------------------------------------------- chart
def chart(S):
    c = Card("chart", 1000, 470, f"{S['total']:,} contributions in the last 12 months, "
             f"current streak {S['current']} days, longest {S['longest']}, busiest day {S['best']}")
    base = 1.3
    label(c, 40, 62, "the last 12 months on github", d=base)
    c.t(38, 144, [(f"{S['total']:,} ", 400, False, C["ink"]), ("contributions", 400, True, C["ink"])],
        "serif", 80, ls=-0.8, d=base + 0.05)
    base_y, max_h, x0, pitch, bw = 404, 210, 40, 54, 40
    top = max(S["months"]) or 1  # the partial month can already be the biggest, so it sets the scale too
    complete = S["months"][:-1] or [0]
    peak = S["months"].index(max(complete))  # only a finished month earns the highlight
    for i, (v, (y, m)) in enumerate(zip(S["months"], S["keys"])):
        x, h = x0 + i * pitch, max(4, round(v / top * max_h))
        partial = i == len(S["months"]) - 1
        fill = C["faint"] if partial else (C["blue"] if i == peak else C["ink"])
        bar = f'<rect x="{x}" y="{base_y - h}" width="{bw}" height="{h}" rx="5" fill="{fill}"/>'
        c.body.append(bar if STATIC else bar.replace("<rect ", f'<rect class="b" style="animation-delay:{base + 0.2 + i * 0.05:.2f}s" ', 1))
        c.t(x + bw / 2, 430, MONTHS[m - 1], "mono", 12, fill=C["muted"], anchor="middle", d=base + 0.2 + i * 0.03)
        if i == peak or partial:
            c.t(x + bw / 2, base_y - h - 10, f"{v:,}", "mono", 13, 500,
                fill=C["blue"] if i == peak else C["muted"], anchor="middle", d=base + 0.8)
    cur, plural = S["current"], "day" if S["current"] == 1 else "days"
    rows = [
        ([(f"{cur} ", 400, False, C["ink"]), (plural, 400, True, C["ink"])], f"current streak, longest {S['longest']}d"),
        ([(f"{S['active']} ", 400, False, C["ink"]), (f"/ {S['span']}", 400, False, C["muted"])], "days with a commit"),
        ([(f"{S['best']}", 400, False, C["ink"])], "on the busiest day"),
    ]
    for k, (runs, cap) in enumerate(rows):
        y0 = 150 + k * 132
        c.t(740, y0, runs, "serif", 64, ls=-0.6, d=base + 0.2 + k * 0.12)
        c.t(740, y0 + 32, cap, "sans", 16, fill=C["muted"], d=base + 0.3 + k * 0.12)
        if k < 2:
            c.add(f'<rect x="740" y="{y0 + 56}" width="220" height="1" fill="{C["line"]}"/>', base + 0.3 + k * 0.12)
    return c


# ---------------------------------------------------------------- section heading + repos
def heading():
    c = Card("coding-head", 1000, 76, "What I'm coding", fill="none", border=False)
    # text must read on both a white and a dark page, so it follows the viewer's colour scheme
    c.css = f".hd tspan{{fill:{C['ink']}}}@media (prefers-color-scheme:dark){{.hd tspan{{fill:{C['card']}}}}}"
    runs = [("What I'm ", 400, False, C["ink"]), ("coding", 400, True, C["ink"])]
    c.add(f'<g class="hd">{c.te(8, 56, runs, "serif", 52, ls=-0.5)}</g>', 2.4)
    return c


def repo(spec, meta, i):
    base = 2.6 + i * 0.12
    col = C[spec["color"]]
    lang, live = meta.get("language") or "", bool(meta.get("homepage"))
    foot = " · ".join(p for p in (lang, "live" if live else "") if p)
    c = Card(f"repo-{i + 1}", 320, 250, f"{spec['name']}: {spec['desc']}")
    c.add(f'<rect x="28" y="33" width="14" height="14" rx="3.5" fill="{col}"/>', base)
    c.t(54, 48, spec["name"], "sans", 21, 600, d=base)
    for j, line in enumerate(wrap(spec["desc"], "sans", 16, 264)[:4]):
        c.t(28, 98 + j * 25, line, "sans", 16, fill=C["body"], d=base + 0.1)
    c.t(28, 220, foot, "mono", 13, fill=C["muted"], d=base + 0.2)
    return c


# ---------------------------------------------------------------- checks
def verify(name, svg):
    minidom.parseString(svg)  # well-formed XML
    stripped = svg.replace('xmlns="http://www.w3.org/2000/svg"', "").replace(
        'xmlns:xlink="http://www.w3.org/1999/xlink"', "")
    assert "http" not in stripped, f"{name}: external URL inside the card"
    assert "<script" not in svg and "<foreignObject" not in svg, f"{name}: scripts do not run in <img>"
    for ref in re.findall(r'(?:href|src)="([^"]*)"', svg):
        assert ref.startswith("data:"), f"{name}: non-data href {ref[:40]}"
    for ref in re.findall(r"url\(([^)]*)\)", svg):
        assert ref.startswith(("data:", "#")), f"{name}: non-local url({ref[:40]})"
    if STATIC:
        assert "<animate" not in svg and "@keyframes" not in svg, f"{name}: STATIC output is animated"


def main():
    P = json.loads((ROOT / "data/profile.json").read_text("utf-8"))
    S = load(P)
    cards = [hero(P), heatmap(S), chart(S)]
    cards += [tile(t, i) for i, t in enumerate(P["tiles"])]
    cards.append(heading())
    cards += [repo(f, S["D"]["repos"].get(f["name"], {}), i) for i, f in enumerate(P["featured"])]
    cards.append(Card("gap", 10, 10, "", border=False, fill="none"))
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    for card in cards:
        svg = card.svg()
        verify(card.name, svg)
        (OUT / f"{card.name}.svg").write_text(svg, "utf-8", newline="\n")
        print(f"{card.name:12} {len(svg) / 1024:6.1f} KB")
    print("static final frame" if STATIC else "animated")


if __name__ == "__main__":
    main()
