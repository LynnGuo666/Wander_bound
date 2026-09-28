import React, { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api.js';
import { ArrowDown, ArrowUp, Eye, EyeOff, KeyRound, RotateCcw, Save, Settings2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const KEY_FIELDS = [
  ['stepfun', 'Step Plan', 'Step 5 模型调用'],
  ['amap', '高德 Web', '地点、餐饮与路线'],
  ['dida', '道旅 MCP', '酒店查询'],
  ['duffel', 'Duffel', '航班报价'],
  ['tuniu', '途牛 MCP', '机票、火车票与门票'],
  ['flyai', '飞猪 FlyAI', '机票、火车票与景点'],
];
const GROUPS = [
  ['flights', '飞机票', { duffel: 'Duffel', flyai: '飞猪 FlyAI', tuniu: '途牛 MCP' }],
  ['trains', '火车票', { rail12306: '12306 社区 MCP', flyai: '飞猪 FlyAI', tuniu: '途牛 MCP' }],
  ['attractions', '景点门票', { flyai: '飞猪 FlyAI', tuniu: '途牛 MCP' }],
];

export default function DeveloperSettingsView({ onSaved }) {
  const [settings, setSettings] = useState(null);
  const [keys, setKeys] = useState({});
  const [priorities, setPriorities] = useState({});
  const [visible, setVisible] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  async function load() {
    setBusy(true); setError('');
    try {
      const response = await apiFetch('/api/settings');
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
      setSettings(result); setPriorities(result.priorities); setKeys({});
    } catch (reason) { setError(reason.message || '无法读取设置'); }
    finally { setBusy(false); }
  }
  useEffect(() => { load(); }, []);

  function move(group, index, offset) {
    setPriorities(previous => {
      const next = [...previous[group]];
      [next[index], next[index + offset]] = [next[index + offset], next[index]];
      return { ...previous, [group]: next };
    });
    setNotice('');
  }

  async function save(event) {
    event.preventDefault(); setBusy(true); setError(''); setNotice('');
    try {
      const response = await apiFetch('/api/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credentials: keys, priorities }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
      setSettings(result); setPriorities(result.priorities); setKeys({}); setVisible({});
      setNotice('已保存到 Spark 服务端 config.yml，新规划立即生效。');
      onSaved?.();
    } catch (reason) { setError(reason.message || '保存失败'); }
    finally { setBusy(false); }
  }

  return <form onSubmit={save} className="flex flex-col gap-6 settings-page">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold tracking-[.16em] text-primary">DEVELOPER / PROVIDERS</p><h2 className="mt-2 text-2xl font-semibold tracking-tight">供应商配置</h2><p className="mt-2 text-sm text-muted-foreground">调试服务密钥与数据源优先级。</p></div><Button type="button" variant="outline" onClick={load} disabled={busy}><RotateCcw data-icon="inline-start" />重新读取</Button></div>
    {error ? <p role="alert" className="text-sm text-destructive">{error}</p> : null}
    {notice ? <p role="status" className="text-sm text-primary">{notice}</p> : null}
    <div className="settings-advanced-content"><p className="text-sm text-muted-foreground">以下配置保存在 Spark 的 config.yml。已有密钥不会回传到浏览器。</p>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><KeyRound data-icon="inline-start" />API 密钥</CardTitle><CardDescription>输入新密钥并保存会替换旧值。空输入框不会修改已保存的密钥；点“清除”后保存会删除对应值。</CardDescription></CardHeader><CardContent><FieldGroup>{KEY_FIELDS.map(([id, label, hint]) => {
      const status = settings?.credentials?.[id];
      const clearing = keys[id] === null;
      return <Field key={id}><div className="flex flex-wrap items-center justify-between gap-2"><FieldLabel htmlFor={`setting-${id}`}>{label}</FieldLabel><div className="flex items-center gap-2"><span className="text-xs text-muted-foreground">{hint}</span><Badge variant={clearing ? 'outline' : status?.configured ? 'secondary' : 'outline'}>{clearing ? '待清除' : status?.stored ? '已保存' : status?.environment ? '环境变量' : '未配置'}</Badge></div></div><div className="flex gap-2"><InputGroup><InputGroupInput id={`setting-${id}`} autoComplete="off" spellCheck="false" type={visible[id] ? 'text' : 'password'} value={keys[id] || ''} onChange={event => setKeys(previous => ({ ...previous, [id]: event.target.value }))} placeholder={status?.configured ? '已配置；输入新值可替换' : '输入密钥'} /><InputGroupAddon align="inline-end"><InputGroupButton type="button" aria-label={visible[id] ? `隐藏${label}密钥` : `显示${label}密钥`} size="icon-xs" onClick={() => setVisible(previous => ({ ...previous, [id]: !previous[id] }))}>{visible[id] ? <EyeOff /> : <Eye />}</InputGroupButton></InputGroupAddon></InputGroup><Button type="button" variant="outline" disabled={!status?.stored && !keys[id]} onClick={() => setKeys(previous => ({ ...previous, [id]: null }))}>清除</Button></div></Field>;
    })}</FieldGroup></CardContent></Card>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><Settings2 data-icon="inline-start" />数据源优先级</CardTitle><CardDescription>每类能力从第 1 个有有效结果的来源选推荐项；来源无报价、查询失败或结果不符合时依次回退。所有已取得结果仍会显示。</CardDescription></CardHeader><CardContent className="flex flex-col gap-6">{GROUPS.map(([group, title, labels]) => <section key={group} aria-label={`${title}来源优先级`} className="flex flex-col gap-2"><h2 className="font-medium">{title}</h2><div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>顺位</TableHead><TableHead>工具来源</TableHead><TableHead className="text-right">调整</TableHead></TableRow></TableHeader><TableBody>{(priorities[group] || []).map((id, index, items) => <TableRow key={id}><TableCell><Badge variant={index === 0 ? 'default' : 'outline'}>第 {index + 1} 位</Badge></TableCell><TableCell>{labels[id] || id}</TableCell><TableCell className="text-right"><div className="flex justify-end gap-1"><Button type="button" size="icon-sm" variant="outline" disabled={index === 0 || busy} aria-label={`上移${labels[id] || id}`} onClick={() => move(group, index, -1)}><ArrowUp /></Button><Button type="button" size="icon-sm" variant="outline" disabled={index === items.length - 1 || busy} aria-label={`下移${labels[id] || id}`} onClick={() => move(group, index, 1)}><ArrowDown /></Button></div></TableCell></TableRow>)}</TableBody></Table></div></section>)}</CardContent><CardFooter className="justify-end"><Button type="submit" disabled={busy || !settings}><Save data-icon="inline-start" />{busy ? '保存中…' : '保存设置'}</Button></CardFooter></Card>
    </div>
  </form>;
}
