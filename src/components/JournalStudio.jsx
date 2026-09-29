import React, { useEffect, useRef, useState } from 'react';
import { ArrowDown, ArrowUp, ImagePlus, LoaderCircle, Plus, Sparkles, Trash2 } from 'lucide-react';
import templates from '../../workflows/journal-templates.json';
import stickerCategories from '../../workflows/journal-sticker-categories.json';
import { PrivateMedia } from './PrivateMedia.jsx';
import BinderFlipTransition from './BinderFlipTransition.jsx';
import { cityArtwork, mediaRequest, tripDate, tripTitle } from '../lib/media.js';
import { addStickerAccents } from '../lib/journalLayout.js';
import { hasCurrentJournalAsset, itineraryMotifs, journalPhotoId, pinAutomaticAssets, selectJournalAsset, stickerMotifForItem } from '../lib/journalMotifs.js';
import { recalledJournalPages, recalledJournalVisuals, rememberJournalPages, rememberJournalVisuals } from '../lib/journalPageCache.js';

const STORE_PREFIX = 'travel-journal-layout-v1:';
const DRAFT_PREFIX = 'travel-journal-pending-v1:';
const samePage = (left, right) => JSON.stringify(left) === JSON.stringify(right);
function loadDrafts(tripId) {
  try {
    const drafts = JSON.parse(localStorage.getItem(`${DRAFT_PREFIX}${tripId}`) || '{}');
    return drafts && typeof drafts === 'object' && !Array.isArray(drafts) ? drafts : {};
  } catch { return {}; }
}
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const itemId = () => crypto.randomUUID();
function defaultText(trip) {
  try {
    const note = localStorage.getItem(`travel-journal-v1:${trip.id}`);
    if (note) return note;
  } catch { /* Browser storage may be disabled. */ }
  return `${tripTitle(trip)} · ${tripDate(trip)}\n在这里写下旅途中最想留住的一刻。`;
}

function fromTemplate(template, trip, pageIndex, stickerIds = [], stampId = '', photoIds = [], assets = {}) {
  let photo = pageIndex * 2;
  let sticker = 0;
  const items = template.slots.map(slot => {
    const photoIndex = slot.kind === 'photo' ? photo++ : null;
    return { ...slot, id: itemId(),
    ...(slot.kind === 'photo' ? { photoIndex, ...(photoIds.length ? { photoId: photoIds[photoIndex % photoIds.length] } : {}) } : {}),
    ...(slot.kind === 'video' && assets.videoId ? { videoId: assets.videoId } : {}),
    ...(slot.kind === 'text' ? { text: assets.diaryText || defaultText(trip) } : {}),
    ...(slot.kind === 'postcard' ? { text: assets.postcardText || `${tripTitle(trip)}\n寄给未来的自己`, stampId, ...(assets.postcardId ? { assetId: assets.postcardId } : {}) } : {}),
    ...(['cover', 'illustration'].includes(slot.kind) && assets.illustrationId ? { assetId: assets.illustrationId } : {}),
    ...(slot.kind === 'sticker' && stickerIds.length ? { stickerId: stickerIds[(pageIndex + sticker++) % stickerIds.length] } : {}),
    };
  });
  return addStickerAccents(items, template.id, pageIndex, stickerIds, itemId);
}
function freshLayout(trip) {
  return [{ templateId: templates[0].id, items: fromTemplate(templates[0], trip, 0) },
    { templateId: templates[3].id, items: fromTemplate(templates[3], trip, 1) }];
}
function loadLayout(trip, token) {
  const cached = recalledJournalPages(token, trip.id);
  if (cached) return cached;
  try {
    const stored = JSON.parse(localStorage.getItem(`${STORE_PREFIX}${trip.id}`));
    if (Array.isArray(stored) && stored.length >= 2 && stored.length <= 12 && stored.length % 2 === 0
        && stored.every(page => Array.isArray(page.items)))
      return stored.map(page => ({ ...page, items: page.items.map(item => item.kind === 'book'
        ? { ...item, kind: 'text', text: defaultText(trip) } : item) }));
  } catch { /* Empty or older local layout. */ }
  return freshLayout(trip);
}
function customizedLegacyPage(page, trip, pageIndex) {
  const template = templates.find(item => item.id === page.templateId);
  if (!template || !Array.isArray(page.items)) return true;
  const oldPhotoCollage = template.id === 'book-and-clip' && page.items.length === template.slots.length - 1
    && template.slots.at(-1).kind === 'illustration';
  if (page.items.length !== template.slots.length && !oldPhotoCollage) return true;
  const serverTitle = trip.plan?.destination || trip.title || '旅途';
  let photoIndex = pageIndex * 2;
  return page.items.some((item, index) => {
    const slot = template.slots[index];
    const expectedPhoto = slot.kind === 'photo' ? photoIndex++ : null;
    return item.kind !== slot.kind || ['x', 'y', 'w', 'h', 'r', 'z'].some(key => item[key] !== slot[key])
      || (item.kind === 'text' && ![defaultText(trip), `${serverTitle}\n写下旅途中最想留住的一刻。`].includes(item.text))
      || (item.kind === 'postcard' && ![`${tripTitle(trip)}\n寄给未来的自己`, `${serverTitle}\n寄给未来的自己`].includes(item.text))
      || (item.kind === 'photo' && item.photoIndex !== expectedPhoto);
  });
}
function labelFor(kind) {
  return { cover: '城市插画', illustration: '旅途插画', photo: '旅途照片', video: '旅途短片', text: '日记', sticker: '千问贴纸', stamp: '行程邮票', postcard: '明信片', clip: '曲别针', ticket: '车票', boarding: '登机牌' }[kind] || kind;
}
export default function JournalStudio({ trip, photos: providedPhotos = [], selectedIds: providedSelectedIds = [], works = [], detailReady = false, privateReady = false, token, onOpenSettings, onCreateWork, onSameCity, sameCityCount = 0, rememberedStops = [], turnDirection = "", onTurnComplete, note = "", onNoteChange, previewOnly = false, sourceRef, nextTrip, previousTrip }) {
  const itineraryAssets = itineraryMotifs(trip, stickerCategories);
  const itineraryAssetKey = JSON.stringify(itineraryAssets);
  const cachedVisuals = useRef(recalledJournalVisuals(token, trip.id) || {});
  const [pages, setPages] = useState(() => loadLayout(trip, token));
  const [previewPhotos, setPreviewPhotos] = useState(cachedVisuals.current.photos || []);
  const [previewSelectedIds, setPreviewSelectedIds] = useState(cachedVisuals.current.selectedIds || []);
  const [previewWorks, setPreviewWorks] = useState(cachedVisuals.current.works || []);
  const [previewDataReady, setPreviewDataReady] = useState(!token);
  const [previewAssetsReady, setPreviewAssetsReady] = useState(!token);
  const photos = previewOnly || !detailReady ? previewPhotos : providedPhotos;
  const selectedIds = previewOnly || !privateReady ? previewSelectedIds : providedSelectedIds;
  const pagesRef = useRef(pages);
  const versionRef = useRef(0);
  const serverPagesRef = useRef([]);
  const draftsRef = useRef(loadDrafts(trip.id));
  const saveChain = useRef(Promise.resolve());
  const [ready, setReady] = useState(!token);
  const [spreadIndex, setSpreadIndex] = useState(0);
  const [spreadTurn, setSpreadTurn] = useState(null);
  const [selected, setSelected] = useState(null);
  const [stickerJobs, setStickerJobs] = useState(cachedVisuals.current.stickers || []);
  const stickerJobsRef = useRef(stickerJobs);
  const [motif, setMotif] = useState('');
  const [toolTab, setToolTab] = useState('layout');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [pendingCount, setPendingCount] = useState(Object.keys(draftsRef.current).length);
  const [draftConflict, setDraftConflict] = useState(false);
  const drag = useRef(null);
  const stageRef = useRef(null);
  const nextPreviewRef = useRef(null);
  const previousPreviewRef = useRef(null);
  const nextSpreadPreviewRef = useRef(null);
  const previousSpreadPreviewRef = useRef(null);
  const noteApplied = useRef(false);
  const videos = (previewOnly || !privateReady ? previewWorks : works)
    .filter(work => work.kind === 'memory' && work.status === 'succeeded');

  function updateStickerJobs(next) {
    const resolved = typeof next === 'function' ? next(stickerJobsRef.current) : next;
    stickerJobsRef.current = resolved;
    setStickerJobs(resolved);
    rememberJournalVisuals(token, trip.id, { stickers: resolved });
  }

  function acceptDocument(document) {
    pagesRef.current = document.pages;
    serverPagesRef.current = document.pages;
    versionRef.current = document.version;
    rememberJournalPages(token, trip.id, document.pages);
    setPages(document.pages);
  }
  function storeDrafts() {
    setPendingCount(Object.keys(draftsRef.current).length);
    try {
      if (Object.keys(draftsRef.current).length)
        localStorage.setItem(`${DRAFT_PREFIX}${trip.id}`, JSON.stringify(draftsRef.current));
      else localStorage.removeItem(`${DRAFT_PREFIX}${trip.id}`);
    } catch { setError('本地草稿保存失败，请复制重要文字后重试。'); }
  }
  async function syncDrafts(document, overwrite = false) {
    const drafts = draftsRef.current;
    const indices = Object.keys(drafts).map(Number).filter(index => Number.isInteger(index) && index >= 0).sort((a, b) => a - b);
    let conflict = false;
    for (const index of indices) {
      const draft = drafts[index];
      if (!draft?.page || !document.pages[index]) continue;
      if (samePage(document.pages[index], draft.page)) { delete drafts[index]; storeDrafts(); continue; }
      if (!overwrite && !samePage(document.pages[index], draft.basePage)) { conflict = true; continue; }
      const savedPage = draft.page;
      try {
        document = await mediaRequest(`/api/media/trips/${trip.id}/journal/pages/${index}`, token,
          { method: 'PUT', body: JSON.stringify({ expectedVersion: document.version, page: savedPage }) });
      } catch (reason) {
        setError(`本地修改未同步：${reason.message}`);
        break;
      }
      if (drafts[index] === draft) delete drafts[index];
      storeDrafts();
    }
    setDraftConflict(conflict);
    return document;
  }
  async function restoreDrafts(document, overwrite = false) {
    const latest = await syncDrafts(document, overwrite);
    acceptDocument(latest);
    const overlay = [...latest.pages];
    for (const [index, draft] of Object.entries(draftsRef.current))
      if (overlay[Number(index)] && draft?.page) overlay[Number(index)] = draft.page;
    pagesRef.current = overlay;
    rememberJournalPages(token, trip.id, overlay);
    setPages(overlay);
    if (Object.keys(draftsRef.current).length)
      setError('本地修改仍未同步，已保留在页面上；同步后才能使用 AI 排版。');
    else setError('');
  }
  useEffect(() => {
    if (!token) { setReady(true); return; }
    let alive = true;
    mediaRequest(`/api/media/trips/${trip.id}/journal`, token)
      .then(async document => {
        if (!alive) return;
        let stored = null;
        try { stored = JSON.parse(localStorage.getItem(`${STORE_PREFIX}${trip.id}`) || 'null'); }
        catch { /* Damaged legacy layout is ignored. */ }
        if (document.version === 0 && Array.isArray(stored) && stored.length === 2) {
          for (let index = 0; index < 2; index++) {
            if (!customizedLegacyPage(stored[index], trip, index)) continue;
            document = await mediaRequest(`/api/media/trips/${trip.id}/journal/pages/${index}`, token,
              { method: 'PUT', body: JSON.stringify({ expectedVersion: document.version, page: stored[index] }) });
          }
        }
        if (alive) {
          try { await restoreDrafts(document); }
          catch (reason) {
            acceptDocument(document);
            const overlay = [...document.pages];
            for (const [index, draft] of Object.entries(draftsRef.current))
              if (overlay[Number(index)] && draft?.page) overlay[Number(index)] = draft.page;
            pagesRef.current = overlay; rememberJournalPages(token, trip.id, overlay); setPages(overlay);
            setError(`本地修改未同步：${reason.message}`);
          }
          setReady(true);
        }
      })
      .catch(reason => {
        if (!alive) return;
        const overlay = [...pagesRef.current];
        for (const [index, draft] of Object.entries(draftsRef.current))
          if (overlay[Number(index)] && draft?.page) overlay[Number(index)] = draft.page;
        pagesRef.current = overlay; rememberJournalPages(token, trip.id, overlay); setPages(overlay);
        setError(`无法读取手账：${reason.message}；本地修改仍保留在此浏览器。`);
        setReady(true);
      });
    return () => { alive = false; };
  }, [trip.id, token]);

  function persistPage(pageIndex) {
    if (!token || !ready) return;
    const page = pagesRef.current[pageIndex];
    saveChain.current = saveChain.current.catch(() => {}).then(async () => {
      try {
        const document = await mediaRequest(`/api/media/trips/${trip.id}/journal/pages/${pageIndex}`, token,
          { method: 'PUT', body: JSON.stringify({ expectedVersion: versionRef.current, page }) });
        versionRef.current = document.version;
        serverPagesRef.current = document.pages;
        const draft = draftsRef.current[pageIndex];
        if (draft && samePage(draft.page, page)) delete draftsRef.current[pageIndex];
        else if (draft) draftsRef.current[pageIndex] = { ...draft, basePage: document.pages[pageIndex] };
        storeDrafts();
        if (!Object.keys(draftsRef.current).length) { setError(''); setDraftConflict(false); }
      } catch (reason) { setError(`页面未同步：${reason.message}`); throw reason; }
    });
  }
  function editPage(pageIndex, transform, persist = true) {
    const next = pagesRef.current.map((page, index) => index === pageIndex
      ? { ...transform(pinAutomaticAssets(page, index, stickerJobsRef.current, itineraryAssets, selectedIds, videos.map(video => video.id))),
        source: 'user', protected: true } : page);
    pagesRef.current = next;
    rememberJournalPages(token, trip.id, next);
    setPages(next);
    if (token && !previewOnly) {
      const previous = draftsRef.current[pageIndex];
      draftsRef.current[pageIndex] = { page: next[pageIndex], basePage: previous?.basePage || serverPagesRef.current[pageIndex] };
      storeDrafts();
    }
    if (persist) persistPage(pageIndex);
  }
  async function retryDrafts() {
    setBusy(true); setError('');
    try {
      await saveChain.current.catch(() => {});
      saveChain.current = Promise.resolve();
      const document = await mediaRequest(`/api/media/trips/${trip.id}/journal`, token);
      await restoreDrafts(document, draftConflict);
    } catch (reason) { setError(`本地修改未同步：${reason.message}`); }
    finally { setBusy(false); }
  }

  useEffect(() => {
    if (!previewOnly || !token) return;
    let alive = true;
    setPreviewDataReady(false);
    Promise.all([
      mediaRequest(`/api/trips/${trip.id}`, token),
      mediaRequest(`/api/media/trips/${trip.id}/selected-photos`, token),
      mediaRequest(`/api/media/trips/${trip.id}/works`, token),
    ]).then(([detail, selection, result]) => {
      if (alive) {
        const visuals = { photos: detail.photos || [], selectedIds: selection.photoIds || [], works: result.works || [] };
        setPreviewPhotos(visuals.photos); setPreviewSelectedIds(visuals.selectedIds); setPreviewWorks(visuals.works);
        rememberJournalVisuals(token, trip.id, visuals);
        setPreviewDataReady(true);
      }
    }).catch(() => { if (alive) setPreviewDataReady(false); });
    return () => { alive = false; };
  }, [previewOnly, trip.id, token]);

  useEffect(() => {
    if (previewOnly || !ready) return;
    try { localStorage.setItem(`${STORE_PREFIX}${trip.id}`, JSON.stringify(pages)); }
    catch { setError('排版未能保存在当前浏览器'); }
  }, [pages, trip.id, ready]);
  useEffect(() => {
    if (previewOnly || !note || !ready || noteApplied.current) return;
    noteApplied.current = true;
    const firstPage = pagesRef.current[0];
    if (!firstPage || firstPage.protected || !firstPage.items.some(item => item.kind === 'text')) return;
    editPage(0, page => ({ ...page, items: page.items.map(item => item.kind === 'text'
      ? { ...item, text: note.slice(0, 2000) } : item) }));
  }, [note, ready, trip.id]);
  useEffect(() => {
    if (!token) { updateStickerJobs([]); return; }
    let alive = true;
    const refresh = () => mediaRequest(`/api/media/trips/${trip.id}/stickers`, token)
      .then(result => { if (alive) { updateStickerJobs(result.stickers || []); if (previewOnly) setPreviewAssetsReady(true); } })
      .catch(reason => { if (alive) { setError(reason.message); if (previewOnly) setPreviewAssetsReady(false); } });
    async function seedTripAssets() {
      try {
        const result = await mediaRequest(`/api/media/trips/${trip.id}/stickers`, token);
        if (!alive) return;
        const current = result.stickers || [];
        updateStickerJobs(current);
        const wanted = [{ kind: 'illustration', motif: itineraryAssets.illustration },
          { kind: 'postcard', motif: itineraryAssets.postcard },
          { kind: 'stamp', motif: itineraryAssets.stamp },
          ...itineraryAssets.stickers.map(next => ({ kind: 'sticker', motif: next }))];
        for (const item of wanted) {
          if (!alive) return;
          if (hasCurrentJournalAsset(current, item.kind, item.motif, result.promptVersions)) continue;
          const created = await mediaRequest(`/api/media/trips/${trip.id}/stickers`, token,
            { method: 'POST', body: JSON.stringify(item) });
          current.push(created);
          updateStickerJobs([...current]);
        }
      } catch (reason) { if (alive) setError(reason.message); }
    }
    if (previewOnly) {
      setPreviewAssetsReady(false);
      refresh();
    }
    else seedTripAssets();
    const timer = setInterval(refresh, 5000);
    return () => { alive = false; clearInterval(timer); };
  }, [trip.id, token, itineraryAssetKey]);
  function updateItem(pageIndex, id, patch, persist = true) {
    if (pageIndex === 0 && typeof patch.text === 'string' && pages[pageIndex]?.items.some(item => item.id === id && item.kind === 'text'))
      onNoteChange?.(patch.text);
    editPage(pageIndex, page => ({ ...page, items: page.items.map(item => item.id === id ? { ...item, ...patch } : item) }), persist);
  }
  function setTemplate(pageIndex, templateId, stickerIds = []) {
    const template = templates.find(item => item.id === templateId);
    if (!template) return;
    if (!stickerIds.length) stickerIds = stickerJobs.filter(job => job.kind === 'sticker' && job.status !== 'failed').map(job => job.id);
    const stampId = stickerJobs.find(job => job.kind === 'stamp' && job.status !== 'failed')?.id || '';
    editPage(pageIndex, () => ({ templateId, items: fromTemplate(template, trip, pageIndex, stickerIds, stampId, selectedIds,
      { videoId: videos[0]?.id }) }));
    setSelected(null);
  }
  function addItem(kind, pageIndex) {
    const count = pages[pageIndex].items.length;
    const item = { id: itemId(), kind, x: 15 + count % 4 * 8, y: 15 + count % 5 * 7,
      w: kind === 'clip' ? 12 : kind === 'sticker' ? 24 : 45,
      h: kind === 'clip' ? 15 : kind === 'text' ? 23 : ['ticket', 'boarding'].includes(kind) ? 23 : 30, r: 0, z: count + 2,
      ...(kind === 'photo' ? { photoIndex: 0 } : {}),
      ...(kind === 'photo' && selectedIds.length ? { photoId: selectedIds[0] } : {}),
      ...(kind === 'video' && videos.length ? { videoId: videos[0].id } : {}),
      ...(kind === 'text' || kind === 'postcard' ? { text: kind === 'text' ? defaultText(trip) : `${tripTitle(trip)}\n一张来自旅途的明信片` } : {}),
      ...(kind === 'sticker' && stickerJobs.some(job => job.kind === 'sticker' && job.status !== 'failed') ? { stickerId: stickerJobs.find(job => job.kind === 'sticker' && job.status !== 'failed').id } : {}),
      ...(kind === 'postcard' && stickerJobs.some(job => job.kind === 'stamp' && job.status !== 'failed') ? { stampId: stickerJobs.find(job => job.kind === 'stamp' && job.status !== 'failed').id } : {}),
      ...(['postcard', 'illustration'].includes(kind) && stickerJobs.some(job => job.kind === kind && job.status !== 'failed') ? { assetId: stickerJobs.find(job => job.kind === kind && job.status !== 'failed').id } : {}),
    };
    editPage(pageIndex, page => ({ ...page, items: [...page.items, item] }));
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
    if (Math.abs(event.clientX - state.startX) + Math.abs(event.clientY - state.startY) < 3) return;
    state.moved = true;
    updateItem(state.pageIndex, state.id, {
      x: clamp(state.x + (event.clientX - state.startX) / state.width * 100, 0, 100 - 8),
      y: clamp(state.y + (event.clientY - state.startY) / state.height * 100, 0, 100 - 8),
    }, false);
  }
  async function queueSticker(nextMotif, kind = 'sticker') {
    const created = await mediaRequest(`/api/media/trips/${trip.id}/stickers`, token,
      { method: 'POST', body: JSON.stringify({ motif: nextMotif, kind }) });
    updateStickerJobs(previous => [created, ...previous.filter(job => job.id !== created.id)]);
    return created.id;
  }
  async function generateSticker(event) {
    event.preventDefault();
    if (!motif.trim()) return;
    setBusy(true); setError(''); setNotice('');
    try {
      const id = await queueSticker(motif.trim());
      const pageIndex = selected?.pageIndex ?? spreadIndex * 2;
      const item = { id: itemId(), kind: 'sticker', stickerId: id, x: 67, y: 63,
        w: 24, h: 24, r: -8, z: 20 };
      editPage(pageIndex, page => ({ ...page, items: [...page.items, item] }));
      setMotif(''); setNotice('千问正在绘制贴纸；完成后会自动出现在纸页上。');
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }
  async function generateCategory(category) {
    setBusy(true); setError(''); setNotice('');
    try {
      const nextMotif = itineraryMotifs(trip, [category], { includeAllCategories: true }).stickers[0];
      const id = await queueSticker(nextMotif);
      const pageIndex = selected?.pageIndex ?? spreadIndex * 2;
      const item = { id: itemId(), kind: 'sticker', stickerId: id, x: 63, y: 59,
        w: 25, h: 25, r: -7, z: 21 };
      editPage(pageIndex, page => ({ ...page, items: [...page.items, item] }));
      setNotice(`「${category.name}」已加入纸页，千问绘制完成后会自动显示。`);
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }
  async function aiCompose() {
    setBusy(true); setError(''); setNotice('');
    try {
      await saveChain.current;
      if (Object.keys(draftsRef.current).length) throw new Error('还有本地修改未同步，请先保存页面。');
      if (pagesRef.current.length >= 12 && pagesRef.current.slice(0, 2).every(page => page.protected))
        throw new Error('已达到 12 页上限；现有页面均由你修改，AI 不会覆盖它们。');
      const plan = await mediaRequest(`/api/media/trips/${trip.id}/journal/compose`, token, { method: 'POST' });
      const illustrationId = await queueSticker(plan.illustrationMotif, 'illustration');
      const postcardId = await queueSticker(plan.postcardMotif, 'postcard');
      const stampId = await queueSticker(plan.stampMotif, 'stamp');
      const stickerIds = await Promise.all(plan.stickerMotifs.map(nextMotif => queueSticker(nextMotif)));
      const layouts = plan.templates.map((id, index) => {
        const template = templates.find(item => item.id === id);
        const items = fromTemplate(template, trip, index, stickerIds, stampId,
          plan.photoOrder, { postcardId, illustrationId, videoId: videos[0]?.id,
            diaryText: plan.diaryText, postcardText: plan.postcardText });
        if (index === 0 && !items.some(item => ['cover', 'illustration'].includes(item.kind)))
          items.push({ id: itemId(), kind: 'illustration', assetId: illustrationId, x: 74, y: 6, w: 20, h: 19, r: 7, z: 1 });
        return { templateId: id, items };
      });
      const document = await mediaRequest(`/api/media/trips/${trip.id}/journal/apply-ai`, token,
        { method: 'POST', body: JSON.stringify({ pages: layouts }) });
      acceptDocument(document); setSelected(null); setToolTab('stickers');
      setSpreadIndex(Math.floor(document.updatedPageIndices[0] / 2));
      setNotice(`AI 已填写 ${document.updatedPageIndices.length} 页，保留 ${document.preservedPageIndices.length} 页你的修改；千问正在绘制行程素材。`);
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }
  const active = selected && pages[selected.pageIndex]?.items.find(item => item.id === selected.id);
  function removeActive() {
    if (!selected) return;
    editPage(selected.pageIndex, page => ({ ...page, items: page.items.filter(item => item.id !== selected.id) }));
    setSelected(null);
  }
  async function addSpread() {
    if (!token || busy) return;
    setBusy(true); setError('');
    try {
      await saveChain.current;
      if (Object.keys(draftsRef.current).length) throw new Error('还有本地修改未同步，请先保存页面。');
      const document = await mediaRequest(`/api/media/trips/${trip.id}/journal/spreads`, token,
        { method: 'POST', body: JSON.stringify({ expectedVersion: versionRef.current }) });
      acceptDocument(document);
      setSpreadIndex(document.pages.length / 2 - 1);
      setSelected(null);
      setNotice('已添加两页手账，AI 不会修改你添加的页面。');
    } catch (reason) { setError(reason.message); }
    finally { setBusy(false); }
  }
  function turnSpread(offset) {
    const target = spreadIndex + offset;
    if (spreadTurn || turnDirection || target < 0 || target >= pages.length / 2) return;
    setSpreadTurn({ target, direction: offset > 0 ? 'next' : 'previous' });
  }
  function finishSpreadTurn() {
    if (!spreadTurn) return;
    setSpreadIndex(spreadTurn.target);
    setSelected(null);
    setSpreadTurn(null);
  }
  function addGenerated(job) {
    const pageIndex = selected?.pageIndex ?? spreadIndex * 2;
    const kind = ['sticker', 'stamp'].includes(job.kind) ? 'sticker' : job.kind;
    const item = { id: itemId(), kind, x: kind === 'sticker' ? 65 : 47,
      y: kind === 'sticker' ? 60 : 30, w: kind === 'sticker' ? 23 : 42,
      h: kind === 'sticker' ? 23 : 36, r: -7, z: 22,
      ...(kind === 'sticker' ? { stickerId: job.id } : { assetId: job.id }),
      ...(kind === 'postcard' ? { text: `${tripTitle(trip)}\n旅途寄语` } : {}),
    };
    editPage(pageIndex, page => ({ ...page, items: [...page.items, item] }));
  }
  function renderItem(item, page, pageIndex, itemIndex) {
    if (item.kind === 'cover' || item.kind === 'illustration') {
      const asset = selectJournalAsset(page, item.assetId, stickerJobs, 'illustration', itineraryAssets.illustration, item.assetMotif);
      return asset?.status === 'succeeded'
        ? <PrivateMedia url={`/api/media/stickers/${asset.id}/image`} token={token} loading="eager" alt={`${asset.motif}，千问生成的旅途插画`} />
        : item.assetId ? <span className="studio-sticker-pending">{asset?.status === 'failed' ? '插画生成失败' : '千问绘制中…'}</span>
          : <img src={cityArtwork(trip)} alt={`${tripTitle(trip)}的千问城市插画`} />;
    }
    if (item.kind === 'photo') {
      const chosenId = journalPhotoId(page, item, selectedIds);
      const photo = photos.find(entry => entry.id === chosenId);
      const frame = (item.photoIndex || 0) % 2 ? 'ornate-photo-frame' : 'polaroid-frame';
      return <div className={`studio-prop-wrap studio-photo-${frame}`}><img className="studio-prop" src={`/art/${frame}.png`} alt="千问生成的空白相框" /><div className="studio-photo-slot">{photo && token
        ? <PrivateMedia url={`/api/media/photos/${photo.id}`} token={token} loading="eager" alt="旅途照片" />
        : <span className="studio-empty"><ImagePlus size={20} />{token ? '等待旅途照片' : '连接私有相册'}</span>}</div></div>;
    }
    if (item.kind === 'video') {
      const video = item.videoId ? videos.find(work => work.id === item.videoId)
        : page.protected ? undefined : videos[0];
      return <div className="studio-prop-wrap studio-film-prop"><img className="studio-prop" src="/art/film-frame.png" alt="千问生成的胶片框" /><div className="studio-video-slot">{video && token
        ? <PrivateMedia video url={`/api/media/memories/${video.id}/video`} token={token} />
        : <span className="studio-empty">旅途短片将在这里播放</span>}</div></div>;
    }
    if (item.kind === 'sticker') {
      const motif = stickerMotifForItem(page, pageIndex, itemIndex, itineraryAssets);
      const job = selectJournalAsset(page, item.stickerId, stickerJobs, 'sticker', motif, item.stickerMotif);
      const stickerId = item.stickerId || job?.id;
      return stickerId ? job?.status === 'succeeded'
        ? <PrivateMedia url={`/api/media/stickers/${stickerId}/image`} token={token} loading="eager" alt={`${job.motif}，千问生成的贴纸`} />
        : <span className="studio-sticker-pending">{job?.status === 'failed' ? '贴纸生成失败' : '千问绘制中…'}</span>
        : <span className="studio-sticker-pending">{item.stickerMotif ? '千问绘制中…' : page.protected ? '选择贴纸' : '行程贴纸待生成'}</span>;
    }
    if (item.kind === 'clip') return <img className="studio-clip-art" src="/art/paperclip.png" alt="千问绘制的曲别针插图" />;
    if (item.kind === 'postcard') {
      const stamp = selectJournalAsset(page, item.stampId, stickerJobs, 'stamp', itineraryAssets.stamp, item.stampMotif);
      const stampId = item.stampId || stamp?.id;
      const artwork = selectJournalAsset(page, item.assetId, stickerJobs, 'postcard', itineraryAssets.postcard, item.assetMotif);
      return <div className="studio-prop-wrap"><img className="studio-prop" src="/art/postcard-blank.png" alt="千问生成的明信片模板" />{artwork?.status === 'succeeded'
        ? <span className="studio-postcard-scene"><PrivateMedia url={`/api/media/stickers/${artwork.id}/image`} token={token} loading="eager" alt={`${artwork.motif}，千问绘制的旅途风景`} /></span>
        : null}<span className="studio-postcard-text">{item.text}</span>{stampId ? <span className="studio-stamp">{stamp?.status === 'succeeded'
        ? <PrivateMedia url={`/api/media/stickers/${stampId}/image`} token={token} loading="eager" alt={`${stamp.motif}，千问生成的邮票`} />
        : <span>{stamp?.status === 'failed' ? '邮票失败' : '行程邮票绘制中'}</span>}</span> : null}</div>;
    }
    if (item.kind === 'ticket' || item.kind === 'boarding') return <div className="studio-prop-wrap"><img className="studio-prop" src={`/art/${item.kind === 'ticket' ? 'rail-ticket-blank' : 'boarding-pass-blank'}.png`} alt={`千问生成的${labelFor(item.kind)}模板`} /><span className="studio-ticket-text">{trip.plan?.originCity || '旅途起点'} → {trip.plan?.destination || tripTitle(trip)}<br />{trip.plan?.startDate || '启程日期'}</span></div>;
    return <div className="studio-text">{item.text}</div>;
  }
  function renderSpreadPreview(index, ref) {
    if (index < 0 || index >= pages.length / 2) return null;
    return <div ref={ref} className="studio-preview-source" data-preview-ready="true" aria-hidden="true">
      {pages.slice(index * 2, index * 2 + 2).map((page, localIndex) => { const pageIndex = index * 2 + localIndex; return <div className="studio-page" key={pageIndex}><div className="studio-canvas">{page.items.map((item, itemIndex) =>
        <div className={`studio-item studio-${item.kind}`} key={item.id}
          style={{ left: `${item.x}%`, top: `${item.y}%`, width: `${item.w}%`, height: `${item.h}%`, zIndex: item.z, transform: `rotate(${item.r}deg)` }}>{renderItem(item, page, pageIndex, itemIndex)}</div>)}</div></div>; })}
    </div>;
  }
  if (previewOnly) return <div ref={sourceRef} className="studio-preview-source" data-preview-ready={ready && previewDataReady && previewAssetsReady} aria-hidden="true">{pages.slice(0, 2).map((page, pageIndex) =>
    <div className="studio-page" key={pageIndex}><div className="studio-canvas">{page.items.map((item, itemIndex) =>
      <div className={`studio-item studio-${item.kind}`} key={item.id}
        style={{ left: `${item.x}%`, top: `${item.y}%`, width: `${item.w}%`, height: `${item.h}%`, zIndex: item.z,
          transform: `rotate(${item.r}deg)` }}>{renderItem(item, page, pageIndex, itemIndex)}</div>)}</div></div>)}</div>;
  if (!ready) return <section className="studio-shell" aria-label="可编辑的旅途手账"><p role="status" className="studio-message">正在打开手账…</p></section>;
  return <section className="studio-shell" aria-label="可编辑的旅途手账">
    <div className="studio-toolbar"><strong>{tripTitle(trip)} <small>{tripDate(trip)}</small></strong><div className="studio-spread-nav"><button type="button" disabled={spreadIndex === 0 || !!spreadTurn || !!turnDirection} onClick={() => turnSpread(-1)}>‹</button><small>{spreadIndex + 1} / {Math.ceil(pages.length / 2)}</small><button type="button" disabled={spreadIndex >= pages.length / 2 - 1 || !!spreadTurn || !!turnDirection} onClick={() => turnSpread(1)}>›</button><button type="button" disabled={!token || busy || !!spreadTurn || pages.length >= 12} onClick={addSpread}>＋两页</button></div><div><button className="solid-button" disabled={!token || busy || !ready || !!spreadTurn} onClick={aiCompose}>{busy ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}AI 排版</button>{!token ? <button className="text-button" onClick={onOpenSettings}>连接相册</button> : null}</div></div>
    <div className="studio-workspace">
      <div className="studio-book-stage"><div ref={stageRef} className={`studio-book-spread ${turnDirection ? `turn-${turnDirection}` : ''}`}>{pages.slice(spreadIndex * 2, spreadIndex * 2 + 2).map((page, localIndex) => { const pageIndex = spreadIndex * 2 + localIndex; return <div className="studio-page" key={pageIndex}><div className="studio-canvas" aria-label={`${localIndex === 0 ? '左' : '右'}页画布`}>
        {page.items.map((item, itemIndex) => <div key={item.id} className={`studio-item studio-${item.kind}${selected?.id === item.id ? ' selected' : ''}`}
          role="button" tabIndex={0} aria-label={`${labelFor(item.kind)}，点击编辑，拖动移动`}
          onClick={() => { setSelected({ pageIndex, id: item.id }); setToolTab('edit'); }}
          onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelected({ pageIndex, id: item.id }); setToolTab('edit'); } }}
          onPointerDown={event => onPointerDown(event, pageIndex, item)} onPointerMove={onPointerMove} onPointerUp={() => { if (drag.current?.moved) persistPage(drag.current.pageIndex); drag.current = null; }} onPointerCancel={() => { if (drag.current?.moved) persistPage(drag.current.pageIndex); drag.current = null; }}
          style={{ left: `${item.x}%`, top: `${item.y}%`, width: `${item.w}%`, height: `${item.h}%`, zIndex: item.z, transform: `rotate(${item.r}deg)` }}>{renderItem(item, page, pageIndex, itemIndex)}</div>)}
      </div></div>; })}{turnDirection || spreadTurn ? <BinderFlipTransition direction={turnDirection || spreadTurn.direction} stageRef={stageRef}
        incomingRef={turnDirection ? (turnDirection === 'next' ? nextPreviewRef : previousPreviewRef)
          : (spreadTurn.direction === 'next' ? nextSpreadPreviewRef : previousSpreadPreviewRef)}
        onComplete={turnDirection ? onTurnComplete : finishSpreadTurn} /> : null}</div>
      {renderSpreadPreview(spreadIndex + 1, nextSpreadPreviewRef)}
      {renderSpreadPreview(spreadIndex - 1, previousSpreadPreviewRef)}
      {nextTrip ? <JournalStudio key={nextTrip.id} trip={nextTrip} token={token} previewOnly sourceRef={nextPreviewRef} /> : null}
      {previousTrip ? <JournalStudio key={previousTrip.id} trip={previousTrip} token={token} previewOnly sourceRef={previousPreviewRef} /> : null}</div>
      <aside className="studio-tools" aria-label="手账工具"><nav className="studio-tool-tabs" aria-label="手账工具分类">{[['layout','版式'],['add','添加'],['stickers','贴纸'],['edit','编辑'],['works','作品']].map(([id,name]) => <button key={id} type="button" className={toolTab === id ? 'active' : ''} onClick={() => setToolTab(id)}>{name}</button>)}</nav>
        <div className="studio-tool-content">
          {toolTab === 'layout' ? <div className="studio-panel"><h3>选择版式</h3>{pages.slice(spreadIndex * 2, spreadIndex * 2 + 2).map((page, localIndex) => { const pageIndex = spreadIndex * 2 + localIndex; return <label className="studio-select" key={pageIndex}>{localIndex === 0 ? '左页' : '右页'}{page.protected ? <small>你的页面 · AI 不修改</small> : null}<select value={page.templateId} onChange={event => setTemplate(pageIndex, event.target.value)}>{templates.map(template => <option value={template.id} key={template.id}>{template.name}</option>)}</select></label>; })}<button className="outline-button" disabled={!token || busy} onClick={aiCompose}><Sparkles size={15} />StepFun 为我排版</button>{sameCityCount ? <div className="studio-city-link"><strong>还来过这座城市 {sameCityCount} 次</strong>{rememberedStops.length ? <small>曾去过：{rememberedStops.slice(0, 2).join('、')}</small> : null}<button className="text-button" onClick={onSameCity}>翻看同城记忆</button></div> : null}</div> : null}
          {toolTab === 'add' ? <div className="studio-panel"><h3>添加到{(selected?.pageIndex ?? spreadIndex * 2) % 2 ? '右' : '左'}页</h3><div className="studio-add-grid">{['photo', 'video', 'text', 'postcard', 'ticket', 'boarding', 'clip', 'sticker', 'illustration'].map(kind => <button type="button" key={kind} onClick={() => addItem(kind, selected?.pageIndex ?? spreadIndex * 2)}><Plus size={13} />{labelFor(kind)}</button>)}</div><p>点选纸上元素可拖动位置。</p></div> : null}
          {toolTab === 'stickers' ? <div className="studio-panel studio-sticker-panel"><h3>行程贴纸 · 16 种</h3><form className="studio-generate" onSubmit={generateSticker}><input aria-label="自定义贴纸主题" value={motif} onChange={event => setMotif(event.target.value)} maxLength={80} placeholder="写一个自己的主题" /><button className="outline-button" disabled={!token || busy || motif.trim().length < 2} type="submit">绘制</button></form><div className="studio-category-grid">{stickerCategories.map(category => <button type="button" key={category.id} disabled={!token || busy} onClick={() => generateCategory(category)}>{category.name}<Plus size={12} /></button>)}</div><div className="studio-generated"><strong>已生成 / 绘制中</strong><div>{stickerJobs.filter(job => ['sticker', 'stamp', 'postcard', 'illustration'].includes(job.kind)).map(job => <button type="button" key={job.id} onClick={() => addGenerated(job)} aria-label={`添加${labelFor(job.kind)}：${job.motif}`}><span>{job.status === 'succeeded' ? <PrivateMedia url={`/api/media/stickers/${job.id}/image`} token={token} alt={job.motif} /> : job.status === 'failed' ? '失败' : '绘制中'}</span><small>{job.motif}</small></button>)}</div></div></div> : null}
          {toolTab === 'edit' ? active ? <div className="studio-panel studio-inspector"><h3>编辑{labelFor(active.kind)}</h3>{['text', 'postcard'].includes(active.kind) ? <textarea value={active.text || ''} onChange={event => updateItem(selected.pageIndex, active.id, { text: event.target.value }, false)} onBlur={() => persistPage(selected.pageIndex)} maxLength={300} aria-label="元素文字" /> : null}{active.kind === 'photo' && photos.length ? <label>照片<select value={photos.findIndex(photo => photo.id === active.photoId) >= 0 ? photos.findIndex(photo => photo.id === active.photoId) : active.photoIndex % photos.length} onChange={event => updateItem(selected.pageIndex, active.id, { photoIndex: Number(event.target.value), photoId: photos[Number(event.target.value)].id })}>{photos.map((photo, index) => <option value={index} key={photo.id}>{photo.capturedDay || '照片'} · {index + 1}</option>)}</select></label> : null}{active.kind === 'video' && videos.length ? <label>短片<select value={active.videoId || ''} onChange={event => updateItem(selected.pageIndex, active.id, { videoId: event.target.value })}><option value="">选择短片</option>{videos.map(video => <option value={video.id} key={video.id}>{video.title || '回忆短片'}</option>)}</select></label> : null}{active.kind === 'sticker' && stickerJobs.some(job => ['sticker', 'stamp'].includes(job.kind)) ? <label>贴纸 / 邮票<select value={active.stickerId || ''} onChange={event => updateItem(selected.pageIndex, active.id, { stickerId: event.target.value, stickerMotif: '' })}><option value="">待生成</option>{stickerJobs.filter(job => ['sticker', 'stamp'].includes(job.kind)).map(job => <option value={job.id} key={job.id}>{job.motif}</option>)}</select></label> : null}{['postcard', 'illustration', 'cover'].includes(active.kind) && stickerJobs.some(job => job.kind === (active.kind === 'cover' ? 'illustration' : active.kind)) ? <label>旅途画面<select value={active.assetId || ''} onChange={event => updateItem(selected.pageIndex, active.id, { assetId: event.target.value, assetMotif: '' })}><option value="">默认画面</option>{stickerJobs.filter(job => job.kind === (active.kind === 'cover' ? 'illustration' : active.kind)).map(job => <option value={job.id} key={job.id}>{job.motif}</option>)}</select></label> : null}{active.kind === 'postcard' && stickerJobs.some(job => job.kind === 'stamp') ? <label>邮票<select value={active.stampId || ''} onChange={event => updateItem(selected.pageIndex, active.id, { stampId: event.target.value, stampMotif: '' })}><option value="">不使用邮票</option>{stickerJobs.filter(job => job.kind === 'stamp').map(job => <option value={job.id} key={job.id}>{job.motif}</option>)}</select></label> : null}<div className="studio-sliders">{[['x', '左右', 0, 90], ['y', '上下', 0, 90], ['w', '宽度', 12, 90], ['h', '高度', 10, 85], ['r', '旋转', -30, 30]].map(([field, label, min, max]) => <label key={field}>{label}<input type="range" min={min} max={max} value={active[field]} onChange={event => updateItem(selected.pageIndex, active.id, { [field]: Number(event.target.value) }, false)} onPointerUp={() => persistPage(selected.pageIndex)} onKeyUp={() => persistPage(selected.pageIndex)} /></label>)}</div><div className="studio-layer"><button type="button" onClick={() => updateItem(selected.pageIndex, active.id, { z: active.z + 1 })}><ArrowUp size={14} />上一层</button><button type="button" onClick={() => updateItem(selected.pageIndex, active.id, { z: Math.max(1, active.z - 1) })}><ArrowDown size={14} />下一层</button><button type="button" onClick={removeActive}><Trash2 size={14} />移除</button></div></div> : <div className="studio-panel"><h3>选中一件素材</h3><p>可拖动、调整大小和层次。</p></div> : null}
          {toolTab === 'works' ? <div className="studio-panel studio-work-panel"><h3>旅途作品</h3>{works.slice(0, 3).map(work => <div className="studio-work-card" key={work.id}><strong>{work.title || (work.kind === 'memory' ? '回忆短片' : '风格手账')}</strong><small>{work.status === 'succeeded' ? '已完成' : work.progressLabel || '生成中'}</small>{work.status === 'succeeded' ? work.kind === 'memory' ? <PrivateMedia video url={`/api/media/memories/${work.id}/video`} token={token} /> : <PrivateMedia url={`/api/media/generation-jobs/${work.id}/image`} token={token} alt="旅途作品" /> : null}</div>)}{!works.length ? <p>还没有作品</p> : null}{photos.length && token ? <button className="outline-button" onClick={onCreateWork}>从照片制作</button> : null}</div> : null}
        </div>{notice ? <p role="status" className="studio-message">{notice}</p> : null}{error ? <p role="alert" className="studio-message error">{error}</p> : null}{pendingCount && token ? <button type="button" className="outline-button" disabled={busy} onClick={retryDrafts}>{draftConflict ? '用本地修改覆盖服务器' : '重试同步本地修改'}</button> : null}
      </aside>
    </div>
  </section>;
}
