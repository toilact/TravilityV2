import { describe, expect, it } from 'vitest'
import {
  clarifyAfter, confirmAfter, intentChips, isFinal, mealOf, noFeasibleText, optionPlace, signed, toAnswers, tripLabel,
  viewingOld, vnd,
  type AgentEvent, type Itinerary, type ProposalOption,
} from './api'

describe('toAnswers', () => {
  it('bỏ ô giờ chưa nhập và chip chưa chọn để server không trả 422', () => {
    expect(toAnswers({ travel_mode: 'grab', arrival_mode: '', arrival_time: '', departure_time: '16:00' }))
      .toEqual({ travel_mode: 'grab', departure_time: '16:00' })
  })
})

describe('clarifyAfter', () => {
  const pending = { tripId: 1, questions: [] }
  it('giữ thẻ hỏi lại khi /plan lỗi để người dùng sửa hoặc thử lại', () => {
    expect(clarifyAfter(pending, { type: 'error', message: 'Giờ về phải sau giờ đến' })).toBe(pending)
  })
  it('bỏ thẻ khi đã có lịch trình', () => {
    const itin = { type: 'itinerary', itinerary: {}, places: {}, trip_id: 1, version: 1 } as unknown as AgentEvent
    expect(clarifyAfter(pending, itin)).toBeNull()
  })
  it('thay bằng câu hỏi mới khi có event clarify', () => {
    expect(clarifyAfter(null, { type: 'clarify', trip_id: 2, questions: [] })).toEqual({ tripId: 2, questions: [] })
  })
})

describe('mealOf', () => {
  it('quán ăn trong khung giờ bữa → tên bữa (khớp MEALS ở server/app/rules.py)', () => {
    expect(mealOf('an-uong', '07:30')).toBe('Bữa sáng')
    expect(mealOf('an-uong', '12:00')).toBe('Bữa trưa')
    expect(mealOf('an-uong', '17:00')).toBe('Bữa tối')
  })
  it('ngoài khung giờ hoặc không phải quán ăn → không có nhãn', () => {
    expect(mealOf('an-uong', '15:00')).toBeNull()
    expect(mealOf('an-uong', '21:00')).toBeNull()
    expect(mealOf('tham-quan', '12:00')).toBeNull()
  })
})

describe('intentChips', () => {
  const base = { stay_place_id: null, days: [], total_cost: 0, conflicts: [], summary: '' }
  it('mỗi Intent của Trip thành một chip có nhãn tiếng Việt', () => {
    const it = { ...base, intents: { 'thu-gian': true, 'van-hoa': false }, retention: 0.67 } as Itinerary
    expect(intentChips(it)).toEqual([{ label: 'Thư giãn', ok: true }, { label: 'Văn hoá', ok: false }])
  })
  it('Itinerary lưu trước khi có Intent → không có chip', () => {
    expect(intentChips(base as Itinerary)).toEqual([])
  })
})

describe('noFeasibleText', () => {
  it('đổi mã lý do thành câu tiếng Việt, mã lạ giữ nguyên', () => {
    expect(noFeasibleText(['NO_CANDIDATE', 'XYZ'])).toEqual(['Chưa có Place nào cùng loại để thay.', 'XYZ'])
  })
})

describe('optionPlace', () => {
  it('lấy Place mới ở vị trí Stop đã đổi', () => {
    const o = {
      changed: [[0, 1]],
      itinerary: { days: [{ stops: [{ place_id: 1 }, { place_id: 7 }] }] },
      places: { '1': { id: 1, name: 'Cũ' }, '7': { id: 7, name: 'Mới' } },
    } as unknown as ProposalOption
    expect(optionPlace(o)?.name).toBe('Mới')
  })
})

describe('signed', () => {
  it('thêm dấu và đơn vị; 0 là "như cũ"', () => {
    expect(signed(30000, vnd)).toBe('+' + vnd(30000))
    expect(signed(-12, (x) => `${x} phút`)).toBe('−12 phút')
    expect(signed(0, vnd)).toBe('như cũ')
  })
})

describe('confirmAfter', () => {
  const ask = { type: 'confirm_replan', trip_id: 3, text: 'Đổi 3 ngày?', changes: { days: 3 }, message: '3 ngày' } as const
  it('hiện thẻ khi server xin xác nhận, giữ khi đang nghĩ, ẩn khi có lịch hoặc câu trả lời mới', () => {
    const c = confirmAfter(null, ask)
    expect(c).toEqual({ tripId: 3, text: 'Đổi 3 ngày?', changes: { days: 3 }, message: '3 ngày' })
    expect(confirmAfter(c, { type: 'thinking', text: '…' })).toBe(c)
    expect(confirmAfter(c, { type: 'answer', text: 'ok' })).toBeNull()
    expect(confirmAfter(c, { type: 'trip', trip_id: 3, trip: { budget: 1 }, center: [0, 0] })).toBeNull()
  })
})

describe('isFinal', () => {
  it('mọi event kết thúc một lượt đều được tính, để không báo "ngắt kết nối" nhầm', () => {
    expect(isFinal({ type: 'answer', text: 'ok' })).toBe(true)
    expect(isFinal({ type: 'confirm_replan', trip_id: 1, text: '?', changes: {}, message: 'x' })).toBe(true)
    expect(isFinal({ type: 'error', message: 'x' })).toBe(true)
    expect(isFinal({ type: 'thinking', text: '…' })).toBe(false)
    expect(isFinal({ type: 'tool_call', name: 's', query: 'q', places: [] })).toBe(false)
  })
})

describe('viewingOld', () => {
  it('chỉ đúng khi đang xem bản khác bản mới nhất', () => {
    expect(viewingOld(1, 3)).toBe(true)
    expect(viewingOld(3, 3)).toBe(false)
    expect(viewingOld(null, 3)).toBe(false)
    expect(viewingOld(1, null)).toBe(false)
  })
})

describe('tripLabel', () => {
  it('tên Destination · số ngày · ngày tạo', () => {
    expect(tripLabel({ id: 1, spec: { destination: 'da-lat', days: 2 }, created_at: '2026-09-30T12:00:00+07:00',
      destination_name: 'Đà Lạt' })).toBe('Đà Lạt · 2 ngày · 30/09')
  })
  it('thiếu tên thì dùng slug', () => {
    expect(tripLabel({ id: 1, spec: { destination: 'da-lat', days: 1 }, created_at: '2026-01-05T00:00:00Z',
      destination_name: null }).startsWith('da-lat · 1 ngày')).toBe(true)
  })
})
