import test from 'node:test';
import assert from 'node:assert/strict';
import { PlaneGeometry } from 'three';
import { posePageCurl } from './pageCurl.js';

function sample(geometry, base, progress, direction, distance) {
  const face = posePageCurl(geometry, base, progress, direction);
  const vertex = [...Array(geometry.attributes.position.count).keys()]
    .find(index => Math.abs(base[index * 3] + .5 - distance) < 1e-6);
  return { face, x: geometry.attributes.position.getX(vertex),
    z: geometry.attributes.position.getZ(vertex), u: geometry.attributes.uv.getX(vertex) };
}

test('forward and backward turns land on the correct page with readable reverse textures', () => {
  const geometry = new PlaneGeometry(1, 1, 4, 1);
  const base = geometry.attributes.position.array.slice();
  const nextStart = sample(geometry, base, 0, 'next', 1);
  const nextEnd = sample(geometry, base, 1, 'next', 1);
  const previousStart = sample(geometry, base, 0, 'previous', 1);
  const previousEnd = sample(geometry, base, 1, 'previous', 1);
  assert.deepEqual([nextStart.face, nextStart.x, nextStart.u], ['front', 1, 1]);
  assert.deepEqual([nextEnd.face, nextEnd.x, nextEnd.u], ['back', -1, 0]);
  assert.deepEqual([previousStart.face, previousStart.x, previousStart.u], ['front', -1, 0]);
  assert.deepEqual([previousEnd.face, previousEnd.x, previousEnd.u], ['back', 1, 1]);
  geometry.dispose();
});

test('the middle of a turn bows the sheet toward the viewer', () => {
  const geometry = new PlaneGeometry(1, 1, 4, 1);
  const base = geometry.attributes.position.array.slice();
  const midpoint = sample(geometry, base, .5, 'next', .5);
  assert.ok(midpoint.x > .2);
  assert.ok(midpoint.z > .25);
  geometry.dispose();
});
