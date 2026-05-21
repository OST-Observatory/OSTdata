import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'

export const objectTypeOptions = [
  { title: 'Unknown', value: 'UK' },
  { title: 'Galaxy', value: 'GA' },
  { title: 'Star cluster', value: 'SC' },
  { title: 'Nebula', value: 'NE' },
  { title: 'Solar system', value: 'SO' },
  { title: 'Star', value: 'ST' },
  { title: 'Other', value: 'OT' },
]

/** Parse RA string to degrees. Accepts decimal deg (0–360) or HMS. */
export const parseRaToDeg = (str) => {
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

/** Parse Dec string to degrees. Accepts decimal deg (-90–90) or DMS. */
export const parseDecToDeg = (str) => {
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

export function useCreateObject() {
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
      if (raVal !== null) payload.ra = raVal
      const decVal = parseDecToDeg(createObjectForm.dec)
      if (decVal !== null) payload.dec = decVal
      const obj = await api.createObject(payload)
      const pk = obj?.pk ?? obj?.id
      closeCreateObjectDialog()
      notify.success('Object created.')
      if (pk != null) {
        router.push(`/objects/${pk}`)
      } else {
        router.push('/objects')
      }
      return obj
    } catch (e) {
      const msg = e?.data?.detail || e?.data?.error || e?.message || 'Failed to create object'
      notify.error(msg)
      throw e
    } finally {
      creatingObject.value = false
    }
  }

  return {
    createObjectDialog,
    creatingObject,
    createObjectForm,
    objectTypeOptions,
    closeCreateObjectDialog,
    submitCreateObject,
  }
}
