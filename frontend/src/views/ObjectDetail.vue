<template>
  <v-container fluid>
    <h1 class="text-h4 mb-2">{{ displayTitle }}</h1>
    <!-- <v-row>
      <v-col cols="12">
        <v-card>
          <v-card-title>
            <span class="sr-only">Object summary</span>
          </v-card-title>
        </v-card>
      </v-col>
    </v-row> -->

    <!-- Summary Section -->
    <v-row>
      <!-- Basic Data -->
      <v-col cols="12" md="4">
        <v-card class="uniform-height">
          <v-card-title class="d-flex justify-space-between align-center">
            Basic Data
            <v-btn
              v-if="isAuthenticated"
              icon="mdi-pencil"
              size="small"
              variant="text"
              aria-label="Edit basic data"
              @click="openBasicDialog"
            ></v-btn>
          </v-card-title>
          <v-card-text>
            <v-row>
              <v-col cols="6">
                <v-list>
                  <v-list-item>
                    <v-list-item-title>Right Ascension:</v-list-item-title>
                    <v-list-item-subtitle class="font-mono">{{ formatRA(object?.ra) }}</v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Declination:</v-list-item-title>
                    <v-list-item-subtitle class="font-mono">{{ formatDec(object?.dec) }}</v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Object Type:</v-list-item-title>
                    <v-list-item-subtitle>{{ object?.object_type_display }}</v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Main Target:</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-icon :color="object?.is_main ? 'success' : 'error'" size="small">
                        {{ object?.is_main ? 'mdi-check-circle' : 'mdi-close-circle' }}
                      </v-icon>
                      {{ object?.is_main ? 'Yes' : 'No' }}
                    </v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>SIMBAD Resolved:</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-icon :color="object?.simbad_resolved ? 'success' : 'error'" size="small">
                        {{ object?.simbad_resolved ? 'mdi-check-circle' : 'mdi-close-circle' }}
                      </v-icon>
                      {{ object?.simbad_resolved ? 'Yes' : 'No' }}
                    </v-list-item-subtitle>
                  </v-list-item>
                </v-list>
              </v-col>
              <v-col cols="6">
                <v-list>
                  <v-list-item>
                    <v-list-item-title>Spectroscopy:</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-icon :color="object?.spectroscopy ? 'success' : 'error'" size="small">
                        {{ object?.spectroscopy ? 'mdi-check-circle' : 'mdi-close-circle' }}
                      </v-icon>
                      {{ object?.spectroscopy ? 'Yes' : 'No' }}
                    </v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Photometry:</v-list-item-title>
                    <v-list-item-subtitle>
                      <v-icon :color="object?.photometry ? 'success' : 'error'" size="small">
                        {{ object?.photometry ? 'mdi-check-circle' : 'mdi-close-circle' }}
                      </v-icon>
                      {{ object?.photometry ? 'Yes' : 'No' }}
                    </v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Total Exposure Time:</v-list-item-title>
                    <v-list-item-subtitle>{{ totalExposureTime }}s</v-list-item-subtitle>
                  </v-list-item>
                  <v-list-item>
                    <v-list-item-title>Internal Identifiers:</v-list-item-title>
                    <v-list-item-subtitle>{{ internalIdentifiers }}</v-list-item-subtitle>
                  </v-list-item>
                </v-list>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Notes -->
      <v-col cols="12" md="3">
        <v-card class="uniform-height">
          <v-card-title class="d-flex justify-space-between align-center">
            Notes
            <v-btn
              v-if="isAuthenticated"
              icon="mdi-pencil"
              size="small"
              variant="text"
              @click="openNotesDialog"
            ></v-btn>
          </v-card-title>
          <v-card-text>
            <div v-if="object?.note" v-html="formatNotes(object.note)"></div>
            <div v-else class="text-grey">No notes available</div>
          </v-card-text>
        </v-card>
      </v-col>

      <!-- Tags -->
      <v-col cols="12" md="2">
        <v-card class="uniform-height">
          <v-card-title class="d-flex justify-space-between align-center">
            Tags
            <v-btn
              v-if="isAuthenticated"
              icon="mdi-pencil"
              size="small"
              variant="text"
              @click="openTagDialog"
            ></v-btn>
          </v-card-title>
          <v-card-text>
            <div v-if="normalizedObjectTags.length" class="d-flex flex-wrap gap-2">
              <v-chip
                v-for="(tag, idx) in normalizedObjectTags"
                :key="tag.pk || tag.name || idx"
                :color="tag.color"
                variant="outlined"
                size="small"
              >
                {{ tag.name }}
              </v-chip>
            </div>
            <div v-else class="text-grey">No tags assigned</div>
          </v-card-text>
        </v-card>
      </v-col>
      
      <!-- Aladin Lite Sky Map -->
      <v-col cols="12" md="3">
        <v-card class="uniform-height">
          <v-card-title>Sky Map</v-card-title>
          <v-card-text>
            <div v-if="aladinLoading" class="d-flex align-center justify-center" style="width: 100%; height: 265px;">
              <v-progress-circular indeterminate color="primary" />
            </div>
            <div v-show="!aladinLoading" id="aladin-lite-div" style="width: 100%; height: 265px;"></div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Edit Basic Data Dialog -->
    <v-dialog v-model="basicDialog" max-width="520" @keydown.esc.prevent="closeBasicDialog" aria-labelledby="edit-basic-title">
      <v-card>
        <v-card-title id="edit-basic-title">Edit Basic Data</v-card-title>
        <v-card-text>
          <v-form>
            <v-select
              v-model="editObjectType"
              :items="objectTypeOptions"
              item-title="title"
              item-value="value"
              label="Object Type"
              variant="outlined"
              density="comfortable"
              hide-details
            />
            <div class="d-flex align-center mt-3" style="gap: 16px">
              <v-switch v-model="editSpectroscopy" label="Spectroscopy" color="primary" hide-details density="comfortable" />
              <v-switch v-model="editPhotometry" label="Photometry" color="primary" hide-details density="comfortable" />
            </div>
          </v-form>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" variant="flat" :loading="savingBasic" @click="saveBasicData">Save</v-btn>
          <v-btn variant="text" @click="closeBasicDialog" ref="basicCloseBtn">Cancel</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Sky Map and Aliases -->
    <v-row>

      <!-- Aliases -->
      <v-col cols="12" md="12">
        <v-card>
          <v-card-title>Aliases</v-card-title>
          <v-card-text>
            <div v-if="aliases?.length" class="d-flex flex-wrap gap-2">
              <v-chip
                v-for="alias in aliases"
                :key="alias.pk"
                variant="outlined"
                size="small"
              >
                <a v-if="alias.href" :href="alias.href" target="_blank" class="text-decoration-none">
                  {{ alias.name }}
                </a>
                <span v-else>{{ alias.name }}</span>
              </v-chip>
            </div>
            <div v-else class="text-grey">No aliases known</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <!-- Observation Runs Section -->
    <v-row @click="expandRunsIfCollapsed" :class="{ 'expand-clickable': !showObservationRuns }">
      <v-col cols="12">
        <v-card>
          <v-card-title class="d-flex justify-space-between align-center">
            Observation Runs ({{ observationRuns.length }})
            <v-btn
              :icon="showObservationRuns ? 'mdi-eye-off' : 'mdi-eye'"
              size="small"
              variant="text"
              @click.stop="toggleObservationRuns"
              :aria-label="showObservationRuns ? 'Collapse section' : 'Expand section'"
              :aria-expanded="showObservationRuns ? 'true' : 'false'"
              aria-controls="object-observation-runs"
            ></v-btn>
          </v-card-title>
          <v-card-subtitle v-if="!showObservationRuns" class="text-caption text-secondary px-4 pt-0 pb-2">
            Click anywhere on this section to expand.
          </v-card-subtitle>
          
          <v-expand-transition>
            <div v-show="showObservationRuns" id="object-observation-runs">
              <div class="px-4">
              <v-table class="custom-table">
                <thead>
                  <tr>
                    <th class="text-primary">Date</th>
                    <th class="text-primary">Nobs [FITS/IMG/SER]</th>
                    <th class="text-primary">Lights</th>
                    <th class="text-primary">Flats</th>
                    <th class="text-primary">Darks</th>
                    <th class="text-primary">Other</th>
                    <th class="text-primary">Exposure Time [s]</th>
                    <th class="text-primary">Tags</th>
                    <th class="text-primary">Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in obsRunPagedItems" :key="item.pk || item.id">
                    <td>
                      <router-link :to="`/observation-runs/${item.pk || item.id}`" class="text-decoration-none primary--text cell-truncate">
                        {{ formatRunName(item) }}
                      </router-link>
                    </td>
                    <td>{{ item.n_fits }}/{{ item.n_img }}/{{ item.n_ser }}</td>
                    <td>{{ getCount(item, ['n_light', 'lights']) }}</td>
                    <td>{{ getCount(item, ['n_flat', 'flats']) }}</td>
                    <td>{{ getCount(item, ['n_dark', 'darks']) }}</td>
                    <td>{{ getOtherCount(item) }}</td>
                    <td>{{ formatExposureTime(item.expo_time) }}</td>
                    <td>
                      <div class="d-flex flex-wrap gap-1">
                        <v-chip
                          v-for="tag in (item.tags || [])"
                          :key="tag.pk || tag.name"
                          :color="tag.color"
                          variant="outlined"
                          size="x-small"
                        >
                          {{ tag.name }}
                        </v-chip>
                      </div>
                    </td>
                    <td>
                      <v-chip :color="getStatusColor(item.reduction_status)" size="small">
                        {{ item.reduction_status || 'n/a' }}
                      </v-chip>
                    </td>
                  </tr>
                  <tr v-if="!Array.isArray(observationRuns) || observationRuns.length === 0">
                    <td colspan="5" class="text-caption text-secondary">No runs.</td>
                  </tr>
                </tbody>
              </v-table>
              <v-card-actions class="d-flex align-center justify-space-between px-4 py-2 card-actions-responsive">
                <div class="d-flex align-center actions-left">
                  <span class="text-body-2 mr-4">Items per page:</span>
                  <v-select
                    v-model="runItemsPerPage"
                    :items="runPageSizeOptions"
                    item-title="title"
                    item-value="value"
                    density="compact"
                    variant="outlined"
                    hide-details
                    class="items-per-page-select"
                    style="width: 100px"
                    @update:model-value="handleRunItemsPerPageChange"
                    aria-label="Items per page"
                  ></v-select>
                </div>

                <div class="d-flex align-center actions-right">
                  <span class="text-body-2 mr-4">
                    {{ obsRunPaginationInfo }}
                  </span>
                  <v-btn
                    icon="mdi-page-first"
                    variant="text"
                    :disabled="runPage === 1"
                    @click="handleRunPageChange(1)"
                    class="mx-1 pagination-btn"
                    aria-label="First page"
                  ></v-btn>
                  <v-btn
                    icon="mdi-chevron-left"
                    variant="text"
                    :disabled="runPage === 1"
                    @click="handleRunPageChange(runPage - 1)"
                    class="mx-1 pagination-btn"
                    aria-label="Previous page"
                  ></v-btn>
                  <v-btn
                    icon="mdi-chevron-right"
                    variant="text"
                    :disabled="runPage >= obsRunTotalPages"
                    @click="handleRunPageChange(runPage + 1)"
                    class="mx-1 pagination-btn"
                    aria-label="Next page"
                  ></v-btn>
                  <v-btn
                    icon="mdi-page-last"
                    variant="text"
                    :disabled="runPage >= obsRunTotalPages"
                    @click="handleRunPageChange(obsRunTotalPages)"
                    class="mx-1 pagination-btn"
                    aria-label="Last page"
                  ></v-btn>
                </div>
              </v-card-actions>
              </div>
            </div>
          </v-expand-transition>
        </v-card>
      </v-col>
    </v-row>

    <!-- Data Files Section -->
    <v-row @click="expandDataFilesIfCollapsed" :class="{ 'expand-clickable': !showDataFiles }">
      <v-col cols="12">
        <v-card>
          <v-card-title class="d-flex justify-space-between align-center">
            <span class="d-flex align-center">
              Data Files ({{ filteredDataFiles.length }})
              <v-progress-circular v-if="loadingDataFiles" indeterminate size="16" width="2" class="ml-2" />
            </span>
            <v-btn
              :icon="showDataFiles ? 'mdi-eye-off' : 'mdi-eye'"
              size="small"
              variant="text"
              @click.stop="toggleDataFiles"
              :aria-label="showDataFiles ? 'Collapse section' : 'Expand section'"
              :aria-expanded="showDataFiles ? 'true' : 'false'"
              aria-controls="object-data-files"
            ></v-btn>
          </v-card-title>
          <v-card-subtitle v-if="!showDataFiles" class="text-caption text-secondary px-4 pt-0 pb-2">
            Click anywhere on this section to expand.
          </v-card-subtitle>
          
          <v-expand-transition>
            <div v-show="showDataFiles" id="object-data-files">
              <div class="px-4">
              <!-- Filters -->
              <div class="d-flex align-center flex-wrap mb-1 px-4" style="gap: 12px">
                <v-text-field v-model="dfFilterFileName" label="File name contains" density="comfortable" variant="outlined" style="min-width: 240px" clearable />
                <v-text-field v-model="dfFilterType" label="File type contains" density="comfortable" variant="outlined" style="min-width: 180px" clearable />
                <v-text-field v-model="dfFilterInstrument" label="Instrument contains" density="comfortable" variant="outlined" style="min-width: 200px" clearable />
                <v-select
                  v-model="dfFilterBinning"
                  :items="binningOptions"
                  label="Binning"
                  density="comfortable"
                  variant="outlined"
                  style="min-width: 160px"
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
                  style="min-width: 220px"
                  clearable
                />
                <v-select
                  v-model="dfFilterSpectroscopy"
                  :items="spectroscopyOptions"
                  label="Spectroscopy"
                  density="comfortable"
                  variant="outlined"
                  style="min-width: 180px"
                  clearable
                />
                <v-text-field v-model.number="dfFilterExpMin" type="number" label="Exp min [s]" density="comfortable" variant="outlined" style="min-width: 160px" clearable />
                <v-text-field v-model.number="dfFilterExpMax" type="number" label="Exp max [s]" density="comfortable" variant="outlined" style="min-width: 160px" clearable />
              </div>
              <div class="d-flex align-center flex-wrap mb-4" style="gap: 12px">
                <v-btn variant="text" color="primary" @click="resetDfFilters" aria-label="Reset filters" block>Reset</v-btn>
              </div>

              <!-- Downloads -->
              <div class="d-flex align-center flex-wrap mb-2 px-4" style="gap: 12px" role="toolbar" aria-label="Data files actions">
                <v-btn color="primary" variant="flat" @click="handleDownloadAllObjectFiles" :loading="downloadingAll" aria-label="Download all files">Download all</v-btn>
                <v-btn color="primary" variant="text" :disabled="!filteredDataFiles.length" @click="handleDownloadFilteredObjectFiles" aria-label="Download filtered files">Download filtered</v-btn>
                <v-btn color="primary" variant="text" :disabled="!selectedIds.length" @click="downloadSelectedObjectFiles" :aria-label="`Download selected (${selectedIds.length})`">Download selected ({{ selectedIds.length }})</v-btn>
              </div>

              <v-skeleton-loader v-if="loadingDataFiles" type="table"></v-skeleton-loader>
              <template v-else>
                <v-table v-if="objDfPagedItems && objDfPagedItems.length" class="custom-table">
                  <thead>
                    <tr>
                      <th class="text-primary" style="width:36px">
                        <v-checkbox v-model="selectAll" density="compact" hide-details @change="toggleSelectAll" aria-label="Select all files" />
                      </th>
                      <th class="text-primary">File Name</th>
                      <th class="text-primary">Time</th>
                      <th class="text-primary">Target</th>
                      <th class="text-primary">Coordinates</th>
                      <th class="text-primary">File Type</th>
                      <th class="text-primary">Binning</th>
                      <th class="text-primary">Instrument</th>
                      <th class="text-primary">Exposure Type</th>
                      <th class="text-primary">Exp. Time</th>
                      <th class="text-primary text-right">Tools</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="df in objDfPagedItems" :key="df.pk || df.id">
                      <td>
                        <v-checkbox v-model="selectedIds" :value="(df.pk || df.id)" density="compact" hide-details :aria-label="`Select ${df.file_name}`" />
                      </td>
                      <td>{{ df.file_name }}</td>
                      <td>{{ formatDate(df.obs_date) }}</td>
                      <td>
                        <template v-if="(df.exposure_type || '').toUpperCase() === 'LI'">
                          <router-link
                            v-if="df.main_target && df.main_target.trim()"
                            :to="`/objects/${getObjectIdByTargetName(df.main_target)}`"
                            class="text-decoration-none primary--text"
                          >{{ df.main_target }}</router-link>
                          <span v-else>{{ df.main_target || '—' }}</span>
                        </template>
                        <span v-else class="text-secondary">—</span>
                      </td>
                      <td>{{ df.ra_hms }} {{ df.dec_dms }}</td>
                      <td>{{ df.file_type }}</td>
                      <td>{{ df.binning || '1x1' }}</td>
                      <td>{{ df.instrument || '—' }}</td>
                      <td>{{ df.exposure_type_display || df.exposure_type }}</td>
                      <td>{{ formatExposureTime(df.exptime) }}</td>
                      <td class="text-right">
                        <v-btn
                          v-if="String(df.file_type || '').toUpperCase() !== 'SER'"
                          variant="text"
                          size="small"
                          icon
                          aria-label="Preview"
                          @click="openPreview(df)"
                        >
                          <v-icon>mdi-image-search</v-icon>
                        </v-btn>
                        <v-btn
                          variant="text"
                          size="small"
                          icon
                          :disabled="String(df.file_type || '').toUpperCase() !== 'FITS'"
                          :aria-label="`View FITS header for ${df.file_name}`"
                          @click="openHeader(df)"
                        >
                          <v-icon>mdi-file-document-outline</v-icon>
                        </v-btn>
                        <v-btn variant="text" size="small" icon :href="api.getDataFileDownloadUrl(df.pk || df.id)" :aria-label="`Download ${df.file_name}`">
                          <v-icon>mdi-download</v-icon>
                        </v-btn>
                      </td>
                    </tr>
                  </tbody>
                </v-table>
                <div v-else class="text-caption text-secondary">No data files.</div>
                </template>
              <v-card-actions class="d-flex align-center justify-space-between px-4 py-2 card-actions-responsive">
                <div class="d-flex align-center actions-left">
                  <span class="text-body-2 mr-4">Items per page:</span>
                  <v-select
                    v-model="objDfItemsPerPage"
                    :items="objDfPageSizeOptions"
                    item-title="title"
                    item-value="value"
                    density="compact"
                      variant="outlined"
                    hide-details
                    class="items-per-page-select"
                    style="width: 100px"
                    @update:model-value="handleObjDfItemsPerPageChange"
                    aria-label="Items per page"
                  ></v-select>
                  </div>

                <div class="d-flex align-center actions-right">
                  <span class="text-body-2 mr-4">
                    {{ objDfPaginationInfo }}
                  </span>
                  <v-btn
                    icon="mdi-page-first"
                    variant="text"
                    :disabled="objDfPage === 1"
                    @click="handleObjDfPageChange(1)"
                    class="mx-1 pagination-btn"
                    aria-label="First page"
                  ></v-btn>
                  <v-btn
                    icon="mdi-chevron-left"
                    variant="text"
                    :disabled="objDfPage === 1"
                    @click="handleObjDfPageChange(objDfPage - 1)"
                    class="mx-1 pagination-btn"
                    aria-label="Previous page"
                  ></v-btn>
                  <v-btn
                    icon="mdi-chevron-right"
                    variant="text"
                    :disabled="objDfPage >= objDfTotalPages"
                    @click="handleObjDfPageChange(objDfPage + 1)"
                    class="mx-1 pagination-btn"
                    aria-label="Next page"
                  ></v-btn>
                  <v-btn
                    icon="mdi-page-last"
                    variant="text"
                    :disabled="objDfPage >= objDfTotalPages"
                    @click="handleObjDfPageChange(objDfTotalPages)"
                    class="mx-1 pagination-btn"
                    aria-label="Last page"
                  ></v-btn>
                </div>
              </v-card-actions>
              </div>
            </div>
          </v-expand-transition>
        </v-card>
      </v-col>
    </v-row>

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

    <!-- Tag Edit Dialog -->
    <v-dialog v-model="tagDialog" max-width="500px" @keydown.esc.prevent="closeTagDialog" aria-labelledby="edit-tags-title">
      <v-card>
        <v-card-title id="edit-tags-title">Edit Tags</v-card-title>
        <v-card-text role="group" aria-labelledby="tags-title">
        <h3 id="tags-title" class="sr-only">Select tags for this object</h3>
          <v-checkbox
            v-for="(tag, idx) in availableTags"
            :key="tag?.pk || tag?.name || idx"
            v-model="selectedTags"
            :value="tag?.pk"
            :label="tag?.name"
            :color="tag?.color"
          ></v-checkbox>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="saveTags">Save</v-btn>
          <v-btn @click="closeTagDialog" ref="tagCloseBtn">Cancel</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Edit Notes Dialog -->
    <v-dialog v-model="notesDialog" max-width="640" @keydown.esc.prevent="closeNotesDialog" aria-labelledby="edit-notes-title">
      <v-card>
        <v-card-title id="edit-notes-title">Edit Notes</v-card-title>
        <v-card-text>
          <v-textarea
            v-model="newNote"
            label="Notes"
            variant="outlined"
            rows="8"
            auto-grow
            clearable
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn color="primary" @click="saveNotes">Save</v-btn>
          <v-btn variant="text" @click="closeNotesDialog" ref="notesCloseBtn">Cancel</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/api'
import { useAuthStore } from '@/store/auth'
import { useNotifyStore } from '@/store/notify'

const route = useRoute()
const authStore = useAuthStore()
const notify = useNotifyStore()

// Reactive data
const object = ref(null)
const aliases = ref([])
const observationRuns = ref([])
const dataFiles = ref([])
const availableTags = ref([])
const selectedTags = ref([])
const tagDialog = ref(false)
const tagCloseBtn = ref(null)
const notesDialog = ref(false)
const newNote = ref('')
const notesCloseBtn = ref(null)
const showObservationRuns = ref(false)
const showDataFiles = ref(false)
const loadingObservationRuns = ref(false)
const loadingDataFiles = ref(false)
const aladinLoading = ref(true)
const objDfPage = ref(1)
const objDfItemsPerPage = ref(10)
// Client-side pagination for Observation Runs table
const runPage = ref(1)
const runItemsPerPage = ref(10)
const runPageSizeOptions = [
  { title: '10', value: 10 },
  { title: '25', value: 25 },
  { title: '50', value: 50 },
  { title: '100', value: 100 },
  { title: 'All', value: -1 },
]
const basicDialog = ref(false)
const savingBasic = ref(false)
const basicCloseBtn = ref(null)
const editObjectType = ref(null)
const editSpectroscopy = ref(false)
const editPhotometry = ref(false)

// Computed properties
const isAuthenticated = computed(() => authStore.isAuthenticated)
const totalExposureTime = computed(() => {
  if (!dataFiles.value.length) return '0.0'
  const total = dataFiles.value
    .filter(file => file.exposure_type === 'LI')
    .reduce((sum, file) => sum + (file.exptime || 0), 0)
  return total.toFixed(1)
})

const internalIdentifiers = computed(() => {
  if (!aliases.value.length) return 'None'
  return aliases.value
    .filter(alias => alias.info_from_header)
    .map(alias => alias.name)
    .join(', ')
})

// Extract SIMBAD common name from "NAME xyz" alias pattern
const simbadCommonName = computed(() => {
  const identifiers = object.value?.identifiers || object.value?.identifier_set || []
  const nameAlias = identifiers.find(id => id?.name?.startsWith('NAME '))
  if (nameAlias) {
    return nameAlias.name.replace(/^NAME\s+/, '')
  }
  return null
})

// Display title: "internal name (SIMBAD name)" or just "internal name"
// Only show SIMBAD name if it differs from the internal name
const displayTitle = computed(() => {
  const name = object.value?.name || 'Object'
  const simbadName = simbadCommonName.value
  if (simbadName && simbadName.toLowerCase() !== name.toLowerCase()) {
    return `${name} (${simbadName})`
  }
  return name
})

const objectTypeOptions = [
  { title: 'Galaxy', value: 'GA' },
  { title: 'Star Cluster', value: 'SC' },
  { title: 'Nebula', value: 'NE' },
  { title: 'Star', value: 'ST' },
  { title: 'Solar System', value: 'SO' },
  { title: 'Other', value: 'OT' },
  { title: 'Unknown', value: 'UK' },
]

const openBasicDialog = () => {
  editObjectType.value = object.value?.object_type || null
  editSpectroscopy.value = !!object.value?.spectroscopy
  editPhotometry.value = !!object.value?.photometry
  basicDialog.value = true
}

const closeBasicDialog = () => {
  basicDialog.value = false
  try {
    const el = basicCloseBtn.value
    if (el && typeof el.focus === 'function') setTimeout(() => el.focus(), 0)
  } catch {}
}

const saveBasicData = async () => {
  if (!object.value) return
  try {
    savingBasic.value = true
    const payload = {
      object_type: editObjectType.value,
      spectroscopy: editSpectroscopy.value,
      photometry: editPhotometry.value,
    }
    await api.updateObject(object.value.pk || object.value.id, payload)
    const updated = await api.getObject(object.value.pk || object.value.id)
    object.value = updated
    basicDialog.value = false
    try { notify.success('Basic data updated') } catch {}
  } catch (e) {
    console.error('Error saving basic data', e)
  } finally {
    savingBasic.value = false
  }
}

// Table headers
const observationRunHeaders = [
  { title: 'Date', key: 'name', sortable: true },
  { title: 'Nobs', key: 'n_fits', sortable: true },
  { title: 'Exposure Time [s]', key: 'expo_time', sortable: true },
  { title: 'Tags', key: 'tags', sortable: false },
  { title: 'Status', key: 'reduction_status', sortable: true }
]

const dataFileHeaders = [
  // replaced by objectDataFileHeaders below
]

const objectDataFileHeaders = [
  { title: '', key: 'select', sortable: false, width: 36 },
  { title: 'File Name', key: 'file_name', sortable: true },
  { title: 'Observation Date', key: 'obs_date', sortable: true },
  { title: 'Target', key: 'main_target', sortable: true },
  { title: 'Coordinates', key: 'coordinates', sortable: false },
  { title: 'File Type', key: 'file_type', sortable: true },
  { title: 'Binning', key: 'binning', sortable: false },
  { title: 'Instrument', key: 'instrument', sortable: true },
  { title: 'Exposure Type', key: 'exposure_type_display', sortable: true },
  { title: 'Exposure Time [s]', key: 'exptime', sortable: true },
  { title: 'Observation Run', key: 'observation_run', sortable: true },
  { title: 'Tools', key: 'tools', sortable: false },
]

// Methods
const loadObject = async () => {
  try {
    const objectId = route.params.id
    object.value = await api.getObject(objectId)
    await loadAliases(objectId)
    await loadObservationRuns(objectId)
    await loadDataFiles(objectId)
    await loadAvailableTags()
    initializeAladinLite()
  } catch (error) {
    console.error('Error loading object:', error)
  }
}

const loadAliases = async (objectId) => {
  try {
    // Try to derive aliases from object.identifiers if provided by API
    if (Array.isArray(object.value?.identifiers)) {
      aliases.value = object.value.identifiers
        .filter(id => id && id.info_from_header === false)
        .map(id => ({ pk: id.pk || id.id, name: id.name, href: id.href }))
    } else if (Array.isArray(object.value?.identifier_set)) {
      aliases.value = object.value.identifier_set
        .filter(id => id && id.info_from_header === false)
        .map(id => ({ pk: id.pk || id.id, name: id.name, href: id.href }))
    } else {
    aliases.value = []
    }
  } catch (error) {
    console.error('Error loading aliases:', error)
    aliases.value = []
  }
}

const loadObservationRuns = async (objectId) => {
  try {
    loadingObservationRuns.value = true
    const response = await api.getObjectObservationRuns(objectId)
    observationRuns.value = response
  } catch (error) {
    console.error('Error loading observation runs:', error)
  } finally {
    loadingObservationRuns.value = false
  }
}

const loadDataFiles = async (objectId) => {
  try {
    loadingDataFiles.value = true
    const response = await api.getObjectDataFiles(objectId)
    dataFiles.value = response
  } catch (error) {
    console.error('Error loading data files:', error)
  } finally {
    loadingDataFiles.value = false
  }
}

const loadAvailableTags = async () => {
  try {
    const data = await api.getTags()
    availableTags.value = Array.isArray(data?.results) ? data.results : (Array.isArray(data) ? data : [])
    if (Array.isArray(object.value?.tags)) {
      selectedTags.value = object.value.tags
        .map(t => (t && typeof t === 'object' ? t.pk : null))
        .filter(v => v != null)
    }
  } catch (error) {
    console.error('Error loading tags:', error)
  }
}

const initializeAladinLite = () => {
  // Wait for Aladin v3 script (no jQuery dependency)
  const maxRetries = 100 // 100 retries * 100ms = 10 seconds timeout
  let retryCount = 0

  const checkAndInitialize = () => {
    if (window.A && object.value?.ra && object.value?.dec) {
      try {
        window.A.aladin('#aladin-lite-div', {
          survey: 'P/DSS2/color',
          fov: 0.5,
          target: `${object.value.ra} ${object.value.dec}`,
          showZoomControl: false,
          showLayersControl: false,
          showGotoControl: false,
          showFrame: false
        })
        aladinLoading.value = false
      } catch (error) {
        console.error('Error initializing Aladin Lite:', error)
        const aladinDiv = document.getElementById('aladin-lite-div')
        if (aladinDiv) {
          aladinDiv.innerHTML = `
            <div style="padding: 20px; text-align: center; color: #666;">
              <p>Sky Map not available</p>
              <p>Coordinates: ${formatRA(object.value.ra)} ${formatDec(object.value.dec)}</p>
            </div>
          `
        }
        aladinLoading.value = false
      }
    } else if (window.A) {
      const aladinDiv = document.getElementById('aladin-lite-div')
      if (aladinDiv) {
        aladinDiv.innerHTML = `
          <div style="padding: 20px; text-align: center; color: #666;">
            <p>No coordinates available for sky map</p>
          </div>
        `
      }
      aladinLoading.value = false
    } else if (retryCount < maxRetries) {
      retryCount++
      setTimeout(checkAndInitialize, 100)
    } else {
      // Aladin script failed to load after timeout
      console.warn('Aladin Lite script failed to load after timeout')
      const aladinDiv = document.getElementById('aladin-lite-div')
      if (aladinDiv) {
        aladinDiv.innerHTML = `
          <div style="padding: 20px; text-align: center; color: #666;">
            <p>Sky Map could not be loaded</p>
          </div>
        `
      }
      aladinLoading.value = false
    }
  }

  checkAndInitialize()
}

const openTagDialog = () => {
  tagDialog.value = true
}

const closeTagDialog = () => {
  tagDialog.value = false
  try {
    const el = tagCloseBtn.value
    if (el && typeof el.focus === 'function') setTimeout(() => el.focus(), 0)
  } catch {}
}

const saveTags = async () => {
  try {
    const objectId = route.params.id
    await api.updateObject(objectId, { tag_ids: selectedTags.value })
    await loadObject() // Reload to get updated tags
    tagDialog.value = false
    try { notify.success('Tags updated') } catch {}
  } catch (error) {
    console.error('Error saving tags:', error)
  }
}

const toggleObservationRuns = () => {
  showObservationRuns.value = !showObservationRuns.value
}

const toggleDataFiles = () => {
  showDataFiles.value = !showDataFiles.value
}

const expandRunsIfCollapsed = () => {
  if (!showObservationRuns.value) showObservationRuns.value = true
}

const expandDataFilesIfCollapsed = () => {
  if (!showDataFiles.value) showDataFiles.value = true
}

const openNotesDialog = () => {
  newNote.value = object.value?.note || ''
  notesDialog.value = true
}

const closeNotesDialog = () => {
  notesDialog.value = false
  try {
    const el = notesCloseBtn.value
    if (el && typeof el.focus === 'function') setTimeout(() => el.focus(), 0)
  } catch {}
}

const saveNotes = async () => {
  try {
    const objectId = route.params.id
    await api.updateObject(objectId, { note: newNote.value })
    await loadObject()
    notesDialog.value = false
    try { notify.success('Notes updated') } catch {}
  } catch (error) {
    console.error('Error saving notes:', error)
  }
}

// Utility functions
const formatRA = (ra) => {
  if (!ra || ra === -1) return 'N/A'
  const hours = Math.floor(ra / 15)
  const minutes = Math.floor((ra % 15) * 4)
  const seconds = ((ra % 15) * 4 - minutes) * 60
  return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toFixed(1).padStart(4, '0')}`
}

const formatDec = (dec) => {
  if (!dec || dec === -1) return 'N/A'
  const sign = dec >= 0 ? '+' : '-'
  const absDec = Math.abs(dec)
  const degrees = Math.floor(absDec)
  const minutes = Math.floor((absDec - degrees) * 60)
  const seconds = ((absDec - degrees) * 60 - minutes) * 60
  return `${sign}${degrees.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toFixed(1).padStart(4, '0')}`
}

const formatNotes = (notes) => {
  return notes.replace(/\n/g, '<br>')
}

const formatDate = (date) => {
  if (!date) return 'N/A'
  return new Date(date).toLocaleDateString()
}

const formatExposureTime = (time) => {
  if (!time || time === 0) return '-'
  if (time >= 1) return time.toString()
  return time.toFixed(2)
}

// Count helpers (robust to numeric strings)
const getCount = (item, keys) => {
  for (const k of keys) {
    const v = item?.[k]
    if (typeof v === 'number') return v
    if (typeof v === 'string') {
      const s = v.trim()
      if (s !== '' && !Number.isNaN(Number(s))) return Number(s)
    }
  }
  return 0
}
const getOtherCount = (item) => {
  const total = getCount(item, ['n_total', 'n_datafiles', 'n_files', 'files'])
  const li = getCount(item, ['n_light', 'lights'])
  const fl = getCount(item, ['n_flat', 'flats'])
  const da = getCount(item, ['n_dark', 'darks'])
  const other = total - (li + fl + da)
  return other >= 0 ? other : 0
}

const formatRunName = (run) => {
  if (!run?.start_time || !run?.end_time) return run?.name
  const norm = (s) => {
    if (!s) return ''
    let x = String(s).split('.')[0].replace('T', ' ').replace('Z', '')
    const [d, tRaw] = x.split(' ')
    const t = (tRaw || '')
    const hm = t.includes(':') ? t.slice(0, 5) : t
    return { d: d || '', t: hm }
  }
  const s = norm(run.start_time)
  const e = norm(run.end_time)
  const startStr = s.d ? `${s.d} ${s.t}` : s.t
  const endStr = e.t
  return `${startStr}-${endStr}`
}

const formatRunNameFromId = (name) => {
  if (!name) return name
  const digits = String(name).replace(/\D/g, '')
  if (digits.length >= 8) {
    return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)}`
  }
  return name
}

const getStatusColor = (status) => {
  const colors = {
    'FR': 'success',
    'PR': 'warning',
    'ER': 'error',
    'NE': 'grey'
  }
  return colors[status] || 'grey'
}

const getStatusIcon = (status) => {
  const icons = {
    'FR': 'mdi-check-circle',
    'PR': 'mdi-clock',
    'ER': 'mdi-alert-circle',
    'NE': 'mdi-minus-circle'
  }
  return icons[status] || 'mdi-minus-circle'
}

const normalizedObjectTags = computed(() => {
  if (!Array.isArray(object.value?.tags)) return []
  return object.value.tags
    .map(t => (t && typeof t === 'object') ? t : null)
    .filter(Boolean)
})

// Lifecycle
onMounted(() => {
  loadObject()
})

// Filters state and helpers
const dfFilterFileName = ref('')
const dfFilterType = ref('')
const dfFilterInstrument = ref('')
const dfFilterBinning = ref(null)
const dfFilterExposureTypes = ref([])
const dfFilterSpectroscopy = ref(null)
const dfFilterExpMin = ref(null)
const dfFilterExpMax = ref(null)
// removed pixel filters

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

// no pixel count parsing needed anymore

const filteredDataFiles = computed(() => {
  let items = Array.isArray(dataFiles.value) ? dataFiles.value.slice() : []
  const name = (dfFilterFileName.value || '').toLowerCase()
  if (name) items = items.filter(f => (f.file_name || '').toLowerCase().includes(name))
  const ftype = (dfFilterType.value || '').toLowerCase()
  if (ftype) items = items.filter(f => (f.file_type || '').toLowerCase().includes(ftype))
  const instr = (dfFilterInstrument.value || '').toLowerCase()
  if (instr) items = items.filter(f => (f.instrument || '').toLowerCase().includes(instr))
  if (dfFilterBinning.value) {
    items = items.filter(f => (f.binning || '').toLowerCase() === String(dfFilterBinning.value).toLowerCase())
  }
  if (Array.isArray(dfFilterExposureTypes.value) && dfFilterExposureTypes.value.length) {
    const set = new Set(dfFilterExposureTypes.value)
    items = items.filter(f => set.has(f.exposure_type))
  }
  if (dfFilterSpectroscopy.value !== null && dfFilterSpectroscopy.value !== undefined && dfFilterSpectroscopy.value !== '') {
    items = items.filter(f => Boolean(f.spectroscopy) === Boolean(dfFilterSpectroscopy.value))
  }
  if (dfFilterExpMin.value != null && dfFilterExpMin.value !== '') {
    items = items.filter(f => (f.exptime || 0) >= Number(dfFilterExpMin.value))
  }
  if (dfFilterExpMax.value != null && dfFilterExpMax.value !== '') {
    items = items.filter(f => (f.exptime || 0) <= Number(dfFilterExpMax.value))
  }
  return items
})

const objDfPagedItems = computed(() => {
  if (objDfItemsPerPage.value === -1) return filteredDataFiles.value
  const start = (objDfPage.value - 1) * objDfItemsPerPage.value
  return filteredDataFiles.value.slice(start, start + objDfItemsPerPage.value)
})

// Checkbox select-all and selection helpers for paged items
const selectAll = ref(false)
watch(objDfPagedItems, () => {
  selectAll.value = false
  selectedIds.value = []
})
const toggleSelectAll = () => {
  if (selectAll.value) {
    selectedIds.value = (objDfPagedItems.value || []).map(df => df.pk || df.id)
  } else {
    selectedIds.value = []
  }
}

// For Object Detail, link target always resolves to the current object id
const getObjectIdByTargetName = (name) => {
  return object.value?.pk || object.value?.id || route.params.id
}

const objDfTotalPages = computed(() => {
  if (objDfItemsPerPage.value === -1) return 1
  return Math.max(1, Math.ceil((filteredDataFiles.value.length || 0) / (objDfItemsPerPage.value || 10)))
})

const objDfPaginationInfo = computed(() => {
  if (objDfItemsPerPage.value === -1) return `Showing all ${filteredDataFiles.value.length}`
  const start = (objDfPage.value - 1) * objDfItemsPerPage.value + 1
  const end = Math.min(objDfPage.value * objDfItemsPerPage.value, filteredDataFiles.value.length)
  return `${start}-${end} of ${filteredDataFiles.value.length}`
})

const objDfPageSizeOptions = [
  { title: '10', value: 10 },
  { title: '25', value: 25 },
  { title: '50', value: 50 },
  { title: '100', value: 100 },
  { title: 'All', value: -1 },
]

const handleObjDfPageChange = (newPage) => {
  if (newPage >= 1 && newPage <= objDfTotalPages.value) {
    objDfPage.value = newPage
  }
}

const handleObjDfItemsPerPageChange = () => {
  objDfPage.value = 1
}

// Observation runs pagination helpers
const obsRunPagedItems = computed(() => {
  const items = Array.isArray(observationRuns.value) ? observationRuns.value : []
  if (runItemsPerPage.value === -1) return items
  const start = (runPage.value - 1) * runItemsPerPage.value
  return items.slice(start, start + runItemsPerPage.value)
})
const obsRunTotalPages = computed(() => {
  const total = Array.isArray(observationRuns.value) ? observationRuns.value.length : 0
  if (runItemsPerPage.value === -1) return 1
  return Math.max(1, Math.ceil(total / (runItemsPerPage.value || 10)))
})
const obsRunPaginationInfo = computed(() => {
  const total = Array.isArray(observationRuns.value) ? observationRuns.value.length : 0
  if (runItemsPerPage.value === -1) return `Showing all ${total}`
  const start = (runPage.value - 1) * runItemsPerPage.value + 1
  const end = Math.min(runPage.value * runItemsPerPage.value, total)
  return `${start}-${end} of ${total}`
})
const handleRunPageChange = (newPage) => {
  if (newPage >= 1 && newPage <= obsRunTotalPages.value) {
    runPage.value = newPage
  }
}
const handleRunItemsPerPageChange = () => {
  runPage.value = 1
}

const resetDfFilters = () => {
  dfFilterFileName.value = ''
  dfFilterType.value = ''
  dfFilterInstrument.value = ''
  dfFilterBinning.value = null
  dfFilterExposureTypes.value = []
  dfFilterSpectroscopy.value = null
  dfFilterExpMin.value = null
  dfFilterExpMax.value = null
}

// Downloads & Preview
const selectedIds = ref([])
const downloadingAll = ref(false)
const downloadAllObjectFiles = async () => {
  try {
    downloadingAll.value = true
    // build ids from all dataFiles for this object
    const ids = (Array.isArray(dataFiles.value) ? dataFiles.value : []).map(f => f.pk || f.id)
    const url = api.getDataFilesZipUrl(ids)
    window.location.href = url
  } finally {
    downloadingAll.value = false
  }
}
const downloadSelectedObjectFiles = () => {
  if (!selectedIds.value.length) return
  const url = api.getDataFilesZipUrl(selectedIds.value)
  window.location.href = url
}
const downloadFilteredObjectFiles = () => {
  const ids = filteredDataFiles.value.map(f => f.pk || f.id)
  if (!ids.length) return
  const url = api.getDataFilesZipUrl(ids)
  window.location.href = url
}

// Async job helpers (bulk, across runs)
const pollJobUntilReady = async (jobId, { timeoutMs = 120000, intervalMs = 1500 } = {}) => {
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const status = await api.getDownloadJobStatus(jobId)
    if (status?.status === 'done' && status?.url) return status
    if (status?.status === 'failed' || status?.status === 'cancelled') throw new Error(status?.error || 'Job failed')
    await new Promise(r => setTimeout(r, intervalMs))
  }
  throw new Error('Timed out waiting for download job')
}

const triggerAsyncBulkDownload = async (ids = [], filters = {}) => {
  try {
    downloadingAll.value = true
    const res = await api.createBulkDownloadJob(ids, filters)
    const jobId = res?.job_id
    if (!jobId) throw new Error('Job not created')
    try {
      const status = await pollJobUntilReady(jobId)
      await api.downloadJobFile(jobId)
    } catch (e) {
      try { notify.error(e?.message || 'Download job failed') } catch {}
      return
    }
  } finally {
    downloadingAll.value = false
  }
}

const handleDownloadAllObjectFiles = async () => {
  const count = Array.isArray(dataFiles.value) ? dataFiles.value.length : 0
  if (count > 5) {
    const ids = (Array.isArray(dataFiles.value) ? dataFiles.value : []).map(f => f.pk || f.id)
    await triggerAsyncBulkDownload(ids, {})
  } else {
    await downloadAllObjectFiles()
  }
}

const handleDownloadFilteredObjectFiles = async () => {
  const count = filteredDataFiles.value.length
  if (count > 5) {
    const ids = filteredDataFiles.value.map(f => f.pk || f.id)
    await triggerAsyncBulkDownload(ids, {})
  } else {
    downloadFilteredObjectFiles()
  }
}

const previewDialog = ref(false)
const previewTitle = ref('')
const previewUrl = ref('')
const previewLoading = ref(false)
const openPreview = (df) => {
  previewTitle.value = df?.file_name || 'Preview'
  previewLoading.value = true
  previewUrl.value = ''
  previewDialog.value = true
  setTimeout(() => {
    previewUrl.value = api.getDataFileThumbnailUrl(df?.pk || df?.id, 800)
  }, 0)
}
const handlePreviewLoad = () => { previewLoading.value = false }
const handlePreviewError = () => { previewLoading.value = false }

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

// Binning options derived from data
const binningOptions = computed(() => {
  const set = new Set((dataFiles.value || []).map(f => f?.binning).filter(Boolean))
  return Array.from(set)
})

watch(object, (val) => {
  try {
    const base = 'OST Data Archive'
    const name = val?.name || 'Object'
    document.title = `${name} – ${base}`
    const desc = `Details for object ${name}: coordinates, runs, files and tags.`
    let tag = document.querySelector('meta[name="description"]')
    if (!tag) {
      tag = document.createElement('meta')
      tag.setAttribute('name', 'description')
      document.head.appendChild(tag)
    }
    tag.setAttribute('content', desc)
  } catch {}
})
// Preview dialog template is declared implicitly by state; ensure consumers handle open/close
</script>

<style scoped>
.preview-container {
  min-height: 320px;
}
.preview-placeholder {
  height: 300px;
}
.font-mono {
  font-family: 'Courier New', monospace;
}

.gap-1 {
  gap: 4px;
}

.gap-2 {
  gap: 8px;
}

.uniform-height {
  height: 340px;
  display: flex;
  flex-direction: column;
}

.uniform-height .v-card-text {
  flex: 1;
  overflow-y: auto;
}

.expand-clickable {
  cursor: pointer;
}

.expand-clickable:hover {
  background-color: rgba(var(--v-theme-primary), 0.04);
}

/* Align observation runs table styling with other detail tables */
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
.v-data-table :deep(td) {
  padding: 8px 16px !important;
}

/* Make links consistent with ObservationRuns.vue */
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

/* Single-line truncation with ellipsis for links */
.cell-truncate {
  display: inline-block;
  max-width: 320px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  vertical-align: bottom;
}
</style> 