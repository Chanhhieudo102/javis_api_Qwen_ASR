import os
import modal
from huggingface_hub import snapshot_download

# Constants
REPO_ID = "Qwen/Qwen3-ASR-1.7B-hf"
MODEL_DIR = "/mnt/VOICE/models"
LOCAL_MODEL_DIR = f"{MODEL_DIR}/Qwen3-ASR-1.7B-hf"

app = modal.App("download-weights")
volume = modal.Volume.from_name("VOICE", create_if_missing=True)

# Define the image with required libraries
image = modal.Image.debian_slim().pip_install("huggingface_hub", "hf_transfer")

@app.function(image=image, volumes={"/mnt/VOICE": volume}, timeout=3600)
def download() -> None:
    """Download the model weights from Hugging Face Hub."""
    # Enable Hugging Face fast transfer
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1" 

    # Ensure target directory exists
    os.makedirs(MODEL_DIR, exist_ok=True)

    print("Downloading model...")
    snapshot_download(
        repo_id=REPO_ID,
        local_dir=LOCAL_MODEL_DIR,
        ignore_patterns=["*.pt", "*.msgpack", "*.bin"] 
    )
    
    # Commit changes to the Modal Volume
    volume.commit()
    print("Download and volume commit completed successfully!")

@app.local_entrypoint()
def main() -> None:
    download.remote()