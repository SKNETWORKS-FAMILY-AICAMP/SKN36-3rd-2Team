export function evidencePhoto(sessionId: string | undefined, id: string) {
  if (!sessionId) return undefined
  const api = import.meta.env.VITE_API_BASE_URL ?? '/api'
  const src = api + '/games/' + encodeURIComponent(sessionId) + '/evidence/' + encodeURIComponent(id) + '/photo'
  return { src, thumb: src + '?thumbnail=true', caption: '확보한 증거 사진' }
}
