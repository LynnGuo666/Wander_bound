import React, { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, BookOpen, Camera, Check, Film, ImagePlus, LoaderCircle, RefreshCw, Save, Sparkles } from 'lucide-react';
import { PrivateMedia } from '../components/PrivateMedia.jsx';
import { cityArtwork, mediaRequest, tripDate, tripTitle } from '../lib/media.js';

const NOTE_PREFIX = 'travel-journal-v1:';
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

function readNote(id) {
  try { return localStorage.getItem(`${NOTE_PREFIX}${id}`) || ''; } catch { return ''; }
}

function statusText(work) {
  return work.status === 'succeeded' ? '已完成' : work.status === 'failed' ? '生成失败' : work.progressLabel || '正在生成';
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
  const [works, setWorks] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [styles, setStyles] = useState([]);
  const [styleId, setStyleId] = useState('watercolor');
  const [photoId, setPhotoId] = useState('');
  const [title, setTitle] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const activeTrip = useRef('');

  async function refreshPrivate(id) {
    if (!token) { setWorks([]); setSelectedIds([]); return; }
    try {
      const [workResult, selection, catalog] = await Promise.all([
        mediaRequest(`/api/media/trips/${id}/works`, token),
        mediaRequest(`/api/media/trips/${id}/selected-photos`, token),
        mediaRequest('/api/media/scrapbook-styles', token),
      ]);
      if (activeTrip.current !== id) return;
      setWorks(workResult.works || []);
      setSelectedIds(selection.photoIds || []);
      setStyles(catalog.styles || []);
      setError('');
    } catch (reason) { if (activeTrip.current === id) setError(reason.message); }
  }

  useEffect(() => {
    if (!trip) { activeTrip.current = ''; setDetail(null); return; }
    const id = trip.id;
    activeTrip.current = id;
    const controller = new AbortController();
    setDetail(null); setNote(readNote(id)); setWorks([]); setSelectedIds([]); setError(''); setNotice(''); setPhotoId('');
    fetch(`/api/trips/${encodeURIComponent(id)}`, { signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error('旅途暂时无法读取'); return response.json(); })
      .then(result => { if (!controller.signal.aborted) { setDetail(result); setPhotoId(result.photos?.[0]?.id || ''); } })
      .catch(reason => { if (!controller.signal.aborted) setError(reason.message); });
    refreshPrivate(id);
    return () => controller.abort();
  }, [trip?.id, token]);

  function saveNote(value) {
    setNote(value);
    if (!trip) return;
    try { localStorage.setItem(`${NOTE_PREFIX}${trip.id}`, value); }
    catch { setError('日记未能保存在当前浏览器'); }
  }

  function turn(direction) {
    setIndex(previous => Math.min(Math.max(previous + direction, 0), pages.length - 1));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function chooseMode(next) {
    if (next === 'random') {
      const choices = allPages.filter(item => item.id !== randomId);
      const pool = choices.length ? choices : allPages;
      setRandomId(pool[Math.floor(Math.random() * pool.length)]?.id || null);
    }
    if (next === 'city') setFocusCity(cityKey(trip?.plan?.destination || allPages[0]?.plan?.destination));
    setIndex(0); setMode(next);
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
  }, [pages.length]);

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
      setTitle(''); await refreshPrivate(trip.id);
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }

  if (!allPages.length) return <div className="travel-page page-enter"><div className="page-intro"><span className="section-kicker">THE TRAVEL JOURNAL</span><h1>旅途，是可以翻阅的。</h1><p>完成一趟行程后，它会成为手账本里的第一页。</p></div><div className="empty-panel"><BookOpen /><h2>还没有可以翻阅的旅途</h2><p>先到“行程”页规划并完成一次旅行吧。</p></div></div>;
  return <div className="travel-page page-enter">
    <div className="page-intro travel-intro"><div><span className="section-kicker">THE TRAVEL JOURNAL</span><h1>把日子，装订成故事。</h1><p>每一页都是一段旅程。照片、作品和你亲手写下的心情，都留在这里。</p></div><span className="journal-volume">VOL. {String(index + 1).padStart(2, '0')}</span></div>
    <div className="binder-shell"><div className="binder-content"><nav className="page-turn" aria-label="翻阅旅途"><button onClick={() => turn(-1)} disabled={index === 0 || !pages.length} aria-label="上一页"><ArrowLeft size={18} /> 上一页</button><span>{pages.length ? `第 ${index + 1} 页 / 共 ${pages.length} 页` : '暂无匹配的记忆'}</span><button onClick={() => turn(1)} disabled={index === pages.length - 1 || !pages.length} aria-label="下一页">下一页 <ArrowRight size={18} /></button></nav>
    {!pages.length ? <div className="empty-panel binder-empty"><BookOpen /><h2>今天还没有旧旅途</h2><p>没有往年今天的行程记录。可以切换右侧标签，继续翻阅其他故事。</p></div> : <article className="journal-book" key={trip.id}><div className="journal-spine" aria-hidden="true" /><div className="journal-page journal-visual"><div className="journal-label">TRAVEL NOTES · {String(index + 1).padStart(2, '0')}</div><div className="journal-cover"><img src={cityArtwork(trip)} alt={`${tripTitle(trip)}的风格化城市插画`} /><div><span>一场值得记住的旅行</span><h2>{tripTitle(trip)}</h2><small>{tripDate(trip)}</small></div></div><div className="journal-sticker" aria-hidden="true" /><div className="journal-photo-header"><Camera size={17} /> 沿途的画面 <span>{detail?.photos?.length || 0} 张照片</span></div>
      {detail?.photos?.length && token ? <div className="journal-photo-grid">{detail.photos.slice(0, 4).map((photo, photoIndex) => <figure key={photo.id} className={`polaroid polaroid-${photoIndex % 3}`}><PrivateMedia url={`/api/media/photos/${photo.id}`} token={token} alt={`${tripTitle(trip)}的旅途照片`} /><figcaption>{photo.capturedDay || '旅途片刻'}</figcaption></figure>)}</div> : <div className="journal-photo-empty"><ImagePlus /><p>{!token ? '连接私有相册后，照片就会出现在这一页。' : '这趟旅程还没有上传照片。'}</p>{!token ? <button className="text-button" onClick={onOpenSettings}>前往设置 <ArrowRight size={14} /></button> : null}</div>}
    </div><div className="journal-page journal-words"><div className="journal-date"><span>{trip.plan?.destination || '旅途'}</span><span>{trip.plan?.startDate || ''}</span></div><span className="section-kicker">DEAR DIARY</span><h2>写给这段旅程</h2><p className="journal-note-hint">写下路上的一个瞬间、一顿饭，或是只属于你的感受。</p><label className="sr-only" htmlFor="journal-note">旅行日记</label><textarea id="journal-note" className="journal-note" value={note} onChange={event => saveNote(event.target.value)} placeholder="那天走进这座城市的时候，我记得……" /><p className="journal-saved"><Save size={14} /> 日记保存在此浏览器</p>
      {priorCityTrips.length ? <aside className="same-city-note"><span className="section-kicker">SAME CITY, ANOTHER TIME</span><h3>你还来过{trip.plan?.destination}</h3><p>过去 {priorCityTrips.length} 次旅程里，{rememberedStops.length ? '这些地点这次没有排进日程：' : '你留下了不同的路线和回忆。'}</p>{rememberedStops.length ? <div>{rememberedStops.map(name => <span key={name}>{name}</span>)}</div> : null}<button type="button" className="text-button" onClick={() => chooseMode('city')}>翻看同城记忆 <ArrowRight size={15} /></button></aside> : null}
      <div className="journal-works"><div className="journal-photo-header"><Sparkles size={17} /> 旅途作品 <button type="button" onClick={() => refreshPrivate(trip.id)} disabled={!token} aria-label="刷新作品"><RefreshCw size={15} /></button></div>{works.length ? <div className="work-list">{works.map(work => <div className="work-item" key={work.id}><div className="work-item-title">{work.kind === 'memory' ? <Film size={17} /> : <Sparkles size={17} />}<strong>{work.title || (work.kind === 'memory' ? '回忆短片' : '风格手账')}</strong><span>{statusText(work)}</span></div>{work.status === 'succeeded' ? work.kind === 'memory' ? <PrivateMedia video url={`/api/media/memories/${work.id}/video`} token={token} className="work-video" /> : <PrivateMedia url={`/api/media/generation-jobs/${work.id}/image`} token={token} alt={`${tripTitle(trip)}的风格手账`} className="work-image" /> : work.error ? <p className="form-error">{work.error}</p> : null}</div>)}</div> : <p className="quiet-copy">{token ? '还没有生成作品。可以从下方选一张照片制作手账。' : '连接私有相册后查看已生成作品。'}</p>}</div>
    </div></article>}
    </div><nav className="binder-tabs" aria-label="旅途索引"><button className={mode === 'timeline' ? 'active' : ''} onClick={() => chooseMode('timeline')}>按日程</button><button className={mode === 'random' ? 'active' : ''} onClick={() => chooseMode('random')}>随机一页</button><button className={mode === 'today' ? 'active' : ''} onClick={() => chooseMode('today')}>过往的今天</button><button className={mode === 'city' ? 'active' : ''} onClick={() => chooseMode('city')}>同城记忆</button></nav></div>
    {pages.length && token && detail?.photos?.length ? <section className="journal-create"><div><span className="section-kicker">CREATE A KEEPSAKE</span><h2>从照片做一页手账</h2><p>先明确选入要使用的照片，再选择风格。生成仅使用当前旅程的私有照片。</p></div><div className="selection-list">{detail.photos.map(photo => <label key={photo.id}><input type="checkbox" checked={selectedIds.includes(photo.id)} onChange={event => setSelectedIds(previous => event.target.checked ? [...previous, photo.id] : previous.filter(id => id !== photo.id))} /><span>{photo.capturedDay || '未标注日期'} · {photo.id.slice(0, 8)}</span>{selectedIds.includes(photo.id) ? <Check size={15} /> : null}</label>)}<button type="button" className="outline-button" disabled={busy} onClick={saveSelection}>保存精选照片</button></div><form onSubmit={createScrapbook} className="create-form"><label>选择照片<select value={photoId} onChange={event => setPhotoId(event.target.value)}>{detail.photos.map(photo => <option key={photo.id} value={photo.id}>{photo.capturedDay || '旅行照片'} · {photo.id.slice(0, 8)}</option>)}</select></label><label>手账风格<select value={styleId} onChange={event => setStyleId(event.target.value)}>{styles.length ? styles.map(style => <option key={style.id} value={style.id}>{style.name}</option>) : <option value="watercolor">水彩</option>}</select></label><label>标题（可选）<input value={title} onChange={event => setTitle(event.target.value)} maxLength={32} placeholder="例如，初见成都" /></label><button className="solid-button" type="submit" disabled={busy || !photoId || !selectedIds.includes(photoId)}>{busy ? <LoaderCircle size={17} className="spin" /> : <Sparkles size={17} />}制作手账</button></form><p className="quiet-copy">短片的分镜与成片流程仍在完善；这里会展示已有的短片作品。</p></section> : null}
    {notice ? <p className="form-success" role="status">{notice}</p> : null}{error ? <p className="form-error" role="alert">{error}</p> : null}
    {pages.length ? <nav className="page-turn page-turn-bottom" aria-label="翻阅旅途"><button onClick={() => turn(-1)} disabled={index === 0}><ArrowLeft size={18} /> 上一页</button><span>{index + 1} / {pages.length}</span><button onClick={() => turn(1)} disabled={index === pages.length - 1}>下一页 <ArrowRight size={18} /></button></nav> : null}
  </div>;
}
