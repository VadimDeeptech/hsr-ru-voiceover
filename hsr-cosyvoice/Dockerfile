# syntax=docker/dockerfile:1
FROM pytorch/pytorch:2.7.1-cuda12.8-cudnn9-devel

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        git ffmpeg sox libsox-dev curl build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone https://github.com/x0152/cosyvoice-tts-api.git server && \
    git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git

WORKDIR /app/CosyVoice

# Зависимости CosyVoice:
# - выкидываем ИНДЕКСЫ из requirements (чужой cu121-индекс подменил нам torch)
# - без torch/torchaudio/tensorrt/deepspeed
# - whisper ставим отдельно через --no-build-isolation (его setup.py требует pkg_resources)
# - В КОНЦЕ принудительно возвращаем согласованную тройку torch/torchaudio/torchvision cu128
RUN --mount=type=cache,target=/root/.cache/pip \
    grep -v -E '^(--extra-index-url|torch|torchaudio|tensorrt|deepspeed|openai-whisper)' requirements.txt > req-filtered.txt && \
    pip install -r req-filtered.txt --extra-index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/ && \
    pip install "huggingface_hub[hf_xet]" fastapi uvicorn python-multipart python-dotenv && \
    pip install "setuptools<81" wheel && \
    pip install --no-build-isolation "openai-whisper==20231117" && \
    pip install --force-reinstall \
        --index-url https://download.pytorch.org/whl/cu128 \
        --extra-index-url https://pypi.org/simple \
        "torch==2.7.1" "torchaudio==2.7.1" "torchvision==0.22.1"

# ФИКС numpy: onnxruntime 1.18 собран под numpy 1.x, а gradio перетянул numpy 2.x
RUN --mount=type=cache,target=/root/.cache/pip pip install "numpy<2"

# ФИКС pkg_resources: lightning (через matcha) импортирует его в рантайме,
# а pip выше не перезаписал setuptools без --force-reinstall
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --force-reinstall --no-deps "setuptools<81"

WORKDIR /app/server

ENV PORT=8020
EXPOSE 8020

CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8020"]