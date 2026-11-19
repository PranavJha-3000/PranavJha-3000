#!/usr/bin/env python3
"""Render the profile README cards into cards/.

    python scripts/render_cards.py          animated cards
    STATIC=1 python scripts/render_cards.py final frame only, for screenshots

Inputs: data/profile.json (copy, links, tiles) and data/contributions.json
(refreshed daily by scripts/fetch_data.py). Needs: pip install fonttools.

Authoring rule: every element is written in its final state. Hidden start
frames exist only inside the keyframes (fill-mode "both"), so STATIC output,
reduced-motion output and renderers that ignore animation all show a complete
card. SMIL is used only for the live dot and the cursor, each with a static
twin that is swapped by prefers-reduced-motion.
"""
import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
import tempfile
from html import escape
from pathlib import Path
from xml.dom import minidom

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "cards"
STATIC = os.environ.get("STATIC") == "1"

# Palette sampled from the design reference: off-white cards, ink, and a blue/red/yellow trio.
C = dict(card="#f3f3f1", ink="#111111", muted="#6e6e69", faint="#c8c8c2", line="#dcdcd6",
         blue="#3057ff", red="#ef3b2d", yellow="#ffc61a", white="#ffffff")
HEAT = ["#e4e4e0", "#c9d3fb", "#8fa2f7", "#4f6df5", "#2640e8"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ADV = 0.6  # IBM Plex Mono advance width, in em

FONTS = {(w, s): ROOT / "fonts" / f"IBMPlexMono-{w}-{s}.woff"
         for w, s in [(400, "normal"), (500, "normal"), (600, "normal"), (500, "italic")]}

ANIM_CSS = """
@keyframes rise{from{opacity:0;transform:translateY(10px)}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes glint{0%{opacity:0;transform:translateX(-150px) skewX(-20deg)}25%,75%{opacity:.4}100%{opacity:0;transform:translateX(470px) skewX(-20deg)}}
.r{animation:rise .7s cubic-bezier(.2,.7,.2,1) both}
.b{transform-box:fill-box;transform-origin:50% 100%;animation:grow .8s cubic-bezier(.2,.7,.2,1) both}
.gl{opacity:0;animation:glint 1.6s ease-in-out both}
@media (prefers-reduced-motion:no-preference){.twin{display:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.smil{display:none}}
""".strip()


def subset_b64(face, chars):
    src = FONTS[face]
    cmap = TTFont(src).getBestCmap()
    missing = sorted(ch for ch in chars if ord(ch) not in cmap)
    if missing:
        raise SystemExit(f"{src.name} has no glyph for {missing}; draw it as a path instead")
    with tempfile.TemporaryDirectory() as td:
        txt, out = Path(td, "t.txt"), Path(td, "o.woff")
        txt.write_text("".join(sorted(chars)), "utf-8")
        subprocess.run([sys.executable, "-m", "fontTools.subset", str(src), f"--text-file={txt}",
                        "--flavor=woff", "--no-hinting", f"--output-file={out}"], check=True)
        return base64.b64encode(out.read_bytes()).decode()


def wrap(text, size, maxw, ls=0.0):
    n = max(1, int(maxw // (size * ADV + ls)))
    lines, cur = [], ""
    for word in text.split():
        nxt = f"{cur} {word}".strip()
        if len(nxt) <= n:
            cur = nxt
        else:
            lines.append(cur)
            cur = word
    return lines + [cur] if cur else lines


def arrow(x, y, color):
    return (f'<path transform="translate({x} {y})" d="M0 7H15M9 1l6 6-6 6" fill="none" '
            f'stroke="{color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>')


class Card:
    def __init__(self, name, w, h, label, fill=None, border=True, radius=20):
        self.name, self.w, self.h, self.label = name, w, h, label
        self.fill, self.border, self.radius = fill or C["card"], border, radius
        self.body, self.defs, self.faces, self.chars = [], "", set(), {" "}

    def add(self, raw, d=None):
        self.body.append(raw if STATIC or d is None else f'<g class="r" style="animation-delay:{d:.2f}s">{raw}</g>')

    def te(self, x, y, runs, size=14, weight=400, italic=False, fill=None, anchor="start", ls=0.0):
        if isinstance(runs, str):
            runs = [(runs, weight, italic, fill or C["ink"])]
        spans = []
        for txt, w, it, f in runs:
            self.faces.add((w, "italic" if it else "normal"))
            self.chars.update(txt)
            spans.append(f'<tspan font-weight="{w}"{" font-style=\"italic\"" if it else ""} fill="{f}">{escape(txt)}</tspan>')
        extra = (f' letter-spacing="{ls:.2f}"' if ls else "") + (f' text-anchor="{anchor}"' if anchor != "start" else "")
        return f'<text x="{x}" y="{y}" font-size="{size}"{extra}>{"".join(spans)}</text>'

    def t(self, x, y, runs, *a, d=None, **kw):
        self.add(self.te(x, y, runs, *a, **kw), d)

    def svg(self):
        css = "".join(
            f"@font-face{{font-family:PlexMono;font-weight:{w};font-style:{s};"
            f"src:url(data:font/woff;base64,{subset_b64((w, s), self.chars)}) format('woff')}}"
            for w, s in sorted(self.faces))
        if not STATIC:
            css += ANIM_CSS
        stroke = f' stroke="{C["line"]}"' if self.border else ""
        frame = (f'<rect x=".5" y=".5" width="{self.w - 1}" height="{self.h - 1}" rx="{self.radius}" '
                 f'fill="{self.fill}"{stroke}/>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'viewBox="0 0 {self.w} {self.h}" width="{self.w}" height="{self.h}" role="img" '
                f'aria-label="{escape(self.label)}" font-family="PlexMono,ui-monospace,monospace">'
                f'<title>{escape(self.label)}</title><style>{css}</style><defs>{self.defs}</defs>'
                f'{frame}{"".join(self.body)}</svg>')


def glint(card, delay):
    if STATIC:
        return
    card.defs += f'<clipPath id="k"><rect width="{card.w}" height="{card.h}" rx="{card.radius}"/></clipPath>'
    card.body.append(f'<g clip-path="url(#k)"><rect class="gl" x="0" y="-20" width="70" height="{card.h + 40}" '
                     f'fill="#fff" style="animation-delay:{delay:.2f}s"/></g>')


# ---------------------------------------------------------------- hero
def hero(P):
    portrait = ROOT / P["portrait"] if P.get("portrait") else None
    portrait = portrait if portrait and portrait.exists() else None
    name = " ".join(P["name"])
    c = Card("hero", 1000, 340, f"{name}. {P['tagline']}")
    # prompt line, as on the site: ~ > whoami with a blinking cursor
    prompt = (c.te(40, 58, "~", 15, fill=C["muted"])
              + f'<path d="M60 49l6 6-6 6" fill="none" stroke="{C["muted"]}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
              + c.te(76, 58, "whoami", 15, fill=C["muted"]))
    c.add(prompt, 0.0)
    cursor = f'<rect x="134" y="45" width="8" height="16" fill="{C["muted"]}"'
    if STATIC:
        c.body.append(cursor + "/>")
    else:
        c.body.append(cursor + ' class="twin"/>')
        c.body.append(cursor + ' class="smil"><animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.5;1" '
                      'dur="1.1s" begin="0s" repeatCount="indefinite"/></rect>')
    if P.get("open_to_work"):
        label = "open to work"
        cx = 960 - len(label) * 13 * ADV - 14
        dot = f'<circle cx="{cx:.1f}" cy="53" r="4" fill="{C["blue"]}"/>'
        if not STATIC:
            dot += (f'<circle class="smil" cx="{cx:.1f}" cy="53" r="4" fill="none" stroke="{C["blue"]}" opacity="0">'
                    '<animate attributeName="r" values="4;11" dur="2.4s" begin="0s" repeatCount="indefinite"/>'
                    '<animate attributeName="opacity" values="0.8;0" dur="2.4s" begin="0s" repeatCount="indefinite"/></circle>')
        c.add(dot + c.te(960, 58, label, 13, fill=C["blue"], anchor="end"), 0.1)
    c.t(38, 158, [(P["name"][0] + " ", 600, False, C["ink"]), (P["name"][1], 500, True, C["blue"])],
        d=0.15, size=88, ls=-3.5)
    maxw = 590 if portrait else 860
    for i, line in enumerate(wrap(P["tagline"], 17, maxw)):
        c.t(40, 204 + i * 26, line, d=0.3, size=17, fill=C["ink"])
    x, chips = 40, []
    for s in P["stack"]:
        w = len(s) * 13 * ADV + 22
        if x + w > (640 if portrait else 960):
            break
        chips.append(f'<rect x="{x}" y="250" width="{w:.1f}" height="28" rx="4" fill="none" stroke="{C["line"]}"/>'
                     + c.te(x + 11, 269, s, 13, fill=C["muted"]))
        x += w + 10
    c.add("".join(chips), 0.4)
    st = P["status"]
    c.add(f'<path d="M40 303l9 6-9 6z" fill="{C["blue"]}"/>'
          + c.te(60, 316, [(st["label"] + " ", 400, False, C["muted"]), (st["name"], 600, False, C["blue"]),
                           (", " + st["rest"], 400, False, C["muted"])], 14), 0.5)
    if portrait:
        mime = "image/png" if portrait.suffix == ".png" else "image/jpeg"
        b64 = base64.b64encode(portrait.read_bytes()).decode()
        c.defs += '<clipPath id="pc"><circle cx="850" cy="176" r="88"/></clipPath>'
        c.add(f'<image href="data:{mime};base64,{b64}" x="762" y="88" width="176" height="176" '
              f'preserveAspectRatio="xMidYMid slice" clip-path="url(#pc)"/>'
              f'<circle cx="850" cy="176" r="88" fill="none" stroke="{C["blue"]}" stroke-width="2"/>', 0.2)
    return c


# ---------------------------------------------------------------- tiles
def tile(spec, i):
    base = 0.6 + i * 0.12
    col = C[spec["color"]]
    dark = C["ink"] if spec["color"] == "yellow" else C["white"]  # text on the tile
    c = Card(f"tile-{i + 1}", 320, 250, f"{spec['big']} {spec['word']}: {spec['body']}", fill=col, border=False, radius=20)
    c.t(28, 46, spec["label"].upper(), 13, 500, fill=dark, ls=1.6, d=base)
    c.add(arrow(277, 38, dark), base)
    n = len(spec["big"]) + 1 + len(spec["word"])
    size = min(40, int(264 / (n * (ADV - 0.04))))
    c.t(28, 130, [(spec["big"], 600, False, dark), (" " + spec["word"], 500, True, dark)],
        d=base + 0.1, size=size, ls=-0.04 * size)
    for j, line in enumerate(wrap(spec["body"], 14, 264)[:3]):
        c.t(28, 178 + j * 21, line, 14, fill=dark, d=base + 0.2)
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


# ---------------------------------------------------------------- chart
def chart(S):
    c = Card("chart", 1000, 450, f"{S['total']:,} contributions in the last 12 months, "
             f"current streak {S['current']} days, longest {S['longest']}, busiest day {S['best']}")
    c.t(40, 60, "THE LAST 12 MONTHS ON GITHUB", 13, fill=C["muted"], ls=1.6, d=1.1)
    c.t(40, 124, [(f"{S['total']:,} ", 600, False, C["ink"]), ("contributions", 500, True, C["blue"])],
        d=1.15, size=52, ls=-2.1)
    base_y, max_h, x0, pitch, bw = 380, 200, 40, 54, 40
    top = max(S["months"]) or 1  # the partial month can already be the biggest, so it sets the scale too
    complete = S["months"][:-1] or [0]
    peak = S["months"].index(max(complete))  # only a finished month earns the highlight
    for i, (v, (y, m)) in enumerate(zip(S["months"], S["keys"])):
        x, h = x0 + i * pitch, max(4, round(v / top * max_h))
        partial = i == len(S["months"]) - 1
        if partial:
            bar = f'<rect x="{x}" y="{base_y - h}" width="{bw}" height="{h}" rx="5" fill="{C["faint"]}"/>'
        else:
            fill = C["blue"] if i == peak else C["ink"]
            bar = f'<rect x="{x}" y="{base_y - h}" width="{bw}" height="{h}" rx="5" fill="{fill}"/>'
        c.body.append(bar if STATIC else bar.replace("<rect ", f'<rect class="b" style="animation-delay:{1.3 + i * 0.05:.2f}s" ', 1))
        c.t(x + bw / 2, 404, MONTHS[m - 1], 12, fill=C["muted"], anchor="middle", d=1.3 + i * 0.03)
        if i == peak or partial:
            c.t(x + bw / 2, base_y - h - 10, f"{v:,}", 13, 500, fill=C["blue"] if i == peak else C["muted"], anchor="middle", d=1.9)
    cur, plural = S["current"], "day" if S["current"] == 1 else "days"
    rows = [
        ([(f"{cur} ", 600, False, C["ink"]), (plural, 500, True, C["blue"])], f"current streak, longest {S['longest']}d"),
        ([(f"{S['active']} ", 600, False, C["ink"]), (f"/ {S['span']}", 400, False, C["muted"])], "days with a commit"),
        ([(f"{S['best']}", 600, False, C["ink"])], "on the busiest day"),
    ]
    for k, (runs, cap) in enumerate(rows):
        y0 = 118 + k * 130
        c.t(740, y0, runs, d=1.3 + k * 0.12, size=46, ls=-1.8)
        c.t(740, y0 + 30, cap, 13, fill=C["muted"], d=1.4 + k * 0.12)
        if k < 2:
            c.add(f'<rect x="740" y="{y0 + 52}" width="220" height="1" fill="{C["line"]}"/>', 1.4 + k * 0.12)
    return c


# ---------------------------------------------------------------- repos
def repo(spec, meta, i):
    base = 1.7 + i * 0.12
    col = C[spec["color"]]
    lang = meta.get("language") or ""
    foot = lang.lower() + (" · live" if meta.get("homepage") else "")
    c = Card(f"repo-{i + 1}", 320, 230, f"{spec['name']}: {spec['desc']}")
    c.add(f'<rect x="28" y="30" width="13" height="13" rx="3" fill="{col}"/>', base)
    c.t(52, 43, spec["name"].lower(), 17, 600, d=base, ls=-0.4)
    for j, line in enumerate(wrap(spec["desc"], 14, 264)[:4]):
        c.t(28, 88 + j * 22, line, 14, fill=C["ink"], d=base + 0.1)
    c.t(28, 202, foot, 13, fill=C["muted"], d=base + 0.2)
    return c


# ---------------------------------------------------------------- heatmap
def heatmap(S):
    c = Card("graph", 1000, 320, f"Contribution graph for the last year, {S['total']:,} contributions")
    base = 2.3
    c.t(40, 68, [("Every day, ", 600, False, C["ink"]), ("in blue", 500, True, C["blue"])],
        d=base, size=30, ls=-1.2)
    c.t(960, 62, "REFRESHED DAILY", 13, fill=C["muted"], anchor="end", ls=1.6, d=base)
    cols, col = [], []
    for d, n, lv in S["days"]:
        if (d.weekday() + 1) % 7 == 0 and col:  # weeks start on Sunday
            cols.append(col)
            col = []
        col.append((d, n, lv))
    cols.append(col)
    gap, gx, gy = 3.0, 40.0, 98
    pitch = (920 + gap) / len(cols)  # grid spans exactly the content width, 40..960
    cell = pitch - gap
    labelled = -9
    labels = []
    for ci, wk in enumerate(cols):
        cells = [f'<rect x="{gx + ci * pitch:.2f}" y="{gy + ((d.weekday() + 1) % 7) * pitch:.2f}" width="{cell:.2f}" '
                 f'height="{cell:.2f}" rx="3.5" fill="{HEAT[lv]}"/>' for d, n, lv in wk]
        grp = "".join(cells)
        c.body.append(grp if STATIC else f'<g class="r" style="animation-delay:{base + 0.2 + ci * 0.012:.3f}s">{grp}</g>')
        first = wk[0][0]
        prev = cols[ci - 1][0][0] if ci else None
        if (prev is None or prev.month != first.month) and ci - labelled >= 4 and ci >= 1:
            labels.append(c.te(gx + ci * pitch, 258, MONTHS[first.month - 1], 12, fill=C["muted"]))
            labelled = ci
    c.add("".join(labels), base + 0.5)
    step, ly = 18, 292  # legend on its own row: the month labels run to the right edge
    lx = 839  # 5 squares + 8px + the 4-char word 'more' end exactly at x=960
    leg = c.te(lx - 8, ly, "less", 12, fill=C["muted"], anchor="end")
    leg += "".join(f'<rect x="{lx + k * step}" y="{ly - 11}" width="12" height="12" rx="3" fill="{HEAT[k]}"/>' for k in range(5))
    leg += c.te(960, ly, "more", 12, fill=C["muted"], anchor="end")
    c.add(leg, base + 0.6)
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
    cards = [hero(P)]
    cards += [tile(t, i) for i, t in enumerate(P["tiles"])]
    cards.append(chart(S))
    cards += [repo(f, S["D"]["repos"].get(f["name"], {}), i) for i, f in enumerate(P["featured"])]
    cards.append(heatmap(S))
    cards.append(Card("gap", 10, 10, "", border=False, fill="none"))
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.svg"):
        old.unlink()
    for card in cards:
        svg = card.svg()
        verify(card.name, svg)
        (OUT / f"{card.name}.svg").write_text(svg, "utf-8", newline="\n")
        print(f"{card.name:8} {len(svg) / 1024:6.1f} KB")
    print("static final frame" if STATIC else "animated")


if __name__ == "__main__":
    main()
