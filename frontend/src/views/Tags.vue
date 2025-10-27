<template>
  <v-container fluid class="tags">
      <div class="d-flex align-center justify-space-between mb-4">
        <h1 class="text-h4">Tags</h1>
        <v-btn
          color="primary"
          prepend-icon="mdi-plus"
          v-if="canEdit"
          @click="openEdit()"
        >New Tag</v-btn>
      </div>

      <v-card class="mb-4">
        <v-card-text>
          <v-row>
            <v-col cols="12" sm="8" md="6">
      <v-text-field
                v-model="search"
                label="Search tags"
                prepend-inner-icon="mdi-magnify"
                single-line
                hide-details
                density="comfortable"
                variant="outlined"
              ></v-text-field>
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="12">
              <v-btn
                variant="text"
                color="secondary"
                prepend-icon="mdi-filter-remove"
                @click="resetFilters"
              >
                Reset Filters
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <v-alert v-if="error" type="error" variant="tonal" class="mb-3">{{ error }}</v-alert>
      <v-card>
        <v-data-table
          :headers="headers"
          :items="items"
          :items-length="totalItems"
          :items-per-page="itemsPerPage === -1 ? totalItems : itemsPerPage"
          :loading="loading"
          :sort-by="[{ key: sortKey.replace('-', ''), order: sortKey.startsWith('-') ? 'desc' : 'asc' }]"
          @update:sort-by="handleSort"
          hide-default-footer
          class="custom-table"
        >
          <template #loading>
            <LoadingState type="table" />
          </template>

          <template #no-data>
            <EmptyState text="No tags found." />
          </template>

          <template #item.name="{ item }">
            <div class="d-flex align-center">
              <v-chip :color="item.color" class="mr-2" variant="flat"></v-chip>
              <v-tooltip :text="item.name" location="top">
                <template #activator="{ props }">
                  <span v-bind="props" class="cell-truncate">{{ item.name }}</span>
                </template>
              </v-tooltip>
            </div>
          </template>

          <template #item.actions="{ item }">
            <v-btn icon variant="text" color="primary" class="action-btn" v-if="canEdit" @click="openEdit(item)" :aria-label="`Edit tag ${item.name}`">
              <v-icon>mdi-pencil</v-icon>
            </v-btn>
            <v-btn icon variant="text" color="error" class="action-btn" v-if="canEdit" @click="remove(item)" :aria-label="`Delete tag ${item.name}`">
              <v-icon>mdi-delete</v-icon>
            </v-btn>
          </template>
        </v-data-table>

        <v-card-actions class="d-flex align-center justify-space-between px-4 py-2 card-actions-responsive">
          <div class="d-flex align-center actions-left">
            <span class="text-body-2 mr-4">Items per page:</span>
            <v-select
              v-model="itemsPerPage"
              :items="[10, 25, 50, 100, -1]"
              :item-title="item => item === -1 ? 'All' : item.toString()"
              :item-value="item => item"
              density="compact"
              variant="outlined"
              hide-details
              class="items-per-page-select"
              style="width: 100px"
              @update:model-value="handleItemsPerPageChange"
              aria-label="Items per page"
            ></v-select>
          </div>

          <div class="d-flex align-center actions-right">
            <span class="text-body-2 mr-4">
              {{ paginationInfo }}
            </span>
            <v-btn icon="mdi-page-first" variant="text" :disabled="currentPage === 1" @click="handlePageChange(1)" class="mx-1 pagination-btn" aria-label="First page" />
            <v-btn icon="mdi-chevron-left" variant="text" :disabled="currentPage === 1" @click="handlePageChange(currentPage - 1)" class="mx-1 pagination-btn" aria-label="Previous page" />
            <v-btn icon="mdi-chevron-right" variant="text" :disabled="currentPage >= totalPages" @click="handlePageChange(currentPage + 1)" class="mx-1 pagination-btn" aria-label="Next page" />
            <v-btn icon="mdi-page-last" variant="text" :disabled="currentPage >= totalPages" @click="handlePageChange(totalPages)" class="mx-1 pagination-btn" aria-label="Last page" />
            <v-btn
              variant="text"
              color="primary"
              prepend-icon="mdi-content-copy"
              class="ml-2"
              @click="copyShareLink"
              aria-label="Copy link to current view"
            >
              Copy link
            </v-btn>
          </div>
        </v-card-actions>
      </v-card>

      <!-- Create/Edit dialog -->
      <v-dialog v-model="editDialog" max-width="520" @keydown.esc.prevent="closeEdit" aria-labelledby="tag-dialog-title">
        <v-card>
          <v-card-title id="tag-dialog-title">{{ editing?.pk ? 'Edit Tag' : 'New Tag' }}</v-card-title>
          <v-card-text>
            <v-form ref="formRef">
              <v-text-field
                v-model="form.name"
                label="Name"
                variant="outlined"
                density="comfortable"
                :rules="[rules.required]"
                hide-details="auto"
                autofocus
              />
              <div class="d-flex align-center mt-3">
                <v-text-field
                  v-model="form.color"
                  label="Color (#RRGGBB)"
                  variant="outlined"
                  density="comfortable"
                  class="mr-3"
                  style="max-width: 180px"
                  :rules="[rules.required, rules.hex]"
                  hide-details="auto"
                />
                <v-chip :style="{ backgroundColor: form.color || '#999', color: '#fff' }" class="mr-3" variant="flat">
                  {{ form.color || '#------' }}
                </v-chip>
                <v-menu v-model="pickerOpen" :close-on-content-click="false" location="bottom">
                  <template #activator="{ props }">
                    <v-btn v-bind="props" variant="outlined" color="primary">Pick</v-btn>
                  </template>
                  <v-card elevation="4">
                    <v-color-picker
                      v-model="form.color"
                      mode="hex"
                      theme="light"
                      width="300"
                    />
                    <v-card-actions>
                      <v-spacer />
                      <v-btn variant="text" @click="pickerOpen = false">Close</v-btn>
                    </v-card-actions>
                  </v-card>
                </v-menu>
              </div>
              <v-alert v-if="savingError" type="error" variant="tonal" class="mt-3">{{ savingError }}</v-alert>
            </v-form>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="closeEdit" ref="cancelBtnRef">Cancel</v-btn>
            <v-btn variant="flat" color="primary" :loading="saving" @click="save">Save</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, computed, watch, reactive } from 'vue'
import { useNotifyStore } from '@/store/notify'
import { api } from '@/services/api'
import { useAuthStore } from '@/store/auth'
import { useQuerySync } from '@/composables/useQuerySync'
import EmptyState from '@/components/ui/EmptyState.vue'
import ErrorState from '@/components/ui/ErrorState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'

const items = ref([])
const loading = ref(false)
const error = ref('')
const search = ref('')
const currentPage = ref(1)
const itemsPerPage = ref(25)
const totalItems = ref(0)
const sortKey = ref('name')

const authStore = useAuthStore()
const canEdit = computed(() => authStore.isAuthenticated)

const headers = [
  { title: 'Name', key: 'name', sortable: true },
  { title: 'Color', key: 'color', sortable: false },
  { title: 'Objects', key: 'n_objects', sortable: true },
  { title: 'Actions', key: 'actions', sortable: false },
]

const totalPages = computed(() => {
  if (itemsPerPage.value === -1) return 1
  return Math.ceil(totalItems.value / itemsPerPage.value)
})

const paginationInfo = computed(() => {
  if (itemsPerPage.value === -1) return `Showing all ${totalItems.value} items`
  const start = (currentPage.value - 1) * itemsPerPage.value + 1
  const end = Math.min(currentPage.value * itemsPerPage.value, totalItems.value)
  return `${start}-${end} of ${totalItems.value}`
})

const fetchTags = async () => {
  try {
    loading.value = true
    const params = {
      page: currentPage.value,
      limit: itemsPerPage.value === -1 ? 10000 : itemsPerPage.value,
      ordering: sortKey.value,
      search: search.value || undefined,
    }
    const data = await api.getTags(params)
    // Support both paginated and plain lists
    if (Array.isArray(data)) {
      items.value = data
      totalItems.value = data.length
    } else {
      items.value = data.results || data.items || []
      totalItems.value = data.count || data.total || items.value.length
    }
  } catch (e) {
    error.value = 'Failed to load tags.'
    items.value = []
    totalItems.value = 0
  } finally {
    loading.value = false
  }
}

const handleSort = (newSortBy) => {
  if (newSortBy.length > 0) {
    const sort = newSortBy[0]
    sortKey.value = `${sort.order === 'desc' ? '-' : ''}${sort.key}`
  } else {
    sortKey.value = 'name'
  }
  syncQueryAndFetch()
}

const handlePageChange = (newPage) => {
  if (newPage >= 1 && newPage <= totalPages.value) {
    currentPage.value = newPage
    syncQueryAndFetch()
  }
}

const handleItemsPerPageChange = () => {
  currentPage.value = 1
  syncQueryAndFetch()
}

import { debounce } from 'lodash'
const debouncedSyncTags = debounce(() => {
  syncQueryAndFetch()
}, 300)

watch(search, () => {
  currentPage.value = 1
  debouncedSyncTags()
})

// CRUD (optional)
const editDialog = ref(false)
const lastFocusedEl = ref(null)
const cancelBtnRef = ref(null)
const saving = ref(false)
const editing = ref(null)
const form = reactive({ name: '', color: '' })
const pickerOpen = ref(false)
const formRef = ref(null)
const savingError = ref('')
const rules = {
  required: v => !!(v && String(v).trim()) || 'Required',
  hex: v => /^#([0-9a-fA-F]{6})$/.test(v || '') || 'Use #RRGGBB',
}
const notify = useNotifyStore()

const openEdit = (item = null) => {
  try { lastFocusedEl.value = document.activeElement } catch {}
  editing.value = item
  form.name = item?.name || ''
  form.color = item?.color || '#ff0000'
  editDialog.value = true
}

const restoreFocus = () => {
  try {
    const el = lastFocusedEl.value
    if (el && typeof el.focus === 'function') setTimeout(() => el.focus(), 0)
  } catch {}
}

const closeEdit = () => {
  editDialog.value = false
  restoreFocus()
}

const save = async () => {
  if (!canEdit.value) return
  try {
    saving.value = true
    savingError.value = ''
    const { valid } = await formRef.value.validate()
    if (!valid) return
    const payload = { name: form.name, color: form.color }
    if (editing.value?.pk) {
      await api.updateTag(editing.value.pk, payload)
      notify.success('Tag updated')
    } else {
      await api.createTag(payload)
      notify.success('Tag created')
    }
    editDialog.value = false
    restoreFocus()
    await fetchTags()
  } catch (e) {
    console.error(e)
    savingError.value = e?.message || 'Save failed'
  } finally {
    saving.value = false
  }
}

const remove = async (item) => {
  if (!canEdit.value || !item?.pk) return
  try {
    await api.deleteTag(item.pk)
    notify.success('Tag deleted')
    await fetchTags()
  } catch (e) {
    console.error(e)
  }
}

const resetFilters = () => {
  search.value = ''
  currentPage.value = 1
  sortKey.value = 'name'
  syncQueryAndFetch()
}

const copyShareLink = async () => {
  try {
    await navigator.clipboard.writeText(window.location.href)
    notify.success('Link copied')
  } catch (e) {
    console.error('Copy link failed', e)
  }
}

const { applyQuery, syncQueryAndFetch } = useQuerySync(
  { page: currentPage, pageSize: itemsPerPage, q: search, sort: sortKey },
  [
    { key: 'page', fromQuery: (v) => { const n = parseInt(v); return Number.isFinite(n) && n > 0 ? n : 1 }, defaultValue: 1 },
    { key: 'pageSize', fromQuery: (v) => { const n = parseInt(v); return Number.isFinite(n) && (n > 0 || n === -1) ? n : 25 }, defaultValue: 25 },
    { key: 'q' },
    { key: 'sort', defaultValue: 'name' },
  ],
  fetchTags
)

applyQuery()
fetchTags()
</script>

<style scoped>
.tags {
  padding: 20px 0;
}

.items-per-page-select {
  max-width: 100px;
}

/* Accessible focus ring for row action buttons */
.action-btn:focus-visible {
  outline: 2px solid currentColor;
  outline-offset: 2px;
  border-radius: 50%;
}

.pagination-btn:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 2px;
  border-radius: 50%;
}

.v-data-table :deep(th) {
  position: sticky;
  top: 0;
  background: rgb(var(--v-theme-surface));
  z-index: 2;
}

.v-data-table :deep(.v-data-table__wrapper) {
  overflow-x: auto;
  overflow-y: visible;
}

/* Align cell padding with other overview tables */
.v-data-table :deep(td) {
  padding: 8px 16px !important;
}

/* Responsive wrapping for action bar */
.card-actions-responsive {
  flex-wrap: wrap;
  gap: 12px;
}
.card-actions-responsive .actions-left,
.card-actions-responsive .actions-right {
  flex-wrap: wrap;
}
.card-actions-responsive .actions-left { row-gap: 8px; }
.card-actions-responsive .actions-right { row-gap: 8px; }
.card-actions-responsive .items-per-page-select { min-width: 96px; }

/* Single-line truncation with ellipsis */
.cell-truncate {
  display: inline-block;
  max-width: 320px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}
</style>