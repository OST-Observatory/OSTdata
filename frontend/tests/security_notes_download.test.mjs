// Lightweight frontend security helpers (no HTML execution for notes / token header).
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')

test('ObservationRunDetail notes use text interpolation, not v-html', () => {
  const src = readFileSync(join(root, 'src/views/ObservationRunDetail.vue'), 'utf8')
  assert.doesNotMatch(src, /v-html=.*note/)
  assert.match(src, /class="notes-text"/)
  assert.match(src, /\{\{\s*run\?\.note/)
})

test('ObjectDetail notes use text interpolation, not v-html', () => {
  const src = readFileSync(join(root, 'src/views/ObjectDetail.vue'), 'utf8')
  assert.doesNotMatch(src, /v-html=.*note/)
  assert.match(src, /class="notes-text"/)
})

test('download job APIs send X-Download-Token header', () => {
  const api = readFileSync(join(root, 'src/services/api.js'), 'utf8')
  const poll = readFileSync(join(root, 'src/utils/downloadJobPoll.js'), 'utf8')
  assert.match(api, /X-Download-Token/)
  assert.match(poll, /jobToken/)
  assert.match(api, /downloadJobFile:\s*async \(jobId,\s*jobToken/)
})

test('download prep message avoids admin jobs and zero-minute wait', async () => {
  const { buildDownloadPrepMessage, formatDownloadJobWaitMinutes } = await import('../src/config/downloadJobs.js')
  assert.equal(formatDownloadJobWaitMinutes(10_000), 1)
  assert.equal(formatDownloadJobWaitMinutes(45 * 60 * 1000), 45)
  const msg = await buildDownloadPrepMessage({ fileCount: 2, items: [{ file_size: 1000 }] })
  assert.doesNotMatch(msg, /Admin/)
  assert.doesNotMatch(msg, /0 minutes/)
  assert.match(msg, /site administrator/)
})
