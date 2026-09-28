import React, { useLayoutEffect, useRef } from 'react';
import { PageFlip } from 'page-flip/dist/js/page-flip.module.js';

/** A live paper fold: StPageFlip bends one Qwen-textured leaf and draws shadows. */
export default function BinderFlipTransition({ direction, stageRef }) {
  const hostRef = useRef(null);
  useLayoutEffect(() => {
    const host = hostRef.current;
    const source = stageRef.current?.querySelectorAll('.studio-page .studio-canvas');
    if (!host || source?.length !== 2) return;
    const pages = Array.from({ length: 4 }, (_, index) => {
      const page = document.createElement('div');
      page.className = 'binder-flip-page';
      const currentSpread = direction === 'next' ? index < 2 : index >= 2;
      if (currentSpread) {
        const canvas = source[index % 2].cloneNode(true);
        canvas.className = 'binder-flip-canvas';
        page.appendChild(canvas);
      }
      return page;
    });
    const flip = new PageFlip(host, {
      width: 420, height: 510, size: 'stretch', minWidth: 100, maxWidth: 2000,
      minHeight: 100, maxHeight: 2000, autoSize: false, usePortrait: false,
      startPage: direction === 'next' ? 0 : 2, showCover: false,
      drawShadow: true, maxShadowOpacity: .28, flippingTime: 850,
      useMouseEvents: true, disableFlipByClick: true, showPageCorners: false,
      mobileScrollSupport: false,
    });
    flip.loadFromHTML(pages);
    const frame = requestAnimationFrame(() => direction === 'next' ? flip.flipNext() : flip.flipPrev());
    return () => { cancelAnimationFrame(frame); flip.destroy(); };
  }, [direction, stageRef]);
  return <><div className="binder-flip-host" ref={hostRef} aria-hidden="true" /><img className="binder-flip-rings" src="/art/binder-rings.png" alt="" aria-hidden="true" /></>;
}
