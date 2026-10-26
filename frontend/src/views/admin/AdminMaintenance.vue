<template>
  <v-container class="py-4 admin-page">
    <header class="d-flex align-center justify-space-between flex-wrap mb-4" style="gap: 12px">
      <div>
        <h1 class="text-h4 mb-1">Maintenance</h1>
        <p class="text-body-2 text-medium-emphasis mb-0">
          Manual triggers for ingest, cleanup, integrity checks, and site banner.
        </p>
      </div>
      <div class="d-flex align-center flex-wrap maint-toolbar" style="gap: 12px">
        <v-switch
          v-model="autoRefresh"
          color="primary"
          hide-details
          inset
          density="comfortable"
          :label="`Auto ${refreshSeconds}s`"
          @update:model-value="scheduleRefresh"
        />
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-refresh"
          :loading="loading"
          @click="refreshHealth"
        >
          Refresh
        </v-btn>
        <v-btn variant="text" prepend-icon="mdi-arrow-left" :to="{ path: '/admin' }">
          Admin
        </v-btn>
      </div>
    </header>

    <p
      v-if="health.settings?.DATA_DIRECTORY"
      class="text-caption text-medium-emphasis mb-3"
    >
      Data directory:
      <code class="maintenance-code">{{ health.settings.DATA_DIRECTORY }}</code>
    </p>

    <v-card v-if="canBanner" variant="outlined" class="admin-maint-card">
      <v-card-title class="maint-section-title text-subtitle-2">
        <v-icon icon="mdi-bullhorn-outline" size="18" class="mr-1" />
        Site-wide banner
      </v-card-title>
      <v-card-text class="maint-section-body">
        <div class="maint-actions mb-2">
          <v-switch v-model="bannerEnabled" inset hide-details color="primary" density="compact" label="Enabled" />
          <v-select
            v-model="bannerLevel"
            :items="bannerLevels"
            label="Level"
            hide-details
            density="compact"
            variant="outlined"
            class="maint-banner-level"
          />
        </div>
        <v-textarea
          v-model="bannerMessage"
          label="Message"
          variant="outlined"
          density="compact"
          auto-grow
          rows="2"
          hide-details
          class="mb-2"
        />
        <div class="maint-actions">
          <v-btn color="primary" variant="tonal" prepend-icon="mdi-content-save" :loading="busy.banner" @click="saveBanner">
            Save
          </v-btn>
          <v-btn variant="text" prepend-icon="mdi-refresh" :loading="busy.banner" @click="loadBanner">
            Reload
          </v-btn>
          <v-btn variant="text" color="error" prepend-icon="mdi-close-circle" :loading="busy.banner" @click="clearBanner">
            Clear
          </v-btn>
        </div>
      </v-card-text>
    </v-card>
    
    <template v-for="section in visibleSections" :key="section.key">
      <v-card variant="outlined" class="admin-maint-card mb-3">
        <v-card-title class="maint-section-title text-subtitle-2">
          <v-icon :icon="section.icon" size="18" class="mr-1" />
          {{ section.title }}
        </v-card-title>
        <v-card-text class="maint-section-body">
          <div class="maint-task-grid">
            <div
              v-for="task in section.tasks"
              :key="task.id"
              class="maint-task-cell"
            >
              <div class="maint-task-head">
                <v-icon :icon="task.icon" :color="task.color" size="18" />
                <span class="text-body-2 font-weight-medium">{{ task.title }}</span>
                <v-chip
                  size="x-small"
                  :color="taskStatusColor(periodic[task.periodicKey])"
                  variant="flat"
                  class="ml-auto"
                >
                  {{ taskStatusLabel(periodic[task.periodicKey]) }}
                </v-chip>
                <v-chip
                  v-if="task.beatFeature && health.features?.[task.beatFeature]"
                  size="x-small"
                  color="success"
                  variant="outlined"
                >
                  Beat
                </v-chip>
              </div>

              <p class="text-caption text-medium-emphasis mb-2 maint-task-desc">
                {{ task.description }}
              </p>

              <div v-if="task.controlsType" class="maint-actions mb-2">
                <template v-if="task.controlsType === 'scan'">
                  <v-switch v-model="scanDryRun" inset hide-details color="primary" density="compact" label="Dry run" />
                  <v-text-field
                    v-model="scanLimit"
                    label="Limit"
                    type="number"
                    min="1"
                    density="compact"
                    variant="outlined"
                    hide-details
                    class="maint-limit-field"
                  />
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-folder-search"
                    :loading="busy.scan"
                    @click="triggerScanMissing"
                  >
                    Run
                  </v-btn>
                </template>

                <template v-else-if="task.controlsType === 'reconcile'">
                  <v-switch v-model="dryRun" inset hide-details color="primary" density="compact" label="Dry run" />
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-compare"
                    :loading="busy.reconcile"
                    @click="triggerReconcile"
                  >
                    Run
                  </v-btn>
                </template>

                <template v-else-if="task.controlsType === 'cleanup'">
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-broom"
                    :loading="busy.cleanup"
                    @click="triggerCleanup"
                  >
                    Run
                  </v-btn>
                </template>

                <template v-else-if="task.controlsType === 'orphans'">
                  <v-switch v-model="orphDryRun" inset hide-details color="primary" density="compact" label="Dry run" />
                  <v-switch v-model="orphFixMissing" inset hide-details color="primary" density="compact" label="Fix hashes" />
                  <v-text-field
                    v-model="orphLimit"
                    label="Limit"
                    type="number"
                    min="1"
                    density="compact"
                    variant="outlined"
                    hide-details
                    class="maint-limit-field"
                  />
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-magnify-scan"
                    :loading="busy.orphans"
                    @click="triggerOrphans"
                  >
                    Run
                  </v-btn>
                </template>

                <template v-else-if="task.controlsType === 'orphanObj'">
                  <v-switch v-model="orphObjDryRun" inset hide-details color="primary" density="compact" label="Dry run" />
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-account-remove"
                    :loading="busy.orphanObj"
                    @click="triggerOrphanObjects"
                  >
                    Run
                  </v-btn>
                </template>

                <template v-else-if="task.controlsType === 'unlink'">
                  <v-switch v-model="unlinkNonLightDryRun" inset hide-details color="primary" density="compact" label="Dry run" />
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-link-off"
                    :loading="busy.unlinkNonLight"
                    @click="triggerUnlinkNonLight"
                  >
                    Run
                  </v-btn>
                </template>

                <template v-else-if="task.controlsType === 'dashboard'">
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-chart-box-outline"
                    :loading="busy.dashboardStats"
                    @click="triggerDashboardStats"
                  >
                    Refresh
                  </v-btn>
                </template>

                <template v-else-if="task.controlsType === 'plate'">
                  <v-switch
                    :model-value="plateSolvingTaskEnabled"
                    :loading="busy.plateSolvingToggle"
                    color="primary"
                    inset
                    hide-details
                    density="compact"
                    label="Enabled"
                    @update:model-value="togglePlateSolvingTask"
                  />
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-star-four-points"
                    :loading="busy.plateSolving"
                    :disabled="!plateSolvingTaskEnabled"
                    @click="triggerPlateSolving"
                  >
                    Trigger
                  </v-btn>
                  <v-btn
                    variant="text"
                    prepend-icon="mdi-open-in-new"
                    :to="{ path: '/admin/plate-solving' }"
                  >
                    Unsolved
                  </v-btn>
                </template>

                <template v-else-if="task.controlsType === 'reEvaluate'">
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-refresh"
                    :loading="busy.reEvaluatePlateSolved"
                    @click="triggerReEvaluatePlateSolved"
                  >
                    Trigger
                  </v-btn>
                </template>
              </div>

              <dl class="maint-kv maint-kv--dense">
                <dt>Last run</dt>
                <dd>
                  <span v-if="periodic[task.periodicKey]?.last_run">
                    {{ formatRelative(periodic[task.periodicKey].last_run, periodic[task.periodicKey].age_seconds) }}
                  </span>
                  <span v-else class="text-medium-emphasis">—</span>
                </dd>
                <template v-for="row in summaryRows(task.periodicKey, task.summarySpec)" :key="row.label">
                  <dt>{{ row.label }}</dt>
                  <dd>{{ row.value }}</dd>
                </template>
              </dl>

              <div
                v-if="periodic[task.periodicKey]?.last_error"
                class="text-error text-caption mt-1"
              >
                {{ periodic[task.periodicKey].last_error }}
              </div>
            </div>
          </div>
        </v-card-text>
      </v-card>
    </template>

    <v-card
      v-if="canReconcile"
      variant="outlined"
      class="admin-maint-card mb-3"
    >
      <v-card-title class="maint-section-title text-subtitle-2 d-flex align-center flex-wrap" style="gap: 8px">
        <v-icon icon="mdi-file-alert-outline" size="18" />
        <span>File integrity</span>
        <v-chip size="x-small" color="error" variant="flat">{{ fileIssueCounts.error }} errors</v-chip>
        <v-chip size="x-small" color="warning" variant="flat">{{ fileIssueCounts.warning }} warnings</v-chip>
        <v-spacer />
        <v-switch
          v-model="checkOnlyUnchecked"
          inset
          hide-details
          color="primary"
          density="compact"
          label="Only unchecked"
        />
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-file-search-outline"
          :loading="busy.checkFiles"
          @click="triggerCheckFiles"
        >
          Check files
        </v-btn>
        <v-btn
          variant="text"
          prepend-icon="mdi-refresh"
          :loading="loadingFileIssues"
          @click="loadFileIssues"
        >
          Refresh
        </v-btn>
      </v-card-title>
      <v-card-text class="maint-section-body pt-0">
        <p class="text-caption text-medium-emphasis mb-2">
          Truncated or unreadable files (errors) and non-compliant headers (warnings) found by the last
          check: {{ fileIssueCounts.checked }} of {{ fileIssueCounts.total }} files checked<template
            v-if="periodic.check_data_files?.last_run"
          >, last run {{ formatRelative(periodic.check_data_files.last_run, periodic.check_data_files.age_seconds) }}</template>.
          New files are checked on ingest.
        </p>
        <div class="d-flex align-center flex-wrap mb-2" style="gap: 8px">
          <v-btn-toggle v-model="fileIssueLevel" density="compact" variant="outlined" divided mandatory>
            <v-btn value="">All</v-btn>
            <v-btn value="error">Errors</v-btn>
            <v-btn value="warning">Warnings</v-btn>
          </v-btn-toggle>
          <v-text-field
            v-model="fileIssueSearch"
            label="Path contains"
            density="compact"
            variant="outlined"
            hide-details
            clearable
            prepend-inner-icon="mdi-magnify"
            style="max-width: 320px"
            @keyup.enter="loadFileIssues(1)"
            @click:clear="fileIssueSearch = ''; loadFileIssues(1)"
          />
        </div>
        <v-skeleton-loader v-if="loadingFileIssues && !fileIssues.length" type="table-row@4" />
        <template v-else-if="fileIssues.length">
          <v-table density="compact" class="maint-flags-table bg-transparent">
            <thead>
              <tr>
                <th>Level</th>
                <th>File</th>
                <th>Run</th>
                <th>Issues</th>
                <th>Checked</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in fileIssues" :key="item.pk">
                <td>
                  <v-chip size="x-small" variant="flat" :color="item.level === 'error' ? 'error' : 'warning'">
                    {{ item.level }}
                  </v-chip>
                </td>
                <td class="text-caption">
                  <div class="font-weight-medium">{{ item.file_name }}</div>
                  <div class="text-medium-emphasis file-issue-path">{{ item.path }}</div>
                </td>
                <td class="text-caption">
                  <router-link
                    v-if="item.observation_run"
                    :to="`/observation-runs/${item.observation_run}`"
                    class="text-primary text-decoration-none"
                  >
                    {{ item.observation_run_name }}
                  </router-link>
                  <span v-else>—</span>
                </td>
                <td class="text-caption">
                  <div
                    v-for="(issue, idx) in item.issues"
                    :key="idx"
                    :class="issue.level === 'error' ? 'text-error' : 'text-warning'"
                  >
                    {{ issue.message }}
                  </div>
                </td>
                <td class="text-caption text-medium-emphasis text-no-wrap">
                  {{ item.checked_at ? formatRelative(item.checked_at) : '—' }}
                </td>
              </tr>
            </tbody>
          </v-table>
          <v-pagination
            v-if="fileIssuePages > 1"
            v-model="fileIssuePage"
            :length="fileIssuePages"
            density="compact"
            total-visible="7"
            class="mt-2"
            @update:model-value="loadFileIssues"
          />
        </template>
        <p v-else class="text-caption text-medium-emphasis mb-0">
          No problems found{{ fileIssueCounts.checked ? '' : ' (no files checked yet)' }}.
        </p>
      </v-card-text>
    </v-card>

    <v-card
      v-if="canReconcile"
      variant="outlined"
      class="admin-maint-card mb-3"
    >
      <v-card-title class="maint-section-title text-subtitle-2 d-flex align-center flex-wrap" style="gap: 8px">
        <v-icon icon="mdi-robot-off-outline" size="18" />
        <span>Lab course AI notice</span>
        <v-chip size="x-small" :color="aiNoticeConfig.enabled ? 'success' : 'grey'" variant="flat">
          {{ aiNoticeConfig.enabled ? 'Enabled' : 'Disabled' }}
        </v-chip>
        <v-spacer />
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-sync"
          :loading="busy.aiNoticeSync"
          @click="triggerAiNoticeSync"
        >
          Sync now
        </v-btn>
        <v-btn variant="text" prepend-icon="mdi-refresh" :loading="loadingAiNotice" @click="loadAiNotice">
          Refresh
        </v-btn>
      </v-card-title>
      <v-card-text class="maint-section-body pt-0">
        <p class="text-caption text-medium-emphasis mb-1">
          Spectra observed within the last {{ aiNoticeConfig.days }} days<template v-if="aiNoticeConfig.since">
          (not before {{ aiNoticeConfig.since }})</template> get the FITS keyword <code>AINOTICE</code> on ingest
          or in the daily sync; it is removed again afterwards. Exempting a file removes the keyword right away.
          Settings: <code>AI_NOTICE_*</code> in the environment.
        </p>
        <p class="text-caption mb-2 ai-notice-text">“{{ aiNoticeConfig.text }}”</p>
        <div class="d-flex align-center flex-wrap mb-2" style="gap: 8px">
          <v-btn-toggle v-model="aiNoticeStatus" density="compact" variant="outlined" divided mandatory>
            <v-btn value="">All</v-btn>
            <v-btn value="active">In file ({{ aiNoticeCounts.active }})</v-btn>
            <v-btn value="pending">Pending ({{ aiNoticeCounts.pending }})</v-btn>
            <v-btn value="exempt">Exempt ({{ aiNoticeCounts.exempt }})</v-btn>
            <v-btn value="error">Errors ({{ aiNoticeCounts.error }})</v-btn>
          </v-btn-toggle>
          <v-text-field
            v-model="aiNoticeSearch"
            label="Path contains"
            density="compact"
            variant="outlined"
            hide-details
            clearable
            prepend-inner-icon="mdi-magnify"
            style="max-width: 320px"
            @keyup.enter="loadAiNotice(1)"
            @click:clear="aiNoticeSearch = ''; loadAiNotice(1)"
          />
        </div>
        <v-skeleton-loader v-if="loadingAiNotice && !aiNoticeRows.length" type="table-row@4" />
        <template v-else-if="aiNoticeRows.length">
          <v-table density="compact" class="maint-flags-table bg-transparent">
            <thead>
              <tr>
                <th>Status</th>
                <th>File</th>
                <th>Run</th>
                <th>Observed</th>
                <th>Removed after</th>
                <th class="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in aiNoticeRows" :key="item.pk">
                <td>
                  <v-chip size="x-small" variant="flat" :color="aiNoticeStatusColor(item.status)">
                    {{ aiNoticeStatusLabel(item.status) }}
                  </v-chip>
                </td>
                <td class="text-caption">
                  <div class="font-weight-medium">{{ item.file_name }}</div>
                  <div class="text-medium-emphasis file-issue-path">{{ item.path }}</div>
                  <div v-if="item.error" class="text-error">{{ item.error }}</div>
                </td>
                <td class="text-caption">
                  <router-link
                    v-if="item.observation_run"
                    :to="`/observation-runs/${item.observation_run}`"
                    class="text-primary text-decoration-none"
                  >
                    {{ item.observation_run_name }}
                  </router-link>
                  <span v-else>—</span>
                </td>
                <td class="text-caption text-no-wrap">{{ item.obs_date || '—' }}</td>
                <td class="text-caption text-no-wrap">{{ item.expires_at ? item.expires_at.slice(0, 10) : '—' }}</td>
                <td class="text-right">
                  <v-btn
                    size="small"
                    variant="text"
                    :color="item.exempt ? 'primary' : 'warning'"
                    :prepend-icon="item.exempt ? 'mdi-undo' : 'mdi-cancel'"
                    :loading="aiNoticeSaving[item.pk]"
                    @click="setAiNoticeExempt(item, !item.exempt)"
                  >
                    {{ item.exempt ? 'Allow again' : 'Exempt' }}
                  </v-btn>
                </td>
              </tr>
            </tbody>
          </v-table>
          <v-pagination
            v-if="aiNoticePages > 1"
            v-model="aiNoticePage"
            :length="aiNoticePages"
            density="compact"
            total-visible="7"
            class="mt-2"
            @update:model-value="loadAiNotice"
          />
        </template>
        <p v-else class="text-caption text-medium-emphasis mb-0">No affected files.</p>
      </v-card-text>
    </v-card>

    <v-card
      v-if="auth.isSuperuser"
      variant="outlined"
      class="admin-maint-card mb-3"
    >
      <v-card-title class="maint-section-title text-subtitle-2 d-flex align-center">
        <v-icon icon="mdi-flag-variant-outline" size="18" class="mr-1" />
        <span>Override flags</span>
        <v-spacer />
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-refresh"
          :loading="busy.overrideFlags"
          @click="loadOverrideFlags"
        >
          Refresh
        </v-btn>
      </v-card-title>
      <v-card-text class="maint-section-body pt-0">
        <p class="text-caption text-medium-emphasis mb-2">
          Instances with manual override fields. Click a name to open details.
        </p>
        <v-skeleton-loader v-if="loadingOverrideFlags" type="table-row@4" />
        <template v-else-if="hasOverrideFlags">
          <div
            v-for="block in overrideBlocks"
            :key="block.key"
            class="mb-3"
          >
            <div class="text-caption font-weight-medium mb-1">
              {{ block.title }} ({{ block.count }})
            </div>
            <v-table density="compact" class="maint-flags-table bg-transparent">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Fields</th>
                  <th class="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in block.items" :key="`${block.key}-${item.id}`">
                  <td class="text-caption">{{ item.id }}</td>
                  <td class="text-caption">
                    <router-link
                      v-if="block.linkPrefix"
                      :to="`${block.linkPrefix}${item.id}`"
                      class="text-primary text-decoration-none"
                    >
                      {{ item.name }}
                    </router-link>
                    <span v-else>{{ item.name }}</span>
                  </td>
                  <td>
                    <div class="d-flex flex-wrap" style="gap: 4px">
                      <v-chip
                        v-for="field in item.override_fields"
                        :key="field"
                        size="x-small"
                        color="warning"
                        variant="outlined"
                      >
                        {{ field }}
                      </v-chip>
                    </div>
                  </td>
                  <td class="text-right">
                    <v-btn
                      size="x-small"
                      variant="text"
                      icon="mdi-refresh"
                      :loading="clearingOverrides[`${block.modelType}-${item.id}`]"
                      aria-label="Clear all override flags"
                      @click="clearAllOverrides(block.modelType, item.id)"
                    />
                  </td>
                </tr>
              </tbody>
            </v-table>
          </div>
        </template>
        <p v-else class="text-caption text-medium-emphasis mb-0">No override flags set.</p>
      </v-card-text>
    </v-card>

  </v-container>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'
import { useAuthStore } from '@/store/auth'

const notify = useNotifyStore()
const auth = useAuthStore()
const loading = ref(false)
const busy = ref({
  cleanup: false,
  reconcile: false,
  scan: false,
  orphans: false,
  orphanObj: false,
  unlinkNonLight: false,
  banner: false,
  dashboardStats: false,
  plateSolving: false,
  plateSolvingToggle: false,
  reEvaluatePlateSolved: false,
  overrideFlags: false,
  checkFiles: false,
  aiNoticeSync: false,
})
const health = ref({ periodic: {}, settings: {}, features: {} })
const overrideFlagsData = ref(null)
const loadingOverrideFlags = ref(false)
const clearingOverrides = ref({})
const fileIssues = ref([])
const fileIssueCounts = ref({ error: 0, warning: 0, checked: 0, total: 0 })
const fileIssueLevel = ref('')
const fileIssueSearch = ref('')
const fileIssuePage = ref(1)
const fileIssuePages = ref(1)
const loadingFileIssues = ref(false)
const checkOnlyUnchecked = ref(true)
const aiNoticeRows = ref([])
const aiNoticeConfig = ref({ enabled: false, text: '', days: 183, since: '' })
const aiNoticeCounts = ref({ active: 0, pending: 0, exempt: 0, error: 0 })
const aiNoticeStatus = ref('')
const aiNoticeSearch = ref('')
const aiNoticePage = ref(1)
const aiNoticePages = ref(1)
const loadingAiNotice = ref(false)
const aiNoticeSaving = ref({})
const periodic = computed(() => health.value?.periodic ?? {})
const dryRun = ref(true)
const autoRefresh = ref(true)
const refreshSeconds = 10
let refreshTimer = null
const orphDryRun = ref(true)
const orphFixMissing = ref(true)
const orphLimit = ref('')
const scanDryRun = ref(true)
const scanLimit = ref('')
const orphObjDryRun = ref(true)
const unlinkNonLightDryRun = ref(true)

const canCleanup = computed(() => auth.hasPerm('users.acl_maintenance_cleanup') || auth.hasPerm('acl_maintenance_cleanup'))
const canReconcile = computed(() => auth.hasPerm('users.acl_maintenance_reconcile') || auth.hasPerm('acl_maintenance_reconcile'))
const canOrphans = computed(() => auth.hasPerm('users.acl_maintenance_orphans') || auth.hasPerm('acl_maintenance_orphans'))
const canBanner = computed(() => auth.hasPerm('users.acl_banner_manage') || auth.hasPerm('acl_banner_manage'))

const bannerEnabled = ref(false)
const bannerMessage = ref('')
const bannerLevel = ref('warning')
const bannerLevels = ['info', 'success', 'warning', 'error']

const plateSolvingTaskEnabled = computed(() => health.value?.features?.plate_solving_enabled ?? false)

const MAINTENANCE_SECTIONS = [
  {
    key: 'filesystem',
    title: 'Filesystem & ingest',
    icon: 'mdi-folder-multiple-outline',
    tasks: [
      {
        id: 'scan',
        periodicKey: 'scan_missing_filesystem',
        title: 'Scan missing files',
        icon: 'mdi-folder-search',
        color: 'teal',
        beatFeature: 'scan_missing_enabled',
        description: () => `Ingest files under the archive not yet in the DB (incl. .avi/.mov).`,
        controlsType: 'scan',
        visible: () => canReconcile.value,
        summarySpec: [
          { key: 'added', label: 'added' },
          { key: 'checked', label: 'checked' },
          { key: 'skipped_known', label: 'skipped known' },
          { key: 'runs_created', label: 'runs created' },
          { key: 'dry_run', label: 'mode', format: 'mode' },
        ],
      },
      {
        id: 'reconcile',
        periodicKey: 'reconcile_filesystem',
        title: 'Reconcile filesystem',
        icon: 'mdi-compare',
        color: 'cyan',
        description: () => `Verify and repair DataFile paths relative to the data directory.`,
        controlsType: 'reconcile',
        visible: () => canReconcile.value,
        summarySpec: [
          { key: 'updated', label: 'updated' },
          { key: 'files_checked', label: 'checked' },
          { key: 'hash_recoveries', label: 'hash fixes' },
          { key: 'recovery_failures', label: 'failures' },
          { key: 'dry_run', label: 'mode', format: 'mode' },
        ],
      },
    ],
  },
  {
    key: 'downloads',
    title: 'Downloads',
    icon: 'mdi-download-network-outline',
    tasks: [
      {
        id: 'cleanup',
        periodicKey: 'cleanup_expired_downloads',
        title: 'Cleanup expired downloads',
        icon: 'mdi-broom',
        color: 'brown',
        description: () => 'Delete ZIP files for expired DownloadJobs and mark them expired.',
        controlsType: 'cleanup',
        visible: () => canCleanup.value,
        summarySpec: [
          { key: 'cleaned', label: 'cleaned' },
          { key: 'checked', label: 'checked' },
          { key: 'freed_bytes', label: 'freed', format: 'bytes' },
        ],
      },
    ],
  },
  {
    key: 'integrity',
    title: 'Data integrity',
    icon: 'mdi-database-check-outline',
    tasks: [
      {
        id: 'orphans',
        periodicKey: 'cleanup_orphans_hashcheck',
        title: 'Orphans & hash drift',
        icon: 'mdi-magnify-scan',
        color: 'deep-orange',
        beatFeature: 'orphans_hashcheck_enabled',
        description: () => 'Find orphan DataFiles, missing files, and repair missing hashes.',
        controlsType: 'orphans',
        visible: () => canOrphans.value,
        summarySpec: [
          { key: 'orphans_count', label: 'orphans' },
          { key: 'hash_set', label: 'hash set' },
          { key: 'hash_drift', label: 'drift' },
          { key: 'dry_run', label: 'mode', format: 'mode' },
        ],
      },
      {
        id: 'orphanObj',
        periodicKey: 'cleanup_orphan_objects',
        title: 'Cleanup orphan objects',
        icon: 'mdi-account-remove',
        color: 'orange',
        description: () => 'Remove Objects with no DataFiles; refresh first_hjd and run links.',
        controlsType: 'orphanObj',
        visible: () => canOrphans.value,
        summarySpec: [
          { key: 'orphans_found', label: 'found' },
          { key: 'orphans_deleted', label: 'deleted' },
          { key: 'dry_run', label: 'mode', format: 'mode' },
        ],
      },
      {
        id: 'unlink',
        periodicKey: 'unlink_non_light_datafiles',
        title: 'Unlink non-light frames',
        icon: 'mdi-link-off',
        color: 'amber',
        description: () => 'Remove Object links for flats, darks, bias, and other non-Light DataFiles.',
        controlsType: 'unlink',
        visible: () => canOrphans.value,
        summarySpec: [
          { key: 'files_found', label: 'found' },
          { key: 'unlinks_done', label: 'unlinked' },
          { key: 'dry_run', label: 'mode', format: 'mode' },
        ],
      },
    ],
  },
  {
    key: 'pipeline',
    title: 'Stats & plate solving',
    icon: 'mdi-pipeline',
    tasks: [
      {
        id: 'dashboard',
        periodicKey: 'refresh_dashboard_stats',
        title: 'Dashboard stats',
        icon: 'mdi-chart-box-outline',
        color: 'blue',
        description: () => 'Pre-compute cached dashboard statistics for large archives.',
        controlsType: 'dashboard',
        visible: () => canReconcile.value,
        summarySpec: [
          { key: 'files.total', label: 'files', format: 'nested' },
          { key: 'objects.total', label: 'objects', format: 'nested' },
          { key: 'runs.total', label: 'runs', format: 'nested' },
          { key: 'storage_size_tb', label: 'storage', format: 'storage_tb' },
        ],
      },
      {
        id: 'plate',
        periodicKey: 'plate_solve_pending_files',
        title: 'Plate solving',
        icon: 'mdi-star-four-points',
        color: 'indigo',
        description: () => 'Plate-solve Light frames in batches via Celery Beat.',
        controlsType: 'plate',
        visible: () => canReconcile.value,
        summarySpec: [
          { key: 'processed', label: 'processed' },
          { key: 'succeeded', label: 'ok' },
          { key: 'failed', label: 'failed' },
        ],
      },
      {
        id: 'reEvaluate',
        periodicKey: 're_evaluate_plate_solved_files',
        title: 'Re-evaluate plate-solved',
        icon: 'mdi-refresh',
        color: 'purple',
        description: () => 'Re-run object association when WCS differs from header (Beat every 2h when enabled).',
        controlsType: 'reEvaluate',
        visible: () => canReconcile.value && !!health.value?.features?.plate_solving_enabled,
        summarySpec: [
          { key: 'evaluated', label: 'evaluated' },
          { key: 'skipped', label: 'skipped' },
          { key: 'errors', label: 'errors' },
        ],
      },
    ],
  },
]

const visibleSections = computed(() =>
  MAINTENANCE_SECTIONS.map((section) => ({
    ...section,
    tasks: section.tasks
      .filter((t) => t.visible())
      .map((t) => ({
        ...t,
        description: typeof t.description === 'function' ? t.description() : t.description,
      })),
  })).filter((s) => s.tasks.length > 0),
)

const hasOverrideFlags = computed(() => {
  const d = overrideFlagsData.value
  if (!d) return false
  return (d.run?.count > 0) || (d.datafile?.count > 0) || (d.object?.count > 0)
})

const overrideBlocks = computed(() => {
  const d = overrideFlagsData.value
  if (!d) return []
  return [
    { key: 'run', title: 'Observation runs', modelType: 'run', count: d.run?.count ?? 0, items: d.run?.items ?? [], linkPrefix: '/observation-runs/' },
    { key: 'datafile', title: 'Data files', modelType: 'datafile', count: d.datafile?.count ?? 0, items: d.datafile?.items ?? [], linkPrefix: null },
    { key: 'object', title: 'Objects', modelType: 'object', count: d.object?.count ?? 0, items: d.object?.items ?? [], linkPrefix: '/objects/' },
  ].filter((b) => b.count > 0)
})

function nestedGet(obj, path) {
  return path.split('.').reduce((o, k) => (o != null ? o[k] : undefined), obj)
}

function summaryRows(periodicKey, spec) {
  const data = periodic.value[periodicKey]?.data
  if (!data || !spec?.length) return []
  return spec.map(({ key, label, format }) => {
    let value = nestedGet(data, key)
    if (format === 'mode') value = data.dry_run ? 'dry' : 'apply'
    else if (format === 'bytes') value = humanBytes(value || 0)
    else if (format === 'storage_tb') {
      value = typeof value === 'number' ? `${value.toFixed(2)} TB` : '—'
    } else if (format === 'nested') {
      value = value ?? '—'
    } else {
      value = value ?? 0
    }
    return { label, value }
  })
}

const refreshHealth = async () => {
  loading.value = true
  try {
    health.value = await api.adminHealth()
  } catch {
    try { notify.error('Failed to load health') } catch { /* ignore */ }
  } finally {
    loading.value = false
  }
}

const scheduleRefresh = () => {
  stopRefresh()
  if (autoRefresh.value) {
    refreshTimer = setInterval(refreshHealth, refreshSeconds * 1000)
  }
}

const stopRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

const triggerOrphans = async () => {
  busy.value.orphans = true
  try {
    const limitVal = parseInt(String(orphLimit.value), 10)
    const opts = {
      dry_run: !!orphDryRun.value,
      fix_missing_hashes: !!orphFixMissing.value,
      limit: Number.isFinite(limitVal) && limitVal > 0 ? limitVal : null,
    }
    await api.adminMaintenanceOrphansHashcheck(opts)
    notify.success(`Scan enqueued (${opts.dry_run ? 'dry' : 'apply'})`)
  } catch {
    notify.error('Failed to enqueue scan')
  } finally {
    busy.value.orphans = false
    setTimeout(refreshHealth, 1500)
  }
}

const loadBanner = async () => {
  busy.value.banner = true
  try {
    const b = await api.adminGetBanner()
    bannerEnabled.value = !!b?.enabled
    bannerMessage.value = String(b?.message || '')
    bannerLevel.value = String(b?.level || 'warning')
  } catch {
    notify.error('Failed to load banner')
  } finally {
    busy.value.banner = false
  }
}

const saveBanner = async () => {
  busy.value.banner = true
  try {
    await api.adminSetBanner({ enabled: !!bannerEnabled.value, message: bannerMessage.value, level: bannerLevel.value })
    notify.success('Banner saved')
  } catch {
    notify.error('Failed to save banner')
  } finally {
    busy.value.banner = false
  }
}

const clearBanner = async () => {
  busy.value.banner = true
  try {
    await api.adminClearBanner()
    bannerEnabled.value = false
    bannerMessage.value = ''
    notify.success('Banner cleared')
  } catch {
    notify.error('Failed to clear banner')
  } finally {
    busy.value.banner = false
  }
}

const triggerCleanup = async () => {
  busy.value.cleanup = true
  try {
    await api.adminMaintenanceCleanup()
    notify.success('Cleanup enqueued')
  } catch {
    notify.error('Failed to enqueue cleanup')
  } finally {
    busy.value.cleanup = false
    setTimeout(refreshHealth, 1500)
  }
}

const triggerReconcile = async () => {
  busy.value.reconcile = true
  try {
    await api.adminMaintenanceReconcile(dryRun.value)
    notify.success(`Reconcile enqueued (${dryRun.value ? 'dry run' : 'apply'})`)
  } catch {
    notify.error('Failed to enqueue reconcile')
  } finally {
    busy.value.reconcile = false
    setTimeout(refreshHealth, 1500)
  }
}

const triggerScanMissing = async () => {
  busy.value.scan = true
  try {
    const limitVal = parseInt(String(scanLimit.value), 10)
    const opts = {
      dry_run: !!scanDryRun.value,
      limit: Number.isFinite(limitVal) && limitVal > 0 ? limitVal : null,
    }
    await api.adminMaintenanceScanMissing(opts)
    notify.success(`Scan enqueued (${opts.dry_run ? 'dry' : 'apply'})`)
  } catch {
    notify.error('Failed to enqueue scan')
  } finally {
    busy.value.scan = false
    setTimeout(refreshHealth, 1500)
  }
}

const triggerOrphanObjects = async () => {
  busy.value.orphanObj = true
  try {
    const opts = { dry_run: !!orphObjDryRun.value }
    await api.adminMaintenanceOrphanObjects(opts)
    notify.success(`Orphan objects cleanup enqueued (${opts.dry_run ? 'dry' : 'apply'})`)
  } catch {
    notify.error('Failed to enqueue orphan objects cleanup')
  } finally {
    busy.value.orphanObj = false
    setTimeout(refreshHealth, 1500)
  }
}

const triggerUnlinkNonLight = async () => {
  busy.value.unlinkNonLight = true
  try {
    const opts = { dry_run: !!unlinkNonLightDryRun.value }
    await api.adminMaintenanceUnlinkNonLightDatafiles(opts)
    notify.success(`Unlink enqueued (${opts.dry_run ? 'dry' : 'apply'})`)
  } catch {
    notify.error('Failed to enqueue unlink task')
  } finally {
    busy.value.unlinkNonLight = false
    setTimeout(refreshHealth, 1500)
  }
}

const triggerDashboardStats = async () => {
  busy.value.dashboardStats = true
  try {
    await api.adminMaintenanceRefreshDashboardStats()
    notify.success('Dashboard stats refresh enqueued')
  } catch {
    notify.error('Failed to enqueue dashboard stats refresh')
  } finally {
    busy.value.dashboardStats = false
    setTimeout(refreshHealth, 1500)
  }
}

const togglePlateSolvingTask = async (enabled) => {
  busy.value.plateSolvingToggle = true
  try {
    await api.setPlateSolvingTaskEnabled(enabled)
    notify.success(enabled ? 'Plate solving task enabled' : 'Plate solving task disabled')
    setTimeout(refreshHealth, 500)
  } catch {
    notify.error('Failed to update plate solving task status')
  } finally {
    busy.value.plateSolvingToggle = false
  }
}

const triggerPlateSolving = async () => {
  busy.value.plateSolving = true
  try {
    await api.adminMaintenanceTriggerPlateSolve()
    notify.success('Plate solving task enqueued')
  } catch {
    notify.error('Failed to enqueue plate solving task')
  } finally {
    busy.value.plateSolving = false
    setTimeout(refreshHealth, 1500)
  }
}

const triggerReEvaluatePlateSolved = async () => {
  busy.value.reEvaluatePlateSolved = true
  try {
    await api.adminMaintenanceReEvaluatePlateSolved()
    notify.success('Re-evaluate task enqueued')
  } catch {
    notify.error('Failed to enqueue re-evaluate task')
  } finally {
    busy.value.reEvaluatePlateSolved = false
    setTimeout(refreshHealth, 1500)
  }
}

const taskStatusColor = (item) => {
  if (!item) return 'secondary'
  if (item.last_error) return 'error'
  if (item.last_run) return 'success'
  return 'secondary'
}

const taskStatusLabel = (item) => {
  if (!item) return '—'
  if (item.last_error) return 'ERROR'
  if (item.last_run) return 'OK'
  return '—'
}

const formatRelative = (iso, ageSec) => {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    const diff = typeof ageSec === 'number' ? ageSec : Math.max(0, Math.round((Date.now() - d.getTime()) / 1000))
    if (diff < 60) return `${diff}s ago`
    const m = Math.floor(diff / 60)
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    return `${Math.floor(h / 24)}d ago`
  } catch {
    return iso
  }
}

const humanBytes = (n) => {
  if (!n || typeof n !== 'number' || !isFinite(n) || n < 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

const FILE_ISSUES_PAGE_SIZE = 50

const loadFileIssues = async (page) => {
  if (!canReconcile.value) return
  if (typeof page === 'number') fileIssuePage.value = page
  loadingFileIssues.value = true
  try {
    const params = { page: fileIssuePage.value, page_size: FILE_ISSUES_PAGE_SIZE }
    if (fileIssueLevel.value) params.level = fileIssueLevel.value
    if (fileIssueSearch.value) params.search = fileIssueSearch.value
    const data = await api.adminFileIssues(params)
    fileIssues.value = data?.results || []
    fileIssueCounts.value = data?.counts || fileIssueCounts.value
    fileIssuePages.value = Math.max(1, Math.ceil((data?.count || 0) / FILE_ISSUES_PAGE_SIZE))
  } catch {
    notify.error('Failed to load file issues')
  } finally {
    loadingFileIssues.value = false
  }
}

const triggerCheckFiles = async () => {
  busy.value.checkFiles = true
  try {
    await api.adminMaintenanceCheckFiles({ only_unchecked: checkOnlyUnchecked.value })
    notify.success(`File check enqueued (${checkOnlyUnchecked.value ? 'unchecked files' : 'all files'})`)
  } catch {
    notify.error('Failed to enqueue file check')
  } finally {
    busy.value.checkFiles = false
    setTimeout(refreshHealth, 1500)
  }
}

watch(fileIssueLevel, () => loadFileIssues(1))

const AI_NOTICE_PAGE_SIZE = 50
const AI_NOTICE_STATUS = {
  active: { label: 'In file', color: 'success' },
  pending: { label: 'Pending', color: 'info' },
  exempt: { label: 'Exempt', color: 'grey' },
  error: { label: 'Error', color: 'error' },
}
const aiNoticeStatusLabel = (status) => AI_NOTICE_STATUS[status]?.label || status
const aiNoticeStatusColor = (status) => AI_NOTICE_STATUS[status]?.color || 'grey'

const loadAiNotice = async (page) => {
  if (!canReconcile.value) return
  if (typeof page === 'number') aiNoticePage.value = page
  loadingAiNotice.value = true
  try {
    const params = { page: aiNoticePage.value, page_size: AI_NOTICE_PAGE_SIZE }
    if (aiNoticeStatus.value) params.status = aiNoticeStatus.value
    if (aiNoticeSearch.value) params.search = aiNoticeSearch.value
    const data = await api.adminAiNotice(params)
    aiNoticeRows.value = data?.results || []
    aiNoticeConfig.value = data?.config || aiNoticeConfig.value
    aiNoticeCounts.value = data?.counts || aiNoticeCounts.value
    aiNoticePages.value = Math.max(1, Math.ceil((data?.count || 0) / AI_NOTICE_PAGE_SIZE))
  } catch {
    notify.error('Failed to load AI notice files')
  } finally {
    loadingAiNotice.value = false
  }
}

const triggerAiNoticeSync = async () => {
  busy.value.aiNoticeSync = true
  try {
    await api.adminAiNoticeSync()
    notify.success('AI notice sync enqueued')
  } catch {
    notify.error('Failed to enqueue AI notice sync')
  } finally {
    busy.value.aiNoticeSync = false
    setTimeout(refreshHealth, 1500)
  }
}

const setAiNoticeExempt = async (item, exempt) => {
  aiNoticeSaving.value = { ...aiNoticeSaving.value, [item.pk]: true }
  try {
    const row = await api.adminAiNoticeExempt(item.pk, exempt)
    if (row?.error) {
      notify.error(`Saved, but the file could not be changed: ${row.error}`)
    } else {
      notify.success(exempt ? 'File exempted, keyword removed' : 'File allowed again')
    }
    await loadAiNotice()
  } catch {
    notify.error('Failed to update the file')
  } finally {
    aiNoticeSaving.value = { ...aiNoticeSaving.value, [item.pk]: false }
  }
}

watch(aiNoticeStatus, () => loadAiNotice(1))

const loadOverrideFlags = async () => {
  loadingOverrideFlags.value = true
  busy.value.overrideFlags = true
  try {
    overrideFlagsData.value = await api.adminListOverrideFlags()
  } catch {
    try { notify.error('Failed to load override flags') } catch { /* ignore */ }
  } finally {
    loadingOverrideFlags.value = false
    busy.value.overrideFlags = false
  }
}

const clearAllOverrides = async (modelType, instanceId) => {
  const key = `${modelType}-${instanceId}`
  clearingOverrides.value[key] = true
  try {
    await api.adminClearAllOverrides(modelType, instanceId)
    notify.success('All override flags cleared')
    await loadOverrideFlags()
  } catch {
    notify.error('Failed to clear override flags')
  } finally {
    clearingOverrides.value[key] = false
  }
}

onMounted(() => {
  refreshHealth()
  scheduleRefresh()
  loadBanner()
  loadOverrideFlags()
  loadFileIssues()
  loadAiNotice()
})

onBeforeUnmount(() => {
  stopRefresh()
})
</script>

<style scoped>
.admin-page {
  max-width: 1280px;
}

.admin-maint-card {
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.admin-maint-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.35);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
}

.admin-maint-card--featured {
  border-width: 2px;
  border-color: rgba(var(--v-theme-primary), 0.35);
  background: linear-gradient(
    145deg,
    rgba(var(--v-theme-primary), 0.06) 0%,
    rgba(var(--v-theme-surface), 1) 55%
  );
}

.maint-section-title {
  padding: 10px 14px 4px;
  min-height: unset;
  line-height: 1.3;
}

.maint-section-body {
  padding: 6px 14px 12px;
}

.maint-task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 8px;
}

.maint-task-cell {
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.03);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.maint-task-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  margin-bottom: 4px;
}

.maint-task-head .ml-auto {
  margin-left: auto;
}

.maint-task-desc {
  line-height: 1.35;
  margin-bottom: 6px !important;
}

.maint-toolbar :deep(.v-btn),
.maint-actions :deep(.v-btn),
.maint-section-title :deep(.v-btn) {
  min-height: 36px;
  height: auto !important;
  padding-block: 7px;
}

.maint-toolbar :deep(.v-btn__prepend),
.maint-actions :deep(.v-btn__prepend),
.maint-section-title :deep(.v-btn__prepend) {
  margin-inline-end: 6px;
}

.maint-toolbar :deep(.v-btn__prepend .v-icon),
.maint-actions :deep(.v-btn__prepend .v-icon),
.maint-section-title :deep(.v-btn__prepend .v-icon) {
  font-size: 1.125rem;
}

.maint-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}

/* Align switches with action button height */
.maint-actions :deep(.v-switch) {
  flex: 0 1 auto;
}

.maint-limit-field {
  max-width: 100px;
  flex: 0 1 100px;
}

.maint-banner-level {
  max-width: 140px;
  flex: 0 1 140px;
}

.maint-code {
  font-size: 0.8125rem;
}

.maint-kv {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 1px 8px;
  margin: 0;
  font-size: 0.75rem;
  line-height: 1.35;
}

.maint-kv dt {
  margin: 0;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-weight: 400;
}

.maint-kv dd {
  margin: 0;
  word-break: break-word;
}

.ai-notice-text {
  font-style: italic;
}

.file-issue-path {
  word-break: break-all;
}

.maint-flags-table :deep(th),
.maint-flags-table :deep(td) {
  padding: 4px 8px !important;
  height: auto !important;
  font-size: 0.8125rem;
}

.maint-flags-table :deep(th) {
  text-transform: uppercase;
  letter-spacing: 0.03em;
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-weight: 600;
}
</style>
