# SLURM 클러스터 구축 가이드

> 서버 9대 (GPU) + NAS 환경 | SLURM 25.11.2 | Ubuntu 22.04/24.04 LTS | 2026년 3월 기준

---

## 1. 전체 아키텍처

### 서버 역할 배정

| 서버 | 호스트명 | IP (예시) | GPU | 역할 | 실행 데몬 |
|------|---------|-----------|-----|------|----------|
| computer0 | computer0 | 192.168.1.10 | 3080 x4 | **마스터 + 계산** | slurmctld, slurmdbd, mariadb, slurmd, munge |
| computer1 | computer1 | 192.168.1.11 | 3090 x4 | 계산 노드 | slurmd, munge |
| computer2 | computer2 | 192.168.1.12 | 3090 x4 | 계산 노드 | slurmd, munge |
| computer3 | computer3 | 192.168.1.13 | 3090 x4 | 계산 노드 | slurmd, munge |
| computer4 | computer4 | 192.168.1.14 | 3090 x4 | 계산 노드 | slurmd, munge |
| computer5 | computer5 | 192.168.1.15 | 4090 x4 | 계산 노드 | slurmd, munge |
| computer6 | computer6 | 192.168.1.16 | 4090 x4 | 계산 노드 | slurmd, munge |
| computer7 | computer7 | 192.168.1.17 | 4090 x4 | 계산 노드 | slurmd, munge |
| computer8 | computer8 | 192.168.1.18 | A6000 x4 | 계산 노드 | slurmd, munge |
| NAS | nas | 192.168.1.20 | - | 공유 스토리지 | NFS server |

> computer0이 마스터(slurmctld + slurmdbd)를 겸하면서 계산 노드(slurmd)로도 동작합니다.

### 네트워크 구성도

```
                         ┌─────────┐
                         │   NAS   │  192.168.1.20
                         │  (NFS)  │
                         └────┬────┘
                              │
      ┌───────────────────────┼───────────────────────┐
      │                       │                       │
 ┌────┴──────┐    ┌───────────┴───────────┐    ┌──────┴──────┐
 │ computer0 │    │  computer1~4 (3090x4) │    │ computer8   │
 │ 마스터+계산│    │  계산 노드             │    │ A6000 x4    │
 │ slurmctld │    ├───────────────────────┤    │ 계산 노드    │
 │ slurmdbd  │    │  computer5~7 (4090x4) │    └─────────────┘
 │ mariadb   │    │  계산 노드             │
 │ slurmd    │    └───────────────────────┘
 │ 3080 x4   │
 └───────────┘
 192.168.1.10      192.168.1.11~17          192.168.1.18
```

### 파티션 (큐) 설계

| 파티션 | 노드 | GPU | 용도 |
|--------|------|-----|------|
| all (기본) | computer[0-8] | 혼합 | 전체 노드 사용 |
| 3090 | computer[1-4] | 3090 x4 | 3090 전용 잡 |
| 4090 | computer[5-7] | 4090 x4 | 4090 전용 잡 |
| a6000 | computer8 | A6000 x4 | A6000 전용 잡 (VRAM 48GB) |

### 공유 디렉토리 구조

```
NAS:/volume1/cluster/
├── home/          → 모든 노드 /home 에 마운트 (사용자 홈)
├── data/          → 모든 노드 /data 에 마운트 (잡 데이터, 학습 데이터셋)
└── sw/            → 모든 노드 /sw 에 마운트 (공용 소프트웨어, conda 등)
```

---

## 2. 사전 준비 (모든 서버 9대에서 실행)

### 2.1 OS 업데이트 및 빌드 의존성 설치

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential git munge libmunge-dev libmunge2 \
    libmariadb-dev libpam0g-dev libhwloc-dev liblua5.3-dev \
    libjson-c-dev libjwt-dev libhttp-parser-dev libdbus-1-dev \
    libnuma-dev libreadline-dev libssl-dev python3 pkg-config \
    autoconf automake
```

### 2.2 호스트명 설정

```bash
# 각 서버에서 해당 호스트명으로 설정
sudo hostnamectl set-hostname computer0   # 서버0 (마스터)
sudo hostnamectl set-hostname computer1   # 서버1
sudo hostnamectl set-hostname computer2   # 서버2
sudo hostnamectl set-hostname computer3   # 서버3
sudo hostnamectl set-hostname computer4   # 서버4
sudo hostnamectl set-hostname computer5   # 서버5
sudo hostnamectl set-hostname computer6   # 서버6
sudo hostnamectl set-hostname computer7   # 서버7
sudo hostnamectl set-hostname computer8   # 서버8
```

### 2.3 /etc/hosts 편집 (모든 서버 동일)

```bash
sudo tee -a /etc/hosts << 'EOF'
192.168.1.10  computer0
192.168.1.11  computer1
192.168.1.12  computer2
192.168.1.13  computer3
192.168.1.14  computer4
192.168.1.15  computer5
192.168.1.16  computer6
192.168.1.17  computer7
192.168.1.18  computer8
192.168.1.20  nas
EOF
```

### 2.4 NTP 시간 동기화 (필수 - munge 인증에 필요)

```bash
# Ubuntu는 systemd-timesyncd가 기본 탑재
sudo timedatectl set-ntp true
timedatectl status

# 또는 chrony 사용
sudo apt install -y chrony
sudo systemctl enable --now chrony

# 동기화 확인
chronyc tracking
```

### 2.5 slurm 사용자/그룹 생성 (모든 서버에서 동일 UID/GID)

```bash
sudo groupadd -g 1100 slurm
sudo useradd -m -u 1100 -g 1100 -s /bin/bash slurm
```

> **중요**: 모든 서버에서 UID/GID가 반드시 동일해야 합니다.

### 2.6 방화벽 포트 개방

```bash
# computer0 (마스터)
sudo ufw allow 6817/tcp   # slurmctld
sudo ufw allow 6818/tcp   # slurmd
sudo ufw allow 6819/tcp   # slurmdbd

# computer1~8 (워커)
sudo ufw allow 6818/tcp   # slurmd

# 모든 서버
sudo ufw reload
sudo ufw status
```

> ufw가 비활성화 상태라면 이 단계는 건너뛰어도 됩니다.

### 2.7 NVIDIA 드라이버 확인 (모든 서버)

```bash
# 드라이버가 이미 설치되어 있는지 확인
nvidia-smi

# 설치되어 있지 않다면
sudo apt install -y nvidia-driver-550
sudo reboot

# 재부팅 후 확인
nvidia-smi
```

---

## 3. NAS/NFS 마운트

### 3.1 NAS 측 NFS export 설정

Synology/QNAP 웹 UI에서 NFS 권한 설정하거나, 리눅스 NAS라면:

```bash
# NAS 서버에서
sudo apt install -y nfs-kernel-server
sudo mkdir -p /volume1/cluster/{home,data,sw}

sudo tee /etc/exports << 'EOF'
/volume1/cluster/home  192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)
/volume1/cluster/data  192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)
/volume1/cluster/sw    192.168.1.0/24(rw,sync,no_subtree_check,no_root_squash)
EOF

sudo systemctl enable --now nfs-kernel-server
sudo exportfs -arv
```

### 3.2 모든 노드에서 NFS 마운트

```bash
# 모든 서버 9대에서 실행
sudo apt install -y nfs-common
sudo mkdir -p /data /sw

# 마운트 테스트
sudo mount -t nfs nas:/volume1/cluster/home /home
sudo mount -t nfs nas:/volume1/cluster/data /data
sudo mount -t nfs nas:/volume1/cluster/sw   /sw

# 영구 마운트 (/etc/fstab에 추가)
sudo tee -a /etc/fstab << 'EOF'
nas:/volume1/cluster/home  /home  nfs  defaults,_netdev  0  0
nas:/volume1/cluster/data  /data  nfs  defaults,_netdev  0  0
nas:/volume1/cluster/sw    /sw    nfs  defaults,_netdev  0  0
EOF
```

### 3.3 마운트 확인

```bash
df -h | grep nas
# 아무 노드에서 파일 만들고 다른 노드에서 보이는지 확인
touch /data/test_from_$(hostname)
ls /data/
```

---

## 4. Munge 인증 설정

### 4.1 computer0(마스터)에서 munge 키 생성

```bash
sudo apt install -y munge libmunge-dev libmunge2

# 키 생성
sudo /usr/sbin/mungekey
# 또는 수동으로:
# sudo dd if=/dev/urandom bs=1 count=1024 > /etc/munge/munge.key

sudo chown munge:munge /etc/munge/munge.key
sudo chmod 400 /etc/munge/munge.key
```

### 4.2 모든 노드에 키 배포

```bash
# computer0에서 나머지 노드로 키 복사
for i in 1 2 3 4 5 6 7 8; do
    sudo scp /etc/munge/munge.key computer${i}:/etc/munge/munge.key
    ssh computer${i} "sudo chown munge:munge /etc/munge/munge.key && sudo chmod 400 /etc/munge/munge.key"
done
```

### 4.3 모든 노드에서 munge 시작

```bash
# 모든 서버 9대에서
sudo systemctl enable --now munge
```

### 4.4 munge 동작 확인

```bash
# computer0에서 인코딩 → 다른 노드에서 디코딩
munge -n | ssh computer1 unmunge
munge -n | ssh computer8 unmunge
# STATUS: Success (0) 가 나오면 정상
```

---

## 5. MariaDB + SlurmDBD 설치 (computer0에서만)

### 5.1 MariaDB 설치 및 설정

```bash
sudo apt install -y mariadb-server libmariadb-dev
sudo systemctl enable --now mariadb

# 보안 초기 설정
sudo mysql_secure_installation
```

### 5.2 SLURM용 데이터베이스 생성

```bash
sudo mysql -u root -p << 'EOF'
CREATE DATABASE slurm_acct_db;
CREATE USER 'slurm'@'localhost' IDENTIFIED BY 'SlurmDBPassword';
GRANT ALL PRIVILEGES ON slurm_acct_db.* TO 'slurm'@'localhost';
FLUSH PRIVILEGES;
EOF
```

### 5.3 slurmdbd.conf 작성

```bash
sudo mkdir -p /etc/slurm

sudo tee /etc/slurm/slurmdbd.conf << 'EOF'
# SlurmDBD Configuration
AuthType=auth/munge

DbdAddr=localhost
DbdHost=computer0
DbdPort=6819
SlurmUser=slurm

DebugLevel=info
LogFile=/var/log/slurm/slurmdbd.log
PidFile=/var/run/slurm/slurmdbd.pid

# Database
StorageType=accounting_storage/mysql
StorageHost=localhost
StoragePort=3306
StorageUser=slurm
StoragePass=SlurmDBPassword
StorageLoc=slurm_acct_db
EOF

sudo chown slurm:slurm /etc/slurm/slurmdbd.conf
sudo chmod 600 /etc/slurm/slurmdbd.conf
```

### 5.4 SlurmDBD 시작

```bash
sudo mkdir -p /var/log/slurm /var/run/slurm
sudo chown slurm:slurm /var/log/slurm /var/run/slurm

sudo systemctl enable --now slurmdbd

# 로그 확인
sudo tail -f /var/log/slurm/slurmdbd.log
```

---

## 6. SLURM 소스 빌드 및 설치

### 6.1 소스 다운로드 (computer0에서)

```bash
cd /tmp
git clone --depth 1 -b slurm-25-11-2-1 https://github.com/SchedMD/slurm.git
cd slurm
```

### 6.2 빌드 및 설치

```bash
cd /tmp/slurm
./configure --prefix=/usr --sysconfdir=/etc/slurm \
    --with-mysql_config=/usr/bin/mysql_config \
    --with-munge=/usr
make -j$(nproc)
sudo make install
```

### 6.3 systemd 서비스 파일 등록

```bash
# 빌드 소스에서 서비스 파일 복사
sudo cp /tmp/slurm/etc/slurmctld.service /etc/systemd/system/
sudo cp /tmp/slurm/etc/slurmd.service /etc/systemd/system/
sudo cp /tmp/slurm/etc/slurmdbd.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 6.4 모든 노드에 설치

**방법 A: NAS를 통해 각 노드에서 빌드 (간편)**

```bash
# computer0에서 소스를 NAS에 복사
cp -r /tmp/slurm /sw/slurm-src/

# computer1~8 각 노드에서 실행
cd /sw/slurm-src
./configure --prefix=/usr --sysconfdir=/etc/slurm --with-munge=/usr
make -j$(nproc)
sudo make install

# systemd 서비스 파일 등록
sudo cp /sw/slurm-src/etc/slurmd.service /etc/systemd/system/
sudo systemctl daemon-reload
```

**방법 B: deb 패키지 빌드 후 배포 (권장)**

```bash
# computer0에서 deb 패키지 빌드
cd /tmp/slurm
sudo apt install -y devscripts debhelper fakeroot
dpkg-buildpackage -b -uc -us

# 빌드된 .deb 파일을 NAS에 복사
mkdir -p /sw/slurm-debs
cp /tmp/slurm*.deb /sw/slurm-debs/

# computer0 (마스터 + 계산 노드)
sudo dpkg -i /sw/slurm-debs/slurm_25.11.2*.deb \
    /sw/slurm-debs/slurm-slurmctld_*.deb \
    /sw/slurm-debs/slurm-slurmdbd_*.deb \
    /sw/slurm-debs/slurm-slurmd_*.deb
sudo apt install -f -y

# computer1~8 (계산 노드)
for i in 1 2 3 4 5 6 7 8; do
    ssh computer${i} "sudo dpkg -i /sw/slurm-debs/slurm_25.11.2*.deb /sw/slurm-debs/slurm-slurmd_*.deb && sudo apt install -f -y"
done
```

### 6.5 필수 디렉토리 생성 (모든 노드)

```bash
# 모든 서버 9대에서 실행
sudo mkdir -p /etc/slurm /var/spool/slurm /var/log/slurm /var/run/slurm /var/lib/slurm
sudo chown -R slurm:slurm /var/spool/slurm /var/log/slurm /var/run/slurm /var/lib/slurm
```

---

## 7. slurm.conf 작성

### 7.1 slurm.conf (모든 노드에 동일하게 배포)

```bash
sudo tee /etc/slurm/slurm.conf << 'EOF'
#
# slurm.conf - SLURM 클러스터 설정
# 9대 GPU 서버 (3080/3090/4090/A6000) + NAS
# 2026-03 | SLURM 25.11.2 | Ubuntu
#

# ============================================================
# 클러스터 기본 정보
# ============================================================
ClusterName=gpucluster
SlurmctldHost=computer0
SlurmUser=slurm
AuthType=auth/munge

# ============================================================
# GPU 지원
# ============================================================
GresTypes=gpu

# ============================================================
# 프로세스 관리
# ============================================================
ProctrackType=proctrack/linuxproc
ReturnToService=1
TaskPlugin=task/affinity

# ============================================================
# 네트워크 포트
# ============================================================
SlurmctldPort=6817
SlurmdPort=6818

# ============================================================
# 파일 경로
# ============================================================
SlurmctldPidFile=/var/run/slurm/slurmctld.pid
SlurmdPidFile=/var/run/slurm/slurmd.pid
SlurmdSpoolDir=/var/spool/slurm
StateSaveLocation=/var/lib/slurm

# ============================================================
# 타이머
# ============================================================
InactiveLimit=0
KillWait=30
MinJobAge=300
SlurmctldTimeout=120
SlurmdTimeout=300
Waittime=0

# ============================================================
# 스케줄링
# ============================================================
SchedulerType=sched/backfill
SelectType=select/cons_tres
SelectTypeParameters=CR_Core_Memory

# ============================================================
# 로깅 & 어카운팅
# ============================================================
AccountingStorageHost=computer0
AccountingStorageType=accounting_storage/slurmdbd
JobCompLoc=/var/log/slurm/jobcomp.log
JobCompType=jobcomp/filetxt
JobAcctGatherFrequency=30
SlurmctldDebug=info
SlurmctldLogFile=/var/log/slurm/slurmctld.log
SlurmdDebug=info
SlurmdLogFile=/var/log/slurm/slurmd.log

# ============================================================
# 계산 노드 정의
# ============================================================
# CPUs, RealMemory는 각 서버에서 slurmd -C 로 확인 후 수정
# Gres=gpu:모델명:개수 형식

# 3080 노드 (VRAM 10GB)
NodeName=computer0 NodeAddr=192.168.1.10 CPUs=32 RealMemory=64000 Gres=gpu:3080:4 State=UNKNOWN

# 3090 노드 (VRAM 24GB)
NodeName=computer1 NodeAddr=192.168.1.11 CPUs=64 RealMemory=128000 Gres=gpu:3090:4 State=UNKNOWN
NodeName=computer2 NodeAddr=192.168.1.12 CPUs=64 RealMemory=128000 Gres=gpu:3090:4 State=UNKNOWN
NodeName=computer3 NodeAddr=192.168.1.13 CPUs=64 RealMemory=128000 Gres=gpu:3090:4 State=UNKNOWN
NodeName=computer4 NodeAddr=192.168.1.14 CPUs=64 RealMemory=128000 Gres=gpu:3090:4 State=UNKNOWN

# 4090 노드 (VRAM 24GB)
NodeName=computer5 NodeAddr=192.168.1.15 CPUs=64 RealMemory=128000 Gres=gpu:4090:4 State=UNKNOWN
NodeName=computer6 NodeAddr=192.168.1.16 CPUs=64 RealMemory=128000 Gres=gpu:4090:4 State=UNKNOWN
NodeName=computer7 NodeAddr=192.168.1.17 CPUs=64 RealMemory=128000 Gres=gpu:4090:4 State=UNKNOWN

# A6000 노드 (VRAM 48GB)
NodeName=computer8 NodeAddr=192.168.1.18 CPUs=64 RealMemory=128000 Gres=gpu:a6000:4 State=UNKNOWN

# ============================================================
# 파티션 (큐) 정의
# ============================================================
# 전체 노드 (기본 파티션)
PartitionName=all   Nodes=computer[0-8] Default=YES MaxTime=INFINITE State=UP

# GPU 모델별 파티션
PartitionName=3090  Nodes=computer[1-4]  Default=NO MaxTime=INFINITE State=UP
PartitionName=4090  Nodes=computer[5-7]  Default=NO MaxTime=INFINITE State=UP
PartitionName=a6000 Nodes=computer8      Default=NO MaxTime=INFINITE State=UP
EOF
```

### 7.2 gres.conf (GPU 리소스 설정 - 모든 노드에 동일하게)

```bash
sudo tee /etc/slurm/gres.conf << 'EOF'
# GPU Generic Resource Configuration
# AutoDetect=nvml 로 NVIDIA GPU 자동 감지
AutoDetect=nvml
EOF
```

> `AutoDetect=nvml`을 사용하면 각 노드에서 GPU를 자동으로 감지합니다.
> 자동 감지가 안 되면 아래처럼 수동 설정:

```bash
# 수동 설정 예시 (AutoDetect가 안 되는 경우)
sudo tee /etc/slurm/gres.conf << 'EOF'
# computer0: 3080 x4
Name=gpu Type=3080 File=/dev/nvidia[0-3]

# computer1~4: 3090 x4
Name=gpu Type=3090 File=/dev/nvidia[0-3]

# computer5~7: 4090 x4
Name=gpu Type=4090 File=/dev/nvidia[0-3]

# computer8: A6000 x4
Name=gpu Type=a6000 File=/dev/nvidia[0-3]
EOF
```

### 7.3 cgroup.conf (모든 노드에 동일하게)

```bash
sudo tee /etc/slurm/cgroup.conf << 'EOF'
ConstrainCores=yes
ConstrainRAMSpace=yes
ConstrainSwapSpace=no
ConstrainDevices=yes
EOF
```

### 7.4 설정 파일 배포

```bash
# computer0에서 모든 노드로 설정 파일 복사
for i in 1 2 3 4 5 6 7 8; do
    sudo scp /etc/slurm/slurm.conf computer${i}:/etc/slurm/slurm.conf
    sudo scp /etc/slurm/gres.conf computer${i}:/etc/slurm/gres.conf
    sudo scp /etc/slurm/cgroup.conf computer${i}:/etc/slurm/cgroup.conf
done
```

---

## 8. 클러스터 시작

### 8.1 시작 순서 (반드시 순서대로 - 모두 computer0에서)

```bash
# 1단계: MariaDB (이미 실행 중이어야 함)
sudo systemctl status mariadb

# 2단계: SlurmDBD
sudo systemctl enable --now slurmdbd
sudo tail -f /var/log/slurm/slurmdbd.log
# "slurmdbd version 25.11.2 started" 확인 후 Ctrl+C

# 3단계: Slurmctld
sudo systemctl enable --now slurmctld
sudo tail -f /var/log/slurm/slurmctld.log
# "slurmctld version 25.11.2 started" 확인 후 Ctrl+C

# 4단계: computer0의 slurmd (마스터도 계산 노드이므로)
sudo systemctl enable --now slurmd
```

### 8.2 워커 일괄 시작 (computer0에서 SSH로)

```bash
for i in 1 2 3 4 5 6 7 8; do
    echo "Starting slurmd on computer${i}..."
    ssh computer${i} "sudo systemctl enable --now slurmd"
done
```

### 8.3 상태 확인

```bash
# 노드 상태 확인
sinfo
# 기대 출력:
# PARTITION AVAIL  TIMELIMIT  NODES  STATE NODELIST
# all*         up   infinite      9   idle computer[0-8]
# 3090         up   infinite      4   idle computer[1-4]
# 4090         up   infinite      3   idle computer[5-7]
# a6000        up   infinite      1   idle computer8

# 상세 노드 정보 (GPU 포함)
scontrol show nodes

# GPU 리소스 확인
sinfo -o "%N %G"
# 출력 예시:
# computer0 gpu:3080:4
# computer1 gpu:3090:4
# ...
```

---

## 9. 초기 설정 및 검증

### 9.1 클러스터/계정 등록

```bash
# 클러스터 등록
sacctmgr add cluster gpucluster

# 계정 생성
sacctmgr add account research Description="Research Team"

# 사용자 추가
sacctmgr add user daniel Account=research
```

### 9.2 기본 잡 테스트

```bash
# 단일 노드 테스트
sbatch --wrap="hostname && nvidia-smi"
squeue   # 잡 상태 확인
sacct    # 완료 후 기록 확인

# 결과 파일 확인
cat slurm-*.out
```

### 9.3 GPU 잡 테스트

```bash
# GPU 1개 요청
sbatch --gres=gpu:1 --wrap="nvidia-smi"

# 특정 GPU 모델 요청
sbatch --gres=gpu:3090:2 --partition=3090 --wrap="nvidia-smi"
sbatch --gres=gpu:4090:4 --partition=4090 --wrap="nvidia-smi"
sbatch --gres=gpu:a6000:4 --partition=a6000 --wrap="nvidia-smi"

# A6000 VRAM 48GB 필요한 대형 모델 학습
sbatch --gres=gpu:a6000:4 --partition=a6000 --wrap="python train_large_model.py"
```

### 9.4 멀티노드 GPU 잡 테스트

```bash
# 3090 노드 3대, 각 4GPU = 총 12 GPU
sbatch -N 3 --gres=gpu:4 --partition=3090 --wrap="hostname && nvidia-smi"

# 전체 클러스터에서 아무 GPU 2개
srun --gres=gpu:2 nvidia-smi
```

### 9.5 잡 스크립트 예시 (딥러닝 학습)

```bash
cat << 'EOF' > /data/train_job.sh
#!/bin/bash
#SBATCH --job-name=train
#SBATCH --output=/data/logs/train_%j.log
#SBATCH --error=/data/logs/train_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --gres=gpu:4
#SBATCH --partition=4090
#SBATCH --time=24:00:00

echo "Job ID: $SLURM_JOB_ID"
echo "Node: $(hostname)"
echo "GPUs: $CUDA_VISIBLE_DEVICES"
nvidia-smi

# 학습 실행
cd /data/my_project
python train.py --gpus 4 --batch_size 128
EOF

mkdir -p /data/logs
sbatch /data/train_job.sh
```

### 9.6 멀티노드 분산 학습 잡 스크립트 (PyTorch DDP)

```bash
cat << 'EOF' > /data/distributed_train.sh
#!/bin/bash
#SBATCH --job-name=ddp_train
#SBATCH --output=/data/logs/ddp_%j.log
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=8
#SBATCH --mem=120G
#SBATCH --gres=gpu:4
#SBATCH --partition=3090

export MASTER_ADDR=$(scontrol show hostnames $SLURM_JOB_NODELIST | head -n1)
export MASTER_PORT=29500
export WORLD_SIZE=$SLURM_NTASKS

srun torchrun \
    --nproc_per_node=4 \
    --nnodes=$SLURM_NNODES \
    --node_rank=$SLURM_NODEID \
    --master_addr=$MASTER_ADDR \
    --master_port=$MASTER_PORT \
    /data/my_project/train_ddp.py
EOF

sbatch /data/distributed_train.sh
```

---

## 10. 주요 명령어 정리

### 잡 관리

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `sbatch` | 잡 스크립트 제출 | `sbatch job.sh` |
| `srun` | 잡 즉시 실행 (인터랙티브) | `srun --gres=gpu:1 nvidia-smi` |
| `salloc` | 리소스 할당 (인터랙티브 세션) | `salloc --gres=gpu:2 --partition=4090` |
| `squeue` | 잡 큐 확인 | `squeue -u daniel` |
| `scancel` | 잡 취소 | `scancel 12345` |
| `sacct` | 잡 히스토리 조회 | `sacct --format=JobID,JobName,State,Elapsed,AllocGRES` |

### 클러스터 상태

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `sinfo` | 파티션/노드 상태 | `sinfo -N -l` |
| `sinfo -o "%N %G"` | 노드별 GPU 확인 | - |
| `scontrol show nodes` | 노드 상세 정보 | `scontrol show node computer5` |
| `scontrol show job` | 잡 상세 정보 | `scontrol show job 12345` |

### 관리 명령어

| 명령어 | 설명 | 예시 |
|--------|------|------|
| `scontrol update` | 노드 상태 변경 | `scontrol update NodeName=computer1 State=DRAIN Reason="maintenance"` |
| `scontrol reconfigure` | 설정 리로드 | `scontrol reconfigure` |
| `sacctmgr` | 계정/사용자 관리 | `sacctmgr show user` |

---

## 11. 트러블슈팅

### 노드가 down 상태일 때

```bash
# 원인 확인
scontrol show node computer1 | grep -i reason

# 노드 복구
scontrol update NodeName=computer1 State=RESUME
```

### munge 인증 실패

```bash
# munge 키가 동일한지 확인
md5sum /etc/munge/munge.key                     # computer0
ssh computer1 md5sum /etc/munge/munge.key       # computer1

# 시간 동기화 확인
date && ssh computer1 date

# munge 재시작
sudo systemctl restart munge
```

### GPU가 SLURM에서 안 보일 때

```bash
# nvidia-smi가 되는지 확인
ssh computer1 nvidia-smi

# gres.conf 확인
cat /etc/slurm/gres.conf

# /dev/nvidia* 디바이스 파일 확인
ls -la /dev/nvidia*

# slurmd 재시작
sudo systemctl restart slurmd

# slurmctld에서 노드 GRES 확인
scontrol show node computer1 | grep Gres
```

### slurmd 시작 실패

```bash
# 로그 확인
sudo journalctl -u slurmd -n 50
sudo tail -50 /var/log/slurm/slurmd.log

# 일반적인 원인:
# - slurm.conf의 CPUs/RealMemory가 실제 서버 스펙과 다름
#   → slurmd -C 로 실제 스펙 확인 후 slurm.conf 수정
# - munge가 먼저 시작되지 않음
# - /var/spool/slurm 디렉토리 권한 문제
```

### slurmctld 시작 실패

```bash
sudo journalctl -u slurmctld -n 50
sudo tail -50 /var/log/slurm/slurmctld.log

# 일반적인 원인:
# - slurmdbd가 먼저 시작되지 않음
# - /var/lib/slurm 디렉토리 권한 문제
# - slurm.conf 문법 오류
```

### 노드 실제 스펙 확인 (slurm.conf 작성 시 참고)

```bash
# 각 워커 노드에서 실행
slurmd -C
# 출력 예시:
# NodeName=computer1 CPUs=64 Boards=1 SocketsPerBoard=2 CoresPerSocket=16 ThreadsPerCore=2 RealMemory=128000
# → 이 값을 slurm.conf의 NodeName 줄에 사용
```

---

## 12. 웹 대시보드 (AILAB Dashboard)

웹 브라우저에서 클러스터 상태 확인, 잡 제출/취소가 가능한 대시보드.
slurmrestd REST API를 활용하며, Python 프록시 서버가 JWT 인증을 처리합니다.

### 12.1 사전 조건

- slurmrestd가 동작 중이어야 함 (JWT 인증 활성화)
- `slurm.conf`에 아래 설정 추가:

```conf
AuthAltTypes=auth/jwt
AuthAltParameters=jwt_key=/etc/slurm/jwt_hs256.key
```

- JWT 키 생성 (아직 없다면):

```bash
# computer0에서
openssl rand -hex 32 > /etc/slurm/jwt_hs256.key
chown slurm:slurm /etc/slurm/jwt_hs256.key
chmod 600 /etc/slurm/jwt_hs256.key
# slurmctld, slurmdbd 재시작
sudo systemctl restart slurmdbd slurmctld
```

- slurmrestd 시작:

```bash
sudo -u slurm slurmrestd 0.0.0.0:6820 &
# 또는 systemd 서비스로 등록
```

### 12.2 대시보드 파일 구조

```
slurm-dashboard/
├── index.html      # 프론트엔드 (Tailwind CSS, AILAB 브랜딩)
├── server.py       # Python 프록시 서버 (JWT 인증 + TensorBoard 프록시)
├── logo-dark.png   # AILAB 로고 (다크용)
└── logo-white.png  # AILAB 로고 (화이트용)
```

### 12.3 대시보드 설치 및 실행

```bash
# 1. 대시보드 디렉토리를 computer0 (마스터)에 배치
cp -r slurm-dashboard /sw/slurm-dashboard

# 2. 프록시 서버 실행
cd /sw/slurm-dashboard
python3 server.py &

# 3. 브라우저에서 접속
# http://computer0:3080
```

### 12.4 systemd 서비스로 등록 (자동 시작)

```bash
sudo tee /etc/systemd/system/slurm-dashboard.service << 'EOF'
[Unit]
Description=SLURM Web Dashboard
After=slurmctld.service slurmrestd.service
Wants=slurmrestd.service

[Service]
Type=simple
User=slurm
WorkingDirectory=/sw/slurm-dashboard
ExecStart=/usr/bin/python3 /sw/slurm-dashboard/server.py
Restart=always
RestartSec=5
Environment=SLURMRESTD_URL=http://localhost:6820
Environment=SLURM_API_VERSION=v0.0.44
Environment=TENSORBOARD_URL=http://localhost:6006

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now slurm-dashboard

# 상태 확인
sudo systemctl status slurm-dashboard
```

### 12.5 server.py 환경변수

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `SLURMRESTD_URL` | `http://localhost:6820` | slurmrestd 주소 |
| `SLURM_API_VERSION` | `v0.0.44` | REST API 버전 (25.11.x = v0.0.44, 25.05.x = v0.0.42) |
| `TENSORBOARD_URL` | `http://localhost:6006` | TensorBoard 서버 주소 |

### 12.6 대시보드 기능

| 페이지 | 기능 |
|--------|------|
| **Overview** | 노드 요약 (Idle/Busy/Down), CPU 사용률, Running/Pending 잡 수, 최근 잡 목록 |
| **Submit Job** | 웹에서 잡 제출 (사용자, 이름, 파티션, 노드수, CPU, 메모리, GPU, 시간, 명령어) |
| **Jobs** | 전체 잡 큐 확인 + 사용자별 필터 + Cancel 버튼 |
| **Nodes** | 노드별 상세 정보 (CPU/Memory 사용 바, GPU, OS 정보) |
| **Experiments** | Runs 뷰 (TensorBoard 이벤트 파일 스캔) + TensorBoard 뷰 (임베드 iframe) |

> 10초마다 자동 새로고침. Experiments 탭은 TensorBoard 이벤트 파일을 /data에서 스캔하여 표시하며, TensorBoard 뷰에서 전체 TensorBoard UI를 임베드.

### 12.7 외부 접속 허용 (방화벽)

```bash
# computer0에서
sudo ufw allow 3080/tcp
# 이제 같은 네트워크의 다른 PC에서도 http://192.168.1.10:3080 으로 접속 가능
```

### 12.8 TensorBoard 연동 (학습 시각화)

TensorBoard 서버를 별도 컨테이너로 실행하여, 학습 중 실시간 메트릭을 대시보드에서 확인할 수 있습니다.

#### TensorBoard 서버 구성

```
┌──────────────┐     ┌───────────────┐     ┌──────────────────┐
│  학습 잡      │     │  TensorBoard  │     │  AILAB Dashboard │
│ (GPU 노드)    │     │  Container    │     │  (port 3080)     │
│              │     │  (port 6006)  │     │                  │
│ → events.out │ ──→ │ --logdir /data│ ──→ │ Experiments 탭    │
│   tfevents.* │     │              │     │ (iframe 임베드)    │
└──────────────┘     └───────────────┘     └──────────────────┘
        │                    │
        └──── /data 공유 볼륨 ────┘
```

#### 설치 및 실행

**Docker Compose 환경 (개발/테스트):**

```bash
# docker-compose.yml에 tensorboard 서비스가 이미 포함됨
docker compose up tensorboard -d

# 상태 확인
docker compose ps tensorboard
curl http://localhost:6006
```

`docker-compose.yml` 서비스 설정:

```yaml
tensorboard:
  image: tensorflow/tensorflow:latest
  container_name: tensorboard
  command: >
    bash -c "pip install tensorboard -q &&
    tensorboard --logdir /data --bind_all --port 6006 --reload_interval 30"
  volumes:
    - slurm_jobdir:/data:ro
  ports:
    - "${TENSORBOARD_PORT:-6006}:6006"
  restart: unless-stopped
```

**베어메탈 환경 (프로덕션):**

```bash
# 방법 A: pip으로 직접 설치 (computer0에서)
pip3 install tensorboard
tensorboard --logdir /data --bind_all --port 6006 --reload_interval 30 &

# 방법 B: systemd 서비스로 등록
sudo tee /etc/systemd/system/tensorboard.service << 'EOF'
[Unit]
Description=TensorBoard Server
After=network.target

[Service]
Type=simple
User=slurm
ExecStart=/usr/local/bin/tensorboard --logdir /data --bind_all --port 6006 --reload_interval 30
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now tensorboard
```

#### 학습 스크립트에서 TensorBoard 로깅

```python
from torch.utils.tensorboard import SummaryWriter

writer = SummaryWriter(log_dir="/data/my_project/output/tb")

for epoch in range(num_epochs):
    train_loss = train_one_epoch()
    val_loss = validate()
    writer.add_scalar("train/loss", train_loss, epoch)
    writer.add_scalar("val/loss", val_loss, epoch)
    writer.add_scalar("val/accuracy", val_acc, epoch)

writer.close()
```

#### 대시보드에서 확인

1. 대시보드 접속 (http://computer0:3080)
2. **Experiments** 탭 클릭
3. **Runs** 뷰: /data 내 TensorBoard 이벤트 파일을 스캔하여 프로젝트/런 목록 표시, 메트릭 요약 및 차트
4. **TensorBoard** 뷰: TensorBoard 전체 UI가 iframe으로 임베드 (실시간 업데이트)

#### 방화벽 (베어메탈)

```bash
# TensorBoard 포트 개방 (직접 접속 시)
sudo ufw allow 6006/tcp

# 대시보드 프록시를 통해서만 접근한다면 6006은 localhost만 허용하고 3080만 개방
```

---

## 13. Apptainer 컨테이너 기반 ML 학습

Slurm에서 Docker 이미지를 Apptainer(Singularity)로 변환하여 학습 잡을 실행하는 방법.
각 프로젝트마다 독립된 환경(Ubuntu, CUDA, Python 버전 등)을 유지할 수 있습니다.

### 13.1 Apptainer 설치 (모든 노드)

```bash
sudo apt install -y apptainer
# 또는 공식 릴리스에서 설치:
# https://apptainer.org/docs/admin/main/installation.html
```

### 13.2 Docker 이미지 → SIF 변환

```bash
# 방법 A: Docker Hub에서 직접 빌드
apptainer build /sw/containers/pytorch.sif docker://pytorch/pytorch:2.0.0-cuda11.8-cudnn8-devel

# 방법 B: 로컬 Docker 이미지에서 변환
docker build -t my-project:latest .
docker save my-project:latest -o /tmp/my-project.tar
apptainer build /sw/containers/my-project.sif docker-archive:///tmp/my-project.tar
rm /tmp/my-project.tar
```

> SIF 파일은 NAS 공유 디렉토리(`/sw/containers/`)에 배치하면 모든 노드에서 접근 가능.

### 13.3 Apptainer 기반 sbatch 스크립트

```bash
#!/bin/bash
#SBATCH --job-name=container-train
#SBATCH --output=/data/logs/train_%j.out
#SBATCH --nodes=1
#SBATCH --gres=gpu:4
#SBATCH --partition=4090
#SBATCH --time=24:00:00

CONTAINER=/sw/containers/my-project.sif

apptainer exec --nv \
    --bind /data:/data \
    --bind /sw:/sw \
    ${CONTAINER} \
    python3 /data/my_project/train.py --gpus 4
```

**주요 옵션:**
- `--nv`: NVIDIA GPU 드라이버를 컨테이너에 자동 바인드
- `--bind A:B`: 호스트 경로 A를 컨테이너 내 B로 마운트
- 컨테이너 내부에서 호스트의 `/home`은 기본으로 마운트됨

### 13.4 예시: Diffusion-Planner 학습

Diffusion-Planner (ICLR 2025) - Ubuntu 22.04 + CUDA 11.8 + PyTorch 2.0 환경.

#### Docker 이미지 빌드

```bash
cd /data/projects/Diffusion-Planner

# nuplan-devkit를 추가 빌드 컨텍스트로 지정
docker buildx build \
    --build-context nuplan-devkit=/data/projects/nuplan-devkit \
    -t diffusion-planner:latest .

# SIF 변환 후 NAS에 배치
docker save diffusion-planner:latest -o /tmp/dp.tar
apptainer build /sw/containers/diffusion_planner.sif docker-archive:///tmp/dp.tar
rm /tmp/dp.tar
```

#### 데이터 전처리 (1회)

```bash
sbatch << 'EOF'
#!/bin/bash
#SBATCH --job-name=dp-preprocess
#SBATCH --output=/data/logs/preprocess_%j.out
#SBATCH --cpus-per-task=8
#SBATCH --time=04:00:00

apptainer exec \
    --bind /data:/data \
    /sw/containers/diffusion_planner.sif \
    python3 /opt/Diffusion-Planner/data_process.py \
        --data_path /data/nuplan-v1.1/splits/mini \
        --map_path /data/nuplan-v1.1/maps \
        --save_path /data/diffusion_planner/preprocessed \
        --total_scenarios 100
EOF
```

#### 학습 제출

```bash
sbatch << 'EOF'
#!/bin/bash
#SBATCH --job-name=dp-train
#SBATCH --output=/data/logs/dp_train_%j.out
#SBATCH --nodes=1
#SBATCH --gres=gpu:4
#SBATCH --partition=4090
#SBATCH --cpus-per-task=16
#SBATCH --time=48:00:00

CONTAINER=/sw/containers/diffusion_planner.sif
NGPUS=4

apptainer exec --nv \
    --bind /data:/data \
    ${CONTAINER} \
    python3 -m torch.distributed.run \
        --nnodes 1 \
        --nproc-per-node ${NGPUS} \
        --standalone \
        /opt/Diffusion-Planner/train_predictor.py \
        --train_set /data/diffusion_planner/preprocessed \
        --train_set_list /data/diffusion_planner/training_files.json \
        --batch_size 512 \
        --train_epochs 100 \
        --save_dir /data/diffusion_planner/output \
        --use_wandb True
EOF
```

#### 멀티노드 학습 (3090 x2 = 8 GPU)

```bash
sbatch << 'EOF'
#!/bin/bash
#SBATCH --job-name=dp-ddp
#SBATCH --output=/data/logs/dp_ddp_%j.out
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=4
#SBATCH --gres=gpu:4
#SBATCH --partition=3090
#SBATCH --time=72:00:00

CONTAINER=/sw/containers/diffusion_planner.sif
export MASTER_ADDR=$(scontrol show hostnames $SLURM_JOB_NODELIST | head -n1)
export MASTER_PORT=29500

srun apptainer exec --nv \
    --bind /data:/data \
    ${CONTAINER} \
    python3 -m torch.distributed.run \
        --nnodes ${SLURM_NNODES} \
        --nproc-per-node 4 \
        --rdzv_backend c10d \
        --rdzv_endpoint ${MASTER_ADDR}:${MASTER_PORT} \
        /opt/Diffusion-Planner/train_predictor.py \
        --train_set /data/diffusion_planner/preprocessed \
        --train_set_list /data/diffusion_planner/training_files.json \
        --batch_size 2048 \
        --train_epochs 500 \
        --save_dir /data/diffusion_planner/output \
        --use_wandb True
EOF
```

### 13.5 학습 모니터링 연동

#### TensorBoard (기본)

학습 스크립트에서 TensorBoard 이벤트 파일을 `/data` 하위에 저장하면, TensorBoard 서버가 자동으로 감지합니다.

```python
# 학습 스크립트 내
from torch.utils.tensorboard import SummaryWriter
writer = SummaryWriter(log_dir="/data/my_project/output/tb")
```

대시보드 Experiments 탭에서 Runs 목록과 TensorBoard UI를 확인할 수 있습니다.

#### W&B (선택)

W&B를 병행 사용하려면 환경변수 설정:

```bash
# .bashrc 또는 sbatch 스크립트 내에서
export WANDB_API_KEY=your_api_key
export WANDB_ENTITY=your_team
```

---

## 14. 전체 구축 순서 요약 (체크리스트)

```
[ ] 1.  모든 서버: OS 업데이트, 빌드 의존성 설치 (apt)
[ ] 2.  모든 서버: 호스트명 설정 (computer0~8)
[ ] 3.  모든 서버: /etc/hosts 편집
[ ] 4.  모든 서버: NTP 동기화
[ ] 5.  모든 서버: slurm 사용자 생성 (동일 UID=1100, GID=1100)
[ ] 6.  모든 서버: 방화벽 포트 개방 (ufw)
[ ] 7.  모든 서버: NVIDIA 드라이버 확인 (nvidia-smi)
[ ] 8.  NAS: NFS export 설정
[ ] 9.  모든 서버: NFS 마운트 (/home, /data, /sw)
[ ] 10. computer0: munge 키 생성
[ ] 11. 모든 서버: munge 키 배포 및 시작
[ ] 12. munge 인증 테스트
[ ] 13. computer0: MariaDB 설치 및 DB 생성
[ ] 14. computer0: slurmdbd.conf 작성 및 시작
[ ] 15. SLURM 소스 빌드
[ ] 16. 모든 서버: SLURM 설치 + systemd 서비스 등록
[ ] 17. slurm.conf, gres.conf, cgroup.conf 작성 및 배포
[ ] 18. computer0: slurmctld 시작
[ ] 19. 모든 서버: slurmd 시작
[ ] 20. sinfo로 클러스터 상태 확인 (9노드 idle, GPU 표시)
[ ] 21. sacctmgr로 클러스터/계정 등록
[ ] 22. GPU 잡 테스트 (sbatch --gres=gpu:1)
[ ] 23. 멀티노드 잡 테스트 (sbatch -N 3 --gres=gpu:4)
[ ] 24. JWT 키 생성 및 slurmrestd 시작
[ ] 25. 웹 대시보드 설치 및 systemd 등록 (TENSORBOARD_URL 설정)
[ ] 26. TensorBoard 서버 설치 및 시작 (pip install tensorboard 또는 Docker)
[ ] 27. 브라우저에서 http://computer0:3080 접속 확인
[ ] 28. 모든 노드: Apptainer 설치 (apt install apptainer)
[ ] 29. NAS에 컨테이너 디렉토리 생성 (/sw/containers/)
[ ] 30. ML 프로젝트 Docker 이미지 빌드 → SIF 변환 → /sw/containers/ 배치
[ ] 31. 컨테이너 기반 GPU 잡 테스트 (apptainer exec --nv)
```

---

## 참고 링크

- [SLURM 공식 문서](https://slurm.schedmd.com/)
- [SLURM Quick Start (Admin)](https://slurm.schedmd.com/quickstart_admin.html)
- [slurm.conf 매뉴얼](https://slurm.schedmd.com/slurm.conf.html)
- [SLURM GRES (GPU) 설정](https://slurm.schedmd.com/gres.html)
- [slurmdbd.conf 매뉴얼](https://slurm.schedmd.com/slurmdbd.conf.html)
- [SchedMD GitHub](https://github.com/SchedMD/slurm)
