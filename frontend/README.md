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
