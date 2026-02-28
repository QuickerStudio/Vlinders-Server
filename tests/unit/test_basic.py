"""
简单的单元测试示例
"""
import pytest
from vlinders_server.config import Config, ModelConfig


def test_config_initialization():
    """测试配置初始化"""
    config = Config()
    assert config.server is not None
    assert isinstance(config.models, dict)


def test_model_config():
    """测试模型配置"""
    model_config = ModelConfig(
        name="test-model",
        path="/path/to/model",
        tensor_parallel_size=1,
        max_model_len=2048
    )

    assert model_config.name == "test-model"
    assert model_config.tensor_parallel_size == 1
    assert model_config.enabled is True


@pytest.mark.asyncio
async def test_vllm_service_initialization():
    """测试 vLLM 服务初始化"""
    from vlinders_server.inference import VLLMInferenceService

    service = VLLMInferenceService()
    assert service.engines == {}
    assert service.model_configs == {}
