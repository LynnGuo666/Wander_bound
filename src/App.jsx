import React, { Suspense, useEffect, useMemo, useState } from 'react';
import { Activity, Compass, Database, Heart, MapPinned, Server, ShieldCheck } from 'lucide-react';
import { DEFAULT_MEMORY } from '../shared/catalog.mjs';
import { normalizeMemory, parseTripRequest } from '../shared/planner.mjs';
import { readStored, upcomingFriday } from './browser-state.mjs';
import JourneyForm from './workbench/JourneyForm.jsx';
import CredentialsPanel from './workbench/CredentialsPanel.jsx';
import AgentTimeline from './workbench/AgentTimeline.jsx';
import PlanSnapshot from './workbench/PlanSnapshot.jsx';
import { useAgentRun } from './workbench/useAgentRun.js';

const PlanView = React.lazy(() => import('./views/PlanView.jsx'));
const MemoryView = React.lazy(() => import('./views/MemoryView.jsx'));
const SourcesView = React.lazy(() => import('./views/SourcesView.jsx'));
const tabs = [ ['debug', Activity, 'Agent Debug'], ['plan', MapPinned, '完整行程'], ['memory', Heart, '旅行记忆'], ['sources', Database, '数据来源'] ];

export default function App() {
  const [view, setView] = useState('debug');
  const [memory, setMemory] = useState(() => normalizeMemory(readStored('travel-memory-v1', DEFAULT_MEMORY)));
  const [form, setForm] = useState(() => ({ query: '我想去深圳玩 3 天，机票尽量便宜，但不要红眼航班。', originCity: memory.homeCity || '', destination: '深圳', days: 3, startDate: upcomingFriday() }));
  const [credentials, setCredentials] = useState({});
  const [health, setHealth] = useState(null);
  const [selectedDay, setSelectedDay] = useState(null);
  const [newCity, setNewCity] = useState('');
  const [newPlace, setNewPlace] = useState('');
  const [message, setMessage] = useState('');
  const { events, plan, error, running, run, cancel } = useAgentRun();
  const placeCount = useMemo(() => plan?.itinerary?.reduce((sum, day) => sum + day.stops.length, 0) || 0, [plan]);

  useEffect(() => { fetch('/api/health').then(response => response.json()).then(setHealth).catch(() => setHealth({ ok: false })); }, []);
  function update(field, value) {
    setForm(previous => {
      const next = { ...previous, [field]: value };
      if (field === 'query') {
        const parsed = parseTripRequest(value);
        if (parsed.destination) next.destination = parsed.destination;
        if (parsed.days) next.days = parsed.days;
      }
      return next;
    });
  }
  function updateMemory(patch) {
    setMemory(previous => {
      const next = normalizeMemory({ ...previous, ...patch });
      localStorage.setItem('travel-memory-v1', JSON.stringify(next));
      return next;
    });
  }
  function generate() {
    setView('debug'); setMessage('');
    run({ ...form, memory, credentials: Object.fromEntries(Object.entries(credentials).filter(([, value]) => value.trim()).map(([name, value]) => [name, value.trim()])) });
  }
  function rememberTrip() {
    if (!plan) return;
    const visitedPlaces = [...memory.visitedPlaces];
    for (const day of plan.itinerary) for (const stop of day.stops) {
      if (!visitedPlaces.some(place => place.id === stop.id)) visitedPlaces.push({ id: stop.id, name: stop.name, city: plan.destination });
    }
    updateMemory({ visitedCities: [...new Set([...memory.visitedCities, plan.destination])], visitedPlaces });
    setMessage(`已记录 ${plan.destination} 的 ${placeCount} 个地点。`);
  }
  function addVisitedCity() {
    const city = newCity.trim().replace(/市$/, '');
    if (city) { updateMemory({ visitedCities: [...new Set([...memory.visitedCities, city])] }); setNewCity(''); }
  }
  function addVisitedPlace() {
    const name = newPlace.trim();
    if (name) { updateMemory({ visitedPlaces: [...memory.visitedPlaces, { id: `manual-${Date.now()}`, name, city: form.destination }] }); setNewPlace(''); }
  }
  return <div className="wb-app">
    <aside className="wb-sidebar"><div className="wb-brand"><span><Compass size={22} /></span><div><strong>行驿</strong><small>WAYSTATION / SPARK</small></div></div><div className="wb-nav-label">MISSION CONTROL</div><nav aria-label="主导航">{tabs.map(([id, Icon, label]) => <button type="button" key={id} className={view === id ? 'active' : ''} onClick={() => setView(id)}><Icon size={17} /><span>{label}</span>{id === 'debug' && running ? <i className="wb-nav-pulse" /> : null}</button>)}</nav><div className="wb-sidebar-bottom"><div className="wb-node"><span className={health?.ok ? 'wb-node-light online' : 'wb-node-light'} /><div><strong>DGX SPARK / 82</strong><small>{health?.ok ? 'Agent API 已连接' : '检查连接中'}</small></div></div><p>规划执行与媒体处理运行在 Spark 节点。敏感密钥按请求传递。</p></div></aside>
    <div className="wb-main"><header className="wb-header"><div><span className="wb-header-kicker">DEEPSLEEP–TT / TRAVEL AGENT</span><strong>{tabs.find(tab => tab[0] === view)?.[2]}</strong></div><div className="wb-header-status"><Server size={14} /><span>{health?.ok ? 'SPARK ONLINE' : 'SPARK OFFLINE'}</span><i className={health?.ok ? 'online' : ''} /></div></header>
      <main className="wb-content">{view === 'debug' ? <><div className="wb-hero"><div><span className="wb-hero-kicker">AGENT OPERATIONS · LIVE TRACE</span><h1>从一句想法，<br /><em>到一段真实旅程。</em></h1><p>输入旅程，观察模型按阶段选择工具、验证地点并完成行程。</p></div><div className="wb-hero-stamp"><span>NODE 032</span><strong>SPARK</strong><small>LOCAL INTELLIGENCE</small></div></div><div className="wb-grid"><div className="wb-stack"><JourneyForm form={form} update={update} onSubmit={generate} running={running} /><CredentialsPanel credentials={credentials} setCredentials={setCredentials} serverModelConfigured={health?.model?.configured} /></div><AgentTimeline events={events} running={running} error={error} plan={plan} onCancel={cancel} /><PlanSnapshot plan={plan} onDetails={() => setView('plan')} /></div><div className="wb-footer-note"><ShieldCheck size={15} /> 调试记录只显示可验证的执行事件，不包含密钥、工具原始返回或模型隐藏思维链。</div></> : null}
        <Suspense fallback={<div className="wb-loading">正在加载视图…</div>}>
          {view === 'plan' ? plan ? <PlanView detailOnly form={{ ...form, loading: running }} actions={{ updateQuery: value => update('query', value), setDestination: value => update('destination', value), setStartDate: value => update('startDate', value), setDays: value => update('days', value), generate, detectLocation: () => {}, setOriginCity: value => update('originCity', value), updateMemory, setMessage, rememberTrip, setSelectedDay }} plan={plan} placeCount={placeCount} selectedDay={selectedDay} message={message} memory={memory} /> : <div className="wb-await"><MapPinned size={35} /><h2>还没有真实行程</h2><p>先在 Agent Debug 执行一次规划。</p><button type="button" onClick={() => setView('debug')}>前往调试台</button></div> : null}
          {view === 'memory' ? <MemoryView memory={memory} destination={form.destination} updateMemory={updateMemory} setOriginCity={value => update('originCity', value)} newCity={newCity} setNewCity={setNewCity} addVisitedCity={addVisitedCity} newPlace={newPlace} setNewPlace={setNewPlace} addVisitedPlace={addVisitedPlace} /> : null}
          {view === 'sources' ? <SourcesView plan={plan} /> : null}
        </Suspense>
      </main>
    </div>
    <nav className="wb-mobile-nav" aria-label="移动端导航">{tabs.map(([id, Icon, label]) => <button type="button" key={id} className={view === id ? 'active' : ''} onClick={() => setView(id)}><Icon size={18} /><span>{label.replace('Agent ', '')}</span></button>)}</nav>
  </div>;
}
