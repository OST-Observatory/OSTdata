<template>
  <v-container fluid class="py-4">
    <div class="d-flex align-center justify-space-between mb-4 flex-wrap" style="gap: 12px">
      <h1 class="text-h5">Admin · Objects</h1>
      <div class="d-flex align-center flex-wrap" style="gap: 8px">
        <v-btn variant="text" :to="{ path: '/objects' }">Open Objects list</v-btn>
      </div>
    </div>

    <h2 class="text-h6 mb-3">Create object</h2>

    <v-card class="mb-4 create-object-card">
      <v-card-text>
        <p class="text-body-2 text-medium-emphasis mb-4">
          Add a new archive object (any type). For solar-system targets, set type <strong>Solar system</strong> and upload a preview image below.
        </p>
        <v-btn
          color="primary"
          size="large"
          prepend-icon="mdi-plus"
          aria-label="Create new object"
          @click="createObjectDialog = true"
        >
          Create new object
        </v-btn>
      </v-card-text>
    </v-card>

    <div class="d-flex align-center justify-space-between mb-4 flex-wrap" style="gap: 12px">
      <h2 class="text-h6">Solar-system preview images</h2>
      <div class="d-flex align-center flex-wrap" style="gap: 8px">
        <v-btn variant="outlined" prepend-icon="mdi-refresh" :loading="loading" @click="fetchItems">
          Refresh
        </v-btn>
      </div>
    </div>

    <v-alert type="info" variant="tonal" class="mb-4" density="compact">
      Preview images for <strong>solar-system objects</strong> (type SO) are stored on disk and shown on the object detail page instead of the sky map when present.
      Filename stem = sanitized object name (spaces → underscores, parentheses removed).
      <span v-if="imagesDirectory" class="d-block mt-1 text-caption">Directory: {{ imagesDirectory }}</span>
    </v-alert>

    <v-card>
      <v-card-text>
        <v-data-table
          :headers="headers"
          :items="items"
          :loading="loading"
          item-key="pk"
          density="comfortable"
          :items-per-page="25"
        >
          <template #item.preview="{ item }">
            <v-avatar v-if="item.has_image && item.image_url" size="48" rounded="sm">
              <v-img :src="item.image_url" :alt="item.name" cover />
            </v-avatar>
            <span v-else class="text-caption text-medium-emphasis">—</span>
          </template>
          <template #item.has_image="{ item }">
            <v-icon :color="item.has_image ? 'success' : 'disabled'">
              {{ item.has_image ? 'mdi-check-circle' : 'mdi-close-circle' }}
            </v-icon>
          </template>
          <template #item.actions="{ item }">
            <div class="d-flex align-center flex-wrap" style="gap: 4px">
              <v-btn
                size="small"
                variant="tonal"
                color="primary"
                prepend-icon="mdi-upload"
                :loading="uploadingId === item.pk"
                @click="triggerUpload(item)"
              >
                Upload
              </v-btn>
              <v-btn
                v-if="item.has_image"
                size="small"
                variant="text"
                color="error"
                prepend-icon="mdi-delete"
                :loading="deletingId === item.pk"
                @click="removeImage(item)"
              >
                Remove
              </v-btn>
              <v-btn
                size="small"
                variant="text"
                :to="`/objects/${item.pk}`"
              >
                View
              </v-btn>
            </div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>

    <input
      ref="fileInputRef"
      type="file"
      accept="image/jpeg,image/png,image/webp,image/gif"
      class="d-none"
      @change="onFileSelected"
    />

    <v-dialog v-model="createObjectDialog" max-width="480" persistent aria-labelledby="admin-create-object-title">
      <v-card>
        <v-card-title id="admin-create-object-title">Create new object</v-card-title>
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
          <v-spacer />
          <v-btn variant="text" @click="closeCreateObjectDialog">Cancel</v-btn>
          <v-btn
            color="primary"
            :loading="creatingObject"
            :disabled="!createObjectForm.name?.trim()"
            @click="submitCreateObject"
          >
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'
import { useCreateObject } from '@/composables/useCreateObject'

const notify = useNotifyStore()
const loading = ref(false)
const items = ref([])
const imagesDirectory = ref('')
const uploadingId = ref(null)
const deletingId = ref(null)
const uploadTarget = ref(null)
const fileInputRef = ref(null)

const {
  createObjectDialog,
  creatingObject,
  createObjectForm,
  objectTypeOptions,
  closeCreateObjectDialog,
  submitCreateObject,
} = useCreateObject()

const headers = [
  { title: 'Name', key: 'name', sortable: true },
  { title: 'File stem', key: 'sanitized_filename', sortable: true },
  { title: 'Image', key: 'has_image', sortable: true, width: 80 },
  { title: 'Preview', key: 'preview', sortable: false, width: 72 },
  { title: 'Actions', key: 'actions', sortable: false, align: 'end' },
]

const fetchItems = async () => {
  try {
    loading.value = true
    const data = await api.adminListSolarSystemImages()
    items.value = Array.isArray(data?.items) ? data.items : []
    imagesDirectory.value = data?.directory || ''
  } catch (e) {
    console.error(e)
    notify.error('Failed to load solar-system objects')
  } finally {
    loading.value = false
  }
}

const triggerUpload = (item) => {
  uploadTarget.value = item
  if (fileInputRef.value) {
    fileInputRef.value.value = ''
    fileInputRef.value.click()
  }
}

const onFileSelected = async (event) => {
  const file = event?.target?.files?.[0]
  const item = uploadTarget.value
  if (!file || !item?.pk) return
  try {
    uploadingId.value = item.pk
    await api.adminUploadSolarSystemImage(item.pk, file)
    notify.success(`Image uploaded for ${item.name}`)
    await fetchItems()
  } catch (e) {
    console.error(e)
    notify.error(e?.data?.detail || 'Upload failed')
  } finally {
    uploadingId.value = null
    uploadTarget.value = null
  }
}

const removeImage = async (item) => {
  if (!item?.pk) return
  try {
    deletingId.value = item.pk
    await api.adminDeleteSolarSystemImage(item.pk)
    notify.success(`Image removed for ${item.name}`)
    await fetchItems()
  } catch (e) {
    console.error(e)
    notify.error('Failed to remove image')
  } finally {
    deletingId.value = null
  }
}

onMounted(() => {
  fetchItems()
})
</script>
