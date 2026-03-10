# SLURM 클러스터 사용자 가이드

> AILAB GPU 클러스터 | SLURM 25.11.2 | 2026년 3월 기준

---

## 1. 접속 방법

### 1.1 SSH 접속

```bash
# 마스터 노드(computer0)에 SSH 접속
ssh your_username@192.168.1.10
```

### 1.2 웹 대시보드

브라우저에서 접속:

```
http://192.168.1.10:3080
```

대시보드에서 할 수 있는 일:
- 클러스터 상태 확인 (Overview)
- 웹에서 잡 제출 (Submit Job)
- 잡 큐 확인 / 취소 (Jobs)
- 노드 리소스 확인 (Nodes)
- 학습 모니터링 (Experiments - TensorBoard)

---

## 2. 클러스터 리소스 현황

### 노드 구성

| 노드 | GPU | VRAM | 용도 |
|------|-----|------|------|
| computer0 | 3080 x4 | 10GB x4 | 마스터 + 계산 |
| computer1~4 | 3090 x4 | 24GB x4 | 계산 노드 |
| computer5~7 | 4090 x4 | 24GB x4 | 계산 노드 |
| computer8 | A6000 x4 | 48GB x4 | 계산 노드 (대형 모델) |

### 파티션 (큐)

| 파티션 | 노드 | 언제 사용? |
|--------|------|-----------|
| `all` (기본) | computer[0-8] | GPU 모델 상관없을 때 |
| `3090` | computer[1-4] | 3090 지정 |
| `4090` | computer[5-7] | 4090 지정 |
| `a6000` | computer8 | VRAM 48GB 필요할 때 |

### 공유 디렉토리

| 경로 | 용도 | 예시 |
|------|------|------|
| `/home/<user>/` | 홈 디렉토리 | 개인 설정, 코드 |
| `/data/` | 데이터 + 잡 결과 | 데이터셋, 체크포인트, 로그 |
| `/sw/` | 공유 소프트웨어 | 컨테이너 SIF, conda |

> 모든 디렉토리는 NAS에서 NFS로 공유되어 **어떤 노드에서든 동일하게 접근 가능**합니다.

---

## 3. 잡 제출 - 기본

### 3.1 즉시 실행 (srun)

```bash
# GPU 1개 할당받아 nvidia-smi 실행
srun --gres=gpu:1 nvidia-smi

# GPU 1개 할당받아 인터랙티브 셸 진입
srun --gres=gpu:1 --pty bash
```

### 3.2 스크립트 제출 (sbatch) - 가장 많이 사용

```bash
# job.sh 파일 작성 후 제출
sbatch job.sh

# 출력: Submitted batch job 12345
```

### 3.3 가장 간단한 잡 스크립트

```bash
#!/bin/bash
#SBATCH --job-name=my_train        # 잡 이름
#SBATCH --output=/data/logs/%j.out # 표준 출력 (%j = Job ID)
#SBATCH --error=/data/logs/%j.err  # 에러 출력
#SBATCH --gres=gpu:1               # GPU 1개 요청
#SBATCH --time=04:00:00            # 최대 4시간

echo "Job started on $(hostname)"
nvidia-smi
python3 /data/my_project/train.py
```

저장 후 실행:

```bash
mkdir -p /data/logs
sbatch job.sh
```

### 3.4 웹 대시보드에서 잡 제출

1. http://192.168.1.10:3080 접속
2. 좌측 사이드바에서 사용자 선택
3. **Submit Job** 클릭
4. 양식 작성:
   - Job Name: 잡 이름
   - Partition: 파티션 선택 (기본: all)
   - GPUs: GPU 개수 (예: `1`, `4`, `4090:2`)
   - CPUs per Task: CPU 코어 수
   - Memory: 메모리 (예: `32G`)
   - Time Limit: 최대 시간 (예: `8:00:00`)
   - Command: 실행할 명령어
5. **Submit Job** 버튼 클릭

---

## 4. 잡 스크립트 작성법

### 4.1 SBATCH 옵션 정리

```bash
#!/bin/bash
#SBATCH --job-name=train           # 잡 이름 (squeue에 표시)
#SBATCH --output=/data/logs/%j.out # 표준 출력 파일
#SBATCH --error=/data/logs/%j.err  # 에러 출력 파일

# === 리소스 요청 ===
#SBATCH --partition=4090           # 파티션 (all, 3090, 4090, a6000)
#SBATCH --nodes=1                  # 노드 수
#SBATCH --ntasks-per-node=1        # 노드당 태스크 수
#SBATCH --cpus-per-task=8          # 태스크당 CPU 코어 수
#SBATCH --mem=64G                  # 메모리
#SBATCH --gres=gpu:4               # GPU 개수

# === 시간 ===
#SBATCH --time=24:00:00            # 최대 실행 시간 (HH:MM:SS)
```

### 4.2 GPU 요청 방법

```bash
# GPU 1개 (모델 무관)
#SBATCH --gres=gpu:1

# GPU 4개 (모델 무관)
#SBATCH --gres=gpu:4

# 3090 2개 지정
#SBATCH --gres=gpu:3090:2
#SBATCH --partition=3090

# A6000 4개 지정 (VRAM 48GB 필요 시)
#SBATCH --gres=gpu:a6000:4
#SBATCH --partition=a6000
```

### 4.3 예시: 단일 GPU 학습

```bash
#!/bin/bash
#SBATCH --job-name=single_gpu
#SBATCH --output=/data/logs/%j.out
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --partition=4090
#SBATCH --time=12:00:00

cd /data/my_project
python3 train.py \
    --batch_size 64 \
    --epochs 100 \
    --lr 1e-4
```

### 4.4 예시: 멀티 GPU 학습 (DDP, 단일 노드)

```bash
#!/bin/bash
#SBATCH --job-name=ddp_single
#SBATCH --output=/data/logs/%j.out
#SBATCH --gres=gpu:4
#SBATCH --cpus-per-task=16
#SBATCH --mem=120G
#SBATCH --partition=4090
#SBATCH --time=24:00:00

cd /data/my_project

python3 -m torch.distributed.run \
    --nproc-per-node 4 \
    --standalone \
    train.py \
    --batch_size 256 \
    --epochs 100
```

### 4.5 예시: 멀티 노드 분산 학습 (DDP, 2노드 x 4GPU = 8GPU)

```bash
#!/bin/bash
#SBATCH --job-name=ddp_multi
#SBATCH --output=/data/logs/%j.out
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=4
#SBATCH --cpus-per-task=8
#SBATCH --mem=120G
#SBATCH --gres=gpu:4
#SBATCH --partition=3090
#SBATCH --time=48:00:00

export MASTER_ADDR=$(scontrol show hostnames $SLURM_JOB_NODELIST | head -n1)
export MASTER_PORT=29500

srun python3 -m torch.distributed.run \
    --nproc-per-node 4 \
    --nnodes $SLURM_NNODES \
    --rdzv_backend c10d \
    --rdzv_endpoint $MASTER_ADDR:$MASTER_PORT \
    /data/my_project/train.py \
    --batch_size 512
```

### 4.6 예시: 컨테이너(Apptainer) 기반 학습

프로젝트별 독립 환경이 필요할 때 SIF 컨테이너를 사용합니다.

```bash
#!/bin/bash
#SBATCH --job-name=container_train
#SBATCH --output=/data/logs/%j.out
#SBATCH --gres=gpu:4
#SBATCH --partition=4090
#SBATCH --time=24:00:00

CONTAINER=/sw/containers/my-project.sif

apptainer exec --nv \
    --bind /data:/data \
    --bind /sw:/sw \
    ${CONTAINER} \
    python3 /opt/my-project/train.py --gpus 4
```

**주요 옵션:**
- `--nv`: GPU 드라이버 자동 바인드 (필수)
- `--bind A:B`: 호스트 A를 컨테이너 내 B로 마운트
- 컨테이너 안에서 `$HOME`은 자동 마운트됨

---

## 5. 잡 관리

### 5.1 잡 상태 확인

```bash
# 내 잡 확인
squeue -u $(whoami)

# 출력 예시:
#   JOBID PARTITION     NAME     USER ST  TIME  NODES NODELIST
#   12345      4090    train   daniel  R  2:30      1 computer5

# 전체 잡 큐
squeue

# 상세 정보
scontrol show job 12345
```

**잡 상태 코드:**
| 코드 | 의미 |
|------|------|
| `PD` | Pending (대기 중 - 리소스 부족) |
| `R` | Running (실행 중) |
| `CG` | Completing (종료 중) |
| `CD` | Completed (완료) |
| `F` | Failed (실패) |
| `CA` | Cancelled (취소됨) |

### 5.2 잡 취소

```bash
# 특정 잡 취소
scancel 12345

# 내 잡 모두 취소
scancel -u $(whoami)

# 잡 이름으로 취소
scancel --name=train
```

### 5.3 잡 히스토리 조회

```bash
# 최근 완료된 잡 확인
sacct --format=JobID,JobName,State,Elapsed,AllocGRES,NodeList -u $(whoami)

# 출력 예시:
#   JobID     JobName    State    Elapsed  AllocGRES  NodeList
#   12345       train  COMPLETED  03:45:22  gpu:4090:4  computer5
#   12346   preprocess  COMPLETED  00:23:11             computer0

# 특정 기간 잡 조회
sacct --starttime=2026-03-01 --endtime=2026-03-10 -u $(whoami)
```

### 5.4 잡 출력 확인

```bash
# 실행 중인 잡의 실시간 출력 확인
tail -f /data/logs/12345.out

# 에러 로그 확인
cat /data/logs/12345.err
```

---

## 6. 클러스터 상태 확인

### 6.1 노드/파티션 상태

```bash
# 파티션별 상태 요약
sinfo
# 출력:
# PARTITION AVAIL  TIMELIMIT  NODES  STATE NODELIST
# all*         up   infinite      7   idle computer[0-4,6-8]
# all*         up   infinite      2  mixed computer5,computer7
# 3090         up   infinite      4   idle computer[1-4]
# 4090         up   infinite      1   idle computer6
# 4090         up   infinite      2  mixed computer5,computer7
# a6000        up   infinite      1   idle computer8

# 노드별 GPU 현황
sinfo -o "%N %G %C %m"
# %N=노드명, %G=GRES(GPU), %C=CPU(할당/유휴/기타/전체), %m=메모리
```

**노드 상태:**
| 상태 | 의미 |
|------|------|
| `idle` | 유휴 (사용 가능) |
| `mixed` | 일부 리소스 사용 중 |
| `alloc` | 전체 리소스 사용 중 |
| `drain` | 관리자가 비활성화 (점검 중) |
| `down` | 장애 |

### 6.2 GPU 사용 현황

```bash
# 노드별 GPU 사용 상태
sinfo -N -o "%N %G %e/%m %C"

# 특정 노드 상세 정보
scontrol show node computer5
```

---

## 7. 학습 모니터링 (TensorBoard)

### 7.1 학습 스크립트에서 로깅

```python
from torch.utils.tensorboard import SummaryWriter

# 로그를 /data 하위에 저장 (TensorBoard 서버가 자동 감지)
writer = SummaryWriter(log_dir="/data/my_project/output/tb")

for epoch in range(num_epochs):
    train_loss = train_one_epoch()
    val_loss = validate()

    writer.add_scalar("train/loss", train_loss, epoch)
    writer.add_scalar("val/loss", val_loss, epoch)
    writer.add_scalar("learning_rate", lr, epoch)

writer.close()
```

PyTorch Lightning 사용 시:

```python
from pytorch_lightning.loggers import TensorBoardLogger

logger = TensorBoardLogger(
    save_dir="/data/my_project/output",
    name="tb"
)
trainer = pl.Trainer(logger=logger, ...)
```

### 7.2 대시보드에서 모니터링

1. http://192.168.1.10:3080 접속
2. **Experiments** 탭 클릭
3. 두 가지 뷰 사용 가능:

| 뷰 | 설명 |
|----|------|
| **Runs** | /data 내 이벤트 파일 스캔. 프로젝트/런 목록, 메트릭 요약, 상태(running/finished), 차트 |
| **TensorBoard** | TensorBoard 전체 UI를 iframe으로 임베드. Scalars, Images, Graphs, Histograms 등 |

### 7.3 TensorBoard 직접 접속

```
http://192.168.1.10:6006
```

> TensorBoard가 `/data` 전체를 `--logdir`로 스캔하므로, `/data` 하위 어디에 이벤트 파일을 저장하든 자동으로 감지됩니다.

---

## 8. 자주 쓰는 패턴

### 8.1 GPU 인터랙티브 세션 (디버깅/테스트)

```bash
# GPU 1개 할당 + 2시간 제한 + 인터랙티브 셸
srun --gres=gpu:1 --time=02:00:00 --pty bash

# 셸 안에서 자유롭게 테스트
nvidia-smi
python3 -c "import torch; print(torch.cuda.is_available())"
python3 train.py --epochs 1  # 빠른 테스트
```

### 8.2 컨테이너 인터랙티브 세션

```bash
srun --gres=gpu:1 --partition=4090 --pty \
    apptainer shell --nv /sw/containers/my-project.sif

# 컨테이너 안에서
Apptainer> python3 -c "import torch; print(torch.__version__)"
Apptainer> python3 train.py --epochs 1
```

### 8.3 잡 의존성 (순차 실행)

```bash
# 전처리 → 학습 순서로 실행
JOB1=$(sbatch --parsable preprocess.sh)
sbatch --dependency=afterok:$JOB1 train.sh

# JOB1이 성공(afterok)해야 train.sh가 실행됨
```

### 8.4 잡 배열 (하이퍼파라미터 서치)

```bash
#!/bin/bash
#SBATCH --job-name=hpsearch
#SBATCH --output=/data/logs/hp_%A_%a.out
#SBATCH --gres=gpu:1
#SBATCH --array=0-4           # 5개의 잡 생성 (SLURM_ARRAY_TASK_ID = 0,1,2,3,4)

LR_LIST=(1e-3 5e-4 1e-4 5e-5 1e-5)
LR=${LR_LIST[$SLURM_ARRAY_TASK_ID]}

python3 train.py --lr $LR --run_name "lr_${LR}"
```

```bash
sbatch hp_search.sh
# 5개 잡이 동시에 제출됨 (GPU 여유에 따라 병렬 실행)
```

### 8.5 알림 받기 (잡 완료 시)

```bash
#!/bin/bash
#SBATCH --mail-type=END,FAIL     # 완료/실패 시 알림
#SBATCH --mail-user=you@email.com
```

> 메일 서버 설정이 필요합니다. 대안으로 학습 스크립트 끝에 슬랙 웹훅 등을 호출할 수 있습니다.

---

## 9. 프로젝트 디렉토리 구조 권장안

```
/data/
├── datasets/                     # 공용 데이터셋
│   ├── nuplan-v1.1/
│   ├── nuscenes/
│   └── waymo/
├── <사용자명>/                    # 사용자별 작업 디렉토리
│   └── <프로젝트명>/
│       ├── code/                  # 또는 git clone 경로
│       ├── output/
│       │   ├── checkpoints/       # 모델 체크포인트
│       │   └── tb/                # TensorBoard 로그
│       └── preprocessed/          # 전처리 데이터
└── logs/                          # Slurm 잡 로그 (공용)
```

---

## 10. 트러블슈팅

### 잡이 계속 PENDING 상태

```bash
# 원인 확인
squeue -j 12345 -o "%R"
```

| 이유 | 해결 |
|------|------|
| `Resources` | GPU/CPU/메모리 부족. 다른 잡이 끝날 때까지 대기 |
| `Priority` | 우선순위 대기. 시간이 지나면 실행됨 |
| `PartitionNodeLimit` | 파티션에 충분한 노드 없음 → 파티션 변경 |
| `ReqNodeNotAvail` | 요청한 노드가 down/drain → 관리자 문의 |

### GPU가 보이지 않음

```bash
# 잡 안에서 확인
echo $CUDA_VISIBLE_DEVICES   # 할당된 GPU 번호
nvidia-smi                     # GPU 상태

# 비어있으면 --gres=gpu:N 을 빼먹었을 수 있음
```

### Out of Memory (OOM)

```bash
# 메모리를 더 요청
#SBATCH --mem=128G

# GPU OOM이면 batch size 줄이기
python3 train.py --batch_size 32  # 기존 64에서 줄임
```

### 잡이 시간 초과로 죽음

```bash
# 시간 제한 늘리기
#SBATCH --time=48:00:00   # 기본 무제한이 아닐 수 있음

# 체크포인트에서 재시작하는 스크립트 작성 권장
python3 train.py --resume /data/output/checkpoint_last.pt
```

### 어떤 파티션/GPU를 써야 할지 모르겠음

| 상황 | 추천 |
|------|------|
| 빠른 테스트/디버깅 | `all` 파티션, GPU 1개 |
| 일반 학습 (batch 적당) | `3090` 또는 `4090`, GPU 1~4개 |
| VRAM 많이 필요 (대형 모델) | `a6000`, GPU 1~4개 (VRAM 48GB) |
| 대규모 분산 학습 | `3090` 멀티노드 또는 `4090` 멀티노드 |

---

## 빠른 참조 카드

```bash
# === 잡 제출 ===
sbatch job.sh                          # 잡 스크립트 제출
srun --gres=gpu:1 --pty bash           # GPU 인터랙티브 셸

# === 잡 확인 ===
squeue -u $(whoami)                    # 내 잡 목록
scontrol show job 12345                # 잡 상세 정보
sacct -u $(whoami)                     # 잡 히스토리

# === 잡 취소 ===
scancel 12345                          # 특정 잡 취소
scancel -u $(whoami)                   # 내 잡 모두 취소

# === 클러스터 상태 ===
sinfo                                  # 파티션/노드 요약
sinfo -N -o "%N %G %C"                # 노드별 GPU/CPU

# === 대시보드 ===
# http://192.168.1.10:3080             # 웹 대시보드
# http://192.168.1.10:6006             # TensorBoard 직접 접속
```

SLURM → Diffusion-Planner 학습 → 대시보드 전체 흐름 (간략)                                                                                                                               
                                                                                                                                                                                           
  1. Docker 이미지 빌드 + SIF 변환                                                                                                                                                         
                                                                                                                                                                                           
  # 프로젝트 Docker 이미지 빌드                                                                                                                                                          
  cd /data/projects/Diffusion-Planner                                                                                                                                                      
  docker buildx build --build-context nuplan-devkit=/data/projects/nuplan-devkit -t diffusion-planner:latest .
                                                                                                                                                                                           
  # Apptainer SIF로 변환 → NAS 공유 디렉토리에 배치                                                                                                                                        
  docker save diffusion-planner:latest -o /tmp/dp.tar                                                                                                                                      
  apptainer build /sw/containers/diffusion_planner.sif docker-archive:///tmp/dp.tar

  2. 데이터 전처리 (sbatch)

  sbatch << 'EOF'
  #!/bin/bash
  #SBATCH --job-name=dp-preprocess
  #SBATCH --output=/data/logs/preprocess_%j.out
  apptainer exec --bind /data:/data /sw/containers/diffusion_planner.sif \
      python3 /opt/Diffusion-Planner/data_process.py \
      --data_path /data/nuplan-v1.1/splits/mini \
      --map_path /data/nuplan-v1.1/maps \
      --save_path /data/diffusion_planner/preprocessed \
      --total_scenarios 100
  EOF

  3. 학습 Job 제출 (sbatch + Apptainer + DDP)

  sbatch << 'EOF'
  #!/bin/bash
  #SBATCH --job-name=dp-train
  #SBATCH --output=/data/logs/dp_train_%j.out
  #SBATCH --gres=gpu:4
  #SBATCH --partition=4090
  #SBATCH --time=48:00:00
  apptainer exec --nv --bind /data:/data /sw/containers/diffusion_planner.sif \
      python3 -m torch.distributed.run --nnodes 1 --nproc-per-node 4 --standalone \
      /opt/Diffusion-Planner/train_predictor.py \
      --train_set /data/diffusion_planner/preprocessed \
      --train_set_list /data/diffusion_planner/training_files.json
  EOF
  - SLURM이 SLURM_PROCID 환경변수를 세팅 → ddp.py가 자동 감지하여 DDP 초기화

 - 멀티노드도 가능: --nodes=2 --ntasks-per-node=4 + srun apptainer exec ...

  4. 백엔드 서버 (slurmrestd + 대시보드 프록시)

  # JWT 키 생성 (1회)
  openssl rand -hex 32 > /etc/slurm/jwt_hs256.key

  # slurmrestd 시작 (REST API)
  sudo -u slurm slurmrestd 0.0.0.0:6820 &

  # 대시보드 프록시 서버 시작
  cd /sw/slurm-dashboard
  python3 server.py &
  # 또는 systemd: sudo systemctl start slurm-dashboard

  5. 대시보드 접속

  http://computer0:3080   ← AILAB 대시보드 (Overview, Submit Job, Jobs, Nodes, Experiments)
  http://computer0:6006   ← TensorBoard 직접 접속

  대시보드 기능:

  ┌─────────────┬─────────────────────────────────────────────────────┐
  │     탭      │                        기능                         │
  ├─────────────┼─────────────────────────────────────────────────────┤
  │ Overview    │ 노드 상태, CPU 사용률, Running/Pending 잡           │
  ├─────────────┼─────────────────────────────────────────────────────┤
  │ Submit Job  │ 웹에서 잡 제출                                      │
  ├─────────────┼─────────────────────────────────────────────────────┤
  │ Jobs        │ 잡 큐 확인 + Cancel                                 │
  ├─────────────┼─────────────────────────────────────────────────────┤
  │ Nodes       │ 노드별 CPU/Memory/GPU 바                            │
  ├─────────────┼─────────────────────────────────────────────────────┤
  │ Experiments │ TensorBoard 이벤트 스캔 + TensorBoard iframe 임베드 │
  └─────────────┴─────────────────────────────────────────────────────┘
