import React, { useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, CalendarDays, ChevronRight, Compass, LoaderCircle, MapPin, Plus, RefreshCw, Send, Sparkles } from 'lucide-react';
import { PrivateMedia } from '../components/PrivateMedia.jsx';
import { cityArtwork, tripDate, tripTitle } from '../lib/media.js';
import { apiFetch } from '../lib/api.js';
import { HistoryImporter, HistoryJourney } from '../components/HistoryJourney.jsx';
import TripMap from '../TripMap.jsx';

const STATUS = { not_started: '即将出发', in_progress: '正在旅途', ended: '旅程已结束' };

function TripCover({ trip, index = 0, large = false }) {
  return <div className={`trip-cover trip-cover-${index % 4}${large ? ' trip-cover-large' : ''}`}>
    <img src={cityArtwork(trip)} alt={`${tripTitle(trip)}的风格化城市插画`} />
    <span className="trip-cover-city">{tripTitle(trip)}</span>
  </div>;
}

function PlanComposer({ form, update, onGenerate, running, error, events, onCancel }) {
  const recent = [...events].reverse().find(item => item.type === 'model_turn_end' && item.publicNote);
  return <section className="plan-composer" aria-label="规划新行程">
    <div className="section-kicker"><Sparkles size={15} /> 从一个想法开始</div>
    <h2>下一站，想去哪里？</h2>
    <p>说说时间、预算和你喜欢的旅行方式，我们会把它整理成可查看、可修改的行程。</p>
    <form onSubmit={event => { event.preventDefault(); if (form.query.trim()) onGenerate(); }}>
      <label className="sr-only" htmlFor="trip-query">描述旅行计划</label>
      <textarea id="trip-query" rows={3} value={form.query} onChange={event => update('query', event.target.value)} placeholder="例如：十月从上海出发去成都玩四天，想看熊猫、吃川菜，行程轻松一些…" required />
      <details className="plan-options"><summary>补充出发地与日期（可选）</summary><div className="plan-options-grid">
        <label>出发城市<input value={form.originCity} onChange={event => update('originCity', event.target.value)} placeholder="例如 上海" /></label>
        <label>目的地<input value={form.destination} onChange={event => update('destination', event.target.value)} placeholder="也可由需求识别" /></label>
        <label>出发日期<input type="date" value={form.startDate} onChange={event => update('startDate', event.target.value)} /></label>
        <label>旅行天数<input type="number" min="1" max="21" value={form.days} onChange={event => update('days', event.target.value ? Number(event.target.value) : '')} placeholder="天数" /></label>
      </div></details>
      <div className="plan-composer-actions"><span>地点与价格会标明来源</span><button className="solid-button" disabled={running || !form.query.trim()} type="submit">{running ? <LoaderCircle size={17} className="spin" /> : <ArrowRight size={17} />}{running ? '正在规划…' : '生成行程'}</button></div>
    </form>
    {running ? <div className="plan-progress" role="status"><span className="progress-dot" />{recent?.publicNote || '正在查找地点、交通与住宿，稍等片刻…'}<button type="button" onClick={onCancel}>停止</button></div> : null}
    {error ? <p className="form-error" role="alert">{error}</p> : null}
  </section>;
}

function ScheduleAdjuster({ trip, onUpdated }) {
  const plan = trip.plan;
  const [outbound, setOutbound] = useState(plan.recommendedOutboundFlightId || plan.recommendedOutboundTrainId || '');
  const [returning, setReturning] = useState(plan.recommendedReturnFlightId || plan.recommendedReturnTrainId || '');
  const [hotel, setHotel] = useState(plan.selectedHotelId || '');
  const [orders, setOrders] = useState(() => Object.fromEntries((plan.itinerary || []).map(day => [day.date, day.stops.map(stop => stop.id)])));
  const [durations, setDurations] = useState({});
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);
  const outboundOffers = [...(plan.flights || []), ...(plan.trains || [])];
  const returnOffers = [...(plan.returnFlights || []), ...(plan.returnTrains || [])];
  function move(date, index, delta) {
    setOrders(previous => { const next = [...previous[date]]; const other = index + delta;
      if (other < 0 || other >= next.length) return previous;
      [next[index], next[other]] = [next[other], next[index]];
      return { ...previous, [date]: next }; });
  }
  async function save() {
    setBusy(true); setStatus('正在重新查询高德路线…');
    try {
      const payload = { dayOrders: orders, durations };
      const selectedOutbound = outboundOffers.find(item => item.id === outbound);
      const selectedReturn = returnOffers.find(item => item.id === returning);
      if (selectedOutbound) payload[selectedOutbound.flightNumber ? 'outboundFlightId' : 'outboundTrainId'] = outbound;
      if (selectedReturn) payload[selectedReturn.flightNumber ? 'returnFlightId' : 'returnTrainId'] = returning;
      if (hotel) payload.hotelId = hotel;
      const response = await apiFetch(`/api/trips/${trip.id}/recalculate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
      onUpdated(result); setStatus('时间线和地图已更新。');
    } catch (error) { setStatus(error.message); }
    finally { setBusy(false); }
  }
  return <details className="rounded-xl border p-4"><summary className="cursor-pointer font-semibold">调整班次、酒店、顺序与时长</summary><div className="mt-3 space-y-3 text-sm">
    {outboundOffers.length > 0 && <label className="block">去程 <select value={outbound} onChange={event => setOutbound(event.target.value)} className="ml-2 rounded border p-1"><option value="">未选</option>{outboundOffers.map(item => <option key={item.id} value={item.id}>{item.flightNumber || item.trainNumber} · {item.departureAt}</option>)}</select></label>}
    {returnOffers.length > 0 && <label className="block">返程 <select value={returning} onChange={event => setReturning(event.target.value)} className="ml-2 rounded border p-1"><option value="">未选</option>{returnOffers.map(item => <option key={item.id} value={item.id}>{item.flightNumber || item.trainNumber} · {item.departureAt}</option>)}</select></label>}
    {(plan.hotels || []).length > 0 && <label className="block">酒店 <select value={hotel} onChange={event => setHotel(event.target.value)} className="ml-2 rounded border p-1"><option value="">住宿区域</option>{plan.hotels.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>}
    {(plan.itinerary || []).map(day => <div key={day.date}><strong>{day.date}</strong>{(orders[day.date] || []).map((id, index) => { const stop = day.stops.find(item => item.id === id); return <div key={id} className="flex items-center gap-2 py-1"><span>{stop?.name}</span><button onClick={() => move(day.date, index, -1)} aria-label={`提前${stop?.name}`}>↑</button><button onClick={() => move(day.date, index, 1)} aria-label={`推后${stop?.name}`}>↓</button><input aria-label={`${stop?.name}游玩分钟`} type="number" min="30" max="360" value={durations[id] ?? stop?.duration ?? stop?.recommendedDurationMinutes ?? 90} onChange={event => setDurations(previous => ({ ...previous, [id]: Number(event.target.value) }))} className="w-20 rounded border p-1" />分钟</div>; })}</div>)}
    <button className="solid-button" disabled={busy} onClick={save}>重新计算</button>{status && <span role="status">{status}</span>}
  </div></details>;
}

function TripDetail({ trip, index, onBack, onRevise, onRecalculated, running, token }) {
  const [instruction, setInstruction] = useState('');
  const [selectedDay, setSelectedDay] = useState(1);
  const plan = trip.plan;
  return <div className="trip-detail page-enter">
    <button className="text-button" onClick={onBack}><ArrowLeft size={17} /> 返回所有行程</button>
    <TripCover trip={trip} index={index} large />
    <div className="trip-detail-head"><div><span className="section-kicker">YOUR ITINERARY</span><h1>{tripTitle(trip)}</h1><p><CalendarDays size={16} />{tripDate(trip)}{plan?.days ? ` · ${plan.days} 天` : ''}</p></div><span className="status-pill">{STATUS[trip.status] || '规划中'}</span></div>
    {!plan ? <div className="empty-panel"><Compass /><h2>行程还在形成中</h2><p>继续回答规划问题，确定后就能在这里查看逐日安排。</p></div> : <>
      <div className="trip-facts"><span>目的地 <strong>{plan.destination}</strong></span><span>景点 <strong>{plan.itinerary?.reduce((count, day) => count + (day.stops?.length || 0), 0) || 0} 处</strong></span><span>住宿选择 <strong>{plan.hotels?.length || 0} 项</strong></span><span>交通选择 <strong>{(plan.flights?.length || 0) + (plan.trains?.length || 0)} 项</strong></span></div>
      <ScheduleAdjuster key={plan.generatedAt} trip={trip} onUpdated={onRecalculated} />
      <section className="rounded-xl border p-4"><h2 className="mb-2 font-semibold">行程路线</h2><p className="mb-2 text-sm text-muted-foreground">实线来自高德；虚线是地点间示意。点选路线查看当天时间线。</p><TripMap itinerary={plan.itinerary || []} journeys={plan.groundJourneys || []} stayArea={plan.stayArea} terminals={plan.terminals} startLocation={plan.startLocation} selectedDay={selectedDay} onSelectDay={setSelectedDay} /></section>
      <section className="trip-days"><div className="section-heading"><div><span className="section-kicker">DAY BY DAY</span><h2>每天，都有值得期待的事</h2></div></div>
        {(plan.itinerary || []).filter(day => !selectedDay || selectedDay === day.day).map((day, dayIndex) => <article className="trip-day" key={day.day}><div className="day-number">{String(day.day || dayIndex + 1).padStart(2, '0')}</div><div><div className="day-heading"><div><h3>{day.title || `第 ${day.day} 天`}</h3><p>{day.date}{day.city ? ` · ${day.city}` : ''}{day.feasibility?.issues?.length ? ` · ${day.feasibility.issues.join('；')}` : ''}</p>{day.timeCost && <p>时间成本：交通 {day.timeCost.travelMinutes} 分钟 · 游玩 {day.timeCost.visitMinutes} 分钟 · 准备与用餐 {day.timeCost.bufferMinutes} 分钟{day.timeCost.unknownLegs ? ` · ${day.timeCost.unknownLegs} 段未知` : ''}</p>}</div><span>DAY {day.day}</span></div>
          {day.timeline?.length ? <ol className="stop-list">{day.timeline.map((item, stopIndex) => <li key={stopIndex}><span className="stop-time">{item.startAt?.slice(11, 16) || '待定'}</span><div><strong>{item.label}</strong><small>{item.routeStatus === 'unknown' ? '高德交通时间未知' : item.durationSource === 'ai_recommended' ? 'AI 建议时长' : item.durationSource === 'planning_default' ? '规划占位时长' : item.minutes != null ? `${item.minutes} 分钟` : item.kind}</small></div></li>)}</ol> : <p className="quiet-copy">这一天的时间线还没有生成。</p>}
        </div></article>)}
      </section>
      {trip.photos?.length ? <section className="trip-photo-section"><div className="section-heading"><div><span className="section-kicker">MOMENTS</span><h2>这趟旅程的照片</h2></div></div>{token ? <div className="trip-photo-grid">{trip.photos.slice(0, 6).map(photo => <PrivateMedia key={photo.id} url={`/api/media/photos/${photo.id}`} token={token} alt={`${tripTitle(trip)}的旅行照片`} />)}</div> : <p className="quiet-copy">照片保存在私有相册。到设置页连接后可查看。</p>}</section> : null}
      <section className="revise-panel"><div><span className="section-kicker">MAKE IT YOURS</span><h2>想换一种走法？</h2><p>可以继续修改这趟行程，已确定的内容会保留在历史版本里。</p></div><form onSubmit={event => { event.preventDefault(); if (instruction.trim()) { onRevise(trip, instruction.trim()); setInstruction(''); } }}><label className="sr-only" htmlFor="revision">修改行程</label><textarea id="revision" value={instruction} onChange={event => setInstruction(event.target.value)} placeholder="例如：第三天轻松一点，留更多时间在老城区…" rows={3} /><button className="solid-button" disabled={running || !instruction.trim()} type="submit"><Send size={16} />发送修改</button></form></section>
    </>}
  </div>;
}

export default function TripsView({ trips, refreshTrips, currentTripId, currentPlan, form, memory, update, onGenerate, events, error, running, onCancel, onOpenTrip, onRevise, token }) {
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const [composing, setComposing] = useState(false);
  async function open(id) {
    setLoading(true); setDetailError('');
    try {
      const response = await apiFetch(`/api/trips/${encodeURIComponent(id)}`);
      if (!response.ok) throw new Error('行程暂时无法读取');
      const detail = await response.json();
      setSelected(detail); setComposing(false); onOpenTrip(detail);
    } catch (reason) { setDetailError(reason.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { if (currentTripId && !running && selected?.id !== currentTripId) open(currentTripId); }, [currentTripId, running]);
  useEffect(() => { if (currentPlan && currentTripId) setSelected(previous => previous?.id === currentTripId ? { ...previous, plan: currentPlan } : previous); }, [currentPlan, currentTripId]);
  const selectedIndex = trips.findIndex(item => item.id === selected?.id);
  if (selected?.kind === 'history') return <HistoryJourney trip={selected} onBack={() => setSelected(null)} onChanged={refreshTrips} />;
  if (selected) return <TripDetail trip={selected} index={selectedIndex < 0 ? 0 : selectedIndex} onBack={() => setSelected(null)} running={running} token={token} onRevise={(trip, instruction) => onRevise(trip.id, instruction)} onRecalculated={plan => { setSelected(previous => ({ ...previous, plan })); refreshTrips(); }} />;
  return <div className="journeys-page page-enter">
    <section className="journeys-hero"><div><span className="section-kicker">THE JOURNEY BEGINS HERE</span><h1>去看看世界，<br /><em>也留下自己的故事。</em></h1><p>从一个念头出发，把每一次计划都变成值得回看的旅程。</p><button className="light-button" onClick={() => { setComposing(true); document.getElementById('plan-composer')?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }}><Plus size={18} /> 规划新行程</button></div><div className="hero-art"><img src="/art/travel-cover.webp" alt="山海与小镇的风格化旅行插画" /></div></section>
    <div id="plan-composer" className={composing || !trips.length || running || error ? '' : 'composer-collapsed'}><PlanComposer form={form} update={update} onGenerate={() => { setComposing(true); onGenerate(); }} running={running} error={error} events={events} onCancel={onCancel} /></div>
    <HistoryImporter onCreated={refreshTrips} homeCity={memory?.homeCity} />
    <section className="journey-list"><div className="section-heading"><div><span className="section-kicker">YOUR COLLECTION</span><h2>我的行程 <span>{trips.length ? String(trips.length).padStart(2, '0') : ''}</span></h2><p>继续筹备，或重新走进一段已经完成的旅程。</p></div><button className="icon-text-button" onClick={refreshTrips} aria-label="刷新行程"><RefreshCw size={17} /> 刷新</button></div>
      {detailError ? <p className="form-error" role="alert">{detailError}</p> : null}{loading ? <p className="quiet-copy">正在打开行程…</p> : null}
      {trips.length ? <div className="trip-card-grid">{trips.map((trip, index) => <button className="trip-card" key={trip.id} onClick={() => open(trip.id)}><TripCover trip={trip} index={index} /><div className="trip-card-body"><span className="trip-card-status">{STATUS[trip.status] || '规划中'}</span><h3>{tripTitle(trip)}</h3><p><CalendarDays size={14} />{tripDate(trip)}</p><span className="trip-card-link">查看行程 <ChevronRight size={16} /></span></div></button>)}</div> : <div className="empty-panel"><Compass /><h3>你的旅程，从这里开始</h3><p>写下想去的地方，第一张行程卡片就会出现。</p></div>}
    </section>
  </div>;
}
