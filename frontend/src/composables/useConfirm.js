import { reactive } from 'vue'

// One confirmation dialog for the whole app (components/ui/ConfirmDialog.vue in AppLayout), used
// instead of the browser's confirm(): same look in both themes, destructive actions in red.
const state = reactive({
  open: false,
  title: '',
  text: '',
  confirmText: 'Confirm',
  cancelText: 'Cancel',
  color: 'error',
  resolve: null,
})

function answer(confirmed) {
  const resolve = state.resolve
  state.resolve = null
  state.open = false
  if (resolve) resolve(confirmed)
}

/**
 * Ask for confirmation; resolves to true (confirmed) or false (cancelled, Esc, click outside).
 * color: 'error' for destructive or irreversible actions (default), 'primary' otherwise.
 */
export function confirmAction({ title, text = '', confirmText = 'Confirm', cancelText = 'Cancel', color = 'error' }) {
  // A dialog still open (should not happen) counts as cancelled
  if (state.resolve) answer(false)
  Object.assign(state, { title, text, confirmText, cancelText, color, open: true })
  return new Promise((resolve) => {
    state.resolve = resolve
  })
}

export function useConfirm() {
  return { state, answer, confirmAction }
}
