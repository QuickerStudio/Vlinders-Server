# vLLM 集成方案

**版本**: v1.0
**最后更新**: 2026-02-28
**文档类型**: 技术实施

---

## 📋 文档概述

本文档详细说明如何在 Vlinders-Server 中集成和使用 vLLM，包括安装、配置、优化和生产部署。

---

## 🎯 vLLM 简介

### 什么是 vLLM？

vLLM 是由 UC Berkeley 开发的高性能大模型推理引擎，专为生产环境设计。

**核心特性**:
- **PagedAttention** - 高效的注意力机制，内存利用率提升 4x
- **Continuous Batching** - 连续批处理，吞吐量提升 24x
- **异步推理** - 原生支持 Python asyncio
- **流式生成** - 实时输出 Token
- **多 GPU 支持** - Tensor Parallelism

### 性能对比

```
基准测试 (Llama 3 70B, 4x A100 80GB):

传统方法:
- 吞吐量: 10 requests/s
- 延迟: 2000ms (TTFT)
- GPU 利用率: 60%

vLLM:
- 吞吐量: 240 requests/s (24x ↑)
- 延迟: 500ms (TTFT) (4x ↓)
- GPU 利用率: 90%
```

---

## 🔧 安装和配置

### 环境要求

**硬件**:
- GPU: NVIDIA A100/H100 (推荐) 或 V100/A10
- VRAM: 至少 40GB (Llama 3 70B 需要 4x 80GB)
- CPU: 16+ 核心
- RAM: 128GB+
- 存储: 500GB+ SSD

**软件**:
- OS: Ubuntu 22.04 LTS
- Python: 3.10 或 3.11
- CUDA: 12.1+
- cuDNN: 8.9+
- Driver: 535+

### 安装步骤

#### 1. 安装 CUDA 和 cuDNN

```bash
# 安装 CUDA 12.1
wget https://developer.download.nvidia.com/compute/cuda/12.1.0/local_installers/cuda_12.1.0_530.30.02_linux.run
sudo sh cuda_12.1.0_530.30.02_linux.run

# 设置环境变量
export CUDA_HOME=/usr/local/cuda-12.1
export PATH=$CUDA_HOME/bin:$PATH
export LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH

# 验证安装
nvcc --version
nvidia-smi
```

#### 2. 创建 Python 环境

```bash
# 使用 conda 或 venv
conda create -n vlinders python=3.11
conda activate vlinders

# 或使用 venv
python3.11 -m venv venv
source venv/bin/activate
```

#### 3. 安装 vLLM

```bash
# 从 PyPI 安装（推荐）
pip install vllm

# 或从源码安装（最新功能）
git clone https://github.com/vllm-project/vllm.git
cd vllm
pip install -e .

# 验证安装
python -c "import vllm; print(vllm.__version__)"
```

#### 4. 安装依赖

```bash
# 安装其他依赖
pip install torch==2.1.0 --index-url https://download.pytorch.org/whl/cu121
pip install transformers accelerate
pip install fastapi uvicorn
pip install prometheus-client

# 验证 CUDA 可用
python -c "import torch; print(torch.cuda.is_available())"
```

---

## 📦 模型加载

### 支持的模型格式

vLLM 支持以下模型格式：
- Hugging Face Transformers
- GGUF (通过转换)
- AWQ (量化)
- GPTQ (量化)

### 下载模型

```bash
# 使用 Hugging Face CLI
pip install huggingface-hub

# 下载模型
huggingface-cli download meta-llama/Meta-Llama-3-70B-Instruct \
  --local-dir /models/llama-3-70b \
  --local-dir-use-symlinks False

# 或使用 Python
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="meta-llama/Meta-Llama-3-70B-Instruct",
    local_dir="/models/llama-3-70b",
    local_dir_use_symlinks=False
)
```

### 加载模型到 vLLM

```python
from vllm import AsyncLLMEngine
from vllm.engine.arg_utils import AsyncEngineArgs

# 配置引擎参数
engine_args = AsyncEngineArgs(
    model="/models/llama-3-70b",
    tensor_parallel_size=4,  # 使用 4 个 GPU
    dtype="float16",         # 使用 FP16
    max_model_len=32768,     # 最大上下文长度
    gpu_memory_utilization=0.9,  # GPU 内存使用率
    trust_remote_code=True,
    enable_prefix_caching=True,  # 启用前缀缓存
    disable_log_stats=False
)

# 创建引擎
engine = AsyncLLMEngine.from_engine_args(engine_args)

print(f"Model loaded successfully")
print(f"Max tokens: {engine_args.max_model_len}")
print(f"Tensor parallel size: {engine_args.tensor_parallel_size}")
```

### 多模型管理

```python
class ModelManager:
    """管理多个模型"""

    def __init__(self):
        self.engines = {}

    async def load_model(
        self,
        model_name: str,
        model_path: str,
        tensor_parallel_size: int = 1
    ):
        """加载模型"""
        engine_args = AsyncEngineArgs(
            model=model_path,
            tensor_parallel_size=tensor_parallel_size,
            dtype="float16",
            max_model_len=32768,
            gpu_memory_utilization=0.9
        )

        engine = AsyncLLMEngine.from_engine_args(engine_args)
        self.engines[model_name] = engine

        print(f"✅ Model {model_name} loaded")

    def get_engine(self, model_name: str):
        """获取模型引擎"""
        if model_name not in self.engines:
            raise ValueError(f"Model {model_name} not loaded")
        return self.engines[model_name]

# 使用示例
manager = ModelManager()

# 加载多个模型
await manager.load_model(
    "vlinders-gpt-4",
    "/models/llama-3-70b",
    tensor_parallel_size=4
)

await manager.load_model(
    "vlinders-gpt-3.5",
    "/models/llama-3-8b",
    tensor_parallel_size=1
)
```

---

## 🚀 推理接口

### 异步推理

```python
from vllm import SamplingParams
import uuid

async def generate_text(
    engine: AsyncLLMEngine,
    prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    top_p: float = 0.95,
    stop: list = None
):
    """异步生成文本"""

    # 配置采样参数
    sampling_params = SamplingParams(
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        stop=stop or []
    )

    # 生成请求 ID
    request_id = f"req_{uuid.uuid4().hex[:8]}"

    # 异步生成
    final_output = None
    async for output in engine.generate(
        prompt,
        sampling_params,
        request_id
    ):
        final_output = output

    # 返回结果
    if final_output and final_output.outputs:
        return {
            "text": final_output.outputs[0].text,
            "finish_reason": final_output.outputs[0].finish_reason,
            "usage": {
                "prompt_tokens": len(final_output.prompt_token_ids),
                "completion_tokens": len(final_output.outputs[0].token_ids),
                "total_tokens": len(final_output.prompt_token_ids) + len(final_output.outputs[0].token_ids)
            }
        }

# 使用示例
result = await generate_text(
    engine,
    "Write a fibonacci function in Python:",
    max_tokens=500,
    temperature=0.2
)

print(result["text"])
print(f"Tokens used: {result['usage']['total_tokens']}")
```

### 流式生成

```python
async def generate_stream(
    engine: AsyncLLMEngine,
    prompt: str,
    max_tokens: int = 2048,
    temperature: float = 0.7
):
    """流式生成文本"""

    sampling_params = SamplingParams(
        temperature=temperature,
        max_tokens=max_tokens
    )

    request_id = f"req_{uuid.uuid4().hex[:8]}"

    # 流式生成
    async for output in engine.generate(
        prompt,
        sampling_params,
        request_id
    ):
        if output.outputs:
            yield {
                "text": output.outputs[0].text,
                "finish_reason": output.outputs[0].finish_reason
            }

# 使用示例
async for chunk in generate_stream(
    engine,
    "Write a story about AI:",
    max_tokens=1000
):
    print(chunk["text"], end="", flush=True)
    if chunk["finish_reason"]:
        print(f"\n[{chunk['finish_reason']}]")
```

### 批处理

```python
async def generate_batch(
    engine: AsyncLLMEngine,
    prompts: list[str],
    max_tokens: int = 2048
):
    """批量生成"""

    sampling_params = SamplingParams(
        max_tokens=max_tokens,
        temperature=0.7
    )

    # 提交所有请求
    request_ids = []
    for prompt in prompts:
        request_id = f"req_{uuid.uuid4().hex[:8]}"
        request_ids.append(request_id)

        # 异步提交（不等待）
        asyncio.create_task(
            engine.generate(prompt, sampling_params, request_id)
        )

    # vLLM 会自动批处理这些请求
    # 等待所有请求完成
    results = []
    for request_id in request_ids:
        # 获取结果（实际实现需要结果队列）
        result = await get_result(request_id)
        results.append(result)

    return results
```

---

## ⚡ 性能优化

### 1. GPU 内存管理

```python
# 配置 GPU 内存使用率
engine_args = AsyncEngineArgs(
    model="/models/llama-3-70b",
    gpu_memory_utilization=0.9,  # 使用 90% GPU 内存
    # 0.9 是推荐值，留 10% 给系统
)

# 监控 GPU 内存
import torch

def print_gpu_memory():
    for i in range(torch.cuda.device_count()):
        allocated = torch.cuda.memory_allocated(i) / 1024**3
        reserved = torch.cuda.memory_reserved(i) / 1024**3
        print(f"GPU {i}: {allocated:.2f}GB / {reserved:.2f}GB")
```

### 2. 前缀缓存

```python
# 启用前缀缓存
engine_args = AsyncEngineArgs(
    model="/models/llama-3-70b",
    enable_prefix_caching=True,  # 启用前缀缓存
)

# 前缀缓存的好处：
# 如果多个请求有相同的前缀（如系统提示），
# vLLM 会缓存前缀的 KV Cache，避免重复计算

# 示例：
system_prompt = "You are a helpful coding assistant."

# 请求 1
prompt1 = system_prompt + "\nWrite a Python function"
# 计算完整的 KV Cache

# 请求 2
prompt2 = system_prompt + "\nWrite a JavaScript function"
# 复用 system_prompt 的 KV Cache，只计算新部分
```

### 3. 量化

```python
# 使用 AWQ 量化（推荐）
engine_args = AsyncEngineArgs(
    model="/models/llama-3-70b-awq",  # AWQ 量化模型
    quantization="awq",
    dtype="float16"
)

# 或使用 GPTQ 量化
engine_args = AsyncEngineArgs(
    model="/models/llama-3-70b-gptq",
    quantization="gptq",
    dtype="float16"
)

# 量化的好处：
# - 内存使用减少 50-75%
# - 吞吐量提升 1.5-2x
# - 精度损失 < 1%
```

### 4. Tensor Parallelism 配置

```python
# 单 GPU（小模型）
engine_args = AsyncEngineArgs(
    model="/models/llama-3-8b",
    tensor_parallel_size=1
)

# 2 GPU（中等模型）
engine_args = AsyncEngineArgs(
    model="/models/llama-3-70b",
    tensor_parallel_size=2
)

# 4 GPU（大模型）
engine_args = AsyncEngineArgs(
    model="/models/llama-3-70b",
    tensor_parallel_size=4
)

# 8 GPU（超大模型）
engine_args = AsyncEngineArgs(
    model="/models/llama-3-405b",
    tensor_parallel_size=8
)

# 规则：
# - tensor_parallel_size 必须能整除 GPU 数量
# - 通信开销随 TP 增加而增加
# - 建议：模型大小 / GPU 数量 = 每个 GPU 20-40GB
```

---

## 🐳 生产部署

### Docker 部署

```dockerfile
# Dockerfile
FROM nvidia/cuda:12.1.0-devel-ubuntu22.04

# 安装 Python
RUN apt-get update && apt-get install -y \
    python3.11 python3.11-venv python3-pip \
    git wget

# 创建工作目录
WORKDIR /app

# 安装 vLLM
RUN pip install vllm torch transformers

# 复制代码
COPY . /app

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# 构建镜像
docker build -t vlinders-server:latest .

# 运行容器
docker run --gpus all \
  -p 8000:8000 \
  -v /models:/models \
  -e CUDA_VISIBLE_DEVICES=0,1,2,3 \
  vlinders-server:latest
```

### Kubernetes 部署

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: vlinders-server
spec:
  replicas: 2
  selector:
    matchLabels:
      app: vlinders-server
  template:
    metadata:
      labels:
        app: vlinders-server
    spec:
      containers:
      - name: vlinders-server
        image: vlinders-server:latest
        ports:
        - containerPort: 8000
        resources:
          limits:
            nvidia.com/gpu: 4  # 每个 Pod 4 个 GPU
            memory: 128Gi
            cpu: 16
          requests:
            nvidia.com/gpu: 4
            memory: 128Gi
            cpu: 16
        volumeMounts:
        - name: models
          mountPath: /models
        env:
        - name: CUDA_VISIBLE_DEVICES
          value: "0,1,2,3"
      volumes:
      - name: models
        persistentVolumeClaim:
          claimName: models-pvc
```

### 监控和日志

```python
# 添加 Prometheus 指标
from prometheus_client import Counter, Histogram, Gauge

# 请求计数
request_count = Counter(
    'vllm_requests_total',
    'Total requests',
    ['model', 'status']
)

# 响应时间
response_time = Histogram(
    'vllm_response_seconds',
    'Response time',
    ['model']
)

# GPU 使用率
gpu_utilization = Gauge(
    'vllm_gpu_utilization',
    'GPU utilization',
    ['gpu_id']
)

# 在推理时记录指标
async def generate_with_metrics(engine, prompt):
    start_time = time.time()

    try:
        result = await generate_text(engine, prompt)
        request_count.labels(model='llama-3-70b', status='success').inc()
        return result
    except Exception as e:
        request_count.labels(model='llama-3-70b', status='error').inc()
        raise
    finally:
        duration = time.time() - start_time
        response_time.labels(model='llama-3-70b').observe(duration)
```

---

## 🎯 最佳实践

### 1. 参数调优

```python
# 推荐配置（Llama 3 70B, 4x A100 80GB）
engine_args = AsyncEngineArgs(
    model="/models/llama-3-70b",
    tensor_parallel_size=4,
    dtype="float16",
    max_model_len=32768,
    gpu_memory_utilization=0.9,
    enable_prefix_caching=True,
    disable_log_stats=False,
    max_num_seqs=256,  # 最大并发序列数
    max_num_batched_tokens=32768  # 最大批处理 tokens
)
```

### 2. 常见问题

**Q: OOM (Out of Memory) 错误**
```python
# 解决方案：
# 1. 降低 gpu_memory_utilization
gpu_memory_utilization=0.85  # 从 0.9 降到 0.85

# 2. 减少 max_model_len
max_model_len=16384  # 从 32768 降到 16384

# 3. 增加 tensor_parallel_size
tensor_parallel_size=8  # 从 4 增加到 8
```

**Q: 推理速度慢**
```python
# 解决方案：
# 1. 启用前缀缓存
enable_prefix_caching=True

# 2. 使用量化
quantization="awq"

# 3. 增加批处理大小
max_num_seqs=512
```

### 3. 性能基准

```python
# 性能测试脚本
import asyncio
import time

async def benchmark(engine, num_requests=100):
    """性能基准测试"""

    prompts = [f"Request {i}: Write code" for i in range(num_requests)]

    start_time = time.time()

    tasks = [
        generate_text(engine, prompt, max_tokens=100)
        for prompt in prompts
    ]

    results = await asyncio.gather(*tasks)

    end_time = time.time()
    duration = end_time - start_time

    print(f"Total requests: {num_requests}")
    print(f"Total time: {duration:.2f}s")
    print(f"Throughput: {num_requests / duration:.2f} req/s")
    print(f"Average latency: {duration / num_requests * 1000:.2f}ms")

# 运行基准测试
await benchmark(engine, num_requests=100)
```

---

## 📝 总结

### vLLM 集成检查清单

- [ ] 安装 CUDA 12.1+ 和 cuDNN 8.9+
- [ ] 安装 vLLM 和依赖
- [ ] 下载模型到本地
- [ ] 配置 Tensor Parallelism
- [ ] 启用前缀缓存
- [ ] 实现异步推理接口
- [ ] 实现流式生成
- [ ] 添加监控指标
- [ ] Docker 容器化
- [ ] Kubernetes 部署
- [ ] 性能基准测试

### 关键配置参数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| `tensor_parallel_size` | 4 | 根据模型大小和 GPU 数量 |
| `gpu_memory_utilization` | 0.9 | 留 10% 给系统 |
| `max_model_len` | 32768 | 根据需求调整 |
| `enable_prefix_caching` | True | 提升性能 |
| `dtype` | float16 | 平衡性能和精度 |

---

**下一步**: 阅读 [04-Agent编排系统.md](./04-Agent编排系统.md)
