#!/bin/bash
set -e

#
# 마스터 노드 설치 (slurmctld + slurmdbd + mariadb + slurmd)
# 사전조건: setup-common.sh 실행 완료
# 사용법: sudo bash scripts/setup-master.sh
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== 마스터 노드 설치 ==="

echo "[1/5] MariaDB 설치..."
apt install -y mariadb-server libmariadb-dev
systemctl enable --now mariadb
mysql -u root << 'SQL'
CREATE DATABASE IF NOT EXISTS slurm_acct_db;
CREATE USER IF NOT EXISTS 'slurm'@'localhost' IDENTIFIED BY 'SlurmDBPassword';
GRANT ALL PRIVILEGES ON slurm_acct_db.* TO 'slurm'@'localhost';
FLUSH PRIVILEGES;
SQL

echo "[2/5] Munge 키 설정..."
if [ -f /etc/munge/munge.key ]; then
    echo "  munge 키가 이미 존재합니다. 기존 키를 사용합니다."
else
    /usr/sbin/mungekey
fi
chown munge:munge /etc/munge/munge.key
chmod 400 /etc/munge/munge.key
systemctl enable --now munge

echo "[3/5] SLURM 빌드..."
if [ ! -d /tmp/slurm ]; then
    cd /tmp
    git clone --depth 1 -b slurm-25-11-2-1 https://github.com/SchedMD/slurm.git
fi
cd /tmp/slurm
# Ubuntu 24.04: mysql_config → mariadb_config로 이름 변경됨. 심볼릭 링크 생성
if [ ! -f /usr/bin/mysql_config ] && [ -f /usr/bin/mariadb_config ]; then
    ln -sf /usr/bin/mariadb_config /usr/bin/mysql_config
    echo "  Created symlink: mysql_config → mariadb_config"
fi
./configure --prefix=/usr --sysconfdir=/etc/slurm \
    --with-mysql_config=/usr/bin --with-munge=/usr
make -j$(nproc)
make install

cp etc/slurmctld.service /etc/systemd/system/
cp etc/slurmd.service /etc/systemd/system/
cp etc/slurmdbd.service /etc/systemd/system/
systemctl daemon-reload

echo "[4/5] slurm.conf 생성 & 배포..."
bash "$SCRIPT_DIR/generate-slurm-conf.sh"
cp "$PROJECT_DIR/config/slurm.conf" /etc/slurm/
cp "$PROJECT_DIR/config/slurmdbd.conf" /etc/slurm/
cp "$PROJECT_DIR/config/gres.conf" /etc/slurm/
cp "$PROJECT_DIR/config/cgroup.conf" /etc/slurm/
chown slurm:slurm /etc/slurm/slurmdbd.conf
chmod 600 /etc/slurm/slurmdbd.conf

echo "[5/5] 데몬 시작..."
systemctl enable --now slurmdbd
sleep 3
systemctl enable --now slurmctld
sleep 2
systemctl enable --now slurmd

# 클러스터/계정 등록
sacctmgr -i add cluster gpucluster 2>/dev/null || true
sacctmgr -i add account research Description="Research" 2>/dev/null || true
sacctmgr -i add user $(logname 2>/dev/null || echo $SUDO_USER) Account=research 2>/dev/null || true

echo ""
echo "=== 마스터 설치 완료 ==="
echo ""
echo "다음 단계 - 각 워커 노드에 munge 키 복사:"

grep -v '^#' "$PROJECT_DIR/cluster.conf" | grep -v '^\s*$' | while read -r NAME IP _ _ _ _ ROLE; do
    if [ "$ROLE" = "worker" ]; then
        echo "  scp /etc/munge/munge.key <user>@${IP}:/tmp/"
    fi
done

echo ""
echo "워커 노드에서 실행:"
echo "  sudo bash scripts/setup-common.sh"
echo "  sudo bash scripts/setup-worker.sh"
echo ""
sinfo
