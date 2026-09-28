#!/usr/bin/env python3
"""Idempotently register four public JPEGs in an isolated Spark test trip.

Only source metadata and hashes enter the receipt. JPEG bytes travel over the
already trusted SSH connection and then the loopback media API; no token is
printed, transmitted back to the Mac, or written to this repository.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs/validation-assets/m01-public-yellowstone.json"
DEFAULT_RECEIPT = ROOT / "docs/validation-assets/m01-public-yellowstone-receipt.json"
EXPECTED_DEPLOY_SHA = "24aae844e252fe7cd8606a8f25ede45b66990dc0"

REMOTE_CODE = r'''
import base64, hashlib, json, os, subprocess, sys
from pathlib import Path
import httpx
from pyserver.trips.store import TripStore
from pyserver.media.images import normalize

payload = json.load(sys.stdin)
sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
if sha != payload['expected_deploy_sha'] or subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
    raise RuntimeError('Spark deployment SHA changed or checkout is dirty; review before import')
pid = subprocess.check_output(['systemctl', '--user', 'show', 'travel-agent.service', '-p', 'MainPID', '--value'], text=True).strip()
env = Path('/proc', pid, 'environ').read_bytes().split(b'\0')
token = next((part.partition(b'=')[2].decode() for part in env if part.startswith(b'MEDIA_API_TOKEN=')), '')
if not token:
    for line in Path('/home/Developer/travel-agent/.env').read_text().splitlines():
        if line.startswith('MEDIA_API_TOKEN='):
            token = line.split('=', 1)[1].strip().strip('"').strip("'")
            break
if not token:
    raise RuntimeError('Media token unavailable in service environment')
headers = {'Authorization': 'Bearer ' + token}
trips = TripStore()
matches = [trip for path in trips.root.glob('*.json')
           if (trip := trips.get(path.stem)) and (trip.get('request') or {}).get('fixtureKey') == payload['fixture_key']]
if len(matches) > 1:
    raise RuntimeError('Multiple fixture trips found; manual reconciliation required')
trip = matches[0] if matches else trips.create({
    'query': 'M01 公共照片人工验收集合（多日期，非真实行程）',
    'fixtureKey': payload['fixture_key'],
    'kind': 'manual-public-photo-acceptance',
})
trip_id = trip['id']
receipt = {'schema_version': 1, 'deployment_sha': sha, 'trip_id': trip_id,
           'trip_creation': 'TripStore.create' if not matches else 'TripStore.get (reused)',
           'fixture_key': payload['fixture_key'], 'batch_id': payload['batch_id'],
           'source': payload['source'], 'photos': []}
with httpx.Client(base_url='http://127.0.0.1:4174', timeout=45) as client:
    listed = client.get('/api/media/photos', params={'tripId': trip_id}, headers=headers)
    listed.raise_for_status()
    existing = {}
    for photo in listed.json()['photos']:
        original = client.get('/api/media/photos/' + photo['id'], params={'variant': 'original'}, headers=headers)
        original.raise_for_status()
        existing.setdefault(hashlib.sha256(original.content).hexdigest(), []).append(photo['id'])
    for card in payload['photos']:
        source = base64.b64decode(card['jpeg_b64'], validate=True)
        if hashlib.sha256(source).hexdigest() != card['source_sha256']:
            raise RuntimeError('Source JPEG hash changed: ' + str(card['page_id']))
        normalized, width, height = normalize(source)
        digest = hashlib.sha256(normalized).hexdigest()
        candidates = existing.get(digest, [])
        if len(candidates) > 1:
            raise RuntimeError('Duplicate originals in fixture trip: ' + str(card['page_id']))
        if candidates:
            photo_id, upload_status = candidates[0], 'reused'
        else:
            upload_headers = {**headers, 'X-Trip-Id': trip_id, 'Content-Type': 'image/jpeg'}
            if card.get('captured_day'):
                upload_headers['X-Captured-Day'] = card['captured_day']
            created = client.post('/api/media/photos', headers=upload_headers, content=source)
            created.raise_for_status()
            if created.status_code != 201:
                raise RuntimeError('Unexpected upload status')
            photo_id, upload_status = created.json()['id'], 201
            existing[digest] = [photo_id]
        original = client.get('/api/media/photos/' + photo_id, params={'variant': 'original'}, headers=headers)
        original.raise_for_status()
        if hashlib.sha256(original.content).hexdigest() != digest:
            raise RuntimeError('Original readback hash mismatch: ' + str(card['page_id']))
        receipt['photos'].append({'page_id': card['page_id'], 'photo_id': photo_id,
                                  'upload_status': upload_status, 'original_get_status': original.status_code,
                                  'source_sha256': card['source_sha256'], 'original_sha256': digest,
                                  'original_width': width, 'original_height': height})
    ids = [item['photo_id'] for item in receipt['photos']]
    before = client.get('/api/media/trips/' + trip_id + '/selected-photos', headers=headers)
    before.raise_for_status()
    prior = before.json()
    if prior['photoIds'] and (prior['photoIds'] != ids or prior['batchId'] != payload['batch_id'] or prior['source'] != payload['source']):
        raise RuntimeError('Existing fixture selection differs; refusing to replace it')
    selected = client.put('/api/media/trips/' + trip_id + '/selected-photos', headers=headers,
                          json={'batchId': payload['batch_id'], 'source': payload['source'], 'photoIds': ids})
    selected.raise_for_status()
    reread = client.get('/api/media/trips/' + trip_id + '/selected-photos', headers=headers)
    reread.raise_for_status()
    selection = reread.json()
    if selection['photoIds'] != ids or selection['batchId'] != payload['batch_id'] or selection['source'] != payload['source']:
        raise RuntimeError('Selected-photos readback mismatch')
    receipt['selection_put_status'] = selected.status_code
    receipt['selection_get_status'] = reread.status_code
    receipt['selection_updated_at'] = selection['updatedAt']
    receipt['selection_count'] = len(selection['photoIds'])
print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--fixture-dir", type=Path, default=Path("/private/tmp/travel-public-fixtures"))
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    cards = []
    for card in manifest["photos"]:
        raw = (args.fixture_dir / card["file"]).read_bytes()
        if not raw.startswith(b"\xff\xd8") or len(raw) > 15 * 1024 * 1024:
            raise ValueError(f"Invalid JPEG or upload limit exceeded: {card['page_id']}")
        if hashlib.sha256(raw).hexdigest() != card["source_sha256"]:
            raise ValueError(f"Source hash mismatch: {card['page_id']}")
        cards.append({"page_id": card["page_id"], "source_sha256": card["source_sha256"],
                      "captured_day": card["captured_day"], "jpeg_b64": base64.b64encode(raw).decode("ascii")})
    payload = {"expected_deploy_sha": EXPECTED_DEPLOY_SHA, "fixture_key": manifest["fixture_key"],
               "batch_id": manifest["batch_id"], "source": manifest["source"], "photos": cards}
    runner = "import base64; exec(base64.b64decode('" + base64.b64encode(REMOTE_CODE.encode()).decode() + "'))"
    command = ["ssh", "-S", "/private/tmp/travel-spark-control-20260928", "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=/private/tmp/travel-spark-known-hosts-20260928",
               "-p", "6082", "Developer@106.13.186.155",
               "cd /home/Developer/travel-agent && .venv/bin/python -c \"" + runner + "\""]
    result = subprocess.run(command, input=json.dumps(payload).encode(), capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError("Spark fixture registration failed: " + result.stderr.decode(errors="replace")[-1000:])
    receipt = json.loads(result.stdout)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.receipt.with_suffix(".tmp")
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, args.receipt)
    print(f"trip={receipt['trip_id']} selected={receipt['selection_count']} receipt={args.receipt}")


if __name__ == "__main__":
    main()
