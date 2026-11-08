"""Writes the five slide-ready SVG diagrams into ../diagrams/. Run: python docs/presentation/build/diagrams.py"""
from pathlib import Path
from palette import *

OUT = Path(__file__).resolve().parent.parent / "diagrams"
FONT = "Inter, 'Segoe UI', Arial, sans-serif"
MONO = "'JetBrains Mono', Consolas, monospace"


def svg(w, h, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" font-family="{FONT}">'
            f'<title>{title}</title><defs>'
            f'<marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{TEXT2}"/></marker>'
            f'<marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="{BRAND_TEXT}"/></marker>'
            f'</defs><rect width="{w}" height="{h}" fill="{BG}"/>{body}</svg>')


def box(x, y, w, h, title, sub="", color=LINE2, fill=S2, tcolor=TEXT, size=20, subsize=15, mono=False):
    out = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="{fill}" stroke="{color}" stroke-width="2"/>'
    lines = sub.split("\n") if sub else []
    ty = y + (h / 2 - 8 * len(lines) + 2 if lines else h / 2 + 7)
    out += f'<text x="{x + w / 2}" y="{ty}" text-anchor="middle" fill="{tcolor}" font-size="{size}" font-weight="700"{" font-family=%s" % chr(34) + MONO + chr(34) if mono else ""}>{title}</text>'
    for i, ln in enumerate(lines):
        out += f'<text x="{x + w / 2}" y="{ty + 22 + i * 19}" text-anchor="middle" fill="{TEXT2}" font-size="{subsize}">{ln}</text>'
    return out


def arrow(x1, y1, x2, y2, color=TEXT2, label="", lx=None, ly=None, dash=False, marker="a"):
    d = ' stroke-dasharray="7 6"' if dash else ""
    out = f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="2.4" fill="none" marker-end="url(#{marker})"{d}/>'
    if label:
        out += f'<text x="{lx if lx is not None else (x1 + x2) / 2}" y="{ly if ly is not None else (y1 + y2) / 2 - 8}" text-anchor="middle" fill="{color}" font-size="14">{label}</text>'
    return out


def text(x, y, s, size=16, color=TEXT2, weight=400, anchor="start", mono=False):
    f = f' font-family="{MONO}"' if mono else ""
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}"{f}>{s}</text>'


def pipeline():
    b = text(40, 54, "From question to cited answer", 30, TEXT, 800)
    b += text(40, 82, "Code finds the facts. The model only phrases them. A verifier checks every answer. Abstaining is a valid answer.", 16, TEXT2)
    # row 1: build time
    b += text(40, 130, "BUILD ONCE (offline, from the organiser files)", 13, TEXT3, 700)
    b += box(40, 144, 200, 84, "XML + PDF", "32 daily reports\n54 PDF pages", CTX)
    b += box(300, 144, 200, 84, "Parser", "WITSML to records", ROUTE)
    b += box(560, 144, 200, 84, "Page locator", "record to PDF page,\nsection, box", ROUTE)
    b += box(820, 144, 260, 84, "Evidence store", "1,783 records,\neach with a stable ID", OK, S3)
    b += arrow(240, 186, 296, 186) + arrow(500, 186, 556, 186) + arrow(760, 186, 816, 186)
    # row 2: per question
    b += text(40, 282, "PER QUESTION", 13, TEXT3, 700)
    b += box(40, 296, 170, 84, "Question", "any wording", BRAND, S2)
    b += box(250, 296, 190, 84, "Router", "wells, dates, topics\nmode + confidence", ROUTE)
    b += box(480, 296, 210, 84, "Context builder", "evidence lines, window\nnotes, aggregates, ABSENT", ROUTE)
    b += box(730, 296, 190, 84, "Model", "Haiku 5.5, twice\nJSON only", FLAG)
    b += box(960, 296, 190, 84, "Verifier", "13 code checks", OK, S3)
    b += box(1190, 296, 190, 84, "Writer", "predictions.csv\nevidence strings", BRAND)
    for x1, x2 in [(210, 246), (440, 476), (690, 726), (920, 956), (1150, 1186)]:
        b += arrow(x1, 338, x2, 338)
    b += arrow(950, 228, 345, 292, TEXT3, "", None, None, True)
    b += text(760, 276, "per-question steps read the store", 14, TEXT3, 400, "middle")
    # row 3: repair paths
    b += text(40, 450, "WHEN THE VERIFIER OBJECTS", 13, TEXT3, 700)
    b += box(730, 470, 190, 80, "Escalate", "Sonnet 5.5, with the\nverifier message", FLAG)
    b += box(960, 470, 190, 80, "Arbitrate", "when the two Haiku\nruns disagree", FLAG)
    b += box(480, 470, 210, 80, "Second pass", "multi-report only:\nenriched context", ROUTE)
    b += box(1190, 470, 190, 80, "Abstain", "ABSENT record says\nwhat was searched", ABSTAIN)
    b += arrow(1055, 380, 825, 468, ABSTAIN, "fail", 960, 440)
    b += arrow(920, 510, 956, 510, TEXT2)
    b += arrow(605, 468, 605, 384, ROUTE, "retry once", 650, 430, True)
    b += arrow(1285, 384, 1285, 466, ABSTAIN)
    b += text(1275, 426, "no support in the archive", 14, ABSTAIN, 400, "end")
    # row 4: surfaces
    b += text(40, 620, "WHERE THE ANSWER GOES", 13, TEXT3, 700)
    b += box(40, 636, 300, 76, "Notebook", "solution.ipynb, offline by default", OK, S3)
    b += box(380, 636, 300, 76, "Answer cache", "llm_cache.json, same keys every run", OK, S3)
    b += box(720, 636, 300, 76, "Backend API", "FastAPI, traces every stage", ROUTE)
    b += box(1060, 636, 320, 76, "Dashboard", "answer, evidence page, replay, 3D", BRAND)
    b += arrow(680, 674, 716, 674) + arrow(1020, 674, 1056, 674)
    b += arrow(340, 674, 376, 674, TEXT2)
    return svg(1420, 760, b, "End-to-end pipeline")


def trust():
    b = text(10, 28, "The trust layer: nothing reaches predictions.csv unchecked", 22, TEXT, 800)
    b += box(10, 130, 150, 90, "Model reply", "status, answer,\ncited_ids, rationale", FLAG, size=17, subsize=13.5)
    b += box(200, 60, 350, 250, "Verifier: 13 checks in code", "valid JSON, status, answer text\ncitation shape, ID was shown to the model\na citation is required\nabstain cites only ABSENT records\nnumbers, units, dates, times supported\nno false not-found, parts answered\nno missed evidence", OK, S3, size=18, subsize=13.5)
    b += arrow(160, 175, 196, 175)
    items = [("All checks pass", "accept, then repair citations", OK, S3), ("Failed, or abstained with a matching line", "escalate to Sonnet 5.5 with the message", FLAG, S2),
             ("The two Haiku runs disagree", "Sonnet arbitrates, one retry", FLAG, S2), ("Abstain or partial on multi-report", "second pass, enriched context", ROUTE, S2),
             ("No such field in the archive", "abstain and cite the ABSENT record", ABSTAIN, S2)]
    for i, (t, sub, c, f) in enumerate(items):
        y = 44 + i * 60
        b += box(610, y, 330, 52, "", "", c, f)
        b += text(775, y + 22, t, 14.5, TEXT, 700, "middle") + text(775, y + 41, sub, 13, TEXT2, 400, "middle")
        b += arrow(552, 185, 606, y + 26, TEXT3)
    b += box(990, 44, 190, 52, "", "", OK, S3) + text(1085, 66, "Citation repair", 14.5, TEXT, 700, "middle") + text(1085, 85, "adds records the answer uses", 12.5, TEXT2, 400, "middle")
    b += arrow(942, 70, 986, 70)
    b += box(990, 150, 190, 90, "", "", ABSTAIN, S2) + text(1085, 176, "Still failing?", 14.5, TEXT, 700, "middle")
    for i, ln in enumerate(["keep the first answer,", "flag it for review,", "confidence 0.2"]):
        b += text(1085, 197 + i * 17, ln, 13, TEXT2, 400, "middle")
    b += arrow(942, 130, 986, 175, TEXT3) + arrow(942, 190, 986, 200, TEXT3)
    b += text(10, 332, "Confidence is set by rules, never by the model. Source: submission/archive_qa/verify.py", 13, TEXT3, 400, "start")
    return svg(1190, 345, b, "Trust layer")


def evidence_flow():
    nb = "\u00a0"
    b = text(40, 54, "One fact, one ID, one citation", 30, TEXT, 800)
    b += box(40, 100, 420, 200, "", "", CTX, S2)
    b += text(60, 132, "XML (source of truth)", 15, CTX, 700)
    for i, ln in enumerate(['<fluid>', nb * 2 + '<type>NaCl brine</type>', nb * 2 + '<locationSample>Active pit</locationSample>', nb * 2 + '<density uom="g/cm3">1.03</density>', '</fluid>']):
        b += text(60, 164 + i * 24, ln.replace("<", "&lt;").replace(">", "&gt;"), 14, TEXT, 400, "start", True)
    b += box(540, 100, 450, 200, "", "", OK, S3)
    b += text(560, 132, "Evidence record", 15, OK, 700)
    for i, ln in enumerate(["id       F1C-20140326-FLUID-01", "well     15/9-F-1-C", "report   2014-03-26 (D-1 to D)", "field    density = 1.03 g/cm3", "pdf      15_9_F_1_C_2014_03_26.pdf p.1", "section  Drilling Fluid"]):
        b += text(560, 162 + i * 22, ln.replace(" ", nb), 14, TEXT, 400, "start", True)
    b += arrow(462, 200, 536, 200) + text(499, 186, "parser", 13, TEXT3, 400, "middle")
    b += box(1070, 100, 480, 200, "", "", FLAG, S2)
    b += text(1090, 132, "Line the model sees", 15, FLAG, 700)
    b += text(1090, 166, "[F1C-20140326-FLUID-01] fluid |", 13.5, TEXT, 400, "start", True)
    b += text(1090, 190, "density=1.03 g/cm3; type=NaCl brine;", 13.5, TEXT, 400, "start", True)
    b += text(1090, 214, "locationSample=Active pit; md=4094 m", 13.5, TEXT, 400, "start", True)
    b += text(1090, 238, "| report 2014-03-26", 13.5, TEXT, 400, "start", True)
    b += text(1090, 262, "| at 2014-03-25T21:00:00", 13.5, TEXT, 400, "start", True)
    b += arrow(992, 200, 1066, 200) + text(1029, 186, "context", 13, TEXT3, 400, "middle")
    b += box(40, 380, 440, 120, "Model answers", "1.03 g/cm3\ncited_ids: F1C-20140326-FLUID-01", FLAG)
    b += box(560, 380, 440, 120, "Verifier", "1.03 is in the cited record\nthe ID was in the context", OK, S3)
    b += box(1080, 380, 470, 120, "Writer builds the evidence string", "from the store, never from model text", BRAND)
    b += arrow(482, 440, 556, 440) + arrow(1002, 440, 1076, 440)
    b += text(1310, 340, "The model may cite only IDs it was shown.", 15, FLAG, 400, "middle")
    b += arrow(1310, 302, 1310, 326, FLAG)
    b += box(40, 580, 1510, 160, "", "", BRAND, S1)
    b += text(70, 618, "predictions.csv, evidence column", 15, BRAND_TEXT, 700)
    b += text(70, 652, "15_9_F_1_C_2014_03_26.pdf p.1 (Drilling Fluid); 15_9_F_1_C_2014_03_26.xml F1C-20140326-FLUID-01", 17, TEXT, 400, "start", True)
    b += text(70, 688, "A reviewer opens the PDF at page 1, finds the Drilling Fluid table, and opens the XML at the same ID.", 16, TEXT2)
    b += text(70, 716, "If the PDF never prints a value (for example tightWell), the evidence cites the XML only and says so.", 16, TEXT2)
    b += arrow(1315, 502, 1315, 576, TEXT3)
    return svg(1590, 770, b, "Evidence record and citation flow")


def date_window():
    b = text(40, 54, "The date-window trap: report D covers D-1 to D", 30, TEXT, 800)
    b += text(40, 84, "Example: question T2-016 asks about the sample on 2014-03-26. The sample is stamped 2014-03-25 at 21:00.", 16, TEXT2)
    # timeline
    x0, x1, y = 120, 1360, 300
    b += f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{LINE2}" stroke-width="3"/>'
    b += f'<rect x="{x0 + 300}" y="{y - 60}" width="{600}" height="120" rx="10" fill="{OK}" fill-opacity="0.10" stroke="{OK}" stroke-width="2"/>'
    b += text(x0 + 600, y - 72, "Report dated 2014-03-26 covers this window", 17, OK, 700, "middle")
    for xx, lab, sub in [(x0 + 300, "2014-03-25", "00:00"), (x0 + 900, "2014-03-26", "00:00")]:
        b += f'<line x1="{xx}" y1="{y - 76}" x2="{xx}" y2="{y + 76}" stroke="{OK}" stroke-width="3"/>'
        b += text(xx, y + 104, lab, 17, TEXT, 700, "middle") + text(xx, y + 126, sub, 15, TEXT2, 400, "middle")
    sx = x0 + 300 + 600 * 21 / 24
    b += f'<circle cx="{sx}" cy="{y}" r="12" fill="{FLAG}"/>'
    b += text(sx, y - 24, "NaCl brine sample", 16, FLAG, 700, "middle") + text(sx, y + 38, "2014-03-25 21:00", 15, TEXT, 400, "middle")
    b += box(120, 440, 560, 200, "", "", ABSTAIN, S2)
    b += text(144, 476, "What goes wrong", 18, ABSTAIN, 700)
    for i, ln in enumerate(["The question says 2014-03-26.", "The record says 2014-03-25T21:00.", "Large models read that as a mismatch and abstain.", "In the benchmark, date-window cases scored 12 percent overall."]):
        b += text(144, 510 + i * 28, ln, 16, TEXT)
    b += box(760, 440, 600, 200, "", "", OK, S3)
    b += text(784, 476, "What the pipeline does", 18, OK, 700)
    for i, ln in enumerate(["Each record carries its report window.", "When a question names a clock time and a date, a", "WINDOW NOTE says: the D-1 timestamp belongs to report D.", "The verifier accepts dates found in the cited record's window."]):
        b += text(784, 510 + i * 28, ln, 16, TEXT)
    b += text(40, 700, "Sources: submission/DATA_NOTES.md (Dates), submission/archive_qa/context.py (window_note), tools/llm_bench/RECOMMENDATION.md (local benchmark notes)", 13, TEXT3, 400, "start", True)
    return svg(1480, 740, b, "Date window trap")


def deployment():
    b = text(20, 34, "Deployment topology", 24, TEXT, 800)
    b += text(20, 58, "The repository deploys nothing by itself. Hosted URLs are placeholders (TODO-URL). See web/DEPLOY.md.", 14.5, TEXT2)
    b += box(20, 90, 210, 110, "Browser", "presenter, judge\nor engineer", CTX, size=22, subsize=16)
    b += box(300, 90, 250, 110, "Static site", "React + three.js\nVercel (TODO-URL)", BRAND, size=22, subsize=16)
    b += box(640, 90, 280, 110, "API", "FastAPI, one worker\nRender (TODO-URL)", ROUTE, size=22, subsize=16)
    b += box(1010, 90, 160, 110, "OpenRouter", "holds the only\nkey", FLAG, size=20, subsize=16)
    b += arrow(230, 145, 296, 145, TEXT2, "load", 263, 132) + arrow(550, 145, 636, 145, TEXT2, "HTTPS", 593, 132) + arrow(920, 145, 1006, 145, FLAG, "uncached", 963, 132)
    b += box(20, 240, 210, 150, "Security", "key only on API host\nnever returned or logged\nCORS allow-list\n$3 limit on the key", OK, S1, size=18, subsize=14.5)
    b += box(300, 240, 250, 150, "Offline fallback", "same API on the laptop\nvite preview, ?api=localhost\nnotebook, no key, 10 s\n72 questions from cache", ABSTAIN, S1, size=18, subsize=14.5)
    b += box(640, 240, 280, 150, "Inside the API", "frozen pipeline\ndata pack 7.5 MB\ncaches: committed, unseen, runtime\nguards: limits, budget, timeout", ROUTE, S1, size=18, subsize=14.5)
    b += arrow(780, 202, 780, 236, ROUTE)
    b += text(20, 424, "Sources: web/DEPLOY.md, web/render.yaml, web/server/API.md, web/app/README.md", 13, TEXT3, 400, "start", True)
    return svg(1190, 440, b, "Deployment topology")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in [("pipeline", pipeline), ("trust_layer", trust), ("evidence_citation_flow", evidence_flow),
                     ("date_window", date_window), ("deployment", deployment)]:
        (OUT / f"{name}.svg").write_text(fn(), encoding="utf-8")
        print("wrote", name)
