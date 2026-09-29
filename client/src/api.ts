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
  intents?: Record<string, boolean>; retention?: number | null  // thiếu ở Itinerary lưu trước lát A
}
export type AgentEvent =
  | { type: 'thinking'; text: string }
  | { type: 'trip'; trip_id: number; trip: { budget: number }; center: [number, number] }
  | { type: 'tool_call'; name: string; query: string; places: Place[] }
  | { type: 'clarify'; trip_id: number; questions: Question[] }
  | {
    type: 'itinerary'; itinerary: Itinerary; places: Record<string, Place>; trip_id: number; version: number
    changed?: [number, number][]  // [ngày, Stop] vừa đổi khi sửa lịch; lập mới thì không có
  }
  | { type: 'answer'; text: string }  // trả lời câu hỏi trên Trip đang mở, không đổi lịch trình
  | { type: 'error'; message: string }

// Khớp MEALS ở server/app/rules.py: Stop an-uong bắt đầu trong khung giờ = bữa đó
const MEALS: [string, string, string][] = [['Bữa sáng', '06:00', '10:00'], ['Bữa trưa', '11:00', '14:00'], ['Bữa tối', '17:00', '21:00']]

export function mealOf(kind: string | undefined, startTime: string): string | null {
  if (kind !== 'an-uong') return null
  return MEALS.find(([, lo, hi]) => lo <= startTime && startTime < hi)?.[0] ?? null
}

export const vnd = (n: number) => n.toLocaleString('vi-VN') + 'đ'

// Khớp INTENT_LABELS ở server/app/domain.py
export const INTENT_LABELS: Record<string, string> = {
  'am-thuc': 'Ẩm thực', 'thien-nhien': 'Thiên nhiên', 'van-hoa': 'Văn hoá', 'thu-gian': 'Thư giãn', 'vui-choi': 'Vui chơi',
}

export function intentChips(it: Itinerary): { label: string; ok: boolean }[] {
  return Object.entries(it.intents ?? {}).map(([k, ok]) => ({ label: INTENT_LABELS[k] ?? k, ok }))
}

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

/** tripId có → tin nhắn tiếp theo của Trip đang mở; null → chuyến mới. */
export const streamTrip = (token: string, message: string, tripId: number | null, onEvent: (e: AgentEvent) => void) =>
  streamSSE(token, '/trips', { message, trip_id: tripId }, onEvent)

export const streamPlan = (token: string, tripId: number, answers: Answers, onEvent: (e: AgentEvent) => void) =>
  streamSSE(token, `/trips/${tripId}/plan`, answers, onEvent)

export type DisruptionKind = 'closed' | 'disliked'
export type ItineraryEvent = Extract<AgentEvent, { type: 'itinerary' }>
export type ProposalOption = {
  itinerary: Itinerary; places: Record<string, Place>; changed: [number, number][]
  metrics: {
    cost_delta: number; travel_min_delta: number; day_end_after: string; retention_after: number | null
    intents_kept: string[]; intents_lost: string[]
  }
  reason_codes: string[]; explanation: string
}
export type Proposal = { proposal_id: number; options?: ProposalOption[]; no_feasible?: string[] }

async function postJSON<T>(token: string, path: string, body: unknown): Promise<T> {
  const r = await fetch(API + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  })
  if (r.status === 401) throw new Error('unauthorized')
  const data = await r.json().catch(() => ({}))
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Lỗi máy chủ (${r.status})`)
  return data as T
}

export const reportDisruption = (token: string, tripId: number, version: number, kind: DisruptionKind,
  dayIndex: number, stopIndex: number) =>
  postJSON<Proposal>(token, `/trips/${tripId}/disruptions`,
    { version, kind, day_index: dayIndex, stop_index: stopIndex })

export const applyProposal = (token: string, tripId: number, proposalId: number, option: number) =>
  postJSON<ItineraryEvent>(token, `/trips/${tripId}/proposals/${proposalId}/apply`, { option })

const NO_FEASIBLE_TEXT: Record<string, string> = {
  NO_CANDIDATE: 'Chưa có Place nào cùng loại để thay.',
  NO_OPEN_CANDIDATE: 'Các Place tương tự đều đóng cửa vào giờ này.',
  NOT_REACHABLE_IN_TIME: 'Các Place tương tự quá xa, không kịp giờ Stop kế tiếp.',
  OVER_BUDGET: 'Thay thế sẽ vượt Budget.',
  NEW_CONFLICT: 'Thay thế sẽ làm lịch trình phát sinh xung đột mới.',
}
export const noFeasibleText = (codes: string[]) => codes.map((c) => NO_FEASIBLE_TEXT[c] ?? c)

export function optionPlace(o: ProposalOption): Place | undefined {
  const [d, s] = o.changed[0]
  return o.places[o.itinerary.days[d].stops[s].place_id]
}

export const signed = (n: number, unit: (x: number) => string) =>
  n === 0 ? 'như cũ' : (n > 0 ? '+' : '−') + unit(Math.abs(n))
