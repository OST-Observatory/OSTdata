/**
 * Black or white text for a background color (#rgb or #rrggbb), whichever has the higher WCAG
 * contrast with it; '' for values that are no hex color (e.g. theme color names).
 */
export function readableTextColor(background) {
  const match = /^#?([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(String(background || '').trim())
  if (!match) return ''
  let hex = match[1]
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('')
  const [r, g, b] = [0, 2, 4]
    .map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map(c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
  // Contrast with white: 1.05 / (L + 0.05), with black: (L + 0.05) / 0.05
  return 1.05 / (luminance + 0.05) >= (luminance + 0.05) / 0.05 ? '#ffffff' : '#000000'
}
