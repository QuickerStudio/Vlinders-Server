"""
vLLM 推理服务核心模块
"""
import uuid
import asyncio
from typing import Dict, Optional, List, AsyncGenerator, Any
from dataclasses import dataclass

from vllm import AsyncLLMEngine, SamplingParams
from vllm.engine.arg_utils import AsyncEngineArgs

from ..utils import logger
from ..config import ModelConfig


@dataclass
class GenerationResult:
    """生成结果"""
    text: str
    finish_reason: str
    usage: Dict[str, int]


class VLLMInferenceService:
    """基于 vLLM 的推理服务"""

    def __init__(self):
        self.engines: Dict[str, AsyncLLMEngine] = {}
        self.model_configs: Dict[str, ModelConfig] = {}
        self._lock = asyncio.Lock()

    async def load_model(
        self,
        model_name: str,
        model_config: ModelConfig
    ) -> None:
        """加载模型到 vLLM"""

        async with self._lock:
            if model_name in self.engines:
                logger.warning(f"Model {model_name} already loaded")
                return

            logger.info(f"Loading model {model_name} from {model_config.path}")

            try:
                # 配置引擎参数
                engine_args = AsyncEngineArgs(
                    model=model_config.path,
                    tensor_parallel_size=model_config.tensor_parallel_size,
                    dtype=model_config.dtype,
                    max_model_len=model_config.max_model_len,
                    gpu_memory_utilization=model_config.gpu_memory_utilization,
                    trust_remote_code=model_config.trust_remote_code,
                    enable_prefix_caching=model_config.enable_prefix_caching,
                    disable_log_stats=False
                )

                # 创建引擎
                engine = AsyncLLMEngine.from_engine_args(engine_args)

                self.engines[model_name] = engine
                self.model_configs[model_name] = model_config

                logger.info(
                    f"✅ Model {model_name} loaded successfully "
                    f"(TP={model_config.tensor_parallel_size}, "
                    f"max_len={model_config.max_model_len})"
                )

            except Exception as e:
                logger.error(f"Failed to load model {model_name}: {e}")
                raise

    async def unload_model(self, model_name: str) -> None:
        """卸载模型"""

        async with self._lock:
            if model_name not in self.engines:
                logger.warning(f"Model {model_name} not loaded")
                return

            logger.info(f"Unloading model {model_name}")

            # vLLM 会自动清理资源
            del self.engines[model_name]
            del self.model_configs[model_name]

            logger.info(f"✅ Model {model_name} unloaded")

    def get_engine(self, model_name: str) -> AsyncLLMEngine:
        """获取模型引擎"""

        engine = self.engines.get(model_name)
        if not engine:
            raise ValueError(f"Model {model_name} not loaded")
        return engine

    def list_models(self) -> List[str]:
        """列出已加载的模型"""
        return list(self.engines.keys())

    async def generate(
        self,
        model: str,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stop: Optional[List[str]] = None,
        stream: bool = False
    ) -> GenerationResult:
        """生成文本（非流式）"""

        engine = self.get_engine(model)

        # 配置采样参数
        sampling_params = SamplingParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop or []
        )

        # 生成请求 ID
        request_id = f"req_{uuid.uuid4().hex[:8]}"

        logger.debug(f"Generating text for request {request_id}")

        # 异步生成
        final_output = None
        async for output in engine.generate(prompt, sampling_params, request_id):
            final_output = output

        # 返回结果
        if final_output and final_output.outputs:
            result = GenerationResult(
                text=final_output.outputs[0].text,
                finish_reason=final_output.outputs[0].finish_reason,
                usage={
                    "prompt_tokens": len(final_output.prompt_token_ids),
                    "completion_tokens": len(final_output.outputs[0].token_ids),
                    "total_tokens": (
                        len(final_output.prompt_token_ids) +
                        len(final_output.outputs[0].token_ids)
                    )
                }
            )

            logger.debug(
                f"Request {request_id} completed: "
                f"{result.usage['total_tokens']} tokens"
            )

            return result

        raise RuntimeError("Generation failed: no output")

    async def generate_stream(
        self,
        model: str,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stop: Optional[List[str]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """生成文本（流式）"""

        engine = self.get_engine(model)

        # 配置采样参数
        sampling_params = SamplingParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop or []
        )

        # 生成请求 ID
        request_id = f"req_{uuid.uuid4().hex[:8]}"

        logger.debug(f"Streaming generation for request {request_id}")

        # 流式生成
        async for output in engine.generate(prompt, sampling_params, request_id):
            if output.outputs:
                yield {
                    "text": output.outputs[0].text,
                    "finish_reason": output.outputs[0].finish_reason,
                    "done": output.finished
                }

        logger.debug(f"Request {request_id} stream completed")

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""

        return {
            "status": "healthy",
            "models_loaded": self.list_models(),
            "model_count": len(self.engines)
        }


# 全局推理服务实例
vllm_service = VLLMInferenceService()
