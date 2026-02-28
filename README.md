# Vlinders-Server 设计文档

**版本**: v1.0
**最后更新**: 2026-02-28
**状态**: 📝 设计阶段

---

## 📋 概述

Vlinders-Server 是服务器端的推理和管理框架，基于 vLLM 提供高性能的大模型推理能力，并实现 Agent 编排、工具执行、代码分析等核心功能。

### 核心定位

> **推理层 + Agent 编排引擎**
>
> 不直接面向用户，只接受来自 Vlinders-API 的内部请求

### 技术栈

```yaml
核心框架:
  - Python 3.11+
  - vLLM (大模型推理)
  - FastAPI (HTTP 服务)
  - gRPC (高性能内部通信)

代码分析:
  - Tree-sitter (语法解析)
  - Pygments (语法高亮)

向量搜索:
  - Qdrant (向量数据库)
  - sentence-transformers (嵌入生成)

缓存和队列:
  - Redis (缓存、任务队列)
  - Celery (异步任务)

数据库:
  - PostgreSQL (元数据、日志)

监控:
  - Prometheus (指标)
  - Grafana (可视化)
  - OpenTelemetry (追踪)
```

---

## 🏗️ 架构设计

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Vlinders-Server                               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              API Gateway (FastAPI)                      │    │
│  │  - /internal/chat                                       │    │
│  │  - /internal/agent                                      │    │
│  │  - /internal/tools                                      │    │
│  │  - /internal/embeddings                                 │    │
│  └────────────────────────────────────────────────────────┘    │
│                           ↓                                      │
│  ┌────────────────────────────────────────────────────────┐    │
│  │           Agent Orchestrator (核心)                     │    │
│  │  - Agent 生命周期管理                                   │    │
│  │  - 工具调用循环                                         │    │
│  │  - 子 Agent 并行执行                                    │    │
│  │  - 上下文管理                                           │    │
│  └────────────────────────────────────────────────────────┘    │
│         ↓              ↓              ↓              ↓          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  vLLM    │  │  Tool    │  │  Code    │  │ Context  │      │
│  │ Inference│  │ Executor │  │ Analysis │  │ Manager  │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
│         ↓              ↓              ↓              ↓          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  GPU     │  │ Sandbox  │  │Tree-sitter│ │  Redis   │      │
│  │ Cluster  │  │          │  │          │  │          │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              Knowledge Base                             │    │
│  │  - Qdrant (向量数据库)                                  │    │
│  │  - PostgreSQL (元数据)                                  │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 目录结构

```
Vlinders-Server/
├── README.md                          # 项目说明
├── docs/                              # 文档
│   ├── architecture.md                # 架构设计
│   ├── vllm-setup.md                  # vLLM 配置指南
│   ├── agent-system.md                # Agent 系统设计
│   └── deployment.md                  # 部署指南
├── requirements.txt                   # Python 依赖
├── pyproject.toml                     # 项目配置
├── docker-compose.yml                 # Docker 编排
├── Dockerfile                         # Docker 镜像
│
├── vlinders_server/                   # 主代码目录
│   ├── __init__.py
│   ├── main.py                        # 入口文件
│   ├── config.py                      # 配置管理
│   │
│   ├── api/                           # API 层
│   │   ├── __init__.py
│   │   ├── internal.py                # 内部 API 端点
│   │   ├── health.py                  # 健康检查
│   │   └── middleware.py              # 中间件
│   │
│   ├── inference/                     # 推理层
│   │   ├── __init__.py
│   │   ├── vllm_service.py            # vLLM 推理服务
│   │   ├── model_manager.py           # 模型管理
│   │   ├── prompt_builder.py          # Prompt 构建
│   │   └── streaming.py               # 流式响应处理
│   │
│   ├── agent/                         # Agent 层
│   │   ├── __init__.py
│   │   ├── orchestrator.py            # Agent 编排器
│   │   ├── tool_calling_loop.py       # 工具调用循环
│   │   ├── agent_types.py             # Agent 类型定义
│   │   ├── subagent_executor.py       # 子 Agent 执行器
│   │   └── hooks.py                   # Hook 系统
│   │
│   ├── tools/                         # 工具层
│   │   ├── __init__.py
│   │   ├── executor.py                # 工具执行器
│   │   ├── registry.py                # 工具注册表
│   │   ├── sandbox.py                 # 沙箱环境
│   │   └── builtin/                   # 内置工具
│   │       ├── code_search.py
│   │       ├── semantic_search.py
│   │       ├── file_operations.py
│   │       └── web_search.py
│   │
│   ├── code_analysis/                 # 代码分析层
│   │   ├── __init__.py
│   │   ├── parser.py                  # Tree-sitter 解析器
│   │   ├── symbol_extractor.py        # 符号提取
│   │   ├── dependency_analyzer.py     # 依赖分析
│   │   └── embeddings.py              # 代码嵌入
│   │
│   ├── context/                       # 上下文管理层
│   │   ├── __init__.py
│   │   ├── manager.py                 # 上下文管理器
│   │   ├── compressor.py              # 对话压缩
│   │   ├── memory.py                  # Memory 服务
│   │   └── cache.py                   # 缓存管理
│   │
│   ├── knowledge/                     # 知识库层
│   │   ├── __init__.py
│   │   ├── vector_store.py            # 向量存储
│   │   ├── indexer.py                 # 索引器
│   │   └── retriever.py               # 检索器
│   │
│   └── utils/                         # 工具类
│       ├── __init__.py
│       ├── logger.py                  # 日志
│       ├── metrics.py                 # 指标
│       └── errors.py                  # 错误处理
│
├── tests/                             # 测试
│   ├── unit/
│   ├── integration/
│   └── performance/
│
├── scripts/                           # 脚本
│   ├── setup_vllm.sh                  # vLLM 安装脚本
│   ├── download_models.py             # 模型下载
│   └── benchmark.py                   # 性能测试
│
└── configs/                           # 配置文件
    ├── models.yaml                    # 模型配置
    ├── agents.yaml                    # Agent 配置
    └── tools.yaml                     # 工具配置
```

---

## 🚀 核心模块设计

### 1. vLLM 推理服务

**文件**: `vlinders_server/inference/vllm_service.py`

**职责**:
- 加载和管理多个模型
- 提供高性能推理接口
- 支持流式和非流式生成
- GPU 资源管理

**关键特性**:
- 多 GPU 并行（Tensor Parallelism）
- 连续批处理（Continuous Batching）
- PagedAttention 优化
- 动态批处理

**示例代码**:
```python
from vllm import AsyncLLMEngine, SamplingParams
from vllm.engine.arg_utils import AsyncEngineArgs

class VLLMInferenceService:
    """基于 vLLM 的推理服务"""

    def __init__(self):
        self.engines: Dict[str, AsyncLLMEngine] = {}
        self.model_configs: Dict[str, ModelConfig] = {}

    async def load_model(
        self,
        model_name: str,
        model_path: str,
        tensor_parallel_size: int = 1,
        max_model_len: int = 32768,
        gpu_memory_utilization: float = 0.9
    ):
        """加载模型到 vLLM"""

        engine_args = AsyncEngineArgs(
            model=model_path,
            tensor_parallel_size=tensor_parallel_size,
            dtype="float16",
            max_model_len=max_model_len,
            gpu_memory_utilization=gpu_memory_utilization,
            trust_remote_code=True,
            enable_prefix_caching=True  # 启用前缀缓存
        )

        engine = AsyncLLMEngine.from_engine_args(engine_args)
        self.engines[model_name] = engine

        self.model_configs[model_name] = ModelConfig(
            name=model_name,
            path=model_path,
            max_tokens=max_model_len,
            tensor_parallel_size=tensor_parallel_size
        )

        logger.info(f"Model {model_name} loaded successfully")

    async def generate(
        self,
        model: str,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stream: bool = False,
        stop: Optional[List[str]] = None
    ):
        """生成文本"""

        engine = self.engines.get(model)
        if not engine:
            raise ValueError(f"Model {model} not loaded")

        sampling_params = SamplingParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=stop
        )

        request_id = f"req_{uuid.uuid4().hex[:8]}"

        if stream:
            # 流式生成
            async for output in engine.generate(
                prompt,
                sampling_params,
                request_id
            ):
                if output.outputs:
                    yield {
                        'text': output.outputs[0].text,
                        'finish_reason': output.outputs[0].finish_reason
                    }
        else:
            # 非流式生成
            final_output = None
            async for output in engine.generate(
                prompt,
                sampling_params,
                request_id
            ):
                final_output = output

            if final_output and final_output.outputs:
                return {
                    'text': final_output.outputs[0].text,
                    'finish_reason': final_output.outputs[0].finish_reason,
                    'usage': {
                        'prompt_tokens': len(final_output.prompt_token_ids),
                        'completion_tokens': len(final_output.outputs[0].token_ids),
                        'total_tokens': len(final_output.prompt_token_ids) + len(final_output.outputs[0].token_ids)
                    }
                }
```

---

### 2. Agent 编排器

**文件**: `vlinders_server/agent/orchestrator.py`

**职责**:
- 管理 Agent 生命周期
- 协调主 Agent 和子 Agent
- 执行工具调用循环
- 处理并行执行

**示例代码**:
```python
class AgentOrchestrator:
    """Agent 编排器"""

    def __init__(
        self,
        inference_service: VLLMInferenceService,
        tool_executor: ToolExecutor,
        context_manager: ContextManager,
        code_analyzer: CodeAnalysisEngine
    ):
        self.inference = inference_service
        self.tools = tool_executor
        self.context = context_manager
        self.code_analyzer = code_analyzer

    async def run_agent(
        self,
        agent_type: str,
        instruction: str,
        context: Dict[str, Any],
        config: Optional[AgentConfig] = None
    ) -> AgentResult:
        """运行 Agent"""

        # 1. 创建 Agent 上下文
        agent_context = await self.context.create_context(
            agent_type=agent_type,
            instruction=instruction,
            workspace=context.get('workspace'),
            history=context.get('history', []),
            tools=context.get('tools', [])
        )

        # 2. 选择模型
        model = self._select_model(agent_type, config)

        # 3. 执行工具调用循环
        loop_result = await self._run_tool_calling_loop(
            agent_context=agent_context,
            model=model,
            max_iterations=config.max_iterations if config else 10
        )

        # 4. 处理子 Agent 调用
        if loop_result.subagent_calls:
            subagent_results = await self._execute_subagents_parallel(
                loop_result.subagent_calls,
                agent_context
            )
            loop_result.merge_subagent_results(subagent_results)

        # 5. 压缩上下文（如果需要）
        if agent_context.should_compress():
            await self.context.compress_background(agent_context)

        return AgentResult(
            response=loop_result.final_response,
            tool_calls=loop_result.tool_calls,
            iterations=loop_result.iterations,
            usage=loop_result.usage
        )

    async def _run_tool_calling_loop(
        self,
        agent_context: AgentContext,
        model: str,
        max_iterations: int
    ) -> ToolCallingLoopResult:
        """执行工具调用循环"""

        iteration = 0
        tool_call_rounds = []

        while iteration < max_iterations:
            # 1. 构建 Prompt
            prompt = await self._build_prompt(
                agent_context,
                tool_call_rounds
            )

            # 2. 调用模型
            response = await self.inference.generate(
                model=model,
                prompt=prompt,
                max_tokens=4096,
                temperature=0.7,
                stream=False
            )

            # 3. 解析工具调用
            tool_calls = self._parse_tool_calls(response['text'])

            if not tool_calls:
                # 没有工具调用，结束循环
                break

            # 4. 执行工具（并行）
            tool_results = await self.tools.execute_batch(tool_calls)

            # 5. 记录本轮
            tool_call_rounds.append({
                'iteration': iteration,
                'tool_calls': tool_calls,
                'tool_results': tool_results,
                'response': response['text']
            })

            # 6. 更新上下文
            agent_context.add_tool_round(tool_call_rounds[-1])

            iteration += 1

        return ToolCallingLoopResult(
            final_response=response['text'],
            tool_calls=tool_call_rounds,
            iterations=iteration,
            usage=response.get('usage', {})
        )

    async def _execute_subagents_parallel(
        self,
        subagent_calls: List[SubagentCall],
        parent_context: AgentContext
    ) -> List[SubagentResult]:
        """并行执行多个子 Agent"""

        tasks = [
            self.run_agent(
                agent_type=call.agent_type,
                instruction=call.instruction,
                context={
                    'workspace': parent_context.workspace,
                    'parent_agent_id': parent_context.agent_id
                }
            )
            for call in subagent_calls
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [
            SubagentResult(
                agent_type=call.agent_type,
                result=result if not isinstance(result, Exception) else None,
                error=str(result) if isinstance(result, Exception) else None
            )
            for call, result in zip(subagent_calls, results)
        ]
```

---

### 3. 工具执行器

**文件**: `vlinders_server/tools/executor.py`

**职责**:
- 执行工具调用
- 沙箱隔离
- 并行执行
- 错误处理

**示例代码**:
```python
class ToolExecutor:
    """工具执行器"""

    def __init__(self, sandbox: Sandbox):
        self.tools: Dict[str, Tool] = {}
        self.sandbox = sandbox
        self.register_builtin_tools()

    def register_builtin_tools(self):
        """注册内置工具"""
        from .builtin import (
            CodeSearchTool,
            SemanticSearchTool,
            FileOperationsTool,
            WebSearchTool
        )

        self.tools['search_code'] = CodeSearchTool()
        self.tools['semantic_search'] = SemanticSearchTool()
        self.tools['read_file'] = FileOperationsTool()
        self.tools['web_search'] = WebSearchTool()

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Optional[ExecutionContext] = None
    ) -> ToolResult:
        """执行单个工具"""

        tool = self.tools.get(tool_name)
        if not tool:
            raise ToolNotFoundError(f"Tool {tool_name} not found")

        # 1. 验证参数
        validated_args = tool.validate_arguments(arguments)

        # 2. 检查权限
        if context and not self._check_permission(tool, context):
            raise PermissionError(f"Not allowed to use {tool_name}")

        # 3. 在沙箱中执行
        try:
            result = await self.sandbox.execute(
                tool=tool,
                arguments=validated_args,
                timeout=tool.timeout,
                resource_limits=tool.resource_limits
            )

            return ToolResult(
                tool_name=tool_name,
                success=True,
                result=result,
                duration=result.duration
            )

        except Exception as e:
            logger.error(f"Tool {tool_name} execution failed: {e}")
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=str(e)
            )

    async def execute_batch(
        self,
        tool_calls: List[ToolCall],
        context: Optional[ExecutionContext] = None
    ) -> List[ToolResult]:
        """批量执行工具（并行）"""

        tasks = [
            self.execute(call.name, call.arguments, context)
            for call in tool_calls
        ]

        return await asyncio.gather(*tasks, return_exceptions=True)
```

---

## 📡 内部 API 设计

**文件**: `vlinders_server/api/internal.py`

```python
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import StreamingResponse

app = FastAPI(title="Vlinders-Server Internal API")

# 内部认证
INTERNAL_SECRET = os.getenv('INTERNAL_SECRET')

def verify_internal_auth(x_internal_auth: str = Header(...)):
    """验证内部请求"""
    if x_internal_auth != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

@app.post("/internal/chat")
async def internal_chat(
    request: InternalChatRequest,
    auth: str = Depends(verify_internal_auth)
):
    """内部聊天接口"""

    # 运行 Agent
    result = await agent_orchestrator.run_agent(
        agent_type='chat',
        instruction=request.messages[-1]['content'],
        context={
            'messages': request.messages,
            'tools': request.tools,
            'user_id': request.user_id
        }
    )

    # 返回结果
    return {
        'id': f"chatcmpl_{uuid.uuid4().hex[:8]}",
        'model': request.model,
        'choices': [{
            'message': {
                'role': 'assistant',
                'content': result.response
            },
            'finish_reason': 'stop'
        }],
        'usage': result.usage
    }

@app.post("/internal/chat/stream")
async def internal_chat_stream(
    request: InternalChatRequest,
    auth: str = Depends(verify_internal_auth)
):
    """内部聊天接口（流式）"""

    async def generate():
        async for chunk in agent_orchestrator.run_agent_stream(
            agent_type='chat',
            instruction=request.messages[-1]['content'],
            context={
                'messages': request.messages,
                'tools': request.tools
            }
        ):
            yield f"data: {json.dumps(chunk)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream"
    )

@app.post("/internal/agent")
async def internal_agent(
    request: InternalAgentRequest,
    auth: str = Depends(verify_internal_auth)
):
    """内部 Agent 接口"""

    result = await agent_orchestrator.run_agent(
        agent_type=request.agent_type,
        instruction=request.instruction,
        context=request.context,
        config=request.config
    )

    return {
        'agent_id': result.agent_id,
        'response': result.response,
        'tool_calls': result.tool_calls,
        'iterations': result.iterations,
        'usage': result.usage
    }

@app.post("/internal/tools/execute")
async def internal_tool_execute(
    request: InternalToolRequest,
    auth: str = Depends(verify_internal_auth)
):
    """内部工具执行接口"""

    result = await tool_executor.execute(
        tool_name=request.tool_name,
        arguments=request.arguments
    )

    return {
        'success': result.success,
        'result': result.result,
        'error': result.error,
        'duration': result.duration
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        'status': 'healthy',
        'models_loaded': list(vllm_service.engines.keys()),
        'gpu_available': torch.cuda.is_available(),
        'gpu_count': torch.cuda.device_count()
    }
```

---

## 🔧 配置管理

**文件**: `configs/models.yaml`

```yaml
models:
  - name: vlinders-gpt-4
    path: /models/llama-3-70b
    tensor_parallel_size: 4
    max_model_len: 32768
    gpu_memory_utilization: 0.9
    enabled: true

  - name: vlinders-gpt-3.5
    path: /models/llama-3-8b
    tensor_parallel_size: 1
    max_model_len: 16384
    gpu_memory_utilization: 0.8
    enabled: true

  - name: vlinders-code
    path: /models/codellama-34b
    tensor_parallel_size: 2
    max_model_len: 16384
    gpu_memory_utilization: 0.85
    enabled: true
```

**文件**: `configs/agents.yaml`

```yaml
agents:
  plan:
    model: vlinders-gpt-4
    max_iterations: 5
    tools:
      - search_code
      - read_file
      - semantic_search
    subagents:
      - explore

  explore:
    model: vlinders-gpt-3.5  # 使用小模型
    max_iterations: 3
    tools:
      - search_code
      - read_file

  edit:
    model: vlinders-gpt-4
    max_iterations: 10
    tools:
      - search_code
      - read_file
      - edit_file
      - run_test
```

---

## 🚀 部署方案

### Docker Compose

**文件**: `docker-compose.yml`

```yaml
version: '3.8'

services:
  vlinders-server:
    build: .
    ports:
      - "8000:8000"
    environment:
      - INTERNAL_SECRET=${INTERNAL_SECRET}
      - REDIS_URL=redis://redis:6379
      - POSTGRES_URL=postgresql://postgres:password@postgres:5432/vlinders
      - QDRANT_URL=http://qdrant:6333
    volumes:
      - ./models:/models
      - ./data:/data
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 4
              capabilities: [gpu]

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  postgres:
    image: postgres:15-alpine
    environment:
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=vlinders
    volumes:
      - postgres_data:/var/lib/postgresql/data

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  postgres_data:
  qdrant_data:
```

---

## 📊 性能指标

### 目标性能

| 指标 | 目标值 |
|------|--------|
| 首 Token 延迟 (TTFT) | < 500ms |
| Token 生成速度 | > 50 tokens/s |
| 并发请求数 | > 100 |
| GPU 利用率 | > 80% |
| 内存使用 | < 90% |

---

## 📝 下一步

1. ✅ 实现 vLLM 推理服务
2. ✅ 实现 Agent 编排器
3. ✅ 实现工具执行器
4. ✅ 实现代码分析引擎
5. ✅ 部署和测试

---

**状态**: 📝 设计完成
**下一步**: 开始实施
