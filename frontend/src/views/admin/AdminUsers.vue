<template>
  <v-container fluid class="py-4">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h5">Admin · Users</h1>
    </div>

    <v-card class="mb-4">
      <v-card-title class="text-h6">LDAP Tools</v-card-title>
      <v-card-text>
        <v-row class="align-end">
          <v-col cols="12" sm="6" md="4">
            <v-text-field
              v-model="ldapUser"
              label="Test username (e.g. uid)"
              prepend-inner-icon="mdi-account-search"
              hide-details
              density="comfortable"
              variant="outlined"
            />
          </v-col>
          <v-col cols="12" sm="6" md="4">
            <v-text-field
              v-model="ldapFilter"
              label="Override filter (optional)"
              prepend-inner-icon="mdi-filter"
              hide-details
              density="comfortable"
              variant="outlined"
            />
          </v-col>
          <v-col cols="12" sm="12" md="4">
            <v-btn color="primary" prepend-icon="mdi-play" :loading="ldapLoading" @click="runLdapTest">
              Run test
            </v-btn>
          </v-col>
        </v-row>
        <div v-if="ldapResult" class="mt-3">
          <div class="d-flex flex-wrap" style="gap: 8px">
            <v-chip size="small" :color="ldapResult.configured ? 'success' : 'secondary'">configured</v-chip>
            <v-chip size="small" :color="ldapResult.can_import ? 'success' : 'error'">module</v-chip>
            <v-chip size="small" :color="ldapResult.bind_ok ? 'success' : 'error'">bind</v-chip>
            <v-chip size="small" :color="ldapResult.search_ok ? 'success' : 'error'">search</v-chip>
            <v-chip v-if="ldapResult.latency_ms != null" size="small" color="secondary" variant="flat">
              {{ ldapResult.latency_ms }}ms
            </v-chip>
            <v-chip v-if="ldapResult.count != null" size="small" color="secondary" variant="flat">
              {{ ldapResult.count }} result(s)
            </v-chip>
          </div>
          <div class="text-caption text-medium-emphasis mt-2" v-if="ldapResult.server_uri">
            Server: {{ ldapResult.server_uri }}
          </div>
          <div class="mt-2" v-if="ldapResult.first_dn">
            <div class="text-caption text-medium-emphasis mb-1">First DN</div>
            <code class="text-body-2">{{ ldapResult.first_dn }}</code>
          </div>
          <div class="mt-2" v-if="ldapResult.attrs">
            <div class="text-caption text-medium-emphasis mb-1">Attributes</div>
            <div class="text-caption">uid: {{ ldapResult.attrs.uid || '—' }}</div>
            <div class="text-caption">mail: {{ ldapResult.attrs.mail || '—' }}</div>
            <div class="text-caption">givenName: {{ ldapResult.attrs.givenName || '—' }}</div>
            <div class="text-caption">sn: {{ ldapResult.attrs.sn || '—' }}</div>
          </div>
          <div class="mt-2" v-if="ldapResult.mapping_preview">
            <div class="text-caption text-medium-emphasis mb-1">Mapping preview</div>
            <div class="text-caption">first_name: {{ ldapResult.mapping_preview.first_name || '—' }}</div>
            <div class="text-caption">last_name: {{ ldapResult.mapping_preview.last_name || '—' }}</div>
            <div class="text-caption">email: {{ ldapResult.mapping_preview.email || '—' }}</div>
          </div>
          <div class="mt-2" v-if="ldapResult.groups && Object.keys(ldapResult.groups).length">
            <div class="text-caption text-medium-emphasis mb-1">Groups</div>
            <div class="d-flex flex-wrap" style="gap: 6px">
              <v-chip size="small" :color="ldapResult.groups.staff ? 'primary' : 'default'" variant="flat">staff</v-chip>
              <v-chip size="small" :color="ldapResult.groups.superuser ? 'primary' : 'default'" variant="flat">superuser</v-chip>
              <v-chip size="small" :color="ldapResult.groups.supervisor ? 'primary' : 'default'" variant="flat">supervisor</v-chip>
              <v-chip size="small" :color="ldapResult.groups.student ? 'primary' : 'default'" variant="flat">student</v-chip>
            </div>
          </div>
          <div class="mt-2 text-error text-caption" v-if="ldapResult.errors && Object.keys(ldapResult.errors).length">
            <div v-for="(v, k) in ldapResult.errors" :key="k">{{ k }}: {{ v }}</div>
          </div>
        </div>
      </v-card-text>
    </v-card>

    <v-alert v-if="!canView" type="warning" variant="tonal" class="mb-4">
      You don't have permission to view users.
    </v-alert>

    <v-card v-if="canView">
      <v-card-text>
        <v-row>
          <v-col cols="12" sm="6" md="4">
            <v-text-field
              v-model="search"
              label="Search (username/email)"
              prepend-inner-icon="mdi-magnify"
              hide-details
              density="comfortable"
              variant="outlined"
            />
          </v-col>
        </v-row>
      </v-card-text>

      <v-data-table
        :headers="headers"
        :items="filteredItems"
        item-key="id"
        :loading="loading"
        class="custom-table"
      >
        <template #loading>
          <LoadingState type="table" />
        </template>
        <template #no-data>
          <EmptyState text="No users found." />
        </template>

        <template #item.username="{ item }">
          <span class="cell-truncate">{{ item.username }}</span>
        </template>
        <template #item.email="{ item }">
          <span class="cell-truncate">{{ item.email }}</span>
        </template>
        <template #item.source="{ item }">
          <v-chip size="x-small" :color="(item.source || '').toUpperCase() === 'LDAP' ? 'primary' : 'secondary'" variant="flat">
            {{ (item.source || 'local') }}
          </v-chip>
        </template>
        <template #item.last_login="{ item }">
          <span class="text-caption">{{ formatRelative(item.last_login) }}</span>
        </template>
        <template #item.is_active="{ item }">
          <v-switch
            v-model="item.is_active"
            color="primary"
            hide-details
            density="compact"
            inset
            :disabled="!canEdit"
            @update:model-value="(val) => toggleActive(item, val)"
            :aria-label="`Toggle active for ${item.username}`"
          />
        </template>
        <template #item.is_staff="{ item }">
          <v-switch
            v-model="item.is_staff"
            color="primary"
            hide-details
            density="compact"
            inset
            :disabled="!canEdit"
            @update:model-value="(val) => toggleStaff(item, val)"
            :aria-label="`Toggle staff for ${item.username}`"
          />
        </template>
        <template #item.is_supervisor="{ item }">
          <v-switch
            v-model="item.is_supervisor"
            color="primary"
            hide-details
            density="compact"
            inset
            :disabled="!canEdit"
            @update:model-value="(val) => toggleSupervisor(item, val)"
            :aria-label="`Toggle supervisor for ${item.username}`"
          />
        </template>
        <template #item.is_student="{ item }">
          <v-switch
            v-model="item.is_student"
            color="primary"
            hide-details
            density="compact"
            inset
            :disabled="!canEdit"
            @update:model-value="(val) => toggleStudent(item, val)"
            :aria-label="`Toggle student for ${item.username}`"
          />
        </template>
        <template #item.is_superuser="{ item }">
          <v-chip size="small" :color="item.is_superuser ? 'primary' : 'default'" variant="flat">
            {{ item.is_superuser ? 'Yes' : 'No' }}
          </v-chip>
        </template>
        <template #item.actions="{ item }">
          <div v-if="canDelete">
            <v-btn icon variant="text" color="error" class="action-btn" @click="remove(item)" :aria-label="`Delete ${item.username}`">
              <v-icon>mdi-delete</v-icon>
            </v-btn>
          </div>
        </template>
      </v-data-table>
    </v-card>

    <v-card class="mt-4">
      <v-card-title class="text-h6">ACL</v-card-title>
      <v-card-text>
        <div class="text-caption text-medium-emphasis mb-2">
          Manage which roles have which permissions. Superusers bypass ACL.
        </div>
        <div class="mb-2 d-flex align-center" style="gap: 12px">
          <v-btn color="secondary" variant="outlined" prepend-icon="mdi-refresh" :loading="aclLoading" @click="loadAcl">Refresh</v-btn>
          <v-btn color="primary" prepend-icon="mdi-content-save" :loading="aclSaving" @click="saveAcl">Save changes</v-btn>
        </div>
        <v-table density="comfortable">
          <thead>
            <tr>
              <th class="text-left">Permission</th>
              <th v-for="g in aclGroups" :key="g" class="text-center text-capitalize">{{ g }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in aclPerms" :key="p.codename">
              <td class="text-caption">{{ p.name }}</td>
              <td v-for="g in aclGroups" :key="g" class="text-center">
                <v-checkbox
                  v-model="aclMatrixLocal[g]"
                  :value="p.codename"
                  hide-details
                  density="compact"
                />
              </td>
            </tr>
          </tbody>
        </v-table>
        <div v-if="aclError" class="text-error text-caption mt-2">{{ aclError }}</div>
      </v-card-text>
    </v-card>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'
import EmptyState from '@/components/ui/EmptyState.vue'
import LoadingState from '@/components/ui/LoadingState.vue'
import { useAuthStore } from '@/store/auth'

const loading = ref(false)
const items = ref([])
const search = ref('')
const notify = useNotifyStore()
const ldapUser = ref('')
const ldapFilter = ref('')
const ldapLoading = ref(false)
const ldapResult = ref(null)
const auth = useAuthStore()

// ACL helpers
const canView = computed(() => auth.isAdmin || auth.hasPerm('users.acl_users_view') || auth.hasPerm('acl_users_view'))
const canEdit = computed(() => auth.isAdmin || auth.hasPerm('users.acl_users_edit_roles') || auth.hasPerm('acl_users_edit_roles'))
const canDelete = computed(() => auth.isAdmin || auth.hasPerm('users.acl_users_delete') || auth.hasPerm('acl_users_delete'))

const headers = [
  { title: 'Username', key: 'username', sortable: true },
  { title: 'Email', key: 'email', sortable: true },
  { title: 'Source', key: 'source', sortable: true },
  { title: 'Last login', key: 'last_login', sortable: true },
  { title: 'Active', key: 'is_active', sortable: false },
  { title: 'Staff', key: 'is_staff', sortable: false },
  { title: 'Supervisor', key: 'is_supervisor', sortable: false },
  { title: 'Student', key: 'is_student', sortable: false },
  { title: 'Superuser', key: 'is_superuser', sortable: false },
  { title: 'Actions', key: 'actions', sortable: false },
]

const filteredItems = computed(() => {
  const q = search.value.trim().toLowerCase()
  if (!q) return items.value
  return items.value.filter(u =>
    (u.username || '').toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q)
  )
})

const fetchUsers = async () => {
  loading.value = true
  try {
    if (!canView.value) { items.value = []; return }
    const data = await api.adminListUsers()
    items.value = Array.isArray(data) ? data : (data.results || data.items || [])
  } catch (e) {
    items.value = []
  } finally {
    loading.value = false
  }
}

const toggleActive = async (user, val) => {
  try {
    await api.adminUpdateUser(user.id, { is_active: !!val })
    notify.success('Updated')
  } catch (e) {
    user.is_active = !val
    notify.error('Update failed')
  }
}

const toggleStaff = async (user, val) => {
  try {
    await api.adminUpdateUser(user.id, { is_staff: !!val })
    notify.success('Updated')
  } catch (e) {
    user.is_staff = !val
    notify.error('Update failed')
  }
}

const toggleSupervisor = async (user, val) => {
  try {
    await api.adminUpdateUser(user.id, { is_supervisor: !!val })
    notify.success('Updated')
  } catch (e) {
    user.is_supervisor = !val
    notify.error('Update failed')
  }
}

const toggleStudent = async (user, val) => {
  try {
    await api.adminUpdateUser(user.id, { is_student: !!val })
    notify.success('Updated')
  } catch (e) {
    user.is_student = !val
    notify.error('Update failed')
  }
}

const remove = async (user) => {
  if (!user?.id) return
  if (!confirm(`Delete user ${user.username}? This cannot be undone.`)) return
  try {
    await api.adminDeleteUser(user.id)
    notify.success('User deleted')
    await fetchUsers()
  } catch (e) {
    notify.error('Delete failed')
  }
}

onMounted(fetchUsers)

const runLdapTest = async () => {
  ldapLoading.value = true
  ldapResult.value = null
  try {
    const payload = {}
    if (ldapUser.value) payload.username = ldapUser.value
    if (ldapFilter.value) payload.filter = ldapFilter.value
    const res = await api.adminLdapTest(payload)
    ldapResult.value = res
    if (!res?.configured) {
      notify.error('LDAP not configured')
    } else if (!res?.can_import) {
      notify.error('python-ldap not available on server')
    } else if (!res?.bind_ok) {
      notify.error('LDAP bind failed')
    } else if (!res?.search_ok) {
      notify.error('LDAP search failed')
    } else {
      notify.success('LDAP test OK')
    }
  } catch (e) {
    notify.error('LDAP test error')
  } finally {
    ldapLoading.value = false
  }
}

// ACL helpers
const loadAcl = async () => {
  aclLoading.value = true
  aclError.value = ''
  try {
    const data = await api.adminAclGet()
    aclGroups.value = Array.isArray(data?.groups) ? data.groups : []
    aclPerms.value = Array.isArray(data?.permissions) ? data.permissions : []
    const m = data?.matrix || {}
    aclMatrix.value = m
    // Local clone as group->Set array for checkbox v-model
    const local = {}
    aclGroups.value.forEach(g => {
      local[g] = Array.isArray(m[g]) ? m[g].slice() : []
    })
    aclMatrixLocal.value = local
  } catch (e) {
    aclError.value = 'Failed to load ACL'
  } finally {
    aclLoading.value = false
  }
}
const saveAcl = async () => {
  aclSaving.value = true
  aclError.value = ''
  try {
    const matrix = {}
    Object.keys(aclMatrixLocal.value || {}).forEach(g => {
      matrix[g] = (aclMatrixLocal.value[g] || []).slice()
    })
    await api.adminAclSet(matrix)
    notify.success('ACL saved')
    await loadAcl()
  } catch (e) {
    aclError.value = 'Failed to save ACL'
  } finally {
    aclSaving.value = false
  }
}
onMounted(() => {
  loadAcl()
})
const formatRelative = (iso) => {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    const diff = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000))
    if (diff < 60) return `${diff}s ago`
    const m = Math.floor(diff / 60)
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    const days = Math.floor(h / 24)
    return `${days}d ago`
  } catch { return iso }
}
</script>

<style scoped>
.custom-table :deep(th) {
  position: sticky;
  top: 0;
  background: rgb(var(--v-theme-surface));
  z-index: 2;
}
.custom-table :deep(td) { padding: 8px 16px !important; }
.cell-truncate { max-width: 280px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.action-btn:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; border-radius: 50%; }
</style>


