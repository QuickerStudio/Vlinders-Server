"""
配置管理模块
"""
import os
from typing import Dict, List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class ModelConfig(BaseSettings):
    """单个模型配置"""
    name: str
    path: str
    tensor_parallel_size: int = 1
    max_model_len: int = 32768
    gpu_memory_utilization: float = 0.9
    dtype: str = "float16"
    enable_prefix_caching: bool = True
    trust_remote_code: bool = True
    enabled: bool = True


class ServerConfig(BaseSettings):
    """服务器配置"""
    # 服务配置
    host: str = Field(default="0.0.0.0", env="SERVER_HOST")
    port: int = Field(default=8000, env="SERVER_PORT")
    workers: int = Field(default=1, env="SERVER_WORKERS")

    # 内部认证
    internal_secret: str = Field(default="", env="INTERNAL_SECRET")

    # 数据库配置
    redis_url: str = Field(default="redis://localhost:6379", env="REDIS_URL")
    postgres_url: str = Field(default="postgresql://localhost:5432/vlinders", env="POSTGRES_URL")
    qdrant_url: str = Field(default="http://localhost:6333", env="QDRANT_URL")

    # GPU 配置
    cuda_visible_devices: Optional[str] = Field(default=None, env="CUDA_VISIBLE_DEVICES")

    # 日志配置
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class Config:
    """全局配置"""

    def __init__(self):
        self.server = ServerConfig()
        self.models: Dict[str, ModelConfig] = {}

    def load_models_config(self, config_path: str = "configs/models.yaml") -> None:
        """加载模型配置"""
        import yaml

        if not os.path.exists(config_path):
            return

        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        for model_data in data.get('models', []):
            model_config = ModelConfig(**model_data)
            if model_config.enabled:
                self.models[model_config.name] = model_config

    def get_model_config(self, model_name: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        return self.models.get(model_name)


# 全局配置实例
config = Config()
