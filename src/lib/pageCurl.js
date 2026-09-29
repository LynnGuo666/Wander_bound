/** Bend a leaf continuously between the measured left and right page bounds. */
export function posePageCurl(geometry, basePositions, progress, direction, pageWidth = 1, gutter = 0) {
  const angle = Math.PI * progress;
  const bend = 1.25 * Math.sin(angle);
  const faceDirection = direction === 'next' ? 1 : -1;
  const positions = geometry.attributes.position;
  for (let index = 0; index < positions.count; index++) {
    const edgeDistance = basePositions[index * 3] + pageWidth / 2;
    const alongPage = edgeDistance / pageWidth;
    const y = basePositions[index * 3 + 1];
    // Integrate a rotating tangent along the paper. The radius changes smoothly
    // through the turn while the sheet travels across the binder's center gap.
    const horizontal = bend < 1e-4
      ? edgeDistance * Math.cos(angle)
      : pageWidth / bend * (Math.sin(angle + bend * (alongPage - .5)) - Math.sin(angle - bend / 2));
    const lift = bend < 1e-4
      ? edgeDistance * Math.sin(angle)
      : pageWidth / bend * (Math.cos(angle - bend / 2) - Math.cos(angle + bend * (alongPage - .5)));
    positions.setXYZ(index, faceDirection * (gutter / 2 * Math.cos(angle) + horizontal), y, lift);
  }
  positions.needsUpdate = true;
  geometry.computeVertexNormals();
}

/** The reverse side of a leaf reads in the opposite horizontal direction. */
export function mirrorPageUV(geometry) {
  const uvs = geometry.attributes.uv;
  for (let index = 0; index < uvs.count; index++) uvs.setX(index, 1 - uvs.getX(index));
  uvs.needsUpdate = true;
}
