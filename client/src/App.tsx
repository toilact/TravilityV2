import { useState } from 'react'
import {
  clarifyAfter, streamPlan, streamTrip, type AgentEvent, type Answers, type Clarify, type Itinerary, type Place,
} from './api'
import ChatPanel, { type ChatItem } from './components/ChatPanel'
import ClarifyCard from './components/ClarifyCard'
import Login from './components/Login'
import MapView from './components/MapView'
import Timeline from './components/Timeline'

function loadToken() {
  try { return localStorage.getItem('token') } catch { return null }
}
function saveToken(t: string | null) {
  try {
    if (t) localStorage.setItem('token', t)
    else localStorage.removeItem('token')
  } catch { /* chỉ là tiện ích nhớ đăng nhập */ }
}

export default function App() {
  const [token, setToken] = useState<string | null>(loadToken)
  const [chat, setChat] = useState<ChatItem[]>([])
  const [busy, setBusy] = useState(false)
  const [center, setCenter] = useState<[number, number]>([108.4583, 11.9404])
  const [searchPins, setSearchPins] = useState<Place[]>([])
  const [itinerary, setItinerary] = useState<Itinerary | null>(null)
  const [places, setPlaces] = useState<Record<string, Place>>({})
  const [budget, setBudget] = useState<number | null>(null)
  const [clarify, setClarify] = useState<Clarify | null>(null)

  if (!token) return <Login onToken={(t) => { saveToken(t); setToken(t) }} />

  const add = (item: ChatItem) => setChat((c) => [...c, item])

  function handle(e: AgentEvent) {
    setClarify((c) => clarifyAfter(c, e))
    switch (e.type) {
      case 'thinking': add({ role: 'ai', text: e.text }); break
      case 'trip': setCenter(e.center); setBudget(e.trip.budget); setItinerary(null); break
      case 'tool_call':
        add({ role: 'tool', text: `Đang tìm: ${e.query} (${e.places.length} kết quả)` })
        setSearchPins((p) => [...p, ...e.places.filter((x) => !p.some((y) => y.id === x.id))])
        break
      case 'itinerary':
        setPlaces(e.places); setItinerary(e.itinerary); setSearchPins([])
        add({ role: 'ai', text: e.itinerary.summary })
        break
      case 'error': add({ role: 'error', text: e.message }); break
    }
  }

  async function run(stream: (onEvent: (e: AgentEvent) => void) => Promise<void>) {
    setBusy(true)
    setSearchPins([])
    try {
      await stream(handle)
    } catch (err) {
      if (err instanceof Error && err.message === 'unauthorized') { saveToken(null); setToken(null) }
      else add({ role: 'error', text: 'Mất kết nối tới máy chủ. Kiểm tra server đã chạy chưa.' })
    } finally {
      setBusy(false)
    }
  }

  const send = (message: string) => {
    add({ role: 'user', text: message })
    setClarify(null)  // câu mới = Trip mới, bỏ câu hỏi của Trip cũ
    return run((on) => streamTrip(token!, message, on))
  }
  const answer = (tripId: number, a: Answers) => run((on) => streamPlan(token!, tripId, a, on))

  return (
    <div className="grid h-screen grid-cols-[22rem_1fr_24rem] bg-stone-50 text-stone-900">
      <ChatPanel items={chat} busy={busy} onSend={send}>
        {clarify && <ClarifyCard questions={clarify.questions} busy={busy}
          onSubmit={(a) => answer(clarify.tripId, a)} />}
      </ChatPanel>
      <MapView center={center} searchPins={searchPins} itinerary={itinerary} places={places} />
      <Timeline itinerary={itinerary} places={places} budget={budget} />
    </div>
  )
}
