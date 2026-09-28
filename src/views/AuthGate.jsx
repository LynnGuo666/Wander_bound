import React, { useState } from 'react';
import { Compass } from 'lucide-react';

export default function AuthGate({ onAuthenticated }) {
  const [registering, setRegistering] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [invite, setInvite] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const response = await fetch(`/api/auth/${registering ? 'register' : 'login'}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, ...(registering ? { invite } : {}) }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '登录失败');
      onAuthenticated(result);
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }

  return <main className="auth-screen"><div className="auth-card">
    <span className="auth-mark"><Compass size={27} /></span>
    <p className="section-kicker">TRAVEL STORIES</p><h1>欢迎来到行驿</h1>
    <p>登录后，行程、照片与日记只对你的账号可见。</p>
    <form onSubmit={submit} className="auth-form">
      <label>用户名<input autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required /></label>
      <label>密码<input type="password" autoComplete={registering ? 'new-password' : 'current-password'} value={password} onChange={event => setPassword(event.target.value)} required /></label>
      {registering ? <label>邀请码<input type="password" autoComplete="off" value={invite} onChange={event => setInvite(event.target.value)} required /></label> : null}
      {error ? <p role="alert" className="form-error">{error}</p> : null}
      <button className="solid-button" type="submit" disabled={busy}>{busy ? '请稍候…' : registering ? '创建账号' : '登录'}</button>
    </form>
    <button className="text-button" type="button" onClick={() => { setRegistering(!registering); setError(''); }}>
      {registering ? '已有账号？返回登录' : '有邀请码？创建账号'}
    </button>
  </div></main>;
}
