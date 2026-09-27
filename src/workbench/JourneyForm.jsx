import React from 'react';
import { ArrowUpRight, CalendarDays, MapPin, Navigation2, Play } from 'lucide-react';

export default function JourneyForm({ form, update, onSubmit, running }) {
  return <form className="wb-panel wb-form" onSubmit={event => { event.preventDefault(); onSubmit(); }}>
    <div className="wb-panel-head"><span className="wb-index">01 / JOURNEY BRIEF</span><Navigation2 size={17} /></div>
    <h2>旅程指令</h2>
    <p className="wb-muted">描述你想要的旅程，Agent 会按需加载地点、交通、住宿等工具。</p>
    <label className="wb-field wb-field-wide"><span>你想怎么旅行</span><textarea value={form.query} onChange={event => update('query', event.target.value)} rows={4} placeholder="我想从上海去深圳玩 3 天，避开红眼航班…" /></label>
    <div className="wb-field-grid">
      <label className="wb-field"><span><MapPin size={13} /> 出发城市</span><input value={form.originCity} onChange={event => update('originCity', event.target.value)} placeholder="上海" /></label>
      <label className="wb-field"><span><MapPin size={13} /> 目的地</span><input value={form.destination} onChange={event => update('destination', event.target.value)} placeholder="深圳" required /></label>
      <label className="wb-field"><span><CalendarDays size={13} /> 出发日期</span><input type="date" value={form.startDate} onChange={event => update('startDate', event.target.value)} required /></label>
      <label className="wb-field"><span>旅行天数</span><select value={form.days} onChange={event => update('days', Number(event.target.value))}>{[1,2,3,4,5,6,7].map(day => <option key={day} value={day}>{day} 天</option>)}</select></label>
    </div>
    <button className="wb-run" disabled={running} type="submit"><Play size={16} fill="currentColor" /> {running ? 'Agent 正在执行…' : '开始真实调试'} <ArrowUpRight size={16} /></button>
  </form>;
}
