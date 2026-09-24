# Vue 3 + Vite

This template should help get you started developing with Vue 3 in Vite. The template uses Vue 3 `<script setup>` SFCs, check out the [script setup docs](https://v3.vuejs.org/api/sfc-script-setup.html#sfc-script-setup) to learn more.

Learn more about IDE Support for Vue in the [Vue Docs Scaling up Guide](https://vuejs.org/guide/scaling-up/tooling.html#ide-support).

## Environment variables

Create a `.env` (or `.env.local`) file in this directory to configure runtime behavior:

```
VITE_API_BASE=/api
# Optional timezone used for date formatting (e.g., UTC or Europe/Berlin)
VITE_TIME_ZONE=
```

- `VITE_API_BASE`: Base URL for the backend API. Defaults to `/api` which is proxied to `http://127.0.0.1:8000` via `vite.config.js` during development.
- `VITE_TIME_ZONE`: If set, dates are formatted in this zone in the UI. Leave empty to use the browser default.
- `VITE_BOKEH_VERSION`: Version of the vendored BokehJS bundle (see below). Must match the Python `bokeh` version in `requirements.txt`.

## Vendored assets

Third-party browser assets are self-hosted from `public/vendor/` (no third-party CDN requests).
Exception: Aladin Lite (sky view) is intentionally loaded from CDS Strasbourg.

| File | Version | Source | SHA-256 |
|------|---------|--------|---------|
| `public/vendor/bokeh/bokeh-3.9.0.min.js` | 3.9.0 | https://cdn.bokeh.org/bokeh/release/bokeh-3.9.0.min.js | `83771b3b796a8d6bbaf93184a44fdf22798a1bae6df8c1a95ff7afb9174a2a2a` |

The BokehJS file is byte-identical to `bokeh/server/static/js/bokeh.min.js` from the Python package `bokeh==3.9.0` (BSD-3-Clause; license header retained). It is loaded on demand by `src/utils/bokeh.js`. Only the core bundle is needed: the backend plots (`obs_run/plotting.py`) use plots, annotations and `Tabs`/`TabPanel` (layouts, part of core). If plots ever use widgets, `DataTable`, WebGL or MathText, also vendor the matching `bokeh-widgets-`, `bokeh-tables-`, `bokeh-gl-` or `bokeh-mathjax-<ver>.min.js` and load them after the core bundle.

Served URL: `vite build` copies `public/vendor/` to `dist/vendor/`, `collectstatic` puts it into `static/vendor/`, and Apache serves it at `/data_archive/static/vendor/...` (the loader uses `${BASE_URL}static/`, like the favicons in `index.html`; the Vite dev server serves it at `${BASE_URL}vendor/`).

Updating BokehJS when the Python `bokeh` version changes:

```
cd OSTdata/frontend/public/vendor/bokeh
VER=3.9.0   # new version
curl -fsSLO https://cdn.bokeh.org/bokeh/release/bokeh-${VER}.min.js
sha256sum bokeh-${VER}.min.js
# optional cross-check against the installed Python package (hashes should be identical):
sha256sum /path/to/ostdata_env/lib/python3.*/site-packages/bokeh/server/static/js/bokeh.min.js
rm bokeh-<old version>.min.js
```

Then set `VITE_BOKEH_VERSION` in `.env`, update the fallback in `src/utils/bokeh.js` and the table above, run `npm run build` and `python manage.py collectstatic`.
