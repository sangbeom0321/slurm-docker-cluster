#!/bin/bash
#SBATCH --job-name=dp-preprocess
#SBATCH --output=/data/diffusion_planner/logs/preprocess_%j.out
#SBATCH --error=/data/diffusion_planner/logs/preprocess_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --time=02:00:00

#
# Diffusion-Planner 데이터 전처리 (nuPlan mini → NPZ)
# 실험용: --total_scenarios 100
#

CONTAINER=/data/containers/diffusion_planner.sif
NUPLAN_DATA=/data/nuplan/nuplan-v1.1/splits/mini
NUPLAN_MAPS=/data/nuplan/maps
SAVE_PATH=/data/diffusion_planner/preprocessed

echo "=== Diffusion-Planner Data Preprocessing ==="
echo "Container: ${CONTAINER}"
echo "Data path: ${NUPLAN_DATA}"
echo "Map path:  ${NUPLAN_MAPS}"
echo "Save path: ${SAVE_PATH}"
echo ""

apptainer exec \
    --bind /data:/data \
    --bind /workspace:/workspace \
    --pwd /opt/Diffusion-Planner \
    ${CONTAINER} \
    python3 /opt/Diffusion-Planner/data_process.py \
        --data_path ${NUPLAN_DATA} \
        --map_path ${NUPLAN_MAPS} \
        --save_path ${SAVE_PATH} \
        --total_scenarios 100

echo ""
echo "=== Preprocessing complete ==="
echo "Preprocessed files:"
ls -lh ${SAVE_PATH}/*.npz 2>/dev/null | wc -l
echo "files generated"
