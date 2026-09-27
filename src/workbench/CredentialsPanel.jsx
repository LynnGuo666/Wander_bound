import React, { useState } from 'react';
import { Eye, EyeOff, KeyRound, ShieldCheck } from 'lucide-react';

const FIELDS = [
  ['stepfun', 'StepFun · Step 5 Preview', '用于 Agent 模型循环'],
  ['amap', '高德 Web 服务', '地点、餐饮和路线'],
  ['dida', '道旅', '酒店候选'],
  ['duffel', 'Duffel', '航班报价'],
  ['tuniu', '途牛', 'MCP 交通与门票'],
  ['flyai', '飞猪 FlyAI', '交通与景点；空白可试用'],
];

export default function CredentialsPanel({ credentials, setCredentials, serverModelConfigured }) {
  const [expanded, setExpanded] = useState(true);
  const [visible, setVisible] = useState({});
  const count = FIELDS.filter(([name]) => credentials[name]).length;
  return <section className="wb-panel wb-credentials">
    <button type="button" className="wb-panel-toggle" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}><span><KeyRound size={17} /> 单次请求密钥</span><strong>{count ? `${count} 项已填` : serverModelConfigured ? '服务端已有模型密钥' : '等待配置'}</strong></button>
    {expanded ? <><p className="wb-muted">密钥只存在当前页面内存，提交时发给 Spark Agent；不写入浏览器存储，也不会出现在执行日志中。</p><div className="wb-key-list">{FIELDS.map(([name, label, hint]) => <label className="wb-key" key={name}><span><b>{label}</b><small>{hint}</small></span><div><input autoComplete="off" spellCheck="false" type={visible[name] ? 'text' : 'password'} value={credentials[name] || ''} onChange={event => setCredentials(previous => ({ ...previous, [name]: event.target.value }))} placeholder={name === 'stepfun' && serverModelConfigured ? '已由服务端配置，可留空' : '本次请求填写'} /><button type="button" aria-label={visible[name] ? `隐藏${label}密钥` : `显示${label}密钥`} onClick={() => setVisible(previous => ({ ...previous, [name]: !previous[name] }))}>{visible[name] ? <EyeOff size={15} /> : <Eye size={15} />}</button></div></label>)}</div><div className="wb-private"><ShieldCheck size={16} /> 仅适合在队伍的 Tailscale 私网中填写；请勿使用公开 HTTP 地址。</div></> : null}
  </section>;
}
