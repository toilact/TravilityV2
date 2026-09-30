import { useState, type ReactNode } from 'react'

export type ChatItem = { role: 'user' | 'ai' | 'tool' | 'error'; text: string }

const STYLE: Record<ChatItem['role'], string> = {
  user: 'self-end bg-emerald-700 text-white',
  ai: 'bg-white border border-stone-200',
  tool: 'text-xs italic text-stone-500',
  error: 'bg-red-50 text-red-700 border border-red-200',
}

export default function ChatPanel({ items, busy, onSend, onNewTrip, onLogout, children }: {
  items: ChatItem[];
  busy: boolean;
  onSend: (message: string) => void;
  onNewTrip?: () => void;
  onLogout: () => void;
  children?: ReactNode
}) {
  const [text, setText] = useState('')
  const [showMenu, setShowMenu] = useState(false) // Quản lý ẩn/hiện menu dropdown

  // === [THÊM MỚI]: State quản lý Modal thông tin tài khoản và dữ liệu form ===
  const [showProfileModal, setShowProfileModal] = useState(false)
  const [fullName, setFullName] = useState('Nguyễn Văn A') // Tên mặc định
  const [phone, setPhone] = useState('0912345678')       // SĐT mặc định

  function handleSaveProfile(e: React.FormEvent) {
    e.preventDefault()
    alert('Đã cập nhật thông tin thành công!')
    setShowProfileModal(false)
  }

  return (
    <aside className="flex min-h-0 flex-col border-r border-stone-200 relative">
      <div className="flex items-center justify-between p-4">
        <h1 className="text-xl font-semibold">Travility</h1>

        <div className="flex items-center gap-2">
          {onNewTrip && (
            <button disabled={busy} onClick={onNewTrip}
              className="rounded-lg border border-stone-300 px-3 py-1 text-sm disabled:opacity-50">＋ Chuyến mới</button>
          )}

          {/* Khu vực Avatar & Dropdown Menu */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowMenu(!showMenu)}
              className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-700 text-sm font-semibold text-white shadow hover:bg-emerald-800 transition-colors focus:outline-none"
            >
              {fullName ? fullName.charAt(0).toUpperCase() : 'U'}
            </button>

            {showMenu && (
              <div className="absolute right-0 mt-2 w-56 rounded-xl bg-white p-2 shadow-lg border border-stone-200 z-50">
                {/* Thông tin nhanh hiển thị trên menu */}
                <div className="px-3 py-2 border-b border-stone-100 mb-1">
                  <p className="text-xs text-stone-500">Đăng nhập với</p>
                  <p className="text-sm font-medium text-stone-800 truncate">{fullName}</p>
                </div>

                {/* === [THÊM MỚI]: Nút mở bảng Thông tin / Cập nhật tài khoản === */}
                <button
                  type="button"
                  onClick={() => {
                    setShowMenu(false)
                    setShowProfileModal(true) // Mở modal thông tin
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-stone-700 rounded-lg hover:bg-stone-50 transition-colors flex items-center gap-2 font-medium"
                >
                  ⚙️ Thông tin tài khoản
                </button>

                {/* Nút Đăng xuất */}
                <button
                  type="button"
                  onClick={() => {
                    setShowMenu(false)
                    onLogout()
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-red-600 rounded-lg hover:bg-red-50 transition-colors flex items-center gap-2 font-medium mt-1"
                >
                  🚪 Đăng xuất
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Phần Chat chính */}
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

      {/* === [THÊM MỚI]: Giao diện Modal Cập nhật thông tin tài khoản nổi lên màn hình === */}
      {showProfileModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
          <div className="w-full max-w-md bg-white rounded-2xl p-6 shadow-xl border border-stone-200 space-y-4">
            <div className="flex justify-between items-center border-b border-stone-100 pb-3">
              <h2 className="text-lg font-semibold text-stone-800">Thông tin tài khoản</h2>
              <button
                type="button"
                onClick={() => setShowProfileModal(false)}
                className="text-stone-400 hover:text-stone-700 font-bold text-lg"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveProfile} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-stone-700 mb-1">Họ và tên</label>
                <input
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="w-full rounded-lg border border-stone-300 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-600"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-stone-700 mb-1">Số điện thoại</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full rounded-lg border border-stone-300 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-600"
                  required
                />
              </div>

              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowProfileModal(false)}
                  className="px-4 py-2 text-sm rounded-lg border border-stone-300 text-stone-700 hover:bg-stone-100 transition-colors"
                >
                  Hủy
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 text-sm rounded-lg bg-emerald-700 text-white font-medium hover:bg-emerald-800 transition-colors"
                >
                  Lưu thay đổi
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </aside>
  )
}