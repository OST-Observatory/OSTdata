import { watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'

// A tiny utility to sync a view's reactive state with URL query parameters.
// keys: array of { key, toQuery(value), fromQuery(raw), defaultValue }
// fetch: function to call after query changes
export function useQuerySync(stateRefs, keys, fetch) {
  const router = useRouter()
  const route = useRoute()

  const truthy = (v) => v !== undefined && v !== null && v !== ''

  const serializeQuery = () => {
    const q = {}
    for (const k of keys) {
      const value = stateRefs[k.key]?.value
      if (value === undefined) continue
      const enc = k.toQuery ? k.toQuery(value) : value
      if (truthy(enc)) q[k.key] = enc
    }
    return q
  }

  const applyQuery = () => {
    const q = route.query
    for (const k of keys) {
      const raw = q[k.key]
      const value = truthy(raw)
        ? (k.fromQuery ? k.fromQuery(raw) : raw)
        : (k.defaultValue !== undefined ? k.defaultValue : stateRefs[k.key]?.value)
      if (stateRefs[k.key]) stateRefs[k.key].value = value
    }
  }

  const syncQueryAndFetch = () => {
    router.replace({ query: serializeQuery() })
    fetch()
  }

  const watchKeys = keys
    .filter((k) => !!stateRefs[k.key])
    .map((k) => stateRefs[k.key])

  watch(watchKeys, () => {
    syncQueryAndFetch()
  })

  // public API
  return {
    applyQuery,
    syncQueryAndFetch,
  }
}


