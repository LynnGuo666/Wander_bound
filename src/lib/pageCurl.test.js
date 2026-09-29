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
  assert.ok(midpoint.x > .1);
  assert.ok(midpoint.z > .45);
  assert.equal(sample(geometry, base, .49, 'next', .5).u, .5);
  assert.equal(sample(geometry, base, .51, 'next', .5).u, .5);
  assert.equal(sample(reverse, base, .49, 'next', 0).u, 1);
  assert.equal(sample(reverse, base, .51, 'next', 0).u, 1);
  geometry.dispose();
  reverse.dispose();
});

test('turning carries the hinge across the binder and preserves paper length', () => {
  const geometry = new PlaneGeometry(1, 1, 36, 1);
  const base = geometry.attributes.position.array.slice();
  for (const direction of ['next', 'previous']) {
    for (const progress of [.1, .25, .5, .75, .9]) {
      const hinge = sample(geometry, base, progress, direction, 0, 1, .1);
      assert.ok(Math.abs(hinge.x - (direction === 'next' ? .05 : -.05) * Math.cos(Math.PI * progress)) < 1e-5);
      assert.ok(Math.abs(hinge.z) < 1e-5);
      posePageCurl(geometry, base, progress, direction, 1, .1);
      const vertices = geometry.attributes.position;
      for (let index = 1; index < 37; index++) {
        const segment = Math.hypot(vertices.getX(index) - vertices.getX(index - 1),
          vertices.getZ(index) - vertices.getZ(index - 1));
        assert.ok(Math.abs(segment - 1 / 36) < .0001);
      }
    }
  }
  geometry.dispose();
});
