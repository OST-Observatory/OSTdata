<template>
  <v-container class="py-4">
    <h1 class="text-h4 mb-4">Admin</h1>
    <v-row>
      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Tags</v-card-title>
          <v-card-text>
            Create, edit, and delete tags.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/tags' }" aria-label="Open Tags management">
              Open Tags
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Users & Roles</v-card-title>
          <v-card-text>
            Manage user activation and staff roles.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/users' }" aria-label="Open Users management">
              Open Users
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Download Jobs</v-card-title>
          <v-card-text>
            Monitor download jobs; cancel stuck tasks.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/jobs' }" aria-label="Open Download Jobs">
              Open Download Jobs
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Health</v-card-title>
          <v-card-text>
            Quick system diagnostics (API/Bokeh versions).
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/health' }" aria-label="Open Health">
              Open Health
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Data Maintenance</v-card-title>
          <v-card-text>
            Utilities for tags, objects, and runs.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/maintenance' }" aria-label="Open Maintenance">
              Open Maintenance
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Observation Runs</v-card-title>
          <v-card-text>
            Review runs and update metadata.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/observation-runs' }" aria-label="Open Observation Runs">
              Open Runs
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Objects</v-card-title>
          <v-card-text>
            Manage objects and attributes.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/objects' }" aria-label="Open Objects">
              Open Objects
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Exposure Type Discrepancies</v-card-title>
          <v-card-text>
            Review and resolve exposure type classification discrepancies.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/exposure-type-discrepancies' }" aria-label="Open Exposure Type Discrepancies">
              Open Discrepancies
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Spectrograph Management</v-card-title>
          <v-card-text>
            Manage spectrograph property for data files with spectrograph set or WAVE exposure type.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/spectrograph-files' }" aria-label="Open Spectrograph Management">
              Open Spectrograph
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="6" lg="4">
        <v-card variant="outlined" class="mb-4">
          <v-card-title class="text-h6">Plate Solving</v-card-title>
          <v-card-text>
            Manage plate solving for data files.
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" :to="{ path: '/admin/plate-solving' }" aria-label="Open Plate Solving">
              Open Plate Solving
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
// Guard in router ensures only admins reach this view
</script>

<style scoped>
</style>


