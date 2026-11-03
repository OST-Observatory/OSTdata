import { api } from '@/services/api'

/**
 * Plate solve files in the background (Celery task) and wait for the results by polling the state of
 * the files: with several solvers and retries a single file can take minutes, too long for one
 * HTTP request. onQueued is called once the task is queued; resolves to [{file_id, success, tool, error}].
 */
export async function plateSolveInBackground(fileIds, { onQueued, intervalMs = 4000, maxWaitMs = 60 * 60 * 1000 } = {}) {
  const job = await api.triggerPlateSolve(fileIds)
  if (onQueued) onQueued(job)
  const started = Date.now()
  while (Date.now() - started < maxWaitMs) {
    await new Promise(resolve => setTimeout(resolve, intervalMs))
    let status
    try {
      status = await api.getPlateSolveTriggerStatus(job.file_ids, job.queued_at)
    } catch {
      continue  // e.g. a short network outage: keep waiting
    }
    if (status?.done) return status.files
  }
  throw new Error('Plate solving did not finish within the waiting time; results will appear later')
}

/** Short summary for a notification. */
export function plateSolveSummary(results) {
  const succeeded = results.filter(r => r.success)
  if (results.length === 1) {
    return succeeded.length
      ? { ok: true, text: `Plate solved (${succeeded[0].tool || 'unknown tool'})` }
      : { ok: false, text: `Plate solving failed: ${results[0].error || 'no solution'}` }
  }
  return {
    ok: succeeded.length > 0,
    text: `Plate solving: ${succeeded.length} of ${results.length} files solved`,
  }
}
