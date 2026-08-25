# Deploying MANTIS

Three artifacts go to the judges: **the repo**, **the document**, **the
prototype URL**. This file is the runbook for the third.

---

## The short version

`web/dist` is a **self-contained static site**. It carries frozen copies of every
API response and replays the committed authorisation feed on a client-side
timer, so it works with no backend at all. Deploying the prototype is therefore
uploading one folder — no Python host, no cold start, nothing to keep awake.

```bash
make submission     # ood -> feed -> docx -> static -> web
# then upload web/dist to any static host
```

Hosting the API as well is **optional** and upgrades the demo from an offline
replay to a real SSE stream. The console detects which it has and says so on
screen.

---

## Option A — static only (recommended for the deadline)

The fewest moving parts and nothing that can be asleep when a judge clicks.

### Vercel

1. `npm i -g vercel` (or use the dashboard).
2. From the repo root:
   ```bash
   make static && cd web && npm run build
   vercel deploy --prod ./dist
   ```
3. Or, in the dashboard: **Add New → Project → import the GitHub repo**, then set
   - Root Directory: `web`
   - Build Command: `npm run build`
   - Output Directory: `dist`

   `web/vercel.json` already sets the framework and the SPA rewrite.

   One caveat with the dashboard route: Vercel builds from the git checkout, so
   `web/public/data/` must be **committed** for the offline mode to survive the
   build. It is. If you ever regenerate it with `make static`, commit the result.

### Netlify

Drag `web/dist` onto <https://app.netlify.com/drop>. That is the whole procedure.

### GitHub Pages

Needs no new account, since the repo is already on GitHub.

```bash
make static && cd web && npm run build
npx gh-pages -d dist        # or push dist to a gh-pages branch
```

Then **Settings → Pages → Source: gh-pages**. If the site is served from a
subpath (`/<repo-name>/`), build with that base or the asset URLs will 404:

```bash
cd web && npx vite build --base=/Mastercard-Innovation-Hackathon-/
```

---

## Option B — static UI plus a live API

Adds the real SSE stream. Deploy the API first, then rebuild the UI pointing at
it.

### The API, on Render

`render.yaml` is committed as a blueprint.

1. **New → Blueprint**, point it at the repo, and Render reads `render.yaml`.
2. Or **New → Web Service** manually:
   - Build: `pip install -e .`
   - Start: `python -m mantis.api --host 0.0.0.0`
   - Health check: `/health`

`mantis/api/__main__.py` reads `$PORT`, which is what Render injects.

> **The free tier sleeps after ~15 minutes idle and takes ~30 s to wake.** Open
> the URL once immediately before presenting. This is the single most likely way
> for the demo to look broken, and it is also the reason the console falls back
> to the offline replay instead of showing a spinner.

### The API, on Railway

`railway.json` is committed. `railway up` from the repo root, or import the repo
in the dashboard.

### The API, on Hugging Face Spaces

Create a **Docker** Space and push the repo; the committed `Dockerfile` targets
port 7860, which is what Spaces expects.

### Then point the UI at it

```bash
cd web
VITE_API_BASE=https://your-api-host.onrender.com npm run build
```

CORS is already configured for `*.vercel.app`, `*.netlify.app` and `*.hf.space`
(see `CORS_ORIGIN_REGEX` in `mantis/api/app.py`). A different host needs one line
added there and a redeploy.

---

## Before you believe it works

Verified locally already: a clean clone serves every endpoint, the SSE stream
delivers well-formed frames, the docx regenerates, and CORS answers correctly for
both a Vercel origin and localhost. What is **not** verified is the deployed URL,
because that cannot be checked from here. Check it yourself:

- [ ] Open the URL **on a phone**, on mobile data rather than the venue wifi.
- [ ] Press **Start authorisation stream** and watch rows arrive and resolve
      red/green.
- [ ] Click a declined row — the alert panel must show the layer bars and the
      top-3 contributions.
- [ ] Switch to **Results** — the three-row recovery table (0.811 / 0.013 /
      0.539) must render large.
- [ ] Check the badge in the console's control row: `API connected` or
      `offline replay`. Either is fine; know which one you are demoing.
- [ ] If you deployed the API, hit its URL once ~1 minute before presenting so
      it is awake.

---

## Regenerating everything

```bash
make firewall      # refits the layers, rewrites RESULTS.md      (~15 min)
make loop          # the evasion curve and the zero-day rows     (~35 min)
make submission    # ood, feed, docx, static, web                (~4 min)
```

The order matters. `RESULTS.md` is written by `make firewall`; the document and
the results screen are both **generated from it**, so they cannot drift from what
the code produces. Nothing downstream is ever retyped.
