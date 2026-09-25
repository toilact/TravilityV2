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
  from_place_id: number; to_place_id: number; distance_km: number; duration_min: number; mode: string; cost: number
}
export type Day = { date: string | null; stops: Stop[]; legs: Leg[]; rain_chance: number | null }
export type Conflict = { kind: string; message: string; day_index: number | null; place_id: number | null }
export type Itinerary = {
  stay_place_id: number | null; days: Day[]; total_cost: number; conflicts: Conflict[]; summary: string
}
export type AgentEvent =
  | { type: 'thinking'; text: string }
  | { type: 'trip'; trip_id: number; trip: { budget: number }; center: [number, number] }
  | { type: 'tool_call'; name: string; query: string; places: Place[] }
  | { type: 'itinerary'; itinerary: Itinerary; places: Record<string, Place>; trip_id: number; version: number }
  | { type: 'error'; message: string }

export async function authRequest(path: '/auth/login' | '/auth/register', email: string, password: string) {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const body = await r.json()
  if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Email hoặc mật khẩu không hợp lệ (mật khẩu tối thiểu 8 ký tự)')
  return body.token as string
}

export async function streamTrip(token: string, message: string, onEvent: (e: AgentEvent) => void) {
  const r = await fetch(API + '/trips', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify({ message }),
  })
  if (r.status === 401) throw new Error('unauthorized')
  if (!r.ok || !r.body) {
    onEvent({ type: 'error', message: `Lỗi máy chủ (${r.status})` })
    return
  }
  const reader = r.body.pipeThrough(new TextDecoderStream()).getReader()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += value
    const { events, rest } = parseSSE(buf)
    buf = rest
    events.forEach((e) => onEvent(e as AgentEvent))
  }
}
