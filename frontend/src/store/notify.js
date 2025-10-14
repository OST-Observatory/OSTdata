import { defineStore } from 'pinia'

let nextId = 1

export const useNotifyStore = defineStore('notify', {
  state: () => ({
    notifications: [], // { id, type, text, timeout, visible }
  }),
  actions: {
    push(payload) {
      const id = nextId++
      const { type = 'info', text = '', timeout = 4000 } = payload || {}
      this.notifications.push({ id, type, text, timeout, visible: true })
      return id
    },
    success(text, timeout = 3000) {
      return this.push({ type: 'success', text, timeout })
    },
    info(text, timeout = 3000) {
      return this.push({ type: 'info', text, timeout })
    },
    warning(text, timeout = 4000) {
      return this.push({ type: 'warning', text, timeout })
    },
    error(text, timeout = 5000) {
      return this.push({ type: 'error', text, timeout })
    },
    dismiss(id) {
      const n = this.notifications.find(n => n.id === id)
      if (n) n.visible = false
      // Remove after small delay to allow animation
      setTimeout(() => {
        this.notifications = this.notifications.filter(n => n.id !== id)
      }, 200)
    },
    clear() {
      this.notifications = []
    }
  }
})


