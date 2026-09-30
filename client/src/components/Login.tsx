import { useState, type FormEvent } from 'react'
import { authRequest } from '../api'

const INPUT = 'mt-1 w-full rounded-lg border border-stone-300 px-3 py-2'

export default function Login({ onToken }: { onToken: (token: string) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  // 2. Thêm state quản lý hiển thị/ẩn mật khẩu
  const [showPassword, setShowPassword] = useState(false)

  // 4. State lưu trữ lỗi trả về từ server
  const [error, setError] = useState<string | null>(null)

  // 3. State quản lý trạng thái đang gửi (dùng để khóa nút submit)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onToken(await authRequest(mode === 'login' ? '/auth/login' : '/auth/register', email, password))
    } catch (err) {
      // 4. Hiển thị lỗi từ server khi gặp sự cố
      setError(err instanceof Error ? err.message : 'Có lỗi xảy ra')
    } finally {
      setBusy(false)
    }
  }

  // 5. Khi chuyển giữa Đăng nhập/Đăng ký, xóa lỗi cũ
  function handleModeSwitch() {
    setMode(mode === 'login' ? 'register' : 'login')
    setError(null) // Xóa sạch thông báo lỗi cũ tại đây
  }

  return (
    <main className="flex h-screen items-center justify-center bg-stone-100 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-3 rounded-2xl bg-white p-6 shadow">
        {/* 6. Dùng tiếng Việt nhất quán cho tiêu đề */}
        <h1 className="text-2xl font-semibold">Travility</h1>

        {/* 1. Thêm nhãn rõ cho email */}
        <label className="block text-sm">
          Email
          <input
            type="email"
            required
            autoComplete="email"
            className={INPUT}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>

        {/* 1. Thêm nhãn rõ cho mật khẩu */}
        <label className="block text-sm">
          Mật khẩu
          <div className="relative mt-1">
            {/* 2. Thay đổi type linh hoạt dựa vào trạng thái showPassword */}
            <input
              type={showPassword ? 'text' : 'password'}
              required
              minLength={8}
              className={`${INPUT} mt-0 pr-14`}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            {/* 2. Nút bấm bật/tắt hiện/ẩn mật khẩu */}
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute inset-y-0 right-0 px-3 text-xs font-medium text-stone-600 hover:text-stone-900"
            >
              {showPassword ? 'Ẩn' : 'Hiện'}
            </button>
          </div>
        </label>

        {/* 4. Khối giao diện hiển thị lỗi từ server */}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}

        {/* 3. Vô hiệu nút submit khi đang gửi (busy = true) */}
        <button
          disabled={busy}
          className="w-full rounded-lg bg-emerald-700 py-2 text-white disabled:opacity-50 transition-opacity"
        >
          {busy ? 'Đang xử lý...' : (mode === 'login' ? 'Đăng nhập' : 'Đăng ký')}
        </button>

        {/* 5 & 6. Nút chuyển đổi chế độ với từ ngữ tiếng Việt nhất quán ("Đăng nhập", "Đăng ký") */}
        <button
          type="button"
          className="w-full text-sm text-emerald-800"
          onClick={handleModeSwitch}
        >
          {mode === 'login' ? 'Chưa có tài khoản? Đăng ký' : 'Đã có tài khoản? Đăng nhập'}
        </button>
      </form>
    </main>
  )
}