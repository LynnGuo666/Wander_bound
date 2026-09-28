import React from 'react';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export default function SettingsView({ mediaToken, onMediaTokenChange, health, onOpenDebug }) {
  return <div className="flex flex-col gap-6 settings-page">
    <div><p className="text-xs font-semibold tracking-[.16em] text-primary">YOUR SETTINGS</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">设置</h1><p className="mt-2 text-sm text-muted-foreground">连接私有相册，保存旅途里的照片和作品。</p></div>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck size={18} />私有相册</CardTitle><CardDescription>连接后可以在“行程”和“旅途”查看照片与已生成作品。令牌仅保存在当前浏览器会话。</CardDescription></CardHeader><CardContent className="space-y-3"><label htmlFor="media-token" className="text-sm font-medium">媒体访问令牌</label><div className="flex flex-wrap gap-2"><input id="media-token" type="password" autoComplete="off" className="settings-token-input" value={mediaToken} onKeyDown={event => { if (event.key === 'Enter') event.preventDefault(); }} onChange={event => onMediaTokenChange(event.target.value)} placeholder="输入后自动连接当前会话" /><Button type="button" variant="outline" disabled={!mediaToken} onClick={() => onMediaTokenChange('')}>断开连接</Button></div><p className="text-xs text-muted-foreground">规划服务：{health?.ok ? '已连接' : '暂时不可用'} · 私有相册：{mediaToken ? '已填写令牌' : '未连接'}</p></CardContent></Card>
    <div className="settings-debug-link"><span>项目维护</span><button type="button" className="text-button" onClick={onOpenDebug}>开发者调试 <ArrowRight size={15} /></button></div>
  </div>;
}
