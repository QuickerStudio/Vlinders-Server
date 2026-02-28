"""
健康检查端点
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Dict, Any

# TODO: 在 vLLM 和 torch 安装完成后启用
# import torch
# from ..inference import vllm_service


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

    # TODO: 在 torch 安装完成后启用 GPU 检测
    gpu_available = False
    gpu_count = 0
    gpu_info = []

    # TODO: 在 vLLM 安装完成后启用模型检测
    models_loaded = []

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

    # TODO: 在 vLLM 安装完成后启用模型检测
    models = []

    if not models:
        return {"ready": False, "reason": "No models loaded (vLLM not installed)"}

    return {"ready": True, "models": models}


@router.get("/live")
async def liveness_check():
    """
    存活检查端点

    用于 Kubernetes 存活探针
    """

    return {"alive": True}
