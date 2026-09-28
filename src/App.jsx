import React, { Suspense, useCallback, useEffect, useState } from 'react';
import { BookOpen, Compass, Settings2, UserRound } from 'lucide-react';
import { DEFAULT_MEMORY, normalizeMemory } from './lib/memory.js';
import { readStored } from './browser-state.mjs';
import QuestionPanel from './workbench/QuestionPanel.jsx';
import { useAgentRun } from './workbench/useAgentRun.js';
import { Toaster } from '@/components/ui/toast';
import { apiFetch, sessionToken } from './lib/api.js';
import AuthGate from './views/AuthGate.jsx';
import './journey.css';

const TripsView = React.lazy(() => import('./views/TripsView.jsx'));
const TravelView = React.lazy(() => import('./views/TravelView.jsx'));
const MemoryView = React.lazy(() => import('./views/MemoryView.jsx'));
const SettingsView = React.lazy(() => import('./views/SettingsView.jsx'));
const DebugView = React.lazy(() => import('./views/DebugView.jsx'));
const NAV = [['trips', Compass, '行程'], ['travel', BookOpen, '旅途'], ['profile', UserRound, '我的'], ['settings', Settings2, '设置']];

function Navigation({ view, navigate, className }) {
  return <nav className={className} aria-label="主导航">{NAV.map(([id, Icon, label]) => {
    const active = view === id || (view === 'debug' && id === 'settings');
    return <button key={id} type="button" className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} onClick={() => navigate(id)}><Icon size={20} strokeWidth={active ? 2.2 : 1.9} aria-hidden="true" /><span>{label}</span></button>;
  })}</nav>;
}

export default function App() {
  const [session, setSession] = useState(sessionToken);
  const [user, setUser] = useState(null);
  const [view, setView] = useState(() => new URLSearchParams(window.location.search).has('debug') ? 'debug' : 'trips');
  const [trips, setTrips] = useState([]);
  const [tripError, setTripError] = useState('');
  const [memory, setMemory] = useState(DEFAULT_MEMORY);
  const [form, setForm] = useState({ query: '', originCity: '', destination: '', days: '', startDate: '' });
  const [health, setHealth] = useState(null);
  const [newCity, setNewCity] = useState('');
  const [newPlace, setNewPlace] = useState('');
  const { events, plan, question, tripId, error, running, run, answerQuestion, openTrip, reviseTrip, cancel, reset } = useAgentRun();

  const refreshTrips = useCallback(async () => {
    try {
      if (!sessionToken()) return;
      const response = await apiFetch('/api/trips');
      if (!response.ok) throw new Error('行程读取失败');
      const result = await response.json();
      setTrips(result.trips || []); setTripError('');
    } catch (reason) { setTripError(reason.message || '行程读取失败'); }
  }, []);
  const refreshHealth = useCallback(() => {
    fetch('/api/health').then(response => response.json()).then(setHealth).catch(() => setHealth({ ok: false }));
  }, []);
  useEffect(() => { if (session) { refreshTrips(); apiFetch('/api/auth/me').then(r => r.ok ? r.json() : Promise.reject()).then(r => { setUser(r.user); setMemory(normalizeMemory(readStored(`travel-memory-v1:${r.user.id}`, DEFAULT_MEMORY))); }).catch(() => { try { sessionStorage.removeItem('travel-session'); } catch {} setSession(''); }); } refreshHealth(); }, [session, refreshTrips, refreshHealth]);
  useEffect(() => { if (tripId && !running) refreshTrips(); }, [tripId, running, plan, refreshTrips]);

  function update(field, value) { setForm(previous => ({ ...previous, [field]: value })); }
  function updateMemory(patch) {
    setMemory(previous => {
      const next = normalizeMemory({ ...previous, ...patch });
      try { localStorage.setItem(`travel-memory-v1:${user?.id || 'unknown'}`, JSON.stringify(next)); } catch { /* Keep this session usable. */ }
      return next;
    });
  }
  function authenticate(result) { sessionStorage.setItem('travel-session', result.token); setSession(result.token); setUser(result.user); setMemory(normalizeMemory(readStored(`travel-memory-v1:${result.user.id}`, DEFAULT_MEMORY))); }
  async function logout() { try { await apiFetch('/api/auth/logout', { method: 'POST' }); } finally { sessionStorage.removeItem('travel-session'); reset(); setSession(''); setUser(null); setTrips([]); setMemory(DEFAULT_MEMORY); } }
  function navigate(next) {
    const url = new URL(window.location.href);
    if (next === 'debug') url.searchParams.set('debug', '1');
    else url.searchParams.delete('debug');
    window.history.replaceState(null, '', url);
    setView(next);
  }
  function addVisitedCity() {
    const name = newCity.trim().replace(/市$/, '');
    if (name) { updateMemory({ visitedCities: [...new Set([...memory.visitedCities, name])] }); setNewCity(''); }
  }
  function addVisitedPlace() {
    const name = newPlace.trim();
    if (name) { updateMemory({ visitedPlaces: [...memory.visitedPlaces, { id: `manual-${Date.now()}`, name, city: form.destination }] }); setNewPlace(''); }
  }

  if (!session) return <AuthGate onAuthenticated={authenticate} />;
  return <div className="travel-app">
    <header className="site-header"><div className="header-inner"><button className="brand" onClick={() => navigate('trips')} aria-label="行驿，返回行程"><span className="brand-mark"><Compass size={23} strokeWidth={1.8} /></span><span><strong>行驿</strong><small>TRAVEL STORIES</small></span></button>
      <Navigation className="primary-nav" view={view} navigate={navigate} />
      <span className={`connection-indicator ${health?.ok ? 'online' : ''}`} title={health?.ok ? '规划服务已连接' : '规划服务未连接'}><i />{health?.ok ? '旅程已就绪' : '连接中'}</span>
    </div></header>
    <Navigation className="mobile-nav" view={view} navigate={navigate} />
    <main className="app-main" id="main-content"><Suspense fallback={<div className="loading-page">正在打开旅程…</div>}>
      {view === 'trips' ? <TripsView trips={trips} refreshTrips={refreshTrips} currentTripId={tripId} currentPlan={plan} form={form} update={update} onGenerate={() => run({ ...form, memory })} events={events} error={error || tripError} running={running} onCancel={cancel} onOpenTrip={openTrip} onRevise={reviseTrip} token={session} /> : null}
      {view === 'travel' ? <TravelView trips={trips} token={session} onOpenSettings={() => navigate('settings')} /> : null}
      {view === 'profile' ? <MemoryView memory={memory} trips={trips} destination={form.destination} updateMemory={updateMemory} setOriginCity={value => update('originCity', value)} newCity={newCity} setNewCity={setNewCity} addVisitedCity={addVisitedCity} newPlace={newPlace} setNewPlace={setNewPlace} addVisitedPlace={addVisitedPlace} /> : null}
      {view === 'settings' ? <SettingsView user={user} onLogout={logout} health={health} onOpenDebug={() => navigate('debug')} /> : null}
      {view === 'debug' ? user?.role === 'admin' ? <DebugView onSaved={refreshHealth} onBack={() => navigate('settings')} /> : <p>仅管理员可访问高级设置。</p> : null}
    </Suspense></main>
    <footer className="site-footer"><span>行驿 · 留下每一次出发</span><span>行程、照片与日记保存在你的私有账号。</span></footer>
    <Toaster viewportClassName="max-w-2xl" />
    <QuestionPanel question={question} onAnswer={answerQuestion} running={running} />
  </div>;
}
