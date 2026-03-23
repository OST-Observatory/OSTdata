import {
  ensureDownloadJobConfig,
  getDownloadJobMaxWaitMs,
  getDownloadJobPollIntervalMs,
} from '@/config/downloadJobs'
import { api } from '@/services/api'

/**
 * Poll until job is done (then caller usually calls api.downloadJobFile).
 * @param {string} jobId
 * @param {{ timeoutMs?: number, intervalMs?: number }} [overrides]
 */
export async function pollDownloadJobUntilReady(jobId, overrides = {}) {
  await ensureDownloadJobConfig()
  const timeoutMs = overrides.timeoutMs ?? getDownloadJobMaxWaitMs()
  const intervalMs = overrides.intervalMs ?? getDownloadJobPollIntervalMs()
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const status = await api.getDownloadJobStatus(jobId)
    if (status?.status === 'done' && status?.url) return status
    if (status?.status === 'failed' || status?.status === 'cancelled') {
      throw new Error(status?.error || 'Job failed')
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
  throw new Error('Timed out waiting for download job')
}
