import React, { useCallback, useEffect, useState } from 'react';
import { Database, RefreshCw, Settings2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const ROWS = [
  { id: 'flyai-flight', ability: '飞机票', provider: '飞猪 FlyAI', protocol: 'Docker OTA MCP', tool: 'flyai_search_flight', source: 'flyai', data: 'flights', label: '飞猪 FlyAI' },
  { id: 'tuniu-flight', ability: '飞机票', provider: '途牛', protocol: 'Docker OTA MCP → 途牛 MCP', tool: 'tuniu_search_flight', source: 'tuniu', data: 'flights', label: '途牛 MCP' },
  { id: 'duffel-flight', ability: '飞机票', provider: 'Duffel', protocol: 'REST API', tool: 'offer_requests', source: 'duffel', data: 'flights', label: 'Duffel', description: '按出发地、目的地、日期查询航班报价；由服务端 REST 适配器实现。' },
  { id: 'flyai-train', ability: '火车票', provider: '飞猪 FlyAI', protocol: 'Docker OTA MCP', tool: 'flyai_search_train', source: 'flyai', data: 'trains', label: '飞猪 FlyAI' },
  { id: 'tuniu-train', ability: '火车票', provider: '途牛', protocol: 'Docker OTA MCP → 途牛 MCP', tool: 'tuniu_search_train', source: 'tuniu', data: 'trains', label: '途牛 MCP' },
  { id: '12306-direct', ability: '火车票 / 余票', provider: '12306 社区 MCP', protocol: 'Docker 12306 MCP', tool: 'get-tickets', source: 'rail12306', data: 'trains', label: '12306 MCP（社区）' },
  { id: '12306-transfer', ability: '中转换乘', provider: '12306 社区 MCP', protocol: 'Docker 12306 MCP', tool: 'get-interline-tickets', source: 'rail12306', data: 'trains', label: '12306 MCP（社区）' },
  { id: 'flyai-poi', ability: '景点与门票', provider: '飞猪 FlyAI', protocol: 'Docker OTA MCP', tool: 'flyai_search_poi', source: 'flyai', data: 'attractionOffers', label: '飞猪 FlyAI' },
  { id: 'tuniu-ticket', ability: '景点与门票', provider: '途牛', protocol: 'Docker OTA MCP → 途牛 MCP', tool: 'tuniu_search_ticket', source: 'tuniu', data: 'attractionOffers', label: '途牛 MCP' },
  { id: 'dida-hotel', ability: '酒店', provider: '道旅', protocol: '道旅 MCP', tool: 'searchHotels', source: 'dida', data: 'hotels', label: '道旅', description: '按目的地、入住日期和预算查询酒店；连接后通过 tools/list 展示上游描述。' },
  { id: 'amap-place', ability: '地点', provider: '高德', protocol: 'Web REST API', tool: '/v3/place/text', source: 'amap', data: 'itinerary', label: '高德', description: '搜索目的地 POI；深圳还可使用本地编辑目录。' },
  { id: 'amap-food', ability: '餐饮', provider: '高德', protocol: 'Web REST API', tool: '/v3/place/around', source: 'amap', data: 'dining', label: '高德', description: '按行程末站周边查询餐饮 POI，保留评分与人均的来源。' },
  { id: 'amap-route', ability: '地面交通', provider: '高德', protocol: 'Web REST API', tool: '/v3/direction/*', source: 'amap', data: 'groundJourneys', label: '高德', description: '查询步行和公交线路、时长、换乘信息。' },
];

function resultCount(plan, row) {
  if (!plan) return '尚未运行';
  if (row.data === 'itinerary') return `${plan.itinerary?.reduce((sum, day) => sum + day.stops.filter(stop => stop.source?.includes('高德')).length, 0) || 0} 个高德地点`;
  const rows = row.data === 'flights' ? [...(plan.flights || []), ...(plan.returnFlights || [])]
    : row.data === 'trains' ? [...(plan.trains || []), ...(plan.returnTrains || [])] : plan[row.data] || [];
  return `${rows.filter(item => (item.provider === row.label || row.source === 'amap')
    && (row.source !== 'rail12306' || (row.tool === 'get-tickets' ? item.stops === 0 : item.stops > 0))).length} 条`;
}

function ConnectionState({ row, catalog, plan, onOpenSettings }) {
  const provider = plan?.providerStatus?.[row.source] || catalog?.providers?.[row.source];
  const mcp = row.protocol.includes('MCP');
  const discovery = row.source === 'dida' ? catalog?.connections?.dida?.discovery : row.source === 'rail12306' ? catalog?.connections?.rail?.discovery : catalog?.connections?.ota?.discovery;
  if (mcp && discovery === 'failed') return <Badge variant="destructive">发现失败</Badge>;
  if (mcp && discovery === 'unavailable') return <Badge variant="outline">MCP 未运行</Badge>;
  if (!provider?.configured) return ['tuniu', 'dida', 'duffel', 'amap'].includes(row.source)
    ? <Button type="button" size="xs" variant="link" onClick={onOpenSettings}><Settings2 data-icon="inline-start" />去设置密钥</Button>
    : <Badge variant="outline">未配置</Badge>;
  if (provider?.error) return <Badge variant="destructive">查询失败</Badge>;
  if (plan && provider?.result === 'ok') return <Badge>本次查询成功</Badge>;
  if (provider?.partialError) return <Badge variant="secondary">部分成功</Badge>;
  return <Badge variant="secondary">已连接，待查询</Badge>;
}

function SchemaDialog({ selected, onClose }) {
  const schema = selected?.tool?.inputSchema;
  const properties = Object.entries(schema?.properties || {});
  const required = new Set(schema?.required || []);
  return <Dialog open={Boolean(selected)} onOpenChange={open => { if (!open) onClose(); }}><DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl"><DialogHeader><DialogTitle>{selected?.tool?.name || 'MCP 工具'} · 参数</DialogTitle><DialogDescription>{selected?.tool?.description || '此 MCP 没有返回工具说明。'}</DialogDescription></DialogHeader>{properties.length ? <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead>字段</TableHead><TableHead>类型</TableHead><TableHead>必填</TableHead><TableHead>说明与限制</TableHead></TableRow></TableHeader><TableBody>{properties.map(([name, field]) => <TableRow key={name}><TableCell className="font-mono text-xs">{name}</TableCell><TableCell>{field.type || field.anyOf?.map(item => item.type).join(' / ') || '未声明'}{field.items?.type ? `〈${field.items.type}〉` : ''}</TableCell><TableCell><Badge variant={required.has(name) ? 'default' : 'outline'}>{required.has(name) ? '是' : '否'}</Badge></TableCell><TableCell className="max-w-80 whitespace-normal text-sm">{field.description || '未提供说明'}{field.enum?.length ? <p className="mt-1 text-xs text-muted-foreground">可选值：{field.enum.join('、')}</p> : null}{field.default !== undefined ? <p className="mt-1 text-xs text-muted-foreground">默认：{String(field.default)}</p> : null}</TableCell></TableRow>)}</TableBody></Table></div> : <p className="text-sm text-muted-foreground">此工具无需输入参数。</p>}</DialogContent></Dialog>;
}

export default function SourcesView({ plan, onOpenSettings }) {
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectedSchema, setSelectedSchema] = useState(null);
  const refresh = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await fetch('/api/capabilities', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
      setCatalog(result);
    } catch (reason) { setError(reason.message || '能力发现失败'); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);
  const otaTools = catalog?.connections?.ota?.tools || [];
  const didaTools = catalog?.connections?.dida?.tools || [];
  const railTools = catalog?.connections?.rail?.tools || [];
  const discovered = otaTools.length + didaTools.length + railTools.length;
  return <div className="flex flex-col gap-6">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-semibold tracking-[.16em] text-primary">DATA CAPABILITIES</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">能力与数据来源</h1><p className="mt-2 text-sm text-muted-foreground">每一行对应一个真实接入路径。MCP 工具名称、说明与参数来自当前连接的 tools/list；REST 行明确标注为服务端适配器。</p></div><Button variant="outline" onClick={refresh} disabled={loading}><RefreshCw data-icon="inline-start" className={loading ? 'animate-spin' : undefined} />重新发现</Button></div>
    <div className="flex flex-wrap gap-2"><Badge variant="secondary">MCP 实时发现 {discovered} 个工具</Badge><Badge variant="outline">OTA Docker：{catalog?.connections?.ota?.discovery || '读取中'}</Badge><Badge variant="outline">12306 MCP：{catalog?.connections?.rail?.discovery || '读取中'}</Badge><Badge variant="outline">道旅 MCP：{catalog?.connections?.dida?.discovery || '读取中'}</Badge>{catalog?.checkedAt ? <span className="text-xs text-muted-foreground">发现时间 {new Date(catalog.checkedAt).toLocaleString('zh-CN')}</span> : null}</div>
    {error ? <p className="text-sm text-destructive" role="alert">{error}</p> : null}
    <Card><CardHeader><CardTitle>能力清单</CardTitle><CardDescription>“已发现”只代表工具元数据真实存在；“本次查询成功”和数据数量来自实际规划结果。</CardDescription></CardHeader><CardContent><Table><TableHeader><TableRow><TableHead>数据能力</TableHead><TableHead>供应商 / 协议</TableHead><TableHead>真实工具与说明</TableHead><TableHead>连接状态</TableHead><TableHead className="text-right">本次结果</TableHead></TableRow></TableHeader><TableBody>{ROWS.map(row => {
      const tool = (row.source === 'dida' ? didaTools : row.source === 'rail12306' ? railTools : otaTools).find(item => item.name === row.tool);
      const isMcp = row.protocol.includes('MCP');
      return <TableRow key={row.id}><TableCell className="font-medium">{row.ability}</TableCell><TableCell><div className="flex flex-col gap-1"><span>{row.provider}</span><span className="text-xs text-muted-foreground">{row.protocol}</span></div></TableCell><TableCell className="min-w-72"><div className="flex flex-col gap-1"><code className="text-xs text-primary">{row.tool}</code><span className="text-xs leading-5 text-muted-foreground">{tool?.description || (isMcp ? '连接未返回该工具说明；仅列出本项目尝试调用的工具名。' : row.description)}</span>{tool?.inputSchema ? <Button type="button" variant="link" size="xs" className="w-fit" onClick={() => setSelectedSchema({ row, tool })}>查看 MCP 参数</Button> : null}</div></TableCell><TableCell><ConnectionState row={row} catalog={catalog} plan={plan} onOpenSettings={onOpenSettings} /></TableCell><TableCell className="text-right text-xs tabular-nums">{resultCount(plan, row)}</TableCell></TableRow>;
    })}</TableBody></Table></CardContent></Card>
    <Card size="sm"><CardHeader><CardTitle className="flex items-center gap-2"><Database data-icon="inline-start" /> 元数据与结果的区别</CardTitle><CardDescription>OTA MCP 的六个只读工具由本项目封装；12306 是社区实现，直连其运行时 tools/list，并查询直达与中转余票。途牛和道旅仍需对应认证。工具发现不等于查询成功，也不代表铁路官方提供 MCP。</CardDescription></CardHeader></Card>
    <SchemaDialog selected={selectedSchema} onClose={() => setSelectedSchema(null)} />
  </div>;
}
