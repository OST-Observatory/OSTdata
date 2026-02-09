<template>
  <v-container fluid class="run-detail">
      <h1 class="text-h4 mb-2">{{ run?.name || 'Observation Run' }} <span v-if="dateString" class="text-caption text-secondary">({{ dateString }})</span></h1>
      <v-row class="mb-4">
        <!-- Basic Data -->
        <v-col cols="12" md="5">
          <v-card class="uniform-height">
            <v-card-title class="d-flex align-center justify-space-between">
              Basic Data
              <div class="d-flex align-center" style="gap: 8px">
                <v-btn
                  v-if="canEditRun"
                    icon="mdi-pencil-box"
                  size="small"
                  variant="text"
                  aria-label="Edit observation run"
                  @click="openRunEdit"
                ></v-btn>
                <v-btn
                  v-if="isAuthenticated"
                  icon="mdi-pencil"
                  size="small"
                  variant="text"
                  aria-label="Edit observation type"
                  @click="openObsTypeDialog"
                ></v-btn>
                <v-chip :color="getStatusColor(run?.status || run?.reduction_status)" size="small">
                  {{ run?.status || run?.reduction_status || 'n/a' }}
                </v-chip>
              </div>
            </v-card-title>
            <div class="text-caption text-secondary px-4">Times shown in {{ tzDisplay }}.</div>
            <v-card-text>
              <v-row>
                <v-col cols="12" sm="6">
                  <v-list>
                    <v-list-item>
                      <v-list-item-title>Start</v-list-item-title>
                      <v-list-item-subtitle>{{ formatDate(run?.start_time) }}</v-list-item-subtitle>
                    </v-list-item>
                    <v-list-item>
                      <v-list-item-title>End</v-list-item-title>
                      <v-list-item-subtitle>{{ formatDate(run?.end_time) }}</v-list-item-subtitle>
                    </v-list-item>
                    <v-list-item>
                      <v-list-item-title>Exposure</v-list-item-title>
                      <v-list-item-subtitle>{{ formatExposureTime(run?.expo_time) }}</v-list-item-subtitle>
                    </v-list-item>
                  </v-list>
                </v-col>
                <v-col cols="12" sm="6">
                  <v-list>
                    <v-list-item>
                      <v-list-item-title>Files</v-list-item-title>
                      <v-list-item-subtitle>{{ run?.n_fits }}/{{ run?.n_img }}/{{ run?.n_ser }}</v-list-item-subtitle>
                    </v-list-item>
                    <v-list-item>
                      <v-list-item-title>Observation Type</v-list-item-title>
                      <v-list-item-subtitle>
                        <v-chip
                          v-if="run?.spectroscopy"
                          color="primary"
                          size="small"
                          variant="tonal"
                          class="mr-1"
                        >Spectroscopy</v-chip>
                        <v-chip
                          v-if="run?.photometry"
                          color="primary"
                          size="small"
                          variant="tonal"
                        >Photometry</v-chip>
                        <span v-if="!run?.spectroscopy && !run?.photometry" class="text-secondary">n/a</span>
                      </v-list-item-subtitle>
                    </v-list-item>
                  </v-list>
                </v-col>
              </v-row>
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Notes -->
        <v-col cols="12" md="4">
          <v-card class="uniform-height">
            <v-card-title class="d-flex align-center justify-space-between">
              Notes
              <v-btn
                v-if="isAuthenticated"
                icon="mdi-pencil"
                size="small"
                variant="text"
                aria-label="Edit notes"
                @click="openNotesDialog"
              ></v-btn>
            </v-card-title>
            <v-card-text>
              <v-alert v-if="error" type="error" variant="tonal" class="mb-2">{{ error }}</v-alert>
              <v-skeleton-loader v-if="loading" type="article"></v-skeleton-loader>
              <div v-else v-html="run?.note || '<span class=\'text-grey\'>No notes available</span>'"></div>
            </v-card-text>
          </v-card>
        </v-col>

        <!-- Tags -->
        <v-col cols="12" md="3">
          <v-card class="uniform-height">
            <v-card-title class="d-flex align-center justify-space-between">
              Tags
              <v-btn
                v-if="isAuthenticated"
                icon="mdi-pencil"
                size="small"
                variant="text"
                aria-label="Edit tags"
                @click="openTagDialog"
              ></v-btn>
            </v-card-title>
            <v-card-text>
              <div v-if="Array.isArray(run?.tags) && run.tags.length" class="d-flex flex-wrap gap-2">
                <v-chip
                  v-for="(tag, idx) in run.tags"
                  :key="tag?.pk || tag?.name || idx"
                  :color="tag?.color"
                  variant="outlined"
                  size="small"
                >
                  {{ tag?.name || tag }}
                </v-chip>
              </div>
              <div v-else class="text-grey">No tags assigned</div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <!-- Override Flags (Admin only) -->
      <v-row v-if="isAdmin" @click="expandOverrideFlagsIfCollapsed" :class="{ 'expand-clickable': !showOverrideFlags }">
        <v-col cols="12">
          <v-card class="mb-4">
            <v-card-title class="d-flex justify-space-between align-center">
              Override Flags
              <div class="d-flex align-center" style="gap: 8px">
                <v-btn
                  v-if="hasAnyOverride"
                  prepend-icon="mdi-refresh"
                  size="default"
                  variant="outlined"
                  color="warning"
                  aria-label="Clear all override flags"
                  @click.stop="clearAllOverrides"
                  :loading="clearingOverrides"
                  :disabled="!showOverrideFlags"
                  class="override-clear-btn"
                >
                  Clear all
                </v-btn>
                <v-btn
                  :icon="showOverrideFlags ? 'mdi-eye-off' : 'mdi-eye'"
                  size="small"
                  variant="text"
                  @click.stop="toggleOverrideFlags"
                  :aria-label="showOverrideFlags ? 'Collapse section' : 'Expand section'"
                  :aria-expanded="showOverrideFlags ? 'true' : 'false'"
                  aria-controls="override-flags-section"
                ></v-btn>
              </div>
            </v-card-title>
            <v-card-subtitle v-if="!showOverrideFlags" class="text-caption text-secondary px-4 pt-0 pb-2">
              Click anywhere on this section to expand.
            </v-card-subtitle>
            <v-expand-transition>
              <div v-show="showOverrideFlags" id="override-flags-section">
                <v-card-text>
                  <v-list density="compact">
                    <v-list-item v-if="run?.name_override">
                      <template v-slot:prepend>
                        <v-icon>mdi-lock</v-icon>
                      </template>
                      <v-list-item-title>Name</v-list-item-title>
                      <template v-slot:append>
                        <v-btn
                          icon="mdi-close-circle"
                          size="x-small"
                          variant="text"
                          color="warning"
                          @click.stop="clearSingleOverride('name')"
                          :loading="clearingSingleOverride['name']"
                          aria-label="Clear name override"
                        ></v-btn>
                      </template>
                    </v-list-item>
                    <v-list-item v-if="run?.is_public_override">
                      <template v-slot:prepend>
                        <v-icon>mdi-lock</v-icon>
                      </template>
                      <v-list-item-title>Public</v-list-item-title>
                      <template v-slot:append>
                        <v-btn
                          icon="mdi-close-circle"
                          size="x-small"
                          variant="text"
                          color="warning"
                          @click.stop="clearSingleOverride('is_public')"
                          :loading="clearingSingleOverride['is_public']"
                          aria-label="Clear public override"
                        ></v-btn>
                      </template>
                    </v-list-item>
                    <v-list-item v-if="run?.reduction_status_override">
                      <template v-slot:prepend>
                        <v-icon>mdi-lock</v-icon>
                      </template>
                      <v-list-item-title>Status</v-list-item-title>
                      <template v-slot:append>
                        <v-btn
                          icon="mdi-close-circle"
                          size="x-small"
                          variant="text"
                          color="warning"
                          @click.stop="clearSingleOverride('reduction_status')"
                          :loading="clearingSingleOverride['reduction_status']"
                          aria-label="Clear status override"
                        ></v-btn>
                      </template>
                    </v-list-item>
                    <v-list-item v-if="run?.photometry_override">
                      <template v-slot:prepend>
                        <v-icon>mdi-lock</v-icon>
                      </template>
                      <v-list-item-title>Photometry</v-list-item-title>
                      <template v-slot:append>
                        <v-btn
                          icon="mdi-close-circle"
                          size="x-small"
                          variant="text"
                          color="warning"
                          @click.stop="clearSingleOverride('photometry')"
                          :loading="clearingSingleOverride['photometry']"
                          aria-label="Clear photometry override"
                        ></v-btn>
                      </template>
                    </v-list-item>
                    <v-list-item v-if="run?.spectroscopy_override">
                      <template v-slot:prepend>
                        <v-icon>mdi-lock</v-icon>
                      </template>
                      <v-list-item-title>Spectroscopy</v-list-item-title>
                      <template v-slot:append>
                        <v-btn
                          icon="mdi-close-circle"
                          size="x-small"
                          variant="text"
                          color="warning"
                          @click.stop="clearSingleOverride('spectroscopy')"
                          :loading="clearingSingleOverride['spectroscopy']"
                          aria-label="Clear spectroscopy override"
                        ></v-btn>
                      </template>
                    </v-list-item>
                    <v-list-item v-if="run?.note_override">
                      <template v-slot:prepend>
                        <v-icon>mdi-lock</v-icon>
                      </template>
                      <v-list-item-title>Note</v-list-item-title>
                      <template v-slot:append>
                        <v-btn
                          icon="mdi-close-circle"
                          size="x-small"
                          variant="text"
                          color="warning"
                          @click.stop="clearSingleOverride('note')"
                          :loading="clearingSingleOverride['note']"
                          aria-label="Clear note override"
                        ></v-btn>
                      </template>
                    </v-list-item>
                    <v-list-item v-if="run?.mid_observation_jd_override">
                      <template v-slot:prepend>
                        <v-icon>mdi-lock</v-icon>
                      </template>
                      <v-list-item-title>Date/JD</v-list-item-title>
                      <template v-slot:append>
                        <v-btn
                          icon="mdi-close-circle"
                          size="x-small"
                          variant="text"
                          color="warning"
                          @click.stop="clearSingleOverride('mid_observation_jd')"
                          :loading="clearingSingleOverride['mid_observation_jd']"
                          aria-label="Clear date/JD override"
                        ></v-btn>
                      </template>
                    </v-list-item>
                    <v-list-item v-if="!hasAnyOverride" title="No overrides" class="text-secondary" />
                  </v-list>
                </v-card-text>
              </div>
            </v-expand-transition>
          </v-card>
        </v-col>
      </v-row>

      <!-- Edit Observation Run Dialog -->
      <v-dialog v-model="runEditDialog" max-width="640" aria-labelledby="edit-run-title">
        <v-card>
          <v-card-title id="edit-run-title">Edit Observation Run</v-card-title>
          <v-card-text>
            <v-row dense class="mb-2">
              <v-col cols="12" sm="6">
                <v-text-field v-model="runEditForm.name" label="Name" variant="outlined" density="comfortable" hide-details />
              </v-col>
              <v-col cols="12" sm="6">
                <v-select
                  v-model="runEditForm.reduction_status"
                  :items="runStatusOptions"
                  item-title="title"
                  item-value="value"
                  label="Reduction status"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                />
              </v-col>
            </v-row>
            <v-row dense class="mb-2">
              <v-col cols="12" sm="4">
                <v-switch v-model="runEditForm.is_public" inset hide-details color="primary" :label="`Public`" />
              </v-col>
            </v-row>
            <v-row dense class="mt-2">
              <v-col cols="12" sm="7">
                <v-text-field
                  v-model="runEditDateInput"
                  label="Observation date/time (ISO, e.g. 2021-02-24T23:30:00Z)"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                  clearable
                />
              </v-col>
              <v-col cols="12" sm="5">
                <v-text-field
                  v-model.number="runEditJdInput"
                  label="Julian Date (e.g. 2459254.48)"
                  type="number"
                  variant="outlined"
                  density="comfortable"
                  hide-details
                  clearable
                />
              </v-col>
              <v-col cols="12">
                <v-btn variant="text" color="primary" @click="runEditRecomputeDate" :loading="runEditSaving">
                  Recompute date from files
                </v-btn>
              </v-col>
            </v-row>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" @click="runEditDialog = false">Cancel</v-btn>
            <v-btn color="primary" variant="flat" :loading="runEditSaving" @click="saveRunEdit">Save</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Edit Observation Type Dialog -->
      <v-dialog v-model="obsTypeDialog" max-width="520" @keydown.esc.prevent="closeObsTypeDialog" aria-labelledby="edit-obs-type-title">
        <v-card>
          <v-card-title id="edit-obs-type-title">Edit Observation Type</v-card-title>
          <v-card-text>
            <div class="d-flex align-center" style="gap: 16px">
              <v-switch v-model="editSpectroscopy" label="Spectroscopy" color="primary" hide-details density="comfortable" />
              <v-switch v-model="editPhotometry" label="Photometry" color="primary" hide-details density="comfortable" />
            </div>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn color="primary" variant="flat" :loading="savingObsType" @click="saveObsType">Save</v-btn>
            <v-btn variant="text" @click="closeObsTypeDialog" ref="obsTypeCloseBtn">Cancel</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Edit Notes Dialog -->
      <v-dialog v-model="notesDialog" max-width="640" @keydown.esc.prevent="closeNotesDialog" aria-labelledby="edit-run-notes-title">
        <v-card>
          <v-card-title id="edit-run-notes-title">Edit Notes</v-card-title>
          <v-card-text>
            <v-textarea v-model="newNote" label="Notes" variant="outlined" rows="8" auto-grow clearable />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn color="primary" @click="saveRunNotes">Save</v-btn>
            <v-btn variant="text" @click="closeNotesDialog" ref="notesCloseBtn">Cancel</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Edit Tags Dialog -->
      <v-dialog v-model="tagDialog" max-width="520" @keydown.esc.prevent="closeTagDialog" aria-labelledby="edit-run-tags-title">
        <v-card>
          <v-card-title id="edit-run-tags-title">Edit Tags</v-card-title>
          <v-card-text>
            <v-checkbox
              v-for="(tag, idx) in availableTags"
              :key="tag?.pk || tag?.name || idx"
              v-model="selectedTags"
              :value="tag?.pk"
              :label="tag?.name"
              :color="tag?.color"
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn color="primary" @click="saveRunTags">Save</v-btn>
            <v-btn variant="text" @click="closeTagDialog" ref="tagCloseBtn">Cancel</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Main Objects Details -->
      <v-row>
        <v-col cols="12">
          <v-card class="mb-4">
        <v-card-title>Main Objects</v-card-title>
        <v-card-text class="px-4">
          <v-skeleton-loader v-if="loadingObjects" type="table"></v-skeleton-loader>
          <template v-else>
            <v-table v-if="mainObjectsDetails && mainObjectsDetails.length" class="custom-table">
              <thead>
                <tr>
                  <th class="text-primary">Name</th>
                  <th class="text-primary">Type</th>
                  <th class="text-primary">RA</th>
                  <th class="text-primary">Dec</th>
                  <th class="text-primary">Exposure</th>
                  <th class="text-primary">Files</th>
                  <th class="text-primary">Instrument</th>
                  <th class="text-primary">Telescope</th>
                  <th class="text-primary">Airmass</th>
                  <th class="text-primary">Observed</th>
                  <th class="text-primary">Sky</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in mainObjectsDetails" :key="row.id">
                  <td>
                    <router-link :to="`/objects/${row.id}`" class="text-decoration-none primary--text">{{ row.name }}</router-link>
                  </td>
                  <td class="text-secondary">{{ row.object_type_display }}</td>
                  <td class="text-secondary font-mono">{{ formatRA(row.ra) }}</td>
                  <td class="text-secondary font-mono">{{ formatDec(row.dec) }}</td>
                  <td class="text-secondary">{{ formatExposureTime(row.expo_time) }}</td>
                  <td class="text-secondary">{{ row.n_fits }}/{{ row.n_img }}/{{ row.n_ser }}</td>
                  <td class="text-secondary">{{ (row.instruments && row.instruments.length) ? row.instruments.join(', ') : '—' }}</td>
                  <td class="text-secondary">{{ (row.telescopes && row.telescopes.length) ? row.telescopes.join(', ') : '—' }}</td>
                  <td class="text-secondary d-flex align-center">
                    <span>{{ formatAirmassRange(row.airmass_min, row.airmass_max) }}</span>
                    <v-tooltip text="Visibility" location="top">
                      <template #activator="{ props }">
                        <v-btn
                          v-bind="props"
                          icon
                          variant="text"
                          color="primary"
                          size="small"
                          class="ml-1"
                          :aria-label="`Open visibility for ${row.name}`"
                          :disabled="!row.observed_start || !row.expo_time"
                          @click="openVisibility(row)"
                        >
                          <v-icon size="18">mdi-chart-line</v-icon>
                        </v-btn>
                      </template>
                    </v-tooltip>
                  </td>
                  <td class="text-secondary">{{ formatObservedWindow(row.observed_start, row.observed_end) }}</td>
                  <td>
                    <v-btn
                      variant="text"
                      color="primary"
                      size="small"
                      :disabled="!row.ra || !row.dec || !row.expo_time"
                      @click="openSkyFov(row)"
                    >
                      Sky FOV
                    </v-btn>
                  </td>
                </tr>
              </tbody>
            </v-table>
            <div v-else class="text-caption text-secondary">No main objects.</div>
          </template>
        </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <!-- Auxiliary Objects -->
      <v-row v-if="run?.photometry">
        <v-col cols="12">
          <v-card class="mb-4">
            <v-card-title>Auxiliary Objects</v-card-title>
            <v-card-text class="px-4">
              <v-skeleton-loader v-if="loadingObjects" type="chip"></v-skeleton-loader>
              <template v-else>
                <div v-if="auxObjects && auxObjects.length" class="d-flex flex-wrap gap-2">
                  <v-chip
                    v-for="obj in auxObjects"
                    :key="obj.pk || obj.id"
                    variant="outlined"
                    size="small"
                    color="primary"
                    :to="`/objects/${obj.pk || obj.id}`"
                    link
                  >
                    {{ obj.name }}
                  </v-chip>
                </div>
                <div v-else class="text-caption text-secondary">No auxiliary objects.</div>
              </template>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
      
      <!-- Data Files of this Run -->
      <v-row>
        <v-col cols="12">
          <v-card class="mb-4">
            <v-card-title class="d-flex align-start justify-space-between flex-column flex-md-row">
              <div class="text-h6 mb-2">Data Files</div>
            </v-card-title>
            <v-card-text>
          <div class="d-flex align-center flex-wrap mb-1 px-4" style="gap: 12px">
            <v-text-field v-model="dfFilterFileName" label="File name contains" density="comfortable" variant="outlined" style="min-width: 220px" clearable />
            <v-text-field v-model="dfFilterTarget" label="Target contains" density="comfortable" variant="outlined" style="min-width: 220px" clearable />
            <v-text-field v-model="dfFilterType" label="File type contains" density="comfortable" variant="outlined" style="min-width: 180px" clearable />
            <v-text-field v-model="dfFilterInstrument" label="Instrument contains" density="comfortable" variant="outlined" style="min-width: 200px" clearable />
            <v-select
              v-model="dfFilterBinning"
              :items="binningOptions"
              label="Binning"
              density="comfortable"
              variant="outlined"
              style="min-width: 100px"
              clearable
            />
            <v-select
              v-model="dfFilterExposureTypes"
              :items="exposureTypeOptions"
              label="Exposure type"
              multiple
              chips
              closable-chips
              density="comfortable"
              variant="outlined"
              style="min-width: 200px"
              clearable
            />
            <v-select
              v-model="dfFilterSpectroscopy"
              :items="spectroscopyOptions"
              label="Spectroscopy"
              density="comfortable"
              variant="outlined"
              style="min-width: 160px"
              clearable
            />
            <v-text-field v-model.number="dfFilterExpMin" type="number" label="Exp min [s]" density="comfortable" variant="outlined" style="min-width: 160px" clearable />
            <v-text-field v-model.number="dfFilterExpMax" type="number" label="Exp max [s]" density="comfortable" variant="outlined" style="min-width: 160px" clearable />
          </div>
          <div class="d-flex align-center flex-wrap mb-4 px-4" style="gap: 12px">
            <v-btn variant="text" color="primary" @click="resetDfFilters" aria-label="Reset filters" block>Reset</v-btn>
          </div>
          <div class="d-flex align-center flex-wrap mb-2 px-4" style="gap: 12px">
            <v-btn color="primary" variant="flat" @click="handleDownloadAll" :loading="downloadingAll" aria-label="Download all files">Download all</v-btn>
            <v-btn color="primary" variant="text" :disabled="!dataFilesTotal" @click="handleDownloadFiltered" aria-label="Download filtered files">Download filtered</v-btn>
            <v-btn color="primary" variant="text" :disabled="!selectedIds.length" @click="downloadSelected" :aria-label="`Download selected (${selectedIds.length})`">Download selected ({{ selectedIds.length }})</v-btn>
          </div>
          <v-skeleton-loader v-if="loadingDataFiles" type="table"></v-skeleton-loader>
          <template v-else>
            <v-data-table
              v-if="sortedDataFiles && sortedDataFiles.length"
              :headers="runDataFileHeaders"
              :items="sortedDataFiles"
              :items-per-page="dataFilesItemsPerPage === -1 ? sortedDataFiles.length : dataFilesItemsPerPage"
              :page="dataFilesPage"
              :sort-by="dfSortBy"
              @update:sort-by="handleDfSort"
              hide-default-footer
              class="custom-table"
              item-key="pk"
              item-value="pk"
            >
              <template v-slot:header.select>
                <div class="d-flex justify-center">
                  <v-checkbox
                    v-model="selectAll"
                    density="compact"
                    hide-details
                    @change="toggleSelectAll"
                    aria-label="Select all files"
                  />
                </div>
              </template>
              <template v-slot:item.select="{ item }">
                <v-checkbox
                  v-model="selectedIds"
                  :value="(item.pk || item.id)"
                  density="compact"
                  hide-details
                  :aria-label="`Select ${item.file_name}`"
                />
              </template>
              <template v-slot:item.file_name="{ item }">
                {{ item.file_name }}
              </template>
              <template v-slot:item.obs_date="{ item }">
                {{ formatTimeOnly(item.obs_date) }}
              </template>
              <template v-slot:item.main_target="{ item }">
                <template v-if="isLight(item)">
                  <template v-if="item.header_target_name && item.header_target_name.trim() && item.header_target_name !== '-'">
                    {{ item.header_target_name }}
                    <template v-if="item.main_target && item.main_target.trim() && item.main_target !== '-'">
                      <span class="text-secondary"> (</span>
                      <router-link
                        v-if="getObjectIdByTargetName(item.main_target)"
                        :to="`/objects/${getObjectIdByTargetName(item.main_target)}`"
                        class="text-decoration-none primary--text"
                      >{{ item.main_target }}</router-link>
                      <span v-else>{{ item.main_target }}</span>
                      <span class="text-secondary">)</span>
                    </template>
                  </template>
                  <span v-else>{{ item.header_target_name || '—' }}</span>
                </template>
                <span v-else class="text-secondary">—</span>
              </template>
              <template v-slot:item.coordinates="{ item }">
                {{ item.ra_hms }} {{ item.dec_dms }}
              </template>
              <template v-slot:item.file_type="{ item }">
                {{ item.file_type }}
              </template>
              <template v-slot:item.binning="{ item }">
                {{ item.binning || '1x1' }}
              </template>
              <template v-slot:item.instrument="{ item }">
                <template v-if="item.spectrograph && item.spectrograph !== 'N'">
                  {{ getSpectrographLabel(item.spectrograph) }}{{ item.instrument ? ' ' + item.instrument : '' }}
                </template>
                <template v-else>
                  {{ item.instrument || '—' }}
                </template>
              </template>
              <template v-slot:item.exposure_type_display="{ item }">
                {{ item.exposure_type_display || item.exposure_type }}
              </template>
              <template v-slot:item.exptime="{ item }">
                {{ formatExposureTime(item.exptime) }}
              </template>
              <template v-slot:item.tools="{ item }">
                <div class="d-flex justify-end">
                  <v-btn
                    v-if="!isSer(item)"
                    variant="text"
                    size="small"
                    icon
                    aria-label="Preview"
                    @click="openPreview(item)"
                  >
                    <v-icon>mdi-image-search</v-icon>
                  </v-btn>
                  <v-btn
                    variant="text"
                    size="small"
                    icon
                    :disabled="String(item.file_type || '').toUpperCase() !== 'FITS'"
                    :aria-label="`View FITS header for ${item.file_name}`"
                    @click="openHeader(item)"
                  >
                    <v-icon>mdi-file-document-outline</v-icon>
                  </v-btn>
                  <v-btn variant="text" size="small" icon :href="api.getDataFileDownloadUrl(item.pk || item.id)" :aria-label="`Download ${item.file_name}`">
                    <v-icon>mdi-download</v-icon>
                  </v-btn>
                </div>
              </template>
            </v-data-table>
            <div v-else class="text-caption text-secondary">No data files found for this run.</div>
          </template>
        </v-card-text>
            <v-card-actions class="d-flex align-center justify-space-between px-4 py-2 card-actions-responsive">
              <div class="d-flex align-center actions-left">
                <span class="text-body-2 mr-4">Items per page:</span>
                <v-select
                  v-model="dataFilesItemsPerPage"
                  :items="dataFilesPageSizeOptions"
                  item-title="title"
                  item-value="value"
                  density="compact"
                  variant="outlined"
                  hide-details
                  class="items-per-page-select"
                  style="width: 100px"
                  @update:model-value="handleDfItemsPerPageChange"
                  aria-label="Items per page"
                ></v-select>
              </div>

              <div class="d-flex align-center actions-right">
                <span class="text-body-2 mr-4">
                  {{ dfPaginationInfo }}
                </span>
                <v-btn
                  icon="mdi-page-first"
                  variant="text"
                  :disabled="dataFilesPage === 1"
                  @click="handleDfPageChange(1)"
                  class="mx-1 pagination-btn"
                  aria-label="First page"
                ></v-btn>
                <v-btn
                  icon="mdi-chevron-left"
                  variant="text"
                  :disabled="dataFilesPage === 1"
                  @click="handleDfPageChange(dataFilesPage - 1)"
                  class="mx-1 pagination-btn"
                  aria-label="Previous page"
                ></v-btn>
                <v-btn
                  icon="mdi-chevron-right"
                  variant="text"
                  :disabled="dataFilesPage >= dfTotalPages"
                  @click="handleDfPageChange(dataFilesPage + 1)"
                  class="mx-1 pagination-btn"
                  aria-label="Next page"
                ></v-btn>
                <v-btn
                  icon="mdi-page-last"
                  variant="text"
                  :disabled="dataFilesPage >= dfTotalPages"
                  @click="handleDfPageChange(dfTotalPages)"
                  class="mx-1 pagination-btn"
                  aria-label="Last page"
                ></v-btn>
              </div>
            </v-card-actions>
          </v-card>
        </v-col>
      </v-row>

      <!-- Observing Conditions -->
      <v-row @click="expandObservingIfCollapsed" :class="{ 'expand-clickable': !showObservingConditions }">
        <v-col cols="12">
          <v-card class="mb-4">
            <v-card-title class="d-flex justify-space-between align-center">
              Observing Conditions
              <v-btn
                :icon="showObservingConditions ? 'mdi-eye-off' : 'mdi-eye'"
                size="small"
                variant="text"
                @click.stop="toggleObservingConditions"
                :aria-label="showObservingConditions ? 'Collapse section' : 'Expand section'"
                :aria-expanded="showObservingConditions ? 'true' : 'false'"
                aria-controls="run-observing-conditions"
              ></v-btn>
            </v-card-title>
            <v-card-subtitle v-if="!showObservingConditions" class="text-caption text-secondary px-4 pt-0 pb-2">
              Click anywhere on this section to expand.
            </v-card-subtitle>
            <v-expand-transition>
              <div v-show="showObservingConditions" id="run-observing-conditions">
                <v-card-text class="px-4">
                  <v-alert v-if="conditionsError" type="error" variant="tonal">{{ conditionsError }}</v-alert>
                  <v-skeleton-loader v-else-if="conditionsLoading" type="image"></v-skeleton-loader>
                  <v-alert v-else-if="conditionsTooSmall" type="info" variant="tonal">
                    Screen is too narrow to display the plot. Please rotate your phone to landscape and press Load again.
                  </v-alert>
                  <div v-else :class="['conditions-wrapper', { hidden: !conditionsVisible }]">
                    <div id="conditions-container"></div>
                  </div>
                </v-card-text>
              </div>
            </v-expand-transition>
          </v-card>
        </v-col>
      </v-row>

      <!-- Visibility dialog -->
      <v-dialog v-model="visibilityDialog" max-width="820" @keydown.esc.prevent="closeVisibility" aria-labelledby="visibility-title">
        <v-card>
          <v-card-title id="visibility-title">Visibility</v-card-title>
          <v-card-text>
            <div v-if="visibilityError" class="text-error">{{ visibilityError }}</div>
            <v-skeleton-loader v-else-if="visibilityLoading" type="image"></v-skeleton-loader>
            <div v-else id="visibility-container"></div>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn variant="text" color="primary" @click="closeVisibility" ref="visibilityCloseBtn">Close</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Preview dialog -->
      <v-dialog v-model="previewDialog" max-width="900" aria-labelledby="preview-title">
        <v-card>
          <v-card-title id="preview-title">{{ previewTitle }}</v-card-title>
          <v-card-text class="preview-container">
            <div v-if="previewLoading" class="d-flex align-center justify-center preview-placeholder">
              <v-progress-circular indeterminate color="primary" />
            </div>
            <v-img
              v-if="previewUrl"
              :src="previewUrl"
              alt="Preview"
              max-height="600"
              contain
              @load="handlePreviewLoad"
              @error="handlePreviewError"
            />
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" color="primary" @click="previewDialog = false">Close</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- FITS Header dialog -->
      <v-dialog v-model="headerDialog" max-width="800" aria-labelledby="header-title">
        <v-card>
          <v-card-title id="header-title">{{ headerTitle || 'FITS Header' }}</v-card-title>
          <v-card-text>
            <v-alert v-if="headerError" type="error" variant="tonal">{{ headerError }}</v-alert>
            <v-skeleton-loader v-else-if="headerLoading" type="table" />
            <template v-else>
              <v-table density="compact">
                <thead>
                  <tr>
                    <th class="text-primary" style="width: 30%">Key</th>
                    <th class="text-primary">Value</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="([k, v], idx) in headerEntries" :key="k || idx">
                    <td class="font-mono">{{ k }}</td>
                    <td class="font-mono">{{ formatHeaderValue(v) }}</td>
                  </tr>
                </tbody>
              </v-table>
              <div v-if="!headerEntries.length" class="text-caption text-secondary">No header data.</div>
            </template>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" color="primary" @click="headerDialog = false">Close</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- Sky FOV dialog -->
      <v-dialog v-model="fovDialog" max-width="900" @keydown.esc.prevent="closeFov" aria-labelledby="fov-title">
        <v-card>
          <v-card-title id="fov-title">Sky FOV</v-card-title>
          <v-card-text>
            <v-alert v-if="fovError" type="error" variant="tonal">{{ fovError }}</v-alert>
            <v-skeleton-loader v-else-if="fovLoading" type="image" />
            <div v-else id="fov-container"></div>
          </v-card-text>
          <v-card-actions>
            <v-spacer />
            <v-btn variant="text" color="primary" @click="closeFov" ref="fovCloseBtn">Close</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/api'
import { useNotifyStore } from '@/store/notify'
import { useAuthStore } from '@/store/auth'
import { formatDateTime } from '@/utils/datetime'
import { getStatusColor } from '@/utils/status'

const route = useRoute()
const notify = useNotifyStore()
const authStore = useAuthStore()
const isAuthenticated = computed(() => authStore.isAuthenticated)
const isAdmin = computed(() => authStore.isAdmin)
const canEditRun = computed(() => authStore.isAdmin || authStore.hasPerm('users.acl_runs_edit') || authStore.hasPerm('acl_runs_edit'))
const runId = route.params.id
const clearingOverrides = ref(false)
const clearingSingleOverride = ref({})

const run = ref(null)
const loading = ref(false)
const error = ref(null)
const objects = ref([])
const loadingObjects = ref(false)
const mainObjectsDetails = ref([])
const auxObjects = ref([])
const dataFiles = ref([])
const loadingDataFiles = ref(false)
const dataFilesPage = ref(1)
const dataFilesItemsPerPage = ref(10)
const dataFilesTotal = ref(0)
const dataFilesPageSizeOptions = [
  { title: '10', value: 10 },
  { title: '25', value: 25 },
  { title: '50', value: 50 },
  { title: '100', value: 100 },
  { title: 'All', value: -1 },
]
const dfFilterTarget = ref('')
const dfFilterType = ref('')
const dfFilterInstrument = ref('')
const dfFilterBinning = ref(null)
const dfFilterExpMin = ref(null)
const dfFilterExpMax = ref(null)
const dfFilterExposureTypes = ref([])
const dfFilterSpectroscopy = ref(null)

// Get spectrograph display label
const getSpectrographLabel = (spectrograph) => {
  const labels = {
    'D': 'DADOS',
    'B': 'BACHES',
    'E': 'EINSTEIN_TOWER',
    'N': 'NONE',
  }
  return labels[spectrograph] || spectrograph
}
const dfFilterFileName = ref('')
const dfFilterPixelsMin = ref(null)
const dfFilterPixelsMax = ref(null)
const dfSortBy = ref([{ key: 'obs_date', order: 'desc' }])
const exposureTypeOptions = [
  { title: 'Light (LI)', value: 'LI' },
  { title: 'Wave (WA)', value: 'WA' },
  { title: 'Flat (FL)', value: 'FL' },
  { title: 'Dark (DA)', value: 'DA' },
  { title: 'Bias (BI)', value: 'BI' },
  { title: 'Unknown (UK)', value: 'UK' },
]
const spectroscopyOptions = [
  { title: 'Yes', value: true },
  { title: 'No', value: false },
]
const visibilityDialog = ref(false)
const visibilityCloseBtn = ref(null)
const visibilityError = ref('')
const visibilityLoading = ref(false)
const visibilityCache = new Map()
const conditionsLoading = ref(false)
const conditionsError = ref('')
const conditionsVisible = ref(false)
const conditionsTooSmall = ref(false)
const conditionsCache = new Map()
const fovDialog = ref(false)
const fovCloseBtn = ref(null)
const fovLoading = ref(false)
const fovError = ref('')
const fovCache = new Map()
// Collapsible Observing Conditions (match Object Detail UX)
const showObservingConditions = ref(false)
const openObserving = async () => {
  if (!showObservingConditions.value) showObservingConditions.value = true
  if (!conditionsVisible.value && !conditionsLoading.value) {
    await loadConditions()
  }
}
const toggleObservingConditions = async () => {
  if (showObservingConditions.value) {
    showObservingConditions.value = false
  } else {
    await openObserving()
  }
}
const expandObservingIfCollapsed = async () => {
  if (!showObservingConditions.value) {
    await openObserving()
  }
}

// Collapsible Override Flags
const showOverrideFlags = ref(false)
const toggleOverrideFlags = () => {
  showOverrideFlags.value = !showOverrideFlags.value
}
const expandOverrideFlagsIfCollapsed = () => {
  if (!showOverrideFlags.value) {
    showOverrideFlags.value = true
  }
}

const notesDialog = ref(false)
const newNote = ref('')
const notesCloseBtn = ref(null)
const tagDialog = ref(false)
const availableTags = ref([])
const selectedTags = ref([])
const tagCloseBtn = ref(null)
const obsTypeDialog = ref(false)
const editSpectroscopy = ref(false)
const editPhotometry = ref(false)
const savingObsType = ref(false)
const obsTypeCloseBtn = ref(null)

// Admin run edit
const runEditDialog = ref(false)
const runEditSaving = ref(false)
const runEditForm = ref({
  name: '',
  reduction_status: 'NE',
  is_public: true,
})
const runEditDateInput = ref('')
const runEditJdInput = ref(null)
const runStatusOptions = [
  { title: 'New', value: 'NE' },
  { title: 'Partly reduced', value: 'PR' },
  { title: 'Fully reduced', value: 'FR' },
  { title: 'Reduction error', value: 'ER' },
]
const openRunEdit = () => {
  if (!run.value) return
  runEditForm.value = {
    name: run.value.name || '',
    reduction_status: run.value.reduction_status || 'NE',
    is_public: run.value.is_public ?? true,
  }
  runEditDateInput.value = ''
  runEditJdInput.value = null
  runEditDialog.value = true
}
const normalizeIso = (s) => {
  if (!s) return ''
  let x = String(s).trim()
  if (/^\d{4}-\d{2}-\d{2}\s/.test(x)) x = x.replace(' ', 'T')
  if (!/[zZ]|[+\-]\d{2}:\d{2}$/.test(x)) x = `${x}Z`
  return x
}
const saveRunEdit = async () => {
  try {
    runEditSaving.value = true
    const payload = {
      name: runEditForm.value.name,
      reduction_status: runEditForm.value.reduction_status,
      is_public: !!runEditForm.value.is_public,
    }
    await api.updateObservationRun(runId, payload)
    // Optional: set mid_observation_jd if provided
    const hasJd = runEditJdInput.value != null && runEditJdInput.value !== ''
    const hasIso = runEditDateInput.value && String(runEditDateInput.value).trim()
    if (hasJd || hasIso) {
      const datePayload = {}
      if (hasJd) datePayload.jd = Number(runEditJdInput.value)
      if (!hasJd && hasIso) datePayload.iso = normalizeIso(runEditDateInput.value)
      await api.adminSetRunDate(runId, datePayload)
    }
    const data = await api.getObservationRun(runId)
    run.value = data
    runEditDialog.value = false
    try { notify.success('Observation run updated') } catch {}
  } catch (e) {
    console.error(e)
    try { notify.error('Failed to update observation run') } catch {}
  } finally {
    runEditSaving.value = false
  }
}
const runEditRecomputeDate = async () => {
  try {
    runEditSaving.value = true
    await api.adminRecomputeRunDate(runId)
    const data = await api.getObservationRun(runId)
    run.value = data
    try { notify.success('Observation date recomputed from files') } catch {}
  } catch (e) {
    console.error(e)
    try { notify.error('Failed to recompute observation date') } catch {}
  } finally {
    runEditSaving.value = false
  }
}

const dateString = computed(() => {
  if (!run.value?.name) return ''
  const n = run.value.name
  if (n.length >= 8 && /^\d{8}/.test(n)) {
    return `${n.slice(0,4)}-${n.slice(4,6)}-${n.slice(6,8)}`
  }
  return ''
})

const tzEnv = import.meta.env.VITE_TIME_ZONE
const tzDisplay = computed(() => {
  if (tzEnv && String(tzEnv).toUpperCase() === 'UTC') return 'UTC'
  if (tzEnv) return `local time (${tzEnv})`
  return 'local time'
})

// Override flags
const hasAnyOverride = computed(() => {
  if (!run.value) return false
  return !!(run.value.name_override || run.value.is_public_override || 
           run.value.reduction_status_override || run.value.photometry_override ||
           run.value.spectroscopy_override || run.value.note_override ||
           run.value.mid_observation_jd_override)
})

const clearSingleOverride = async (fieldName) => {
  if (!isAdmin.value || !runId) return
  const key = fieldName
  clearingSingleOverride.value[key] = true
  try {
    await api.adminClearOverrideFlag('run', runId, fieldName)
    notify.success(`Override flag for ${fieldName} cleared`)
    // Reload run data
    const data = await api.getObservationRun(runId)
    run.value = data
  } catch (e) {
    notify.error(`Failed to clear override flag for ${fieldName}`)
  } finally {
    clearingSingleOverride.value[key] = false
  }
}

const clearAllOverrides = async () => {
  if (!isAdmin.value || !runId) return
  clearingOverrides.value = true
  try {
    await api.adminClearAllOverrides('run', runId)
    notify.success('All override flags cleared')
    // Reload run data
    const data = await api.getObservationRun(runId)
    run.value = data
  } catch (e) {
    notify.error('Failed to clear override flags')
  } finally {
    clearingOverrides.value = false
  }
}

// Parse backend datetime strings (e.g., "YYYY-MM-DD HH:mm:ss.sss") as UTC if no timezone is present
const parseUtcDate = (value) => {
  if (!value) return null
  if (value instanceof Date) return value
  let s = String(value).trim()
  // Replace space with 'T' for ISO and append 'Z' if no timezone offset present
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d+)?$/.test(s)) {
    s = s.replace(' ', 'T') + 'Z'
  }
  return new Date(s)
}

const formatDate = (date) => formatDateTime(parseUtcDate(date))
const formatTimeOnly = (date) => {
  const d = parseUtcDate(date)
  if (!d) return '—'
  const locales = (typeof navigator !== 'undefined' && navigator.languages && navigator.languages.length)
    ? navigator.languages
    : (typeof navigator !== 'undefined' ? [navigator.language] : undefined)
  const fmt = new Intl.DateTimeFormat(locales, { timeStyle: 'medium', timeZone: import.meta.env.VITE_TIME_ZONE || undefined })
  return fmt.format(d)
}

const formatExposureTime = (seconds) => {
  if (!seconds) return '0s'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const remainingSeconds = Math.floor(seconds % 60)
  let result = ''
  if (hours > 0) result += `${hours}h `
  if (minutes > 0) result += `${minutes}m `
  if (remainingSeconds > 0 || result === '') result += `${remainingSeconds}s`
  return result.trim()
}

// Parse a positive integer from a free-form input string. Returns undefined if none.
const parsePositiveInt = (value) => {
  if (value == null) return undefined
  const str = String(value)
  const match = str.match(/\d+/)
  if (!match) return undefined
  const n = Number(match[0])
  return Number.isFinite(n) && n >= 0 ? n : undefined
}

// Parse pixel count from input. Accepts either a single integer (total pixels)
// or a WxH style like "5000x5000", "5000*5000", "5000×5000" (product of both).
const parsePixelCount = (value) => {
  if (value == null) return undefined
  const str = String(value)
  // Try WxH patterns first
  const parts = str.split(/[^0-9]+/).filter(Boolean)
  if (parts.length >= 2) {
    const w = Number(parts[0])
    const h = Number(parts[1])
    if (Number.isFinite(w) && Number.isFinite(h) && w >= 0 && h >= 0) {
      return Math.floor(w * h)
    }
  }
  // Fallback: single leading integer means total pixel count
  const n = parsePositiveInt(str)
  return n
}

// Client-side filtered list to support binning filtering (server has no binning param)
const filteredDataFiles = computed(() => {
  let items = Array.isArray(dataFiles.value) ? dataFiles.value.slice() : []
  if (dfFilterBinning.value) {
    items = items.filter(f => (f.binning || '').toLowerCase() === String(dfFilterBinning.value).toLowerCase())
  }
  return items
})

// Sort function for data files
const sortDataFiles = (items, sortBy) => {
  if (!sortBy || sortBy.length === 0) return items
  
  const sorted = [...items]
  const sort = sortBy[0]
  const key = sort.key
  const order = sort.order === 'desc' ? -1 : 1
  
  sorted.sort((a, b) => {
    let aVal = a[key]
    let bVal = b[key]
    
    // Handle special cases
    if (key === 'obs_date') {
      aVal = a.obs_date ? new Date(a.obs_date).getTime() : 0
      bVal = b.obs_date ? new Date(b.obs_date).getTime() : 0
    } else if (key === 'exptime') {
      aVal = a.exptime || 0
      bVal = b.exptime || 0
    } else if (key === 'binning') {
      // Parse binning like "2x2" to numeric value for sorting
      const parseBinning = (bin) => {
        if (!bin) return 0
        const match = String(bin).match(/(\d+)x(\d+)/)
        return match ? parseInt(match[1]) * parseInt(match[2]) : 0
      }
      aVal = parseBinning(a.binning)
      bVal = parseBinning(b.binning)
    } else if (key === 'exposure_type_display') {
      aVal = a.exposure_type_display || a.exposure_type || ''
      bVal = b.exposure_type_display || b.exposure_type || ''
    } else if (key === 'main_target') {
      // For sorting by target, use main_target if available, otherwise header_target_name
      aVal = (a.main_target && a.main_target !== '-') ? a.main_target : (a.header_target_name || '')
      bVal = (b.main_target && b.main_target !== '-') ? b.main_target : (b.header_target_name || '')
    }
    
    // Handle null/undefined
    if (aVal == null) aVal = ''
    if (bVal == null) bVal = ''
    
    // Compare
    if (typeof aVal === 'string' && typeof bVal === 'string') {
      return aVal.localeCompare(bVal) * order
    }
    if (aVal < bVal) return -1 * order
    if (aVal > bVal) return 1 * order
    return 0
  })
  
  return sorted
}

const sortedDataFiles = computed(() => {
  return sortDataFiles(filteredDataFiles.value, dfSortBy.value)
})

const handleDfSort = (newSortBy) => {
  dfSortBy.value = newSortBy.length > 0 ? newSortBy : [{ key: 'obs_date', order: 'desc' }]
}

// Binning options derived from loaded files
// (defined once - remove duplicates)



const formatRA = (ra) => {
  if (ra === undefined || ra === null) return 'N/A'
  const hours = Math.floor(ra / 15)
  const minutes = Math.floor((ra % 15) * 4)
  const seconds = ((ra % 15) * 4 - minutes) * 60
  return `${hours.toString().padStart(2, '0')}h ${minutes.toString().padStart(2, '0')}m ${seconds.toFixed(1)}s`
}

const formatDec = (dec) => {
  if (dec === undefined || dec === null) return 'N/A'
  const sign = dec >= 0 ? '+' : '-'
  const absDec = Math.abs(dec)
  const degrees = Math.floor(absDec)
  const minutes = Math.floor((absDec - degrees) * 60)
  const seconds = ((absDec - degrees) * 60 - minutes) * 60
  return `${sign}${degrees.toString().padStart(2, '0')}° ${minutes.toString().padStart(2, '0')}' ${seconds.toFixed(1)}"`
}

const formatAirmassRange = (minVal, maxVal) => {
  if (!minVal && !maxVal) return '—'
  const format = (v) => (v || v === 0) ? Number(v).toFixed(2) : '—'
  return `${format(minVal)} – ${format(maxVal)}`
}

const formatObservedWindow = (start, end) => {
  if (!start && !end) return '—'
  const s = parseUtcDate(start)
  const e = parseUtcDate(end)
  const locales = (typeof navigator !== 'undefined' && navigator.languages && navigator.languages.length)
    ? navigator.languages
    : (typeof navigator !== 'undefined' ? [navigator.language] : undefined)
  const dateTimeFmt = new Intl.DateTimeFormat(locales, { dateStyle: 'short', timeStyle: 'medium', timeZone: import.meta.env.VITE_TIME_ZONE || undefined })
  const timeFmt = new Intl.DateTimeFormat(locales, { timeStyle: 'medium', timeZone: import.meta.env.VITE_TIME_ZONE || undefined })

  if (s && e && s.getFullYear() === e.getFullYear() && s.getMonth() === e.getMonth() && s.getDate() === e.getDate()) {
    return `${dateTimeFmt.format(s)} … ${timeFmt.format(e)}`
  }
  return `${s ? dateTimeFmt.format(s) : '—'} … ${e ? dateTimeFmt.format(e) : '—'}`
}

const fetchRun = async () => {
  try {
    loading.value = true
    error.value = null
    const data = await api.getObservationRun(runId)
    run.value = data
  } catch (e) {
    console.error('Error fetching run:', e)
    error.value = 'Failed to load observation run.'
  } finally {
    loading.value = false
  }
}

const fetchObjects = async () => {
  try {
    loadingObjects.value = true
    // Use Vuetify-optimized endpoint which supports observation_run filtering by pk
    const response = await api.getObjectsVuetify({ page: 1, itemsPerPage: -1, observation_run: runId })
    const all = response.results || response.items || response || []
    objects.value = all
    // Split into aux and main
    auxObjects.value = all.filter(o => o.is_main === false)
    const mains = all.filter(o => o.is_main)
    // For each main object, find run-specific metrics in observation_run array
    mainObjectsDetails.value = mains.map(o => {
      const linkRun = Array.isArray(o.observation_run) ? o.observation_run.find(r => String(r.pk || r.id) === String(runId)) : null
      return {
        id: o.pk || o.id,
        name: o.name,
        ra: o.ra,
        dec: o.dec,
        object_type_display: o.object_type_display,
        expo_time: linkRun?.expo_time || 0,
        n_fits: linkRun?.n_fits || 0,
        n_img: linkRun?.n_img || 0,
        n_ser: linkRun?.n_ser || 0,
        instruments: linkRun?.instruments || [],
        telescopes: linkRun?.telescopes || [],
        airmass_min: linkRun?.airmass_min ?? null,
        airmass_max: linkRun?.airmass_max ?? null,
        observed_start: linkRun?.observed_start || null,
        observed_end: linkRun?.observed_end || null,
      }
    })

    // Attach minimal datafiles arrays for table (if provided by API)
    // If not present, leave empty to avoid extra roundtrips now
    objects.value = objects.value.map(o => ({
      ...o,
      datafiles: Array.isArray(o.datafiles) ? o.datafiles : []
    }))
  } catch (e) {
    console.error('Error fetching objects for run:', e)
    objects.value = []
    auxObjects.value = []
    mainObjectsDetails.value = []
  } finally {
    loadingObjects.value = false
  }
}

// Provide quick lookups from target name -> object id for linking in files table
const targetNameToObjectId = computed(() => {
  const map = new Map()
  for (const o of objects.value || []) {
    if (o?.name) {
      const normalized = String(o.name).toLowerCase().replace(/\s+/g, '')
      map.set(normalized, o.pk || o.id)
      // Also add original name (lowercase) for exact matches
      map.set(String(o.name).toLowerCase(), o.pk || o.id)
    }
  }
  return map
})

const getObjectIdByTargetName = (name) => {
  if (!name) return null
  const normalized = String(name).toLowerCase().replace(/\s+/g, '')
  // Try normalized (without spaces) first, then exact match
  return targetNameToObjectId.value.get(normalized) || 
         targetNameToObjectId.value.get(String(name).toLowerCase()) || 
         null
}

const isLight = (df) => {
  const code = (df?.exposure_type || '').toUpperCase()
  return code === 'LI' || df?.exposure_type_display === 'Light'
}

const isSer = (df) => {
  const name = String(df?.file_name || '')
  const extMatch = /\.ser$/i.test(name)
  const typeMatch = String(df?.file_type || '').toUpperCase() === 'SER'
  return extMatch || typeMatch
}

const fetchRunDataFiles = async () => {
  try {
    loadingDataFiles.value = true
    const limit = dataFilesItemsPerPage.value === -1 ? 10000 : dataFilesItemsPerPage.value
    // Reset to first page when switching to "All"
    if (dataFilesItemsPerPage.value === -1 && dataFilesPage.value !== 1) dataFilesPage.value = 1
  const nMin = undefined
  const nMax = undefined

    const res = await api.getRunDataFilesPaged(runId, {
      page: dataFilesPage.value,
      limit,
      main_target: dfFilterTarget.value || undefined,
      file_type: dfFilterType.value || undefined,
      binning: dfFilterBinning.value || undefined,
      exptime_min: dfFilterExpMin.value != null && dfFilterExpMin.value !== '' ? dfFilterExpMin.value : undefined,
      exptime_max: dfFilterExpMax.value != null && dfFilterExpMax.value !== '' ? dfFilterExpMax.value : undefined,
      exposure_type: Array.isArray(dfFilterExposureTypes.value) && dfFilterExposureTypes.value.length ? dfFilterExposureTypes.value : undefined,
      spectroscopy: dfFilterSpectroscopy.value,
      file_name: dfFilterFileName.value || undefined,
      instrument: dfFilterInstrument.value || undefined,
      // pixel_count filters removed
    })
    dataFiles.value = Array.isArray(res?.results) ? res.results : (Array.isArray(res) ? res : [])
    dataFilesTotal.value = (typeof res?.count === 'number') ? res.count : dataFiles.value.length
  } catch (e) {
    console.error('Error fetching run datafiles:', e)
    dataFiles.value = []
  } finally {
    loadingDataFiles.value = false
  }
}

onMounted(() => {
  fetchRun()
  fetchObjects()
  fetchRunDataFiles()
})

watch([dataFilesPage, dataFilesItemsPerPage], () => {
  fetchRunDataFiles()
})

watch([dfFilterFileName, dfFilterTarget, dfFilterType, dfFilterInstrument, dfFilterBinning, dfFilterExpMin, dfFilterExpMax, dfFilterExposureTypes, dfFilterSpectroscopy], () => {
  dataFilesPage.value = 1
  fetchRunDataFiles()
})

const resetDfFilters = () => {
  dfFilterTarget.value = ''
  dfFilterType.value = ''
  dfFilterInstrument.value = ''
  dfFilterBinning.value = null
  dfFilterExpMin.value = null
  dfFilterExpMax.value = null
  dfFilterExposureTypes.value = []
  dfFilterSpectroscopy.value = null
  dfFilterFileName.value = ''
}

const dfTotalPages = computed(() => {
  if (dataFilesItemsPerPage.value === -1) return 1
  return Math.max(1, Math.ceil((dataFilesTotal.value || 0) / (dataFilesItemsPerPage.value || 10)))
})

const dfPaginationInfo = computed(() => {
  if (dataFilesItemsPerPage.value === -1) return `Showing all ${dataFilesTotal.value}`
  const start = (dataFilesPage.value - 1) * dataFilesItemsPerPage.value + 1
  const end = Math.min(dataFilesPage.value * dataFilesItemsPerPage.value, dataFilesTotal.value)
  return `${start}-${end} of ${dataFilesTotal.value}`
})

const handleDfPageChange = (newPage) => {
  if (newPage >= 1 && newPage <= dfTotalPages.value) {
    dataFilesPage.value = newPage
    fetchRunDataFiles()
  }
}

const handleDfItemsPerPageChange = () => {
  dataFilesPage.value = 1
  fetchRunDataFiles()
}

// Define headers for data files table
const runDataFileHeaders = [
  { title: '', key: 'select', sortable: false, width: 48 },
  { title: 'File Name', key: 'file_name', sortable: true },
  { title: 'Time', key: 'obs_date', sortable: true },
  { title: 'Target', key: 'main_target', sortable: true },
  { title: 'Coordinates', key: 'coordinates', sortable: false },
  { title: 'File Type', key: 'file_type', sortable: true },
  { title: 'Binning', key: 'binning', sortable: true },
  { title: 'Instrument', key: 'instrument', sortable: true },
  { title: 'Exposure Type', key: 'exposure_type_display', sortable: true },
  { title: 'Exp. Time', key: 'exptime', sortable: true },
  { title: 'Tools', key: 'tools', sortable: false, align: 'end' },
]

watch([run, dateString], () => {
  try {
    const base = 'OST Data Archive'
    const titleRun = run.value?.name || 'Observation Run'
    const date = dateString.value ? ` (${dateString.value})` : ''
    document.title = `${titleRun}${date} – ${base}`
    const desc = `Observation run ${titleRun}${date}: status, objects, and plots.`
    let tag = document.querySelector('meta[name="description"]')
    if (!tag) {
      tag = document.createElement('meta')
      tag.setAttribute('name', 'description')
      document.head.appendChild(tag)
    }
    tag.setAttribute('content', desc)
  } catch {}
})

const ensureBokehLoaded = async () => {
  if (window.Bokeh) return
  await new Promise((resolve, reject) => {
    const script = document.createElement('script')
    const ver = import.meta.env.VITE_BOKEH_VERSION || '3.8.0'
    script.src = `https://cdn.bokeh.org/bokeh/release/bokeh-${ver}.min.js`
    script.onload = resolve
    script.onerror = reject
    document.head.appendChild(script)
  })
}

const toHjd = (dateStr) => {
  if (!dateStr) return null
  const ms = new Date(dateStr).getTime()
  if (Number.isNaN(ms)) return null
  return ms / 86400000 + 2440587.5
}

const openVisibility = async (row) => {
  visibilityError.value = ''
  visibilityDialog.value = true
  try {
    visibilityLoading.value = true
    await ensureBokehLoaded()
    const cacheKey = `${runId}:${row.id}`
    let item = visibilityCache.get(cacheKey)
    if (!item) {
      const params = new URLSearchParams({
        run_id: String(runId),
        ra: String(row.ra),
        dec: String(row.dec),
        start_hjd: String(toHjd(row.observed_start) ?? ''),
        expo_time: String(row.expo_time || 0)
      })
      const base = import.meta.env.VITE_API_BASE || '/api'
      const res = await fetch(`${base}/runs/visibility/?${params.toString()}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      item = await res.json()
      visibilityCache.set(cacheKey, item)
    }
    const container = document.getElementById('visibility-container')
    if (container) container.innerHTML = ''
    window.Bokeh.embed.embed_item(item, 'visibility-container')
    try { notify.success('Visibility loaded') } catch {}
  } catch (e) {
    visibilityError.value = 'Failed to load visibility plot.'
    console.error(e)
  } finally {
    visibilityLoading.value = false
  }
}

const loadConditions = async () => {
  try {
    conditionsError.value = ''
    conditionsLoading.value = true
    // On very small portrait screens, show hint instead of rendering
    try {
      if (window.matchMedia && window.matchMedia('(max-width: 480px) and (orientation: portrait)').matches) {
        conditionsTooSmall.value = true
        conditionsVisible.value = false
        return
      }
    } catch {}

    await ensureBokehLoaded()
    const base = import.meta.env.VITE_API_BASE || '/api'
    let item = conditionsCache.get(String(runId))
    if (!item) {
      const res = await fetch(`${base}/runs/runs/${runId}/conditions/`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      item = await res.json()
      conditionsCache.set(String(runId), item)
    }
    const container = document.getElementById('conditions-container')
    if (container) container.innerHTML = ''
    window.Bokeh.embed.embed_item(item, 'conditions-container')
    try { notify.success('Observing conditions loaded') } catch {}
    conditionsVisible.value = true
  } catch (e) {
    console.error(e)
    conditionsError.value = 'Failed to load observing conditions.'
  } finally {
    conditionsLoading.value = false
  }
}

const hideConditions = () => {
  conditionsVisible.value = false
}

const restoreFocusEl = (elRef) => {
  try {
    const el = elRef?.value
    if (el && typeof el.focus === 'function') setTimeout(() => el.focus(), 0)
  } catch {}
}

const closeVisibility = () => {
  visibilityDialog.value = false
  restoreFocusEl(visibilityCloseBtn)
}

const closeFov = () => {
  fovDialog.value = false
  restoreFocusEl(fovCloseBtn)
}

const openNotesDialog = () => {
  newNote.value = run.value?.note || ''
  notesDialog.value = true
}

const closeNotesDialog = () => {
  notesDialog.value = false
  restoreFocusEl(notesCloseBtn)
}

const saveRunNotes = async () => {
  try {
    await api.updateObservationRun(runId, { note: newNote.value })
    const data = await api.getObservationRun(runId)
    run.value = data
    notesDialog.value = false
    try { notify.success('Notes updated') } catch {}
  } catch (e) {
    console.error(e)
  }
}

const openObsTypeDialog = () => {
  editSpectroscopy.value = !!run.value?.spectroscopy
  editPhotometry.value = !!run.value?.photometry
  obsTypeDialog.value = true
}

const closeObsTypeDialog = () => {
  obsTypeDialog.value = false
  try { const el = obsTypeCloseBtn.value; if (el && typeof el.focus === 'function') setTimeout(() => el.focus(), 0) } catch {}
}

const saveObsType = async () => {
  try {
    savingObsType.value = true
    await api.updateObservationRun(runId, { spectroscopy: editSpectroscopy.value, photometry: editPhotometry.value })
    const data = await api.getObservationRun(runId)
    run.value = data
    obsTypeDialog.value = false
    try { notify.success('Observation type updated') } catch {}
  } catch (e) {
    console.error('Error updating observation type', e)
  } finally {
    savingObsType.value = false
  }
}

const openTagDialog = async () => {
  try {
    // Load available tags if not loaded
    if (!availableTags.value.length) {
      const data = await api.getTags()
      availableTags.value = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : [])
    }
    // Preselect current run tags by pk
    if (Array.isArray(run.value?.tags)) {
      selectedTags.value = run.value.tags
        .map(t => (t && typeof t === 'object') ? t.pk : null)
        .filter(v => v != null)
    }
    tagDialog.value = true
  } catch (e) {
    console.error(e)
  }
}

const closeTagDialog = () => {
  tagDialog.value = false
  restoreFocusEl(tagCloseBtn)
}

const saveRunTags = async () => {
  try {
    await api.updateObservationRun(runId, { tag_ids: selectedTags.value })
    const data = await api.getObservationRun(runId)
    run.value = data
    tagDialog.value = false
    try { notify.success('Tags updated') } catch {}
  } catch (e) {
    console.error(e)
  }
}

const openSkyFov = async (row) => {
  fovDialog.value = true
  fovError.value = ''
  try {
    fovLoading.value = true
    await ensureBokehLoaded()
    const key = `${row.id}:${row.ra}:${row.dec}`
    let item = fovCache.get(key)
    if (!item) {
      const params = new URLSearchParams({
        ra: String(row.ra),
        dec: String(row.dec),
        fov_x: String(0.5),
        fov_y: String(0.5),
        scale: String(30),
        rotation: String(0),
        constellations: 'true'
      })
      const base = import.meta.env.VITE_API_BASE || '/api'
      const res = await fetch(`${base}/runs/fov/?${params.toString()}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      item = await res.json()
      fovCache.set(key, item)
    }
    const container = document.getElementById('fov-container')
    if (container) container.innerHTML = ''
    window.Bokeh.embed.embed_item(item, 'fov-container')
    try { notify.success('Sky FOV loaded') } catch {}
  } catch (e) {
    console.error(e)
    fovError.value = 'Failed to load sky FOV.'
  } finally {
    fovLoading.value = false
  }
}

// Image preview dialog
const previewDialog = ref(false)
const previewTitle = ref('')
const previewUrl = ref('')
const previewLoading = ref(false)
const openPreview = (df) => {
  previewTitle.value = df?.file_name || 'Preview'
  previewLoading.value = true
  previewUrl.value = ''
  previewDialog.value = true
  // Defer setting URL to next tick to ensure dialog renders placeholder immediately
  setTimeout(() => {
    previewUrl.value = api.getDataFileThumbnailUrl(df?.pk || df?.id, 800)
  }, 0)
}
const handlePreviewLoad = () => {
  previewLoading.value = false
}
// FITS header dialog
const headerDialog = ref(false)
const headerTitle = ref('')
const headerLoading = ref(false)
const headerError = ref('')
const headerEntries = ref([])
const openHeader = async (df) => {
  headerTitle.value = df?.file_name || 'FITS Header'
  headerError.value = ''
  headerEntries.value = []
  headerDialog.value = true
  try {
    headerLoading.value = true
    const payload = await api.getDataFileHeader(df?.pk || df?.id)
    const hdr = (payload && payload.header) ? payload.header : {}
    // Convert object to sorted entries (keys alphabetical)
    headerEntries.value = Object.entries(hdr).sort((a, b) => String(a[0]).localeCompare(String(b[0])))
  } catch (e) {
    console.error('Failed to fetch FITS header', e)
    headerError.value = 'Failed to fetch FITS header.'
  } finally {
    headerLoading.value = false
  }
}
const formatHeaderValue = (v) => {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') {
    try { return JSON.stringify(v) } catch { return String(v) }
  }
  return String(v)
}
// Downloads
const selectedIds = ref([])
const selectAll = ref(false)
const downloadingAll = ref(false)
const toggleSelectAll = () => {
  if (selectAll.value) {
    selectedIds.value = (dataFiles.value || []).map(df => df.pk || df.id)
  } else {
    selectedIds.value = []
  }
}
watch(dataFiles, () => {
  // Reset selectAll when page changes
  selectAll.value = false
  selectedIds.value = []
})
const downloadAll = async () => {
  try {
    downloadingAll.value = true
    const url = api.getRunDataFilesZipUrl(runId)
    window.location.href = url
  } finally {
    downloadingAll.value = false
  }
}
const downloadSelected = () => {
  if (!selectedIds.value.length) return
  const url = api.getRunDataFilesZipUrl(runId, selectedIds.value)
  window.location.href = url
}


const buildCurrentFilters = () => ({
  file_type: dfFilterType.value || undefined,
  instrument: dfFilterInstrument.value || undefined,
  main_target: dfFilterTarget.value || undefined,
  exptime_min: dfFilterExpMin.value != null && dfFilterExpMin.value !== '' ? dfFilterExpMin.value : undefined,
  exptime_max: dfFilterExpMax.value != null && dfFilterExpMax.value !== '' ? dfFilterExpMax.value : undefined,
  file_name: dfFilterFileName.value || undefined,
  exposure_type: Array.isArray(dfFilterExposureTypes.value) && dfFilterExposureTypes.value.length ? dfFilterExposureTypes.value : undefined,
  spectroscopy: dfFilterSpectroscopy.value,
})

const downloadFiltered = () => {
  const url = api.getRunDataFilesZipUrl(runId, [], buildCurrentFilters())
  window.location.href = url
}

// Async job helpers
const pollJobUntilReady = async (jobId, { timeoutMs = 120000, intervalMs = 1500 } = {}) => {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const status = await api.getDownloadJobStatus(jobId)
    if (status?.status === 'done' && status?.url) {
      return status
    }
    if (status?.status === 'failed' || status?.status === 'cancelled') {
      throw new Error(status?.error || 'Job failed')
    }
    await new Promise(r => setTimeout(r, intervalMs))
  }
  throw new Error('Timed out waiting for download job')
}

const triggerAsyncDownload = async (ids = [], filters = {}) => {
  try {
    downloadingAll.value = true
    const res = await api.createRunDownloadJob(runId, ids, filters)
    const jobId = res?.job_id
    if (!jobId) throw new Error('Job not created')
    try { notify.success('Preparing download...') } catch {}
    try {
      const status = await pollJobUntilReady(jobId)
      await api.downloadJobFile(jobId)
    } catch (e) {
      // Show a clearer message to the user (e.g., cancelled by admin) rather than a generic uncaught error
      try { notify.error(e?.message || 'Download job failed') } catch {}
      return
    }
  } finally {
    downloadingAll.value = false
  }
}

const handleDownloadAll = async () => {
  // If many files, prefer async job
  if ((dataFilesTotal.value || 0) > 5) {
    await triggerAsyncDownload([], {})
  } else {
    await downloadAll()
  }
}

const handleDownloadFiltered = async () => {
  if ((dataFilesTotal.value || 0) > 5) {
    await triggerAsyncDownload([], buildCurrentFilters())
  } else {
    downloadFiltered()
  }
}

const handlePreviewError = (e) => {
  try { notify.error('Failed to load preview') } catch {}
}

const binningOptions = computed(() => {
  const set = new Set((dataFiles.value || []).map(f => f?.binning).filter(Boolean))
  return Array.from(set)
})
</script>

<style scoped>
.run-detail {
  padding: 20px 0;
}

/* Link styling similar to Dashboard tables */
.custom-table :deep(a) {
  color: var(--v-theme-primary);
  text-decoration: none;
  font-weight: 600;
  transition: all var(--v-theme-transition-fast);
  position: relative;
  padding: 2px 4px;
  border-radius: var(--v-theme-radius-sm);
  background-color: rgba(var(--v-theme-primary-light), 0.3);
  display: inline-block;
  margin: -2px -4px;
}

.custom-table :deep(a:hover) {
  color: var(--v-theme-primary-dark);
  background-color: rgba(var(--v-theme-primary-light), 0.9);
  transform: translateY(-1px);
}

.custom-table :deep(a::after) {
  content: '';
  position: absolute;
  width: 100%;
  height: 2px;
  bottom: 0;
  left: 0;
  background-color: var(--v-theme-primary);
  transform: scaleX(0);
  transition: transform var(--v-theme-transition-fast);
  border-radius: var(--v-theme-radius-sm);
}

.custom-table :deep(a:hover::after) {
  transform: scaleX(1);
}

.conditions-wrapper {
  width: 100%;
}

.conditions-wrapper.hidden {
  display: none;
}

.uniform-height {
  height: 260px;
  display: flex;
  flex-direction: column;
}

.uniform-height .v-card-text {
  flex: 1;
  overflow-y: auto;
}

.preview-container {
  min-height: 320px; /* reserve space so dialog doesn't jump */
}
.preview-placeholder {
  height: 300px;
}

.expand-clickable {
  cursor: pointer;
}
.expand-clickable:hover {
  background-color: rgba(var(--v-theme-primary), 0.04);
}

.override-clear-btn {
  min-height: 30px;
  padding-top: 5px;
  padding-bottom: 5px;
}
</style> 