import React, { useMemo, useState } from 'react';
import { Compass, Sparkles, Heart, Database, CircleCheck, ChevronRight } from 'lucide-react';
import { DEFAULT_MEMORY } from '../shared/catalog.mjs';
import { normalizeMemory, parseTripRequest } from '../shared/planner.mjs';
import { initialPlan, readStored, upcomingFriday } from './initial-plan.mjs';
import PlanView from './views/PlanView.jsx';
import MemoryView from './views/MemoryView.jsx';
import SourcesView from './views/SourcesView.jsx';

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
        {view === 'plan' ? <PlanView
          form={{ query, destination, originCity, days, startDate, location, locationState, loading }}
          actions={{ updateQuery, setDestination, setStartDate, setDays, generate, detectLocation, setOriginCity, updateMemory, setMessage, rememberTrip, setSelectedDay }}
          plan={plan} placeCount={placeCount} selectedDay={selectedDay} message={message} memory={memory}
        /> : null}
        {view === 'memory' ? <MemoryView
          memory={memory} destination={destination} updateMemory={updateMemory} setOriginCity={setOriginCity}
          newCity={newCity} setNewCity={setNewCity} addVisitedCity={addVisitedCity}
          newPlace={newPlace} setNewPlace={setNewPlace} addVisitedPlace={addVisitedPlace}
        /> : null}
        {view === 'sources' ? <SourcesView plan={plan} /> : null}
      </main>
    </div>
    <nav className="mobile-nav" aria-label="移动端导航"><NavItem icon={Sparkles} label="规划" active={view === 'plan'} onClick={() => setView('plan')} /><NavItem icon={Heart} label="记忆" active={view === 'memory'} onClick={() => setView('memory')} /><NavItem icon={Database} label="来源" active={view === 'sources'} onClick={() => setView('sources')} /></nav>
  </div>;
}
