# CLAUDE.md - Slurm Docker Cluster

## Project Overview

Docker Compose 기반 SLURM 클러스터. 개발/테스트/경량 워크로드를 위한 잡 스케줄링 환경으로, 동적 워커 스케일링과 GPU/모니터링 옵션을 지원한다.

## Tech Stack

- **OS**: Rocky Linux 9
- **Slurm**: 25.11.2 / 25.05.6
- **DB**: MariaDB
- **Monitoring**: Elasticsearch/Kibana (optional), TensorBoard
- **GPU**: NVIDIA CUDA (optional)
- **Build**: Docker, Make

## Project Structure

```
slurm-docker-cluster/
├── config/                  # Slurm 설정 (버전별: 25.05, 25.11, common)
├── examples/                # 잡 제출 예제
├── slurm-dashboard/         # 웹 UI 클러스터 모니터링
├── rpmbuild/                # RPM 빌드 매크로
├── docker-compose.yml       # 서비스 정의 (mysql, slurmdbd, slurmctld, workers, ...)
├── Dockerfile               # 3-stage 멀티아키텍처 빌드
├── Makefile                 # 30+ 관리 명령어
└── docker-entrypoint.sh     # 컨테이너 초기화
```

## Build & Run

```bash
make build                   # Docker 이미지 빌드
make up                      # 클러스터 시작
make down                    # 클러스터 중지
make shell                   # slurmctld 셸 접속
make test                    # 테스트 실행
make scale-cpu-workers N=5   # 워커 스케일
make set-version VER=25.05.6 # Slurm 버전 전환
```

## Key Notes

- 버전 자동 감지: 설정 파일 자동 선택
- 동적 노드: c1,c2... (CPU), g1,g2... (GPU)
- GPU/Elasticsearch .env 파일로 기능 토글
- 멀티아키텍처 지원 (amd64/arm64)
- Diffusion-Planner 학습 지원

## Git Workflow

- 작업 시작 시 `git log --oneline -20`으로 최근 맥락 파악
- 하나의 기능/작업이 완료될 때마다 자동으로 commit 수행
- 커밋 메시지는 무엇을 왜 했는지 명확하게 기술하여, 나중에 커밋 로그만으로 프로젝트 흐름을 파악할 수 있도록 한다

## Rules

1. 한국어로 소통한다.
2. Slurm 설정 변경 시 버전 호환성 확인.
3. 불확실할 때는 질문한다.
