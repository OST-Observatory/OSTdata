<template>
  <!-- Sky view of a plate-solved file: the preview placed on the sky by its WCS (Aladin Lite), with a
       coordinate grid and the run's cached SIMBAD objects. Mounted once in AppLayout (useSkyView). -->
  <v-dialog v-model="skyViewOpen" max-width="1200" @after-enter="show">
    <v-card>
      <v-card-title class="d-flex align-center" style="gap: 8px">
        <v-icon icon="mdi-earth" size="20" />
        <span class="text-truncate">Sky view: {{ skyViewFile?.file_name }}</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="skyViewOpen = false" />
      </v-card-title>
      <v-card-text>
        <div class="d-flex flex-wrap align-center mb-2 sky-controls">
          <v-switch v-model="showImage" label="Image" color="primary" density="compact" hide-details inset />
          <v-switch v-model="showSurvey" label="Sky survey (DSS)" color="primary" density="compact" hide-details inset />
          <v-switch v-model="showGrid" label="Coordinate grid" color="primary" density="compact" hide-details inset />
          <v-switch v-model="showObjects" label="SIMBAD objects" color="primary" density="compact" hide-details inset />
          <div class="sky-mag">
            <div class="text-caption">Stars brighter than V = {{ magLimit }}</div>
            <v-slider v-model="magLimit" :min="4" :max="18" :step="0.5" density="compact" hide-details :disabled="!showObjects" />
          </div>
          <span class="text-caption text-medium-emphasis">{{ visibleObjects.length }} of {{ objects.length }} objects shown</span>
        </div>
        <v-alert v-if="error" type="warning" variant="tonal" class="mb-2">{{ error }}</v-alert>
        <div class="sky-view-wrapper">
          <div ref="container" class="sky-view-container" />
          <div v-if="loading" class="sky-view-loading">
            <v-progress-circular indeterminate color="primary" />
          </div>
        </div>
        <p class="text-caption text-medium-emphasis mt-2 mb-0">
          Objects from the SIMBAD lookup cached for the run<template v-if="auxStatus && auxStatus !== 'done'">
          (lookup {{ auxStatus }})</template>; galaxies, nebulae and clusters are shown regardless of brightness.
          The sky survey needs the CDS servers; image, grid and objects work without them.
        </p>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '@/services/api'
import { useSkyView } from '@/composables/useSkyView'

const { skyViewFile, skyViewOpen } = useSkyView()

const container = ref(null)
const loading = ref(false)
const error = ref('')
const objects = ref([])
const auxStatus = ref(null)
const showImage = ref(true)
const showSurvey = ref(true)
const showGrid = ref(true)
const showObjects = ref(true)
const magLimit = ref(12)

// Extended objects often have no V magnitude in SIMBAD
const EXTENDED_TYPES = new Set(['GA', 'NE', 'SC'])
const MAX_LABELLED = 80

let A = null
let aladin = null
let targetCatalog = null
let simbadCatalog = null
let shownPk = null

const visibleObjects = computed(() => {
  if (!showObjects.value) return []
  const others = objects.value
    .filter((o) => !o.main)
    .filter((o) => (typeof o.v_mag === 'number' ? o.v_mag <= magLimit.value : EXTENDED_TYPES.has(o.object_type)))
    .sort((a, b) => (a.v_mag ?? -99) - (b.v_mag ?? -99))
    .slice(0, MAX_LABELLED)
  return [...objects.value.filter((o) => o.main), ...others]
})

const sourceFor = (o) => A.source(o.ra, o.dec, {
  name: o.name,
  type: o.object_type_display || o.object_type || '',
  V: typeof o.v_mag === 'number' ? o.v_mag.toFixed(2) : '',
})

function updateCatalogs() {
  if (!aladin) return
  targetCatalog.removeAll()
  simbadCatalog.removeAll()
  targetCatalog.addSources(visibleObjects.value.filter((o) => o.main).map(sourceFor))
  simbadCatalog.addSources(visibleObjects.value.filter((o) => !o.main).map(sourceFor))
}

async function ensureAladin(view) {
  if (aladin) return
  // Self-hosted, loaded on first use only (separate chunk; no CDS server needed for the library)
  A = (await import('aladin-lite')).default
  await A.init
  aladin = A.aladin(container.value, {
    survey: 'P/DSS2/color',
    fov: view.fov_deg * 1.3,
    target: `${view.center.ra} ${view.center.dec}`,
    showCooGrid: showGrid.value,
    showReticle: false,
    showFrame: true,
    showLayersControl: false,
    showGotoControl: false,
    showShareControl: false,
    showSettingsControl: false,
    showContextMenu: false,
    showFullscreenControl: true,
  })
  const label = { displayLabel: true, labelColumn: 'name', labelFont: '12px sans-serif', onClick: 'showPopup' }
  targetCatalog = A.catalog({ name: 'Targets', color: '#ffd54f', labelColor: '#ffd54f', sourceSize: 20, ...label })
  simbadCatalog = A.catalog({ name: 'SIMBAD', color: '#4fc3f7', labelColor: '#4fc3f7', sourceSize: 12, ...label })
  aladin.addCatalog(targetCatalog)
  aladin.addCatalog(simbadCatalog)
}

async function show() {
  const item = skyViewFile.value
  const pk = item?.pk ?? item?.id
  if (pk == null || pk === shownPk) return
  loading.value = true
  error.value = ''
  try {
    const view = await api.getDataFileSkyView(pk)
    if (!view?.available) {
      error.value = view?.reason || 'Sky view not available for this file'
      return
    }
    await ensureAladin(view)
    objects.value = view.objects || []
    auxStatus.value = view.aux_objects_status
    aladin.setOverlayImageLayer(A.image(api.getDataFileSkyImageUrl(pk), {
      name: item.file_name || 'image',
      imgFormat: 'jpeg',
      wcs: view.wcs,
    }))
    aladin.gotoRaDec(view.center.ra, view.center.dec)
    aladin.setFoV(view.fov_deg * 1.3)
    applyLayerSettings()
    updateCatalogs()
    shownPk = pk
  } catch (e) {
    console.error('Sky view failed', e)
    error.value = 'The sky view could not be loaded (the browser needs WebGL2).'
  } finally {
    loading.value = false
  }
}

function applyLayerSettings() {
  if (!aladin) return
  aladin.getBaseImageLayer?.()?.setOpacity(showSurvey.value ? 1 : 0)
  aladin.getOverlayImageLayer?.()?.setOpacity(showImage.value ? 1 : 0)
  if (typeof aladin.setCooGrid === 'function') aladin.setCooGrid({ enabled: showGrid.value })
}

watch([showSurvey, showImage, showGrid], applyLayerSettings)
watch(visibleObjects, updateCatalogs)
</script>

<style scoped>
.sky-controls {
  gap: 4px 20px;
}

.sky-mag {
  width: 220px;
}

.sky-view-wrapper {
  position: relative;
}

.sky-view-container {
  width: 100%;
  height: 65vh;
  min-height: 360px;
}

.sky-view-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
