#!/usr/bin/env python3
"""
Sample training script that logs to W&B.
Simulates a CNN training loop with hyperparameters, metrics, and model artifact.
"""

import wandb
import random
import math
import time
import argparse
import json
import os


def simulate_training(config):
    """Simulate a training loop with realistic loss curves."""
    run = wandb.init(
        project=config["project"],
        name=config.get("run_name"),
        config={
            "model": config["model"],
            "optimizer": config["optimizer"],
            "learning_rate": config["lr"],
            "batch_size": config["batch_size"],
            "epochs": config["epochs"],
            "weight_decay": config["weight_decay"],
            "dataset": config["dataset"],
            "gpu_type": config.get("gpu_type", "simulated"),
        },
    )

    # Simulate training
    epochs = config["epochs"]
    base_loss = 2.5 + random.uniform(-0.3, 0.3)
    base_acc = 0.1 + random.uniform(-0.05, 0.05)
    lr = config["lr"]
    best_val_acc = 0.0

    for epoch in range(1, epochs + 1):
        # Simulate decreasing loss with noise
        progress = epoch / epochs
        train_loss = base_loss * math.exp(-3 * progress) + random.uniform(0, 0.05)
        val_loss = train_loss + random.uniform(0.01, 0.15)
        train_acc = 1.0 - base_loss * 0.35 * math.exp(-3 * progress) + random.uniform(-0.02, 0.02)
        val_acc = train_acc - random.uniform(0.01, 0.05)
        current_lr = lr * (0.1 ** (progress * 2)) if progress > 0.5 else lr

        train_acc = min(max(train_acc, 0), 1.0)
        val_acc = min(max(val_acc, 0), 1.0)
        best_val_acc = max(best_val_acc, val_acc)

        wandb.log({
            "train_loss": round(train_loss, 4),
            "val_loss": round(val_loss, 4),
            "train_acc": round(train_acc, 4),
            "val_acc": round(val_acc, 4),
            "learning_rate": round(current_lr, 8),
            "epoch": epoch,
        })

        print(f"Epoch {epoch}/{epochs} - loss: {train_loss:.4f} - acc: {train_acc:.4f} "
              f"- val_loss: {val_loss:.4f} - val_acc: {val_acc:.4f}")
        time.sleep(0.3)  # Simulate computation time

    # Log final summary metrics
    wandb.summary["best_val_acc"] = round(best_val_acc, 4)
    wandb.summary["final_train_loss"] = round(train_loss, 4)

    # Log a simple model artifact
    model_info = {
        "model": config["model"],
        "final_accuracy": round(val_acc, 4),
        "parameters": sum(random.randint(1000, 50000) for _ in range(10)),
    }
    artifact_path = "/tmp/model_info.json"
    with open(artifact_path, "w") as f:
        json.dump(model_info, f, indent=2)
    artifact = wandb.Artifact(f"model-{config['model'].replace('/', '-')}", type="model")
    artifact.add_file(artifact_path)
    run.log_artifact(artifact)

    print(f"\nTraining complete! Final val_acc: {val_acc:.4f}")
    print(f"W&B run logged to project: {config['project']}")
    wandb.finish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="Diffusion-Planner")
    parser.add_argument("--run-name", default=None)
    parser.add_argument("--model", default="DiT-L/2")
    parser.add_argument("--optimizer", default="AdamW")
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--weight-decay", type=float, default=0.01)
    parser.add_argument("--dataset", default="nuPlan-v1.1")
    parser.add_argument("--gpu-type", default="simulated")
    args = parser.parse_args()

    config = {
        "project": args.project,
        "run_name": args.run_name,
        "model": args.model,
        "optimizer": args.optimizer,
        "lr": args.lr,
        "batch_size": args.batch_size,
        "epochs": args.epochs,
        "weight_decay": args.weight_decay,
        "dataset": args.dataset,
        "gpu_type": args.gpu_type,
    }
    simulate_training(config)
