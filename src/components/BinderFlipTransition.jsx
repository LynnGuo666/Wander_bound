import React, { useLayoutEffect, useRef } from 'react';
import { PageFlip } from 'page-flip/dist/js/page-flip.module.js';

/** A live paper fold: StPageFlip bends one Qwen-textured leaf and draws shadows. */
export default function BinderFlipTransition({ direction, stageRef, incomingRef, onComplete }) {
  const hostRef = useRef(null);
  const completeRef = useRef(onComplete);
  completeRef.current = onComplete;
  useLayoutEffect(() => {
    const host = hostRef.current;
    const stage = stageRef.current;
    if (!host || !stage) return;
    let active = true;
    let flip;
    let frame;
    let cancelWait = () => {};
    let imageTimer;
    const preview = incomingRef.current;
    const previewPainted = () => preview?.dataset.previewReady === 'true'
      && !preview.querySelector('.media-placeholder');
    const waitForPreview = () => new Promise(resolve => {
      if (previewPainted()) { resolve(true); return; }
      if (!preview) { resolve(false); return; }
      let settled = false;
      const observer = new MutationObserver(() => { if (previewPainted()) finish(true); });
      const timer = setTimeout(() => finish(false), 1500);
      function finish(ready) {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        observer.disconnect();
        resolve(ready);
      }
      cancelWait = () => finish(false);
      observer.observe(preview, { subtree: true, childList: true, attributes: true });
    });
    async function start() {
      if (!await waitForPreview() || !active) { if (active) completeRef.current?.(); return; }
      const source = stage.querySelectorAll(':scope > .studio-page > .studio-canvas');
      const incoming = preview.querySelectorAll(':scope > .studio-page > .studio-canvas');
      if (source.length !== 2 || incoming.length !== 2) { completeRef.current?.(); return; }
      const images = [...source, ...incoming].flatMap(canvas => [...canvas.querySelectorAll('img')]);
      await Promise.race([
        Promise.all(images.map(img => img.decode().catch(() => {}))),
        new Promise(resolve => { imageTimer = setTimeout(resolve, 1200); }),
      ]);
      clearTimeout(imageTimer);
      if (!active) return;
      if (images.some(img => !img.complete || !img.naturalWidth)) { completeRef.current?.(); return; }
      const pages = Array.from({ length: 4 }, (_, index) => {
        const page = document.createElement('div');
        page.className = `binder-flip-page binder-flip-page-${index % 2 ? 'right' : 'left'}`;
        const canvasSource = (direction === 'next' ? index < 2 : index >= 2)
          ? source[index % 2] : incoming[index % 2];
        const canvas = canvasSource.cloneNode(true);
        canvas.className = 'binder-flip-canvas';
        page.appendChild(canvas);
        return page;
      });
      flip = new PageFlip(host, {
        width: host.clientWidth / 2, height: host.clientHeight, size: 'fixed', autoSize: false, usePortrait: false,
        startPage: direction === 'next' ? 0 : 2, showCover: false,
        drawShadow: true, maxShadowOpacity: .28, flippingTime: 850,
        useMouseEvents: false, disableFlipByClick: true, showPageCorners: false,
        mobileScrollSupport: false,
      });
      let started = false;
      flip.on('changeState', event => {
        if (event.data === 'flipping') started = true;
        if (event.data === 'read' && started) completeRef.current?.();
      });
      flip.loadFromHTML(pages);
      stage.classList.add('flip-active');
      frame = requestAnimationFrame(() => direction === 'next' ? flip.flipNext() : flip.flipPrev());
    }
    start().catch(() => { if (active) completeRef.current?.(); });
    return () => {
      active = false;
      cancelWait();
      clearTimeout(imageTimer);
      cancelAnimationFrame(frame);
      stage.classList.remove('flip-active');
      flip?.destroy();
    };
  }, [direction, stageRef, incomingRef]);
  return <><div className="binder-flip-host" ref={hostRef} aria-hidden="true" /><img className="binder-flip-rings" src="/art/binder-rings.png" alt="" aria-hidden="true" /></>;
}
