<template>
  <v-container class="py-4">
    <h1 class="text-h4 mb-4">Admin</h1>
    <v-row>
      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Tags</v-card-title>
          <v-card-text>
            Create, edit, and delete tags.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/tags' }" aria-label="Open Tags management">
              Open Tags
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Users & Roles</v-card-title>
          <v-card-text>
            Manage user activation and staff roles.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/users' }" aria-label="Open Users management">
              Open Users
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Download Jobs</v-card-title>
          <v-card-text>
            Monitor download jobs; cancel stuck tasks.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/jobs' }" aria-label="Open Download Jobs">
              Open Download Jobs
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Health</v-card-title>
          <v-card-text>
            Quick system diagnostics (API/Bokeh versions).
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/health' }" aria-label="Open Health">
              Open Health
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Data Maintenance</v-card-title>
          <v-card-text>
            Utilities for tags, objects, and runs.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/maintenance' }" aria-label="Open Maintenance">
              Open Maintenance
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Observation Runs</v-card-title>
          <v-card-text>
            Review runs and update metadata.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/observation-runs' }" aria-label="Open Observation Runs">
              Open Runs
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Objects</v-card-title>
          <v-card-text>
            Create new objects and manage existing ones.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" @click="createObjectDialog = true" aria-label="Create new object">
              Create new object
            </v-btn>
            <v-btn variant="text" :to="{ path: '/objects' }" aria-label="Open Objects">
              Open Objects
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Exposure Type Discrepancies</v-card-title>
          <v-card-text>
            Review and resolve exposure type classification discrepancies.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/exposure-type-discrepancies' }" aria-label="Open Exposure Type Discrepancies">
              Open Discrepancies
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Spectrograph Management</v-card-title>
          <v-card-text>
            Manage spectrograph property for data files with spectrograph set or WAVE exposure type.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/spectrograph-files' }" aria-label="Open Spectrograph Management">
              Open Spectrograph
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Plate Solving</v-card-title>
          <v-card-text>
            Manage plate solving for data files.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/plate-solving' }" aria-label="Open Plate Solving">
              Open Plate Solving
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <!-- Create Object Dialog -->
    <v-dialog v-model="createObjectDialog" max-width="480" persistent aria-labelledby="create-object-title">
      <v-card>
        <v-card-title id="create-object-title">Create new object</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="createObjectForm.name"
            label="Name"
            required
            variant="outlined"
            density="comfortable"
            hide-details
            class="mb-3"
            autofocus
          />
          <v-select
            v-model="createObjectForm.object_type"
            :items="objectTypeOptions"
            item-title="title"
            item-value="value"
            label="Object Type"
            variant="outlined"
            density="comfortable"
            hide-details
            clearable
            class="mb-3"
          />
          <v-row dense class="mb-3">
            <v-col cols="6">
              <v-text-field
                v-model="createObjectForm.ra"
                label="RA"
                variant="outlined"
                density="comfortable"
                hide-details
                placeholder="deg oder HH:MM:SS"
              />
            </v-col>
            <v-col cols="6">
              <v-text-field
                v-model="createObjectForm.dec"
                label="Dec"
                variant="outlined"
                density="comfortable"
                hide-details
                placeholder="deg oder ±DD:MM:SS"
              />
            </v-col>
          </v-row>
          <v-textarea
            v-model="createObjectForm.note"
            label="Note"
            variant="outlined"
            density="comfortable"
            hide-details
            rows="2"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeCreateObjectDialog">Cancel</v-btn>
          <v-btn color="primary" :loading="creatingObject" :disabled="!createObjectForm.name?.trim()" @click="submitCreateObject">
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'

const router = useRouter()
const notify = useNotifyStore()
const createObjectDialog = ref(false)
const creatingObject = ref(false)
const createObjectForm = reactive({
  name: '',
  object_type: null,
  ra: '',
  dec: '',
  note: '',
})

/** Parse RA string to degrees. Accepts decimal deg (0–360) or HMS (HH:MM:SS, HH:MM, HH MM SS). */
const parseRaToDeg = (str) => {
  if (!str || typeof str !== 'string') return null
  const s = str.trim()
  if (!s) return null
  const hasColonOrSpace = /[:,\s]/.test(s)
  const parts = s.split(/[:,\s]+/).filter(Boolean)
  if (hasColonOrSpace && parts.length >= 2) {
    const h = Number(parts[0])
    const m = Number(parts[1])
    const sec = parts.length >= 3 ? Number(parts[2]) : 0
    if (Number.isFinite(h) && Number.isFinite(m) && Number.isFinite(sec) && h >= 0 && h < 24 && m >= 0 && m < 60 && sec >= 0 && sec < 60) {
      return (h + m / 60 + sec / 3600) * 15
    }
  }
  const deg = parseFloat(s)
  if (!Number.isFinite(deg)) return null
  if (deg >= 0 && deg <= 360) return deg
  if (deg >= 0 && deg <= 24) return deg * 15
  return null
}

/** Parse Dec string to degrees. Accepts decimal deg (-90–90) or DMS (±DD:MM:SS, ±DD:MM, ±DD MM SS). */
const parseDecToDeg = (str) => {
  if (!str || typeof str !== 'string') return null
  const s = str.trim()
  if (!s) return null
  const signMatch = s.match(/^([+-])?/)
  const sign = (signMatch && signMatch[1] === '-') ? -1 : 1
  const rest = s.replace(/^[+-]/, '').trim()
  const hasColonOrSpace = /[:,\s]/.test(rest)
  const parts = rest.split(/[:,\s]+/).filter(Boolean)
  if (hasColonOrSpace && parts.length >= 2) {
    const d = Number(parts[0])
    const m = Number(parts[1])
    const sec = parts.length >= 3 ? Number(parts[2]) : 0
    if (Number.isFinite(d) && Number.isFinite(m) && Number.isFinite(sec) && d >= 0 && d <= 90 && m >= 0 && m < 60 && sec >= 0 && sec < 60) {
      return sign * (d + m / 60 + sec / 3600)
    }
  }
  const deg = parseFloat(s)
  if (!Number.isFinite(deg)) return null
  if (deg >= -90 && deg <= 90) return deg
  return null
}

const objectTypeOptions = [
  { title: 'Unknown', value: 'UK' },
  { title: 'Galaxy', value: 'GA' },
  { title: 'Star cluster', value: 'SC' },
  { title: 'Nebula', value: 'NE' },
  { title: 'Solar system', value: 'SO' },
  { title: 'Star', value: 'ST' },
  { title: 'Other', value: 'OT' },
]

const closeCreateObjectDialog = () => {
  createObjectDialog.value = false
  createObjectForm.name = ''
  createObjectForm.object_type = null
  createObjectForm.ra = ''
  createObjectForm.dec = ''
  createObjectForm.note = ''
}

const submitCreateObject = async () => {
  const name = createObjectForm.name?.trim()
  if (!name) return
  if (createObjectForm.ra?.trim() && parseRaToDeg(createObjectForm.ra) === null) {
    notify.error('Ungültiges RA-Format. Verwenden Sie Grad (0–360) oder HH:MM:SS.')
    return
  }
  if (createObjectForm.dec?.trim() && parseDecToDeg(createObjectForm.dec) === null) {
    notify.error('Ungültiges Dec-Format. Verwenden Sie Grad (-90–90) oder ±DD:MM:SS.')
    return
  }
  try {
    creatingObject.value = true
    const payload = {
      name,
      object_type: createObjectForm.object_type || undefined,
      note: createObjectForm.note?.trim() || undefined,
      tag_ids: [],
    }
    const raVal = parseRaToDeg(createObjectForm.ra)
    if (raVal !== null) {
      payload.ra = raVal
    }
    const decVal = parseDecToDeg(createObjectForm.dec)
    if (decVal !== null) {
      payload.dec = decVal
    }
    const obj = await api.createObject(payload)
    const pk = obj?.pk ?? obj?.id
    closeCreateObjectDialog()
    notify.success('Object created.')
    if (pk != null) {
      router.push(`/objects/${pk}`)
    } else {
      router.push('/objects')
    }
  } catch (e) {
    const msg = e?.data?.detail || e?.data?.error || e?.message || 'Failed to create object'
    notify.error(msg)
  } finally {
    creatingObject.value = false
  }
}
</script>

<style scoped>
</style>


