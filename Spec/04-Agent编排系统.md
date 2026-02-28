# Agent 编排系统设计

**版本**: v1.0
**最后更新**: 2026-02-28
**文档类型**: 系统设计
**依赖文档**: [01-架构设计.md](./01-架构设计.md)

---

## 📋 文档概述

本文档详细描述 Vlinders-Server 的 Agent 编排系统设计，包括 Agent 生命周期管理、工具调用循环、子 Agent 并行执行、上下文管理等核心功能。

---

## 🎯 系统定位

### 核心职责

> **Agent 编排引擎 - Vlinders-Server 的大脑**
>
> Agent Orchestrator 是整个推理服务的核心，负责协调所有 AI 相关的复杂逻辑。

### 设计目标

1. **智能编排** - 自动管理 Agent 生命周期，支持复杂任务分解
2. **高效执行** - 工具并行调用，子 Agent 并行执行
3. **上下文管理** - 智能压缩，节省 Token 成本
4. **可扩展性** - 支持自定义 Agent 类型和工具

---

## 🏗️ 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              Agent Registry                             │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐│    │
│  │  │   Plan   │  │ Explore  │  │   Edit   │  │ Search ││    │
│  │  │  Agent   │  │  Agent   │  │  Agent   │  │ Agent  ││    │
│  │  └──────────┘  └──────────┘  └──────────┘  └────────┘│    │
│  └────────────────────────────────────────────────────────┘    │
│                           ↓                                      │
│  ┌────────────────────────────────────────────────────────┐    │
│  │           Tool Calling Loop Engine                      │    │
│  │  ┌──────────────────────────────────────────────────┐  │    │
│  │  │  1. Build Prompt                                 │  │    │
│  │  │  2. Call vLLM                                    │  │    │
│  │  │  3. Parse Response                               │  │    │
│  │  │  4. Extract Tool Calls                           │  │    │
│  │  │  5. Execute Tools (Parallel)                     │  │    │
│  │  │  6. Collect Results                              │  │    │
│  │  │  7. Update Context                               │  │    │
│  │  │  8. Check Continue → Loop or Return              │  │    │
│  │  └──────────────────────────────────────────────────┘  │    │
│  └────────────────────────────────────────────────────────┘    │
│         ↓              ↓              ↓              ↓          │
│  ┌────────────────────────────────────────────────────────┐    │
│  │           Sub-Agent Executor                            │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐             │    │
│  │  │ Agent 1  │  │ Agent 2  │  │ Agent N  │             │    │
│  │  │ (Async)  │  │ (Async)  │  │ (Async)  │             │    │
│  │  └──────────┘  └──────────┘  └──────────┘             │    │
│  └────────────────────────────────────────────────────────┘    │
│                           ↓                                      │
│  ┌────────────────────────────────────────────────────────┐    │
│  │           Context Manager                               │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐             │    │
│  │  │ History  │  │Compress  │  │  Token   │             │    │
│  │  │ Manager  │  │  Engine  │  │  Budget  │             │    │
│  │  └──────────┘  └──────────┘  └──────────┘             │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🔧 核心组件设计

### 1. Agent Orchestrator（编排器）

**职责**: Agent 生命周期管理和任务编排

**核心代码**:

```python
from typing import Dict, Any, List, Optional, AsyncIterator
from dataclasses import dataclass
from enum import Enum
import asyncio
import uuid


class AgentType(Enum):
    """Agent 类型枚举"""
    PLAN = "plan"          # 规划型 Agent
    EXPLORE = "explore"    # 探索型 Agent
    EDIT = "edit"          # 编辑型 Agent
    SEARCH = "search"      # 搜索型 Agent
    CUSTOM = "custom"      # 自定义 Agent


@dataclass
class AgentConfig:
    """Agent 配置"""
    max_iterations: int = 10           # 最大迭代次数
    max_tokens: int = 100000           # Token 预算
    temperature: float = 0.7           # 生成温度
    parallel_tools: bool = True        # 是否并行执行工具
    enable_sub_agents: bool = True     # 是否启用子 Agent
    compression_threshold: float = 0.75  # 压缩阈值（Token 使用率）
    timeout: int = 300                 # 超时时间（秒）


@dataclass
class AgentContext:
    """Agent 上下文"""
    agent_id: str
    agent_type: AgentType
    instruction: str
    workspace: str
    history: List[Dict[str, Any]]
    tools: List[str]
    token_used: int = 0
    iteration: int = 0
    metadata: Dict[str, Any] = None


@dataclass
class AgentResult:
    """Agent 执行结果"""
    agent_id: str
    success: bool
    response: str
    tool_calls: List[Dict[str, Any]]
    iterations: int
    tokens_used: int
    duration_ms: int
    sub_agents: List[str] = None
    error: Optional[str] = None


class AgentOrchestrator:
    """
    Agent 编排器 - 核心业务逻辑

    职责:
    1. 管理 Agent 生命周期
    2. 执行工具调用循环
    3. 协调子 Agent 并行执行
    4. 管理对话上下文
    """

    def __init__(
        self,
        inference_service,      # VLLMInferenceService
        tool_executor,          # ToolExecutor
        context_manager,        # ContextManager
        code_analyzer           # CodeAnalysisEngine
    ):
        self.inference = inference_service
        self.tools = tool_executor
        self.context = context_manager
        self.code_analyzer = code_analyzer
        self.agent_registry = AgentRegistry()
        self.active_agents: Dict[str, AgentContext] = {}

    async def run_agent(
        self,
        agent_type: str,
        instruction: str,
        workspace: str,
        history: List[Dict[str, Any]] = None,
        config: Optional[AgentConfig] = None
    ) -> AgentResult:
        """
        运行 Agent 的主入口

        Args:
            agent_type: Agent 类型 (plan/explore/edit/search)
            instruction: 用户指令
            workspace: 工作空间路径
            history: 对话历史
            config: Agent 配置

        Returns:
            AgentResult: Agent 执行结果
        """
        # 1. 初始化配置
        config = config or AgentConfig()
        agent_id = str(uuid.uuid4())
        start_time = asyncio.get_event_loop().time()

        # 2. 创建 Agent 上下文
        context = await self.context.create_context(
            agent_id=agent_id,
            agent_type=AgentType(agent_type),
            instruction=instruction,
            workspace=workspace,
            history=history or []
        )

        # 3. 注册 Agent
        self.active_agents[agent_id] = context

        try:
            # 4. 获取 Agent 实例
            agent = self.agent_registry.get_agent(agent_type)

            # 5. 执行工具调用循环
            result = await self._tool_calling_loop(
                agent=agent,
                context=context,
                config=config
            )

            # 6. 计算执行时间
            duration_ms = int(
                (asyncio.get_event_loop().time() - start_time) * 1000
            )

            # 7. 返回结果
            return AgentResult(
                agent_id=agent_id,
                success=True,
                response=result["response"],
                tool_calls=result["tool_calls"],
                iterations=context.iteration,
                tokens_used=context.token_used,
                duration_ms=duration_ms,
                sub_agents=result.get("sub_agents")
            )

        except Exception as e:
            # 错误处理
            duration_ms = int(
                (asyncio.get_event_loop().time() - start_time) * 1000
            )
            return AgentResult(
                agent_id=agent_id,
                success=False,
                response="",
                tool_calls=[],
                iterations=context.iteration,
                tokens_used=context.token_used,
                duration_ms=duration_ms,
                error=str(e)
            )

        finally:
            # 8. 清理资源
            del self.active_agents[agent_id]
```

---

### 2. Tool Calling Loop（工具调用循环）

**核心逻辑**: 迭代执行工具调用，直到任务完成

**流程图**:

```
┌─────────────────────────────────────────────────────────┐
│              Tool Calling Loop                          │
│                                                         │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 1. 构建 Prompt                                  │  │
│  │    - 系统指令                                   │  │
│  │    - 对话历史                                   │  │
│  │    - 可用工具列表                               │  │
│  │    - 当前指令                                   │  │
│  └─────────────────────────────────────────────────┘  │
│                     ↓                                   │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 2. 调用 vLLM 推理                               │  │
│  │    - 选择模型                                   │  │
│  │    - 生成响应                                   │  │
│  │    - 流式输出（可选）                           │  │
│  └─────────────────────────────────────────────────┘  │
│                     ↓                                   │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 3. 解析响应                                     │  │
│  │    - 提取文本内容                               │  │
│  │    - 提取工具调用                               │  │
│  │    - 提取子 Agent 调用                          │  │
│  └─────────────────────────────────────────────────┘  │
│                     ↓                                   │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 4. 判断是否有工具调用                           │  │
│  │    - 无 → 返回最终结果                          │  │
│  │    - 有 → 继续执行                              │  │
│  └─────────────────────────────────────────────────┘  │
│                     ↓                                   │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 5. 并行执行工具                                 │  │
│  │    - asyncio.gather()                           │  │
│  │    - 沙箱隔离                                   │  │
│  │    - 超时控制                                   │  │
│  └─────────────────────────────────────────────────┘  │
│                     ↓                                   │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 6. 收集工具结果                                 │  │
│  │    - 成功结果                                   │  │
│  │    - 错误信息                                   │  │
│  │    - 执行时间                                   │  │
│  └─────────────────────────────────────────────────┘  │
│                     ↓                                   │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 7. 更新上下文                                   │  │
│  │    - 添加工具调用到历史                         │  │
│  │    - 添加工具结果到历史                         │  │
│  │    - 更新 Token 计数                            │  │
│  └─────────────────────────────────────────────────┘  │
│                     ↓                                   │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 8. 检查继续条件                                 │  │
│  │    - 迭代次数 < max_iterations                  │  │
│  │    - Token 使用 < max_tokens                    │  │
│  │    - 未超时                                     │  │
│  │    - 有工具调用                                 │  │
│  └─────────────────────────────────────────────────┘  │
│                     ↓                                   │
│  ┌─────────────────────────────────────────────────┐  │
│  │ 9. 判断是否需要压缩上下文                       │  │
│  │    - Token 使用率 >= 75% → 后台压缩             │  │
│  └─────────────────────────────────────────────────┘  │
│                     ↓                                   │
│              回到步骤 1 或 返回结果                     │
└─────────────────────────────────────────────────────────┘
```

**实现代码**:

```python
async def _tool_calling_loop(
    self,
    agent,
    context: AgentContext,
    config: AgentConfig
) -> Dict[str, Any]:
    """
    工具调用循环

    Args:
        agent: Agent 实例
        context: Agent 上下文
        config: Agent 配置

    Returns:
        Dict: 包含 response, tool_calls, sub_agents
    """
    all_tool_calls = []
    sub_agents = []
    final_response = ""

    while context.iteration < config.max_iterations:
        context.iteration += 1

        # 1. 构建 Prompt
        prompt = await self._build_prompt(agent, context)

        # 2. 调用 vLLM 推理
        response = await self.inference.generate(
            model=agent.model_name,
            prompt=prompt,
            temperature=config.temperature,
            max_tokens=config.max_tokens - context.token_used
        )

        # 3. 解析响应
        parsed = self._parse_response(response)
        final_response = parsed["content"]
        tool_calls = parsed["tool_calls"]
        sub_agent_calls = parsed["sub_agents"]

        # 4. 更新 Token 计数
        context.token_used += response.usage.total_tokens

        # 5. 添加 Assistant 消息到历史
        context.history.append({
            "role": "assistant",
            "content": final_response,
            "tool_calls": tool_calls
        })

        # 6. 如果没有工具调用，结束循环
        if not tool_calls and not sub_agent_calls:
            break

        # 7. 执行工具调用
        if tool_calls:
            tool_results = await self._execute_tools(
                tool_calls=tool_calls,
                config=config
            )
            all_tool_calls.extend(tool_calls)

            # 8. 添加工具结果到历史
            context.history.append({
                "role": "tool",
                "tool_calls": tool_calls,
                "results": tool_results
            })

        # 9. 执行子 Agent 调用
        if sub_agent_calls and config.enable_sub_agents:
            sub_agent_results = await self._execute_sub_agents(
                sub_agent_calls=sub_agent_calls,
                parent_context=context,
                config=config
            )
            sub_agents.extend([sa["agent_id"] for sa in sub_agent_results])

            # 10. 添加子 Agent 结果到历史
            context.history.append({
                "role": "sub_agent",
                "results": sub_agent_results
            })

        # 11. 检查是否需要压缩上下文
        if self.context.should_compress(context, config):
            await self.context.compress_background(context)

        # 12. 检查 Token 预算
        if context.token_used >= config.max_tokens:
            break

    return {
        "response": final_response,
        "tool_calls": all_tool_calls,
        "sub_agents": sub_agents
    }
```

---

### 3. Tool Executor（工具执行器）

**职责**: 并行执行工具，沙箱隔离

**实现代码**:

```python
async def _execute_tools(
    self,
    tool_calls: List[Dict[str, Any]],
    config: AgentConfig
) -> List[Dict[str, Any]]:
    """
    并行执行工具

    Args:
        tool_calls: 工具调用列表
        config: Agent 配置

    Returns:
        List[Dict]: 工具执行结果列表
    """
    if config.parallel_tools:
        # 并行执行
        tasks = [
            self.tools.execute(
                tool_name=call["name"],
                arguments=call["arguments"]
            )
            for call in tool_calls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    else:
        # 串行执行
        results = []
        for call in tool_calls:
            result = await self.tools.execute(
                tool_name=call["name"],
                arguments=call["arguments"]
            )
            results.append(result)

    # 格式化结果
    formatted_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            formatted_results.append({
                "tool_call_id": tool_calls[i]["id"],
                "success": False,
                "error": str(result)
            })
        else:
            formatted_results.append({
                "tool_call_id": tool_calls[i]["id"],
                "success": True,
                "result": result.output,
                "duration_ms": result.duration_ms
            })

    return formatted_results
```

---

### 4. Sub-Agent Executor（子 Agent 执行器）

**职责**: 并行执行子 Agent，收集结果

**使用场景**:
- 复杂任务分解（Plan Agent 创建多个 Edit Agent）
- 并行搜索（Explore Agent 创建多个 Search Agent）
- 独立子任务（每个子 Agent 有独立上下文）

**实现代码**:

```python
async def _execute_sub_agents(
    self,
    sub_agent_calls: List[Dict[str, Any]],
    parent_context: AgentContext,
    config: AgentConfig
) -> List[Dict[str, Any]]:
    """
    并行执行子 Agent

    Args:
        sub_agent_calls: 子 Agent 调用列表
        parent_context: 父 Agent 上下文
        config: Agent 配置

    Returns:
        List[Dict]: 子 Agent 执行结果列表
    """
    # 创建子 Agent 任务
    tasks = []
    for call in sub_agent_calls:
        # 创建子 Agent 配置（继承父配置，但降低限制）
        sub_config = AgentConfig(
            max_iterations=config.max_iterations // 2,
            max_tokens=config.max_tokens // len(sub_agent_calls),
            temperature=config.temperature,
            parallel_tools=config.parallel_tools,
            enable_sub_agents=False,  # 禁止子 Agent 再创建子 Agent
            timeout=config.timeout // 2
        )

        # 创建子 Agent 任务
        task = self.run_agent(
            agent_type=call["agent_type"],
            instruction=call["instruction"],
            workspace=parent_context.workspace,
            history=[],  # 子 Agent 独立上下文
            config=sub_config
        )
        tasks.append(task)

    # 并行执行所有子 Agent
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 格式化结果
    formatted_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            formatted_results.append({
                "agent_type": sub_agent_calls[i]["agent_type"],
                "instruction": sub_agent_calls[i]["instruction"],
                "success": False,
                "error": str(result)
            })
        else:
            formatted_results.append({
                "agent_id": result.agent_id,
                "agent_type": sub_agent_calls[i]["agent_type"],
                "instruction": sub_agent_calls[i]["instruction"],
                "success": result.success,
                "response": result.response,
                "iterations": result.iterations,
                "tokens_used": result.tokens_used
            })

    return formatted_results
```

---

## 🤖 Agent 类型详解

### 1. Plan Agent（规划型）

**职责**: 任务分解和规划

**特点**:
- 分析复杂任务
- 创建执行计划
- 调度子 Agent

**Prompt 模板**:

```python
PLAN_AGENT_PROMPT = """
You are a Plan Agent. Your job is to analyze complex tasks and break them down into smaller, manageable sub-tasks.

## Your Capabilities:
1. Analyze the user's request
2. Break down into sub-tasks
3. Create sub-agents to execute each sub-task
4. Coordinate results from sub-agents

## Available Sub-Agent Types:
- explore: Search and explore codebase
- edit: Modify code files
- search: Search for specific information

## Instructions:
{instruction}

## Workspace:
{workspace}

## Output Format:
1. Analysis: Explain your understanding of the task
2. Plan: List all sub-tasks
3. Sub-Agents: Create sub-agents for each sub-task

Use the `create_sub_agent` tool to create sub-agents.
"""


class PlanAgent:
    """规划型 Agent"""

    def __init__(self):
        self.agent_type = AgentType.PLAN
        self.model_name = "qwen2.5-72b-instruct"  # 使用大模型
        self.tools = [
            "create_sub_agent",
            "search_code",
            "read_file"
        ]

    def build_prompt(
        self,
        instruction: str,
        workspace: str,
        history: List[Dict[str, Any]]
    ) -> str:
        """构建 Prompt"""
        return PLAN_AGENT_PROMPT.format(
            instruction=instruction,
            workspace=workspace
        )
```

**使用示例**:

```python
# 用户请求: "重构整个认证系统"
result = await orchestrator.run_agent(
    agent_type="plan",
    instruction="重构整个认证系统，使用 JWT 替换 Session",
    workspace="/path/to/project"
)

# Plan Agent 会:
# 1. 分析认证系统的当前实现
# 2. 创建执行计划:
#    - 子任务 1: 搜索所有认证相关代码
#    - 子任务 2: 实现 JWT 工具函数
#    - 子任务 3: 修改登录接口
#    - 子任务 4: 修改认证中间件
#    - 子任务 5: 更新测试
# 3. 创建 5 个子 Agent 并行执行
# 4. 收集结果并总结
```

---

### 2. Explore Agent（探索型）

**职责**: 代码库探索和搜索

**特点**:
- 语义搜索
- 代码分析
- 依赖追踪

**Prompt 模板**:

```python
EXPLORE_AGENT_PROMPT = """
You are an Explore Agent. Your job is to search and explore the codebase to find relevant information.

## Your Capabilities:
1. Semantic search across codebase
2. Analyze code structure
3. Trace dependencies
4. Find related files

## Available Tools:
- semantic_search: Search by meaning
- search_code: Search by pattern
- read_file: Read file contents
- analyze_code: Analyze code structure

## Instructions:
{instruction}

## Workspace:
{workspace}

## Output Format:
1. Search Strategy: Explain your search approach
2. Findings: List all relevant files and code
3. Analysis: Summarize what you found
"""


class ExploreAgent:
    """探索型 Agent"""

    def __init__(self):
        self.agent_type = AgentType.EXPLORE
        self.model_name = "qwen2.5-32b-instruct"  # 中等模型
        self.tools = [
            "semantic_search",
            "search_code",
            "read_file",
            "analyze_code"
        ]

    def build_prompt(
        self,
        instruction: str,
        workspace: str,
        history: List[Dict[str, Any]]
    ) -> str:
        """构建 Prompt"""
        return EXPLORE_AGENT_PROMPT.format(
            instruction=instruction,
            workspace=workspace
        )
```

**使用示例**:

```python
# 用户请求: "找到所有处理用户认证的代码"
result = await orchestrator.run_agent(
    agent_type="explore",
    instruction="找到所有处理用户认证的代码",
    workspace="/path/to/project"
)

# Explore Agent 会:
# 1. 使用 semantic_search 搜索 "user authentication"
# 2. 使用 search_code 搜索 "login", "auth", "jwt"
# 3. 读取相关文件
# 4. 分析代码结构
# 5. 返回所有相关文件和代码片段
```

---

### 3. Edit Agent（编辑型）

**职责**: 代码修改和重构

**特点**:
- 精确编辑
- 语法检查
- 测试验证

**Prompt 模板**:

```python
EDIT_AGENT_PROMPT = """
You are an Edit Agent. Your job is to modify code files according to instructions.

## Your Capabilities:
1. Read and understand existing code
2. Make precise edits
3. Ensure syntax correctness
4. Run tests to verify changes

## Available Tools:
- read_file: Read file contents
- edit_file: Edit file with precise changes
- run_tests: Run tests
- analyze_code: Check syntax

## Instructions:
{instruction}

## Workspace:
{workspace}

## Output Format:
1. Analysis: Explain what needs to be changed
2. Changes: List all modifications
3. Verification: Confirm tests pass
"""


class EditAgent:
    """编辑型 Agent"""

    def __init__(self):
        self.agent_type = AgentType.EDIT
        self.model_name = "qwen2.5-32b-instruct"
        self.tools = [
            "read_file",
            "edit_file",
            "run_tests",
            "analyze_code"
        ]

    def build_prompt(
        self,
        instruction: str,
        workspace: str,
        history: List[Dict[str, Any]]
    ) -> str:
        """构建 Prompt"""
        return EDIT_AGENT_PROMPT.format(
            instruction=instruction,
            workspace=workspace
        )
```

**使用示例**:

```python
# 用户请求: "修改 login 函数使用 JWT"
result = await orchestrator.run_agent(
    agent_type="edit",
    instruction="修改 auth.py 中的 login 函数，使用 JWT 替换 Session",
    workspace="/path/to/project"
)

# Edit Agent 会:
# 1. 读取 auth.py
# 2. 分析 login 函数
# 3. 修改代码使用 JWT
# 4. 运行测试验证
# 5. 返回修改结果
```

---

### 4. Search Agent（搜索型）

**职责**: 特定信息搜索

**特点**:
- 快速搜索
- 精确匹配
- 轻量级

**Prompt 模板**:

```python
SEARCH_AGENT_PROMPT = """
You are a Search Agent. Your job is to quickly find specific information.

## Your Capabilities:
1. Fast pattern matching
2. Exact search
3. File filtering

## Available Tools:
- search_code: Search by pattern
- grep: Fast text search
- find_files: Find files by name

## Instructions:
{instruction}

## Workspace:
{workspace}

## Output Format:
Return search results directly.
"""


class SearchAgent:
    """搜索型 Agent"""

    def __init__(self):
        self.agent_type = AgentType.SEARCH
        self.model_name = "qwen2.5-7b-instruct"  # 小模型
        self.tools = [
            "search_code",
            "grep",
            "find_files"
        ]

    def build_prompt(
        self,
        instruction: str,
        workspace: str,
        history: List[Dict[str, Any]]
    ) -> str:
        """构建 Prompt"""
        return SEARCH_AGENT_PROMPT.format(
            instruction=instruction,
            workspace=workspace
        )
```

---

## 📊 上下文管理

### Context Manager（上下文管理器）

**职责**: 管理对话历史，智能压缩

**核心功能**:

```python
class ContextManager:
    """上下文管理器"""

    def __init__(
        self,
        inference_service,
        redis_client
    ):
        self.inference = inference_service
        self.redis = redis_client
        self.compression_model = "qwen2.5-7b-instruct"  # 使用小模型压缩

    async def create_context(
        self,
        agent_id: str,
        agent_type: AgentType,
        instruction: str,
        workspace: str,
        history: List[Dict[str, Any]]
    ) -> AgentContext:
        """创建 Agent 上下文"""
        return AgentContext(
            agent_id=agent_id,
            agent_type=agent_type,
            instruction=instruction,
            workspace=workspace,
            history=history,
            tools=self._get_tools_for_agent(agent_type),
            token_used=0,
            iteration=0,
            metadata={}
        )

    def should_compress(
        self,
        context: AgentContext,
        config: AgentConfig
    ) -> bool:
        """判断是否需要压缩"""
        token_usage_ratio = context.token_used / config.max_tokens
        return token_usage_ratio >= config.compression_threshold

    async def compress_background(
        self,
        context: AgentContext
    ) -> None:
        """
        后台压缩对话历史

        策略:
        1. 保留最近 3 轮对话
        2. 压缩之前的对话为摘要
        3. 使用小模型生成摘要
        4. 异步执行，不阻塞主流程
        """
        # 分离最近对话和历史对话
        recent_messages = context.history[-6:]  # 最近 3 轮（user + assistant）
        old_messages = context.history[:-6]

        if not old_messages:
            return

        # 构建压缩 Prompt
        compress_prompt = f"""
Summarize the following conversation history concisely:

{self._format_messages(old_messages)}

Provide a brief summary (max 200 words) that captures:
1. Main topics discussed
2. Key decisions made
3. Important context

Summary:
"""

        # 使用小模型生成摘要
        summary = await self.inference.generate(
            model=self.compression_model,
            prompt=compress_prompt,
            temperature=0.3,
            max_tokens=500
        )

        # 替换历史消息为摘要
        context.history = [
            {
                "role": "system",
                "content": f"Previous conversation summary:\n{summary.content}"
            }
        ] + recent_messages

        # 更新 Token 计数（摘要通常更短）
        context.token_used = self._count_tokens(context.history)

    def _count_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算 Token 数量"""
        # 简单估算: 1 token ≈ 4 characters
        total_chars = sum(
            len(str(msg.get("content", "")))
            for msg in messages
        )
        return total_chars // 4

    def _format_messages(self, messages: List[Dict[str, Any]]) -> str:
        """格式化消息为文本"""
        formatted = []
        for msg in messages:
            role = msg["role"]
            content = msg.get("content", "")
            formatted.append(f"{role}: {content}")
        return "\n\n".join(formatted)

    def _get_tools_for_agent(self, agent_type: AgentType) -> List[str]:
        """获取 Agent 可用的工具列表"""
        tool_mapping = {
            AgentType.PLAN: [
                "create_sub_agent",
                "search_code",
                "read_file"
            ],
            AgentType.EXPLORE: [
                "semantic_search",
                "search_code",
                "read_file",
                "analyze_code"
            ],
            AgentType.EDIT: [
                "read_file",
                "edit_file",
                "run_tests",
                "analyze_code"
            ],
            AgentType.SEARCH: [
                "search_code",
                "grep",
                "find_files"
            ]
        }
        return tool_mapping.get(agent_type, [])
```

---

## 🔧 Agent Registry（Agent 注册表）

**职责**: 管理所有 Agent 类型

**实现代码**:

```python
class AgentRegistry:
    """Agent 注册表"""

    def __init__(self):
        self._agents: Dict[str, Any] = {}
        self._register_builtin_agents()

    def _register_builtin_agents(self):
        """注册内置 Agent"""
        self.register("plan", PlanAgent())
        self.register("explore", ExploreAgent())
        self.register("edit", EditAgent())
        self.register("search", SearchAgent())

    def register(self, agent_type: str, agent: Any):
        """注册 Agent"""
        self._agents[agent_type] = agent

    def get_agent(self, agent_type: str) -> Any:
        """获取 Agent"""
        if agent_type not in self._agents:
            raise ValueError(f"Unknown agent type: {agent_type}")
        return self._agents[agent_type]

    def list_agents(self) -> List[str]:
        """列出所有 Agent 类型"""
        return list(self._agents.keys())
```

---

## 🚀 性能优化

### 1. 并行执行优化

**策略**:
- 工具并行执行（asyncio.gather）
- 子 Agent 并行执行
- 批量推理优化

**代码示例**:

```python
# 并行执行多个工具
tool_results = await asyncio.gather(
    self.tools.execute("search_code", {"pattern": "login"}),
    self.tools.execute("search_code", {"pattern": "auth"}),
    self.tools.execute("read_file", {"path": "auth.py"}),
    return_exceptions=True
)

# 并行执行多个子 Agent
sub_agent_results = await asyncio.gather(
    self.run_agent("explore", "搜索认证代码", workspace),
    self.run_agent("explore", "搜索测试代码", workspace),
    self.run_agent("edit", "修改登录函数", workspace),
    return_exceptions=True
)
```

### 2. 缓存优化

**策略**:
- 推理结果缓存
- 工具结果缓存
- 代码分析缓存

**代码示例**:

```python
class CachedInferenceService:
    """带缓存的推理服务"""

    def __init__(self, inference_service, redis_client):
        self.inference = inference_service
        self.redis = redis_client

    async def generate(self, model: str, prompt: str, **kwargs):
        """生成文本（带缓存）"""
        # 1. 计算缓存 key
        cache_key = f"inference:{model}:{hash(prompt)}"

        # 2. 检查缓存
        cached = await self.redis.get(cache_key)
        if cached:
            return json.loads(cached)

        # 3. 调用推理
        result = await self.inference.generate(model, prompt, **kwargs)

        # 4. 缓存结果
        await self.redis.set(
            cache_key,
            json.dumps(result.dict()),
            ex=3600  # 1 小时
        )

        return result
```

### 3. Token 优化

**策略**:
- 智能压缩历史
- 精简 Prompt
- 使用小模型处理简单任务

**Token 预算分配**:

```python
# 总预算: 100,000 tokens
# 分配策略:
# - 系统 Prompt: 2,000 tokens (2%)
# - 对话历史: 30,000 tokens (30%)
# - 工具调用: 20,000 tokens (20%)
# - 生成输出: 48,000 tokens (48%)

class TokenBudgetManager:
    """Token 预算管理器"""

    def __init__(self, total_budget: int = 100000):
        self.total_budget = total_budget
        self.system_budget = int(total_budget * 0.02)
        self.history_budget = int(total_budget * 0.30)
        self.tools_budget = int(total_budget * 0.20)
        self.output_budget = int(total_budget * 0.48)

    def allocate(self, context: AgentContext) -> Dict[str, int]:
        """分配 Token 预算"""
        return {
            "system": self.system_budget,
            "history": self.history_budget,
            "tools": self.tools_budget,
            "output": self.output_budget
        }
```

---

## 📈 监控和日志

### 1. Agent 执行日志

**记录内容**:
- Agent 类型和 ID
- 执行时间
- 迭代次数
- Token 使用量
- 工具调用记录
- 子 Agent 调用记录

**代码示例**:

```python
class AgentLogger:
    """Agent 日志记录器"""

    def __init__(self, db_client):
        self.db = db_client

    async def log_execution(
        self,
        result: AgentResult,
        context: AgentContext
    ):
        """记录 Agent 执行"""
        await self.db.execute("""
            INSERT INTO agent_executions (
                id, agent_type, instruction, iterations,
                duration_ms, tokens_used, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
            result.agent_id,
            context.agent_type.value,
            context.instruction,
            result.iterations,
            result.duration_ms,
            result.tokens_used,
            datetime.now()
        )

    async def log_tool_call(
        self,
        agent_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
        duration_ms: int
    ):
        """记录工具调用"""
        await self.db.execute("""
            INSERT INTO tool_calls (
                id, agent_execution_id, tool_name,
                arguments, result, duration_ms,
                success, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
            str(uuid.uuid4()),
            agent_id,
            tool_name,
            json.dumps(arguments),
            json.dumps(result),
            duration_ms,
            result.get("success", False),
            datetime.now()
        )
```

### 2. 性能指标

**Prometheus 指标**:

```python
from prometheus_client import Counter, Histogram, Gauge

# Agent 执行计数
agent_executions = Counter(
    'vlinders_agent_executions_total',
    'Total agent executions',
    ['agent_type', 'success']
)

# Agent 执行时间
agent_duration = Histogram(
    'vlinders_agent_duration_seconds',
    'Agent execution duration',
    ['agent_type']
)

# Agent 迭代次数
agent_iterations = Histogram(
    'vlinders_agent_iterations',
    'Agent iterations',
    ['agent_type']
)

# Token 使用量
agent_tokens = Histogram(
    'vlinders_agent_tokens',
    'Agent tokens used',
    ['agent_type']
)

# 活跃 Agent 数量
active_agents = Gauge(
    'vlinders_active_agents',
    'Number of active agents'
)
```

---

## 🎯 完整示例

### 复杂任务执行示例

**场景**: 用户请求重构认证系统

```python
# 1. 用户请求
user_request = "重构整个认证系统，使用 JWT 替换 Session，并更新所有相关测试"

# 2. 创建 Plan Agent
result = await orchestrator.run_agent(
    agent_type="plan",
    instruction=user_request,
    workspace="/path/to/project",
    config=AgentConfig(
        max_iterations=15,
        max_tokens=150000,
        enable_sub_agents=True
    )
)

# 3. Plan Agent 执行流程:

# Iteration 1: 分析任务
# - 调用 search_code 搜索认证相关代码
# - 调用 read_file 读取关键文件
# - 分析当前实现

# Iteration 2: 创建执行计划
# - 创建 5 个子任务
# - 为每个子任务创建子 Agent

# Sub-Agent 1: Explore Agent
# - 任务: 搜索所有认证相关代码
# - 工具: semantic_search, search_code, read_file
# - 结果: 找到 15 个相关文件

# Sub-Agent 2: Edit Agent
# - 任务: 实现 JWT 工具函数
# - 工具: read_file, edit_file, run_tests
# - 结果: 创建 jwt_utils.py

# Sub-Agent 3: Edit Agent
# - 任务: 修改登录接口
# - 工具: read_file, edit_file, run_tests
# - 结果: 修改 auth.py

# Sub-Agent 4: Edit Agent
# - 任务: 修改认证中间件
# - 工具: read_file, edit_file, run_tests
# - 结果: 修改 middleware.py

# Sub-Agent 5: Edit Agent
# - 任务: 更新测试
# - 工具: read_file, edit_file, run_tests
# - 结果: 更新 test_auth.py

# Iteration 3: 收集结果
# - 汇总所有子 Agent 的结果
# - 验证所有测试通过
# - 生成最终报告

# 4. 返回结果
print(f"Success: {result.success}")
print(f"Iterations: {result.iterations}")
print(f"Tokens Used: {result.tokens_used}")
print(f"Duration: {result.duration_ms}ms")
print(f"Sub-Agents: {len(result.sub_agents)}")
print(f"\nResponse:\n{result.response}")
```

**输出示例**:

```
Success: True
Iterations: 3
Tokens Used: 45230
Duration: 12500ms
Sub-Agents: 5

Response:
认证系统重构完成！

## 执行摘要:
1. ✅ 搜索并分析了 15 个认证相关文件
2. ✅ 创建了 JWT 工具函数 (jwt_utils.py)
3. ✅ 修改了登录接口使用 JWT (auth.py)
4. ✅ 更新了认证中间件 (middleware.py)
5. ✅ 更新了所有测试 (test_auth.py)

## 修改的文件:
- src/utils/jwt_utils.py (新建)
- src/api/auth.py (修改)
- src/middleware/auth_middleware.py (修改)
- tests/test_auth.py (修改)

## 测试结果:
所有 23 个测试通过 ✅

## 注意事项:
- 需要在环境变量中配置 JWT_SECRET
- Session 相关代码已移除
- 建议进行手动测试验证
```

---

## 🎯 总结

Vlinders-Server 的 Agent 编排系统具有以下特点:

1. **智能编排** - 自动管理 Agent 生命周期，支持复杂任务分解
2. **高效执行** - 工具并行调用，子 Agent 并行执行
3. **灵活扩展** - 支持自定义 Agent 类型和工具
4. **上下文管理** - 智能压缩，节省 Token 成本
5. **完善监控** - 详细的日志和性能指标

---

**相关文档**:
- [01-架构设计.md](./01-架构设计.md)
- [02-技术选型.md](./02-技术选型.md)
- [03-API设计.md](./03-API设计.md)
