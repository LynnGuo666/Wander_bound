import React, { Suspense, useEffect, useState } from 'react';
import { Activity, Compass, Database, Heart, MapPinned, Server, Settings2, ShieldCheck, Luggage } from 'lucide-react';
import { DEFAULT_MEMORY } from '../shared/catalog.mjs';
import { normalizeMemory } from '../shared/planner.mjs';
import { readStored } from './browser-state.mjs';
import JourneyForm from './workbench/JourneyForm.jsx';
import AgentTimeline from './workbench/AgentTimeline.jsx';
import QuestionPanel from './workbench/QuestionPanel.jsx';
import { useAgentRun } from './workbench/useAgentRun.js';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Toaster } from '@/components/ui/toast';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

const PlanView = React.lazy(() => import('./views/PlanView.jsx'));
const MemoryView = React.lazy(() => import('./views/MemoryView.jsx'));
const SourcesView = React.lazy(() => import('./views/SourcesView.jsx'));
const SettingsView = React.lazy(() => import('./views/SettingsView.jsx'));
const TripsView = React.lazy(() => import('./views/TripsView.jsx'));
const NAV = [['debug', Activity, 'Agent 调试'], ['trips', Luggage, '我的行程'], ['plan', MapPinned, '完整行程'], ['sources', Database, '能力来源'], ['memory', Heart, '旅行记忆'], ['settings', Settings2, '设置']];

export default function App() {
  const [view, setView] = useState('debug');
  const [memory, setMemory] = useState(() => normalizeMemory(readStored('travel-memory-v1', DEFAULT_MEMORY)));
  const [form, setForm] = useState(() => ({ query: '我想去深圳玩 3 天，机票尽量便宜，但不要红眼航班。', originCity: '', destination: '', days: '', startDate: '' }));
  const [health, setHealth] = useState(null);
  const [selectedDay, setSelectedDay] = useState(null);
  const [newCity, setNewCity] = useState('');
  const [newPlace, setNewPlace] = useState('');
  const { events, plan, question, tripId, error, running, run, answerQuestion, openTrip, reviseTrip, cancel } = useAgentRun();
  function refreshHealth() { fetch('/api/health').then(response => response.json()).then(setHealth).catch(() => setHealth({ ok: false })); }
  useEffect(() => { refreshHealth(); }, []);
  function update(field, value) {
    setForm(previous => {
      const next = { ...previous, [field]: value };
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
    run({ ...form, memory });
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
    <header className="border-b bg-card"><div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-4 md:px-8"><div className="flex items-center gap-3"><div className="flex size-10 items-center justify-center rounded-lg bg-primary text-primary-foreground"><Compass /></div><div><strong className="block text-lg leading-none">行驿</strong><span className="text-xs text-muted-foreground">DeepSleep-TT · 本地 FastAPI</span></div></div><TabsList className="max-w-full overflow-x-auto">{NAV.map(([id, Icon, label]) => <TabsTrigger key={id} value={id}><Icon data-icon="inline-start" />{label}</TabsTrigger>)}</TabsList><Badge variant={health?.ok ? 'secondary' : 'outline'}><Server data-icon="inline-start" />{health?.ok ? '本地 API 已连接' : '连接检查中'}</Badge></div></header>
    <main className="mx-auto w-full max-w-7xl px-4 py-6 md:px-8 md:py-9">
      <TabsContent value="debug"><div className="flex flex-col gap-6"><div><p className="text-xs font-semibold tracking-[.16em] text-primary">TRAVEL AGENT / LIVE WORKSPACE</p><h1 className="mt-2 text-3xl font-semibold tracking-tight md:text-4xl">看见 Agent 如何完成一趟旅程</h1><p className="mt-2 max-w-3xl text-sm text-muted-foreground">从公开行动说明到 Function Call，再到模型用量、缓存和结果来源。每项数据都有可检查的执行记录。</p></div><div className="grid items-start gap-6 lg:grid-cols-[360px_minmax(0,1fr)]"><div className="flex flex-col gap-4"><JourneyForm form={form} update={update} onSubmit={generate} running={running} /><Card size="sm"><CardHeader><CardTitle>服务端配置</CardTitle><CardDescription>模型密钥和工具优先级请在设置页保存到 config.yml。</CardDescription></CardHeader><CardContent><Button type="button" variant="outline" onClick={() => setView('settings')}><Settings2 data-icon="inline-start" />打开设置</Button></CardContent></Card></div><AgentTimeline events={events} running={running} error={error} plan={plan} onCancel={cancel} modelConfigured={health?.model?.configured} onOpenSettings={() => setView('settings')} /></div>{plan ? <Card><CardHeader><CardTitle>{plan.destination} · {plan.days} 天行程</CardTitle><CardDescription>{plan.agentRun?.status === 'completed' ? 'Step Plan 模型完成' : '规则补全'} · {plan.itinerary?.reduce((sum, day) => sum + day.stops.length, 0)} 个地点</CardDescription></CardHeader><CardContent className="flex flex-wrap gap-3"><Badge variant="secondary">航班 {plan.flights?.length || 0}</Badge><Badge variant="secondary">火车 {plan.trains?.length || 0}</Badge><Badge variant="secondary">酒店 {plan.hotels?.length || 0}</Badge><button type="button" className="text-sm font-medium text-primary underline" onClick={() => setView('plan')}>查看完整行程</button></CardContent></Card> : null}<p className="flex items-center gap-2 text-xs text-muted-foreground"><ShieldCheck />密钥只保存在服务端；模型返回的原始 thinking 仅在对应调试轮次展开。</p></div></TabsContent>
      <TabsContent value="trips"><Suspense fallback={<p className="text-sm text-muted-foreground">正在加载行程…</p>}><TripsView currentTripId={tripId} running={running} onOpenConversation={trip => { openTrip(trip); setView('debug'); }} onOpenPlan={trip => { openTrip(trip); setView('plan'); }} onRevise={reviseTrip} /></Suspense></TabsContent>
      <TabsContent value="plan"><Suspense fallback={<p className="text-sm text-muted-foreground">正在加载行程…</p>}>{plan ? <PlanView plan={plan} selectedDay={selectedDay} memory={memory} actions={{ rememberTrip, setSelectedDay }} /> : <Card><CardHeader><CardTitle>还没有行程</CardTitle><CardDescription>先在 Agent 调试页运行一次规划。</CardDescription></CardHeader></Card>}</Suspense></TabsContent>
      <TabsContent value="sources"><Suspense fallback={<p className="text-sm text-muted-foreground">正在读取能力…</p>}><SourcesView plan={plan} onOpenSettings={() => setView('settings')} /></Suspense></TabsContent>
      <TabsContent value="memory"><Suspense fallback={<p className="text-sm text-muted-foreground">正在加载旅行记忆…</p>}><MemoryView memory={memory} destination={form.destination} updateMemory={updateMemory} setOriginCity={value => update('originCity', value)} newCity={newCity} setNewCity={setNewCity} addVisitedCity={addVisitedCity} newPlace={newPlace} setNewPlace={setNewPlace} addVisitedPlace={addVisitedPlace} /></Suspense></TabsContent>
      <TabsContent value="settings"><Suspense fallback={<p className="text-sm text-muted-foreground">正在加载设置…</p>}><SettingsView onSaved={refreshHealth} /></Suspense></TabsContent>
    </main>
    <Toaster viewportClassName="max-w-2xl" />
    <QuestionPanel question={question} onAnswer={answerQuestion} running={running} />
  </Tabs>;
}
