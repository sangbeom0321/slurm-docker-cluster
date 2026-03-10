#!/bin/bash
set -e

#
# cluster.conf를 읽어 config/slurm.conf를 자동 생성
# 사용법: bash scripts/generate-slurm-conf.sh
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CLUSTER_CONF="$PROJECT_DIR/cluster.conf"
OUTPUT="$PROJECT_DIR/config/slurm.conf"

if [ ! -f "$CLUSTER_CONF" ]; then
    echo "ERROR: $CLUSTER_CONF not found"
    exit 1
fi

# 마스터 호스트명 찾기
MASTER_HOST=$(grep -v '^#' "$CLUSTER_CONF" | grep -v '^\s*$' | awk '$7=="master" {print $1}')
if [ -z "$MASTER_HOST" ]; then
    echo "ERROR: master 역할 노드가 cluster.conf에 없습니다"
    exit 1
fi

# 모든 노드 이름 수집
ALL_NODES=$(grep -v '^#' "$CLUSTER_CONF" | grep -v '^\s*$' | awk '{print $1}' | paste -sd, -)

# slurm.conf 생성
cat > "$OUTPUT" << CONF
#
# slurm.conf - 자동 생성됨 (generate-slurm-conf.sh)
# 수정하지 마세요. cluster.conf를 수정한 뒤 스크립트를 재실행하세요.
#

ClusterName=gpucluster
SlurmctldHost=${MASTER_HOST}
SlurmUser=slurm
AuthType=auth/munge
AuthAltTypes=auth/jwt
AuthAltParameters=jwt_key=/etc/slurm/jwt_hs256.key

GresTypes=gpu

ProctrackType=proctrack/linuxproc
ReturnToService=1
TaskPlugin=task/affinity

SlurmctldPort=6817
SlurmdPort=6818

SlurmctldPidFile=/var/run/slurm/slurmctld.pid
SlurmdPidFile=/var/run/slurm/slurmd.pid
SlurmdSpoolDir=/var/spool/slurm
StateSaveLocation=/var/lib/slurm

InactiveLimit=0
KillWait=30
MinJobAge=300
SlurmctldTimeout=120
SlurmdTimeout=300
Waittime=0

SchedulerType=sched/backfill
SelectType=select/cons_tres
SelectTypeParameters=CR_Core_Memory

AccountingStorageHost=${MASTER_HOST}
AccountingStorageType=accounting_storage/slurmdbd
JobCompLoc=/var/log/slurm/jobcomp.log
JobCompType=jobcomp/filetxt
JobAcctGatherFrequency=30
SlurmctldDebug=info
SlurmctldLogFile=/var/log/slurm/slurmctld.log
SlurmdDebug=info
SlurmdLogFile=/var/log/slurm/slurmd.log

# ============================================================
# 노드 정의 (cluster.conf에서 자동 생성)
# ============================================================
CONF

# 노드 엔트리 생성
grep -v '^#' "$CLUSTER_CONF" | grep -v '^\s*$' | while read -r NAME IP CPUS MEM GPU_TYPE GPU_COUNT ROLE; do
    echo "NodeName=${NAME} NodeAddr=${IP} CPUs=${CPUS} RealMemory=${MEM} Gres=gpu:${GPU_TYPE}:${GPU_COUNT} State=UNKNOWN" >> "$OUTPUT"
done

# 파티션 추가
cat >> "$OUTPUT" << CONF

# ============================================================
# 파티션
# ============================================================
PartitionName=all Nodes=${ALL_NODES} Default=YES MaxTime=INFINITE State=UP
CONF

# slurmdbd.conf도 마스터 호스트명 반영
SLURMDBD_CONF="$PROJECT_DIR/config/slurmdbd.conf"
if [ -f "$SLURMDBD_CONF" ]; then
    sed -i "s/^DbdHost=.*/DbdHost=${MASTER_HOST}/" "$SLURMDBD_CONF"
fi

echo "Generated: $OUTPUT"
echo "Master: ${MASTER_HOST}"
echo "Nodes: ${ALL_NODES}"
cat "$OUTPUT" | grep "^NodeName="
