# UI demo plan: the dashboard part of the live demo

Team Trinergy, NAPE AICE 2026, Track 2. Length: **3 minutes 30 seconds**.
It follows the 1 minute 30 second notebook run, which is written in `docs/presentation/Demo_Script.md`. This file does not repeat that script.
Hosted address: TODO-URL. Figures below were read from the live API on 2026-11-08 and can be re-checked on the Questions page.

## Roles

- Roles follow `docs/presentation/Demo_Script.md`: **PD** (product designer) has the keyboard and mouse and speaks the dashboard lines. **PE** (petroleum engineer) speaks the evidence lines, marked **[PE]** below, at the evidence lens (1:00 to 1:20) and at the abstention evidence (1:54).
- If one person does everything, read the "Words" column while doing the "Driver" column. In the tables, "Narrator" means PD unless marked [PE].
- Say the words as written. They are short on purpose. Do not add numbers that are not on the screen.

## The one choice to make before you start

The full version runs in the **normal views** (rail collapsed, browser zoom up), not in Presenter mode. Reason: the evidence lens lives on the Answer view, and the Answer view is outside the Presenter tour.
Presenter mode is the right choice for the **60-second version** at the end of this file, and as a fallback if the normal views misbehave.

## Timing at a glance

| Clock | Part | Length |
|---|---|---|
| 0:00 | Overview and the four rules | 20 s |
| 0:20 | T2-016 in Mission control, then the evidence lens (the date-window trap) | 60 s |
| 1:20 | T2-032 abstention (the Western Atlas trap) | 45 s |
| 2:05 | T2-017 multi-report with escalation | 60 s |
| 3:05 | Ask box, one question from a judge | 15 s |
| 3:20 | Hand back to the closing slides | 10 s |
| 3:30 | End | |

The replay runs at 1x. At 1x a six-stage question takes about 16 seconds and the nine-stage T2-017 about 24 seconds. Pause with **Space** wherever the table says so, talk, then press **Space** again.

## Minute by minute

### 0:00 to 0:20, Overview and the four rules (20 s)

| | |
|---|---|
| **Cue in** | The notebook run ends with the line in Demo_Script.md: "That was the engine. Now the way people will actually use it." The laptop passes to PD, who says: "This is the same pipeline behind an API. Every screen is real data." |
| **Driver** | Switch to the browser tab (Alt+Tab or Ctrl+Tab). It is already on the Overview (`#/`). Wait one second for the counters. At 0:08 scroll down with the mouse wheel until "Four rules the system never breaks" fills the screen. |
| **Words** | "Ask the archive. Get the evidence, or an honest 'not here'. Seventy-two questions, thirty-two reports, every answer cites its page. Four rules: code finds the facts. AI only phrases them. A verifier checks every claim. And abstaining is a valid answer." |
| **Cue out** | Narrator: "Let me show that on one question." Driver: scroll back up, press the red **Watch it work** button, or open the bookmark `#/mission/T2-016`. |

### 0:20 to 1:20, T2-016, the date-window trap, and the evidence lens (60 s)

| Clock | Driver | Words |
|---|---|---|
| 0:20 | Bookmark `#/mission/T2-016`. The replay starts by itself. | "What was the density of the brine sampled from the active pit on well F-1 C on 26 March 2014?" |
| 0:28 | Press **Space** to pause at the stage "Pick the reports" (pill 2). | "The router is code, not a model. It opens one report out of thirty-two. A daily report dated D covers D minus one to D, so it opens exactly the 26 March report. The sample was taken the evening before, and that is inside the report." |
| 0:42 | Press **Space** to resume. Let it run through "Gather the evidence" and "Draft the answer". | "Only that report's records go to a small model. It phrases an answer and cites a record." |
| 0:50 | At "Verify every claim" the checks tick in. Pause with **Space** if they are too fast to follow. | "Then code checks every claim: the citation exists, the number appears in it, the unit and the date match." |
| 0:56 | The last stage resolves. | "One point zero three grams per cubic centimetre. Confidence zero point nine five, set by a written rule, never by the model." |
| 1:00 | Click **Open evidence and full trace** in the answer card. On the Answer view scroll down past "Evidence lens" until the red box is in the middle of the screen (about four wheel clicks). | **[PE]** "And here is the proof. This is the real page of the original report. The red box is that value, in the drilling fluid table, page one." |
| 1:16 | Hold. Do not scroll. | "Answer, page, line. That is what a reviewer needs." |
| **Cue out** | | Narrator: "Now what happens when the archive does not have the answer." Driver: bookmark `#/mission/T2-032`. |

Check before you say it: T2-016 answered `1.03 g/cm3`, confidence `0.95`, one cited record `F1C-20140326-FLUID-01`.

### 1:20 to 2:05, T2-032, the abstention (45 s)

| Clock | Driver | Words |
|---|---|---|
| 1:20 | Bookmark `#/mission/T2-032`. Press **Space** at once, then click the pill **Gather the evidence**. The sweep runs for about a second. | "Which mud logging company and which engineer recorded the gas readings on well 19 A on 29 August 1997?" |
| 1:32 | Point at the amber report node and the amber card on the right. | "The router opened the one report. Nothing in it is a mud logging field. The system sweeps the report and finds nothing." |
| 1:42 | Click the pill **Resolve** (the last one). | "There is a company in that report called Western Atlas. It ran a wireline logging tool, not mud logging. A weaker system would answer with it. This one rejects it, and says why." |
| 1:54 | Click **Open evidence and full trace**. The evidence lens shows "Nothing to show: this is what was searched" with the rejected items. Hold. | **[PE]** "Confidence zero point eight five: an abstention, backed by a record of what was searched. Saying 'not in the archive' is a correct answer." |
| **Cue out** | | Narrator: "Now a harder one: four reports, four wells." Driver: bookmark `#/mission/T2-017`. |

If you prefer a simpler abstention, use T2-031 (the cost of replacement parts). Say: "There is no cost field anywhere in these reports, so the system says so."

### 2:05 to 3:05, T2-017, multi-report with escalation (60 s)

Stay in 2D unless the real-laptop frame-rate test (checklist) passed. 3D is optional and adds no time.

| Clock | Driver | Words |
|---|---|---|
| 2:05 | Bookmark `#/mission/T2-017`. It plays. | "During the October 2016 plug and abandonment campaign, in what order did the rig move between wells?" |
| 2:12 | Press **Space** at "Pick the reports". Point at the four lit nodes in four different lanes. | "Four reports, across four wells, picked by date range. The model has to read them in order." |
| 2:24 | Press **Space** to resume. At "Verify every claim 1" press **Space** again. Point at the violet flagged check. | "The first draft cited a number the records did not support. The verifier flagged it. Violet, not red: it is a finding, not a crash." |
| 2:40 | Press **Space**. The stage "Escalate" appears. Let it run to the end. | "So a larger model took over with the same evidence, and it passed. The escalation is visible and explained, not hidden." |
| 2:56 | The last stage resolves. | "Ten cited records, confidence zero point seven: lower, because more records mean more that can go wrong." |
| 3:02 | Optional, only if the 3D test passed: click **3D**. Step with the left arrow to "Draft the answer 1". | "The same run in 3D: the real wells in their surveyed paths, and the search moving through the archive." |
| **Cue out** | | Narrator: "Judges, give me a question." Driver: press `[` is not needed. Click **Ask** in the rail, or the bookmark `#/ask`. |

Check before you say it: T2-017 is answered, confidence `0.70`, flag `escalated`, 9 stages, 10 cited records.

### 3:05 to 3:20, the Ask box, one judge-invited question (15 s)

| Clock | Driver | Words |
|---|---|---|
| 3:05 | Click the question box. Type or paste the judge's question. Press **Ctrl+Enter** (or **Cmd+Enter**). | "Type anything about these wells." |
| 3:10 | The stages appear live. Wait for the answer. | "You can see each stage as it happens." |
| 3:18 | Do not open the trace. | Read the answer or the result aloud: the figure and its page, or "not in the archive". |

What can come back, and the sentence to say:

| Result | Say |
|---|---|
| An answer | "Answer, and the page it came from." |
| Abstain | "Not in the archive. It says so and shows what it searched." |
| Needs clarification (a vague question) | "It asks instead of guessing. Three real examples to click." |
| NOT EVALUATED | "A brand new question, and live mode is off here. It does not guess." |

Keep one safe question ready in case no judge speaks. Use the suggestion chip **Answered**, or paste the T2-016 question.

### 3:20 to 3:30, hand back (10 s)

Narrator: "That is the dashboard. Every answer has its proof, and when there is no answer, it says so. Back to the slides for results and what this could mean for Heirs."
Driver: switch to the slides (Alt+Tab) and advance to the results slide.

## Pre-demo checklist

Do these in order, 10 minutes before.

1. **Warm the server.** Open `https://well-archive-api.onrender.com/health` in a tab. It should show `"status":"ok"` within a minute. The hosted free tier sleeps when idle.
2. **Open the site** at TODO-URL. Look at the footer: it should say `API well-archive-api.onrender.com`.
3. **Bookmarks** in one folder, in this order: `#/` (Overview), `#/mission/T2-016`, `#/mission/T2-032`, `#/mission/T2-017`, `#/ask`.
4. **Theme:** dark (the default). Use the sun or moon button at the bottom of the rail to check.
5. **Zoom level:** press Ctrl and plus until the type reads from the back of the room (125% is a good start). [VERIFY on the room's projector.] Press **F11** for full screen.
6. **Rail:** press `[` to collapse the left rail for more room. It is remembered.
7. **Presenter mode:** open `#/present` once and press Esc, to confirm it loads. Leave it off for the full version.
8. **3D toggle default:** leave it on 2D. Test 3D on this laptop: open `#/mission/T2-017`, click 3D, let it play once at 1x. If it is smooth, 3D is allowed for the demo. If it stutters or flips back to 2D by itself with a notice, stay in 2D. Frame rate on a real laptop has not been measured. [VERIFY]
9. **Ask test:** send one cached question, for example the T2-016 question, to confirm the box works. The limit is 6 questions a minute, so do not send more than two.
10. **Quiet the machine:** do not disturb on, notifications off, other tabs closed, charger plugged in, mouse pointer visible.
11. **Backup running:** in two terminals start the local server (see the table below). Keep a third tab on `http://localhost:5173/?api=http://localhost:8000#/`.

## If it fails

| What happens | Recovery step | The one sentence to say |
|---|---|---|
| **Server asleep** (page says "Waking the archive server") | Wait up to 60 seconds. If it is still waiting after 75 seconds, click **Try again**. If it is not up after two minutes, switch to the local tab and carry on. | "The free hosting sleeps when idle. It will be up in a moment." |
| **Wi-Fi down** | Switch to the backup tab `http://localhost:5173/?api=http://localhost:8000#/`. It needs no network. The two commands: `conda activate nape && uvicorn web.server.app:app --port 8000` (repo root) and `npx vite preview --port 5173 --strictPort` (in `web/app`). | "No network needed. Everything runs from the data pack on this laptop." |
| **3D is slow, blank, or fell back to 2D** | Press **2D** at the top right (or do nothing if it already fell back). Carry on with 2D. | "Same run, in 2D." |
| **Ask is rate limited** (amber card with a countdown) | Do not retry. Click **Questions** in the rail, open any row, and show its answer view. | "To keep the demo available for everyone it allows a few questions a minute. Here is one it already answered." |
| **Ask returns NOT EVALUATED** | Leave it. It is a correct state. Then click the suggestion chip **Answered**. | "Live mode is off here, so it will not guess. A question already in the archive replays in full." |
| **Replay is stuck or odd** | Press **R** to replay, or click a stage pill to jump. | "Let me replay that stage." |
| **Page is blank** | Press Ctrl+Shift+R. If still blank, open the local backup tab. | "One second, I will switch to the local copy." |

## The 60-second version (when time is tight)

Use Presenter mode. Driver opens `#/present?step=1` before the talk.

| Clock | Driver | Words |
|---|---|---|
| 0:00 | Presenter step 2 (T2-016) is on screen. Press **S** until the speed reads 2x, so the replay takes about 8 seconds. | "Every answer, with its proof. The router opens one report out of thirty-two, code checks every claim, and the answer is one point zero three, confidence zero point nine five." |
| 0:20 | Press **→** to step 3 (T2-032). Press **S** for 2x. Press **Space** at the sweep stage ("Gather the evidence"). | "When the archive does not have the answer, it says so. It searched one report, found no mud logging field, and rejected a company that only ran a wireline tool." |
| 0:40 | Press **→** to step 4 (T2-017). Press **Space** to pause at the violet flagged check. | "And when its own checks disagree, it escalates, visibly. The first draft cited a number the records did not support." |
| 0:55 | Press **Esc** to leave. | "That is the dashboard. Back to the slides." |

If there are only 30 seconds, show step 3 (the abstention) only. It is the most memorable.

## After the demo

- Press **Esc** if in Presenter mode, and press `[` to restore the rail if you will take questions on other views.
- The Cost page (`#/cost`) answers "how much did this cost": a small model makes 80% of the calls and about 13% of the cost.
- The Generalisation page answers "does it work on questions it has not seen", with its honest caveat: tuned on these questions, independent test in progress.
