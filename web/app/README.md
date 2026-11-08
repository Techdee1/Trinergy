# Intelligent Well Archive: web app

Team Trinergy, NAPE AICE 2026, Track 2. Built for Heirs Energies. Data: Equinor Volve dataset.
A React + TypeScript app (Vite) over the tested backend in [../server](../server/API.md). Everything on screen comes from the real API. Fonts, icons and
libraries are bundled, and the only run-time network calls go to the API.

## Configuration: which API the app talks to

The API base URL is resolved once at start-up, first match wins:

| Order | Source | Use it for |
|---|---|---|
| 1 | `?api=<url>` in the address bar (before or after the `#`), e.g. `…/index.html?api=http://localhost:8000` | quick switching during a demo. Kept for the tab; `?api=default` clears it |
| 2 | `dist/config.js`: `window.__WELL_ARCHIVE_CONFIG__ = { apiUrl: 'https://…' }` | pointing a built `dist/` at another backend without rebuilding |
| 3 | `VITE_API_URL` at build time | `.env.production` (committed) sets `https://well-archive-api.onrender.com` for `npm run build` and Vercel; `.env.local` (git-ignored) for local overrides; see `.env.example` |
| 4 | `http://localhost:8000` | dev server with no env file |

The active URL and where it came from are shown in the footer (`API … · set by ?api=`). Only `http(s)` URLs are accepted.
**All of these values are public** (they ship to every browser). Never put a key or token in them: the OpenRouter key lives only on the API server.
`.env`, `.env.local` and `.env.*.local` are git-ignored.

**CORS:** the API only accepts browser origins listed in its `ALLOWED_ORIGINS` (default `http://localhost:3000,http://localhost:5173`). Whatever origin serves the
site must be in that list. Opening `dist/index.html` straight from disk (`file://`) is blocked by the browser, so always serve it over http.

## Run: local demo

```bash
# 1. API (repo root)
conda activate nape
uvicorn web.server.app:app --port 8000

# 2a. dev server (from web/app): uses http://localhost:8000 by default
npm install
npm run dev                                   # http://localhost:5173

# 2b. or the committed build, pointed at the local API
npx vite preview --port 5173                  # serves dist/ (its build default is the hosted API)
#    open http://localhost:5173/?api=http://localhost:8000
```

`dist/` uses relative asset paths and hash routing (`#/mission/T2-017`), so any static server works, on any sub-path, with no rewrite rules.

## Run: hosted

1. **API on Render**: deployed from `web/server` (see `web/DEPLOY.md`), public URL `https://well-archive-api.onrender.com`.
2. **Site on Vercel**: import the repo, root directory `web/app`, build command `npm run build`, output directory `dist`. Set the environment variable
   `VITE_API_URL=https://well-archive-api.onrender.com` (already the default in `.env.production`, so this is optional unless the API moves).
3. **Allow the site's origin on the API**: in the Render dashboard, set `ALLOWED_ORIGINS` on the API service to include the Vercel URL, for example
   `ALLOWED_ORIGINS=https://well-archive.vercel.app,http://localhost:5173,http://localhost:3000` (exact origin: scheme and host, no trailing slash, no path),
   then redeploy. Without this step the browser blocks every request and the site stays on "Waking the archive server".
4. The free Render plan sleeps when idle: the first visit can take up to a minute, and the site shows a designed waiting state meanwhile.

## Build

```bash
npm run build          # type-checks, then writes web/app/dist (committed), using .env.production
```

## Verify

```bash
npx playwright install chromium     # once
BASE='http://localhost:5173/?api=http://localhost:8000' node tests/shots.mjs   # dist build, local API
node tests/shots3d.mjs                                                     # dev server on :3000 (npx vite --port 3000)
```

`tests/shots.mjs` runs against the live API. It renders every view in both themes at 1920x1080 and 1366x768, runs the replay for an answered, a
multi-report, an archive-wide and an abstained question, reaches every Ask state, fails on any console error, and writes screenshots to `screenshots/`.
Real states are hit for real (clarification, early abstain, answered, abstain, a real 429). Four states need server configuration we do not change
(live mode off, budget reached, NOT EVALUATED, a server that is asleep), so they use mocked responses built from real payloads; those screenshots are named
accordingly in the test output. The run asks about ten live questions on the free (no model call) or cached path, so mind the server's
rate limit (6 a minute, 40 a day per IP).

## Views

| Route | What it is |
|---|---|
| `#/` | Overview: live counters, the four principles, entry to the replay |
| `#/mission/:id` | Mission control: question picker and the 2D replay (3D slot behind a toggle) |
| `#/questions` | Results board for all 72 questions, filter by set, mode, status |
| `#/question/:id` | Answer view: answer, confidence rule, evidence lens (PDF page with highlight boxes), trace timeline |
| `#/generalisation` | The 40 unseen questions by category, baseline vs current, with the honest caveat |
| `#/impact` | Impact for Heirs: problem, use cases, deployment, roadmap, illustrative calculator |
| `#/archive` | Timeline of the 32 reports by wellbore, record counts |
| `#/cost` | Cost per question, model mix, cache, budget |
| `#/ask` | Ask your own question with a live trace and designed error states |
| `#/present` | Presenter mode (guided tour) |
| `#/styleguide` | Design tokens and components |

## Design system

Tokens live in [src/styles/tokens.css](src/styles/tokens.css) (colour, type, 8 pt space, radius family, motion) with dark and light themes.
Brand colours come from heirsenergies.com: site CSS `#FE0000` and `#E61100`, and Pillow extraction from the logo and favicon (dominant `#F80000`).
Heirs red marks the primary action, the active selection and the playhead only. Status has its own colours, each with an icon and a label:
verified = green, abstain = amber, router-selected = blue, flag = violet, context = neutral. Red never means failure. The Heirs logo is not used
and this is not presented as an official Heirs product.

## 3-minute demo script

1. **Overview (30 s).** "Ask the archive. Get the evidence, or an honest 'not here'." Point at the live counters: 72 questions, 32 reports, 1,783 records,
   all verified, about 2 cents a question. Name the four rules: code finds the facts, AI only phrases, a verifier checks, abstention is valid.
2. **Date-window trap (40 s).** Press *Watch it work* on T2-016 (or step 2 of Presenter mode). A report dated D covers D-1 to D. Watch the question parse,
   one report open, the verifier tick through, and the answer resolve with its confidence rule.
3. **Abstention (40 s).** T2-032, "Western Atlas". The sweep passes over the opened report and finds nothing. The ABSENT result names what was searched and what
   looked close but was rejected. Open the evidence lens: an elegant "nothing to show" state, not a made-up citation.
4. **Multi-report (30 s).** T2-017. Four reports across four wells. The first draft cited a number the records did not support, the verifier flagged it (violet),
   a larger model escalated. Show that the escalation is visible in the stepper.
5. **Evidence (20 s).** Open any answer, then the evidence lens: the real PDF page, the highlight on the row, zoom. An XML-only record shows the "in the XML, not on the page" state.
6. **Try your own (20 s).** Ask page: click a suggestion, or type. Show a vague question ("What happened?") and the three clickable examples.

Closing line: cost page (Haiku does 80% of calls for 13% of cost) and the Generalisation caveat: tuned on these questions, independent test in progress.

## Presenter mode

Open from the rail (**Presenter mode**) or `#/present`. Type scale is enlarged, the rail is hidden, everything works offline.

| Key | Action |
|---|---|
| `→` / `←` (or PageDown / PageUp) | next / previous step |
| `1` to `5` | jump to a step |
| `Space` | play / pause the replay |
| `R` | replay from the start |
| `S` | cycle speed 0.5x, 1x, 2x, 4x |
| `,` / `.` | step the replay back / forward |
| `H` | hide or show the cursor |
| `Esc` | exit |

The same replay keys (`Space`, `←`, `→`, `R`, `S`) work in Mission control. In the 3D view `F` toggles Focus; `[` collapses the sidebar.

## 3D view (Mission control, and story (c) in Presenter mode)

Behind the 2D/3D toggle; 2D is the default and the fallback (automatic on WebGL failure or sustained frame rate under 20 fps, with a quiet notice).
Plain three.js, lazy-loaded (`src/three/`, about 141 kB gzip, nothing fetched). Verify with `node tests/shots3d.mjs` (needs the dev server on port 3000).

- **Real:** well path shapes (minimum curvature from the survey stations in `/trajectories`), TVD values and the TVD scale, station MDs, the 6 reports
  that carry their own survey stations (placed at that day's deepest station, solid sphere), every stage, record count, cited ID and ABSENT result (from the trace).
- **Schematic:** the platform template ring and the 15/9-19 offset (absolute coordinates are not in the data), the dashed line from each wellhead
  to its first surveyed station, the 1,500 m dashed line for 15/9-F-1 (no azimuth) and 15/9-F-12 (no survey), and the position of the 26 reports
  with no depth in the data (flat ring, spread in date order along the path). The legend and the on-screen note say so.
- **Focus** (`F`, or the button top right of the 3D view) gives the scene the full width and nearly the full height; the stage list and side panel
  give way to a compact card (current stage, counts, answer and confidence). On by default below 1600 px wide; the choice is remembered.
- The left sidebar collapses to icons with the button next to the logo, or `[`. Remembered across visits.
- Mouse: drag to orbit, scroll to zoom, right-drag to pan, hover a report or well, click a report to list its records in the side panel. *Reset view*
  returns to the choreographed camera. The replay keys are the same as 2D.

## Code map

- [src/lib/adapter.ts](src/lib/adapter.ts): the shared data adapter (replay timeline, derived state, world with trajectories). The 2D replay and the 3D scene both use it.
- [src/lib/useReplay.ts](src/lib/useReplay.ts): playback. Visible state is a pure function of the stage index.
- [src/components/Replay2D.tsx](src/components/Replay2D.tsx): the lanes, stepper, now card and answer card.
- [src/components/EvidenceLens.tsx](src/components/EvidenceLens.tsx), [TraceTimeline.tsx](src/components/TraceTimeline.tsx): evidence and trace.
- [src/api/client.ts](src/api/client.ts): typed client including the `/ask/stream` SSE reader.
- [3D_BRIEF.md](3D_BRIEF.md): brief for the 3D session. [src/three/MissionControl3D.tsx](src/three/MissionControl3D.tsx) is the slot.
