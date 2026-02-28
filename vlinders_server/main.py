"""
FastAPI 应用主入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import config
from .utils import logger
from .database import db
from .cache import cache
from .api.health import router as health_router

# 注意: vLLM 推理服务需要在安装完依赖后启用
# from .inference import vllm_service
# from .api.internal import router as internal_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""

    # 启动时
    logger.info("Starting Vlinders-Server...")

    # 连接数据库和缓存
    try:
        await cache.connect()
        logger.info("Cache service connected")
    except Exception as e:
        logger.warning(f"Failed to connect to cache: {e}")

    try:
        await db.connect()
        logger.info("Database connected")
    except Exception as e:
        logger.warning(f"Failed to connect to database: {e}")

    # 加载模型配置
    config.load_models_config()

    # TODO: 在 vLLM 安装完成后启用模型加载
    # for model_name, model_config in config.models.items():
    #     try:
    #         await vllm_service.load_model(model_name, model_config)
    #     except Exception as e:
    #         logger.error(f"Failed to load model {model_name}: {e}")

    logger.info("Vlinders-Server started successfully (vLLM disabled)")

    yield

    # 关闭时
    logger.info("Shutting down Vlinders-Server...")

    # 断开数据库和缓存连接
    await cache.disconnect()
    await db.disconnect()


# 创建 FastAPI 应用
app = FastAPI(
    title="Vlinders-Server",
    description="高性能大模型推理服务 - 基于 vLLM",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 中间件（仅用于内部通信）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
# TODO: 在 vLLM 安装完成后启用内部 API
# app.include_router(internal_router, prefix="/internal", tags=["Internal"])
app.include_router(health_router, tags=["Health"])


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "Vlinders-Server",
        "version": "1.0.0",
        "status": "running"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "vlinders_server.main:app",
        host=config.server.host,
        port=config.server.port,
        workers=config.server.workers,
        log_level=config.server.log_level.lower()
    )
