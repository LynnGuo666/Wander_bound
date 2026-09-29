import test from 'node:test';
import assert from 'node:assert/strict';
import { PlaneGeometry } from 'three';
import { mirrorPageUV, posePageCurl } from './pageCurl.js';

function sample(geometry, base, progress, direction, distance, pageWidth = 1, gutter = 0) {
  posePageCurl(geometry, base, progress, direction, pageWidth, gutter);
  const vertex = [...Array(geometry.attributes.position.count).keys()]
    .find(index => Math.abs(base[index * 3] + pageWidth / 2 - distance) < 1e-6);
  return { x: geometry.attributes.position.getX(vertex),
    z: geometry.attributes.position.getZ(vertex), u: geometry.attributes.uv.getX(vertex) };
}

test('forward and backward turns land on the measured page bounds', () => {
  const geometry = new PlaneGeometry(1, 1, 4, 1);
  const base = geometry.attributes.position.array.slice();
  for (const [progress, direction, expected] of [
    [0, 'next', 1.05], [1, 'next', -1.05],
    [0, 'previous', -1.05], [1, 'previous', 1.05],
  ]) assert.ok(Math.abs(sample(geometry, base, progress, direction, 1, 1, .1).x - expected) < 1e-5);
  geometry.dispose();
});

test('both faces keep readable UVs while the sheet bends through the middle', () => {
  const geometry = new PlaneGeometry(1, 1, 4, 1);
  const reverse = geometry.clone();
  mirrorPageUV(reverse);
  const base = geometry.attributes.position.array.slice();
  const midpoint = sample(geometry, base, .5, 'next', .5);
  assert.ok(midpoint.x > .2);
  assert.ok(midpoint.z > .25);
  assert.equal(sample(geometry, base, .49, 'next', .5).u, .5);
  assert.equal(sample(geometry, base, .51, 'next', .5).u, .5);
  assert.equal(sample(reverse, base, .49, 'next', 0).u, 1);
  assert.equal(sample(reverse, base, .51, 'next', 0).u, 1);
  geometry.dispose();
  reverse.dispose();
});
