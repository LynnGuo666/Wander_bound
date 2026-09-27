import React, { useEffect, useState } from 'react';
import { ArrowRight, Camera, History, MapPin, RefreshCw, Send } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';

const STATUS = { not_started: '未开始', in_progress: '进行中', ended: '已结束' };

export default function TripsView({ currentTripId, onOpenConversation, onOpenPlan, onRevise, running }) {
  const [trips, setTrips] = useState([]);
  const [selected, setSelected] = useState(null);
  const [instruction, setInstruction] = useState('');
  const [error, setError] = useState('');
  async function refresh() {
    try {
      const response = await fetch('/api/trips');
      if (!response.ok) throw new Error('行程读取失败');
      const list = (await response.json()).trips;
      setTrips(list);
      if (selected?.id || currentTripId) await select(selected?.id || currentTripId);
    } catch (reason) { setError(reason.message); }
  }
  async function select(id) {
    const response = await fetch(`/api/trips/${id}`);
    if (!response.ok) { setError('行程读取失败'); return; }
    setSelected(await response.json());
  }
  useEffect(() => { refresh(); }, [currentTripId]);
  function revise() {
    if (!selected || !instruction.trim()) return;
    onOpenConversation(selected);
    onRevise(selected.id, instruction.trim());
    setInstruction('');
  }
  return <div className="flex flex-col gap-6"><div className="flex items-end justify-between gap-4"><div><p className="text-xs font-semibold tracking-[.16em] text-primary">YOUR JOURNEYS</p><h1 className="mt-2 text-3xl font-semibold">我的行程</h1><p className="mt-2 text-sm text-muted-foreground">规划会话、逐日安排和照片共用同一个行程 ID；每次修改都保留历史版本。</p></div><Button variant="outline" onClick={refresh}><RefreshCw data-icon="inline-start" />刷新</Button></div>
    {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    <div className="grid items-start gap-6 lg:grid-cols-[320px_minmax(0,1fr)]"><Card><CardHeader><CardTitle>行程列表</CardTitle><CardDescription>按最近修改时间排序</CardDescription></CardHeader><CardContent className="flex flex-col gap-2">{trips.length ? trips.map(trip => <Button key={trip.id} variant={selected?.id === trip.id ? 'secondary' : 'ghost'} className="h-auto w-full justify-between gap-3 py-3 text-left" onClick={() => select(trip.id)}><span className="min-w-0 truncate">{trip.plan?.destination || trip.title}</span><Badge variant="outline">{STATUS[trip.status]}</Badge></Button>) : <p className="text-sm text-muted-foreground">还没有行程；从 Agent 调试页开始规划。</p>}</CardContent></Card>
      {selected ? <div className="flex min-w-0 flex-col gap-4"><Card><CardHeader><div className="flex flex-wrap items-center gap-2"><CardTitle>{selected.plan?.destination || selected.title}</CardTitle><Badge>{STATUS[selected.status]}</Badge><Badge variant="outline">{selected.phase === 'planning' ? '规划中' : '行程已确定'}</Badge></div><CardDescription>{selected.plan ? `${selected.plan.startDate} 至 ${selected.plan.endDate} · ${selected.plan.days} 天` : '会话进行中，行程尚未确定'} · {selected.id}</CardDescription></CardHeader><CardContent className="flex flex-wrap gap-2"><Button onClick={() => onOpenConversation(selected)}>查看会话与 Debug <ArrowRight data-icon="inline-end" /></Button>{selected.plan ? <Button variant="outline" onClick={() => onOpenPlan(selected)}>查看完整行程</Button> : null}</CardContent></Card>
        {selected.plan ? <Card><CardHeader><CardTitle>逐日安排与导航</CardTitle><CardDescription>点击目的地可打开高德导航。</CardDescription></CardHeader><CardContent className="space-y-4">{selected.plan.itinerary?.map(day => <div key={day.day} className="border-t pt-3 first:border-t-0 first:pt-0"><strong className="text-sm">第 {day.day} 天 · {day.date}</strong><div className="mt-2 flex flex-wrap gap-2">{day.stops?.length ? day.stops.map(stop => <a key={stop.id} href={`https://uri.amap.com/navigation?to=${encodeURIComponent(`${stop.lng},${stop.lat},${stop.name}`)}&mode=car&src=travel-agent`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-sm text-primary"><MapPin className="size-3" />{stop.name}</a>) : <span className="text-sm text-muted-foreground">当天尚无可核实的地点</span>}</div></div>)}</CardContent></Card> : null}
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><Camera className="size-4" />行程照片</CardTitle><CardDescription>iOS 上传时使用本行程 ID，照片会自动归档到这里。</CardDescription></CardHeader><CardContent>{selected.photos?.length ? <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{selected.photos.map(photo => <figure key={photo.id} className="overflow-hidden rounded-md border"><img src={`/api/trips/${selected.id}/photos/${photo.id}`} alt={photo.capturedDay || '旅行照片'} className="aspect-square w-full object-cover" loading="lazy" /><figcaption className="p-2 text-xs text-muted-foreground">{photo.capturedDay || '未记录日期'}</figcaption></figure>)}</div> : <p className="text-sm text-muted-foreground">还没有关联的照片。</p>}</CardContent></Card>
        <Card><CardHeader><CardTitle className="flex items-center gap-2"><History className="size-4" />会话与行程历史</CardTitle><CardDescription>{selected.revisions?.length || 0} 个已确定版本 · {selected.events?.filter(event => event.type === 'user_answer').length || 0} 次问答</CardDescription></CardHeader><CardContent className="space-y-3">{selected.revisions?.map((revision, index) => <div key={index} className="rounded-md border p-3 text-sm"><strong>版本 {index + 1} · {new Date(revision.at).toLocaleString('zh-CN')}</strong><p className="mt-1 text-muted-foreground">{revision.instruction}</p><p className="mt-1">{revision.plan?.destination} · {revision.plan?.startDate} 至 {revision.plan?.endDate}</p></div>)}<div className="border-t pt-3"><label htmlFor="trip-revision" className="text-sm font-medium">继续对话，修改这趟行程</label><Textarea id="trip-revision" className="mt-2" value={instruction} onChange={event => setInstruction(event.target.value)} placeholder="例如：把第三天改成轻松一点，保留已经确定的日期和预算" /><Button className="mt-2" onClick={revise} disabled={running || !instruction.trim()}><Send data-icon="inline-start" />发送修改</Button></div></CardContent></Card>
      </div> : null}</div>
  </div>;
}
