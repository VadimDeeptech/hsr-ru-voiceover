#!/usr/bin/env python3
"""Скачивает модель Fun-CosyVoice3-0.5B с HuggingFace в указанную директорию.

Использование:
    python download_model.py [target_dir]
По умолчанию: ./models/Fun-CosyVoice3-0.5B
"""
import os
import sys

from huggingface_hub import snapshot_download

MODEL_ID = "FunAudioLLM/Fun-CosyVoice3-0.5B"
TARGET_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "models", "Fun-CosyVoice3-0.5B"
)

os.makedirs(TARGET_DIR, exist_ok=True)

print(f"Downloading {MODEL_ID} to {TARGET_DIR} ...")
path = snapshot_download(repo_id=MODEL_ID, local_dir=TARGET_DIR)
print(f"Done: {path}")
