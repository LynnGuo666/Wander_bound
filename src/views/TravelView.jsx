import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, BookOpen, Check, LoaderCircle, Sparkles, X } from 'lucide-react';
import JournalStudio from '../components/JournalStudio.jsx';
import { mediaRequest, tripTitle } from '../lib/media.js';
import { apiFetch } from '../lib/api.js';

const cityKey = value => String(value || '').trim().replace(/市$/, '');

function happenedOnThisDay(trip) {
  const start = trip.plan?.startDate;
  const end = trip.plan?.endDate || start;
  if (!start) return false;
  const today = new Date();
  const currentYear = today.getFullYear();
  const day = new Date(`${start}T12:00:00`);
  const last = new Date(`${end}T12:00:00`);
  for (let count = 0; count < 30 && day <= last; count++, day.setDate(day.getDate() + 1)) {
    if (day.getFullYear() < currentYear && day.getMonth() === today.getMonth() && day.getDate() === today.getDate()) return true;
  }
  return false;
}

export default function TravelView({ trips, token, onOpenSettings }) {
  const allPages = trips.filter(trip => trip.plan || trip.status === 'ended')
    .sort((a, b) => (b.plan?.startDate || b.createdAt || '').localeCompare(a.plan?.startDate || a.createdAt || ''));
  const [mode, setMode] = useState('timeline');
  const [randomId, setRandomId] = useState(null);
  const [focusCity, setFocusCity] = useState('');
  const pages = mode === 'today' ? allPages.filter(happenedOnThisDay)
    : mode === 'random' ? allPages.filter(item => item.id === randomId)
      : mode === 'city' ? allPages.filter(item => cityKey(item.plan?.destination) === focusCity)
        : allPages;
  const [index, setIndex] = useState(0);
  const trip = pages[Math.min(index, Math.max(pages.length - 1, 0))];
  const [detail, setDetail] = useState(null);
  const [note, setNote] = useState('');
  const noteVersion = useRef(0);
  const noteSave = useRef(Promise.resolve());
  const noteTimer = useRef(null);
  const [works, setWorks] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [privateReadyTrip, setPrivateReadyTrip] = useState('');
  const [styles, setStyles] = useState([]);
  const [styleId, setStyleId] = useState('watercolor');
  const [photoId, setPhotoId] = useState('');
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [turnDirection, setTurnDirection] = useState('');
  const turnTimer = useRef(null);
  const pendingIndex = useRef(null);
  const activeTrip = useRef('');

  async function refreshPrivate(id) {
    if (!token) { setWorks([]); setSelectedIds([]); setPrivateReadyTrip(id); return; }
    try {
      const [workResult, selection, catalog] = await Promise.all([
        mediaRequest(`/api/media/trips/${id}/works`, token),
        mediaRequest(`/api/media/trips/${id}/selected-photos`, token),
        mediaRequest('/api/media/scrapbook-styles', token),
      ]);
      if (activeTrip.current !== id) return;
      setWorks(workResult.works || []);
      setSelectedIds(selection.photoIds || []);
      setPrivateReadyTrip(id);
      setStyles(catalog.styles || []);
      setError('');
    } catch (reason) { if (activeTrip.current === id) setError(reason.message); }
  }

  useEffect(() => {
    if (!trip) { activeTrip.current = ''; setDetail(null); return; }
    const id = trip.id;
    activeTrip.current = id;
    const controller = new AbortController();
    setDetail(null); setNote(''); setWorks([]); setSelectedIds([]); setPrivateReadyTrip(''); setError(''); setNotice(''); setPhotoId('');
    apiFetch(`/api/trips/${encodeURIComponent(id)}`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error('旅途暂时无法读取'); return response.json(); })
      .then(result => { if (!controller.signal.aborted) { setDetail(result); setPhotoId(result.photos?.[0]?.id || ''); } })
      .catch(reason => { if (!controller.signal.aborted) setError(reason.message); });
    if (token) mediaRequest(`/api/trips/${encodeURIComponent(id)}/note`, token).then(result => {
      if (controller.signal.aborted) return;
      noteVersion.current = result.version;
      setNote(result.text);
    }).catch(reason => { if (!controller.signal.aborted) setError(reason.message); });
    refreshPrivate(id);
    return () => { controller.abort(); clearTimeout(noteTimer.current); };
  }, [trip?.id, token]);

  function saveNote(value) {
    setNote(value);
    if (!trip || !token) return;
    const id = trip.id;
    clearTimeout(noteTimer.current);
    noteTimer.current = setTimeout(() => {
      noteSave.current = noteSave.current.catch(() => {}).then(async () => {
        try {
          const saved = await mediaRequest(`/api/trips/${encodeURIComponent(id)}/note`, token, {
            method: 'PUT', body: JSON.stringify({ text: value, version: noteVersion.current }),
          });
          noteVersion.current = saved.version;
          if (activeTrip.current === id) setError('');
        } catch (reason) { if (activeTrip.current === id) setError(`日记未保存：${reason.message}`); }
      });
    }, 600);
  }

  function turn(direction) {
    if (turnTimer.current) return;
    const next = Math.min(Math.max(index + direction, 0), pages.length - 1);
    if (next === index) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setIndex(next); return; }
    pendingIndex.current = next;
    setTurnDirection(direction > 0 ? 'next' : 'prev');
    turnTimer.current = setTimeout(finishTurn, 4500);
  }

  function finishTurn() {
    if (pendingIndex.current === null) return;
    clearTimeout(turnTimer.current);
    setIndex(pendingIndex.current);
    pendingIndex.current = null;
    setTurnDirection('');
    turnTimer.current = null;
  }

  useEffect(() => () => { if (turnTimer.current) clearTimeout(turnTimer.current); }, []);

  function chooseMode(next) {
    if (next === 'random') {
      const choices = allPages.filter(item => item.id !== randomId);
      const pool = choices.length ? choices : allPages;
      setRandomId(pool[Math.floor(Math.random() * pool.length)]?.id || null);
    }
    if (next === 'city') setFocusCity(cityKey(trip?.plan?.destination || allPages[0]?.plan?.destination));
    if (turnTimer.current) { clearTimeout(turnTimer.current); turnTimer.current = null; pendingIndex.current = null; }
    setIndex(0); setMode(next); setTurnDirection('');
  }

  const currentStops = new Set(trip?.plan?.itinerary?.flatMap(day => day.stops || []).map(stop => stop.name) || []);
  const priorCityTrips = allPages.filter(item => item.id !== trip?.id && cityKey(item.plan?.destination) === cityKey(trip?.plan?.destination)
    && (item.plan?.startDate || '') < (trip?.plan?.startDate || ''));
  const rememberedStops = [...new Set(priorCityTrips.flatMap(item => item.plan?.itinerary?.flatMap(day => day.stops || []).map(stop => stop.name) || []))]
    .filter(name => name && !currentStops.has(name)).slice(0, 5);

  useEffect(() => {
    function onKeyDown(event) {
      if (event.target instanceof HTMLElement && ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)) return;
      if (event.key === 'ArrowLeft') turn(-1);
      if (event.key === 'ArrowRight') turn(1);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [pages.length, index]);

  async function saveSelection() {
    if (!trip) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await mediaRequest(`/api/media/trips/${trip.id}/selected-photos`, token, { method: 'PUT',
        body: JSON.stringify({ photoIds: selectedIds, batchId: `web-${Date.now()}`, source: 'web-journal' }) });
      setNotice('精选照片已保存，可以用它们制作手账。');
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }

  async function createScrapbook(event) {
    event.preventDefault();
    if (!trip || !photoId) return;
    setBusy(true); setError(''); setNotice('');
    try {
      await mediaRequest('/api/media/scrapbooks', token, { method: 'POST',
        body: JSON.stringify({ tripId: trip.id, photoId, styleId, title: title.trim() }) });
      setNotice('手账已开始制作，稍后刷新作品即可查看。');
      setTitle(''); setShowCreate(false); await refreshPrivate(trip.id);
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }

  if (!allPages.length) return <div className="travel-page page-enter"><div className="empty-panel"><BookOpen /><h2>还没有可以翻阅的旅途</h2><p>先到“行程”页规划并完成一次旅行吧。</p></div></div>;
  return <div className="travel-page page-enter">
    <header className="travel-compact-title"><strong>旅途 <span>· {trip ? tripTitle(trip) : '回忆'}</span></strong><small>VOL. {String(index + 1).padStart(2, '0')}</small></header>
    <div className="binder-shell"><div className="binder-content">
      <nav className="page-turn" aria-label="翻阅旅途"><button onPointerDown={() => turn(-1)} onClick={() => turn(-1)} disabled={index === 0 || !pages.length} aria-label="上一页"><ArrowLeft size={18} /> 上一页</button><span>{pages.length ? `${index + 1} / ${pages.length}` : '暂无匹配的记忆'}</span><button onPointerDown={() => turn(1)} onClick={() => turn(1)} disabled={index === pages.length - 1 || !pages.length} aria-label="下一页">下一页 <ArrowRight size={18} /></button></nav>
      {!pages.length ? <div className="empty-panel binder-empty"><BookOpen /><h2>今天还没有旧旅途</h2><p>切换右侧标签，继续翻阅其他故事。</p></div>
        : <JournalStudio key={trip.id} trip={trip} photos={detail?.photos || []} selectedIds={selectedIds} works={works} detailReady={detail?.id === trip.id} privateReady={privateReadyTrip === trip.id} token={token} onOpenSettings={onOpenSettings} onCreateWork={() => setShowCreate(true)} onSameCity={() => chooseMode('city')} sameCityCount={priorCityTrips.length} rememberedStops={rememberedStops} turnDirection={turnDirection} onTurnComplete={finishTurn} nextTrip={pages[index + 1]} previousTrip={pages[index - 1]} note={note} onNoteChange={saveNote} />}
    </div><nav className="binder-tabs" aria-label="旅途索引"><button className={mode === 'timeline' ? 'active' : ''} onClick={() => chooseMode('timeline')}>按日程</button><button className={mode === 'random' ? 'active' : ''} onClick={() => chooseMode('random')}>随机一页</button><button className={mode === 'today' ? 'active' : ''} onClick={() => chooseMode('today')}>过往的今天</button><button className={mode === 'city' ? 'active' : ''} onClick={() => chooseMode('city')}>同城记忆</button></nav></div>
    {showCreate && token && detail?.photos?.length ? <div className="journal-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setShowCreate(false); }}><section className="journal-create journal-modal" role="dialog" aria-modal="true" aria-label="制作手账"><button className="journal-modal-close" onClick={() => setShowCreate(false)} aria-label="关闭"><X size={18} /></button><h2>从照片做一页手账</h2><div className="selection-list">{detail.photos.map(photo => <label key={photo.id}><input type="checkbox" checked={selectedIds.includes(photo.id)} onChange={event => setSelectedIds(previous => event.target.checked ? [...previous, photo.id] : previous.filter(id => id !== photo.id))} /><span>{photo.capturedDay || '未标注日期'} · {photo.id.slice(0, 8)}</span>{selectedIds.includes(photo.id) ? <Check size={15} /> : null}</label>)}<button type="button" className="outline-button" disabled={busy} onClick={saveSelection}>保存精选照片</button></div><form onSubmit={createScrapbook} className="create-form"><label>选择照片<select value={photoId} onChange={event => setPhotoId(event.target.value)}>{detail.photos.map(photo => <option key={photo.id} value={photo.id}>{photo.capturedDay || '旅行照片'} · {photo.id.slice(0, 8)}</option>)}</select></label><label>手账风格<select value={styleId} onChange={event => setStyleId(event.target.value)}>{styles.length ? styles.map(style => <option key={style.id} value={style.id}>{style.name}</option>) : <option value="watercolor">水彩</option>}</select></label><label>标题（可选）<input value={title} onChange={event => setTitle(event.target.value)} maxLength={32} placeholder="例如，初见成都" /></label><button className="solid-button" type="submit" disabled={busy || !photoId || !selectedIds.includes(photoId)}>{busy ? <LoaderCircle size={17} className="spin" /> : <Sparkles size={17} />}制作手账</button></form></section></div> : null}
    {notice ? <p className="travel-toast form-success" role="status">{notice}</p> : null}{error ? <p className="travel-toast form-error" role="alert">{error}</p> : null}
  </div>;
}
