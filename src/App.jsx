import React, { useMemo, useState } from 'react';
import { Compass, MapPinned, Sparkles, Plane, TrainFront, MapPin, CalendarDays, ArrowUpRight, Clock3, Star, Wallet, Heart, Navigation, Settings2, ChevronRight, RotateCcw, Hotel, ShieldCheck, Database, CircleCheck, CircleAlert, LoaderCircle, LocateFixed, Plus, X, SlidersHorizontal, BookmarkCheck } from 'lucide-react';
import TripMap from './TripMap.jsx';
import { CITY_CATALOG, DEFAULT_MEMORY } from '../shared/catalog.mjs';
import { assemblePlan, normalizeMemory, parseTripRequest } from '../shared/planner.mjs';

function upcomingFriday() {
  const date = new Date();
  date.setDate(date.getDate() + ((5 - date.getDay() + 7) % 7 || 7));
  return date.toISOString().slice(0, 10);
}

function readStored(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}

function dateLabel(iso) {
  if (!iso) return '';
  return new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' }).format(new Date(`${iso}T12:00:00`));
}

function money(amount, currency = 'CNY') {
  if (!Number.isFinite(Number(amount))) return '待查询';
  return new Intl.NumberFormat('zh-CN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(amount));
}

function timeOnly(iso) { return iso ? iso.slice(11, 16) : '--:--'; }

const SAMPLE_STATUS = {
  amap: { configured: false, label: '高德地点与路线', result: '未配置' },
  dida: { configured: false, label: '道旅酒店', result: '未配置' },
  duffel: { configured: false, label: 'Duffel 航班', result: '未配置' },
  tuniu: { configured: false, label: '途牛 MCP CLI' },
  flyai: { configured: false, label: '飞猪 FlyAI Skill/CLI' },
  trip: { configured: false, label: '携程景区合作方接口' },
  reviews: { configured: false, label: '大众点评/美团评论 MCP' },
};

function initialPlan(memory) {
  return assemblePlan({ destination: '深圳', originCity: memory.homeCity, startDate: upcomingFriday(), days: 3, memory, places: [], providerStatus: SAMPLE_STATUS });
}

function Pill({ children, icon: Icon, className = '' }) {
  return <span className={`pill ${className}`}>{Icon ? <Icon size={14} /> : null}{children}</span>;
}

function SectionHeading({ eyebrow, title, note, action }) {
  return <div className="section-heading"><div><div className="eyebrow">{eyebrow}</div><h2>{title}</h2>{note ? <p>{note}</p> : null}</div>{action}</div>;
}

function NavItem({ icon: Icon, label, active, onClick, count }) {
  return <button type="button" className={`nav-item ${active ? 'active' : ''}`} onClick={onClick}><Icon size={20} /><span>{label}</span>{count ? <em>{count}</em> : null}</button>;
}

export default function App() {
  const [memory, setMemory] = useState(() => normalizeMemory(readStored('travel-memory-v1', DEFAULT_MEMORY)));
  const [plan, setPlan] = useState(() => readStored('travel-plan-v1', null) || initialPlan(normalizeMemory(readStored('travel-memory-v1', DEFAULT_MEMORY))));
  const [view, setView] = useState('plan');
  const [query, setQuery] = useState('我想去深圳玩 3 天，机票尽量便宜，但不要红眼航班。');
  const [destination, setDestination] = useState('深圳');
  const [originCity, setOriginCity] = useState(memory.homeCity || '');
  const [days, setDays] = useState(3);
  const [startDate, setStartDate] = useState(upcomingFriday());
  const [location, setLocation] = useState(null);
  const [locationState, setLocationState] = useState('点击后获取当前位置');
  const [selectedDay, setSelectedDay] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [newPlace, setNewPlace] = useState('');
  const [newCity, setNewCity] = useState('');

  const placeCount = useMemo(() => plan?.itinerary?.reduce((sum, day) => sum + day.stops.length, 0) || 0, [plan]);
  const sourcesActive = Object.values(plan?.providerStatus || {}).filter(source => source.configured).length;

  function updateMemory(patch) {
    setMemory(previous => {
      const next = normalizeMemory({ ...previous, ...patch });
      localStorage.setItem('travel-memory-v1', JSON.stringify(next));
      return next;
    });
  }

  function updateQuery(value) {
    setQuery(value);
    const parsed = parseTripRequest(value);
    if (parsed.destination) setDestination(parsed.destination);
    if (parsed.days) setDays(parsed.days);
  }

  function detectLocation() {
    if (!navigator.geolocation) { setLocationState('当前环境不支持定位，请填写出发城市'); return; }
    setLocationState('正在获取位置…');
    navigator.geolocation.getCurrentPosition(
      position => {
        setLocation({ lat: position.coords.latitude, lng: position.coords.longitude });
        setLocationState('坐标已获取 · 配置地点服务后识别城市');
      },
      () => setLocationState('无法获取位置，请填写出发城市'),
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 },
    );
  }

  async function generate() {
    setLoading(true); setMessage('');
    try {
      const response = await fetch('/api/plan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, destination, originCity, days, startDate, location, memory }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || '规划失败');
      setPlan(result);
      localStorage.setItem('travel-plan-v1', JSON.stringify(result));
      if (result.originCity) setOriginCity(result.originCity);
      setSelectedDay(null);
      setView('plan');
      const sourceMessage = result.agentRun?.status === 'completed' ? 'Step 5 Preview 已完成规划' : result.agentRun?.status === 'degraded' ? '模型暂不可用，已用规则生成行程' : 'Step 5 Preview 未配置，已用规则生成行程';
      setMessage(result.locationDetected ? `已识别出发城市：${result.originCity}。${sourceMessage}` : sourceMessage);
    } catch (error) { setMessage(`${error.message}。请确认规划服务正在运行。`); }
    finally { setLoading(false); }
  }

  function rememberTrip() {
    const visitedPlaces = [...memory.visitedPlaces];
    for (const day of plan.itinerary) for (const stop of day.stops) {
      if (!visitedPlaces.some(place => place.id === stop.id)) visitedPlaces.push({ id: stop.id, name: stop.name, city: plan.destination });
    }
    updateMemory({ visitedCities: [...new Set([...memory.visitedCities, plan.destination])], visitedPlaces });
    setMessage(`已记录 ${plan.destination} 的 ${placeCount} 个地点，下次会避开它们。`);
  }

  function addVisitedPlace() {
    const name = newPlace.trim();
    if (!name) return;
    updateMemory({ visitedPlaces: [...memory.visitedPlaces, { id: `manual-${Date.now()}`, name, city: destination }] });
    setNewPlace('');
  }

  function addVisitedCity() {
    const city = newCity.trim().replace(/市$/, '');
    if (!city) return;
    updateMemory({ visitedCities: [...new Set([...memory.visitedCities, city])] });
    setNewCity('');
  }

  const bestFlight = plan?.flights?.find(flight => !flight.redEye);
  const bestTrain = plan?.trains?.find(train => !train.redEye);

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Compass size={24} strokeWidth={2.3} /></span><div><strong>旅忆</strong><small>TRAVEL, REMEMBERED</small></div></div>
      <div className="sidebar-title">WORKSPACE</div>
      <nav aria-label="主导航">
        <NavItem icon={Sparkles} label="智能规划" active={view === 'plan'} onClick={() => setView('plan')} />
        <NavItem icon={Heart} label="旅行记忆" active={view === 'memory'} onClick={() => setView('memory')} count={memory.visitedPlaces.length || undefined} />
        <NavItem icon={Database} label="数据来源" active={view === 'sources'} onClick={() => setView('sources')} />
      </nav>
      <div className="sidebar-spacer" />
      <div className="sidebar-card"><span className="sidebar-card-icon"><Sparkles size={18} /></span><h3>每一次出发<br />都值得全新发现</h3><p>记住你喜欢的，也记住你已经看过的。</p></div>
      <div className="sidebar-foot"><span className="avatar">旅</span><div><strong>本地记忆</strong><small>只保存在此设备</small></div><CircleCheck size={16} /></div>
    </aside>

    <div className="main-area">
      <header className="topbar"><div className="breadcrumb">工作台 <ChevronRight size={14} /> <strong>{view === 'plan' ? '智能规划' : view === 'memory' ? '旅行记忆' : '数据来源'}</strong></div><div className="topbar-right"><span className="live-dot" /> {sourcesActive} 个实时源已连接 <span className="topbar-divider" /> <span className="topbar-date">{new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric' }).format(new Date())}</span></div></header>

      <main className="content">
        {view === 'plan' ? <>
          <section className="hero">
            <div className="hero-copy"><Pill icon={Sparkles} className="hero-pill">更懂你的旅行 Agent</Pill><h1>下一站，<em>去发现新的。</em></h1><p>说出你想去的地方。我们结合你的出发位置、偏好和过往足迹，安排一段真正属于你的旅程。</p></div>
            <div className="hero-art" aria-hidden="true"><div className="sun" /><div className="orbit orbit-a" /><div className="orbit orbit-b" /><div className="hero-plane"><Plane size={32} fill="currentColor" /></div><div className="hero-pin"><MapPin size={22} fill="currentColor" /></div><div className="hero-caption">A NEW ROUTE<br />AWAITS YOU ↗</div></div>
          </section>

          <section className="composer" aria-label="创建旅行计划">
            <div className="composer-top"><div className="composer-icon"><Sparkles size={18} /></div><strong>想去哪里走走？</strong><span>自然语言规划</span></div>
            <textarea value={query} onChange={event => updateQuery(event.target.value)} placeholder="例如：我想去深圳玩 3 天，坐飞机，票价优先但不要红眼航班…" rows={2} />
            <div className="composer-controls">
              <label><MapPin size={16} /><span>目的地</span><input aria-label="目的地" value={destination} onChange={event => setDestination(event.target.value)} /></label>
              <label><CalendarDays size={16} /><span>出发日期</span><input aria-label="出发日期" type="date" value={startDate} onChange={event => setStartDate(event.target.value)} /></label>
              <label><Clock3 size={16} /><span>天数</span><select aria-label="旅行天数" value={days} onChange={event => setDays(Number(event.target.value))}>{[1, 2, 3, 4, 5, 6, 7].map(value => <option key={value} value={value}>{value} 天</option>)}</select></label>
              <button type="button" className="primary-button" onClick={generate} disabled={loading}>{loading ? <LoaderCircle size={18} className="spin" /> : <Sparkles size={18} />}{loading ? '正在规划' : '生成行程'}</button>
            </div>
          </section>
          <div className="origin-strip"><div><LocateFixed size={18} /><button type="button" onClick={detectLocation}>{locationState}</button>{location ? <small>{location.lat.toFixed(3)}, {location.lng.toFixed(3)}</small> : null}</div><label>或手动输入出发城市 <input aria-label="出发城市" value={originCity} onChange={event => { setOriginCity(event.target.value); updateMemory({ homeCity: event.target.value }); }} placeholder="如：上海" /></label></div>
          {message ? <div className="feedback" role="status"><CircleAlert size={16} />{message}<button type="button" onClick={() => setMessage('')} aria-label="关闭消息"><X size={15} /></button></div> : null}

          <section className="overview"><div><div className="eyebrow">YOUR NEXT JOURNEY</div><h2>{plan.destination}<span> / {plan.days} 天的全新探索</span></h2><p>{plan.intro}</p><div className="overview-pills"><Pill icon={CalendarDays}>{dateLabel(plan.startDate)} — {dateLabel(plan.endDate)}</Pill><Pill icon={MapPin}>{placeCount} 个地点</Pill><Pill icon={RotateCcw}>{plan.revisit ? '再次探索 · 已排除到访地点' : '初次探索'}</Pill></div></div><div className="overview-number"><strong>{String(plan.days).padStart(2, '0')}</strong><span>DAYS<br />AWAY</span></div></section>

          <div className="two-column">
            <section className="transport-section card-surface"><SectionHeading eyebrow="01 · GETTING THERE" title="怎么去，才符合你的节奏" note={plan.originCity ? `从 ${plan.originCity} 出发 · ${plan.transportPreference === 'flight' ? '优先飞机，价格优先且避开红眼' : '优先高铁'}` : '请定位或填写出发城市，以查询真实交通方案。'} />
              {bestFlight ? <div className="flight-card"><div className="flight-card-head"><Pill icon={Plane}>符合偏好</Pill><span>实时查询 · {bestFlight.provider}</span></div><div className="flight-times"><div><strong>{timeOnly(bestFlight.departureAt)}</strong><small>{bestFlight.origin}</small></div><div className="flight-path"><Plane size={18} /><span /></div><div><strong>{timeOnly(bestFlight.arrivalAt)}</strong><small>{bestFlight.destination}</small></div><b>{bestFlight.totalPrice === null ? '价格待查' : money(bestFlight.totalPrice, bestFlight.currency)}</b></div><div className="flight-meta">{bestFlight.airline} {bestFlight.flightNumber} · {bestFlight.stops ? `${bestFlight.stops} 次中转` : '直飞'} · {bestFlight.priceBasis || '报价条件待核'} · 最终价格以预订时验价为准 {bestFlight.bookingUrl ? <a href={bestFlight.bookingUrl} target="_blank" rel="noreferrer">查看供应商 <ArrowUpRight size={14} /></a> : null}</div></div> : <div className="empty-offer"><span className="empty-offer-icon"><Plane size={22} /></span><div><strong>白天航班 · 低价优先</strong><p>{plan.originCity ? '已记录你的偏好。本次没有取得可核实的航班报价。' : '填写出发城市后可确定机场与交通方案。'}</p></div><span className="pending-badge">暂无实时报价</span></div>}
              <div className="transport-secondary"><TrainFront size={19} /><div><strong>{bestTrain ? `${bestTrain.trainNumber || '火车'} · ${timeOnly(bestTrain.departureAt)} → ${timeOnly(bestTrain.arrivalAt)}` : '高铁作为备选'}</strong><small>{bestTrain ? `${bestTrain.provider} · ${bestTrain.origin || '出发站'} → ${bestTrain.destination || '到达站'} · ${bestTrain.priceBasis || '参考价'}` : '本次没有取得可核实的火车票报价'}</small></div><span>{bestTrain ? bestTrain.totalPrice === null ? '价格待查' : money(bestTrain.totalPrice, bestTrain.currency) : '待查询'}</span>{bestTrain?.bookingUrl ? <a href={bestTrain.bookingUrl} target="_blank" rel="noreferrer" aria-label="查看火车票供应商页面"><ArrowUpRight size={16} /></a> : null}</div>
            </section>

            <section className="stay-section card-surface"><SectionHeading eyebrow="02 · WHERE TO STAY" title="住在行程的中心" note="结合游玩地点、品牌偏好与每晚预算选择住宿区域。" />
              <div className="stay-area"><div className="stay-area-icon"><Hotel size={22} /></div><div><span>建议住宿区域</span><strong>{plan.stayArea?.name || `${plan.destination}市区`}</strong><p>{plan.stayArea?.note || '酒店数据源接入后，可结合行程计算适合的住宿位置。'}</p></div></div>
              <div className="stay-preference"><div><Heart size={15} />偏好品牌：{plan.hotelBrands?.join('、') || '未设置'}</div><div><Wallet size={15} />每晚预算：{money(memory.hotelNightBudget)}</div></div>
              {plan.hotels?.length ? <div className="hotel-offers">{plan.hotels.slice(0, 3).map(hotel => <div className="hotel-offer" key={hotel.id}><div><strong>{hotel.name}</strong><small>{hotel.provider} · {hotel.address || '地址待核实'}</small></div><span>{hotel.displayPrice ? `${money(hotel.displayPrice, hotel.currency)} · ${hotel.priceBasis}` : '价格待核实'}</span>{hotel.bookingUrl ? <a href={hotel.bookingUrl} target="_blank" rel="noreferrer" aria-label={`查看 ${hotel.name}`}><ArrowUpRight size={16} /></a> : null}</div>)}</div> : <div className="stay-placeholder">酒店实时库存未连接，当前建议基于地点分布，未虚构房价。</div>}
            </section>
          </div>

          <div className="journey-grid"><section className="itinerary-section"><SectionHeading eyebrow="03 · THE ITINERARY" title="让每一天都有新发现" note={plan.skippedPlaces?.length ? `已避开你去过的：${plan.skippedPlaces.join('、')}` : '同一区域优先串联，减少路上折返。'} action={<button type="button" className="text-button" onClick={rememberTrip}><BookmarkCheck size={17} /> 完成后记住这趟旅程</button>} />
            <div className="day-list">{plan.itinerary?.map(day => <article className="day-card" key={day.day}><div className="day-heading"><span>DAY {String(day.day).padStart(2, '0')}</span><div><strong>{day.title}</strong><small>{dateLabel(day.date)}</small></div><button type="button" onClick={() => setSelectedDay(selectedDay === day.day ? null : day.day)} aria-label={`在地图查看第 ${day.day} 天`}><MapPinned size={17} /></button></div><div className="stop-list">{day.stops.length ? day.stops.map((stop, index) => <div className="stop" key={stop.id}><div className="stop-time">{stop.start}</div><div className="stop-rail"><span />{index < day.stops.length - 1 ? <i /> : null}</div><div className="stop-body"><div className="stop-title"><strong>{stop.name}</strong><span>{stop.category}</span></div><p>{stop.description}</p><div className="stop-meta"><span><Clock3 size={13} /> 游玩约 {stop.duration} 分钟</span>{stop.travelMinutes ? <span><Navigation size={13} /> 路程约 {stop.travelMinutes} 分钟 · {stop.travelSource}</span> : null}{stop.rating ? <span><Star size={13} /> {stop.rating} · {stop.ratingSource}</span> : <span>暂无可信评分</span>}</div></div></div>) : <div className="empty-day">{day.title === '抵达与入住' ? '抵达时间较晚，留给进城和入住，不再安排景点。' : '还没有可核实的新地点，请接入地点源后重新规划。'}</div>}</div></article>)}</div>
            {plan.attractionOffers?.length ? <div className="hotel-offers">{plan.attractionOffers.map((offer, index) => <div className="hotel-offer" key={`${offer.provider}-${offer.placeId}-${index}`}><div><strong>{offer.name} · {offer.productName || '景区详情'}</strong><small>{offer.provider} · {offer.startingPrice ? `起价对应 ${offer.priceDate || '未知日期'}，出游日价格待核` : offer.priceDate ? `标注日期 ${offer.priceDate}` : '日期请到供应商页面核实'}</small></div><span>{offer.price === null ? '价格请到平台查看' : `${money(offer.price, offer.currency)}${offer.startingPrice ? '起' : ''}`}</span>{offer.bookingUrl ? <a href={offer.bookingUrl} target="_blank" rel="noreferrer" aria-label={`查看 ${offer.name} 门票`}><ArrowUpRight size={16} /></a> : null}</div>)}</div> : null}
          </section><aside className="map-column"><div className="map-sticky"><div className="map-title"><div><span>路线地图</span><strong>{plan.destination} · {placeCount} 站</strong></div><MapPinned size={19} /></div><TripMap itinerary={plan.itinerary} selectedDay={selectedDay} onSelectDay={setSelectedDay} /><div className="map-note"><Navigation size={16} /> 地图连线表示地点顺序；每段交通时间以旁边标注的来源为准。</div><div className="map-footer"><span className="map-legend" /><span>按天查看行程</span><span className="map-updated">更新于 {new Date(plan.generatedAt).toLocaleDateString('zh-CN')}</span></div></div></aside></div>
        </> : null}

        {view === 'memory' ? <section className="subpage"><div className="eyebrow">YOUR TRAVEL MEMORY</div><h1>让下一次，<em>更像你。</em></h1><p className="subpage-intro">偏好和足迹保存在此设备。规划时会避开已到访地点，并优先选择你喜欢的交通与酒店。</p><div className="memory-grid"><div className="settings-card"><div className="settings-heading"><Plane size={19} /><h2>出行偏好</h2></div><label>常用出发城市<input value={memory.homeCity} onChange={event => { updateMemory({ homeCity: event.target.value }); setOriginCity(event.target.value); }} placeholder="如：上海" /></label><label>优先交通方式<select value={memory.transportPreference} onChange={event => updateMemory({ transportPreference: event.target.value })}><option value="flight">飞机</option><option value="train">高铁</option></select></label><label className="switch-row"><span>价格优先</span><input type="checkbox" checked={memory.pricePriority} onChange={event => updateMemory({ pricePriority: event.target.checked })} /></label><label className="switch-row"><span>避开红眼与隔夜航班</span><input type="checkbox" checked={memory.avoidRedEye} onChange={event => updateMemory({ avoidRedEye: event.target.checked })} /></label></div><div className="settings-card"><div className="settings-heading"><Hotel size={19} /><h2>住宿喜好</h2></div><label>喜欢的酒店品牌<input value={memory.hotelBrands.join('、')} onChange={event => updateMemory({ hotelBrands: event.target.value.split(/[、,，]/).map(item => item.trim()).filter(Boolean) })} placeholder="汉庭、希尔顿" /></label><label>每晚预算（人民币）<input type="number" min="0" step="50" value={memory.hotelNightBudget} onChange={event => updateMemory({ hotelNightBudget: Number(event.target.value) })} /></label><div className="settings-note"><ShieldCheck size={16} /> 本地保存，只有规划请求会携带偏好；无需创建账号。</div></div><div className="settings-card memory-span"><div className="settings-heading"><MapPinned size={19} /><h2>去过的地方</h2></div><div className="visited-groups"><div><h3>城市</h3><div className="chips">{memory.visitedCities.length ? memory.visitedCities.map(city => <span key={city}>{city}<button type="button" aria-label={`移除 ${city}`} onClick={() => updateMemory({ visitedCities: memory.visitedCities.filter(item => item !== city) })}><X size={13} /></button></span>) : <small>还没有记录</small>}</div><div className="add-row"><input value={newCity} onChange={event => setNewCity(event.target.value)} onKeyDown={event => event.key === 'Enter' && addVisitedCity()} placeholder="添加已去过的城市" /><button type="button" onClick={addVisitedCity}><Plus size={16} /> 添加</button></div></div><div><h3>地点</h3><div className="chips">{memory.visitedPlaces.length ? memory.visitedPlaces.map(place => <span key={place.id}>{place.name}<button type="button" aria-label={`移除 ${place.name}`} onClick={() => updateMemory({ visitedPlaces: memory.visitedPlaces.filter(item => item.id !== place.id) })}><X size={13} /></button></span>) : <small>标记一次已完成的旅程，这里就会自动记录。</small>}</div><div className="add-row"><input value={newPlace} onChange={event => setNewPlace(event.target.value)} onKeyDown={event => event.key === 'Enter' && addVisitedPlace()} placeholder={`添加${destination}已去过的地点`} /><button type="button" onClick={addVisitedPlace}><Plus size={16} /> 添加</button></div></div></div></div></div></section> : null}

        {view === 'sources' ? <section className="subpage"><div className="eyebrow">DATA & TRUST</div><h1>每一条建议，<em>都有出处。</em></h1><p className="subpage-intro">查询状态由当前服务配置决定。没有价格的来源不会进入“最低价”比较，也不会生成示例报价。</p><div className="sources-grid">{Object.entries(plan.providerStatus || SAMPLE_STATUS).map(([key, source]) => <div className="source-card" key={key}><div className={`source-icon ${source.configured ? 'connected' : ''}`}>{source.configured ? <CircleCheck size={20} /> : <Database size={20} />}</div><div><strong>{source.label}</strong><p>{source.result === 'ok' ? `已连接 · 本次查询成功${source.mode === 'trial' ? ' · 体验模式' : ''}` : source.configured ? `已配置 · ${source.result || '等待查询'}` : source.result || '尚未开通真实数据'}</p></div><span className={source.configured ? 'source-on' : 'source-off'}>{source.configured ? '已接入' : '待接入'}</span></div>)}</div><div className="data-policy"><SlidersHorizontal size={20} /><div><strong>比价接入原则</strong><p>航班和火车票可从飞猪 Skill/CLI、途牛 MCP 查询；道旅提供酒店候选。只有供应商给出完整数字价格时才排序。不同日期、舱位、税费与退改条件的结果会分别标注，预订前需在平台验价。</p></div></div></section> : null}
      </main>
    </div>
    <nav className="mobile-nav" aria-label="移动端导航"><NavItem icon={Sparkles} label="规划" active={view === 'plan'} onClick={() => setView('plan')} /><NavItem icon={Heart} label="记忆" active={view === 'memory'} onClick={() => setView('memory')} /><NavItem icon={Database} label="来源" active={view === 'sources'} onClick={() => setView('sources')} /></nav>
  </div>;
}
