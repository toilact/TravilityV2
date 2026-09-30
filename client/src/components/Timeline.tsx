import type { ReactNode } from 'react'
import { intentChips, mealOf, viewingOld, vnd, type DisruptionKind, type Itinerary, type Place } from '../api'

export default function Timeline({ itinerary, places, budget, busy = false, changed = [], onDisrupt,
  versions = [], version = null, latest = null, pins = [], onView, onRestore, onPin, children }: {
  itinerary: Itinerary | null; places: Record<string, Place>; budget: number | null; changed?: [number, number][]
  busy?: boolean; onDisrupt?: (kind: DisruptionKind, dayIndex: number, stopIndex: number) => void
  versions?: number[]; version?: number | null; latest?: number | null; pins?: number[]
  onView?: (v: number) => void; onRestore?: () => void; onPin?: (placeId: number, pinned: boolean) => void
  children?: ReactNode
}) {
  if (!itinerary) {
    return <aside className="border-l border-stone-200 p-4 text-sm text-stone-500">Lịch trình sẽ hiện ở đây.</aside>
  }
  const stay = itinerary.stay_place_id != null ? places[itinerary.stay_place_id] : undefined
  const old = viewingOld(version, latest)
  return (
    <aside className="min-h-0 overflow-y-auto border-l border-stone-200 p-4">
      {children}
      {versions.length > 1 && (
        <nav aria-label="Phiên bản lịch trình" className="mb-2 flex flex-wrap items-center gap-1 text-xs">
          {versions.map((v, i) => (
            <span key={v} className="flex items-center gap-1">
              {i > 0 && <span className="text-stone-400">·</span>}
              <button disabled={busy} aria-current={v === version ? 'true' : undefined} onClick={() => onView?.(v)}
                className={`rounded px-1.5 py-0.5 ${v === version ? 'bg-emerald-700 text-white' : 'hover:bg-stone-200'}`}>
                v{v}
              </button>
            </span>
          ))}
        </nav>
      )}
      {old && (
        <div role="status" className="mb-3 flex flex-wrap items-center gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
          <span>Đang xem bản {version}</span>
          <button disabled={busy} onClick={onRestore}
            className="rounded bg-amber-600 px-2 py-0.5 text-white disabled:opacity-50">Quay lại bản này</button>
          <button disabled={busy} onClick={() => latest != null && onView?.(latest)}
            className="rounded border border-amber-600 px-2 py-0.5 disabled:opacity-50">Về bản mới nhất</button>
        </div>
      )}
      <div className="mb-3 rounded-xl bg-white p-3 shadow-sm">
        <div className="text-sm text-stone-500">Tổng chi phí ước tính</div>
        <div className="text-2xl font-semibold">{vnd(itinerary.total_cost)}</div>
        {budget != null && <div className="text-xs text-stone-500">Budget {vnd(budget)} · chưa gồm vé đến/rời thành phố</div>}
        {stay && <div className="mt-1 text-xs">Chỗ ở: {stay.name}</div>}
        {intentChips(itinerary).length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
            {intentChips(itinerary).map((c) => (
              <span key={c.label}
                className={`rounded-full px-2 py-0.5 ${c.ok ? 'bg-emerald-100 text-emerald-800' : 'bg-stone-200 text-stone-500'}`}>
                {c.ok ? '✓' : '✗'} {c.label}
              </span>
            ))}
            {itinerary.retention != null && (
              <span className="ml-1 text-stone-500">Giữ mục đích {Math.round(itinerary.retention * 100)}%</span>
            )}
          </div>
        )}
      </div>
      {itinerary.conflicts.length > 0 && (
        <ul className="mb-3 space-y-1 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {itinerary.conflicts.map((c, i) => <li key={i}>{c.message}</li>)}
        </ul>
      )}
      {itinerary.days.map((day, i) => (
        <section key={i} className="mb-4">
          <h2 className="mb-2 font-semibold">
            Ngày {i + 1}{day.date && ` · ${day.date}`}{day.rain_chance != null && ` · mưa ${day.rain_chance}%`}
          </h2>
          <ol className="space-y-2">
            {day.stops.map((s, j) => {
              const meal = mealOf(places[s.place_id]?.kind, s.start_time)
              const pinned = pins.includes(s.place_id)
              return (
              <li key={j} className={`rounded-lg p-3 text-sm shadow-sm ${pinned ? 'bg-emerald-50' : 'bg-white'} ${
                changed.some(([d, k]) => d === i && k === j) ? 'ring-2 ring-amber-400' : ''}`}>
                {meal && <div className="mb-1 text-xs font-medium text-amber-700">🍜 {meal}</div>}
                <div className="flex justify-between gap-2">
                  <span className="font-medium">{s.start_time} · {places[s.place_id]?.name}</span>
                  <span className="shrink-0">{vnd(s.est_cost)}</span>
                </div>
                <p className="mt-1 text-xs text-stone-500">{s.reason}</p>
                {!old && (onDisrupt || onPin) && (
                  <div className="mt-2 flex gap-2 text-xs">
                    {onPin && (
                      <button type="button" disabled={busy} aria-pressed={pinned}
                        title={pinned ? 'Bỏ ghim' : 'Ghim: AI không được đổi Stop này'}
                        onClick={() => onPin(s.place_id, !pinned)}
                        className={`rounded border px-2 py-0.5 disabled:opacity-40 ${
                          pinned ? 'border-emerald-600 bg-emerald-600 text-white' : 'border-stone-300 hover:bg-stone-100'}`}>
                        📌 {pinned ? 'Đã ghim' : 'Ghim'}
                      </button>
                    )}
                    {onDisrupt && (['closed', 'disliked'] as const).map((k) => (
                      <button key={k} type="button" disabled={busy || pinned}
                        title={pinned ? 'Bỏ ghim để đổi' : undefined}
                        onClick={() => onDisrupt(k, i, j)}
                        className="rounded border border-stone-300 px-2 py-0.5 hover:bg-stone-100 disabled:opacity-40">
                        {k === 'closed' ? 'Báo đóng cửa' : 'Đổi chỗ khác'}
                      </button>
                    ))}
                  </div>
                )}
              </li>
              )
            })}
          </ol>
          <p className="mt-1 text-xs text-stone-500">
            Di chuyển: {day.legs.reduce((a, l) => a + l.distance_km, 0).toFixed(1)} km · {vnd(day.legs.reduce((a, l) => a + l.cost, 0))}
          </p>
        </section>
      ))}
    </aside>
  )
}
