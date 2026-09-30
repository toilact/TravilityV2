import { useState, type ReactNode } from 'react'

export type ChatItem = { role: 'user' | 'ai' | 'tool' | 'error'; text: string }

const STYLE: Record<ChatItem['role'], string> = {
  user: 'self-end bg-pine text-white',
  ai: 'bg-white border border-stone-200',
  tool: 'text-xs italic text-stone-500',
  error: 'bg-red-50 text-red-700 border border-red-200',
}

const SUGGESTIONS = [
  'Đà Lạt 2 ngày, 3 triệu, thích cafe view đẹp',
  'Đà Lạt 3 ngày cho gia đình có trẻ nhỏ, đi ô tô',
  'Đà Lạt 1 ngày săn mây ở Cầu Đất, đi xe máy',
]

export default function ChatPanel({ items, busy, onSend, children }: {
  items: ChatItem[]; busy: boolean; onSend: (message: string) => void; children?: ReactNode
}) {
  const [text, setText] = useState('')
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-4" aria-live="polite">
        {items.length === 0 && (
          <div className="grid gap-3 py-2">
            <h3 className="text-2xl font-extrabold leading-tight tracking-tight text-pine">Cuối tuần này bạn muốn đi đâu?</h3>
            <p className="text-sm text-stone-500">Cho Travility biết nơi đến, số ngày và ngân sách. Lịch trình hiện ngay trên bản đồ, sửa bằng cách nhắn tiếp.</p>
            {SUGGESTIONS.map((s) => (
              <button key={s} type="button" disabled={busy} onClick={() => onSend(s)}
                className="rounded-xl border border-stone-200 bg-white px-3 py-2.5 text-left text-sm hover:border-pine disabled:opacity-50">
                {s}
              </button>
            ))}
          </div>
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
        <input aria-label="Yêu cầu chuyến đi" placeholder="Nhắn cho Travility…"
          className="min-w-0 flex-1 rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm"
          value={text} onChange={(e) => setText(e.target.value)} />
        <button disabled={busy} className="rounded-lg bg-marigold px-4 text-sm font-semibold text-stone-900 disabled:opacity-50">Gửi</button>
      </form>
    </div>
  )
}
