import { useState } from 'react'

export type ChatItem = { role: 'user' | 'ai' | 'tool' | 'error'; text: string }

const STYLE: Record<ChatItem['role'], string> = {
  user: 'self-end bg-emerald-700 text-white',
  ai: 'bg-white border border-stone-200',
  tool: 'text-xs italic text-stone-500',
  error: 'bg-red-50 text-red-700 border border-red-200',
}

export default function ChatPanel({ items, busy, onSend }: {
  items: ChatItem[]; busy: boolean; onSend: (message: string) => void
}) {
  const [text, setText] = useState('')
  return (
    <aside className="flex min-h-0 flex-col border-r border-stone-200">
      <h1 className="p-4 text-xl font-semibold">Travility</h1>
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-4" aria-live="polite">
        {items.length === 0 && (
          <p className="text-sm text-stone-500">Thử: "Đi Đà Lạt 2 ngày, 5 triệu, thích cafe chill và thiên nhiên"</p>
        )}
        {items.map((it, i) => (
          <div key={i} className={`max-w-[90%] rounded-xl px-3 py-2 text-sm ${STYLE[it.role]}`}>{it.text}</div>
        ))}
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
