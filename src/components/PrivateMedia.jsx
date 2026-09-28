import React, { useEffect, useState } from 'react';
import { apiFetch } from '../lib/api.js';

export function PrivateMedia({ url, token, alt = '', className = '', video = false }) {
  const [source, setSource] = useState('');
  const [error, setError] = useState(false);
  useEffect(() => {
    if (!url || !token) { setSource(''); return; }
    const controller = new AbortController();
    let objectUrl = '';
    setSource(''); setError(false);
    apiFetch(url, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(String(response.status)); return response.blob(); })
      .then(blob => { if (!controller.signal.aborted) { objectUrl = URL.createObjectURL(blob); setSource(objectUrl); } })
      .catch(() => { if (!controller.signal.aborted) setError(true); });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [url, token]);
  if (error) return <span className="media-placeholder">暂时无法加载</span>;
  if (!source) return <span className="media-placeholder">{token ? '正在加载…' : '连接私有相册后可查看'}</span>;
  return video ? <video className={className} src={source} controls preload="metadata" playsInline />
    : <img className={className} src={source} alt={alt} loading="lazy" />;
}
