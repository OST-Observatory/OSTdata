import { ref } from 'vue'

// One sky view dialog (and one Aladin Lite/WebGL instance) for the whole app, opened from any data
// file table: browsers allow only a limited number of WebGL contexts.
const skyViewFile = ref(null)
const skyViewOpen = ref(false)

export function canShowSkyView(item) {
  return !!(item?.plate_solved && item?.wcs_ra != null && item?.wcs_dec != null)
}

export function useSkyView() {
  const openSkyView = (item) => {
    skyViewFile.value = item
    skyViewOpen.value = true
  }
  return { skyViewFile, skyViewOpen, openSkyView }
}
