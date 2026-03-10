#!/bin/bash
#SBATCH --job-name=dp-train
#SBATCH --output=/data/diffusion_planner/logs/train_%j.out
#SBATCH --error=/data/diffusion_planner/logs/train_%j.err
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --partition=gpu
#SBATCH --time=24:00:00

#
# Diffusion-Planner 학습 (실험용: 소규모 배치 + 짧은 에폭)
# GPU 1개, batch_size 32, 10 epochs
#

CONTAINER=/data/containers/diffusion_planner.sif
TRAIN_DATA=/data/diffusion_planner/preprocessed
TRAIN_LIST=/data/diffusion_planner/preprocessed/training_files.json
SAVE_DIR=/data/diffusion_planner/output

echo "=== Diffusion-Planner Training ==="
echo "Container: ${CONTAINER}"
echo "Train data: ${TRAIN_DATA}"
echo "Train list: ${TRAIN_LIST}"
echo "Output dir: ${SAVE_DIR}"
echo "GPUs: ${SLURM_GPUS_ON_NODE:-1}"
echo ""

# training_files.json이 없으면 자동 생성
if [ ! -f "${TRAIN_LIST}" ]; then
    echo "Generating training file list..."
    apptainer exec ${CONTAINER} python3 -c "
import os, json
path = '${TRAIN_DATA}'
files = sorted([f for f in os.listdir(path) if f.endswith('.npz')])
with open('${TRAIN_LIST}', 'w') as f:
    json.dump(files, f, indent=2)
print(f'Generated list with {len(files)} files')
"
fi

NGPUS=${SLURM_GPUS_ON_NODE:-1}

apptainer exec --nv \
    --bind /data:/data \
    --bind /workspace:/workspace \
    --pwd /opt/Diffusion-Planner \
    --env MASTER_ADDR=127.0.0.1 \
    --env MASTER_PORT=29500 \
    ${CONTAINER} \
    python3 -m torch.distributed.run \
        --nnodes 1 \
        --nproc-per-node ${NGPUS} \
        --master-addr 127.0.0.1 \
        --master-port 29500 \
        /opt/Diffusion-Planner/train_predictor.py \
        --train_set ${TRAIN_DATA} \
        --train_set_list ${TRAIN_LIST} \
        --batch_size 32 \
        --train_epochs 10 \
        --save_utd 5 \
        --save_dir ${SAVE_DIR} \
        --port 29500 \
        --num_workers 2

echo ""
echo "=== Training complete ==="
echo "Checkpoints saved to: ${SAVE_DIR}"
