import React, { useEffect, useState } from 'react';
import { Cpu, HardDrive, LoaderCircle, Play, RotateCcw, Send, Square } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

const LABELS = { ready: '已就绪', stopped_on_demand: '按需停止', stopped: '已停止', not_installed: '尚未部署', external: '外部服务', active: '已运行' };
const gib = value => value == null ? '—' : `${value.toFixed(1)} GiB`;
function ProgressBar({ percent, label }) {
  return <div role="progressbar" aria-label={label} aria-valuemin={percent == null ? undefined : 0} aria-valuemax={percent == null ? undefined : 100} aria-valuenow={percent == null ? undefined : percent} aria-valuetext={percent == null ? `${label}，正在进行` : `${label}，约 ${percent}%`} className="h-2 overflow-hidden rounded-full bg-muted"><div className={`h-full rounded-full bg-primary ${percent == null ? 'w-1/3 animate-pulse' : 'transition-[width] duration-500'}`} style={percent == null ? undefined : { width: `${percent}%` }} /></div>;
}

export default function InferenceView({ initialToken = '' }) {
  const [status, setStatus] = useState(null);
  const [token, setToken] = useState(initialToken);
  const [message, setMessage] = useState('请用两句话介绍你自己。');
  const [answer, setAnswer] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');

  async function refresh() {
    try {
      const response = await fetch('/api/inference/status');
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      setStatus(await response.json());
      setError('');
    } catch (reason) { setError(`无法读取模型状态：${reason.message}`); }
  }
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => clearInterval(timer);
  }, []);

  async function action(name, operation) {
    setBusy(`${name}-${operation}`); setError('');
    try {
      const response = await fetch(`/api/inference/models/${name}/${operation}`, {
        method: 'POST', headers: { Authorization: `Bearer ${token}` },
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
      setStatus(result);
    } catch (reason) { setError(reason.message); }
    finally { setBusy(''); refresh(); }
  }

  async function testChat(event) {
    event.preventDefault(); setBusy('chat-test'); setError(''); setAnswer('');
    try {
      const response = await fetch('/api/inference/chat', { method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`);
      setAnswer(result.message || '模型没有返回正文。');
    } catch (reason) { setError(reason.message); }
    finally { setBusy(''); refresh(); }
  }

  return <div className="flex flex-col gap-6">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold tracking-[.16em] text-primary">SPARK / INFERENCE</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">模型调度</h1><p className="mt-2 text-sm text-muted-foreground">Qwen 优先常驻，图片按需并行驻留，视频任务独占推理资源。旅行规划仍使用当前配置的 Step Plan。</p></div><Button variant="outline" onClick={refresh}><RotateCcw data-icon="inline-start" />刷新</Button></div>
    {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    {status?.error ? <p role="status" className="text-sm text-destructive">最近一次调度错误：{status.error}</p> : null}
    {!status ? <p className="text-sm text-muted-foreground">正在读取 Spark 状态…</p> : !status.enabled ? <Card><CardHeader><CardTitle>当前连接的是本机开发服务</CardTitle><CardDescription>本机 API 没有 Spark 的内存、GPU 和模型调度数据。请连接 Spark 私网，并让开发网页的 `/api/inference` 请求转发到 Spark。</CardDescription></CardHeader></Card> : <>
      <div className="grid gap-4 md:grid-cols-3"><Card><CardHeader><CardTitle>可用内存</CardTitle><CardDescription>CPU 与 GPU 共享</CardDescription></CardHeader><CardContent className="text-2xl font-semibold">{gib(status.memory.availableGiB)}<p className="mt-1 text-xs font-normal text-muted-foreground">总量 {gib(status.memory.totalGiB)} · 空闲 {gib(status.memory.freeGiB)}</p></CardContent></Card><Card><CardHeader><CardTitle>任务队列</CardTitle><CardDescription>等待与执行中的媒体任务</CardDescription></CardHeader><CardContent className="text-2xl font-semibold">{status.queue?.total ?? 0}<p className="mt-1 text-xs font-normal text-muted-foreground">图片 {status.queue?.image ?? 0} · 视频 {status.queue?.video ?? 0}</p></CardContent></Card><Card><CardHeader><CardTitle>控制器</CardTitle><CardDescription>按模型设置空闲保温时间</CardDescription></CardHeader><CardContent><Badge variant={status.enabled ? 'default' : 'outline'}>{status.enabled ? status.phase : '本地观察模式'}</Badge><p className="mt-2 text-xs text-muted-foreground">内存压力 some/full：{status.memory.pressureSome10 ?? '—'}% / {status.memory.pressureFull10 ?? '—'}% · GPU {status.gpu?.utilizationPercent ?? '—'}%</p></CardContent></Card></div>
      {status.loadingModel && status.loadProgress ? <Card><CardHeader><CardTitle>模型加载进度</CardTitle><CardDescription>{status.models.find(model => model.id === status.loadingModel)?.label} · {status.loadProgress.stage}</CardDescription></CardHeader><CardContent className="space-y-2"><ProgressBar percent={status.loadProgress.percent} label={status.loadProgress.stage} /><p className="text-xs text-muted-foreground">{status.loadProgress.estimated ? '总体进度为阶段估算' : '加载完成'} · {status.loadProgress.percent}%</p></CardContent></Card> : null}
      {status.queue?.jobs?.length ? <Card><CardHeader><CardTitle>媒体任务进度</CardTitle><CardDescription>生成阶段无法可靠估算百分比时显示活动状态。</CardDescription></CardHeader><CardContent className="space-y-4">{status.queue.jobs.map(job => <div key={job.id} className="space-y-2 rounded-lg border p-3"><div className="flex items-center justify-between gap-2 text-sm"><strong>{job.kind === 'edit' ? '图片重绘' : '回忆视频'}</strong><span className="text-muted-foreground">{job.progressLabel || '等待调度'}{job.progressPercent == null ? ' · 进行中' : ` · ${job.progressPercent}%`}</span></div><ProgressBar percent={job.progressPercent} label={job.progressLabel || '等待调度'} />{job.kind === 'memory' && job.completedClips ? <p className="text-xs text-muted-foreground">已完成 {job.completedClips} 个镜头</p> : null}</div>)}</CardContent></Card> : null}
      <Card><CardHeader><CardTitle className="flex items-center gap-2"><Cpu />模型服务</CardTitle><CardDescription>任务运行时不会停止模型；手动操作需要媒体访问令牌。</CardDescription></CardHeader><CardContent className="flex flex-col gap-4"><div className="max-w-sm"><Input type="password" autoComplete="off" aria-label="媒体访问令牌" placeholder="媒体访问令牌（仅保留在此页面）" value={token} onChange={event => setToken(event.target.value)} /></div><div className="grid gap-3 md:grid-cols-3">{status.models.map(model => <div key={model.id} className="rounded-lg border p-4"><div className="flex flex-wrap items-center justify-between gap-2"><strong className="text-sm">{model.label}</strong><Badge variant={model.active || status.loadingModel === model.id ? 'default' : 'secondary'}>{model.active ? '运行中' : status.loadingModel === model.id ? '加载中' : LABELS[model.state] || model.state}</Badge></div><p className="mt-2 text-xs text-muted-foreground">{model.service} · {model.id === 'chat' && status.primaryChat ? '优先常驻' : `保温 ${Math.round(model.idleTimeoutSeconds / 60)} 分钟`}{model.idleSeconds != null && model.state === 'ready' ? ` · 空闲 ${model.idleSeconds} 秒` : ''}</p><div className="mt-4 flex gap-2"><Button size="sm" variant="outline" disabled={!status.enabled || !token || !!busy || !!status.loadingModel || model.active || model.state === 'ready' || model.state === 'not_installed'} onClick={() => action(model.id, 'warm')}><Play data-icon="inline-start" />预热</Button><Button size="sm" variant="outline" disabled={!status.enabled || !token || !!busy || !!status.loadingModel || model.active || model.state !== 'ready'} onClick={() => action(model.id, 'release')}><Square data-icon="inline-start" />释放</Button></div></div>)}</div></CardContent></Card>
      <Card><CardHeader><CardTitle className="flex items-center gap-2"><HardDrive />Qwen3.8 测试</CardTitle><CardDescription>独立试跑本地模型；不会改变旅行规划使用的模型。</CardDescription></CardHeader><CardContent><form onSubmit={testChat} className="flex flex-col gap-3"><Textarea aria-label="测试消息" value={message} onChange={event => setMessage(event.target.value)} rows={3} maxLength={4000} /><Button type="submit" className="self-start" disabled={!token || !message.trim() || !!busy || !!status.loadingModel || status.models.find(model => model.id === 'chat')?.state === 'not_installed'}>{busy === 'chat-test' ? <LoaderCircle className="animate-spin" data-icon="inline-start" /> : <Send data-icon="inline-start" />}{busy === 'chat-test' ? '生成中…' : '发送测试消息'}</Button></form>{answer ? <div className="mt-4 whitespace-pre-wrap rounded-lg border bg-muted/30 p-4 text-sm" role="status">{answer}</div> : null}</CardContent></Card>
    </>}
  </div>;
}
