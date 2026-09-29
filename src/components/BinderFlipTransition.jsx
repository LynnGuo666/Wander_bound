import React, { useLayoutEffect, useRef, useState } from 'react';
import { toCanvas } from 'html-to-image';
import * as THREE from 'three';
import { PageFlip } from 'page-flip/dist/js/page-flip.module.js';
import { posePageCurl } from '../lib/pageCurl.js';

const TURN_MS = 1050;
const CAPTURE_SCALE = 1.5;

function withTimeout(promise, ms) {
  let timer;
  return Promise.race([promise, new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('Page capture timed out')), ms);
  })]).finally(() => clearTimeout(timer));
}

function waitForPreview(preview, onCancel) {
  return new Promise(resolve => {
    if (!preview) { resolve(false); return; }
    const ready = () => preview.dataset.previewReady === 'true'
      && ![...preview.querySelectorAll('.media-placeholder')].some(node => node.textContent?.includes('正在加载'));
    if (ready()) { resolve(true); return; }
    let settled = false;
    const observer = new MutationObserver(() => { if (ready()) finish(true); });
    const timer = setTimeout(() => finish(ready()), 2500);
    function finish(value) {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      observer.disconnect();
      resolve(value);
    }
    onCancel(() => finish(false));
    observer.observe(preview, { subtree: true, childList: true, attributes: true });
  });
}

function loadPaper() {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = reject;
    image.src = '/art/binder-paper.webp';
  });
}

async function capturePage(node, paper, side) {
  const capture = await toCanvas(node, {
    pixelRatio: CAPTURE_SCALE,
    skipFonts: true,
    style: { visibility: 'visible' },
  });
  const width = Math.max(1, Math.round(capture.width / .923));
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = capture.height;
  const context = canvas.getContext('2d');
  context.fillStyle = '#fff9ed';
  context.fillRect(0, 0, width, canvas.height);
  if (side === 'left') {
    context.save();
    context.translate(width, 0);
    context.scale(-1, 1);
    context.drawImage(paper, 0, 0, width, canvas.height);
    context.restore();
  } else context.drawImage(paper, 0, 0, width, canvas.height);
  context.drawImage(capture, side === 'left' ? 0 : width - capture.width, 0);
  return canvas;
}

function textureFrom(canvas) {
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}

function WebGLPageCurl({ direction, stageRef, incomingRef, onComplete, onFail }) {
  const hostRef = useRef(null);
  const completeRef = useRef(onComplete);
  const failRef = useRef(onFail);
  completeRef.current = onComplete;
  failRef.current = onFail;
  useLayoutEffect(() => {
    const host = hostRef.current;
    const stage = stageRef.current;
    const preview = incomingRef.current;
    if (!host || !stage) return;
    let active = true;
    let frame = 0;
    let cancelPreview = () => {};
    let renderer;
    const resources = [];
    async function start() {
      const ready = await waitForPreview(preview, cancel => { cancelPreview = cancel; });
      if (!active) return;
      if (!ready) { failRef.current(); return; }
      const source = [...stage.querySelectorAll(':scope > .studio-page > .studio-canvas')];
      const incoming = [...preview.querySelectorAll(':scope > .studio-page > .studio-canvas')];
      if (source.length !== 2 || incoming.length !== 2) { failRef.current(); return; }
      const paper = await loadPaper();
      const images = [...source, ...incoming].flatMap(node => [...node.querySelectorAll('img')]);
      await withTimeout(Promise.all(images.map(image => image.decode().catch(() => {}))), 600)
        .catch(() => {});
      if (!active) return;
      const captures = await withTimeout(Promise.all([...source, ...incoming].map((node, index) =>
        capturePage(node, paper, index % 2 ? 'right' : 'left'))), 3500);
      if (!active) return;
      const textures = captures.map(textureFrom);
      resources.push(...textures);
      const width = host.clientWidth;
      const height = host.clientHeight;
      if (width < 1 || height < 1) throw new Error('Book has no visible size');
      renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'high-performance' });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(width, height);
      renderer.setClearColor(0xffffff, 0);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      host.appendChild(renderer.domElement);
      const pageHeight = 2 * height / width;
      const scene = new THREE.Scene();
      const camera = new THREE.OrthographicCamera(-1, 1, pageHeight / 2, -pageHeight / 2, .01, 10);
      camera.position.set(0, 0, 5);
      camera.lookAt(0, 0, 0);
      scene.add(new THREE.AmbientLight(0xffffff, 1.15));
      const light = new THREE.DirectionalLight(0xffffff, .55);
      light.position.set(-.7, 1.1, 2);
      scene.add(light);
      const current = textures.slice(0, 2);
      const target = textures.slice(2);
      function flatPage(texture, x) {
        const geometry = new THREE.PlaneGeometry(1, pageHeight);
        const material = new THREE.MeshBasicMaterial({ map: texture });
        resources.push(geometry, material);
        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(x, 0, .005);
        scene.add(mesh);
      }
      if (direction === 'next') {
        flatPage(current[0], -.5);
        flatPage(target[1], .5);
      } else {
        flatPage(target[0], -.5);
        flatPage(current[1], .5);
      }
      const shadowCanvas = document.createElement('canvas');
      shadowCanvas.width = 256;
      shadowCanvas.height = 2;
      const shadowContext = shadowCanvas.getContext('2d');
      const gradient = shadowContext.createLinearGradient(0, 0, 256, 0);
      gradient.addColorStop(0, 'rgba(52,38,28,.42)');
      gradient.addColorStop(.32, 'rgba(52,38,28,.17)');
      gradient.addColorStop(1, 'rgba(52,38,28,0)');
      shadowContext.fillStyle = gradient;
      shadowContext.fillRect(0, 0, 256, 2);
      const shadowTexture = textureFrom(shadowCanvas);
      resources.push(shadowTexture);
      const shadowGeometry = new THREE.PlaneGeometry(1, pageHeight);
      resources.push(shadowGeometry);
      const shadowMaterials = [0, 1].map(() => new THREE.MeshBasicMaterial({ map: shadowTexture,
        transparent: true, depthWrite: false, opacity: 0 }));
      resources.push(...shadowMaterials);
      const shadows = shadowMaterials.map((material, index) => {
        const mesh = new THREE.Mesh(shadowGeometry, material);
        mesh.position.set(index ? .5 : -.5, 0, .015);
        mesh.scale.x = index ? 1 : -1;
        scene.add(mesh);
        return mesh;
      });
      const geometry = new THREE.PlaneGeometry(1, pageHeight, 36, 12);
      const base = geometry.attributes.position.array.slice();
      const frontTexture = direction === 'next' ? current[1] : current[0];
      const backTexture = direction === 'next' ? target[0] : target[1];
      const front = new THREE.MeshStandardMaterial({ map: frontTexture, roughness: 1, side: THREE.DoubleSide });
      const back = new THREE.MeshStandardMaterial({ map: backTexture, roughness: 1, side: THREE.DoubleSide });
      resources.push(geometry, front, back);
      const leaf = new THREE.Mesh(geometry, front);
      leaf.position.z = .04;
      scene.add(leaf);
      let face = 'front';
      function draw(progress) {
        const sine = Math.sin(Math.PI * progress);
        const nextFace = posePageCurl(geometry, base, progress, direction);
        if (nextFace !== face) { leaf.material = nextFace === 'front' ? front : back; face = nextFace; }
        shadows[0].material.opacity = .68 * sine * (direction === 'next' ? progress : 1 - progress);
        shadows[1].material.opacity = .68 * sine * (direction === 'next' ? 1 - progress : progress);
        renderer.render(scene, camera);
      }
      draw(0);
      if (!active) return;
      stage.classList.add('flip-active');
      let startedAt;
      function tick(time) {
        if (!active) return;
        if (startedAt === undefined) startedAt = time;
        const t = Math.min((time - startedAt) / TURN_MS, 1);
        draw(t * t * (3 - 2 * t));
        if (t < 1) frame = requestAnimationFrame(tick);
        else completeRef.current?.();
      }
      frame = requestAnimationFrame(tick);
    }
    start().catch(() => { if (active) failRef.current(); });
    return () => {
      active = false;
      cancelPreview();
      cancelAnimationFrame(frame);
      stage.classList.remove('flip-active');
      renderer?.dispose();
      renderer?.domElement.remove();
      resources.forEach(resource => resource.dispose());
    };
  }, [direction, stageRef, incomingRef]);
  return <><div className="binder-curl-host" ref={hostRef} aria-hidden="true" />
    <img className="binder-flip-rings" src="/art/binder-rings.png" alt="" aria-hidden="true" /></>;
}

/** Fallback for browsers without WebGL or DOM texture capture. */
function StPageFlipTransition({ direction, stageRef, incomingRef, onComplete }) {
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
    let completionTimer;
    let completed = false;
    const complete = () => {
      if (!active || completed) return;
      completed = true;
      completeRef.current?.();
    };
    const preview = incomingRef.current;
    const previewPainted = () => preview?.dataset.previewReady === 'true'
      && ![...preview.querySelectorAll('.media-placeholder')].some(node => node.textContent?.includes('正在加载'));
    const waitForPreview = () => new Promise(resolve => {
      if (previewPainted()) { resolve(true); return; }
      if (!preview) { resolve(false); return; }
      let settled = false;
      const observer = new MutationObserver(() => { if (previewPainted()) finish(true); });
      const timer = setTimeout(() => finish(preview?.dataset.previewReady === 'true'), 2500);
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
      if (!await waitForPreview() || !active) { complete(); return; }
      const source = stage.querySelectorAll(':scope > .studio-page > .studio-canvas');
      const incoming = preview.querySelectorAll(':scope > .studio-page > .studio-canvas');
      if (source.length !== 2 || incoming.length !== 2) { complete(); return; }
      const images = [...source, ...incoming].flatMap(canvas => [...canvas.querySelectorAll('img')]);
      await Promise.race([
        Promise.all(images.map(img => img.decode().catch(() => {}))),
        new Promise(resolve => { imageTimer = setTimeout(resolve, 450); }),
      ]);
      clearTimeout(imageTimer);
      if (!active) return;
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
        if (event.data === 'read' && started) complete();
      });
      flip.loadFromHTML(pages);
      frame = requestAnimationFrame(() => {
        if (!active) return;
        stage.classList.add('flip-active');
        direction === 'next' ? flip.flipNext() : flip.flipPrev();
        completionTimer = setTimeout(complete, 1500);
      });
    }
    start().catch(complete);
    return () => {
      active = false;
      cancelWait();
      clearTimeout(imageTimer);
      clearTimeout(completionTimer);
      cancelAnimationFrame(frame);
      stage.classList.remove('flip-active');
      flip?.destroy();
    };
  }, [direction, stageRef, incomingRef]);
  return <><div className="binder-flip-host" ref={hostRef} aria-hidden="true" /><img className="binder-flip-rings" src="/art/binder-rings.png" alt="" aria-hidden="true" /></>;
}

export default function BinderFlipTransition(props) {
  const [fallback, setFallback] = useState(false);
  return fallback ? <StPageFlipTransition {...props} />
    : <WebGLPageCurl {...props} onFail={() => setFallback(true)} />;
}
