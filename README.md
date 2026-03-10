# SLURM 베어메탈 클러스터 설치 매뉴얼

## 사전 요구사항

- Ubuntu 22.04 / 24.04
- NVIDIA 드라이버 설치 완료 (`nvidia-smi` 동작 확인)
- PC 간 SSH 접속 가능

## 현재 구성

| 호스트명 | IP | GPU | 역할 |
|---------|-----|-----|------|
| daniel | 192.168.0.47 | RTX 5060 Ti (16GB) | 마스터 + 워커 |
| 5090 | 192.168.0.153 | RTX 5090 (32GB) | 워커 |

---

## Step 1. PC1 (마스터) 설치

```bash
git clone https://github.com/sangbeom0321/slurm-docker-cluster.git
cd slurm-docker-cluster

# cluster.conf 확인 (IP, GPU 스펙이 맞는지)
cat cluster.conf

# 공통 설치 (의존성, hosts, slurm 유저)
sudo bash scripts/setup-common.sh

# 마스터 설치 (MariaDB, Munge, SLURM 빌드, 데몬 시작)
sudo bash scripts/setup-master.sh
```

## Step 2. Munge 키를 PC2로 복사

```bash
sudo scp /etc/munge/munge.key ailab@192.168.0.153:/tmp/
```

## Step 3. PC2 (워커) 설치

```bash
git clone https://github.com/sangbeom0321/slurm-docker-cluster.git
cd slurm-docker-cluster

# 공통 설치
sudo bash scripts/setup-common.sh

# 워커 설치 (Munge 키 수신, SLURM 빌드, slurmd 시작)
sudo bash scripts/setup-worker.sh
```

## Step 4. 클러스터 확인 (PC1에서)

```bash
sinfo                                               # 두 노드 idle 확인
sbatch --gres=gpu:1 --wrap="hostname && nvidia-smi"  # GPU 잡 테스트
squeue                                               # 잡 큐
cat slurm-*.out                                      # 결과 확인
```

---

## 노드 추가

```bash
# 1. cluster.conf에 한 줄 추가
echo "newnode  192.168.0.200  32  64000  4090  2  worker" >> cluster.conf

# 2. slurm.conf 재생성
bash scripts/generate-slurm-conf.sh

# 3. 모든 노드에 slurm.conf 배포
sudo cp config/slurm.conf /etc/slurm/slurm.conf
scp config/slurm.conf user@newnode:/etc/slurm/slurm.conf

# 4. 새 노드에서 설치
sudo bash scripts/setup-common.sh
sudo bash scripts/setup-worker.sh

# 5. 마스터에서 리로드
sudo scontrol reconfigure
sinfo
```

---

## 트러블슈팅

### 노드가 inval (INVALID_REG) 상태일 때

GPU가 SLURM에서 감지 안 되는 경우. `gres.conf`를 수동 설정으로 변경:

```bash
# /etc/slurm/gres.conf 확인
cat /etc/slurm/gres.conf

# 수동 설정 예시 (AutoDetect=nvml이 안 되는 경우)
# Name=gpu Type=5060ti File=/dev/nvidia0
# Name=gpu Type=5090 File=/dev/nvidia0

# 설정 변경 후
sudo systemctl restart slurmd
sudo scontrol update NodeName=<노드명> State=RESUME
sinfo
```

### 노드가 down 상태일 때

```bash
scontrol show node <노드명> | grep Reason    # 원인 확인
sudo scontrol update NodeName=<노드명> State=RESUME
```

### munge 인증 실패

```bash
# 키가 동일한지 확인
sudo md5sum /etc/munge/munge.key
ssh user@worker sudo md5sum /etc/munge/munge.key

# 시간 동기화 확인
date && ssh user@worker date
```

### SLURM 빌드 시 mysql_config not found

Ubuntu 24.04에서 `mysql_config`가 `mariadb_config`로 이름이 변경됨.
`setup-master.sh`에서 자동으로 심볼릭 링크를 생성하지만, 수동으로 해야 하는 경우:

```bash
sudo ln -sf /usr/bin/mariadb_config /usr/bin/mysql_config
```

---

## 주요 명령어

| 명령어 | 설명 |
|--------|------|
| `sinfo` | 클러스터/노드 상태 |
| `sinfo -N -o "%N %G %C"` | 노드별 GPU/CPU 확인 |
| `sbatch job.sh` | 잡 제출 |
| `squeue` | 잡 큐 확인 |
| `scancel <ID>` | 잡 취소 |
| `sacct` | 잡 히스토리 |
| `scontrol show node` | 노드 상세 정보 |
| `scontrol reconfigure` | 설정 리로드 |
| `scontrol update NodeName=X State=RESUME` | 노드 복구 |
