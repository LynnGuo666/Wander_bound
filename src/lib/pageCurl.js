/** Pose one paper leaf; the caller swaps front/back textures at the edge-on phase. */
export function posePageCurl(geometry, basePositions, progress, direction) {
  const angle = Math.PI * progress;
  const sine = Math.sin(angle);
  const cosine = Math.cos(angle);
  const faceDirection = direction === 'next' ? 1 : -1;
  const face = progress < .5 ? 'front' : 'back';
  const mirror = (face === 'front') === (direction !== 'next');
  const positions = geometry.attributes.position;
  const uvs = geometry.attributes.uv;
  for (let index = 0; index < positions.count; index++) {
    const edgeDistance = basePositions[index * 3] + .5;
    const y = basePositions[index * 3 + 1];
    const bow = .25 * Math.sin(Math.PI * edgeDistance) * sine;
    positions.setXYZ(index, faceDirection * (edgeDistance * cosine + bow), y,
      .13 * edgeDistance * sine + .22 * Math.sin(Math.PI * edgeDistance) * sine);
    uvs.setX(index, mirror ? 1 - edgeDistance : edgeDistance);
  }
  positions.needsUpdate = true;
  uvs.needsUpdate = true;
  geometry.computeVertexNormals();
  return face;
}
