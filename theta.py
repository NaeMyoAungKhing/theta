#!/usr/bin/env python3
"""
Theta - turn a research PDF into a one-page, dyslexia-friendly "rich picture" card.

Output card layout (matches the user's template):
  +-------------------------------------------------------------+
  |  PAPER TITLE  /  authors - year - venue        [STUDY TYPE] |
  |  ........................ RICH PICTURE ..................... |
  |  WHO  ->  CORE APPROACH  ->  FACTORS/THEMES  ->  OUTCOME     |
  |  [ MEANS (how) ............ ] [ ENDS (why / for what) ..... ]|
  +-------------------------------------------------------------+
  [ PAPER INFO: country - region - sample/impact - type ]
  [ KEY VERBATIMS  (page - line, for citation) ]

Usage:
    python theta.py paper.pdf                 # auto-extract everything
    python theta.py paper.pdf fields.json     # auto-extract, then override
                                              # interpretive fields from JSON
Produces:  paper.theta.svg  and  paper.theta.json  (the fields used)

How automatic is it?
  * AUTOMATIC (deterministic): title, authors, year, venue, country, region,
    sample size, study type, and candidate verbatims WITH page + line numbers.
  * INTERPRETIVE (the diagram, Means, Ends): filled by heuristics, and best
    refined by an AI reading step that writes the small JSON schema. That JSON
    is what `fields.json` overrides - see README.md.
"""
import sys, os, re, json, html, subprocess

# -----------------------------------------------------------------------------
# 1. PDF -> text, keeping page + line numbers (so quotes are citable)
# -----------------------------------------------------------------------------
def pdf_pages(path):
    """Return list of pages; each page is a list of (line_no, text) non-empty lines."""
    out = subprocess.run(["pdftotext", "-layout", path, "-"],
                         capture_output=True, text=True).stdout
    pages = []
    for raw in out.split("\f"):
        lines = []
        for i, ln in enumerate(raw.split("\n"), 1):
            if ln.strip():
                lines.append((i, ln.rstrip()))
        pages.append(lines)
    return pages

def flat_text(pages):
    return "\n".join(t for pg in pages for _, t in pg)

# -----------------------------------------------------------------------------
# 2. Deterministic metadata extraction
# -----------------------------------------------------------------------------
COUNTRIES = ["Philippines","Romania","Ecuador","China","United Kingdom","USA",
    "United States","Taiwan","Turkey","Australia","Spain","Indonesia","Japan",
    "Malaysia","Italy","Russia","Canada","Egypt","Greece","Israel","Mexico",
    "Poland","Qatar","Thailand","Saudi Arabia","Brazil","France","Ghana","India",
    "South Korea","Korea","Germany","Netherlands","Portugal","Ireland","Finland"]

REGION = {"Philippines":"Southeast Asia","Romania":"Eastern Europe (EU)",
    "Ecuador":"Latin America","China":"East Asia","Taiwan":"East Asia",
    "Japan":"East Asia","South Korea":"East Asia","Korea":"East Asia",
    "United Kingdom":"Western Europe","Spain":"Western Europe","Italy":"Southern Europe",
    "USA":"North America","United States":"North America","Canada":"North America",
    "Australia":"Oceania","Turkey":"West Asia","India":"South Asia"}

TYPE_RULES = [
    ("PRISMA", "Systematic review (PRISMA)"),
    ("systematic literature review", "Systematic review"),
    ("systematic review", "Systematic review"),
    ("meta-analysis", "Meta-analysis"),
    ("focus group", "Qualitative study (focus group)"),
    ("semi-structured interview", "Qualitative study (interviews)"),
    ("grounded theory", "Qualitative study"),
    ("mixed method", "Mixed-methods study"),
    ("quantitative research", "Quantitative study"),
    ("quantitative", "Quantitative study"),
    ("qualitative", "Qualitative study"),
    ("survey", "Survey study"),
]

def first_page_block(pages):
    return pages[0] if pages else []

def extract_meta(pages):
    text = flat_text(pages)
    low = text.lower()
    meta = {}

    meta["study_type"] = next((label for kw, label in TYPE_RULES if kw in low), "Research article")

    m = re.search(r"\b(19|20)\d{2}\b", text[:4000])
    meta["year"] = m.group(0) if m else ""

    head = text[:3000]
    meta["country"] = next((c for c in COUNTRIES if c in head), "")
    meta["region"] = REGION.get(meta["country"], "")

    sample = ""
    m = re.search(r"\b(\d{1,4})\s+"
                  r"(respondents|participants|informants|representatives|experts|"
                  r"interviewees|companies|firms|primary studies|studies|students|teachers)",
                  low)
    if m:
        sample = f"{m.group(1)} {m.group(2)}"
    meta["sample"] = sample
    return meta

ENDS_TRIGGERS = ["aims to", "aim of", "purpose of", "this study", "this paper",
                 "the study aims", "objective", "findings show", "results show",
                 "results reveal", "the results", "we found", "underscore"]
MEANS_TRIGGERS = ["research design", "design is employed", "method", "sampling",
                  "questionnaire", "focus group", "data were", "data collected",
                  "interview", "protocol", "respondents of the study", "instrument"]

def candidate_quotes(pages, triggers, limit=6):
    hits = []
    for pi, pg in enumerate(pages, 1):
        for (ln, txt) in pg:
            t = txt.strip()
            low = t.lower()
            if len(t) < 40 or len(t) > 220:
                continue
            if any(k in low for k in triggers):
                hits.append({"page": pi, "line": str(ln), "text": t})
            if len(hits) >= limit:
                return hits
    return hits

# -----------------------------------------------------------------------------
# 3. Heuristic interpretive fields (rough; override with JSON / AI step)
# -----------------------------------------------------------------------------
def heuristic_fields(pages, meta):
    title = ""
    auth = ""
    p1 = first_page_block(pages)
    cap_lines = [t for _, t in p1[:14] if sum(c.isupper() for c in t) > len(t) * 0.5 and len(t) > 12]
    if cap_lines:
        title = " ".join(cap_lines[:2]).title()
    for _, t in p1:
        if ("," in t or " and " in t) and any(ch.isalpha() for ch in t) and len(t) < 90 \
                and not t.isupper() and "@" not in t and "Abstract" not in t:
            auth = t.strip()
            break
    ev = candidate_quotes(pages, ENDS_TRIGGERS, 4)
    mv = candidate_quotes(pages, MEANS_TRIGGERS, 4)
    return {
        "title": title or "(title not detected - set manually)",
        "authors": auth or "(authors not detected)",
        "venue": "",
        "central": "Core approach",
        "actors": ["Study participants"],
        "factors": ["(theme 1)", "(theme 2)", "(theme 3)"],
        "outcome": "Reported outcome",
        "finding": "",
        "means": [q["text"][:74] for q in mv] or ["(method not detected)"],
        "ends":  [q["text"][:74] for q in ev] or ["(aim not detected)"],
        "verbatims": (ev + mv)[:6],
    }

# -----------------------------------------------------------------------------
# 4. SVG renderer (the card)
# -----------------------------------------------------------------------------
def esc(s): return html.escape(str(s), quote=True)

def wrap(s, width):
    words, lines, cur = s.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= width:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def stick(cx, top):
    return (f'<circle cx="{cx}" cy="{top}" r="9" fill="#fff"/>'
            f'<line x1="{cx}" y1="{top+9}" x2="{cx}" y2="{top+34}"/>'
            f'<line x1="{cx}" y1="{top+16}" x2="{cx-13}" y2="{top+27}"/>'
            f'<line x1="{cx}" y1="{top+16}" x2="{cx+13}" y2="{top+27}"/>'
            f'<line x1="{cx}" y1="{top+34}" x2="{cx-11}" y2="{top+54}"/>'
            f'<line x1="{cx}" y1="{top+34}" x2="{cx+11}" y2="{top+54}"/>')

PUR="#6C2BD9"; RED="#E11D2A"; BLU="#1E14C7"; GRN="#16A86B"; INK="#1c1a17"

def build_svg(F):
    W = 1320
    s = []
    s.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 1160" '
             f'font-family="Verdana,\'Trebuchet MS\',Arial,sans-serif">')
    s.append('<defs>'
             '<marker id="ar" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto">'
             '<path d="M0,0 L7,3 L0,6 Z" fill="#5b5750"/></marker>'
             '<marker id="arb" markerWidth="8" markerHeight="8" refX="5.5" refY="3" orient="auto">'
             '<path d="M0,0 L7,3 L0,6 Z" fill="#16A86B"/></marker>'
             '<style>.m{font-size:13px;fill:#2a2722;}</style></defs>')
    s.append(f'<rect width="{W}" height="1160" fill="#EFF1F4"/>')

    s.append(f'<rect x="40" y="40" width="1240" height="772" rx="6" fill="#FFFDF8" '
             f'stroke="{PUR}" stroke-width="4"/>')

    s.append(f'<text x="68" y="74" font-size="12" font-weight="700" fill="{PUR}" '
             f'letter-spacing="2">RICH PICTURE</text>')
    ty = 102
    for line in wrap(F["title"], 64)[:2]:
        s.append(f'<text x="68" y="{ty}" font-size="21" font-weight="800" fill="{INK}">{esc(line)}</text>')
        ty += 27
    meta_line = " · ".join(x for x in [F.get("authors",""), F.get("year",""), F.get("venue","")] if x)
    s.append(f'<text x="68" y="{ty+2}" font-size="13.5" fill="#6f6a61">{esc(meta_line)}</text>')
    chip = F.get("study_type","")
    cw = 16 + len(chip)*8.2
    s.append(f'<rect x="{1256-cw}" y="60" width="{cw}" height="30" rx="15" fill="#EDE3FB" stroke="{PUR}" stroke-width="1.6"/>')
    s.append(f'<text x="{1256-cw/2}" y="80" text-anchor="middle" font-size="13" font-weight="700" fill="#4a1f9c">{esc(chip)}</text>')
    div_y = ty + 18
    s.append(f'<line x1="64" y1="{div_y}" x2="1256" y2="{div_y}" stroke="#e3ddcf" stroke-width="1.5"/>')

    band_top = div_y + 18
    midy = band_top + 175
    s.append(f'<text x="78" y="{band_top+14}" font-size="13" font-weight="700" fill="#3a3631">WHO</text>')
    figs = min(3, max(1, len(F.get("actors",[]) ) ))
    s.append(f'<g stroke="#3a3631" stroke-width="2.2" fill="none" stroke-linecap="round">')
    for k in range(figs):
        s.append(stick(96 + k*36, band_top+44))
    s.append('</g>')
    ay = band_top+118
    if F.get("sample"):
        s.append(f'<text x="78" y="{ay}" font-size="13" font-weight="700" fill="{PUR}">{esc(F["sample"])}</text>'); ay+=20
    for a in F.get("actors",[])[:3]:
        for wl in wrap(a, 22):
            s.append(f'<text x="78" y="{ay}" class="m">{esc(wl)}</text>'); ay+=18
    s.append(f'<line x1="190" y1="{midy-20}" x2="276" y2="{midy}" stroke="#5b5750" stroke-width="2.2" marker-end="url(#ar)"/>')
    s.append(f'<circle cx="372" cy="{midy}" r="76" fill="#EDE3FB" stroke="{PUR}" stroke-width="3"/>')
    cl = wrap(F.get("central","Core"), 14)[:3]
    cy = midy - (len(cl)-1)*9 - 2
    for line in cl:
        s.append(f'<text x="372" y="{cy}" text-anchor="middle" font-size="14" font-weight="800" fill="#4a1f9c">{esc(line)}</text>'); cy+=18
    s.append(f'<text x="372" y="{midy+58}" text-anchor="middle" font-size="11.5" fill="#6b4fb0">the approach</text>')
    factors = F.get("factors",[])[:6]
    n = max(1,len(factors))
    fx, fw, fh = 560, 250, 44
    gap = 14
    total = n*fh + (n-1)*gap
    fy0 = midy - total/2
    for i, fct in enumerate(factors):
        yy = fy0 + i*(fh+gap)
        s.append(f'<line x1="450" y1="{midy}" x2="{fx}" y2="{yy+fh/2}" stroke="#9a907c" stroke-width="2" marker-end="url(#ar)"/>')
        s.append(f'<rect x="{fx}" y="{yy}" width="{fw}" height="{fh}" rx="8" fill="#fff" stroke="{PUR}" stroke-width="1.8"/>')
        wl = wrap(f"{i+1} · {fct}", 30)[:2]
        ty2 = yy + (24 if len(wl)==1 else 17)
        for j,line in enumerate(wl):
            fwt = "700" if j==0 else "400"
            s.append(f'<text x="{fx+14}" y="{ty2}" class="m" font-weight="{fwt}">{esc(line)}</text>'); ty2+=16
    s.append(f'<line x1="{fx+fw}" y1="{midy}" x2="{fx+fw+110}" y2="{midy}" stroke="{GRN}" stroke-width="3.5" marker-end="url(#arb)"/>')
    ox = fx+fw+185
    s.append(f'<g transform="translate({ox},{midy})">'
             f'<rect x="-70" y="-44" width="140" height="78" fill="#fff" stroke="{GRN}" stroke-width="2.4"/>'
             f'<polygon points="-82,-44 0,-86 82,-44" fill="#d6f0e4" stroke="{GRN}" stroke-width="2.4"/>'
             f'<line x1="-44" y1="-20" x2="44" y2="-20" stroke="{GRN}" stroke-width="1.6"/>'
             f'<line x1="-44" y1="2" x2="44" y2="2" stroke="{GRN}" stroke-width="1.6"/></g>')
    oyt = midy+58
    for line in wrap(F.get("outcome","Outcome"), 20)[:2]:
        s.append(f'<text x="{ox}" y="{oyt}" text-anchor="middle" font-size="13" font-weight="700" fill="#0e6b45">{esc(line)}</text>'); oyt+=18
    if F.get("finding"):
        s.append(f'<g transform="translate({ox-150},{midy-118})">'
                 f'<rect x="0" y="0" width="300" height="32" rx="16" fill="#FFF1C9" stroke="#C9A227" stroke-width="1.6"/>'
                 f'<text x="150" y="21" text-anchor="middle" font-size="12" font-weight="700" fill="#7a5d10">{esc("✓ "+F["finding"])}</text></g>')

    me_y = 612
    s.append(f'<rect x="44" y="{me_y}" width="600" height="156" fill="{RED}"/>')
    s.append(f'<text x="64" y="{me_y+30}" font-size="18" font-weight="800" fill="#fff">Means  (how)</text>')
    yy = me_y+56
    for b in F.get("means",[])[:5]:
        for wl in wrap("• "+b, 60)[:2]:
            s.append(f'<text x="64" y="{yy}" font-size="13" fill="#fff">{esc(wl)}</text>'); yy+=19
    s.append(f'<rect x="646" y="{me_y}" width="630" height="156" fill="{BLU}"/>')
    s.append(f'<text x="666" y="{me_y+30}" font-size="18" font-weight="800" fill="#fff">Ends  (why / for what)</text>')
    yy = me_y+56
    for b in F.get("ends",[])[:5]:
        for wl in wrap("• "+b, 62)[:2]:
            s.append(f'<text x="666" y="{yy}" font-size="13" fill="#fff">{esc(wl)}</text>'); yy+=19

    s.append(f'<rect x="40" y="828" width="1240" height="92" rx="6" fill="{GRN}"/>')
    s.append(f'<text x="64" y="858" font-size="16" font-weight="800" fill="#fff">Paper Info</text>')
    s.append(f'<text x="64" y="884" font-size="13.5" fill="#fff">'
             f'<tspan font-weight="700">Country:</tspan> {esc(F.get("country") or "—")}    '
             f'<tspan font-weight="700">Region:</tspan> {esc(F.get("region") or "—")}    '
             f'<tspan font-weight="700">Type:</tspan> {esc(F.get("study_type") or "—")}</text>')
    s.append(f'<text x="64" y="908" font-size="13.5" fill="#fff">'
             f'<tspan font-weight="700">Sample / Impact:</tspan> {esc(F.get("impact") or F.get("sample") or "—")}</text>')

    vy = 940
    s.append(f'<rect x="40" y="{vy}" width="1240" height="200" rx="6" fill="#FFFDF8" stroke="{PUR}" stroke-width="3"/>')
    s.append(f'<text x="64" y="{vy+28}" font-size="16" font-weight="800" fill="{INK}">Key verbatims '
             f'<tspan font-weight="400" fill="#8a857c">(page · line — for citation)</tspan></text>')
    ry = vy+50
    for q in F.get("verbatims",[])[:5]:
        cite = f'p{q["page"]} · L{q["line"]}'
        s.append(f'<rect x="64" y="{ry-15}" width="92" height="22" rx="6" fill="#EDE3FB" stroke="{PUR}"/>')
        s.append(f'<text x="110" y="{ry+1}" text-anchor="middle" font-size="11.5" font-weight="700" fill="#4a1f9c">{esc(cite)}</text>')
        line = q["text"]
        line = (line[:120] + "…") if len(line) > 121 else line
        s.append(f'<text x="168" y="{ry+1}" font-size="13" fill="#2a2722">{esc("“"+line+"”")}</text>')
        ry += 30
    s.append('</svg>')
    return "\n".join(s)

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    pdf = sys.argv[1]
    override = sys.argv[2] if len(sys.argv) > 2 else None
    pages = pdf_pages(pdf)
    F = {}
    F.update(extract_meta(pages))
    F.update(heuristic_fields(pages, F))
    F.update(extract_meta(pages))
    if override and os.path.exists(override):
        with open(override) as fh:
            F.update(json.load(fh))
    base = os.path.splitext(pdf)[0]
    with open(base + ".theta.json", "w") as fh:
        json.dump(F, fh, indent=2, ensure_ascii=False)
    with open(base + ".theta.svg", "w") as fh:
        fh.write(build_svg(F))
    print("wrote", base + ".theta.svg")

if __name__ == "__main__":
    main()
