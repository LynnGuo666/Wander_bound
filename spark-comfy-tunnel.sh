#!/usr/bin/env bash
set -euo pipefail

exec ssh -N -i "${SPARK_SSH_KEY:-$HOME/.ssh/id_ed25519}" \
  -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes -p 6082 \
  -L 127.0.0.1:18188:127.0.0.1:8188 \
  -L 127.0.0.1:18191:127.0.0.1:8191 \
  -L 127.0.0.1:14176:127.0.0.1:4176 \
  -L 127.0.0.1:14177:127.0.0.1:4177 \
  -L 127.0.0.1:14178:127.0.0.1:4178 \
  -L 127.0.0.1:14174:127.0.0.1:4174 \
  Developer@106.13.186.155
