import { describe, expect, it } from 'vitest'
import { clarifyAfter, toAnswers, type AgentEvent } from './api'

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
