import { ref } from 'vue'
import { useNotifyStore } from '@/store/notify'
import { plateSolveInBackground, plateSolveSummary } from '@/utils/plateSolveJobs'

/**
 * Plate solving of selected files in the background for a view: solvingIds holds the files in
 * progress (row loading state, no second trigger), notifications report queueing and the result,
 * onDone refreshes the view's data.
 */
export function usePlateSolveJobs({ onDone } = {}) {
  const notify = useNotifyStore()
  const solvingIds = ref(new Set())

  const release = (ids) => {
    const next = new Set(solvingIds.value)
    ids.forEach(id => next.delete(id))
    solvingIds.value = next
  }

  /** Resolves once the task is queued (or failed to queue); the result is reported later. */
  const startPlateSolve = (fileIds, label = '') => new Promise((queued) => {
    const ids = fileIds.filter(id => !solvingIds.value.has(id))
    if (!ids.length) {
      queued(false)
      return
    }
    solvingIds.value = new Set([...solvingIds.value, ...ids])
    plateSolveInBackground(ids, {
      onQueued: () => {
        notify.info(ids.length === 1 && label
          ? `Plate solving ${label} in the background …`
          : `Plate solving ${ids.length} file(s) in the background …`)
        queued(true)
      },
    })
      .then(async (results) => {
        const summary = plateSolveSummary(results)
        if (summary.ok) notify.success(summary.text)
        else notify.warning(summary.text, 8000)
        if (onDone) await onDone()
      })
      .catch((error) => {
        // Errors of the trigger request itself are shown by the API layer
        if (String(error?.message || '').startsWith('Plate solving did not finish')) notify.warning(error.message)
        queued(false)
      })
      .finally(() => release(ids))
  })

  return { solvingIds, startPlateSolve }
}
