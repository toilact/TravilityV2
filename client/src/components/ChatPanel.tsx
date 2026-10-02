import { useEffect, useState, type FormEvent, type ReactNode } from 'react'
import type { Account } from '../api'

export type ChatItem = { role: 'user' | 'ai' | 'tool' | 'error'; text: string }

const STYLE: Record<ChatItem['role'], string> = {
  user: 'self-end bg-emerald-700 text-white',
  ai: 'bg-white border border-stone-200',
  tool: 'text-xs italic text-stone-500',
  error: 'bg-red-50 text-red-700 border border-red-200',
}

type AccountForm = { full_name: string; phone: string | null }

export default function ChatPanel({ items, busy, onSend, onNewTrip, onLogout, account, onSaveAccount, children }: {
  items: ChatItem[];
  busy: boolean;
  onSend: (message: string) => void;
  onNewTrip?: () => void;
  onLogout: () => void;
  account: Account | null;
  onSaveAccount: (value: AccountForm) => Promise<void>;
  children?: ReactNode;
}) {
  const [text, setText] = useState('')
  const [showMenu, setShowMenu] = useState(false)
  const [showProfileModal, setShowProfileModal] = useState(false)
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [profileError, setProfileError] = useState<string | null>(null)
  const [savingProfile, setSavingProfile] = useState(false)

  useEffect(() => {
    setFullName(account?.full_name ?? '')
    setPhone(account?.phone ?? '')
  }, [account])

  async function handleSaveProfile(e: FormEvent) {
    e.preventDefault()
    setSavingProfile(true)
    setProfileError(null)
    try {
      await onSaveAccount({ full_name: fullName, phone: phone || null })
      setShowProfileModal(false)
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : 'Không lưu được thông tin tài khoản')
    } finally {
      setSavingProfile(false)
    }
  }

  const accountLabel = account?.full_name || account?.email || 'Đang tải...'

  return (
    <aside className="relative flex min-h-0 flex-col border-r border-stone-200">
      <div className="flex items-center justify-between p-4">
        <h1 className="text-xl font-semibold">Travility</h1>

        <div className="flex items-center gap-2">
          {onNewTrip && (
            <button disabled={busy} onClick={onNewTrip}
              className="rounded-lg border border-stone-300 px-3 py-1 text-sm disabled:opacity-50">＋ Chuyến mới</button>
          )}

          <div className="relative">
            <button type="button" onClick={() => setShowMenu((value) => !value)}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-700 text-sm font-semibold text-white shadow hover:bg-emerald-800">
              {accountLabel.charAt(0).toUpperCase()}
            </button>

            {showMenu && (
              <div className="absolute right-0 z-50 mt-2 w-56 rounded-xl border border-stone-200 bg-white p-2 shadow-lg">
                <div className="mb-1 border-b border-stone-100 px-3 py-2">
                  <p className="text-xs text-stone-500">Đăng nhập với</p>
                  <p className="truncate text-sm font-medium text-stone-800">{accountLabel}</p>
                  {account?.email && <p className="truncate text-xs text-stone-500">{account.email}</p>}
                </div>
                <button type="button" onClick={() => {
                  setShowMenu(false)
                  setProfileError(null)
                  setShowProfileModal(true)
                }}
                  className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium text-stone-700 hover:bg-stone-50">
                  Thông tin tài khoản
                </button>
                <button type="button" onClick={() => { setShowMenu(false); onLogout() }}
                  className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium text-red-600 hover:bg-red-50">
                  Đăng xuất
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-4" aria-live="polite">
        {items.length === 0 && (
          <p className="text-sm text-stone-500">Thử: “Đi Đà Lạt 2 ngày, 5 triệu, thích cafe chill và thiên nhiên”</p>
        )}
        {items.map((it, i) => (
          <div key={i} className={`max-w-[90%] rounded-xl px-3 py-2 text-sm ${STYLE[it.role]}`}>{it.text}</div>
        ))}
        {children}
        {busy && <div className="animate-pulse text-xs text-stone-500">AI đang lên lịch trình…</div>}
      </div>

      <form className="flex gap-2 border-t border-stone-200 p-3" onSubmit={(e) => {
        e.preventDefault()
        const message = text.trim()
        if (!message || busy) return
        setText('')
        onSend(message)
      }}>
        <input aria-label="Yêu cầu chuyến đi" placeholder="Bạn muốn đi đâu?"
          className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-2 text-sm"
          value={text} onChange={(e) => setText(e.target.value)} />
        <button disabled={busy} className="rounded-lg bg-emerald-700 px-4 text-sm text-white disabled:opacity-50">Gửi</button>
      </form>

      {showProfileModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4">
          <div className="w-full max-w-md space-y-4 rounded-2xl border border-stone-200 bg-white p-6 shadow-xl">
            <div className="flex items-center justify-between border-b border-stone-100 pb-3">
              <h2 className="text-lg font-semibold text-stone-800">Thông tin tài khoản</h2>
              <button type="button" onClick={() => setShowProfileModal(false)} className="text-lg font-bold text-stone-400 hover:text-stone-700">×</button>
            </div>

            <form onSubmit={handleSaveProfile} className="space-y-4">
              <label className="block text-sm font-medium text-stone-700">
                Họ và tên
                <input type="text" required minLength={2} value={fullName} onChange={(e) => setFullName(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-stone-300 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-600" />
              </label>
              <label className="block text-sm font-medium text-stone-700">
                Số điện thoại <span className="font-normal text-stone-500">(không bắt buộc)</span>
                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-stone-300 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-600" />
              </label>
              {profileError && <p role="alert" className="text-sm text-red-700">{profileError}</p>}
              <div className="flex justify-end gap-2 pt-3">
                <button type="button" onClick={() => setShowProfileModal(false)}
                  className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-700 hover:bg-stone-100">Hủy</button>
                <button type="submit" disabled={savingProfile || !account}
                  className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50">
                  {savingProfile ? 'Đang lưu...' : 'Lưu thay đổi'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
  )
}
