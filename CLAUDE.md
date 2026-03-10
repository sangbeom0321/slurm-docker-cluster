# CLAUDE.md - SLURM Bare-Metal GPU Cluster

## Project Overview

베어메탈 SLURM GPU 클러스터. cluster.conf 기반 노드 관리, 2PC~9대 확장 지원.

## Tech Stack

- **OS**: Ubuntu 22.04/24.04
- **Slurm**: 25.11.2 (소스 빌드)
- **DB**: MariaDB
- **Auth**: Munge
- **GPU**: NVIDIA (nvml 자동 감지)

## Project Structure

```
├── cluster.conf            # 노드 정의 (핵심 설정 파일)
├── config/                 # SLURM 설정 (generate-slurm-conf.sh로 자동 생성)
├── scripts/                # 설치 스크립트 (common → master/worker)
├── examples/jobs/          # 잡 제출 예제
├── slurm-dashboard/        # 웹 대시보드
└── docs/                   # 상세 가이드
```

## Build & Run

```bash
# 마스터: setup-common.sh → setup-master.sh
# 워커:   setup-common.sh → setup-worker.sh (munge 키 필요)
# 노드 추가: cluster.conf 수정 → generate-slurm-conf.sh → scontrol reconfigure
```

## Key Notes

- cluster.conf 수정 → generate-slurm-conf.sh로 slurm.conf 자동 생성
- 현재 2PC 테스트 (daniel + 5090), 향후 9대 확장 예정
- Diffusion-Planner 학습 잡 예제 포함

## Git Workflow

- 작업 시작 시 `git log --oneline -20`으로 최근 맥락 파악
- 하나의 기능/작업이 완료될 때마다 자동으로 commit 수행
- 커밋 메시지는 무엇을 왜 했는지 명확하게 기술

## Rules

1. 한국어로 소통한다.
2. cluster.conf 변경 후 반드시 generate-slurm-conf.sh 실행.
3. 불확실할 때는 질문한다.
