import React from 'react';
import { Activity, ChevronDown, Cpu, LoaderCircle, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Bubble, BubbleContent } from '@/components/ui/bubble';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Marker, MarkerContent } from '@/components/ui/marker';
import { Message, MessageAvatar, MessageContent, MessageFooter, MessageHeader } from '@/components/ui/message';
import { MessageScroller, MessageScrollerButton, MessageScrollerContent, MessageScrollerItem, MessageScrollerProvider, MessageScrollerViewport } from '@/components/ui/message-scroller';

function groupEvents(events) {
  const items = [], pending = [];
  let round = null;
  const add = item => { if (round) round.calls.push(item); else items.push(item); };
  for (const event of events) {
    if (event.type === 'model_turn_start') { round = { kind: 'round', id: event.sequence, start: event, end: null, calls: [] }; items.push(round); }
    else if (event.type === 'model_turn_end') { if (round?.start.turn === event.turn) round.end = event; }
    else if (event.type === 'model_text_delta') { if (round?.start.turn === event.turn) round.publicText = `${round.publicText || ''}${event.text || ''}`; }
    else if (event.type === 'tool_start') { const item = { kind: 'tool', id: event.sequence, start: event, end: null }; add(item); pending.push(item); }
    else if (event.type === 'tool_end') { const index = pending.findLastIndex(item => item.start.tool === event.tool && item.start.turn === event.turn); if (index >= 0) pending.splice(index, 1)[0].end = event; else add({ kind: 'tool', id: event.sequence, start: null, end: event }); }
    else if (event.type === 'tool_cache_hit' || event.type === 'tool_rejected') add({ kind: 'tool', id: event.sequence, start: event, end: event });
    else { if (event.type === 'fallback_start' || event.type === 'result_assembled') round = null; items.push({ kind: 'system', id: event.sequence, event }); }
  }
  return items;
}

function CodeBlock({ value }) { return <pre className="max-h-56 overflow-auto rounded-md bg-muted p-3 text-xs leading-relaxed whitespace-pre-wrap break-all">{JSON.stringify(value ?? null, null, 2)}</pre>; }

function FunctionCall({ item }) {
  const event = item.end || item.start;
  const cached = event?.type === 'tool_cache_hit';
  const rejected = event?.type === 'tool_rejected';
  const label = cached ? '缓存命中' : rejected ? '拒绝执行' : !item.end ? '执行中' : item.end.ok ? '已完成' : '执行失败';
  return <Collapsible key={item.id} className="rounded-lg border bg-card">
    <CollapsibleTrigger render={<Button variant="ghost" className="h-auto w-full justify-start gap-2 px-3 py-2" />}><Wrench data-icon="inline-start" /><span className="truncate font-mono text-xs">{item.start?.tool || item.end?.tool}</span><Badge variant={rejected || item.end?.ok === false ? 'destructive' : 'secondary'} className="ml-auto">{label}</Badge><ChevronDown data-icon="inline-end" /></CollapsibleTrigger>
    <CollapsibleContent className="flex flex-col gap-3 border-t p-3 text-xs"><div><p className="mb-1 font-medium">Function call 输入</p><CodeBlock value={item.start?.input ?? {}} /></div>{item.end ? <div><p className="mb-1 font-medium">Function call 返回</p><CodeBlock value={event.output ?? { ok: event.ok, code: event.code }} /></div> : null}{cached ? <p className="text-muted-foreground">本次请求的缓存结果，未重新调用上游。</p> : null}{rejected ? <p className="text-destructive">{event.code} · 工具未执行</p> : null}</CollapsibleContent>
  </Collapsible>;
}

function Round({ item }) {
  const { start, end, calls } = item;
  const note = end?.publicNote || item.publicText || (end ? end.requestedTools?.length ? `本轮选择调用 ${end.requestedTools.join('、')}。` : '本轮没有调用工具。' : '正在等待模型响应…');
  const usage = end?.usage;
  return <Message align="start"><MessageAvatar><Cpu /></MessageAvatar><MessageContent><MessageHeader>Step Plan · 第 {start.turn} 轮 <Badge variant="outline" className="ml-2">{end ? '已返回' : '流式生成中'}</Badge></MessageHeader><Bubble variant="muted"><BubbleContent>{note}</BubbleContent></Bubble><p className="px-3 text-xs text-muted-foreground">{end?.publicNote || item.publicText ? '模型公开行动说明' : '依据实际工具请求生成的摘要'} · 可用工具 {start.availableTools?.length || 0} 个</p><div className="flex flex-col gap-2 px-3">{calls.map(call => <FunctionCall key={call.id} item={call} />)}</div><MessageFooter><div className="flex flex-wrap gap-3"><span>{usage ? `输入 ${usage.prompt_tokens ?? '未返回'} / 输出 ${usage.completion_tokens ?? '未返回'} tokens` : 'Token 用量待返回'}</span><Collapsible><CollapsibleTrigger render={<Button variant="link" size="xs" />}>查看模型输入与用量</CollapsibleTrigger><CollapsibleContent className="mt-2 flex flex-col gap-2"><CodeBlock value={start.input} /><CodeBlock value={usage || {}} /></CollapsibleContent></Collapsible></div></MessageFooter></MessageContent></Message>;
}

function SystemEvent({ event }) {
  if (event.type === 'result_assembled') return <Card size="sm"><CardHeader><CardTitle>结果计算与来源</CardTitle><CardDescription>{event.output?.calculation}</CardDescription></CardHeader><CardContent><Collapsible><CollapsibleTrigger render={<Button variant="outline" size="sm" />}>展开行程、结果数量与来源 <ChevronDown data-icon="inline-end" /></CollapsibleTrigger><CollapsibleContent className="mt-3"><CodeBlock value={event.output} /></CollapsibleContent></Collapsible></CardContent></Card>;
  const text = event.type === 'run_start' ? `Agent 启动 · ${event.mode === 'model' ? '模型循环' : '规则模式'}` : event.type === 'fallback_start' ? `进入规则补全 · ${event.reason}` : event.type === 'validation' ? `行程校验${event.ok ? '通过' : '失败'}` : event.type === 'model_error' ? `模型失败 · ${event.code}` : null;
  return text ? <Marker variant="separator"><MarkerContent>{text}</MarkerContent></Marker> : null;
}

export default function AgentTimeline({ events, running, error, plan, onCancel, modelConfigured, onOpenSettings }) {
  const run = plan?.agentRun;
  const turns = events.filter(event => event.type === 'model_turn_end');
  const inputTokens = run?.usage?.prompt_tokens ?? turns.reduce((sum, event) => sum + (Number(event.usage?.prompt_tokens) || 0), 0);
  const outputTokens = run?.usage?.completion_tokens ?? turns.reduce((sum, event) => sum + (Number(event.usage?.completion_tokens) || 0), 0);
  const modelStarts = events.filter(event => event.type === 'model_turn_start').length;
  const modelCalls = events.filter(event => event.type === 'tool_end' && event.source === 'model').length;
  const agentCalls = events.filter(event => event.type === 'tool_end' && event.source === 'agent').length;
  const usageReported = run?.usage?.reported || turns.some(event => event.usage && (Number.isFinite(event.usage.prompt_tokens) || Number.isFinite(event.usage.completion_tokens)));
  const tokenLabel = value => modelStarts && !usageReported ? running ? '统计中' : '上游未返回' : value;
  const items = groupEvents(events);
  return <Card className="min-w-0"><CardHeader className="border-b"><div className="flex items-center justify-between gap-3"><CardTitle>Agent Loop</CardTitle><Badge variant={running ? 'default' : 'secondary'}>{running ? <><LoaderCircle data-icon="inline-start" className="animate-spin" /> 实时执行</> : run ? run.status : '等待运行'}</Badge></div><CardDescription>模型公开说明、函数调用、返回值和缓存均可展开核对；这里不是内部原始 CoT。</CardDescription><div className="flex flex-wrap gap-2 pt-2"><Badge variant="outline">{modelStarts ? `模型 ${modelStarts} / 200 轮上限` : '模型未调用'}</Badge><Badge variant="outline">模型工具 {modelCalls} / 200 次上限</Badge><Badge variant="outline">规则工具 {agentCalls} 次</Badge><Badge variant="outline">输入 {tokenLabel(inputTokens)} tokens</Badge><Badge variant="outline">输出 {tokenLabel(outputTokens)} tokens</Badge><Badge variant="outline">缓存 {events.filter(e => e.type === 'tool_cache_hit').length} 次</Badge></div>{!modelConfigured && !running && run?.status === 'unconfigured' ? <div className="flex items-center gap-2 pt-2 text-xs text-muted-foreground"><span>本次未配置 Step Plan 密钥，使用规则补全。</span><Button type="button" variant="link" size="xs" onClick={onOpenSettings}>去设置</Button></div> : null}</CardHeader>
    <CardContent className="pt-4"><MessageScrollerProvider autoScroll><MessageScroller className="relative h-[560px]"><MessageScrollerViewport><MessageScrollerContent className="flex flex-col gap-5 p-2">{items.length ? items.map(item => <MessageScrollerItem key={item.id} messageId={String(item.id)}>{item.kind === 'round' ? <Round item={item} /> : item.kind === 'tool' ? <FunctionCall item={item} /> : <SystemEvent event={item.event} />}</MessageScrollerItem>) : <div className="flex h-80 flex-col items-center justify-center gap-2 text-center text-muted-foreground"><Activity /><p className="text-sm">等待第一条执行事件</p><p className="text-xs">点击开始调试后，这里会逐步展示 Agent 与工具的交互。</p></div>}</MessageScrollerContent></MessageScrollerViewport><MessageScrollerButton /></MessageScroller></MessageScrollerProvider>{error ? <p className="mt-3 text-sm text-destructive" role="alert">{error}</p> : null}{running ? <Button variant="outline" size="sm" className="mt-3" onClick={onCancel}>停止等待</Button> : null}</CardContent>
  </Card>;
}
