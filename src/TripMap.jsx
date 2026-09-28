import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

const COLORS = ['#fb7355', '#4b9f85', '#a47ce0', '#dba64e', '#5579c9', '#d56ca1', '#54a7b9'];

export default function TripMap({ itinerary, journeys = [], stayArea, terminals, startLocation, selectedDay, onSelectDay, history = false }) {
  const element = useRef(null);
  const mapRef = useRef(null);
  const layersRef = useRef(null);

  useEffect(() => {
    if (!element.current || mapRef.current) return;
    const map = L.map(element.current, { zoomControl: false, scrollWheelZoom: false }).setView([22.5431, 114.0579], 11);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 18,
    }).addTo(map);
    L.control.zoom({ position: 'bottomright' }).addTo(map);
    mapRef.current = map;
    layersRef.current = L.layerGroup().addTo(map);
    return () => { map.remove(); mapRef.current = null; layersRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layersRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    const bounds = [];
    for (const day of itinerary || []) {
      if (selectedDay && selectedDay !== day.day) continue;
      const coordinates = [];
      day.stops.forEach((stop, index) => {
        const point = [stop.mapCoordinate?.lat ?? stop.lat, stop.mapCoordinate?.lng ?? stop.lng];
        if (!Number.isFinite(stop.lat) || !Number.isFinite(stop.lng)) return;
        coordinates.push(point);
        bounds.push(point);
        const icon = L.divIcon({
          className: 'trip-map-icon',
          html: `<span style="background:${COLORS[(day.day - 1) % COLORS.length]}">${index + 1}</span>`,
          iconSize: [32, 32], iconAnchor: [16, 16],
        });
        const popup = document.createElement('div');
        popup.textContent = `第 ${day.day} 天 · ${stop.name} · ${stop.start || '时间待核实'} · ${stop.category}`;
        L.marker(point, { icon }).addTo(layer).bindPopup(popup).on('click', () => onSelectDay(day.day));
      });
      if (history && coordinates.length > 1) L.polyline(coordinates, { color: COLORS[(day.day - 1) % COLORS.length], weight: 2,
        opacity: .65, dashArray: '3 10' }).addTo(layer).bindTooltip('照片顺序示意，非实际走过的路线');
      for (const route of journeys.filter(item => item.day === day.day)) {
        const path = route.mapGeometry?.length > 1 ? route.mapGeometry.map(item => [item.lat, item.lng]) :
          [route.mapFromCoordinate, route.mapToCoordinate].filter(Boolean).map(item => [item.lat, item.lng]);
        if (path.length < 2) continue;
        bounds.push(...path);
        const line = L.polyline(path, { color: COLORS[(day.day - 1) % COLORS.length], weight: 4, opacity: .85,
          dashArray: route.mapGeometry?.length > 1 ? null : '7 8' }).addTo(layer);
        line.bindTooltip(`${route.from} → ${route.to} · ${route.minutes == null ? '交通时间未知' : `高德预计 ${route.minutes} 分钟`}${route.mapGeometry?.length > 1 ? '' : ' · 示意线'}`);
        line.on('click', () => onSelectDay(day.day));
      }
    }
    for (const point of [stayArea, ...(Object.values(terminals || {}))]) {
      const coord = point?.mapCoordinate || point?.mapFromCoordinate;
      if (!coord || !Number.isFinite(coord.lat) || !Number.isFinite(coord.lng)) continue;
      bounds.push([coord.lat, coord.lng]);
      L.circleMarker([coord.lat, coord.lng], { radius: 7, color: '#173f37', fillOpacity: .9 }).addTo(layer).bindTooltip(point.name);
    }
    if (startLocation && Number.isFinite(startLocation.lat) && Number.isFinite(startLocation.lng)) {
      bounds.push([startLocation.lat, startLocation.lng]);
      L.circleMarker([startLocation.lat, startLocation.lng], { radius: 7, color: '#fb7355', fillOpacity: .9 }).addTo(layer).bindTooltip('出发地点');
    }
    if (bounds.length) map.fitBounds(bounds, { padding: [44, 44], maxZoom: 12 });
    setTimeout(() => map.invalidateSize(), 60);
  }, [itinerary, journeys, stayArea, terminals, startLocation, selectedDay, history]);

  return (
    <div className="map-shell">
      <div ref={element} className="map-canvas" role="img" aria-label="行程地点地图" />
      <div className="map-day-switch" aria-label="选择地图日期">
        <button type="button" className={!selectedDay ? 'active' : ''} onClick={() => onSelectDay(null)}>全部</button>
        {(itinerary || []).map(day => <button type="button" key={day.day} className={selectedDay === day.day ? 'active' : ''} onClick={() => onSelectDay(day.day)}>D{day.day}</button>)}
      </div>
    </div>
  );
}
