import { parseSSE } from './sse'

const API = import.meta.env.VITE_API_URL as string

export type Place = {
  id: number; name: string; kind: string; lat: number; lon: number
  photo_url: string | null; outdoor: boolean; price: number
}
export type Stop = {
  place_id: number; start_time: string; duration_min: number; reason: string; pinned: boolean; est_cost: number
}
export type Leg = {
  from_place_id: number | null; to_place_id: number | null  // null = Hub (sân bay/bến xe)
  distance_km: number; duration_min: number; mode: string; cost: number
}
export type Question = { field: 'travel_mode' | 'arrival'; text: string; options: { value: string; label: string }[] }
export type Answers = { travel_mode?: string; arrival_mode?: string; arrival_time?: string; departure_time?: string }
export type Day = { date: string | null; stops: Stop[]; legs: Leg[]; rain_chance: number | null }
export type Conflict = { kind: string; message: string; day_index: number | null; place_id: number | null }
export type Itinerary = {
  stay_place_id: number | null; days: Day[]; total_cost: number; conflicts: Conflict[]; summary: string
}
export type AgentEvent =
  | { type: 'thinking'; text: string }
  | { type: 'trip'; trip_id: number; trip: { budget: number }; center: [number, number] }
  | { type: 'tool_call'; name: string; query: string; places: Place[] }
  | { type: 'clarify'; trip_id: number; questions: Question[] }
  | { type: 'itinerary'; itinerary: Itinerary; places: Record<string, Place>; trip_id: number; version: number }
  | { type: 'error'; message: string }

export type Clarify = { tripId: number; questions: Question[] }

/** Thẻ hỏi lại chỉ mất khi đã có lịch trình — /plan lỗi (422, AI lỗi) thì giữ để người dùng sửa hoặc thử lại. */
export function clarifyAfter(current: Clarify | null, e: AgentEvent): Clarify | null {
  if (e.type === 'clarify') return { tripId: e.trip_id, questions: e.questions }
  if (e.type === 'itinerary') return null
  return current
}

/** Bỏ trường rỗng (ô giờ chưa nhập, chip chưa chọn) để server không trả 422. */
export function toAnswers(form: Record<string, string>): Answers {
  return Object.fromEntries(Object.entries(form).filter(([, v]) => v !== '')) as Answers
}

export async function authRequest(path: '/auth/login' | '/auth/register', email: string, password: string) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Email hoặc mật khẩu không hợp lệ (mật khẩu tối thiểu 8 ký tự)')
  return body.token as string
}

async function streamSSE(token: string, path: string, body: unknown, onEvent: (e: AgentEvent) => void) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  })
  if (r.status === 401) throw new Error('unauthorized')
  if (!r.ok || !r.body) {
    const detail = (await r.json().catch(() => ({}))).detail
    onEvent({ type: 'error', message: typeof detail === 'string' ? detail : `Lỗi máy chủ (${r.status})` })
    return
  }
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  let finished = false
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += value
    const { events, rest } = parseSSE(buf)
    buf = rest
    events.forEach((e) => {
      const ev = e as AgentEvent
      if (ev.type === 'itinerary' || ev.type === 'error' || ev.type === 'clarify') finished = true
      onEvent(ev)
    })
  }
  if (!finished) onEvent({ type: 'error', message: 'Kết nối bị ngắt giữa chừng, bạn thử lại nhé.' })
}

export const streamTrip = (token: string, message: string, onEvent: (e: AgentEvent) => void) =>
  streamSSE(token, '/trips', { message }, onEvent)

export const streamPlan = (token: string, tripId: number, answers: Answers, onEvent: (e: AgentEvent) => void) =>
  streamSSE(token, `/trips/${tripId}/plan`, answers, onEvent)
