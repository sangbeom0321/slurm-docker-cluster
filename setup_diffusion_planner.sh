#!/bin/bash
set -e

#
# Diffusion-Planner 환경 구축 스크립트
# Docker 이미지 빌드 → Apptainer SIF 변환 → Slurm 공유 볼륨에 배포
#

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIFFUSION_PLANNER_DIR="${SCRIPT_DIR}/../Diffusion-Planner"
NUPLAN_DEVKIT_DIR="${SCRIPT_DIR}/../../Done/nuplan-devkit"
SIF_NAME="diffusion_planner.sif"

echo "============================================"
echo "  Diffusion-Planner Setup for Slurm Cluster"
echo "============================================"

# 1. Build Docker image
echo ""
echo "[1/3] Building Docker image..."
docker buildx build \
    --build-context nuplan-devkit="${NUPLAN_DEVKIT_DIR}" \
    -t diffusion-planner:latest \
    "${DIFFUSION_PLANNER_DIR}"

echo "Docker image built: diffusion-planner:latest"

# 2. Convert to Apptainer SIF
echo ""
echo "[2/3] Converting to Apptainer SIF..."
docker save diffusion-planner:latest -o /tmp/diffusion_planner.tar
echo "Docker image saved to /tmp/diffusion_planner.tar"

# Build SIF inside slurmctld (Apptainer is installed there)
docker exec slurmctld mkdir -p /data/containers
docker cp /tmp/diffusion_planner.tar slurmctld:/tmp/diffusion_planner.tar
docker exec slurmctld apptainer build \
    /data/containers/${SIF_NAME} \
    docker-archive:///tmp/diffusion_planner.tar
docker exec slurmctld rm -f /tmp/diffusion_planner.tar
rm -f /tmp/diffusion_planner.tar

echo "SIF deployed: /data/containers/${SIF_NAME}"

# 3. Create output directories
echo ""
echo "[3/3] Creating directories..."
docker exec slurmctld mkdir -p /data/diffusion_planner/preprocessed
docker exec slurmctld mkdir -p /data/diffusion_planner/output
docker exec slurmctld mkdir -p /data/diffusion_planner/logs

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Preprocess data:"
echo "     docker exec slurmctld sbatch /data/examples/diffusion_planner_preprocess.sbatch"
echo ""
echo "  2. Train model:"
echo "     docker exec slurmctld sbatch /data/examples/diffusion_planner_train.sbatch"
