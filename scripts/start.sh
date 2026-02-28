#!/bin/bash

# Vlinders-Server 启动脚本

set -e

echo "🚀 Starting Vlinders-Server..."

# 检查 GPU
if ! command -v nvidia-smi &> /dev/null; then
    echo "⚠️  Warning: nvidia-smi not found. GPU may not be available."
else
    echo "✅ GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
fi

# 检查环境变量
if [ -z "$INTERNAL_SECRET" ]; then
    echo "⚠️  Warning: INTERNAL_SECRET not set"
fi

# 检查模型目录
if [ ! -d "./models" ]; then
    echo "⚠️  Warning: ./models directory not found"
    mkdir -p ./models
fi

# 启动服务
echo "🔧 Starting server..."
python -m uvicorn vlinders_server.main:app \
    --host ${SERVER_HOST:-0.0.0.0} \
    --port ${SERVER_PORT:-8000} \
    --workers ${SERVER_WORKERS:-1} \
    --log-level ${LOG_LEVEL:-info}
