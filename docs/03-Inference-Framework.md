# 推理框架设计文档

**版本**: v1.0
**创建日期**: 2026-02-28
**负责人**: ML Infrastructure Team
**状态**: 📝 设计阶段

---

## 📋 概述

本文档详细描述 Vlinders Platform 的推理框架，基于 Ray Serve + vLLM 构建高性能、可扩展的大模型推理服务。

### 设计目标

1. **高性能**: P95 延迟 < 500ms，吞吐量 > 1000 req/s
2. **高可用**: 99.9% 可用性，自动故障转移
3. **自动扩缩容**: 根据负载自动调整资源
4. **成本优化**: GPU 利用率 > 85%，支持缩容到零
5. **多模型支持**: 同时服务多个模型，动态加载/卸载

---

## 🏗️ 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        推理架构                                   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              API Gateway (Kong/Traefik)                 │    │
│  │  - 认证/授权                                             │    │
│  │  - 限流                                                  │    │
│  │  - 负载均衡                                              │    │
│  └────────────────────────────────────────────────────────┘    │
│                           ↓                                      │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              Ray Serve (编排层)                         │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐│    │
│  │  │ Deployment 1 │  │ Deployment 2 │  │ Deployment N ││    │
│  │  │ (GPT-4)      │  │ (GPT-3.5)    │  │ (Custom)     ││    │
│  │  │ Replicas: 2-10│  │ Replicas: 1-5│  │ Replicas: 1-3││    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘│    │
│  └────────────────────────────────────────────────────────┘    │
│                           ↓                                      │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              vLLM 推理引擎                              │    │
│  │  - PagedAttention                                       │    │
│  │  - Continuous Batching                                  │    │
│  │  - Prefix Caching                                       │    │
│  │  - Tensor Parallelism                                   │    │
│  └────────────────────────────────────────────────────────┘    │
│                           ↓                                      │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              GPU 集群                                    │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │    │
│  │  │ A100 #1  │  │ A100 #2  │  │ A100 #N  │            │    │
│  │  │ 80GB     │  │ 80GB     │  │ 80GB     │            │    │
│  │  └──────────┘  └──────────┘  └──────────┘            │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Ray Serve 集成

### 为什么选择 Ray Serve？

**对比分析**:

| 特性 | Ray Serve | Triton | TorchServe |
|------|-----------|--------|------------|
| Python 原生 | ✅ | ❌ | ✅ |
| 自动扩缩容 | ✅ | ❌ | ❌ |
| 多模型编排 | ✅ | ✅ | ❌ |
| 生产验证 | ✅ (OpenAI) | ✅ (NVIDIA) | ⚠️ |
| 学习曲线 | 低 | 中 | 低 |
| vLLM 集成 | ✅ 原生 | ⚠️ 需要适配 | ❌ |

**参考**: [Ray Serve Production Guide](https://www.anyscale.com/blog/low-latency-generative-ai-model-serving-with-ray-nvidia)

### Ray Cluster 配置

```yaml
# ray-cluster.yaml
apiVersion: ray.io/v1
kind: RayCluster
metadata:
  name: vlinders-ray-cluster
  namespace: vlinders-inference
spec:
  rayVersion: '2.9.0'

  # Head 节点
  headGroupSpec:
    rayStartParams:
      dashboard-host: '0.0.0.0'
      num-cpus: '0'  # Head 节点不参与计算
      block: 'true'
    template:
      spec:
        containers:
        - name: ray-head
          image: rayproject/ray-ml:2.9.0-gpu
          ports:
          - containerPort: 6379  # Redis
          - containerPort: 8265  # Dashboard
          - containerPort: 10001 # Client
          - containerPort: 8000  # Serve
          resources:
            limits:
              cpu: "4"
              memory: "16Gi"
            requests:
              cpu: "2"
              memory: "8Gi"
          volumeMounts:
          - name: models
            mountPath: /models
            readOnly: true
        volumes:
        - name: models
          persistentVolumeClaim:
            claimName: models-pvc

  # Worker 节点组
  workerGroupSpecs:
  - replicas: 2
    minReplicas: 1
    maxReplicas: 10
    groupName: gpu-workers
    rayStartParams:
      num-gpus: "1"
      block: 'true'
    template:
      spec:
        containers:
        - name: ray-worker
          image: rayproject/ray-ml:2.9.0-gpu
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "ray stop"]
          resources:
            limits:
              nvidia.com/gpu: 1
              cpu: "16"
              memory: "64Gi"
            requests:
              nvidia.com/gpu: 1
              cpu: "8"
              memory: "32Gi"
          volumeMounts:
          - name: models
            mountPath: /models
            readOnly: true
          - name: shm
            mountPath: /dev/shm
        volumes:
        - name: models
          persistentVolumeClaim:
            claimName: models-pvc
        - name: shm
          emptyDir:
            medium: Memory
            sizeLimit: 32Gi  # 共享内存，用于 vLLM
```

### Ray Serve Deployment

```python
# serve_config.py
from ray import serve
from ray.serve.config import AutoscalingConfig
from vllm import AsyncLLMEngine, SamplingParams
from vllm.engine.arg_utils import AsyncEngineArgs
from typing import Dict, AsyncGenerator
import logging

logger = logging.getLogger("ray.serve")

@serve.deployment(
    name="vllm-gpt4",
    num_replicas=2,
    ray_actor_options={
        "num_gpus": 1,
        "num_cpus": 8,
        "memory": 64 * 1024 * 1024 * 1024,  # 64GB
    },
    autoscaling_config=AutoscalingConfig(
        min_replicas=1,
        max_replicas=10,
        target_num_ongoing_requests_per_replica=5,
        upscale_delay_s=30,
        downscale_delay_s=300,
    ),
    max_concurrent_queries=100,
    health_check_period_s=10,
    health_check_timeout_s=30,
)
class VLLMDeployment:
    """vLLM 推理部署"""

    def __init__(
        self,
        model_name: str,
        model_path: str,
        tensor_parallel_size: int = 1,
        max_model_len: int = 16384,
        gpu_memory_utilization: float = 0.90,
    ):
        self.model_name = model_name

        logger.info(f"Initializing vLLM engine for {model_name}")

        # 配置 vLLM 引擎
        engine_args = AsyncEngineArgs(
            model=model_path,
            tensor_parallel_size=tensor_parallel_size,
            dtype="float16",
            max_model_len=max_model_len,
            gpu_memory_utilization=gpu_memory_utilization,
            trust_remote_code=True,
            enable_prefix_caching=True,
            disable_log_stats=False,
            # 性能优化
            max_num_seqs=256,
            max_num_batched_tokens=max_model_len,
        )

        # 创建异步引擎
        self.engine = AsyncLLMEngine.from_engine_args(engine_args)

        logger.info(f"✅ vLLM engine initialized: {model_name}")

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 0.95,
        stream: bool = False,
        **kwargs
    ) -> Dict | AsyncGenerator:
        """生成文本"""

        sampling_params = SamplingParams(
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop=kwargs.get("stop"),
        )

        request_id = f"req_{id(prompt)}"

        if stream:
            return self._generate_stream(prompt, sampling_params, request_id)
        else:
            return await self._generate_complete(prompt, sampling_params, request_id)

    async def _generate_complete(
        self,
        prompt: str,
        sampling_params: SamplingParams,
        request_id: str
    ) -> Dict:
        """非流式生成"""

        final_output = None
        async for output in self.engine.generate(prompt, sampling_params, request_id):
            final_output = output

        if final_output and final_output.outputs:
            return {
                "text": final_output.outputs[0].text,
                "finish_reason": final_output.outputs[0].finish_reason,
                "usage": {
                    "prompt_tokens": len(final_output.prompt_token_ids),
                    "completion_tokens": len(final_output.outputs[0].token_ids),
                    "total_tokens": (
                        len(final_output.prompt_token_ids) +
                        len(final_output.outputs[0].token_ids)
                    )
                }
            }

        raise RuntimeError("Generation failed")

    async def _generate_stream(
        self,
        prompt: str,
        sampling_params: SamplingParams,
        request_id: str
    ) -> AsyncGenerator:
        """流式生成"""

        async for output in self.engine.generate(prompt, sampling_params, request_id):
            if output.outputs:
                yield {
                    "text": output.outputs[0].text,
                    "finish_reason": output.outputs[0].finish_reason,
                    "done": output.finished
                }

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            # 简单的推理测试
            result = await self.generate("test", max_tokens=1)
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


# 部署多个模型
gpt4_deployment = VLLMDeployment.bind(
    model_name="gpt-4",
    model_path="/models/llama-3-70b",
    tensor_parallel_size=4,
    max_model_len=32768,
)

gpt35_deployment = VLLMDeployment.bind(
    model_name="gpt-3.5-turbo",
    model_path="/models/llama-3-8b",
    tensor_parallel_size=1,
    max_model_len=16384,
)
```

### API Gateway 层

```python
# api_gateway.py
from fastapi import FastAPI, HTTPException, Depends
from ray import serve
from pydantic import BaseModel
from typing import List, Optional
import asyncio

app = FastAPI(title="Vlinders Inference API")

class Message(BaseModel):
    role: str
    content: str

class InferenceRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: int = 2048
    temperature: float = 0.7
    top_p: float = 0.95
    stream: bool = False

@serve.deployment(
    name="api-gateway",
    num_replicas=3,
    autoscaling_config=AutoscalingConfig(
        min_replicas=2,
        max_replicas=20,
        target_num_ongoing_requests_per_replica=50,
    ),
)
@serve.ingress(app)
class InferenceGateway:
    """推理 API 网关"""

    def __init__(
        self,
        gpt4_handle: serve.DeploymentHandle,
        gpt35_handle: serve.DeploymentHandle,
    ):
        self.models = {
            "gpt-4": gpt4_handle,
            "gpt-3.5-turbo": gpt35_handle,
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(
        self,
        request: InferenceRequest,
        user: dict = Depends(verify_token),
        usage_tracker: UsageTracker = Depends(),
    ):
        """OpenAI 兼容的聊天接口"""

        # 1. 检查配额
        has_quota = await usage_tracker.check_quota(
            user["tenant_id"],
            "requests"
        )
        if not has_quota:
            raise HTTPException(429, "Quota exceeded")

        # 2. 获取模型 handle
        model_handle = self.models.get(request.model)
        if not model_handle:
            raise HTTPException(404, f"Model {request.model} not found")

        # 3. 构建 prompt
        prompt = self._build_prompt(request.messages)

        # 4. 调用推理
        try:
            result = await model_handle.generate.remote(
                prompt=prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                top_p=request.top_p,
                stream=request.stream,
            )

            # 5. 记录使用量
            await usage_tracker.record_inference(
                tenant_id=user["tenant_id"],
                user_id=user["id"],
                model=request.model,
                tokens_used=result["usage"]["total_tokens"]
            )

            # 6. 返回结果
            return {
                "id": f"chatcmpl_{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": request.model,
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result["text"]
                    },
                    "finish_reason": result["finish_reason"]
                }],
                "usage": result["usage"]
            }

        except Exception as e:
            logger.error(f"Inference failed: {e}")
            raise HTTPException(500, "Inference failed")

    def _build_prompt(self, messages: List[Message]) -> str:
        """构建 prompt"""
        # 简化版，实际应该使用模型的 chat template
        return "\n".join([
            f"{msg.role}: {msg.content}"
            for msg in messages
        ]) + "\nassistant:"


# 部署网关
gateway = InferenceGateway.bind(
    gpt4_handle=gpt4_deployment,
    gpt35_handle=gpt35_deployment,
)
```

---

## ⚡ 性能优化

### 1. vLLM 优化配置

```python
# 最佳实践配置
engine_args = AsyncEngineArgs(
    model=model_path,

    # GPU 配置
    tensor_parallel_size=4,  # 根据模型大小调整
    gpu_memory_utilization=0.90,  # 推荐 0.85-0.95

    # 性能优化
    enable_prefix_caching=True,  # 启用前缀缓存
    max_num_seqs=256,  # 最大并发序列数
    max_num_batched_tokens=32768,  # 批处理 token 数

    # 内存优化
    swap_space=4,  # GB，用于 CPU offloading
    max_model_len=32768,  # 根据需求调整

    # 精度
    dtype="float16",  # 或 "bfloat16"

    # 量化（可选）
    # quantization="awq",  # 或 "gptq"
)
```

### 2. 批处理优化

**Continuous Batching**:

vLLM 自动实现连续批处理，无需手动配置。关键参数：

```python
max_num_seqs=256  # 同时处理的序列数
max_num_batched_tokens=32768  # 批处理的 token 总数
```

**效果**:
- 吞吐量提升 2-10x
- GPU 利用率 > 85%

### 3. 前缀缓存

```python
enable_prefix_caching=True
```

**适用场景**:
- 系统提示词相同
- Few-shot 示例相同
- 长上下文对话

**效果**:
- 首 token 延迟降低 50-80%
- 吞吐量提升 2-3x

### 4. 量化

```python
# AWQ 量化（推荐）
quantization="awq"

# GPTQ 量化
quantization="gptq"
```

**效果**:
- 内存使用减少 50-75%
- 吞吐量提升 1.5-2x
- 精度损失 < 1%

---

## 📊 监控和可观测性

### Prometheus 指标

```python
from prometheus_client import Counter, Histogram, Gauge

# 请求指标
inference_requests_total = Counter(
    'inference_requests_total',
    'Total inference requests',
    ['model', 'status']
)

inference_latency_seconds = Histogram(
    'inference_latency_seconds',
    'Inference latency',
    ['model'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# GPU 指标
gpu_utilization_percent = Gauge(
    'gpu_utilization_percent',
    'GPU utilization',
    ['gpu_id']
)

gpu_memory_used_bytes = Gauge(
    'gpu_memory_used_bytes',
    'GPU memory used',
    ['gpu_id']
)

# Token 指标
tokens_generated_total = Counter(
    'tokens_generated_total',
    'Total tokens generated',
    ['model']
)

# Ray Serve 指标
ray_serve_num_deployment_replicas = Gauge(
    'ray_serve_num_deployment_replicas',
    'Number of deployment replicas',
    ['deployment']
)
```

### 监控仪表板

```yaml
# Grafana Dashboard
{
  "dashboard": {
    "title": "Vlinders Inference Monitoring",
    "panels": [
      {
        "title": "Requests per Second",
        "targets": [{
          "expr": "rate(inference_requests_total[5m])"
        }]
      },
      {
        "title": "P95 Latency",
        "targets": [{
          "expr": "histogram_quantile(0.95, inference_latency_seconds)"
        }]
      },
      {
        "title": "GPU Utilization",
        "targets": [{
          "expr": "avg(gpu_utilization_percent)"
        }]
      },
      {
        "title": "Active Replicas",
        "targets": [{
          "expr": "ray_serve_num_deployment_replicas"
        }]
      },
      {
        "title": "Tokens per Second",
        "targets": [{
          "expr": "rate(tokens_generated_total[5m])"
        }]
      }
    ]
  }
}
```

---

## 🔄 自动扩缩容

### Ray Serve Autoscaling

```python
autoscaling_config=AutoscalingConfig(
    min_replicas=1,
    max_replicas=10,
    target_num_ongoing_requests_per_replica=5,
    upscale_delay_s=30,  # 扩容延迟
    downscale_delay_s=300,  # 缩容延迟（5分钟）
)
```

### KEDA 配置（GPU 节点扩缩容）

```yaml
# keda-scaledobject.yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: ray-worker-scaler
  namespace: vlinders-inference
spec:
  scaleTargetRef:
    name: ray-worker-group
  minReplicaCount: 1
  maxReplicaCount: 10
  cooldownPeriod: 300  # 5 minutes

  triggers:
  # 基于 Prometheus 指标扩缩容
  - type: prometheus
    metadata:
      serverAddress: http://prometheus:9090
      metricName: ray_serve_deployment_queued_queries
      threshold: '10'
      query: |
        sum(ray_serve_deployment_queued_queries{deployment="vllm-gpt4"})

  # 基于 GPU 利用率
  - type: prometheus
    metadata:
      serverAddress: http://prometheus:9090
      metricName: gpu_utilization
      threshold: '80'
      query: |
        avg(gpu_utilization_percent)
```

**参考**: [KEDA GPU Autoscaling](https://www.codelink.io/blog/post/cost-optimized-ml-on-production-autoscaling-gpu-nodes-on-kubernetes-to-zero-using-keda)

---

## 🚀 部署流程

### 1. 准备模型

```bash
# 下载模型
python scripts/download_model.py \
  --model meta-llama/Llama-3-70B-Instruct \
  --output /models/llama-3-70b

# 验证模型
python scripts/verify_model.py /models/llama-3-70b
```

### 2. 部署 Ray Cluster

```bash
# 创建命名空间
kubectl create namespace vlinders-inference

# 部署 Ray Cluster
kubectl apply -f k8s/ray-cluster.yaml

# 等待 Ray Cluster 就绪
kubectl wait --for=condition=ready pod \
  -l ray.io/cluster=vlinders-ray-cluster \
  -n vlinders-inference \
  --timeout=600s
```

### 3. 部署推理服务

```bash
# 部署 Ray Serve 应用
serve deploy serve_config.yaml

# 验证部署
serve status

# 测试推理
curl -X POST http://ray-head:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

### 4. 配置监控

```bash
# 部署 Prometheus
helm install prometheus prometheus-community/prometheus \
  -n monitoring \
  -f k8s/prometheus-values.yaml

# 部署 Grafana
helm install grafana grafana/grafana \
  -n monitoring \
  -f k8s/grafana-values.yaml

# 导入仪表板
kubectl apply -f k8s/grafana-dashboards/
```

---

## 🔧 故障排查

### 常见问题

**1. OOM (Out of Memory)**

```bash
# 检查 GPU 内存
kubectl exec -it ray-worker-0 -- nvidia-smi

# 解决方案：
# - 降低 gpu_memory_utilization 到 0.85
# - 减小 max_model_len
# - 增加 tensor_parallel_size
```

**2. 推理延迟高**

```bash
# 检查批处理
kubectl logs ray-worker-0 | grep "batch_size"

# 解决方案：
# - 启用 prefix caching
# - 增加 max_num_seqs
# - 使用量化模型
```

**3. 副本无法启动**

```bash
# 检查日志
kubectl logs -l ray.io/node-type=worker

# 常见原因：
# - 模型文件缺失
# - GPU 资源不足
# - 内存不足
```

---

## 📚 参考资料

- [Ray Serve Production Guide](https://www.anyscale.com/blog/low-latency-generative-ai-model-serving-with-ray-nvidia)
- [vLLM Production Deployment](https://introl.com/blog/vllm-production-deployment-inference-serving-architecture)
- [vLLM Optimization Guide](https://inference.net/content/vllm-docker-deployment/)
- [KEDA GPU Autoscaling](https://www.codelink.io/blog/post/cost-optimized-ml-on-production-autoscaling-gpu-nodes-on-kubernetes-to-zero-using-keda)

---

**状态**: 📝 设计完成
**下一步**: 实施和性能测试
