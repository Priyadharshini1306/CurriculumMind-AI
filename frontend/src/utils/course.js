// Where a course's "next step" lives in the app.
const ACTION_ROUTES = { curriculum: 'curriculum', graph: 'map', plan: 'plan', learn: 'learn' }

/** Route to open for a course, given its stage: the review it is waiting for, else its overview/learning page. */
export function courseRoute(id, stage) {
  const sub = stage?.action ? ACTION_ROUTES[stage.action] : ''
  return `/app/course/${id}${sub ? `/${sub}` : ''}`
}

export const fileSize = (bytes) => (bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`)
