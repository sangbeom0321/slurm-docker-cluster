# Slurm + Apptainer 컨테이너 학습 가이드

> Slurm 클러스터에서 ML 프로젝트를 컨테이너로 격리 실행하는 방법

---

## 핵심 개념

### 왜 컨테이너인가?

연구실에서 흔한 문제:

```
"내 컴퓨터에서는 되는데 서버에서 안 돼요"
"A 프로젝트는 PyTorch 1.13인데 B 프로젝트는 2.0 필요해요"
"CUDA 11.8이랑 12.1 동시에 필요한데요"
"누가 서버에 뭘 깔아서 내 환경이 망가졌어요"
```

**해결책:** 프로젝트마다 Docker 이미지를 만들고, Slurm에서 Apptainer로 실행.

```
┌─ 프로젝트 A ──────────────────┐  ┌─ 프로젝트 B ──────────────────┐
│ Ubuntu 22.04                  │  │ Ubuntu 20.04                  │
│ CUDA 11.8 + PyTorch 2.0      │  │ CUDA 12.1 + PyTorch 2.3      │
│ Python 3.9                    │  │ Python 3.10                   │
│ diffusion-planner, nuplan-devkit │  │ mmdet3d, spconv            │
└───────────────────────────────┘  └───────────────────────────────┘
         │                                    │
         ▼                                    ▼
   project_a.sif                        project_b.sif
         │                                    │
         └──────────┬─────────────────────────┘
                    ▼
            ┌──────────────┐
            │  Slurm 클러스터  │  ← GPU 서버 9대에는 NVIDIA 드라이버만 있으면 됨
            │  (어떤 노드든)   │     Python, CUDA toolkit, pip 패키지 설치 불필요
            └──────────────┘
```

### Docker vs Apptainer

| | Docker | Apptainer (Singularity) |
|---|---|---|
| 권한 | root 필요 | **일반 사용자로 실행** |
| HPC 호환 | X (보안 문제) | **Slurm 네이티브 지원** |
| GPU | `--gpus all` | `--nv` (드라이버 자동 바인드) |
| 파일시스템 | 격리됨 | **호스트 $HOME 자동 마운트** |
| 이미지 형식 | 레이어 (tar) | **단일 SIF 파일** |

**요약:** Docker로 빌드하고, Apptainer(SIF)로 실행한다.

---

## 전체 워크플로우

```
[개발 PC / 마스터 노드]              [NAS]                    [GPU 노드]

 1. Dockerfile 작성
 2. docker build
 3. apptainer build → SIF 생성  ──→  /sw/containers/에 저장
                                          │
                                          │  NFS 공유
                                          ▼
                                     4. sbatch 제출
                                     5. apptainer exec --nv ← GPU 드라이버 바인드
                                        project.sif
                                        python train.py
```

---

## Step 1. Dockerfile 작성

프로젝트 루트에 `Dockerfile`을 만든다. **이것이 환경의 전부.**

```dockerfile
# 베이스: NVIDIA 공식 CUDA 이미지 (Ubuntu 버전 + CUDA 버전 선택)
FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive

# 시스템 패키지
RUN apt-get update && apt-get install -y \
    python3.9 python3.9-dev python3-pip git wget curl \
    && rm -rf /var/lib/apt/lists/*

# PyTorch (CUDA 버전에 맞는 wheel)
RUN pip3 install torch==2.0.0+cu118 torchvision==0.15.1+cu118 \
    --index-url https://download.pytorch.org/whl/cu118

# 프로젝트 의존성
RUN pip3 install pytorch_lightning==2.0.1 timm tensorboard

# 프로젝트 코드 복사 + 설치
WORKDIR /opt/my-project
COPY . .
RUN pip3 install -e .
```

**주의사항:**
- `nvidia/cuda` 태그에서 CUDA 버전을 선택 (11.8, 12.1, 12.4 등)
- `devel` = 빌드 도구 포함 (큰 이미지), `runtime` = 실행만 (작은 이미지)
- PyTorch wheel URL은 CUDA 버전에 맞춰야 함

### CUDA + PyTorch 호환 조합 예시

| CUDA | PyTorch | Base Image | pip index |
|------|---------|------------|-----------|
| 11.8 | 2.0.0 | `nvidia/cuda:11.8.0-devel-ubuntu22.04` | `cu118` |
| 11.8 | 2.1.0 | `nvidia/cuda:11.8.0-devel-ubuntu22.04` | `cu118` |
| 12.1 | 2.3.0 | `nvidia/cuda:12.1.1-devel-ubuntu22.04` | `cu121` |
| 12.4 | 2.5.0 | `nvidia/cuda:12.4.1-devel-ubuntu22.04` | `cu124` |

---

## Step 2. Docker 이미지 빌드

```bash
cd /path/to/my-project
docker build -t my-project:latest .
```

외부 프로젝트가 필요한 경우 (예: nuplan-devkit):

```bash
# --build-context로 추가 디렉토리를 빌드에 포함
docker buildx build \
    --build-context nuplan-devkit=/path/to/nuplan-devkit \
    -t diffusion-planner:latest .
```

Dockerfile에서 참조:

```dockerfile
COPY --from=nuplan-devkit . /opt/nuplan-devkit
RUN cd /opt/nuplan-devkit && pip3 install -e .
```

---

## Step 3. SIF 변환 및 배포

```bash
# Docker 이미지 → Apptainer SIF (단일 파일)
apptainer build /sw/containers/my-project.sif docker-daemon://my-project:latest

# 또는 Docker daemon 없이 tar에서 변환
docker save my-project:latest -o /tmp/my-project.tar
apptainer build /sw/containers/my-project.sif docker-archive:///tmp/my-project.tar
rm /tmp/my-project.tar
```

**SIF 파일 = 프로젝트 환경 전체가 담긴 단일 파일** (~5~15GB)

NAS 공유 디렉토리에 배치하면 모든 노드에서 즉시 사용 가능:

```
/sw/containers/
├── diffusion_planner.sif      # Ubuntu 22.04, CUDA 11.8, PyTorch 2.0
├── bevformer.sif               # Ubuntu 20.04, CUDA 11.3, PyTorch 1.12
├── uniad.sif                   # Ubuntu 22.04, CUDA 12.1, PyTorch 2.3
└── stable_diffusion.sif        # Ubuntu 22.04, CUDA 12.4, PyTorch 2.5
```

---

## Step 4. Slurm 잡 제출

### 기본 패턴

```bash
#!/bin/bash
#SBATCH --job-name=train
#SBATCH --output=/data/logs/%j.out
#SBATCH --gres=gpu:4
#SBATCH --partition=4090

apptainer exec --nv \
    --bind /data:/data \
    /sw/containers/my-project.sif \
    python3 /opt/my-project/train.py --batch_size 64
```

### 옵션 설명

```bash
apptainer exec \
    --nv \                          # NVIDIA GPU 드라이버를 컨테이너에 바인드
    --bind /data:/data \            # 호스트 /data → 컨테이너 /data 마운트
    --bind /sw:/sw \                # 호스트 /sw → 컨테이너 /sw 마운트
    /sw/containers/project.sif \    # SIF 파일 경로
    python3 train.py                # 컨테이너 안에서 실행할 명령
```

### 자동 마운트 되는 것

| 경로 | 자동 | 설명 |
|------|------|------|
| `$HOME` | O | 사용자 홈 디렉토리 |
| `/tmp` | O | 임시 디렉토리 |
| 현재 디렉토리 | O | `sbatch` 실행 위치 |
| `/data`, `/sw` | X | `--bind`로 명시 필요 |

### DDP 멀티 GPU

```bash
#!/bin/bash
#SBATCH --gres=gpu:4
#SBATCH --partition=4090

apptainer exec --nv \
    --bind /data:/data \
    /sw/containers/project.sif \
    python3 -m torch.distributed.run \
        --nproc-per-node 4 \
        --standalone \
        train.py
```

### DDP 멀티 노드 (2노드 x 4GPU = 8GPU)

```bash
#!/bin/bash
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=4
#SBATCH --gres=gpu:4
#SBATCH --partition=3090

export MASTER_ADDR=$(scontrol show hostnames $SLURM_JOB_NODELIST | head -n1)
export MASTER_PORT=29500

srun apptainer exec --nv \
    --bind /data:/data \
    /sw/containers/project.sif \
    python3 -m torch.distributed.run \
        --nproc-per-node 4 \
        --nnodes $SLURM_NNODES \
        --rdzv_backend c10d \
        --rdzv_endpoint $MASTER_ADDR:$MASTER_PORT \
        train.py
```

> `srun`이 각 노드에서 apptainer를 실행. 노드 간 통신은 NCCL이 처리.

---

## 자주 쓰는 명령어

### 컨테이너 안에서 인터랙티브 셸

```bash
# GPU 할당 받고 컨테이너 셸 진입
srun --gres=gpu:1 --partition=4090 --pty \
    apptainer shell --nv /sw/containers/project.sif

# 안에서 자유롭게 테스트
Apptainer> python3 -c "import torch; print(torch.cuda.is_available())"
Apptainer> nvidia-smi
Apptainer> python3 train.py --epochs 1  # 빠른 테스트
```

### 컨테이너 내용물 확인

```bash
# 설치된 Python 패키지 목록
apptainer exec /sw/containers/project.sif pip3 list

# Python 버전
apptainer exec /sw/containers/project.sif python3 --version

# CUDA 버전
apptainer exec /sw/containers/project.sif nvcc --version
```

### 이미지 업데이트

```bash
# 코드 수정 후 Docker 재빌드 → SIF 재변환
docker build -t my-project:latest .
apptainer build --force /sw/containers/my-project.sif docker-daemon://my-project:latest
#              ^^^^^^^ 기존 SIF 덮어쓰기
```

---

## 디렉토리 구조 권장안

```
NAS:/volume1/cluster/
├── home/                          # 사용자 홈 (NFS → /home)
├── data/                          # 데이터셋 + 학습 결과 (NFS → /data)
│   ├── datasets/
│   │   ├── nuplan-v1.1/
│   │   ├── nuscenes/
│   │   └── waymo/
│   ├── projects/
│   │   ├── diffusion-planner/
│   │   │   ├── preprocessed/     # 전처리 데이터
│   │   │   └── output/           # 체크포인트
│   │   └── bevformer/
│   └── logs/                      # Slurm 잡 로그
└── sw/                            # 공용 소프트웨어 (NFS → /sw)
    ├── containers/                # SIF 파일 모음
    │   ├── diffusion_planner.sif
    │   ├── bevformer.sif
    │   └── pytorch-base-cu118.sif # 범용 베이스 이미지
    └── miniconda3/                # (선택) 공유 conda
```

---

## 트러블슈팅

### GPU가 안 보임

```bash
# --nv 빼먹지 않았는지 확인
apptainer exec --nv project.sif nvidia-smi

# 호스트에서 nvidia-smi 되는지 확인
nvidia-smi
```

### 파일 접근 안 됨

```bash
# --bind 추가
apptainer exec --bind /data:/data project.sif ls /data/

# 또는 Apptainer 설정에서 기본 바인드 추가 (/etc/apptainer/apptainer.conf)
# bind path = /data
# bind path = /sw
```

### CUDA 버전 불일치

```
RuntimeError: CUDA error: no kernel image is available for execution on the device
```

- 호스트 드라이버 버전 확인: `nvidia-smi` (Driver Version 행)
- 드라이버 버전이 컨테이너 CUDA 버전을 지원하는지 확인
- 규칙: **드라이버는 상위 호환** (Driver 535 → CUDA 11.8, 12.0, 12.1 모두 OK)

### SIF 빌드 실패 (디스크 공간)

```bash
# Apptainer 임시 디렉토리 변경
export APPTAINER_TMPDIR=/data/tmp
apptainer build /sw/containers/project.sif docker-daemon://project:latest
```

---

## 요약

```
Dockerfile 작성 → docker build → apptainer build → NAS에 SIF 배포 → sbatch로 제출
```

- **GPU 서버에는 NVIDIA 드라이버만** 설치하면 됨
- Python, CUDA toolkit, pip 패키지는 **전부 컨테이너 안에**
- 프로젝트마다 독립 환경, **충돌 불가능**
- SIF 파일 하나 = 재현 가능한 실험 환경
