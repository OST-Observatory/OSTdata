/**
 * On-demand loader for the self-hosted BokehJS bundle (no third-party CDN).
 *
 * The bundle lives in frontend/public/vendor/bokeh/ (see README there). In the
 * production build it is collected into Django's STATIC_ROOT and served by
 * Apache under `${BASE_URL}static/` (e.g. /data_archive/static/vendor/bokeh/),
 * like the favicons in index.html. The Vite dev server serves public/ directly
 * at BASE_URL.
 *
 * VITE_BOKEH_VERSION must match the Python bokeh version (requirements.txt) and
 * the vendored file name.
 */

const BOKEH_VERSION = import.meta.env?.VITE_BOKEH_VERSION || '3.9.0'

export function bokehScriptUrl() {
  const base = import.meta.env?.BASE_URL || '/'
  const prefix = import.meta.env?.DEV ? base : `${base}static/`
  return `${prefix}vendor/bokeh/bokeh-${BOKEH_VERSION}.min.js`
}

let loadingPromise = null

/** Load BokehJS once; resolves when window.Bokeh is available. */
export function ensureBokeh() {
  if (window.Bokeh) return Promise.resolve()
  if (!loadingPromise) {
    loadingPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script')
      script.src = bokehScriptUrl()
      script.onload = resolve
      script.onerror = (e) => {
        loadingPromise = null
        script.remove()
        reject(e)
      }
      document.head.appendChild(script)
    })
  }
  return loadingPromise
}
