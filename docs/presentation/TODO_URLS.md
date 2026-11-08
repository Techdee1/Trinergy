# Placeholders to fill before presenting

Every place a URL is needed in the documents uses the text `TODO-URL`. Replace it with the real address once the services exist. Nothing in this repository deploys anything by itself (web/DEPLOY.md).

| Placeholder | What it should be | Where it appears |
|---|---|---|
| `TODO-URL` (hosted dashboard) | The public address of the static site (planned: Vercel) | `docs/presentation/Demo_Script.md`; `docs/presentation/diagrams/deployment.svg` and `.png`; `docs/presentation/Flow_and_Architecture.pdf` page 23; `submission/docs/REVIEWER_GUIDE.md`; `submission/docs/ARCHITECTURE.md`; `submission/docs/img/deployment.png` |
| `TODO-URL` (hosted API) | The public address of the API (planned: Render) | the same files; also used as the argument of `python web/server/smoke_remote.py TODO-URL` |

Also remember:

- The API's `ALLOWED_ORIGINS` must include the dashboard's exact origin (scheme and host, no trailing slash), or the browser blocks every request (web/DEPLOY.md, web/app/README.md).
- `web/app/.env.production` already holds a default API address for builds. Check that it matches the real API before building.
- A search for `TODO-URL` in `docs/` and `submission/docs/` lists every place to edit:
  `grep -rn "TODO-URL" docs submission/docs`
