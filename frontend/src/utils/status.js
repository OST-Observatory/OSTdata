export const getStatusColor = (status) => {
  if (!status) return 'secondary'
  const normalized = String(status).toLowerCase()
  if (['co', 'completed', 'complete', 'fully_reduced'].includes(normalized)) return 'success'
  if (['pr', 'in_progress', 'processing', 'partly_reduced', 'pa', 'partial'].includes(normalized)) return 'warning'
  if (['fa', 'error', 'failed', 'reduction_error'].includes(normalized)) return 'error'
  if (['ne', 'new', 'not_reduced'].includes(normalized)) return 'secondary'
  return 'info'
}


