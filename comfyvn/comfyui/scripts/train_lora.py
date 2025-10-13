# comfyvn/scripts/train_lora.py
# 🧬 LoRA Training Automation (v1.0)
# Chat Source: 🧬 9. LoRA System Production Chat

import os
import json
import subprocess
import threading
import datetime
from pathlib import Path


class LoRATrainingJob:
    """Encapsulates a single LoRA training job."""

    def __init__(
        self, dataset_path, output_name, base_model, steps=1000, learning_rate=1e-4
    ):
        self.dataset_path = dataset_path
        self.output_name = output_name
        self.base_model = base_model
        self.steps = steps
        self.learning_rate = learning_rate
        self.status = "pending"
        self.log_path = Path("./logs/lora_training")
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.log_file = (
            self.log_path
            / f"{output_name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )

    def start(self):
        """Launch LoRA training as a background subprocess."""
        self.status = "running"
        cmd = [
            "python",
            "train_network.py",
            f"--pretrained_model_name_or_path={self.base_model}",
            f"--train_data_dir={self.dataset_path}",
            f"--output_name={self.output_name}",
            f"--max_train_steps={self.steps}",
            f"--learning_rate={self.learning_rate}",
        ]

        print(f"[LoRA Training] Starting: {' '.join(cmd)}")
        with open(self.log_file, "w") as log:
            process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT)
        return process


class LoRATrainer:
    """Manages and tracks LoRA training jobs."""

    def __init__(self):
        self.jobs = {}

    def start_job(self, dataset_path, output_name, base_model, steps=1000, lr=1e-4):
        job = LoRATrainingJob(dataset_path, output_name, base_model, steps, lr)
        proc = job.start()
        self.jobs[output_name] = {"job": job, "proc": proc}
        print(f"[LoRATrainer] Job '{output_name}' started (PID {proc.pid})")

    def list_jobs(self):
        return {
            name: {"status": j["job"].status, "pid": j["proc"].pid}
            for name, j in self.jobs.items()
        }

    def stop_job(self, output_name):
        if output_name not in self.jobs:
            print(f"[LoRATrainer] No active job '{output_name}'")
            return
        self.jobs[output_name]["proc"].terminate()
        self.jobs[output_name]["job"].status = "terminated"
        print(f"[LoRATrainer] Job '{output_name}' terminated")

    def tail_log(self, output_name, lines=20):
        """Read last lines of the log file."""
        job = self.jobs.get(output_name, {}).get("job")
        if not job or not job.log_file.exists():
            return []
        with open(job.log_file, "r") as f:
            return f.readlines()[-lines:]


# --- [Integration Patch | 🧬 LoRA System Production Chat] --------------------
from PySide6.QtCore import QObject, Signal


class LoRAJobSignals(QObject):
    job_started = Signal(str, str)  # job_id, label
    job_updated = Signal(str, str)  # job_id, new_status
    job_finished = Signal(str)  # job_id


class LoRATrainerWithSignals(LoRATrainer):
    """LoRA Trainer that broadcasts signals to GUI dock."""

    def __init__(self):
        super().__init__()
        self.signals = LoRAJobSignals()

    def start_job(self, dataset_path, output_name, base_model, steps=1000, lr=1e-4):
        super().start_job(dataset_path, output_name, base_model, steps, lr)
        self.signals.job_started.emit(output_name, "LoRA Training")

    def stop_job(self, output_name):
        super().stop_job(output_name)
        self.signals.job_updated.emit(output_name, "terminated")

    def _mark_complete(self, output_name):
        self.signals.job_finished.emit(output_name)
