#!/bin/bash
set -e

#
# 워커 노드 설치 (slurmd만)
# 사전조건: setup-common.sh 실행 + /tmp/munge.key 복사 완료
# 사용법: sudo bash scripts/setup-worker.sh
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== 워커 노드 설치: $(hostname) ==="

echo "[1/3] Munge 설정..."
if [ -f /tmp/munge.key ]; then
    cp /tmp/munge.key /etc/munge/munge.key
    chown munge:munge /etc/munge/munge.key
    chmod 400 /etc/munge/munge.key
    rm -f /tmp/munge.key
else
    echo "ERROR: /tmp/munge.key 없음. 마스터에서 먼저 복사하세요."
    exit 1
fi
systemctl enable --now munge

echo "[2/3] SLURM 빌드..."
if [ ! -d /tmp/slurm ]; then
    cd /tmp
    git clone --depth 1 -b slurm-25-11-2-1 https://github.com/SchedMD/slurm.git
fi
cd /tmp/slurm
./configure --prefix=/usr --sysconfdir=/etc/slurm --with-munge=/usr
make -j$(nproc)
make install

cp etc/slurmd.service /etc/systemd/system/
systemctl daemon-reload

echo "[3/3] 설정 배포 & slurmd 시작..."
cp "$PROJECT_DIR/config/slurm.conf" /etc/slurm/
cp "$PROJECT_DIR/config/gres.conf" /etc/slurm/
cp "$PROJECT_DIR/config/cgroup.conf" /etc/slurm/

systemctl enable --now slurmd

echo ""
echo "=== 워커 설치 완료: $(hostname) ==="
echo "마스터에서 확인: sinfo"
