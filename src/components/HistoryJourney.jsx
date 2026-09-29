import React, { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api.js';
import TripMap from '../TripMap.jsx';

async function json(path, options) {
  const response = await apiFetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || result.error || `HTTP ${response.status}`);
  return result;
}

export function HistoryImporter({ onCreated, homeCity = '' }) {
  const [files, setFiles] = useState([]);
  const [title, setTitle] = useState('过往旅行');
  const [departureCity, setDepartureCity] = useState(homeCity);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { setDepartureCity(homeCity || ''); }, [homeCity]);
  async function importFiles() {
    setBusy(true);
    try {
      const trip = await json('/api/history/trips', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, homeCity: departureCity.trim() }) });
      onCreated();
      for (let index = 0; index < files.length; index++) {
        setStatus(`上传照片 ${index + 1}/${files.length}`);
        const file = files[index];
        const result = await apiFetch('/api/media/photos', { method: 'POST', headers: { 'Content-Type': 'image/jpeg', 'X-Trip-Id': trip.id,
          'X-Client-Asset-Key': `${file.name}-${file.size}-${file.lastModified}`.replace(/\s/g, '_').slice(0, 128) }, body: file });
        if (!result.ok) throw new Error((await result.json()).detail || '上传失败');
      }
      const listed = await json(`/api/media/photos?tripId=${encodeURIComponent(trip.id)}`);
      if (listed.photos?.length) {
        setStatus('正在私有 Spark 上分析照片…');
        try {
          let job = await json('/api/media/analysis-jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tripId: trip.id, photoIds: listed.photos.map(item => item.id), batchId: crypto.randomUUID(), purpose: 'history' }) });
          while (job.status === 'queued' || job.status === 'running') {
            await new Promise(resolve => setTimeout(resolve, 5000));
            job = await json(`/api/media/analysis-jobs/${job.id}`);
            setStatus(`私有照片分析 ${job.completed}/${job.total}`);
          }
        } catch (error) { setStatus(`视觉分析未完成：${error.message}；仍会保留元数据草稿。`); }
      }
      setStatus('正在从照片生成草稿…');
      await json(`/api/history/trips/${trip.id}/reconstruct`, { method: 'POST' });
      setStatus('草稿已保存。可进入行程继续补充。');
      onCreated();
    } catch (error) { setStatus(`导入暂停：${error.message}`); }
    finally { setBusy(false); }
  }
  return <section className="rounded-xl border p-4 space-y-3"><h3 className="font-semibold">从照片找回旅行</h3>
    <p className="text-sm text-muted-foreground">选择 JPEG 原图以保留拍摄时间和位置；照片只上传到私有相册。</p>
    <input aria-label="旅行名称" value={title} onChange={event => setTitle(event.target.value)} className="w-full rounded border p-2" />
    <input aria-label="常居住地" value={departureCity} onChange={event => setDepartureCity(event.target.value)} placeholder="常居住地，例如长春" className="w-full rounded border p-2" />
    <input aria-label="选择旅行照片" type="file" accept="image/jpeg" multiple onChange={event => setFiles(Array.from(event.target.files || []))} />
    <button className="solid-button" disabled={busy || !files.length} onClick={importFiles}>导入并生成草稿</button>
    {status && <p role="status" className="text-sm">{status}</p>}
  </section>;
}

export function HistoryJourney({ trip, onBack, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [message, setMessage] = useState('');
  const [reply, setReply] = useState('');
  const [error, setError] = useState('');
  const [selectedDay, setSelectedDay] = useState(1);
  const mapDays = (detail?.history?.days || []).map((day, index) => ({ day: index + 1, date: day.date,
    stops: day.events.filter(event => event.coordinate && Number.isFinite(event.coordinate.lat) && Number.isFinite(event.coordinate.lng))
      .map(event => ({ id: event.id, name: event.label, lat: event.coordinate.lat, lng: event.coordinate.lng,
        mapCoordinate: event.coordinate, category: '照片线索', start: event.observedAt?.slice(11, 16) })) }));
  async function refresh() { try { setDetail(await json(`/api/history/trips/${trip.id}`)); } catch (reason) { setError(reason.message); } }
  useEffect(() => { refresh(); }, [trip.id]);
  async function action(name, body) {
    try {
      const result = await json(`/api/history/trips/${trip.id}/${name}`, { method: 'POST', headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
      setReply(result.reply || '已保存'); setMessage(''); await refresh(); onChanged?.();
    } catch (reason) { setError(reason.message); }
  }
  return <div className="trip-detail page-enter space-y-5"><button className="text-button" onClick={onBack}>返回所有行程</button>
    <h1 className="text-3xl font-semibold">{detail?.title || trip.title}</h1>
    {detail?.history?.possibleCity?.name && <p>可能去过：{detail.history.possibleCity.name} · AI 推断 · {detail.history.possibleCity.reason}</p>}
    <p>照片只是时间与地点的线索；未拍摄的活动、住宿和交通保持未知。</p>
    {detail?.history?.journeyHypothesis && <section className="rounded-xl border p-4 space-y-2">
      <h2 className="font-semibold">可能的跨城行程 · 私有模型推断</h2>
      <p>{detail.history.journeyHypothesis.summary}</p>
      {!!detail.history.journeyHypothesis.cities?.length && <p className="text-sm text-muted-foreground">{detail.history.journeyHypothesis.cities.map(city => `${city.name}（${city.role}）`).join(' → ')}</p>}
      {!!detail.history.journeyHypothesis.legs?.length && <ol className="text-sm space-y-1">{detail.history.journeyHypothesis.legs.map((leg, index) => <li key={`${leg.date}-${index}`}>{leg.date} · {leg.from} → {leg.to} · {leg.mode} · {leg.confidence}</li>)}</ol>}
      {!!detail.history.journeyHypothesis.unknowns?.length && <p className="text-sm text-muted-foreground">待核实：{detail.history.journeyHypothesis.unknowns.join('、')}</p>}
    </section>}
    {mapDays.some(day => day.stops.length) && <section className="rounded-xl border p-4"><h2 className="font-semibold">照片位置</h2><TripMap itinerary={mapDays} selectedDay={selectedDay} onSelectDay={setSelectedDay} history /></section>}
    {detail?.history?.days?.filter((_, index) => !mapDays.length || !selectedDay || selectedDay === index + 1).map(day => <section className="rounded-xl border p-4" key={day.date}><h2 className="font-semibold">{day.date}</h2><ol className="mt-3 space-y-2">{day.events.map(event => <li key={event.id}><strong>{event.label}</strong><span className="ml-2 text-sm text-muted-foreground">{event.observedAt || '时间未知'} · {event.source === 'user_confirmed' ? '你已确认' : event.source === 'photo_evidence' ? '照片线索' : '待分析'}</span></li>)}</ol></section>)}
    <textarea aria-label="补充过往行程" value={message} onChange={event => setMessage(event.target.value)} rows={3} className="w-full rounded border p-3" placeholder="例如：第一天先去酒店，西湖是第二天去的" />
    <div className="flex gap-2"><button className="solid-button" disabled={!message.trim()} onClick={() => action('chat', { message })}>发送补充</button><button className="text-button" onClick={() => action('undo')}>撤销</button><button className="text-button" onClick={() => action('confirm')}>确认行程</button></div>
    {reply && <p role="status">{reply}</p>}{error && <p role="alert" className="text-red-600">{error}</p>}
  </div>;
}
