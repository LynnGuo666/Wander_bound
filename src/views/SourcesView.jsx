import React from 'react';
import { CircleCheck, Database, SlidersHorizontal } from 'lucide-react';
import { SAMPLE_STATUS } from '../initial-plan.mjs';

export default function SourcesView({ plan }) {
  return <section className="subpage"><div className="eyebrow">DATA & TRUST</div><h1>每一条建议，<em>都有出处。</em></h1><p className="subpage-intro">查询状态由当前服务配置决定。没有价格的来源不会进入“最低价”比较，也不会生成示例报价。</p><div className="sources-grid">{Object.entries(plan.providerStatus || SAMPLE_STATUS).map(([key, source]) => <div className="source-card" key={key}><div className={`source-icon ${source.configured ? 'connected' : ''}`}>{source.configured ? <CircleCheck size={20} /> : <Database size={20} />}</div><div><strong>{source.label}</strong><p>{source.result === 'ok' ? `已连接 · 本次查询成功${source.mode === 'trial' ? ' · 体验模式' : ''}` : source.configured ? `已配置 · ${source.result || '等待查询'}` : source.result || '尚未开通真实数据'}</p></div><span className={source.configured ? 'source-on' : 'source-off'}>{source.configured ? '已接入' : '待接入'}</span></div>)}</div><div className="data-policy"><SlidersHorizontal size={20} /><div><strong>比价接入原则</strong><p>航班和火车票可从飞猪 Skill/CLI、途牛 MCP 查询；道旅提供酒店候选。只有供应商给出完整数字价格时才排序。不同日期、舱位、税费与退改条件的结果会分别标注，预订前需在平台验价。</p></div></div></section>;
}
