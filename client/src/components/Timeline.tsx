import type { Itinerary, Place } from '../api'

const vnd = (n: number) => n.toLocaleString('vi-VN') + 'đ'

export default function Timeline({ itinerary, places, budget }: {
  itinerary: Itinerary | null; places: Record<string, Place>; budget: number | null
}) {
  if (!itinerary) {
    return <aside className="border-l border-stone-200 p-4 text-sm text-stone-500">Lịch trình sẽ hiện ở đây.</aside>
  }
  const stay = itinerary.stay_place_id != null ? places[itinerary.stay_place_id] : undefined
  return (
    <aside className="min-h-0 overflow-y-auto border-l border-stone-200 p-4">
      <div className="mb-3 rounded-xl bg-white p-3 shadow-sm">
        <div className="text-sm text-stone-500">Tổng chi phí ước tính</div>
        <div className="text-2xl font-semibold">{vnd(itinerary.total_cost)}</div>
        {budget != null && <div className="text-xs text-stone-500">Budget {vnd(budget)} · chưa gồm vé đến/rời thành phố</div>}
        {stay && <div className="mt-1 text-xs">Chỗ ở: {stay.name}</div>}
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
            {day.stops.map((s, j) => (
              <li key={j} className="rounded-lg bg-white p-3 text-sm shadow-sm">
                <div className="flex justify-between gap-2">
                  <span className="font-medium">{s.start_time} · {places[s.place_id]?.name}</span>
                  <span className="shrink-0">{vnd(s.est_cost)}</span>
                </div>
                <p className="mt-1 text-xs text-stone-500">{s.reason}</p>
              </li>
            ))}
          </ol>
          <p className="mt-1 text-xs text-stone-500">
            Di chuyển: {day.legs.reduce((a, l) => a + l.distance_km, 0).toFixed(1)} km · {vnd(day.legs.reduce((a, l) => a + l.cost, 0))}
          </p>
        </section>
      ))}
    </aside>
  )
}
