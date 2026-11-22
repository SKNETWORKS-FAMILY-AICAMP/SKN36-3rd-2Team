import { request } from './httpApi'

export interface PendingStoryEvent {
  eventKey: string
  chapter: string
  title: string
  text: string
}

export interface StoryEventAck {
  eventKey: string
  acknowledged: boolean
  created: boolean
  revision: number
}

function isStoryEvent(value: unknown): value is PendingStoryEvent {
  if (typeof value !== 'object' || value === null) return false

  const event = value as Partial<PendingStoryEvent>

  return (
    typeof event.eventKey === 'string' &&
    /^EVT-CH0[0-4]-[0-9]{3}$/.test(event.eventKey) &&
    typeof event.chapter === 'string' &&
    /^CH0[0-4]$/.test(event.chapter) &&
    event.eventKey.startsWith(`EVT-${event.chapter}-`) &&
    typeof event.title === 'string' &&
    event.title.length > 0 &&
    event.title.length <= 200 &&
    typeof event.text === 'string' &&
    event.text.length > 0 &&
    event.text.length <= 10000
  )
}

export async function getPendingStoryEvents(
  sessionId: string,
): Promise<PendingStoryEvent[]> {
  const response = await request<{ items: unknown }>(
    `/games/${encodeURIComponent(sessionId)}/story-events/pending`,
  )

  if (
    !Array.isArray(response.items) ||
    response.items.length > 30 ||
    !response.items.every(isStoryEvent)
  ) {
    throw new Error('스토리 이벤트 응답 형식이 올바르지 않습니다.')
  }

  return response.items
}

export async function acknowledgeStoryEvent(
  sessionId: string,
  eventKey: string,
): Promise<StoryEventAck> {
  if (!/^EVT-CH0[0-4]-[0-9]{3}$/.test(eventKey)) {
    throw new Error('올바르지 않은 이벤트 ID입니다.')
  }

  const response = await request<StoryEventAck>(
    `/games/${encodeURIComponent(sessionId)}/story-events/${encodeURIComponent(eventKey)}/ack`,
    { method: 'POST' },
  )

  if (
    response.acknowledged !== true ||
    response.eventKey !== eventKey ||
    !Number.isSafeInteger(response.revision)
  ) {
    throw new Error('이벤트 확인 응답이 올바르지 않습니다.')
  }

  return response
}
