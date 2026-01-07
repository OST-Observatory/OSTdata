<template>
  <v-container fluid class="py-4">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h5">Admin · Maintenance</h1>
      <div class="d-flex align-center" style="gap: 8px">
        <v-switch
          v-model="autoRefresh"
          color="primary"
          hide-details
          inset
          density="comfortable"
          :label="`Auto refresh ${refreshSeconds}s`"
        />
        <v-btn color="primary" variant="outlined" prepend-icon="mdi-refresh" :loading="loading" @click="refreshHealth">
          Refresh
        </v-btn>
      </div>
    </div>

    <v-row>
      <v-col cols="12" md="6" v-if="canReconcile">
        <v-card class="mb-4">
          <v-card-title class="text-h6">
            <div class="d-flex align-center" style="gap: 8px">
              <span>Scan missing files (ingest)</span>
              <v-chip
                size="x-small"
                :color="taskStatusColor(health.periodic?.scan_missing_filesystem)"
                variant="flat"
              >
                {{ taskStatusLabel(health.periodic?.scan_missing_filesystem) }}
              </v-chip>
            </div>
          </v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-2">
              Walks the archive under <code>{{ health.settings?.DATA_DIRECTORY || '—' }}</code> to ingest files not yet in the DB (incl. .avi/.mov).
            </div>
            <div class="d-flex align-center mb-2" style="gap: 12px; flex-wrap: wrap">
              <v-switch v-model="scanDryRun" inset hide-details color="primary" :label="`Dry run`" />
              <v-text-field
                v-model="scanLimit"
                label="Limit (optional)"
                type="number"
                min="1"
                density="comfortable"
                variant="outlined"
                hide-details
                style="max-width: 180px"
              />
              <v-btn color="primary" prepend-icon="mdi-folder-search" :loading="busy.scan" @click="triggerScanMissing">
                Run scan
              </v-btn>
            </div>
            <div class="text-caption text-medium-emphasis">
              Last run:
              <span v-if="periodic?.scan_missing_filesystem?.last_run">
                {{ formatRelative(periodic.scan_missing_filesystem.last_run, periodic.scan_missing_filesystem.age_seconds) }}
              </span>
              <span v-else>—</span>
            </div>
            <div v-if="health.periodic?.scan_missing_filesystem?.data" class="mt-2">
              <div class="text-caption text-medium-emphasis">Summary</div>
              <div class="text-caption">
                added: {{ health.periodic.scan_missing_filesystem.data.added ?? 0 }},
                checked: {{ health.periodic.scan_missing_filesystem.data.checked ?? 0 }},
                skipped_known: {{ health.periodic.scan_missing_filesystem.data.skipped_known ?? 0 }},
                skipped_unknown_type: {{ health.periodic.scan_missing_filesystem.data.skipped_unknown_type ?? 0 }},
                runs_seen: {{ health.periodic.scan_missing_filesystem.data.runs_seen ?? 0 }},
                runs_created: {{ health.periodic.scan_missing_filesystem.data.runs_created ?? 0 }},
                mode: {{ health.periodic.scan_missing_filesystem.data.dry_run ? 'dry' : 'apply' }}
              </div>
            </div>
            <div v-if="health.periodic?.scan_missing_filesystem?.last_error" class="text-error text-caption mt-1">
              {{ health.periodic.scan_missing_filesystem.last_error }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" v-if="canCleanup">
        <v-card class="mb-4">
          <v-card-title class="text-h6">
            <div class="d-flex align-center" style="gap: 8px">
              <span>Cleanup expired downloads</span>
              <v-chip
                size="x-small"
                :color="taskStatusColor(health.periodic?.cleanup_expired_downloads)"
                variant="flat"
              >
                {{ taskStatusLabel(health.periodic?.cleanup_expired_downloads) }}
              </v-chip>
            </div>
          </v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-2">
              Deletes ZIP files for expired DownloadJobs and marks them as expired.
            </div>
            <div class="mb-2">
              <v-btn color="primary" prepend-icon="mdi-broom" :loading="busy.cleanup" @click="triggerCleanup">
                Run cleanup
              </v-btn>
            </div>
            <div class="text-caption text-medium-emphasis">
              Last run:
              <span v-if="periodic?.cleanup_expired_downloads?.last_run">
                {{ formatRelative(periodic.cleanup_expired_downloads.last_run, periodic.cleanup_expired_downloads.age_seconds) }}
              </span>
              <span v-else>—</span>
            </div>
            <div v-if="health.periodic?.cleanup_expired_downloads?.data" class="mt-2">
              <div class="text-caption text-medium-emphasis">Summary</div>
              <div class="text-caption">
                cleaned: {{ health.periodic.cleanup_expired_downloads.data.cleaned ?? 0 }},
                checked: {{ health.periodic.cleanup_expired_downloads.data.checked ?? 0 }},
                freed: {{ humanBytes(health.periodic.cleanup_expired_downloads.data.freed_bytes || 0) }}
              </div>
            </div>
            <div v-if="health.periodic?.cleanup_expired_downloads?.last_error" class="text-error text-caption mt-1">
              {{ health.periodic.cleanup_expired_downloads.last_error }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" v-if="canReconcile">
        <v-card class="mb-4">
          <v-card-title class="text-h6">
            <div class="d-flex align-center" style="gap: 8px">
              <span>Reconcile filesystem</span>
              <v-chip
                size="x-small"
                :color="taskStatusColor(health.periodic?.reconcile_filesystem)"
                variant="flat"
              >
                {{ taskStatusLabel(health.periodic?.reconcile_filesystem) }}
              </v-chip>
            </div>
          </v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-2">
              Verify and repair file paths for DataFiles relative to the base <code>{{ health.settings?.DATA_DIRECTORY || '—' }}</code>.
            </div>
            <div class="d-flex align-center mb-2" style="gap: 12px">
              <v-switch v-model="dryRun" inset hide-details color="primary" :label="`Dry run`" />
              <v-btn color="primary" prepend-icon="mdi-compare" :loading="busy.reconcile" @click="triggerReconcile">
                Run reconcile
              </v-btn>
            </div>
            <div class="text-caption text-medium-emphasis">
              Last run:
              <span v-if="periodic?.reconcile_filesystem?.last_run">
                {{ formatRelative(periodic.reconcile_filesystem.last_run, periodic.reconcile_filesystem.age_seconds) }}
              </span>
              <span v-else>—</span>
            </div>
            <div v-if="health.periodic?.reconcile_filesystem?.data" class="mt-2">
              <div class="text-caption text-medium-emphasis">Summary</div>
              <div class="text-caption">
                updated: {{ health.periodic.reconcile_filesystem.data.updated ?? 0 }},
                files_checked: {{ health.periodic.reconcile_filesystem.data.files_checked ?? 0 }},
                already_ok: {{ health.periodic.reconcile_filesystem.data.already_ok ?? 0 }},
                prefix_rewrites: {{ health.periodic.reconcile_filesystem.data.prefix_rewrites ?? 0 }},
                hash_recoveries: {{ health.periodic.reconcile_filesystem.data.hash_recoveries ?? 0 }},
                ambiguous: {{ health.periodic.reconcile_filesystem.data.ambiguous_matches ?? 0 }},
                failures: {{ health.periodic.reconcile_filesystem.data.recovery_failures ?? 0 }},
                runs_missing: {{ health.periodic.reconcile_filesystem.data.runs_missing ?? 0 }},
                mode: {{ health.periodic.reconcile_filesystem.data.dry_run ? 'dry' : 'apply' }}
              </div>
            </div>
            <div v-if="health.periodic?.reconcile_filesystem?.last_error" class="text-error text-caption mt-1">
              {{ health.periodic.reconcile_filesystem.last_error }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" v-if="canOrphans">
        <v-card class="mb-4">
          <v-card-title class="text-h6">
            <div class="d-flex align-center" style="gap: 8px">
              <span>Orphans & Hash-Drift Check</span>
              <v-chip
                size="x-small"
                :color="taskStatusColor(periodic?.cleanup_orphans_hashcheck)"
                variant="flat"
              >
                {{ taskStatusLabel(periodic?.cleanup_orphans_hashcheck) }}
              </v-chip>
            </div>
          </v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-2">
              Scan DataFiles for orphans (missing run or missing file) and check/repair missing hashes.
            </div>
            <div class="d-flex align-center mb-2" style="gap: 12px; flex-wrap: wrap">
              <v-switch v-model="orphDryRun" inset hide-details color="primary" :label="`Dry run`" />
              <v-switch v-model="orphFixMissing" inset hide-details color="primary" :label="`Fix missing hashes`" />
              <v-text-field
                v-model="orphLimit"
                label="Limit (optional)"
                type="number"
                min="1"
                density="comfortable"
                variant="outlined"
                hide-details
                style="max-width: 180px"
              />
              <v-btn color="primary" prepend-icon="mdi-magnify-scan" :loading="busy.orphans" @click="triggerOrphans">
                Run scan
              </v-btn>
            </div>
            <div class="text-caption text-medium-emphasis">
              Last run:
              <span v-if="periodic?.cleanup_orphans_hashcheck?.last_run">
                {{ formatRelative(periodic.cleanup_orphans_hashcheck.last_run, periodic.cleanup_orphans_hashcheck.age_seconds) }}
              </span>
              <span v-else>—</span>
            </div>
            <div v-if="periodic?.cleanup_orphans_hashcheck?.data" class="mt-2">
              <div class="text-caption text-medium-emphasis">Summary</div>
              <div class="text-caption">
                files_checked: {{ periodic.cleanup_orphans_hashcheck.data.files_checked ?? 0 }},
                orphans: {{ periodic.cleanup_orphans_hashcheck.data.orphans_count ?? 0 }},
                orphans_deleted: {{ periodic.cleanup_orphans_hashcheck.data.orphans_deleted ?? 0 }},
                files_missing: {{ periodic.cleanup_orphans_hashcheck.data.files_missing ?? 0 }},
                missing_deleted: {{ periodic.cleanup_orphans_hashcheck.data.missing_deleted ?? 0 }},
                hash_checked: {{ periodic.cleanup_orphans_hashcheck.data.hash_checked ?? 0 }},
                hash_set: {{ periodic.cleanup_orphans_hashcheck.data.hash_set ?? 0 }},
                hash_drift: {{ periodic.cleanup_orphans_hashcheck.data.hash_drift ?? 0 }},
                sizes_updated: {{ periodic.cleanup_orphans_hashcheck.data.sizes_updated ?? 0 }},
                mode: {{ periodic.cleanup_orphans_hashcheck.data.dry_run ? 'dry' : 'apply' }}
              </div>
            </div>
            <div v-if="periodic?.cleanup_orphans_hashcheck?.last_error" class="text-error text-caption mt-1">
              {{ periodic.cleanup_orphans_hashcheck.last_error }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" v-if="canOrphans">
        <v-card class="mb-4">
          <v-card-title class="text-h6">
            <div class="d-flex align-center" style="gap: 8px">
              <span>Cleanup Orphan Objects</span>
              <v-chip
                size="x-small"
                :color="taskStatusColor(periodic?.cleanup_orphan_objects)"
                variant="flat"
              >
                {{ taskStatusLabel(periodic?.cleanup_orphan_objects) }}
              </v-chip>
            </div>
          </v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-2">
              Removes Objects that have no associated DataFiles (orphans after file deletions). Also recalculates first_hjd and cleans stale observation_run links.
            </div>
            <div class="d-flex align-center mb-2" style="gap: 12px; flex-wrap: wrap">
              <v-switch v-model="orphObjDryRun" inset hide-details color="primary" :label="`Dry run`" />
              <v-btn color="primary" prepend-icon="mdi-account-remove" :loading="busy.orphanObj" @click="triggerOrphanObjects">
                Run cleanup
              </v-btn>
            </div>
            <div class="text-caption text-medium-emphasis">
              Last run:
              <span v-if="periodic?.cleanup_orphan_objects?.last_run">
                {{ formatRelative(periodic.cleanup_orphan_objects.last_run, periodic.cleanup_orphan_objects.age_seconds) }}
              </span>
              <span v-else>—</span>
            </div>
            <div v-if="periodic?.cleanup_orphan_objects?.data" class="mt-2">
              <div class="text-caption text-medium-emphasis">Summary</div>
              <div class="text-caption">
                objects_checked: {{ periodic.cleanup_orphan_objects.data.objects_checked ?? 0 }},
                orphans_found: {{ periodic.cleanup_orphan_objects.data.orphans_found ?? 0 }},
                orphans_deleted: {{ periodic.cleanup_orphan_objects.data.orphans_deleted ?? 0 }},
                first_hjd_updated: {{ periodic.cleanup_orphan_objects.data.first_hjd_updated ?? 0 }},
                run_links_cleaned: {{ periodic.cleanup_orphan_objects.data.observation_run_cleaned ?? 0 }},
                mode: {{ periodic.cleanup_orphan_objects.data.dry_run ? 'dry' : 'apply' }}
              </div>
            </div>
            <div v-if="periodic?.cleanup_orphan_objects?.last_error" class="text-error text-caption mt-1">
              {{ periodic.cleanup_orphan_objects.last_error }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="6" v-if="canReconcile">
        <v-card class="mb-4">
          <v-card-title class="text-h6">
            <div class="d-flex align-center" style="gap: 8px">
              <span>Refresh Dashboard Stats</span>
              <v-chip
                size="x-small"
                :color="taskStatusColor(periodic?.refresh_dashboard_stats)"
                variant="flat"
              >
                {{ taskStatusLabel(periodic?.refresh_dashboard_stats) }}
              </v-chip>
            </div>
          </v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-2">
              Pre-compute and cache dashboard statistics (file counts, object types, storage size). Useful for large archives.
            </div>
            <div class="mb-2">
              <v-btn color="primary" prepend-icon="mdi-chart-box-outline" :loading="busy.dashboardStats" @click="triggerDashboardStats">
                Refresh now
              </v-btn>
            </div>
            <div class="text-caption text-medium-emphasis">
              Last run:
              <span v-if="periodic?.refresh_dashboard_stats?.last_run">
                {{ formatRelative(periodic.refresh_dashboard_stats.last_run, periodic.refresh_dashboard_stats.age_seconds) }}
              </span>
              <span v-else>—</span>
            </div>
            <div v-if="periodic?.refresh_dashboard_stats?.data" class="mt-2">
              <div class="text-caption text-medium-emphasis">Summary</div>
              <div class="text-caption">
                files: {{ periodic.refresh_dashboard_stats.data.files?.total ?? '—' }},
                objects: {{ periodic.refresh_dashboard_stats.data.objects?.total ?? '—' }},
                runs: {{ periodic.refresh_dashboard_stats.data.runs?.total ?? '—' }},
                storage: {{ periodic.refresh_dashboard_stats.data.storage_size_tb ? periodic.refresh_dashboard_stats.data.storage_size_tb.toFixed(2) + ' TB' : '—' }}
              </div>
            </div>
            <div v-if="periodic?.refresh_dashboard_stats?.last_error" class="text-error text-caption mt-1">
              {{ periodic.refresh_dashboard_stats.last_error }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
    <v-row>
      <v-col cols="12" md="12" v-if="auth.isAdmin">
        <v-card class="mb-4">
          <v-card-title class="text-h6">
            <div class="d-flex align-center justify-space-between" style="width: 100%">
              <span>Override Flags Overview</span>
              <v-btn color="primary" variant="outlined" prepend-icon="mdi-refresh" size="small" :loading="busy.overrideFlags" @click="loadOverrideFlags">
                Refresh
              </v-btn>
            </div>
          </v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-2">
              List of all instances (runs, datafiles, objects) that have override flags set. Click on an item to navigate to its detail page.
            </div>
            <v-skeleton-loader v-if="loadingOverrideFlags" type="table"></v-skeleton-loader>
            <template v-else>
              <div v-if="overrideFlagsData && (overrideFlagsData.run?.count > 0 || overrideFlagsData.datafile?.count > 0 || overrideFlagsData.object?.count > 0)">
                <!-- Observation Runs -->
                <div v-if="overrideFlagsData.run?.count > 0" class="mb-4">
                  <h3 class="text-subtitle-1 mb-2">Observation Runs ({{ overrideFlagsData.run.count }})</h3>
                  <v-table density="compact">
                    <thead>
                      <tr>
                        <th class="text-primary">ID</th>
                        <th class="text-primary">Name</th>
                        <th class="text-primary">Override Fields</th>
                        <th class="text-primary">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in overrideFlagsData.run.items" :key="`run-${item.id}`">
                        <td>{{ item.id }}</td>
                        <td>
                          <router-link :to="`/observation-runs/${item.id}`" class="text-decoration-none primary--text">
                            {{ item.name }}
                          </router-link>
                        </td>
                        <td>
                          <div class="d-flex flex-wrap gap-1">
                            <v-chip v-for="field in item.override_fields" :key="field" size="x-small" color="warning" variant="outlined">
                              {{ field }}
                            </v-chip>
                          </div>
                        </td>
                        <td>
                          <v-btn
                            size="x-small"
                            variant="text"
                            icon="mdi-refresh"
                            @click="clearAllOverrides('run', item.id)"
                            :loading="clearingOverrides[`run-${item.id}`]"
                            aria-label="Clear all override flags"
                          ></v-btn>
                        </td>
                      </tr>
                    </tbody>
                  </v-table>
                </div>

                <!-- Data Files -->
                <div v-if="overrideFlagsData.datafile?.count > 0" class="mb-4">
                  <h3 class="text-subtitle-1 mb-2">Data Files ({{ overrideFlagsData.datafile.count }})</h3>
                  <v-table density="compact">
                    <thead>
                      <tr>
                        <th class="text-primary">ID</th>
                        <th class="text-primary">Name</th>
                        <th class="text-primary">Override Fields</th>
                        <th class="text-primary">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in overrideFlagsData.datafile.items" :key="`datafile-${item.id}`">
                        <td>{{ item.id }}</td>
                        <td>{{ item.name }}</td>
                        <td>
                          <div class="d-flex flex-wrap gap-1">
                            <v-chip v-for="field in item.override_fields" :key="field" size="x-small" color="warning" variant="outlined">
                              {{ field }}
                            </v-chip>
                          </div>
                        </td>
                        <td>
                          <v-btn
                            size="x-small"
                            variant="text"
                            icon="mdi-refresh"
                            @click="clearAllOverrides('datafile', item.id)"
                            :loading="clearingOverrides[`datafile-${item.id}`]"
                            aria-label="Clear all override flags"
                          ></v-btn>
                        </td>
                      </tr>
                    </tbody>
                  </v-table>
                </div>

                <!-- Objects -->
                <div v-if="overrideFlagsData.object?.count > 0" class="mb-4">
                  <h3 class="text-subtitle-1 mb-2">Objects ({{ overrideFlagsData.object.count }})</h3>
                  <v-table density="compact">
                    <thead>
                      <tr>
                        <th class="text-primary">ID</th>
                        <th class="text-primary">Name</th>
                        <th class="text-primary">Override Fields</th>
                        <th class="text-primary">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="item in overrideFlagsData.object.items" :key="`object-${item.id}`">
                        <td>{{ item.id }}</td>
                        <td>
                          <router-link :to="`/objects/${item.id}`" class="text-decoration-none primary--text">
                            {{ item.name }}
                          </router-link>
                        </td>
                        <td>
                          <div class="d-flex flex-wrap gap-1">
                            <v-chip v-for="field in item.override_fields" :key="field" size="x-small" color="warning" variant="outlined">
                              {{ field }}
                            </v-chip>
                          </div>
                        </td>
                        <td>
                          <v-btn
                            size="x-small"
                            variant="text"
                            icon="mdi-refresh"
                            @click="clearAllOverrides('object', item.id)"
                            :loading="clearingOverrides[`object-${item.id}`]"
                            aria-label="Clear all override flags"
                          ></v-btn>
                        </td>
                      </tr>
                    </tbody>
                  </v-table>
                </div>
              </div>
              <div v-else class="text-caption text-medium-emphasis">
                No override flags set.
              </div>
            </template>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
    <v-row>
      <v-col cols="12" md="12" v-if="canBanner">
        <v-card class="mb-4">
          <v-card-title class="text-h6">Site-wide Banner</v-card-title>
          <v-card-text>
            <div class="text-caption text-medium-emphasis mb-2">
              Show a maintenance notice across the site.
            </div>
            <div class="d-flex align-center mb-2" style="gap: 12px; flex-wrap: wrap">
              <v-switch v-model="bannerEnabled" inset hide-details color="primary" :label="`Enabled`" />
              <v-select
                v-model="bannerLevel"
                :items="bannerLevels"
                label="Level"
                hide-details
                density="comfortable"
                variant="outlined"
                style="max-width: 200px"
              />
            </div>
            <v-textarea
              v-model="bannerMessage"
              label="Banner message"
              variant="outlined"
              auto-grow
              rows="2"
              hide-details
            />
            <div class="mt-3 d-flex align-center" style="gap: 12px">
              <v-btn color="primary" prepend-icon="mdi-content-save" :loading="busy.banner" @click="saveBanner">
                Save
              </v-btn>
              <v-btn color="secondary" variant="outlined" prepend-icon="mdi-refresh" :loading="busy.banner" @click="loadBanner">
                Refresh
              </v-btn>
              <v-btn color="error" variant="text" prepend-icon="mdi-close-circle" :loading="busy.banner" @click="clearBanner">
                Clear
              </v-btn>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'
import { useAuthStore } from '@/store/auth'

const notify = useNotifyStore()
const auth = useAuthStore()
const loading = ref(false)
const busy = ref({ cleanup: false, reconcile: false, scan: false, orphans: false, orphanObj: false, banner: false, dashboardStats: false, overrideFlags: false })
const health = ref({ periodic: {}, settings: {} })
const overrideFlagsData = ref(null)
const loadingOverrideFlags = ref(false)
const clearingOverrides = ref({})
const periodic = computed(() => (health.value && health.value.periodic) ? health.value.periodic : {})
const dryRun = ref(true)
const autoRefresh = ref(true)
const refreshSeconds = 10
let intervalId = null
const orphDryRun = ref(true)
const orphFixMissing = ref(true)
const orphLimit = ref('')
const scanDryRun = ref(true)
const scanLimit = ref('')
const orphObjDryRun = ref(true)

const canCleanup = computed(() => auth.isAdmin || auth.hasPerm('users.acl_maintenance_cleanup') || auth.hasPerm('acl_maintenance_cleanup'))
const canReconcile = computed(() => auth.isAdmin || auth.hasPerm('users.acl_maintenance_reconcile') || auth.hasPerm('acl_maintenance_reconcile'))
const canOrphans = computed(() => auth.isAdmin || auth.hasPerm('users.acl_maintenance_orphans') || auth.hasPerm('acl_maintenance_orphans'))
const canBanner = computed(() => auth.isAdmin || auth.hasPerm('users.acl_banner_manage') || auth.hasPerm('acl_banner_manage'))
// Banner state
const bannerEnabled = ref(false)
const bannerMessage = ref('')
const bannerLevel = ref('warning')
const bannerLevels = ['info','success','warning','error']


const refreshHealth = async () => {
  loading.value = true
  try {
    health.value = await api.adminHealth()
  } catch (e) {
    try { notify.error('Failed to load health') } catch {}
  } finally {
    loading.value = false
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
  } catch (e) {
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
  } catch (e) {
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
  } catch (e) {
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
  } catch (e) {
    notify.error('Failed to clear banner')
  } finally {
    busy.value.banner = false
  }
}

const schedule = () => {
  clear()
  if (autoRefresh.value) {
    intervalId = setInterval(() => {
      refreshHealth()
    }, refreshSeconds * 1000)
  }
}
const clear = () => {
  if (intervalId) {
    clearInterval(intervalId)
    intervalId = null
  }
}

const triggerCleanup = async () => {
  busy.value.cleanup = true
  try {
    await api.adminMaintenanceCleanup()
    notify.success('Cleanup enqueued')
  } catch (e) {
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
  } catch (e) {
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
  } catch (e) {
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
  } catch (e) {
    notify.error('Failed to enqueue orphan objects cleanup')
  } finally {
    busy.value.orphanObj = false
    setTimeout(refreshHealth, 1500)
  }
}

const triggerDashboardStats = async () => {
  busy.value.dashboardStats = true
  try {
    await api.adminMaintenanceRefreshDashboardStats()
    notify.success('Dashboard stats refresh enqueued')
  } catch (e) {
    notify.error('Failed to enqueue dashboard stats refresh')
  } finally {
    busy.value.dashboardStats = false
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
    const days = Math.floor(h / 24)
    return `${days}d ago`
  } catch { return iso }
}

const humanBytes = (n) => {
  if (!n || typeof n !== 'number' || !isFinite(n) || n < 0) return '0 B'
  const units = ['B','KB','MB','GB','TB','PB']
  let i = 0
  let v = n
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

const loadOverrideFlags = async () => {
  loadingOverrideFlags.value = true
  busy.value.overrideFlags = true
  try {
    overrideFlagsData.value = await api.adminListOverrideFlags()
  } catch (e) {
    try { notify.error('Failed to load override flags') } catch {}
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
  } catch (e) {
    notify.error('Failed to clear override flags')
  } finally {
    clearingOverrides.value[key] = false
  }
}

onMounted(() => {
  refreshHealth()
  schedule()
  loadBanner()
  loadOverrideFlags()
})
onBeforeUnmount(() => {
  clear()
})
</script>

<style scoped>
</style>


