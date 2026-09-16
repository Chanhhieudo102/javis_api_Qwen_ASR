from pathlib import Path
import modal
from fastapi import FastAPI

# 1. Định nghĩa môi trường (Image) chạy trên Modal
# Khớp với bản v3_03_09 đã chạy thành công: transformers>=4.48.0 + AutoModelForMultimodalLM
# KHÔNG cần qwen-asr (chỉ dành cho bản Qwen3-ASR-1.7B gốc, không phải bản -hf)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "libsndfile1")  # Cần thiết cho librosa/soundfile
    .pip_install(
        "fastapi",
        "uvicorn",
        "pydantic[email]",
        "pydantic-settings",
        "websockets",
        "transformers>=4.48.0",
        "torch",
        "torchaudio",
        "accelerate",
        "silero-vad",
        "numpy",
        "python-jose[cryptography]",
        "passlib[bcrypt]",
        "python-multipart",
        "pyyaml",
        "email-validator",
        "onnxruntime",
        "librosa",
        "soundfile",
    )
    .add_local_dir(".", remote_path="/root")
)

app = modal.App("javis-api-qwen3-hf-serve")

MINUTES = 60
volumes = {
    "/mnt/VOICE": modal.Volume.from_name(name="VOICE", create_if_missing=True)
}

# Secrets: Tắt DB (ENABLE_DB=false) + đọc .env cho QWEN_MODEL_NAME
app_secrets = [
    modal.Secret.from_dict({
        "ENABLE_DB": "false",
    })
]

env_file = Path(".env") if Path(".env").exists() else Path("javis-api-qwen3-hf/.env")
if env_file.exists():
    app_secrets.append(modal.Secret.from_dotenv(str(env_file)))

@app.function(
    image=image,
    gpu="A10G",  # GPU A10G (24GB VRAM)
    scaledown_window=15 * MINUTES,
    timeout=10 * MINUTES,
    volumes=volumes,
    secrets=app_secrets,
)
@modal.concurrent(max_inputs=32)
@modal.asgi_app()
def serve() -> FastAPI:
    import sys
    import os
    
    # Chỉ định đường dẫn tới thư mục chứa module `app`
    sys.path.insert(0, "/root/javis-api-qwen3-hf")
    sys.path.insert(0, "/root")
    
    # Import FastAPI instance từ file main.py của dự án
    from app.main import app as fastapi_app
    
    return fastapi_app
