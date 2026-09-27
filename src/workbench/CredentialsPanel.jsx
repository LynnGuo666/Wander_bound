import React, { useState } from 'react';
import { Eye, EyeOff, KeyRound } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group';

const FIELDS = [
  ['stepfun', 'Step Plan', '模型循环'],
  ['amap', '高德 Web', '地点、餐饮和路线'],
  ['dida', '道旅 MCP', '酒店候选'],
  ['duffel', 'Duffel', '航班报价'],
  ['tuniu', '途牛 MCP', '机票、火车票与门票'],
  ['flyai', '飞猪 FlyAI', '机票、火车票与景点；可试用'],
];

export default function CredentialsPanel({ credentials, setCredentials, serverModelConfigured }) {
  const [open, setOpen] = useState(false);
  const [visible, setVisible] = useState({});
  const count = FIELDS.filter(([name]) => credentials[name]).length;
  return <Card><Collapsible open={open} onOpenChange={setOpen}>
    <CardHeader><CollapsibleTrigger render={<Button variant="ghost" className="w-full justify-between" />}><span className="flex items-center gap-2"><KeyRound data-icon="inline-start" /> 单次请求凭据</span><Badge variant="secondary">{count ? `${count} 项已填` : serverModelConfigured ? '模型由服务端配置' : '可选'}</Badge></CollapsibleTrigger><CardDescription>只在当前页面内存中保存，提交时经同源私网接口发送至 Spark。</CardDescription></CardHeader>
    <CollapsibleContent><CardContent><FieldGroup>{FIELDS.map(([name, label, hint]) => <Field key={name}><FieldLabel htmlFor={`key-${name}`}>{label}<span className="ml-auto text-xs font-normal text-muted-foreground">{hint}</span></FieldLabel><InputGroup><InputGroupInput id={`key-${name}`} autoComplete="off" spellCheck="false" type={visible[name] ? 'text' : 'password'} value={credentials[name] || ''} onChange={event => setCredentials(previous => ({ ...previous, [name]: event.target.value }))} placeholder="本次请求填写" /><InputGroupAddon align="inline-end"><InputGroupButton aria-label={visible[name] ? `隐藏${label}密钥` : `显示${label}密钥`} size="icon-xs" onClick={() => setVisible(previous => ({ ...previous, [name]: !previous[name] }))}>{visible[name] ? <EyeOff /> : <Eye />}</InputGroupButton></InputGroupAddon></InputGroup></Field>)}</FieldGroup><p className="mt-4 text-xs text-muted-foreground">请仅通过本机 SSH 隧道、队伍私网或 HTTPS 页面填写。</p></CardContent></CollapsibleContent>
  </Collapsible></Card>;
}
