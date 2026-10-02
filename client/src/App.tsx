import { useEffect, useState } from 'react'
import {
  applyProposal, clarifyAfter, confirmAfter, getMe, optionPlace, reportDisruption, streamPlan, streamReplan, streamTrip, updateMe,
  type AgentEvent, type Answers,
  type Account, type Clarify, type ConfirmReplan, type DisruptionKind, type Itinerary, type ItineraryEvent, type Place, type Proposal,
} from './api'
import ChatPanel, { type ChatItem } from './components/ChatPanel'
import ClarifyCard from './components/ClarifyCard'
import ConfirmCard from './components/ConfirmCard'
import Login from './components/Login'
import MapView from './components/MapView'
import ProposalPanel from './components/ProposalPanel'
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
  const [account, setAccount] = useState<Account | null>(null)
  const [chat, setChat] = useState<ChatItem[]>([])
  const [busy, setBusy] = useState(false)
  const [center, setCenter] = useState<[number, number]>([108.4583, 11.9404])
  const [searchPins, setSearchPins] = useState<Place[]>([])
  const [itinerary, setItinerary] = useState<Itinerary | null>(null)
  const [places, setPlaces] = useState<Record<string, Place>>({})
  const [budget, setBudget] = useState<number | null>(null)
  const [clarify, setClarify] = useState<Clarify | null>(null)
  const [confirm, setConfirm] = useState<ConfirmReplan | null>(null)  // đổi Trip chờ người dùng đồng ý lập lại
  const [tripId, setTripId] = useState<number | null>(null)  // Trip đang mở: tin nhắn sau thuộc Trip này
  const [version, setVersion] = useState<number | null>(null)  // version Itinerary đang xem, gửi kèm Disruption
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const [changed, setChanged] = useState<[number, number][]>([])  // Stop vừa đổi, tô viền trên Timeline

  useEffect(() => {
    if (!token) {
      setAccount(null)
      return
    }
    let cancelled = false
    getMe(token).then((value) => {
      if (!cancelled) setAccount(value)
    }).catch((err) => {
      if (!cancelled && err instanceof Error && err.message === 'unauthorized') {
        saveToken(null)
        setToken(null)
      }
    })
    return () => { cancelled = true }
  }, [token])

  if (!token) return <Login onToken={(t) => { saveToken(t); setToken(t) }} />

  // Định nghĩa hàm logout để xóa token trong state và localStorage
  function logout() {
    saveToken(null)
    setToken(null)
  }

  const add = (item: ChatItem) => setChat((c) => [...c, item])

  function handle(e: AgentEvent) {
    setClarify((c) => clarifyAfter(c, e))
    setConfirm((c) => confirmAfter(c, e))
    switch (e.type) {
      case 'thinking': add({ role: 'ai', text: e.text }); break
      case 'trip':
        setTripId(e.trip_id); setVersion(null); setProposal(null)
        setCenter(e.center); setBudget(e.trip.budget); setItinerary(null)
        break
      case 'tool_call':
        add({ role: 'tool', text: `Đang tìm: ${e.query} (${e.places.length} kết quả)` })
        setSearchPins((p) => [...p, ...e.places.filter((x) => !p.some((y) => y.id === x.id))])
        break
      case 'itinerary':
        setPlaces(e.places); setItinerary(e.itinerary); setVersion(e.version); setChanged(e.changed ?? []); setSearchPins([])
        add({ role: 'ai', text: e.itinerary.summary })
        break
      case 'answer': add({ role: 'ai', text: e.text }); break
      case 'confirm_replan': add({ role: 'ai', text: e.text }); break
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

  async function call<T>(fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(true)
    try {
      return await fn()
    } catch (err) {
      if (err instanceof Error && err.message === 'unauthorized') { saveToken(null); setToken(null) }
      else if (err instanceof Error && !(err instanceof TypeError)) add({ role: 'error', text: err.message })
      else add({ role: 'error', text: 'Mất kết nối tới máy chủ. Kiểm tra server đã chạy chưa.' })
    } finally {
      setBusy(false)
    }
  }

  const disrupt = async (kind: DisruptionKind, day: number, stop: number) => {
    const p = await call(() => reportDisruption(token!, tripId!, version!, kind, day, stop))
    if (!p) return
    setProposal(p)
    setSearchPins((p.options ?? []).map(optionPlace).filter((x): x is Place => x !== undefined))
  }

  const apply = async (option: number) => {
    const ev: ItineraryEvent | undefined = await call(() => applyProposal(token!, tripId!, proposal!.proposal_id, option))
    if (!ev) return
    setChanged(proposal!.options?.[option]?.changed ?? [])
    setProposal(null); setSearchPins([])
    setPlaces(ev.places); setItinerary(ev.itinerary); setVersion(ev.version)
    add({ role: 'ai', text: `Đã áp dụng phương án — lịch trình bản ${ev.version}.` })
  }

  const send = (message: string) => {
    add({ role: 'user', text: message })
    return run((on) => streamTrip(token!, message, tripId, on))
  }
  const newTrip = () => {
    setTripId(null); setVersion(null); setProposal(null); setChat([]); setClarify(null); setConfirm(null)
    setItinerary(null); setSearchPins([]); setBudget(null)
  }
  const answer = (tripId: number, a: Answers) => run((on) => streamPlan(token!, tripId, a, on))

  return (
    <div className="grid h-screen grid-cols-[22rem_1fr_24rem] bg-stone-50 text-stone-900">
      <ChatPanel
        items={chat}
        busy={busy}
        onSend={send}
        onNewTrip={tripId != null ? newTrip : undefined}
        onLogout={logout}
        account={account}
        onSaveAccount={async (value) => {
          const updated = await updateMe(token, value)
          setAccount(updated)
        }}
      >
        {clarify && <ClarifyCard questions={clarify.questions} busy={busy}
          onSubmit={(a) => answer(clarify.tripId, a)} />}
        {confirm && <ConfirmCard text={confirm.text} busy={busy}
          onYes={() => run((on) => streamReplan(token!, confirm, on))}
          onNo={() => { setConfirm(null); add({ role: 'ai', text: 'Đã giữ nguyên lịch trình.' }) }} />}
      </ChatPanel>
      <MapView center={center} searchPins={searchPins} itinerary={itinerary} places={places} />
      <Timeline itinerary={itinerary} places={places} budget={budget} busy={busy} changed={changed}
        onDisrupt={tripId != null && version != null ? disrupt : undefined}>
        {proposal && <ProposalPanel proposal={proposal} busy={busy} onApply={apply}
          onClose={() => { setProposal(null); setSearchPins([]) }} />}
      </Timeline>
    </div>
  )
}
