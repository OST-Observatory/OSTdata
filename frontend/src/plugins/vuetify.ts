// Styles
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

// Vuetify
import { createVuetify, type ThemeDefinition } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

const ostdataTheme: ThemeDefinition = {
  dark: false,
  colors: {
    // Primary colors - Based on a fresh, airy blue
    primary: '#1584cb',          // Main blue
    'primary-dark': '#0d5c8f',   // Darker shade for hover states
    'primary-light': '#e8f4fc',  // Very light blue for backgrounds
    'on-primary': '#ffffff',     // White text on primary
    
    // Secondary colors - Complementary warm tone
    secondary: '#2c5282',        // Deep blue for secondary elements
    'secondary-dark': '#1a365d', // Darker shade for hover states
    'secondary-light': '#ebf8ff', // Very light blue for backgrounds
    'on-secondary': '#ffffff',   // White text on secondary
    
    // Status colors - Adjusted to match the new scheme
    success: '#38a169',          // Fresh green
    'on-success': '#ffffff',
    warning: '#dd6b20',          // Warm orange
    'on-warning': '#ffffff',
    error: '#e53e3e',           // Bright red
    'on-error': '#ffffff',
    info: '#3182ce',            // Info blue
    'on-info': '#ffffff',
    
    // Surface colors
    surface: '#ffffff',          // Pure white for cards
    'on-surface': '#2d3748',     // Dark gray for text
    'surface-variant': '#f7fafc', // Light gray for hover states
    'on-surface-variant': '#4a5568', // Medium gray for text
    
    // Background colors
    background: '#eaf2f8',       // Slightly darker blue for main background
    'on-background': '#2d3748',  // Dark gray for text
  },
  variables: {
    // Shadows - Lighter for the airy feel
    'theme-shadow-app-bar': '0 2px 8px rgba(21, 132, 203, 0.15)',
    'theme-shadow-card': '0 2px 4px rgba(21, 132, 203, 0.12)',
    'theme-shadow-card-hover': '0 4px 8px rgba(21, 132, 203, 0.18)',
    'theme-shadow-card-light': '0 2px 4px rgba(21, 132, 203, 0.08)',
    
    // Borders - Slightly blue tinted
    'theme-border-app-bar': '1px solid rgba(21, 132, 203, 0.1)',
    'theme-border-card': '1px solid rgba(21, 132, 203, 0.08)',
    
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

const darkTheme: ThemeDefinition = {
  dark: true,
  colors: {
    primary: '#90caf9',
    'primary-dark': '#42a5f5',
    'primary-light': '#1e293b',
    'on-primary': '#0b0f14',
    // Make secondary readable on dark backgrounds (used by text-secondary)
    secondary: '#a0aec0',
    'secondary-dark': '#64748b',
    'secondary-light': '#cbd5e1',
    'on-secondary': '#0b0f14',
    success: '#66bb6a',
    'on-success': '#0b0f14',
    warning: '#ffa726',
    'on-warning': '#0b0f14',
    error: '#ef5350',
    'on-error': '#0b0f14',
    info: '#29b6f6',
    'on-info': '#0b0f14',
    surface: '#0f172a',
    'on-surface': '#e2e8f0',
    'surface-variant': '#111827',
    'on-surface-variant': '#cbd5e1',
    background: '#0b0f14',
    'on-background': '#e2e8f0',
  },
  variables: {
    'theme-shadow-app-bar': '0 2px 8px rgba(0,0,0,0.6)',
    'theme-shadow-card': '0 2px 4px rgba(0,0,0,0.5)',
    'theme-shadow-card-hover': '0 4px 8px rgba(0,0,0,0.6)',
    'theme-border-app-bar': '1px solid rgba(255,255,255,0.06)',
    'theme-border-card': '1px solid rgba(255,255,255,0.06)',
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
    'theme-opacity-hover': 0.08,
    'theme-container-max-width': '1400px',
    'theme-scrollbar-width': '8px',
    'theme-scrollbar-height': '8px',
  }
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
      border: '1px solid rgba(21, 132, 203, 0.08)',
      rounded: 'md',
      class: 'mb-4',
    },
    VCardTitle: {
      class: 'py-2',
    },
    VCardText: {
      class: 'pt-2 pb-4',
    },
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
    VChip: {
      size: 'small',
      variant: 'tonal',
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