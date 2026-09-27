import React, { useEffect, useRef } from 'react';
import { Activity, Check, CircleAlert, Cpu, LoaderCircle, Wrench } from 'lucide-react';

function conversation(events) {
  const items = [];
  let round = null;
  const pending = [];
  const addCall = call => { if (round) round.calls.push(call); else items.push(call); };
  for (const event of events) {
    if (event.type === 'model_turn_start') {
      round = { kind: 'round', sequence: event.sequence, start: event, end: null, calls: [] };
      items.push(round);
    } else if (event.type === 'model_turn_end') {
      if (round?.start.turn === event.turn) round.end = event;
    } else if (event.type === 'tool_start') {
      const call = { kind: 'call', sequence: event.sequence, start: event, end: null };
      addCall(call); pending.push(call);
    } else if (event.type === 'tool_end') {
      const index = pending.findLastIndex(call => call.start.tool === event.tool && call.start.turn === event.turn);
      if (index >= 0) pending.splice(index, 1)[0].end = event;
      else addCall({ kind: 'call', sequence: event.sequence, start: null, end: event });
    } else if (event.type === 'tool_cache_hit' || event.type === 'tool_rejected') {
      addCall({ kind: 'call', sequence: event.sequence, start: event, end: event });
    } else {
      if (event.type === 'fallback_start' || event.type === 'result_assembled') round = null;
      items.push({ kind: 'event', sequence: event.sequence, event });
    }
  }
  return items;
}

function json(value) { return JSON.stringify(value ?? null, null, 2); }

function Detail({ label, value }) {
  return <details className="wb-debug-detail"><summary>{label}</summary><pre>{json(value)}</pre></details>;
}

function ToolCall({ call }) {
  const { start, end } = call;
  const event = end || start;
  const cached = event?.type === 'tool_cache_hit';
  const rejected = event?.type === 'tool_rejected';
  const done = Boolean(end);
  const title = cached ? '缓存命中' : rejected ? '请求被拒绝' : done ? end.ok ? '执行完成' : '执行失败' : '执行中';
  return <div className={`wb-chat-tool ${rejected || (done && end.ok === false) ? 'failed' : ''}`}>
    <div className="wb-chat-tool-head"><Wrench size={14} /><strong>{start?.tool || end?.tool}</strong><span>{title}{end?.durationMs != null ? ` · ${end.durationMs} ms` : ''}</span></div>
    {rejected ? <small>原因：{event.code}。该函数没有执行。</small> : null}
    {cached ? <small>结果来自本次请求的工具缓存，没有重新查询供应商。</small> : null}
    {start?.source === 'agent' ? <small>由服务端补全流程调用</small> : null}
    <Detail label="查看 function call 输入" value={start?.input ?? {}} />
    {done ? <Detail label="查看 function call 返回" value={event.output ?? { ok: event.ok, code: event.code }} /> : null}
  </div>;
}

function Round({ item }) {
  const { start, end, calls } = item;
  const tools = end?.requestedTools || [];
  const note = end?.publicNote || (end ? tools.length ? `本轮请求 ${tools.join('、')}。` : '本轮没有请求工具。' : '正在等待模型响应…');
  const usage = end?.usage;
  return <article className="wb-chat-round">
    <div className="wb-chat-speaker"><span><Cpu size={15} /></span><strong>Step Plan · 第 {start.turn} 轮</strong><em>{end ? '已返回' : '生成中'}</em></div>
    <p>{note}</p>
    <small className="wb-chat-caption">{end?.publicNote ? '模型公开行动说明' : '根据实际工具请求生成的执行摘要'} · 可用工具 {start.availableTools?.length || 0} 个 · 请求 {tools.length} 个</small>
    <Detail label={`查看本轮模型输入摘要（${start.input?.messageCount || 0} 条消息）`} value={start.input} />
    {usage ? <div className="wb-chat-usage">本轮 token：输入 {usage.prompt_tokens || 0} · 输出 {usage.completion_tokens || 0} · 合计 {(usage.prompt_tokens || 0) + (usage.completion_tokens || 0)}<Detail label="查看 API token 用量与缓存字段" value={usage} /></div> : null}
    {calls.map(call => <ToolCall key={call.sequence} call={call} />)}
  </article>;
}

function SystemEvent({ event }) {
  if (event.type === 'run_start') return <div className="wb-chat-system"><Activity size={14} /> Agent 启动 · {event.mode === 'model' ? 'Step Plan 模型模式' : '确定性模式'}</div>;
  if (event.type === 'fallback_start') return <div className="wb-chat-system warn"><CircleAlert size={14} /> 进入规则补全 · {event.reason}</div>;
  if (event.type === 'model_error') return <div className="wb-chat-system warn"><CircleAlert size={14} /> 模型错误 · {event.code}</div>;
  if (event.type === 'validation') return <div className={`wb-chat-system ${event.ok ? '' : 'warn'}`}><Check size={14} /> 行程约束校验{event.ok ? '通过' : '失败'} · {event.code}</div>;
  if (event.type === 'result_assembled') return <div className="wb-chat-result"><strong>最终结果如何形成</strong><p>{event.output?.calculation}</p><small>{event.output?.days} 天 · {event.output?.stops} 个地点 · 航班 {event.output?.flights} · 火车 {event.output?.trains} · 酒店 {event.output?.hotels}</small><Detail label="查看结果计数与数据来源" value={event.output} /></div>;
  return null;
}

export default function AgentTimeline({ events, running, error, plan, onCancel }) {
  const list = useRef(null);
  useEffect(() => { if (events.length && list.current) list.current.scrollTop = list.current.scrollHeight; }, [events.length]);
  const run = plan?.agentRun;
  const turns = events.filter(event => event.type === 'model_turn_end');
  const promptTokens = run?.usage?.prompt_tokens ?? turns.reduce((sum, event) => sum + (Number(event.usage?.prompt_tokens) || 0), 0);
  const completionTokens = run?.usage?.completion_tokens ?? turns.reduce((sum, event) => sum + (Number(event.usage?.completion_tokens) || 0), 0);
  const cacheHits = events.filter(event => event.type === 'tool_cache_hit').length;
  return <section className="wb-panel wb-timeline">
    <div className="wb-panel-head"><span className="wb-index">02 / AGENT LOOP</span><span className={`wb-live ${running ? 'is-live' : ''}`}>{running ? <><LoaderCircle size={13} className="spin" /> LIVE</> : plan ? 'COMPLETE' : 'STANDBY'}</span></div>
    <h2>Agent 对话与工具记录</h2><p className="wb-muted">按轮查看模型的公开行动说明、实际函数调用、输入输出与缓存。内部原始 CoT 不由 Step Plan 调试接口提供。</p>
    <div className="wb-metrics"><div><b>{run?.modelTurns ?? turns.length}</b><span>模型轮次 / 7</span></div><div><b>{run?.toolCalls ?? turns.reduce((sum, event) => sum + (event.requestedTools?.length || 0), 0)}</b><span>工具请求 / 14</span></div><div><b>{promptTokens + completionTokens}</b><span>已用 TOKEN</span></div></div>
    <p className="wb-budget">输入 {promptTokens} · 输出 {completionTokens} tokens · 工具缓存命中 {cacheHits} 次 · 未设置硬性 token 限额。模型缓存用量以每轮 API 返回字段为准。</p>
    <div className="wb-timeline-list wb-chat-list" ref={list} aria-live="polite">{events.length ? conversation(events).map(item => item.kind === 'round' ? <Round key={item.sequence} item={item} /> : item.kind === 'call' ? <ToolCall key={item.sequence} call={item} /> : <SystemEvent key={item.sequence} event={item.event} />) : <div className="wb-empty-loop"><Activity size={30} /><strong>等待第一条真实事件</strong><span>点击“开始真实调试”后，这里会实时更新。</span></div>}</div>
    {error ? <div className="wb-error" role="alert"><CircleAlert size={16} /> {error}</div> : null}
    {run ? <div className={`wb-outcome ${run.status}`}><strong>{run.status === 'completed' && run.modelTurns > 0 ? 'Step Plan 模型循环已真实完成' : run.status === 'degraded' ? '模型降级 · 行程由规则补全' : '模型未配置 · 规则规划'}</strong><span>{run.modelError ? `错误代码：${run.modelError}` : `模型：${run.model} · ${run.channel === 'step-plan' ? 'Step Plan' : run.channel || '当前通道'}`}</span></div> : null}
    {running ? <button type="button" className="wb-cancel" onClick={onCancel}>停止等待结果</button> : null}
  </section>;
}
