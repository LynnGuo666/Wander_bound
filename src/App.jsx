import React, { Suspense, useCallback, useEffect, useState } from 'react';
import { BookOpen, Compass, Settings2, UserRound } from 'lucide-react';
import { DEFAULT_MEMORY, normalizeMemory } from './lib/memory.js';
import { readStored } from './browser-state.mjs';
import QuestionPanel from './workbench/QuestionPanel.jsx';
import { useAgentRun } from './workbench/useAgentRun.js';
import { Toaster } from '@/components/ui/toast';
import './journey.css';

const TripsView = React.lazy(() => import('./views/TripsView.jsx'));
const TravelView = React.lazy(() => import('./views/TravelView.jsx'));
const MemoryView = React.lazy(() => import('./views/MemoryView.jsx'));
const SettingsView = React.lazy(() => import('./views/SettingsView.jsx'));
const NAV = [['trips', Compass, '行程'], ['travel', BookOpen, '旅途'], ['profile', UserRound, '我的'], ['settings', Settings2, '设置']];

function readMediaToken() {
  try { return sessionStorage.getItem('travel-media-token') || ''; } catch { return ''; }
}

export default function App() {
  const [view, setView] = useState('trips');
  const [trips, setTrips] = useState([]);
  const [tripError, setTripError] = useState('');
  const [memory, setMemory] = useState(() => normalizeMemory(readStored('travel-memory-v1', DEFAULT_MEMORY)));
  const [form, setForm] = useState({ query: '', originCity: '', destination: '', days: '', startDate: '' });
  const [mediaToken, setMediaToken] = useState(readMediaToken);
  const [health, setHealth] = useState(null);
  const [newCity, setNewCity] = useState('');
  const [newPlace, setNewPlace] = useState('');
  const { events, plan, question, tripId, error, running, run, answerQuestion, openTrip, reviseTrip, cancel } = useAgentRun();

  const refreshTrips = useCallback(async () => {
    try {
      const response = await fetch('/api/trips');
      if (!response.ok) throw new Error('行程读取失败');
      const result = await response.json();
      setTrips(result.trips || []); setTripError('');
    } catch (reason) { setTripError(reason.message || '行程读取失败'); }
  }, []);
  const refreshHealth = useCallback(() => {
    fetch('/api/health').then(response => response.json()).then(setHealth).catch(() => setHealth({ ok: false }));
  }, []);
  useEffect(() => { refreshTrips(); refreshHealth(); }, [refreshTrips, refreshHealth]);
  useEffect(() => { if (tripId && !running) refreshTrips(); }, [tripId, running, plan, refreshTrips]);

  function update(field, value) { setForm(previous => ({ ...previous, [field]: value })); }
  function updateMemory(patch) {
    setMemory(previous => {
      const next = normalizeMemory({ ...previous, ...patch });
      try { localStorage.setItem('travel-memory-v1', JSON.stringify(next)); } catch { /* Keep this session usable. */ }
      return next;
    });
  }
  function updateMediaToken(value) {
    setMediaToken(value);
    try { if (value) sessionStorage.setItem('travel-media-token', value); else sessionStorage.removeItem('travel-media-token'); } catch { /* Session-only fallback. */ }
  }
  function addVisitedCity() {
    const name = newCity.trim().replace(/市$/, '');
    if (name) { updateMemory({ visitedCities: [...new Set([...memory.visitedCities, name])] }); setNewCity(''); }
  }
  function addVisitedPlace() {
    const name = newPlace.trim();
    if (name) { updateMemory({ visitedPlaces: [...memory.visitedPlaces, { id: `manual-${Date.now()}`, name, city: form.destination }] }); setNewPlace(''); }
  }

  return <div className="travel-app">
    <header className="site-header"><div className="header-inner"><button className="brand" onClick={() => setView('trips')} aria-label="行驿，返回行程"><span className="brand-mark"><Compass size={23} strokeWidth={1.8} /></span><span><strong>行驿</strong><small>TRAVEL STORIES</small></span></button>
      <nav className="primary-nav" aria-label="主导航">{NAV.map(([id, Icon, label]) => <button key={id} type="button" className={view === id ? 'active' : ''} aria-current={view === id ? 'page' : undefined} onClick={() => setView(id)}><Icon size={18} strokeWidth={1.8} /><span>{label}</span></button>)}</nav>
      <span className={`connection-indicator ${health?.ok ? 'online' : ''}`} title={health?.ok ? '规划服务已连接' : '规划服务未连接'}><i />{health?.ok ? '旅程已就绪' : '连接中'}</span>
    </div></header>
    <main className="app-main" id="main-content"><Suspense fallback={<div className="loading-page">正在打开旅程…</div>}>
      {view === 'trips' ? <TripsView trips={trips} refreshTrips={refreshTrips} currentTripId={tripId} currentPlan={plan} form={form} update={update} onGenerate={() => run({ ...form, memory })} events={events} error={error || tripError} running={running} onCancel={cancel} onOpenTrip={openTrip} onRevise={reviseTrip} token={mediaToken} /> : null}
      {view === 'travel' ? <TravelView trips={trips} token={mediaToken} onOpenSettings={() => setView('settings')} /> : null}
      {view === 'profile' ? <MemoryView memory={memory} trips={trips} destination={form.destination} updateMemory={updateMemory} setOriginCity={value => update('originCity', value)} newCity={newCity} setNewCity={setNewCity} addVisitedCity={addVisitedCity} newPlace={newPlace} setNewPlace={setNewPlace} addVisitedPlace={addVisitedPlace} /> : null}
      {view === 'settings' ? <SettingsView onSaved={refreshHealth} mediaToken={mediaToken} onMediaTokenChange={updateMediaToken} health={health} /> : null}
    </Suspense></main>
    <footer className="site-footer"><span>行驿 · 留下每一次出发</span><span>你的日记保存在当前浏览器，照片保存在私有相册。</span></footer>
    <Toaster viewportClassName="max-w-2xl" />
    <QuestionPanel question={question} onAnswer={answerQuestion} running={running} />
  </div>;
}
