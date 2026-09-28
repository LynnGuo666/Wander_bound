import React, { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, ImagePlus, LoaderCircle, Plus, Sparkles, Trash2 } from 'lucide-react';
import templates from '../../workflows/journal-templates.json';
import stickerCategories from '../../workflows/journal-sticker-categories.json';
import { PrivateMedia } from './PrivateMedia.jsx';
import BinderFlipTransition from './BinderFlipTransition.jsx';
import { cityArtwork, mediaRequest, tripDate, tripTitle } from '../lib/media.js';

const STORE_PREFIX = 'travel-journal-layout-v1:';
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const itemId = () => crypto.randomUUID();
function defaultText(trip) {
  try {
    const note = localStorage.getItem(`travel-journal-v1:${trip.id}`);
    if (note) return note;
  } catch { /* Browser storage may be disabled. */ }
  return `${tripTitle(trip)} · ${tripDate(trip)}\n在这里写下旅途中最想留住的一刻。`;
}

function fromTemplate(template, trip, pageIndex, stickerIds = [], stampId = '') {
  let photo = pageIndex * 2;
  let sticker = 0;
  return template.slots.map(slot => ({ ...slot, id: itemId(),
    ...(slot.kind === 'photo' ? { photoIndex: photo++ } : {}),
    ...(slot.kind === 'text' ? { text: defaultText(trip) } : {}),
    ...(slot.kind === 'postcard' ? { text: `${tripTitle(trip)}\n寄给未来的自己`, stampId } : {}),
    ...(slot.kind === 'sticker' && stickerIds.length ? { stickerId: stickerIds[(pageIndex + sticker++) % stickerIds.length] } : {}),
  }));
}
function freshLayout(trip) {
  return [{ templateId: templates[0].id, items: fromTemplate(templates[0], trip, 0) },
    { templateId: templates[3].id, items: fromTemplate(templates[3], trip, 1) }];
}
function loadLayout(trip) {
  try {
    const stored = JSON.parse(localStorage.getItem(`${STORE_PREFIX}${trip.id}`));
    if (Array.isArray(stored) && stored.length === 2 && stored.every(page => Array.isArray(page.items)))
      return stored.map(page => ({ ...page, items: page.items.map(item => item.kind === 'book'
        ? { ...item, kind: 'text', text: defaultText(trip) } : item) }));
  } catch { /* Empty or older local layout. */ }
  return freshLayout(trip);
}
function labelFor(kind) {
  return { cover: '城市插画', photo: '旅途照片', video: '旅途短片', text: '日记', sticker: '千问贴纸', postcard: '明信片', clip: '曲别针', ticket: '车票', boarding: '登机牌' }[kind] || kind;
}
function itineraryMotifs(trip) {
  const city = trip.plan?.destination || tripTitle(trip);
  const stops = (trip.plan?.itinerary || []).flatMap(day => day.stops || [])
    .map(stop => stop.name).filter(Boolean);
  const place = index => stops[index % Math.max(stops.length, 1)] || city;
  return {
    stickers: stickerCategories.slice(0, 5).map((category, index) => category.motif
      .replaceAll('{{city}}', city).replaceAll('{{place}}', place(index))),
    stamp: `${city}${place(0)}的微型风景`,
  };
}

export default function JournalStudio({ trip, photos = [], works = [], token, onOpenSettings, onCreateWork, onSameCity, sameCityCount = 0, rememberedStops = [], turnDirection = "", note = "", onNoteChange }) {
  const [pages, setPages] = useState(() => loadLayout(trip));
  const [selected, setSelected] = useState(null);
  const [stickerJobs, setStickerJobs] = useState([]);
  const [motif, setMotif] = useState('');
  const [toolTab, setToolTab] = useState('layout');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const drag = useRef(null);
  const stageRef = useRef(null);
  const noteApplied = useRef(false);
  const videos = works.filter(work => work.kind === 'memory' && work.status === 'succeeded');

  useEffect(() => {
    try { localStorage.setItem(`${STORE_PREFIX}${trip.id}`, JSON.stringify(pages)); }
    catch { setError('排版未能保存在当前浏览器'); }
  }, [pages, trip.id]);
  useEffect(() => {
    if (!note || noteApplied.current) return;
    noteApplied.current = true;
    setPages(previous => previous.map((page, pageIndex) => ({ ...page,
      items: page.items.map(item => pageIndex === 0 && item.kind === 'text' && item.text === defaultText(trip)
        ? { ...item, text: note } : item),
    })));
  }, [note, trip.id]);
  useEffect(() => {
    if (!token) { setStickerJobs([]); return; }
    let alive = true;
    const refresh = () => mediaRequest(`/api/media/trips/${trip.id}/stickers`, token)
      .then(result => { if (alive) setStickerJobs(result.stickers || []); })
      .catch(reason => { if (alive) setError(reason.message); });
    async function seedTripAssets() {
      try {
        const result = await mediaRequest(`/api/media/trips/${trip.id}/stickers`, token);
        if (!alive) return;
        const current = result.stickers || [];
        setStickerJobs(current);
        const motifs = itineraryMotifs(trip);
        const wanted = [...motifs.stickers.map(next => ({ kind: 'sticker', motif: next })),
          { kind: 'stamp', motif: motifs.stamp }];
        for (const item of wanted) {
          if (!alive) return;
          if (current.some(job => job.kind === item.kind && job.motif === item.motif)) continue;
          const created = await mediaRequest(`/api/media/trips/${trip.id}/stickers`, token,
            { method: 'POST', body: JSON.stringify(item) });
          current.push(created);
          setStickerJobs([...current]);
        }
      } catch (reason) { if (alive) setError(reason.message); }
    }
    seedTripAssets();
    const timer = setInterval(refresh, 5000);
    return () => { alive = false; clearInterval(timer); };
  }, [trip.id, token]);
  useEffect(() => {
    const stickerIds = stickerJobs.filter(job => job.kind === 'sticker' && job.status !== 'failed').map(job => job.id);
    const stampId = stickerJobs.find(job => job.kind === 'stamp' && job.status !== 'failed')?.id;
    if (!stickerIds.length && !stampId) return;
    setPages(previous => {
      let changed = false;
      const next = previous.map(page => ({ ...page, items: page.items.map((item, index) => {
      if (item.kind === 'sticker' && !item.stickerId && stickerIds.length)
        { changed = true; return { ...item, stickerId: stickerIds[index % stickerIds.length] }; }
      if (item.kind === 'postcard' && !item.stampId && stampId)
        { changed = true; return { ...item, stampId }; }
      return item;
      }) }));
      return changed ? next : previous;
    });
  }, [stickerJobs]);

  function updateItem(pageIndex, id, patch) {
    if (typeof patch.text === 'string' && pages[pageIndex]?.items.some(item => item.id === id && item.kind === 'text'))
      onNoteChange?.(patch.text);
    setPages(previous => previous.map((page, index) => index === pageIndex
      ? { ...page, items: page.items.map(item => item.id === id ? { ...item, ...patch } : item) } : page));
  }
  function setTemplate(pageIndex, templateId, stickerIds = []) {
    const template = templates.find(item => item.id === templateId);
    if (!template) return;
    if (!stickerIds.length) stickerIds = stickerJobs.filter(job => job.kind === 'sticker' && job.status !== 'failed').map(job => job.id);
    const stampId = stickerJobs.find(job => job.kind === 'stamp' && job.status !== 'failed')?.id || '';
    setPages(previous => previous.map((page, index) => index === pageIndex
      ? { templateId, items: fromTemplate(template, trip, pageIndex, stickerIds, stampId) } : page));
    setSelected(null);
  }
  function addItem(kind, pageIndex) {
    const count = pages[pageIndex].items.length;
    const item = { id: itemId(), kind, x: 15 + count % 4 * 8, y: 15 + count % 5 * 7,
      w: kind === 'clip' ? 12 : kind === 'sticker' ? 24 : 45,
      h: kind === 'clip' ? 15 : kind === 'text' ? 23 : ['ticket', 'boarding'].includes(kind) ? 23 : 30, r: 0, z: count + 2,
      ...(kind === 'photo' ? { photoIndex: 0 } : {}),
      ...(kind === 'text' || kind === 'postcard' ? { text: kind === 'text' ? defaultText(trip) : `${tripTitle(trip)}\n一张来自旅途的明信片` } : {}),
      ...(kind === 'sticker' && stickerJobs.some(job => job.kind === 'sticker' && job.status !== 'failed') ? { stickerId: stickerJobs.find(job => job.kind === 'sticker' && job.status !== 'failed').id } : {}),
      ...(kind === 'postcard' && stickerJobs.some(job => job.kind === 'stamp' && job.status !== 'failed') ? { stampId: stickerJobs.find(job => job.kind === 'stamp' && job.status !== 'failed').id } : {}),
    };
    setPages(previous => previous.map((page, index) => index === pageIndex ? { ...page, items: [...page.items, item] } : page));
    setSelected({ pageIndex, id: item.id }); setToolTab('edit');
  }
  function onPointerDown(event, pageIndex, item) {
    if (event.button !== 0 || event.target.closest('video')) return;
    const canvas = event.currentTarget.parentElement;
    drag.current = { pageIndex, id: item.id, startX: event.clientX, startY: event.clientY,
      x: item.x, y: item.y, width: canvas.clientWidth, height: canvas.clientHeight };
    event.currentTarget.setPointerCapture(event.pointerId);
    setSelected({ pageIndex, id: item.id }); setToolTab('edit');
  }
  function onPointerMove(event) {
    const state = drag.current;
    if (!state) return;
    updateItem(state.pageIndex, state.id, {
      x: clamp(state.x + (event.clientX - state.startX) / state.width * 100, 0, 100 - 8),
      y: clamp(state.y + (event.clientY - state.startY) / state.height * 100, 0, 100 - 8),
    });
  }
  async function queueSticker(nextMotif, kind = 'sticker') {
    const created = await mediaRequest(`/api/media/trips/${trip.id}/stickers`, token,
      { method: 'POST', body: JSON.stringify({ motif: nextMotif, kind }) });
    setStickerJobs(previous => [created, ...previous]);
    return created.id;
  }
  async function generateSticker(event) {
    event.preventDefault();
    if (!motif.trim()) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const id = await queueSticker(motif.trim());
      const pageIndex = selected?.pageIndex ?? 0;
      const item = { id: itemId(), kind: 'sticker', stickerId: id, x: 67, y: 63,
        w: 24, h: 24, r: -8, z: 20 };
      setPages(previous => previous.map((page, index) => index === pageIndex
        ? { ...page, items: [...page.items, item] } : page));
      setMotif(''); setNotice('千问正在绘制贴纸；完成后会自动出现在纸页上。');
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }
  async function generateCategory(category) {
    setBusy(true); setError(''); setNotice('');
    try {
      const city = trip.plan?.destination || tripTitle(trip);
      const stops = (trip.plan?.itinerary || []).flatMap(day => day.stops || [])
        .map(stop => stop.name).filter(Boolean);
      const place = stops[stickerCategories.findIndex(item => item.id === category.id) % Math.max(stops.length, 1)] || city;
      const nextMotif = category.motif.replaceAll('{{city}}', city).replaceAll('{{place}}', place);
      const id = await queueSticker(nextMotif);
      const pageIndex = selected?.pageIndex ?? 0;
      const item = { id: itemId(), kind: 'sticker', stickerId: id, x: 63, y: 59,
        w: 25, h: 25, r: -7, z: 21 };
      setPages(previous => previous.map((page, index) => index === pageIndex
        ? { ...page, items: [...page.items, item] } : page));
      setNotice(`「${category.name}」已加入纸页，千问绘制完成后会自动显示。`);
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }
  async function aiCompose() {
    setBusy(true); setError(''); setNotice('');
    try {
      const plan = await mediaRequest(`/api/media/trips/${trip.id}/journal/compose`, token, { method: 'POST' });
      const stickerIds = await Promise.all(plan.stickerMotifs.map(nextMotif => queueSticker(nextMotif)));
      const stampId = await queueSticker(plan.stampMotif, 'stamp');
      const layouts = plan.templates.map((id, index) => {
        const template = templates.find(item => item.id === id);
        return { templateId: id, items: fromTemplate(template, trip, index, stickerIds, stampId) };
      });
      setPages(layouts); setSelected(null); setToolTab('stickers');
      setNotice(`StepFun 已挑选「${layouts.map(page => templates.find(t => t.id === page.templateId)?.name).join('」和「')}」，千问正在绘制行程贴纸与邮票。`);
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }
  const active = selected && pages[selected.pageIndex]?.items.find(item => item.id === selected.id);
  function removeActive() {
    if (!selected) return;
    setPages(previous => previous.map((page, index) => index === selected.pageIndex
      ? { ...page, items: page.items.filter(item => item.id !== selected.id) } : page));
    setSelected(null);
  }
  function renderItem(item) {
    if (item.kind === 'cover') return <img src={cityArtwork(trip)} alt={`${tripTitle(trip)}的千问城市插画`} />;
    if (item.kind === 'photo') {
      const photo = photos[item.photoIndex % Math.max(photos.length, 1)];
      const frame = item.photoIndex % 2 ? 'ornate-photo-frame' : 'polaroid-frame';
      return <div className={`studio-prop-wrap studio-photo-${frame}`}><img className="studio-prop" src={`/art/${frame}.png`} alt="千问生成的空白相框" /><div className="studio-photo-slot">{photo && token
        ? <PrivateMedia url={`/api/media/photos/${photo.id}`} token={token} alt="旅途照片" />
        : <span className="studio-empty"><ImagePlus size={20} />{token ? '等待旅途照片' : '连接私有相册'}</span>}</div></div>;
    }
    if (item.kind === 'video') {
      const video = videos[0];
      return <div className="studio-prop-wrap studio-film-prop"><img className="studio-prop" src="/art/film-frame.png" alt="千问生成的胶片框" /><div className="studio-video-slot">{video && token
        ? <PrivateMedia video url={`/api/media/memories/${video.id}/video`} token={token} />
        : <span className="studio-empty">旅途短片将在这里播放</span>}</div></div>;
    }
    if (item.kind === 'sticker') {
      const job = stickerJobs.find(entry => entry.id === item.stickerId);
      return item.stickerId ? job?.status === 'succeeded'
        ? <PrivateMedia url={`/api/media/stickers/${item.stickerId}/image`} token={token} alt={`${job.motif}，千问生成的贴纸`} />
        : <span className="studio-sticker-pending">{job?.status === 'failed' ? '贴纸生成失败' : '千问绘制中…'}</span>
        : <span className="studio-sticker-pending">行程贴纸待生成</span>;
    }
    if (item.kind === 'clip') return <img className="studio-clip-art" src="/art/paperclip.png" alt="千问绘制的曲别针插图" />;
    if (item.kind === 'postcard') {
      const stampId = item.stampId || stickerJobs.find(job => job.kind === 'stamp')?.id;
      const stamp = stickerJobs.find(job => job.id === stampId);
      return <div className="studio-prop-wrap"><img className="studio-prop" src="/art/postcard-blank.png" alt="千问生成的明信片模板" /><span className="studio-postcard-text">{item.text}</span><span className="studio-stamp">{stamp?.status === 'succeeded'
        ? <PrivateMedia url={`/api/media/stickers/${stampId}/image`} token={token} alt={`${stamp.motif}，千问生成的邮票`} />
        : <span>{stamp?.status === 'failed' ? '邮票失败' : '行程邮票绘制中'}</span>}</span></div>;
    }
    if (item.kind === 'ticket' || item.kind === 'boarding') return <div className="studio-prop-wrap"><img className="studio-prop" src={`/art/${item.kind === 'ticket' ? 'rail-ticket-blank' : 'boarding-pass-blank'}.png`} alt={`千问生成的${labelFor(item.kind)}模板`} /><span className="studio-ticket-text">{trip.plan?.originCity || '旅途起点'} → {trip.plan?.destination || tripTitle(trip)}<br />{trip.plan?.startDate || '启程日期'}</span></div>;
    return <div className="studio-text">{item.text}</div>;
  }
  return <section className="studio-shell" aria-label="可编辑的旅途手账">
    <div className="studio-toolbar"><strong>{tripTitle(trip)} <small>{tripDate(trip)}</small></strong><div><button className="solid-button" disabled={!token || busy} onClick={aiCompose}>{busy ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}AI 排版</button>{!token ? <button className="text-button" onClick={onOpenSettings}>连接相册</button> : null}</div></div>
    <div className="studio-workspace">
      <div className="studio-book-stage"><div ref={stageRef} className={`studio-book-spread ${turnDirection ? `turn-${turnDirection}` : ''}`}>{pages.map((page, pageIndex) => <div className="studio-page" key={pageIndex}><div className="studio-canvas" aria-label={`${pageIndex === 0 ? '左' : '右'}页画布`}>
        {page.items.map(item => <div key={item.id} className={`studio-item studio-${item.kind}${selected?.id === item.id ? ' selected' : ''}`}
          role="button" tabIndex={0} aria-label={`${labelFor(item.kind)}，点击编辑，拖动移动`}
          onClick={() => { setSelected({ pageIndex, id: item.id }); setToolTab('edit'); }}
          onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelected({ pageIndex, id: item.id }); setToolTab('edit'); } }}
          onPointerDown={event => onPointerDown(event, pageIndex, item)} onPointerMove={onPointerMove} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
          style={{ left: `${item.x}%`, top: `${item.y}%`, width: `${item.w}%`, height: `${item.h}%`, zIndex: item.z, transform: `rotate(${item.r}deg)` }}>{renderItem(item)}</div>)}
      </div></div>)}{turnDirection ? <BinderFlipTransition direction={turnDirection} stageRef={stageRef} /> : null}</div></div>
      <aside className="studio-tools" aria-label="手账工具"><nav className="studio-tool-tabs" aria-label="手账工具分类">{[['layout','版式'],['add','添加'],['stickers','贴纸'],['edit','编辑'],['works','作品']].map(([id,name]) => <button key={id} type="button" className={toolTab === id ? 'active' : ''} onClick={() => setToolTab(id)}>{name}</button>)}</nav>
        <div className="studio-tool-content">
          {toolTab === 'layout' ? <div className="studio-panel"><h3>选择版式</h3>{pages.map((page, pageIndex) => <label className="studio-select" key={pageIndex}>{pageIndex === 0 ? '左页' : '右页'}<select value={page.templateId} onChange={event => setTemplate(pageIndex, event.target.value)}>{templates.map(template => <option value={template.id} key={template.id}>{template.name}</option>)}</select></label>)}<button className="outline-button" disabled={!token || busy} onClick={aiCompose}><Sparkles size={15} />StepFun 为我排版</button>{sameCityCount ? <div className="studio-city-link"><strong>还来过这座城市 {sameCityCount} 次</strong>{rememberedStops.length ? <small>曾去过：{rememberedStops.slice(0, 2).join('、')}</small> : null}<button className="text-button" onClick={onSameCity}>翻看同城记忆</button></div> : null}</div> : null}
          {toolTab === 'add' ? <div className="studio-panel"><h3>添加到{selected?.pageIndex === 1 ? '右' : '左'}页</h3><div className="studio-add-grid">{['photo', 'video', 'text', 'postcard', 'ticket', 'boarding', 'clip', 'sticker'].map(kind => <button type="button" key={kind} onClick={() => addItem(kind, selected?.pageIndex ?? 0)}><Plus size={13} />{labelFor(kind)}</button>)}</div><p>点选纸上元素可拖动位置。</p></div> : null}
          {toolTab === 'stickers' ? <div className="studio-panel studio-sticker-panel"><h3>行程贴纸 · 16 种</h3><form className="studio-generate" onSubmit={generateSticker}><input aria-label="自定义贴纸主题" value={motif} onChange={event => setMotif(event.target.value)} maxLength={80} placeholder="写一个自己的主题" /><button className="outline-button" disabled={!token || busy || motif.trim().length < 2} type="submit">绘制</button></form><div className="studio-category-grid">{stickerCategories.map(category => <button type="button" key={category.id} disabled={!token || busy} onClick={() => generateCategory(category)}>{category.name}<Plus size={12} /></button>)}</div><div className="studio-generated"><strong>已生成 / 绘制中</strong><div>{stickerJobs.filter(job => job.kind === 'sticker').map(job => <button type="button" key={job.id} onClick={() => { const pageIndex = selected?.pageIndex ?? 0; setPages(previous => previous.map((page, index) => index === pageIndex ? { ...page, items: [...page.items, { id: itemId(), kind: 'sticker', stickerId: job.id, x: 65, y: 60, w: 23, h: 23, r: -7, z: 22 }] } : page)); }}><span>{job.status === 'succeeded' ? <PrivateMedia url={`/api/media/stickers/${job.id}/image`} token={token} alt={job.motif} /> : job.status === 'failed' ? '失败' : '绘制中'}</span><small>{job.motif}</small></button>)}</div></div></div> : null}
          {toolTab === 'edit' ? active ? <div className="studio-panel studio-inspector"><h3>编辑{labelFor(active.kind)}</h3>{['text', 'postcard'].includes(active.kind) ? <textarea value={active.text || ''} onChange={event => updateItem(selected.pageIndex, active.id, { text: event.target.value })} maxLength={300} aria-label="元素文字" /> : null}{active.kind === 'photo' && photos.length ? <label>照片<select value={active.photoIndex % photos.length} onChange={event => updateItem(selected.pageIndex, active.id, { photoIndex: Number(event.target.value) })}>{photos.map((photo, index) => <option value={index} key={photo.id}>{photo.capturedDay || '照片'} · {index + 1}</option>)}</select></label> : null}{active.kind === 'sticker' && stickerJobs.some(job => job.kind === 'sticker') ? <label>贴纸<select value={active.stickerId || ''} onChange={event => updateItem(selected.pageIndex, active.id, { stickerId: event.target.value })}><option value="">待生成</option>{stickerJobs.filter(job => job.kind === 'sticker').map(job => <option value={job.id} key={job.id}>{job.motif}</option>)}</select></label> : null}<div className="studio-sliders">{[['x', '左右', 0, 90], ['y', '上下', 0, 90], ['w', '宽度', 12, 90], ['h', '高度', 10, 85], ['r', '旋转', -30, 30]].map(([field, label, min, max]) => <label key={field}>{label}<input type="range" min={min} max={max} value={active[field]} onChange={event => updateItem(selected.pageIndex, active.id, { [field]: Number(event.target.value) })} /></label>)}</div><div className="studio-layer"><button type="button" onClick={() => updateItem(selected.pageIndex, active.id, { z: active.z + 1 })}><ArrowUp size={14} />上一层</button><button type="button" onClick={() => updateItem(selected.pageIndex, active.id, { z: Math.max(1, active.z - 1) })}><ArrowDown size={14} />下一层</button><button type="button" onClick={removeActive}><Trash2 size={14} />移除</button></div></div> : <div className="studio-panel"><h3>选中一件素材</h3><p>可拖动、调整大小和层次。</p></div> : null}
          {toolTab === 'works' ? <div className="studio-panel studio-work-panel"><h3>旅途作品</h3>{works.slice(0, 3).map(work => <div className="studio-work-card" key={work.id}><strong>{work.title || (work.kind === 'memory' ? '回忆短片' : '风格手账')}</strong><small>{work.status === 'succeeded' ? '已完成' : work.progressLabel || '生成中'}</small>{work.status === 'succeeded' ? work.kind === 'memory' ? <PrivateMedia video url={`/api/media/memories/${work.id}/video`} token={token} /> : <PrivateMedia url={`/api/media/generation-jobs/${work.id}/image`} token={token} alt="旅途作品" /> : null}</div>)}{!works.length ? <p>还没有作品</p> : null}{photos.length && token ? <button className="outline-button" onClick={onCreateWork}>从照片制作</button> : null}</div> : null}
        </div>{notice ? <p role="status" className="studio-message">{notice}</p> : null}{error ? <p role="alert" className="studio-message error">{error}</p> : null}
      </aside>
    </div>
  </section>;
}
