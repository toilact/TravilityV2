import { useState } from 'react'
import Login from './components/Login'

export default function App() {
  const [token, setToken] = useState<string | null>(null)
  if (!token) return <Login onToken={setToken} />
  return <p className="p-6">Đã đăng nhập.</p>
}
