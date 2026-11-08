"""Builds build/qa.html (for QA_Prep.pdf) and ../QA_Drill.md from qa_data.py."""
import html
from pathlib import Path
import qa_data
from qa_data import QA

HERE = Path(__file__).resolve().parent
NM = HERE.parents[2] / "web/app/node_modules/@fontsource-variable"
css = (HERE / "style.css").read_text()
css = css.replace("FONT_INTER", (NM / "inter/files/inter-latin-wght-normal.woff2").as_uri()).replace("FONT_MONO", (NM / "jetbrains-mono/files/jetbrains-mono-latin-wght-normal.woff2").as_uri())
WHO = {"AIE": "AI engineer", "PD": "Product designer", "PE": "Petroleum engineer"}
WCLS = {"AIE": "flag", "PD": "brand", "PE": "ok"}
extra = """@page{size:794px 1123px;margin:38px 44px;background:#0e0c0b}
.page{background:var(--bg)}
.group{break-before:page;page-break-before:always}
.first{break-before:auto}
.page h1{font-size:30px}
.qa{break-inside:avoid;margin-bottom:12px}
.qa .q{font-style:normal;font-weight:700;font-size:15.5px;color:var(--text);margin:6px 0 5px}
.qa p{font-size:13.5px;margin:0 0 5px;line-height:1.42}
.push{color:var(--t2)}
.nd{border-left:3px solid var(--abs);padding:4px 10px;background:rgba(242,181,68,.09);font-size:12.5px;color:var(--text);border-radius:0 8px 8px 0;margin-top:5px;line-height:1.4}
.gh{font-size:22px;font-weight:800;margin:6px 0 10px;letter-spacing:-.02em;border-bottom:2px solid var(--brandfill);padding-bottom:6px}
.legend span{margin-right:8px}
"""
def card(i, x):
    nd = f'<div class="nd"><b>We have not done this yet.</b> Best way to say it: {html.escape(x["nd"])}</div>' if x["nd"] else ""
    return (f'<div class="card qa"><span class="tag {WCLS[x["who"]]}">{WHO[x["who"]]}</span><span class="tag">Q{i}</span>'
            f'{"<span class=tag&#32;abs>honest gap</span>" if x["nd"] else ""}'
            f'<div class="q">{html.escape(x["q"])}</div><p>{html.escape(x["a"])}</p>'
            f'<p class="push"><b>If they push:</b> {html.escape(x["push"])}</p>{nd}</div>')
body = f"""<div class="kick">Q&amp;A preparation pack</div><h1>Intelligent Well Archive: 56 likely questions</h1>
<p class="muted">Each answer is written to be spoken in about 20 to 30 seconds (35 to 72 words, calm pace). The line after it is the follow-up if they push. A yellow box marks an honest "we have not done that yet", with the best way to say it.</p>
<div class="card"><h2>How to use this</h2><ul><li>Presenters: AI engineer (<span class="tag flag">AI engineer</span>), product designer (<span class="tag brand">Product designer</span>), petroleum engineer (<span class="tag ok">Petroleum engineer</span>). The tag is the best person to answer. Confirm the roles with the team [VERIFY].</li>
<li>Numbers come from repository files. Page 25 of Flow_and_Architecture.pdf lists each number with its source.</li>
<li>Never claim more than the pack does: the 40 of 40 on unseen questions was tuned on those questions. The engineer's hand check and an independent test are pending.</li>
<li>For practice, use QA_Drill.md: one question per block.</li></ul></div>
<div class="card" style="margin-top:12px"><h2>Contents</h2><table><tr><th>Group</th><th class="n">Questions</th></tr>""" + "".join(
    f'<tr><td>{g}</td><td class="n">{sum(1 for x in QA if x["group"] == g)}</td></tr>' for g in ["Technical", "Business", "Skeptical", "Process"]) + f"""<tr><td><b>Honest gaps marked</b></td><td class="n">{sum(1 for x in QA if x["nd"])}</td></tr></table></div>"""
for g in ["Technical", "Business", "Skeptical", "Process"]:
    items = [(i, x) for i, x in enumerate(QA, 1) if x["group"] == g]
    body += f'<div class="group"><div class="gh">{g} questions</div>'
    for i, x in items:
        body += card(i, x)
    body += "</div>"
(HERE / "qa.html").write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Q&A preparation pack</title><style>{css}{extra}</style></head><body><div class="page">{body}</div></body></html>', encoding="utf-8")

md = ["# Q&A drill", "", "One question per block. Read the question aloud, answer in 20 to 30 seconds, then check yourself against the model answer. Then try the follow-up.", "",
      "Tags: AI engineer, Product designer, Petroleum engineer. A line starting with **Honest gap** means the true answer is \"we have not done that yet\".", ""]
for i, x in enumerate(QA, 1):
    md += [f"## Q{i}. {x['q']}", "", f"**Best presenter:** {WHO[x['who']]}  |  **Group:** {x['group']}", "", "**Say it aloud first. Then check yourself:**", "", f"> {x['a']}", "",
           f"**If they push:** {x['push']}", ""]
    if x["nd"]:
        md += [f"**Honest gap.** Best way to say it: {x['nd']}", ""]
    md += ["---", ""]
(HERE.parent / "QA_Drill.md").write_text("\n".join(md), encoding="utf-8")
print(len(QA), "questions")
