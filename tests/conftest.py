"""
测试配置
"""
import pytest


@pytest.fixture
def test_config():
    """测试配置 fixture"""
    from vlinders_server.config import Config

    config = Config()
    return config
