import React, { useEffect, useRef } from 'react';
import { Activity, Check, CircleAlert, Cpu, LoaderCircle, Wrench } from 'lucide-react';

const labels = {
  run_start: event => event.mode === 'model' ? 'Agent 已启动 · 模型模式' : 'Agent 已启动 · 确定性模式',
  model_turn_start: event => `模型第 ${event.turn} 轮 · 加载 ${event.availableTools?.length || 0} 个可用工具`,
  model_turn_end: event => `模型第 ${event.turn} 轮返回 · 请求 ${event.requestedTools?.length || 0} 个工具`,
  tool_start: event => `调用工具 · ${event.tool}`,
  tool_end: event => `${event.ok ? '工具完成' : '工具失败'} · ${event.tool}`,
  model_error: event => `模型失败 · ${event.code}`,
  fallback_start: event => `进入确定性补全 · ${event.reason}`,
  validation: event => event.ok ? '行程约束校验通过' : '行程约束校验失败',
};

function iconFor(event) {
  if (event.type === 'model_turn_start' || event.type === 'model_turn_end') return <Cpu size={15} />;
  if (event.type.startsWith('tool_')) return <Wrench size={15} />;
  if (event.type === 'validation' && event.ok) return <Check size={15} />;
  if (event.type === 'model_error' || event.ok === false) return <CircleAlert size={15} />;
  return <Activity size={15} />;
}

export default function AgentTimeline({ events, running, error, plan, onCancel }) {
  const list = useRef(null);
  useEffect(() => { if (events.length && list.current) list.current.scrollTop = list.current.scrollHeight; }, [events.length]);
  const run = plan?.agentRun;
  return <section className="wb-panel wb-timeline">
    <div className="wb-panel-head"><span className="wb-index">02 / AGENT LOOP</span><span className={`wb-live ${running ? 'is-live' : ''}`}>{running ? <><LoaderCircle size={13} className="spin" /> LIVE</> : plan ? 'COMPLETE' : 'STANDBY'}</span></div>
    <h2>执行记录</h2><p className="wb-muted">这里显示可验证的模型轮次、工具调用、耗时与校验结果；不展示模型隐藏思维链。</p>
    <div className="wb-metrics"><div><b>{run?.modelTurns ?? events.filter(event => event.type === 'model_turn_end').length}</b><span>MODEL ROUNDS</span></div><div><b>{run?.toolCalls ?? events.filter(event => event.type === 'tool_start' && event.source === 'model').length}</b><span>MODEL CALLS</span></div><div><b>{run?.trace?.length ?? events.filter(event => event.type === 'tool_end').length}</b><span>TOOLS EXECUTED</span></div></div>
    <div className="wb-timeline-list" ref={list} aria-live="polite">{events.length ? events.map(event => <div className={`wb-event wb-event-${event.type} ${event.ok === false ? 'failed' : ''}`} key={event.sequence}><span className="wb-event-icon">{iconFor(event)}</span><div><strong>{labels[event.type]?.(event) || event.type}</strong><small>{event.type === 'model_turn_start' ? event.availableTools?.join(' · ') : event.type === 'model_turn_end' ? event.requestedTools?.join(' · ') || '未请求工具' : event.type === 'tool_end' ? `${event.durationMs} ms · ${event.code}` : new Date(event.at).toLocaleTimeString('zh-CN', { hour12: false })}</small></div><em>{String(event.sequence).padStart(2, '0')}</em></div>) : <div className="wb-empty-loop"><Activity size={30} /><strong>等待第一条真实事件</strong><span>点击“开始真实调试”后，这里会实时更新。</span></div>}</div>
    {error ? <div className="wb-error" role="alert"><CircleAlert size={16} /> {error}</div> : null}
    {run ? <div className={`wb-outcome ${run.status}`}><strong>{run.status === 'completed' ? '模型循环已完成' : run.status === 'degraded' ? '模型降级 · 行程由规则补全' : '模型未配置 · 规则规划'}</strong><span>{run.modelError ? `错误代码：${run.modelError}` : `模型：${run.model}`}</span></div> : null}
    {running ? <button type="button" className="wb-cancel" onClick={onCancel}>停止本次请求</button> : null}
  </section>;
}
