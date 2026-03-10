#!/bin/bash
set -e

#
# 공통 설치 (모든 노드에서 실행)
# 사용법: sudo bash scripts/setup-common.sh
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CLUSTER_CONF="$PROJECT_DIR/cluster.conf"

# 현재 호스트명으로 cluster.conf에서 정보 조회
CURRENT_HOST=$(hostname)
NODE_INFO=$(grep -v '^#' "$CLUSTER_CONF" | grep -v '^\s*$' | grep "^${CURRENT_HOST}\s" || true)

if [ -z "$NODE_INFO" ]; then
    echo "WARNING: 현재 호스트명 '${CURRENT_HOST}'이 cluster.conf에 없습니다."
    echo "cluster.conf에 등록된 노드:"
    grep -v '^#' "$CLUSTER_CONF" | grep -v '^\s*$' | awk '{print "  " $1 " (" $2 ")"}'
    echo ""
    echo "호스트명을 먼저 설정하세요: sudo hostnamectl set-hostname <이름>"
    exit 1
fi

echo "=== SLURM 공통 설치: ${CURRENT_HOST} ==="

echo "[1/5] 의존성 설치..."
apt update && apt install -y build-essential git munge libmunge-dev libmunge2 \
    libpam0g-dev libhwloc-dev liblua5.3-dev libjson-c-dev libjwt-dev \
    libhttp-parser-dev libdbus-1-dev libnuma-dev libreadline-dev libssl-dev python3 \
    pkg-config autoconf automake nfs-common

echo "[2/5] /etc/hosts 설정..."
grep -v '^#' "$CLUSTER_CONF" | grep -v '^\s*$' | while read -r NAME IP _ _ _ _ _; do
    if ! grep -q "${IP}.*${NAME}" /etc/hosts; then
        echo "${IP}  ${NAME}" >> /etc/hosts
    fi
done

echo "[3/5] 시간 동기화..."
timedatectl set-ntp true

echo "[4/5] slurm 사용자 생성..."
if ! id slurm &>/dev/null; then
    groupadd -g 1100 slurm
    useradd -m -u 1100 -g 1100 -s /bin/bash slurm
fi

echo "[5/5] 디렉토리 생성..."
mkdir -p /etc/slurm /var/spool/slurm /var/log/slurm /var/run/slurm /var/lib/slurm
chown -R slurm:slurm /var/spool/slurm /var/log/slurm /var/run/slurm /var/lib/slurm

echo "=== 공통 설치 완료: ${CURRENT_HOST} ==="
