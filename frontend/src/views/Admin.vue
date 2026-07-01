<template>
  <v-container class="py-4 admin-page">
    <header class="mb-6">
      <h1 class="text-h4 mb-1">Admin</h1>
      <p class="text-body-2 text-medium-emphasis mb-0">
        Administration and maintenance tools for the archive.
      </p>
    </header>

    <v-row>
      <v-col
        v-for="tile in adminTiles"
        :key="tile.to"
        cols="12"
        sm="6"
        lg="4"
      >
        <v-card
          variant="outlined"
          class="admin-tile h-100 d-flex flex-column"
          :class="{ 'admin-tile--featured': tile.featured }"
        >
          <v-card-item class="pb-2">
            <template #prepend>
              <v-avatar
                :color="tile.avatarColor"
                variant="tonal"
                size="44"
                rounded="lg"
              >
                <v-icon :icon="tile.icon" size="24" />
              </v-avatar>
            </template>
            <v-card-title class="text-h6 py-0">{{ tile.title }}</v-card-title>
            <v-card-subtitle class="text-wrap mt-2 opacity-90">
              {{ tile.description }}
            </v-card-subtitle>
          </v-card-item>

          <v-spacer />

          <v-card-actions class="px-4 pb-4 pt-0 flex-column align-stretch" style="gap: 8px">
            <v-btn
              color="primary"
              :variant="tile.featured ? 'flat' : 'tonal'"
              :prepend-icon="tile.actionIcon"
              :to="{ path: tile.to }"
              block
              :aria-label="tile.ariaLabel"
            >
              {{ tile.actionLabel }}
            </v-btn>
            <v-btn
              v-if="tile.secondaryTo"
              variant="text"
              size="small"
              :to="{ path: tile.secondaryTo }"
              :aria-label="tile.secondaryAriaLabel"
            >
              {{ tile.secondaryLabel }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </v-container>
</template>

<script setup>
const adminTiles = [
  {
    title: 'Users & Roles',
    description: 'Manage user activation and staff roles.',
    icon: 'mdi-account-cog-outline',
    avatarColor: 'primary',
    to: '/admin/users',
    actionLabel: 'Open Users',
    actionIcon: 'mdi-arrow-right',
    ariaLabel: 'Open Users management',
    featured: true,
  },
  {
    title: 'Audit log',
    description: 'Recent edits to objects, runs, data files, identifiers, and tags.',
    icon: 'mdi-history',
    avatarColor: 'brown',
    to: '/admin/audit-log',
    actionLabel: 'Open audit log',
    actionIcon: 'mdi-arrow-right',
    ariaLabel: 'Open audit log',
    featured: true,
  },
  {
    title: 'Download Jobs',
    description: 'Monitor download jobs and cancel stuck tasks.',
    icon: 'mdi-download-network-outline',
    avatarColor: 'teal',
    to: '/admin/jobs',
    actionLabel: 'Open Download Jobs',
    actionIcon: 'mdi-arrow-right',
    ariaLabel: 'Open Download Jobs',
    featured: true,
  },
  {
    title: 'Health',
    description: 'Quick system diagnostics (API, Celery, storage).',
    icon: 'mdi-heart-pulse',
    avatarColor: 'green',
    to: '/admin/health',
    actionLabel: 'Open Health',
    actionIcon: 'mdi-arrow-right',
    ariaLabel: 'Open Health',
    featured: true,
  },
  {
    title: 'Data Maintenance',
    description: 'Cleanup, reconcile, orphans, and banner settings.',
    icon: 'mdi-database-cog-outline',
    avatarColor: 'orange',
    to: '/admin/maintenance',
    actionLabel: 'Open Maintenance',
    actionIcon: 'mdi-arrow-right',
    ariaLabel: 'Open Maintenance',
    featured: true,
  },
  {
    title: 'Objects',
    description: 'Create objects and upload preview images for solar-system targets.',
    icon: 'mdi-creation',
    avatarColor: 'deep-purple',
    to: '/admin/objects',
    actionLabel: 'Objects admin page',
    actionIcon: 'mdi-arrow-right',
    ariaLabel: 'Open Objects admin',
    featured: true,
  },
  {
    title: 'Exposure Type Discrepancies',
    description: 'Review and resolve exposure type classification conflicts.',
    icon: 'mdi-filter-variant',
    avatarColor: 'cyan',
    to: '/admin/exposure-type-discrepancies',
    actionLabel: 'Open Discrepancies',
    actionIcon: 'mdi-arrow-right',
    ariaLabel: 'Open Exposure Type Discrepancies',
    featured: true,
  },
  {
    title: 'Spectrograph Management',
    description: 'Manage spectrograph metadata for WAVE and spectroscopy files.',
    icon: 'mdi-chart-timeline-variant',
    avatarColor: 'indigo',
    to: '/admin/spectrograph-files',
    actionLabel: 'Open Spectrograph',
    actionIcon: 'mdi-arrow-right',
    ariaLabel: 'Open Spectrograph Management',
    featured: true,
  },
  {
    title: 'Plate Solving',
    description: 'Trigger and monitor plate solving for light frames.',
    icon: 'mdi-crosshairs-gps',
    avatarColor: 'blue-grey',
    to: '/admin/plate-solving',
    actionLabel: 'Open Plate Solving',
    actionIcon: 'mdi-arrow-right',
    ariaLabel: 'Open Plate Solving',
    featured: true,
  },
  {
    title: 'Auxiliary Objects',
    description: 'Bulk SIMBAD field lookups and background queue for observation runs.',
    icon: 'mdi-star-circle-outline',
    avatarColor: 'deep-orange',
    to: '/admin/aux-objects',
    actionLabel: 'Open Auxiliary Objects',
    actionIcon: 'mdi-arrow-right',
    ariaLabel: 'Open Auxiliary Objects admin',
    featured: true,
  },
]
</script>

<style scoped>
.admin-page {
  max-width: 1280px;
}

.admin-tile {
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.admin-tile:hover {
  border-color: rgba(var(--v-theme-primary), 0.45);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.admin-tile--featured {
  border-width: 2px;
  border-color: rgba(var(--v-theme-primary), 0.35);
  background: linear-gradient(
    145deg,
    rgba(var(--v-theme-primary), 0.06) 0%,
    rgba(var(--v-theme-surface), 1) 55%
  );
}

.admin-tile--featured:hover {
  border-color: rgba(var(--v-theme-primary), 0.6);
}

.admin-tile :deep(.v-card-item) {
  align-items: flex-start;
}

.admin-tile :deep(.v-card-subtitle) {
  line-height: 1.45;
  white-space: normal;
}
</style>
