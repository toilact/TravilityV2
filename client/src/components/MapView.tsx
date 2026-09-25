import { useEffect, useRef, useState } from 'react'
import Map, { Layer, Marker, Source, type MapRef } from 'react-map-gl/maplibre'
import polyline from '@mapbox/polyline'
import type { Itinerary, Place } from '../api'

const STYLE_URL = `https://tiles.goong.io/assets/goong_map_web.json?api_key=${import.meta.env.VITE_GOONG_MAPTILES_KEY}`
export const DAY_COLORS = ['#047857', '#b45309', '#1d4ed8', '#be123c', '#7c3aed', '#0f766e', '#a16207']
const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }

async function legLine(a: Place, b: Place): Promise<[number, number][]> {
  try {
    const r = await fetch(`https://rsapi.goong.io/Direction?origin=${a.lat},${a.lon}&destination=${b.lat},${b.lon}` +
      `&vehicle=bike&api_key=${import.meta.env.VITE_GOONG_API_KEY}`)
    const body = await r.json()
    return polyline.decode(body.routes[0].overview_polyline.points).map(([lat, lon]: [number, number]) => [lon, lat])
  } catch {
    return [[a.lon, a.lat], [b.lon, b.lat]] // Goong lỗi → vẽ đường thẳng, không chặn demo
  }
}

export default function MapView({ center, searchPins, itinerary, places }: {
  center: [number, number]; searchPins: Place[]; itinerary: Itinerary | null; places: Record<string, Place>
}) {
  const mapRef = useRef<MapRef>(null)
  const [routes, setRoutes] = useState<GeoJSON.FeatureCollection>(EMPTY)

  useEffect(() => {
    mapRef.current?.flyTo({ center, zoom: 12.5, pitch: 50, duration: 2000 })
  }, [center])

  useEffect(() => {
    if (!itinerary) {
      setRoutes(EMPTY)
      return
    }
    let cancelled = false
    ;(async () => {
      const features: GeoJSON.Feature[] = []
      for (const [i, day] of itinerary.days.entries()) {
        for (const leg of day.legs) {
          const a = places[leg.from_place_id], b = places[leg.to_place_id]
          if (!a || !b) continue
          features.push({ type: 'Feature', properties: { color: DAY_COLORS[i % DAY_COLORS.length] },
            geometry: { type: 'LineString', coordinates: await legLine(a, b) } })
        }
      }
      if (cancelled) return
      setRoutes({ type: 'FeatureCollection', features })
      for (const day of itinerary.days) {
        for (const s of day.stops) {
          const p = places[s.place_id], map = mapRef.current
          if (cancelled || !p || !map) return
          map.flyTo({ center: [p.lon, p.lat], zoom: 15, pitch: 60, bearing: (map.getBearing() + 40) % 360, duration: 1800 })
          await new Promise((r) => setTimeout(r, 2200))
        }
      }
    })()
    return () => { cancelled = true }
  }, [itinerary, places])

  const stay = itinerary?.stay_place_id != null ? places[itinerary.stay_place_id] : undefined

  return (
    <Map ref={mapRef} mapStyle={STYLE_URL} style={{ width: '100%', height: '100%' }}
      initialViewState={{ longitude: center[0], latitude: center[1], zoom: 12, pitch: 45 }}>
      <Source id="routes" type="geojson" data={routes}>
        <Layer id="routes" type="line" layout={{ 'line-cap': 'round', 'line-join': 'round' }}
          paint={{ 'line-color': ['get', 'color'], 'line-width': 4, 'line-opacity': 0.85 }} />
      </Source>
      {searchPins.map((p) => (
        <Marker key={`s${p.id}`} longitude={p.lon} latitude={p.lat}>
          <span className="relative flex size-3" title={p.name}>
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-amber-400 opacity-75" />
            <span className="relative inline-flex size-3 rounded-full bg-amber-500" />
          </span>
        </Marker>
      ))}
      {itinerary?.days.flatMap((day, i) => day.stops.map((s, j) => {
        const p = places[s.place_id]
        return p && (
          <Marker key={`d${i}-${j}`} longitude={p.lon} latitude={p.lat}>
            <div title={p.name} style={{ background: DAY_COLORS[i % DAY_COLORS.length] }}
              className="flex size-7 items-center justify-center rounded-full border-2 border-white text-xs font-bold text-white shadow">
              {j + 1}
            </div>
          </Marker>
        )
      }))}
      {stay && (
        <Marker longitude={stay.lon} latitude={stay.lat}>
          <div title={stay.name} className="rounded-md border-2 border-white bg-stone-900 px-2 py-1 text-xs font-semibold text-white shadow">
            Chỗ ở
          </div>
        </Marker>
      )}
    </Map>
  )
}
