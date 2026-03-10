# SLURM Bare-Metal GPU Cluster

베어메탈 SLURM GPU 클러스터. Ubuntu 22.04/24.04 + SLURM 25.11.2.
`cluster.conf` 하나로 노드 추가/삭제 관리.

## 현재 구성 (2PC 테스트)

| 호스트명 | IP | GPU | 역할 |
|---------|-----|-----|------|
| daniel | 192.168.0.47 | RTX 5060 Ti (16GB) | 마스터 + 워커 |
| 5090 | 192.168.0.153 | RTX 5090 (32GB) | 워커 |

## 향후 확장 구성 (9대 + NAS)

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
 │ 3080 x4   │    ├───────────────────────┤    │ 계산 노드    │
 │            │    │  computer5~7 (4090x4) │    └─────────────┘
 └───────────┘    │  계산 노드             │
 192.168.1.10     └───────────────────────┘
                   192.168.1.11~17          192.168.1.18
```

## 프로젝트 구조

```
├── cluster.conf            # 노드 정의 (이 파일만 수정하면 확장 가능)
├── config/                 # SLURM 설정 (자동 생성됨)
│   ├── slurm.conf
│   ├── slurmdbd.conf
│   ├── gres.conf
│   └── cgroup.conf
├── scripts/
│   ├── generate-slurm-conf.sh  # cluster.conf → slurm.conf 생성
│   ├── setup-common.sh         # 공통 설치 (모든 노드)
│   ├── setup-master.sh         # 마스터 설치
│   └── setup-worker.sh         # 워커 설치
├── examples/jobs/          # 잡 제출 예제
├── slurm-dashboard/        # 웹 대시보드
└── docs/                   # 상세 가이드 문서
```

## Quick Start

### 1. 마스터 노드

```bash
git clone https://github.com/sangbeom0321/slurm-docker-cluster.git
cd slurm-docker-cluster

# cluster.conf 확인/수정 (노드 IP, GPU 스펙)
vi cluster.conf

# 설치
sudo bash scripts/setup-common.sh
sudo bash scripts/setup-master.sh
```

### 2. Munge 키 복사 (각 워커로)

```bash
sudo scp /etc/munge/munge.key <user>@<워커IP>:/tmp/
```

### 3. 워커 노드 (각 워커에서)

```bash
git clone https://github.com/sangbeom0321/slurm-docker-cluster.git
cd slurm-docker-cluster
sudo bash scripts/setup-common.sh
sudo bash scripts/setup-worker.sh
```

### 4. 확인

```bash
sinfo                                               # 노드 상태
sbatch --gres=gpu:1 --wrap="hostname && nvidia-smi"  # GPU 테스트
```

## 노드 추가/삭제

```bash
# 1. cluster.conf에 노드 추가
echo "newnode  192.168.0.200  32  64000  4090  2  worker" >> cluster.conf

# 2. slurm.conf 재생성
bash scripts/generate-slurm-conf.sh

# 3. 모든 노드에 slurm.conf 배포 후 리로드
scontrol reconfigure
```

## 주요 명령어

| 명령어 | 설명 |
|--------|------|
| `sinfo` | 클러스터/노드 상태 |
| `sbatch job.sh` | 잡 제출 |
| `squeue` | 잡 큐 확인 |
| `scancel <ID>` | 잡 취소 |
| `sacct` | 잡 히스토리 |
| `scontrol reconfigure` | 설정 리로드 |

## 문서

- [클러스터 구축 가이드](docs/slurm-cluster-setup-guide.md) - 상세 설치 (9대 서버 기준)
- [Apptainer 가이드](docs/slurm-cluster-setup-guide-apptainer.md) - 컨테이너 기반 ML 학습
- [사용자 가이드](docs/slurm-user-guide.md) - 잡 제출/관리

## License

[MIT License](LICENSE)
