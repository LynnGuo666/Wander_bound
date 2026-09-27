import React, { Suspense, useEffect, useState } from 'react';
import { Activity, Compass, Database, Heart, MapPinned, Server, ShieldCheck } from 'lucide-react';
import { DEFAULT_MEMORY } from '../shared/catalog.mjs';
import { normalizeMemory, parseTripRequest } from '../shared/planner.mjs';
import { readStored, upcomingFriday } from './browser-state.mjs';
import JourneyForm from './workbench/JourneyForm.jsx';
import CredentialsPanel from './workbench/CredentialsPanel.jsx';
import AgentTimeline from './workbench/AgentTimeline.jsx';
import { useAgentRun } from './workbench/useAgentRun.js';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const PlanView = React.lazy(() => import('./views/PlanView.jsx'));
const MemoryView = React.lazy(() => import('./views/MemoryView.jsx'));
const SourcesView = React.lazy(() => import('./views/SourcesView.jsx'));
const NAV = [['debug', Activity, 'Agent 调试'], ['plan', MapPinned, '完整行程'], ['sources', Database, '能力来源'], ['memory', Heart, '旅行记忆']];

export default function App() {
  const [view, setView] = useState('debug');
  const [memory, setMemory] = useState(() => normalizeMemory(readStored('travel-memory-v1', DEFAULT_MEMORY)));
  const [form, setForm] = useState(() => ({ query: '我想去深圳玩 3 天，机票尽量便宜，但不要红眼航班。', originCity: memory.homeCity || '', destination: '深圳', days: 3, startDate: upcomingFriday() }));
  const [credentials, setCredentials] = useState({});
  const [health, setHealth] = useState(null);
  const [selectedDay, setSelectedDay] = useState(null);
  const [newCity, setNewCity] = useState('');
  const [newPlace, setNewPlace] = useState('');
  const { events, plan, error, running, run, cancel } = useAgentRun();
  useEffect(() => { fetch('/api/health').then(response => response.json()).then(setHealth).catch(() => setHealth({ ok: false })); }, []);
  function update(field, value) {
    setForm(previous => {
      const next = { ...previous, [field]: value };
      if (field === 'query') { const parsed = parseTripRequest(value); if (parsed.destination) next.destination = parsed.destination; if (parsed.days) next.days = parsed.days; }
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
    setView('debug');
    run({ ...form, memory, credentials: Object.fromEntries(Object.entries(credentials).filter(([, value]) => value.trim()).map(([name, value]) => [name, value.trim()])) });
  }
  function rememberTrip() {
    if (!plan) return;
    const visitedPlaces = [...memory.visitedPlaces];
    for (const day of plan.itinerary) for (const stop of day.stops) if (!visitedPlaces.some(place => place.id === stop.id)) visitedPlaces.push({ id: stop.id, name: stop.name, city: plan.destination });
    updateMemory({ visitedCities: [...new Set([...memory.visitedCities, plan.destination])], visitedPlaces });
  }
  function addVisitedCity() { const name = newCity.trim().replace(/市$/, ''); if (name) { updateMemory({ visitedCities: [...new Set([...memory.visitedCities, name])] }); setNewCity(''); } }
  function addVisitedPlace() { const name = newPlace.trim(); if (name) { updateMemory({ visitedPlaces: [...memory.visitedPlaces, { id: `manual-${Date.now()}`, name, city: form.destination }] }); setNewPlace(''); } }
  return <Tabs value={view} onValueChange={setView} className="min-h-screen bg-background">
    <header className="border-b bg-card"><div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 md:px-8"><div className="flex items-center gap-3"><div className="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground"><Compass /></div><div><strong className="block text-lg leading-none">行驿</strong><span className="text-xs text-muted-foreground">DeepSleep-TT · DGX Spark</span></div></div><TabsList className="max-w-full overflow-x-auto">{NAV.map(([id, Icon, label]) => <TabsTrigger key={id} value={id}><Icon data-icon="inline-start" />{label}</TabsTrigger>)}</TabsList><Badge variant={health?.ok ? 'secondary' : 'outline'}><Server data-icon="inline-start" />{health?.ok ? 'Spark 已连接' : '连接检查中'}</Badge></div></header>
    <main className="mx-auto w-full max-w-7xl px-4 py-6 md:px-8 md:py-9">
      <TabsContent value="debug"><div className="flex flex-col gap-6"><div><p className="text-xs font-semibold tracking-[.16em] text-primary">TRAVEL AGENT / LIVE WORKSPACE</p><h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">看见 Agent 如何完成一趟旅程</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">从公开行动说明到 Function Call，再到模型用量、缓存和结果来源。每项数据都有可检查的执行记录。</p></div><div className="grid items-start gap-6 lg:grid-cols-[360px_minmax(0,1fr)]"><div className="flex flex-col gap-4"><JourneyForm form={form} update={update} onSubmit={generate} running={running} /><CredentialsPanel credentials={credentials} setCredentials={setCredentials} serverModelConfigured={health?.model?.configured} /></div><AgentTimeline events={events} running={running} error={error} plan={plan} onCancel={cancel} /></div>{plan ? <Card><CardHeader><CardTitle>{plan.destination} · {plan.days} 天行程</CardTitle><CardDescription>{plan.agentRun?.status === 'completed' ? 'Step Plan 模型完成' : '规则补全'} · {plan.itinerary?.reduce((sum, day) => sum + day.stops.length, 0)} 个地点</CardDescription></CardHeader><CardContent className="flex flex-wrap gap-3"><Badge variant="secondary">航班 {plan.flights?.length || 0}</Badge><Badge variant="secondary">火车 {plan.trains?.length || 0}</Badge><Badge variant="secondary">酒店 {plan.hotels?.length || 0}</Badge><button type="button" className="text-sm font-medium text-primary underline" onClick={() => setView('plan')}>查看完整行程</button></CardContent></Card> : null}<p className="flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck />密钥不写入本地存储；内部原始 CoT 不在当前 API 中。</p></div></TabsContent>
      <TabsContent value="plan"><Suspense fallback={<p className="text-sm text-muted-foreground">正在加载行程…</p>}>{plan ? <PlanView plan={plan} selectedDay={selectedDay} memory={memory} actions={{ rememberTrip, setSelectedDay }} /> : <Card><CardHeader><CardTitle>还没有行程</CardTitle><CardDescription>先在 Agent 调试页运行一次规划。</CardDescription></CardHeader></Card>}</Suspense></TabsContent>
      <TabsContent value="sources"><Suspense fallback={<p className="text-sm text-muted-foreground">正在读取能力…</p>}><SourcesView plan={plan} credentials={credentials} /></Suspense></TabsContent>
      <TabsContent value="memory"><Suspense fallback={<p className="text-sm text-muted-foreground">正在加载旅行记忆…</p>}><MemoryView memory={memory} destination={form.destination} updateMemory={updateMemory} setOriginCity={value => update('originCity', value)} newCity={newCity} setNewCity={setNewCity} addVisitedCity={addVisitedCity} newPlace={newPlace} setNewPlace={setNewPlace} addVisitedPlace={addVisitedPlace} /></Suspense></TabsContent>
    </main>
  </Tabs>;
}
