import React from 'react';
import { ArrowRight, MapPinned, Plane, TrainFront } from 'lucide-react';

export default function PlanSnapshot({ plan, onDetails }) {
  const days = plan?.itinerary || [];
  const stopCount = days.reduce((sum, day) => sum + day.stops.length, 0);
  return <section className="wb-panel wb-snapshot"><div className="wb-panel-head"><span className="wb-index">03 / OUTPUT</span><MapPinned size={17} /></div><h2>行程预览</h2>
    {!plan ? <div className="wb-snapshot-empty"><div className="wb-ticket-graphic"><span>DESTINATION</span><strong>· · ·</strong><small>AWAITING AGENT</small></div><p>规划完成后，这里会显示实际生成的城市、日程与供应商结果。</p></div> : <><div className="wb-destination"><small>{plan.originCity || '出发地待定'} → DESTINATION</small><strong>{plan.destination}</strong><span>{plan.days} 天 · {stopCount} 个地点</span></div><div className="wb-day-preview">{days.map(day => <div key={day.day}><b>{String(day.day).padStart(2, '0')}</b><span><strong>{day.title}</strong><small>{day.stops.map(stop => stop.name).slice(0, 3).join(' · ') || '抵达与入住'}</small></span></div>)}</div><div className="wb-offers"><span><Plane size={14} /> 航班 {plan.flights?.length || 0}</span><span><TrainFront size={14} /> 火车 {plan.trains?.length || 0}</span><span>酒店 {plan.hotels?.length || 0}</span></div>{!plan.flights?.length && !plan.trains?.length && !plan.hotels?.length ? <p className="wb-muted">本次没有取得可核验的航班、火车或酒店结果；行程地点不代表已完成预订。</p> : null}<button type="button" className="wb-details" onClick={onDetails}>查看完整行程 <ArrowRight size={17} /></button></>}
  </section>;
}
