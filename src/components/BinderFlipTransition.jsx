import React, { useLayoutEffect, useRef } from 'react';
import { PageFlip } from 'page-flip/dist/js/page-flip.module.js';

/** A live paper fold: StPageFlip bends one Qwen-textured leaf and draws shadows. */
export default function BinderFlipTransition({ direction, stageRef, incomingRef, onComplete }) {
  const hostRef = useRef(null);
  const completeRef = useRef(onComplete);
  completeRef.current = onComplete;
  useLayoutEffect(() => {
    const host = hostRef.current;
    const source = stageRef.current?.querySelectorAll(':scope > .studio-page > .studio-canvas');
    const incoming = incomingRef.current?.querySelectorAll(':scope > .studio-page > .studio-canvas');
    if (!host || source?.length !== 2) return;
    const pages = Array.from({ length: 4 }, (_, index) => {
      const page = document.createElement('div');
      page.className = `binder-flip-page binder-flip-page-${index % 2 ? 'right' : 'left'}`;
      const currentSpread = direction === 'next' ? index < 2 : index >= 2;
      const canvasSource = currentSpread ? source[index % 2] : incoming?.[index % 2];
      if (canvasSource) {
        const canvas = canvasSource.cloneNode(true);
        canvas.className = 'binder-flip-canvas';
        page.appendChild(canvas);
      }
      return page;
    });
    const flip = new PageFlip(host, {
      width: host.clientWidth / 2, height: host.clientHeight, size: 'fixed', autoSize: false, usePortrait: false,
      startPage: direction === 'next' ? 0 : 2, showCover: false,
      drawShadow: true, maxShadowOpacity: .28, flippingTime: 850,
      useMouseEvents: true, disableFlipByClick: true, showPageCorners: false,
      mobileScrollSupport: false,
    });
    let started = false;
    flip.on('changeState', event => {
      if (event.data === 'flipping') started = true;
      if (event.data === 'read' && started) completeRef.current?.();
    });
    flip.loadFromHTML(pages);
    const frame = requestAnimationFrame(() => direction === 'next' ? flip.flipNext() : flip.flipPrev());
    return () => { cancelAnimationFrame(frame); flip.destroy(); };
  }, [direction, stageRef, incomingRef]);
  return <><div className="binder-flip-host" ref={hostRef} aria-hidden="true" /><img className="binder-flip-rings" src="/art/binder-rings.png" alt="" aria-hidden="true" /></>;
}
