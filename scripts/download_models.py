#!/usr/bin/env python3
"""
模型下载脚本

使用 Hugging Face Hub 下载模型
"""
import argparse
from huggingface_hub import snapshot_download


def download_model(
    repo_id: str,
    local_dir: str,
    token: str = None
):
    """下载模型"""

    print(f"📥 Downloading model: {repo_id}")
    print(f"📁 Target directory: {local_dir}")

    snapshot_download(
        repo_id=repo_id,
        local_dir=local_dir,
        local_dir_use_symlinks=False,
        token=token
    )

    print(f"✅ Model downloaded successfully to {local_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download models from Hugging Face")
    parser.add_argument("repo_id", help="Model repository ID (e.g., meta-llama/Llama-3-8B)")
    parser.add_argument("--local-dir", required=True, help="Local directory to save model")
    parser.add_argument("--token", help="Hugging Face token (for private models)")

    args = parser.parse_args()

    download_model(
        repo_id=args.repo_id,
        local_dir=args.local_dir,
        token=args.token
    )
