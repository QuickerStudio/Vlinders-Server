"""
内部 API 端点
"""
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import config
from ..utils import logger
from ..inference import vllm_service


router = APIRouter()


# ==================== 请求/响应模型 ====================

class Message(BaseModel):
    """消息模型"""
    role: str
    content: str


class InternalChatRequest(BaseModel):
    """内部聊天请求"""
    model: str
    messages: List[Message]
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    stop: Optional[List[str]] = None
    stream: bool = False
    user_id: Optional[str] = None


class ChatChoice(BaseModel):
    """聊天选择"""
    index: int = 0
    message: Message
    finish_reason: str


class ChatUsage(BaseModel):
    """Token 使用情况"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class InternalChatResponse(BaseModel):
    """内部聊天响应"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatChoice]
    usage: ChatUsage


class InternalEmbeddingRequest(BaseModel):
    """内部嵌入请求"""
    model: str = "default"
    input: str | List[str]


# ==================== 认证 ====================

def verify_internal_auth(x_internal_auth: str = Header(...)) -> None:
    """验证内部请求认证"""

    if not config.server.internal_secret:
        logger.warning("INTERNAL_SECRET not set, skipping authentication")
        return

    if x_internal_auth != config.server.internal_secret:
        logger.warning("Invalid internal authentication")
        raise HTTPException(status_code=403, detail="Forbidden")


# ==================== API 端点 ====================

@router.post("/chat", response_model=InternalChatResponse)
async def internal_chat(
    request: InternalChatRequest,
    _: None = Depends(verify_internal_auth)
) -> InternalChatResponse:
    """
    内部聊天接口（非流式）

    接收来自 Vlinders-API 的聊天请求，返回模型生成的响应
    """

    logger.info(f"Received chat request: model={request.model}, user={request.user_id}")

    # 构建 prompt（简化版，实际应该使用模型的 chat template）
    prompt = "\n".join([f"{msg.role}: {msg.content}" for msg in request.messages])
    prompt += "\nassistant:"

    try:
        # 调用推理服务
        result = await vllm_service.generate(
            model=request.model,
            prompt=prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            stop=request.stop,
            stream=False
        )

        # 构建响应
        import time
        response = InternalChatResponse(
            id=f"chatcmpl_{uuid.uuid4().hex[:8]}",
            created=int(time.time()),
            model=request.model,
            choices=[
                ChatChoice(
                    message=Message(role="assistant", content=result.text),
                    finish_reason=result.finish_reason
                )
            ],
            usage=ChatUsage(**result.usage)
        )

        logger.info(
            f"Chat request completed: tokens={result.usage['total_tokens']}, "
            f"finish_reason={result.finish_reason}"
        )

        return response

    except ValueError as e:
        logger.error(f"Model not found: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Chat request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def internal_chat_stream(
    request: InternalChatRequest,
    _: None = Depends(verify_internal_auth)
):
    """
    内部聊天接口（流式）

    流式返回模型生成的响应
    """

    logger.info(f"Received streaming chat request: model={request.model}")

    # 构建 prompt
    prompt = "\n".join([f"{msg.role}: {msg.content}" for msg in request.messages])
    prompt += "\nassistant:"

    async def generate():
        """生成流式响应"""
        import json
        import time

        request_id = f"chatcmpl_{uuid.uuid4().hex[:8]}"

        try:
            async for chunk in vllm_service.generate_stream(
                model=request.model,
                prompt=prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                stop=request.stop
            ):
                # 构建 SSE 格式的响应
                data = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": request.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": chunk["text"]},
                        "finish_reason": chunk.get("finish_reason")
                    }]
                }

                yield f"data: {json.dumps(data)}\n\n"

                if chunk.get("done"):
                    break

            # 发送结束标记
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            error_data = {"error": str(e)}
            yield f"data: {json.dumps(error_data)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )


@router.post("/embeddings")
async def internal_embeddings(
    request: InternalEmbeddingRequest,
    _: None = Depends(verify_internal_auth)
):
    """
    内部嵌入接口

    生成文本嵌入向量（暂未实现）
    """

    logger.warning("Embeddings endpoint not yet implemented")
    raise HTTPException(status_code=501, detail="Not implemented")


@router.get("/models")
async def list_models(_: None = Depends(verify_internal_auth)):
    """
    列出已加载的模型
    """

    models = vllm_service.list_models()

    return {
        "object": "list",
        "data": [
            {
                "id": model_name,
                "object": "model",
                "owned_by": "vlinders"
            }
            for model_name in models
        ]
    }
