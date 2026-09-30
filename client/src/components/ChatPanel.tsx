import { useState, type ReactNode } from 'react'
import { tripLabel, type TripSummary } from '../api'

export type ChatItem = { role: 'user' | 'ai' | 'tool' | 'error'; text: string }

const STYLE: Record<ChatItem['role'], string> = {
  user: 'self-end bg-emerald-700 text-white',
  ai: 'bg-white border border-stone-200',
  tool: 'text-xs italic text-stone-500',
  error: 'bg-red-50 text-red-700 border border-red-200',
}

export default function ChatPanel({ items, busy, onSend, onNewTrip, trips, onOpenTrip, onLogout, children }: {
  items: ChatItem[]; busy: boolean; onSend: (message: string) => void; onNewTrip?: () => void
  trips: TripSummary[]; onOpenTrip: (id: number) => void; onLogout: () => void; children?: ReactNode
}) {
  const [text, setText] = useState('')
  return (
    <aside className="flex min-h-0 flex-col border-r border-stone-200">
      <div className="flex items-center justify-between gap-2 p-4">
        <h1 className="text-xl font-semibold">Travility</h1>
        <div className="flex items-center gap-2">
          {onNewTrip && (
            <button disabled={busy} onClick={onNewTrip}
              className="rounded-lg border border-stone-300 px-3 py-1 text-sm disabled:opacity-50">＋ Chuyến mới</button>
          )}
          <button onClick={onLogout} className="text-xs text-stone-500 hover:underline">Đăng xuất</button>
        </div>
      </div>
      {trips.length > 0 && (
        <details className="mx-4 mb-2 text-sm">
          <summary className="cursor-pointer text-stone-600">Chuyến đi của tôi ({trips.length})</summary>
          <ul className="mt-1 max-h-48 space-y-1 overflow-y-auto">
            {trips.map((t) => (
              <li key={t.id}>
                <button disabled={busy} onClick={() => onOpenTrip(t.id)}
                  className="w-full rounded px-2 py-1 text-left hover:bg-stone-100 disabled:opacity-50">
                  {tripLabel(t)}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-4" aria-live="polite">
        {items.length === 0 && (
          <p className="text-sm text-stone-500">Thử: "Đi Đà Lạt 2 ngày, 5 triệu, thích cafe chill và thiên nhiên"</p>
        )}
        {items.map((it, i) => (
          <div key={i} className={`max-w-[90%] rounded-xl px-3 py-2 text-sm ${STYLE[it.role]}`}>{it.text}</div>
        ))}
        {children}
        {busy && <div className="animate-pulse text-xs text-stone-500">AI đang lên lịch trình…</div>}
      </div>
      <form className="flex gap-2 border-t border-stone-200 p-3" onSubmit={(e) => {
        e.preventDefault()
        const m = text.trim()
        if (!m || busy) return
        setText('')
        onSend(m)
      }}>
        <input aria-label="Yêu cầu chuyến đi" placeholder="Bạn muốn đi đâu?"
          className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm"
          value={text} onChange={(e) => setText(e.target.value)} />
        <button disabled={busy} className="rounded-lg bg-emerald-700 px-4 text-sm text-white disabled:opacity-50">Gửi</button>
      </form>
    </aside>
  )
}
