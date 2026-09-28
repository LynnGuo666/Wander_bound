import React, { useState } from 'react';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { apiFetch } from '../lib/api.js';

export default function SettingsView({ user, onLogout, health, onOpenDebug }) {
  const [invite, setInvite] = useState('');
  const [error, setError] = useState('');
  async function createInvite() {
    setError('');
    try {
      const response = await apiFetch('/api/auth/invites', { method: 'POST' });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || '创建失败');
      setInvite(result.invite);
    } catch (reason) { setError(reason.message); }
  }
  return <div className="flex flex-col gap-6 settings-page">
    <div><p className="text-xs font-semibold tracking-[.16em] text-primary">YOUR SETTINGS</p><h1 className="mt-2 text-3xl font-semibold tracking-tight">设置</h1><p className="mt-2 text-sm text-muted-foreground">管理行驿账号和私有数据。</p></div>
    <Card><CardHeader><CardTitle className="flex items-center gap-2"><ShieldCheck size={18} />我的账号</CardTitle><CardDescription>行程、照片、作品和日记仅对当前账号可见。</CardDescription></CardHeader><CardContent className="space-y-3"><p>用户名：{user?.username || '读取中'} · {user?.role === 'admin' ? '管理员' : '成员'}</p><p className="text-xs text-muted-foreground">服务：{health?.ok ? '已连接' : '暂时不可用'}</p><Button type="button" variant="outline" onClick={onLogout}>退出登录</Button></CardContent></Card>
    {user?.role === 'admin' ? <Card><CardHeader><CardTitle>邀请成员</CardTitle><CardDescription>每个邀请码仅能使用一次。请通过安全渠道交给受邀者。</CardDescription></CardHeader><CardContent className="space-y-3"><Button type="button" onClick={createInvite}>生成邀请码</Button>{invite ? <div><label htmlFor="new-invite" className="text-sm">邀请码</label><input id="new-invite" className="settings-token-input" readOnly value={invite} onFocus={event => event.target.select()} /></div> : null}{error ? <p role="alert">{error}</p> : null}</CardContent></Card> : null}
    {user?.role === 'admin' ? <div className="settings-debug-link"><span>项目维护</span><button type="button" className="text-button" onClick={onOpenDebug}>高级设置 <ArrowRight size={15} /></button></div> : null}
  </div>;
}
