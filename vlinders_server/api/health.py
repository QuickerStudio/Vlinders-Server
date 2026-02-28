"""
健康检查端点
"""
import torch
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any

from ..inference import vllm_service


router = APIRouter()


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    models_loaded: List[str]
    model_count: int
    gpu_available: bool
    gpu_count: int
    gpu_info: List[Dict[str, Any]]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    健康检查端点

    返回服务状态、已加载模型、GPU 信息等
    """

    # 获取 GPU 信息
    gpu_available = torch.cuda.is_available()
    gpu_count = torch.cuda.device_count() if gpu_available else 0

    gpu_info = []
    if gpu_available:
        for i in range(gpu_count):
            props = torch.cuda.get_device_properties(i)
            allocated = torch.cuda.memory_allocated(i) / 1024**3  # GB
            reserved = torch.cuda.memory_reserved(i) / 1024**3  # GB
            total = props.total_memory / 1024**3  # GB

            gpu_info.append({
                "id": i,
                "name": props.name,
                "memory_allocated_gb": round(allocated, 2),
                "memory_reserved_gb": round(reserved, 2),
                "memory_total_gb": round(total, 2),
                "utilization": round((reserved / total) * 100, 2)
            })

    # 获取模型信息
    models_loaded = vllm_service.list_models()

    return HealthResponse(
        status="healthy",
        models_loaded=models_loaded,
        model_count=len(models_loaded),
        gpu_available=gpu_available,
        gpu_count=gpu_count,
        gpu_info=gpu_info
    )


@router.get("/ready")
async def readiness_check():
    """
    就绪检查端点

    用于 Kubernetes 就绪探针
    """

    models = vllm_service.list_models()

    if not models:
        return {"ready": False, "reason": "No models loaded"}

    return {"ready": True, "models": models}


@router.get("/live")
async def liveness_check():
    """
    存活检查端点

    用于 Kubernetes 存活探针
    """

    return {"alive": True}
