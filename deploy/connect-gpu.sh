#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec ssh -N -p 23271 -o BatchMode=yes -o ExitOnForwardFailure=yes \
 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
 -o UserKnownHostsFile="$HERE/known_hosts" \
 -L 127.0.0.1:18030:127.0.0.1:8030 -L 127.0.0.1:18020:127.0.0.1:8020 \
 root@cpod-1v5bo22hshhu.podtcp.compshare.cn
