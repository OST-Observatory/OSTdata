// Styles
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
import '@/styles/base.css'
import '@/styles/switch-contrast.css'
import '@/styles/admin-cards.css'
import '@/styles/dark-theme.css'
import '@/styles/surface-borders.css'
import '@/styles/forms.css'

// Vuetify
import { createVuetify, type ThemeDefinition } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

/*
 * Categorical colors for chips that tell categories apart (exposure types, spectrographs, cameras):
 * one tone per theme, chosen so the text of tonal chips reaches 4.5:1 (WCAG AA) on cards.
 * Use them as color="cat-<name>" instead of Material palette colors (e.g. "teal"), which are too
 * light on white or too dark on the dark surfaces.
 */
const categoricalLight = {
  'cat-blue': '#0963aa',
  'cat-green': '#2e6e31',
  'cat-orange': '#905000',
  'cat-purple': '#8e24aa',
  'cat-slate': '#4d646f',
  'cat-gray': '#626262',
  'cat-teal': '#006d63',
  'cat-indigo': '#3f51b5',
  'cat-pink': '#ba124b',
  'cat-brown': '#795548',
  'cat-cyan': '#006a77',
  'cat-olive': '#646317',
}

const categoricalDark = {
  'cat-blue': '#60b4f6',
  'cat-green': '#68c06c',
  'cat-orange': '#fe8d00',
  'cat-purple': '#d795e9',
  'cat-slate': '#9db2bb',
  'cat-gray': '#adadad',
  'cat-teal': '#00c1af',
  'cat-indigo': '#a2abdf',
  'cat-pink': '#f48baf',
  'cat-brown': '#c4a69b',
  'cat-cyan': '#00bed5',
  'cat-olive': '#b3b229',
}

const ostdataTheme: ThemeDefinition = {
  dark: false,
  colors: {
    // Primary colors - Based on a fresh, airy blue. Text colors (primary and status) reach at least
    // 4.5:1 (WCAG AA) on white surfaces and the page background, also for text/outlined buttons.
    primary: '#1170ad',          // Main blue
    'primary-dark': '#0d5c8f',   // Darker shade for hover states
    'primary-light': '#e8f4fc',  // Very light blue for backgrounds
    'on-primary': '#ffffff',     // White text on primary
    
    // Secondary colors - Complementary warm tone
    secondary: '#2c5282',        // Deep blue for secondary elements
    'secondary-dark': '#1a365d', // Darker shade for hover states
    'secondary-light': '#ebf8ff', // Very light blue for backgrounds
    'on-secondary': '#ffffff',   // White text on secondary
    
    // Status colors - Adjusted to match the new scheme
    success: '#2a794f',          // Green
    'on-success': '#ffffff',
    warning: '#aa5218',          // Warm orange
    'on-warning': '#ffffff',
    error: '#c53030',            // Red
    'on-error': '#ffffff',
    info: '#2b6cb0',             // Info blue
    'on-info': '#ffffff',

    // App bar and footer (kept apart from secondary, which is also used for content)
    chrome: '#2c5282',
    'on-chrome': '#ffffff',
    
    // Surface colors
    surface: '#ffffff',          // Pure white for cards
    'on-surface': '#2d3748',     // Dark gray for text
    'surface-variant': '#f7fafc', // Light gray for hover states
    'on-surface-variant': '#4a5568', // Medium gray for text
    
    // Background colors
    background: '#eaf2f8',       // Slightly darker blue for main background
    'on-background': '#2d3748',  // Dark gray for text

    ...categoricalLight,
  },
  variables: {
    // Shadows - Lighter for the airy feel
    'theme-shadow-app-bar': '0 2px 8px rgba(21, 132, 203, 0.15)',
    'theme-shadow-card': '0 2px 4px rgba(21, 132, 203, 0.12)',
    'theme-shadow-card-hover': '0 4px 8px rgba(21, 132, 203, 0.18)',
    'theme-shadow-card-light': '0 2px 4px rgba(21, 132, 203, 0.08)',
    
    // Borders - subtle dark hairline on light surfaces
    'theme-border-app-bar': '1px solid rgba(21, 132, 203, 0.1)',
    'theme-border-card': '1px solid rgba(45, 55, 72, 0.14)',
    
    // Border Radius
    'theme-radius-sm': '4px',
    'theme-radius-md': '8px',
    'theme-radius-lg': '12px',
    
    // Spacing
    'theme-spacing-xs': '8px',
    'theme-spacing-sm': '12px',
    'theme-spacing-md': '16px',
    'theme-spacing-lg': '20px',
    'theme-spacing-xl': '24px',
    
    // Transitions
    'theme-transition-fast': '0.2s ease-in-out',
    'theme-transition-normal': '0.3s ease-in-out',
    
    // Opacity
    'theme-opacity-hover': 0.08,
    
    // Container
    'theme-container-max-width': '1400px',

    // Scrollbar
    'theme-scrollbar-width': '8px',
    'theme-scrollbar-height': '8px',
  },
}

/** Dark companion to ostdata light theme — slate blues, not near-black. */
const darkTheme: ThemeDefinition = {
  dark: true,
  colors: {
    // Primary: same family as the light theme, tuned for dark surfaces. Text colors (primary,
    // secondary and status) reach at least 4.5:1 (WCAG AA) on all surface levels.
    primary: '#66bdea',
    'primary-dark': '#3da3d9',
    'primary-light': '#9ad4f5',
    'on-primary': '#0c1824',

    // Secondary: muted light blue for content (buttons, chips); the deep blue of the app bar and
    // footer is "chrome", it would be invisible on dark surfaces
    secondary: '#95b3d4',
    'secondary-dark': '#7a9cc2',
    'secondary-light': '#c2d4e8',
    'on-secondary': '#0c1824',

    // App bar / footer — deep blue (parallel to light chrome #2c5282)
    chrome: '#2f4f73',
    'on-chrome': '#eef4fc',

    success: '#5cc48a',
    'on-success': '#0c1824',
    warning: '#e8ad52',
    'on-warning': '#1a1408',
    error: '#f3969b',
    'on-error': '#1f0c0d',
    info: '#66bdea',
    'on-info': '#0c1824',

    // Layered surfaces (clear steps above background)
    background: '#1a2433',
    'on-background': '#d4deec',
    surface: '#243247',
    'on-surface': '#eef3fa',
    'surface-bright': '#2f3f56',
    'on-surface-bright': '#f4f7fc',
    'surface-light': '#364862',
    'on-surface-light': '#e8eef6',
    'surface-variant': '#33445c',
    'on-surface-variant': '#b8c6d9',

    ...categoricalDark,
  },
  variables: {
    'theme-shadow-app-bar': '0 2px 12px rgba(8, 20, 36, 0.55)',
    'theme-shadow-card': '0 2px 10px rgba(8, 20, 36, 0.4)',
    'theme-shadow-card-hover': '0 6px 20px rgba(8, 20, 36, 0.5)',
    'theme-shadow-card-light': '0 1px 6px rgba(8, 20, 36, 0.3)',
    'theme-border-app-bar': '1px solid rgba(94, 184, 232, 0.22)',
    'theme-border-card': '1px solid rgba(238, 243, 250, 0.22)',
    'theme-radius-sm': '4px',
    'theme-radius-md': '8px',
    'theme-radius-lg': '12px',
    'theme-spacing-xs': '8px',
    'theme-spacing-sm': '12px',
    'theme-spacing-md': '16px',
    'theme-spacing-lg': '20px',
    'theme-spacing-xl': '24px',
    'theme-transition-fast': '0.2s ease-in-out',
    'theme-transition-normal': '0.3s ease-in-out',
    'theme-opacity-hover': 0.1,
    'theme-container-max-width': '1400px',
    'theme-scrollbar-width': '8px',
    'theme-scrollbar-height': '8px',
  },
}

export default createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'ostdata',
    themes: {
      ostdata: ostdataTheme,
      dark: darkTheme,
    },
  },
  defaults: {
    global: {
      ripple: false,
    },
    VAppBar: {
      elevation: 2,
      border: '1px solid rgba(21, 132, 203, 0.1)',
    },
    VIcon: {
      size: 22,
    },
    VCard: {
      elevation: 2,
      border: true,
      rounded: 'md',
      class: 'mb-4',
    },
    VCardTitle: {
      class: 'py-2',
    },
    VCardText: {
      class: 'pt-2 pb-4',
    },
    /*
     * Button emphasis (set variant/color explicitly, the default is a plain text button):
     * - flat + primary: the one main action of a dialog, form or page (Save, Search, Apply filters)
     * - flat + error: confirming a destructive action
     * - tonal + primary: actions inside the many task cards of admin pages (e.g. Maintenance)
     * - outlined + primary: page-level refresh and further toolbar actions (Download selected)
     * - text: Cancel (no color, left of the main action), Close of info dialogs (primary),
     *   Reset filters (secondary), refresh inside a card section (no color)
     * - table row actions: icon, size small, density comfortable, no color (delete/cancel: error),
     *   with tooltip and aria-label; data file rows use DataFileQuickActions
     * Labels in sentence case ("Download selected", not "Download Selected").
     */
    VBtn: {
      ripple: false,
      variant: 'text',
      class: 'text-none',
      density: 'comfortable',
    },
    VListItem: {
      rounded: 'sm',
    },
    VTable: {
      rounded: 'md',
      density: 'comfortable',
      hover: true,
      class: 'custom-table',
    },
    VDataTable: {
      density: 'comfortable',
      hover: true,
      class: 'custom-table',
    },
    VAlert: {
      rounded: 'md',
      border: 'none',
    },
    VField: {
      rounded: 'md',
    },
    VTextField: {
      variant: 'outlined',
      density: 'comfortable',
    },
    VTextarea: {
      variant: 'outlined',
      density: 'comfortable',
    },
    VSelect: {
      variant: 'outlined',
      density: 'comfortable',
    },
    VAutocomplete: {
      variant: 'outlined',
      density: 'comfortable',
    },
    VCombobox: {
      variant: 'outlined',
      density: 'comfortable',
    },
    VFileInput: {
      variant: 'outlined',
      density: 'comfortable',
    },
    VChip: {
      size: 'small',
      variant: 'tonal',
    },
    VSwitch: {
      color: 'primary',
      inset: true,
      class: 'hi-contrast-switch',
    },
  },
  display: {
    mobileBreakpoint: 'sm',
    thresholds: {
      xs: 0,
      sm: 340,
      md: 540,
      lg: 800,
      xl: 1280,
    },
  },
}) 