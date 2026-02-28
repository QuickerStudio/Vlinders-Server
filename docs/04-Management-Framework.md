# 管理框架设计文档

**版本**: v1.0
**创建日期**: 2026-02-28
**负责人**: DevOps Team
**状态**: 📝 设计阶段

---

## 📋 概述

本文档详细描述 Vlinders Platform 的管理框架，包括监控、日志、追踪、告警等完整的可观测性解决方案。

### 设计目标

1. **全栈可观测性**: Metrics + Logs + Traces 三位一体
2. **实时监控**: 秒级数据采集和展示
3. **智能告警**: 准确的异常检测和通知
4. **问题定位**: 快速定位和诊断问题
5. **成本分析**: 资源使用和成本追踪

---

## 🏗️ 可观测性架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    可观测性架构                                   │
│                                                                  │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              应用层                                      │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐            │    │
│  │  │ API      │  │ Inference│  │ User Svc │            │    │
│  │  │ Gateway  │  │ Service  │  │          │            │    │
│  │  └──────────┘  └──────────┘  └──────────┘            │    │
│  │       │              │              │                  │    │
│  │       └──────────────┴──────────────┘                  │    │
│  │                      ↓                                  │    │
│  │         OpenTelemetry SDK (自动埋点)                    │    │
│  └────────────────────────────────────────────────────────┘    │
│                           ↓                                      │
│  ┌────────────────────────────────────────────────────────┐    │
│  │         OpenTelemetry Collector (采集层)                │    │
│  │  - 接收 Traces/Metrics/Logs                            │    │
│  │  - 数据处理和转换                                        │    │
│  │  - 路由到不同后端                                        │    │
│  └────────────────────────────────────────────────────────┘    │
│         │              │              │                          │
│         ↓              ↓              ↓                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                     │
│  │ Tempo    │  │Prometheus│  │  Loki    │                     │
│  │ (Traces) │  │(Metrics) │  │  (Logs)  │                     │
│  └──────────┘  └──────────┘  └──────────┘                     │
│         │              │              │                          │
│         └──────────────┴──────────────┘                          │
│                      ↓                                           │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              Grafana (可视化层)                         │    │
│  │  - 统一仪表板                                            │    │
│  │  - 告警管理                                              │    │
│  │  - 查询和分析                                            │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

**参考**: [OpenTelemetry + Prometheus + Grafana](https://grafana.com/blog/2023/07/20/a-practical-guide-to-data-collection-with-opentelemetry-and-prometheus/)

---

## 📊 Metrics (指标监控)

### Prometheus 部署

```yaml
# prometheus-values.yaml
server:
  global:
    scrape_interval: 15s
    evaluation_interval: 15s
    external_labels:
      cluster: 'vlinders-prod'
      environment: 'production'

  retention: 15d  # 保留 15 天

  persistentVolume:
    enabled: true
    size: 100Gi

  resources:
    limits:
      cpu: 2000m
      memory: 8Gi
    requests:
      cpu: 1000m
      memory: 4Gi

  # Scrape 配置
  scrapeConfigs:
    # Kubernetes 节点
    - job_name: 'kubernetes-nodes'
      kubernetes_sd_configs:
        - role: node
      relabel_configs:
        - source_labels: [__address__]
          regex: '(.*):10250'
          replacement: '${1}:9100'
          target_label: __address__

    # Kubernetes Pods
    - job_name: 'kubernetes-pods'
      kubernetes_sd_configs:
        - role: pod
      relabel_configs:
        - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
          action: keep
          regex: true

    # Ray Serve
    - job_name: 'ray-serve'
      static_configs:
        - targets: ['ray-head:8000']

    # vLLM
    - job_name: 'vllm'
      static_configs:
        - targets: ['vllm-exporter:9090']

alertmanager:
  enabled: true
  persistentVolume:
    enabled: true
    size: 10Gi
```

### 核心指标定义

```python
# metrics.py
from prometheus_client import Counter, Histogram, Gauge, Info
from functools import wraps
import time

# ==================== 业务指标 ====================

# 请求指标
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# 推理指标
inference_requests_total = Counter(
    'inference_requests_total',
    'Total inference requests',
    ['model', 'tenant_id', 'status']
)

inference_latency_seconds = Histogram(
    'inference_latency_seconds',
    'Inference latency',
    ['model'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

inference_tokens_total = Counter(
    'inference_tokens_total',
    'Total tokens generated',
    ['model', 'tenant_id']
)

# 队列指标
inference_queue_size = Gauge(
    'inference_queue_size',
    'Number of requests in queue',
    ['model']
)

# ==================== 系统指标 ====================

# GPU 指标
gpu_utilization_percent = Gauge(
    'gpu_utilization_percent',
    'GPU utilization percentage',
    ['gpu_id', 'node']
)

gpu_memory_used_bytes = Gauge(
    'gpu_memory_used_bytes',
    'GPU memory used in bytes',
    ['gpu_id', 'node']
)

gpu_temperature_celsius = Gauge(
    'gpu_temperature_celsius',
    'GPU temperature',
    ['gpu_id', 'node']
)

# Ray Serve 指标
ray_serve_deployment_replicas = Gauge(
    'ray_serve_deployment_replicas',
    'Number of deployment replicas',
    ['deployment']
)

ray_serve_deployment_queued_queries = Gauge(
    'ray_serve_deployment_queued_queries',
    'Number of queued queries',
    ['deployment']
)

# ==================== 业务指标 ====================

# 用户指标
active_users_total = Gauge(
    'active_users_total',
    'Number of active users',
    ['tenant_id']
)

# 订阅指标
subscriptions_total = Gauge(
    'subscriptions_total',
    'Total subscriptions',
    ['plan', 'status']
)

# 收入指标
revenue_total = Counter(
    'revenue_total',
    'Total revenue in cents',
    ['plan', 'currency']
)

# ==================== 装饰器 ====================

def track_request_metrics(func):
    """追踪 HTTP 请求指标"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        status = 200

        try:
            result = await func(*args, **kwargs)
            return result
        except Exception as e:
            status = 500
            raise
        finally:
            duration = time.time() - start_time
            http_requests_total.labels(
                method=request.method,
                endpoint=request.url.path,
                status=status
            ).inc()
            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=request.url.path
            ).observe(duration)

    return wrapper

def track_inference_metrics(func):
    """追踪推理指标"""
    @wraps(func)
    async def wrapper(model: str, tenant_id: str, *args, **kwargs):
        start_time = time.time()
        status = "success"

        try:
            result = await func(model, tenant_id, *args, **kwargs)

            # 记录 token 使用
            if "usage" in result:
                inference_tokens_total.labels(
                    model=model,
                    tenant_id=tenant_id
                ).inc(result["usage"]["total_tokens"])

            return result

        except Exception as e:
            status = "error"
            raise

        finally:
            duration = time.time() - start_time

            inference_requests_total.labels(
                model=model,
                tenant_id=tenant_id,
                status=status
            ).inc()

            inference_latency_seconds.labels(
                model=model
            ).observe(duration)

    return wrapper
```

### GPU 监控

```python
# gpu_exporter.py
import pynvml
from prometheus_client import start_http_server
import time

class GPUExporter:
    """GPU 指标导出器"""

    def __init__(self):
        pynvml.nvmlInit()
        self.device_count = pynvml.nvmlDeviceGetCount()

    def collect_metrics(self):
        """采集 GPU 指标"""

        for i in range(self.device_count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)

            # 利用率
            utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
            gpu_utilization_percent.labels(
                gpu_id=str(i),
                node=os.environ.get("NODE_NAME", "unknown")
            ).set(utilization.gpu)

            # 内存
            memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
            gpu_memory_used_bytes.labels(
                gpu_id=str(i),
                node=os.environ.get("NODE_NAME", "unknown")
            ).set(memory.used)

            # 温度
            temperature = pynvml.nvmlDeviceGetTemperature(
                handle,
                pynvml.NVML_TEMPERATURE_GPU
            )
            gpu_temperature_celsius.labels(
                gpu_id=str(i),
                node=os.environ.get("NODE_NAME", "unknown")
            ).set(temperature)

    def run(self, port=9090):
        """启动导出器"""
        start_http_server(port)

        while True:
            self.collect_metrics()
            time.sleep(15)  # 每 15 秒采集一次

if __name__ == "__main__":
    exporter = GPUExporter()
    exporter.run()
```

---

## 📝 Logs (日志管理)

### Loki 部署

```yaml
# loki-values.yaml
loki:
  auth_enabled: false

  server:
    http_listen_port: 3100

  ingester:
    lifecycler:
      ring:
        kvstore:
          store: inmemory
        replication_factor: 1
    chunk_idle_period: 5m
    chunk_retain_period: 30s

  schema_config:
    configs:
      - from: 2024-01-01
        store: boltdb-shipper
        object_store: s3
        schema: v11
        index:
          prefix: loki_index_
          period: 24h

  storage_config:
    boltdb_shipper:
      active_index_directory: /loki/index
      cache_location: /loki/cache
      shared_store: s3
    aws:
      s3: s3://us-east-1/vlinders-logs
      s3forcepathstyle: true

  limits_config:
    enforce_metric_name: false
    reject_old_samples: true
    reject_old_samples_max_age: 168h  # 7 days
    ingestion_rate_mb: 10
    ingestion_burst_size_mb: 20

  chunk_store_config:
    max_look_back_period: 0s

  table_manager:
    retention_deletes_enabled: true
    retention_period: 2160h  # 90 days

promtail:
  enabled: true
  config:
    clients:
      - url: http://loki:3100/loki/api/v1/push
```

### 结构化日志

```python
# logging_config.py
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """JSON 格式化器"""

    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 添加额外字段
        if hasattr(record, "tenant_id"):
            log_data["tenant_id"] = record.tenant_id

        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id

        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)

def setup_logging():
    """配置日志"""

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    return logger

# 使用示例
logger = setup_logging()

logger.info(
    "Inference request completed",
    extra={
        "tenant_id": "tenant_123",
        "user_id": "user_456",
        "request_id": "req_789",
        "model": "gpt-4",
        "tokens": 1024,
        "latency_ms": 523
    }
)
```

### 日志查询

```python
# log_query.py
import requests

class LokiClient:
    """Loki 客户端"""

    def __init__(self, url="http://loki:3100"):
        self.url = url

    def query(
        self,
        query: str,
        start: str = "1h",
        limit: int = 100
    ):
        """查询日志"""

        response = requests.get(
            f"{self.url}/loki/api/v1/query_range",
            params={
                "query": query,
                "start": start,
                "limit": limit
            }
        )

        return response.json()

# 使用示例
client = LokiClient()

# 查询特定租户的错误日志
logs = client.query(
    query='{tenant_id="tenant_123"} |= "ERROR"',
    start="24h"
)

# 查询推理延迟 > 1s 的日志
logs = client.query(
    query='{job="inference"} | json | latency_ms > 1000',
    start="1h"
)
```

---

## 🔍 Traces (分布式追踪)

### Tempo 部署

```yaml
# tempo-values.yaml
tempo:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: 0.0.0.0:4317
        http:
          endpoint: 0.0.0.0:4318

  storage:
    trace:
      backend: s3
      s3:
        bucket: vlinders-traces
        endpoint: s3.amazonaws.com
        region: us-east-1

  retention: 720h  # 30 days

  resources:
    limits:
      cpu: 2000m
      memory: 4Gi
    requests:
      cpu: 1000m
      memory: 2Gi
```

### OpenTelemetry 集成

```python
# tracing.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

def setup_tracing(service_name: str):
    """配置分布式追踪"""

    # 创建 TracerProvider
    provider = TracerProvider(
        resource=Resource.create({
            "service.name": service_name,
            "service.version": "1.0.0",
            "deployment.environment": "production"
        })
    )

    # 配置 OTLP 导出器
    otlp_exporter = OTLPSpanExporter(
        endpoint="http://tempo:4317",
        insecure=True
    )

    # 添加 Span 处理器
    provider.add_span_processor(
        BatchSpanProcessor(otlp_exporter)
    )

    # 设置全局 TracerProvider
    trace.set_tracer_provider(provider)

    return trace.get_tracer(service_name)

# 自动埋点
def instrument_app(app: FastAPI):
    """自动埋点 FastAPI 应用"""

    # FastAPI 埋点
    FastAPIInstrumentor.instrument_app(app)

    # HTTP 客户端埋点
    HTTPXClientInstrumentor().instrument()

    # 数据库埋点
    AsyncPGInstrumentor().instrument()

# 手动埋点示例
tracer = setup_tracing("inference-service")

@app.post("/inference")
async def inference(request: InferenceRequest):
    with tracer.start_as_current_span("inference") as span:
        # 添加属性
        span.set_attribute("model", request.model)
        span.set_attribute("tenant_id", request.tenant_id)

        # 子 Span
        with tracer.start_as_current_span("load_model"):
            model = await load_model(request.model)

        with tracer.start_as_current_span("generate"):
            result = await model.generate(request.prompt)

        # 记录事件
        span.add_event("inference_completed", {
            "tokens": result["usage"]["total_tokens"]
        })

        return result
```

---

## 🚨 告警系统

### Alertmanager 配置

```yaml
# alertmanager-config.yaml
global:
  resolve_timeout: 5m
  slack_api_url: 'https://hooks.slack.com/services/xxx'

route:
  group_by: ['alertname', 'cluster', 'service']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'

  routes:
    # 严重告警 -> PagerDuty
    - match:
        severity: critical
      receiver: 'pagerduty'
      continue: true

    # 警告 -> Slack
    - match:
        severity: warning
      receiver: 'slack'

receivers:
  - name: 'default'
    slack_configs:
      - channel: '#alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'xxx'

  - name: 'slack'
    slack_configs:
      - channel: '#warnings'
```

### 告警规则

```yaml
# alert-rules.yaml
groups:
  - name: inference_alerts
    interval: 30s
    rules:
      # 高延迟告警
      - alert: HighInferenceLatency
        expr: |
          histogram_quantile(0.95,
            rate(inference_latency_seconds_bucket[5m])
          ) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High inference latency"
          description: "P95 latency is {{ $value }}s"

      # GPU 利用率低
      - alert: LowGPUUtilization
        expr: avg(gpu_utilization_percent) < 30
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Low GPU utilization"
          description: "GPU utilization is {{ $value }}%"

      # 推理失败率高
      - alert: HighInferenceErrorRate
        expr: |
          rate(inference_requests_total{status="error"}[5m])
          /
          rate(inference_requests_total[5m])
          > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High inference error rate"
          description: "Error rate is {{ $value | humanizePercentage }}"

      # 队列积压
      - alert: InferenceQueueBacklog
        expr: inference_queue_size > 100
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Inference queue backlog"
          description: "Queue size is {{ $value }}"

  - name: system_alerts
    interval: 30s
    rules:
      # GPU 温度过高
      - alert: HighGPUTemperature
        expr: gpu_temperature_celsius > 85
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High GPU temperature"
          description: "GPU {{ $labels.gpu_id }} temperature is {{ $value }}°C"

      # 内存使用率高
      - alert: HighMemoryUsage
        expr: |
          (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes)
          /
          node_memory_MemTotal_bytes
          > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value | humanizePercentage }}"

      # Pod 重启频繁
      - alert: PodRestartingFrequently
        expr: rate(kube_pod_container_status_restarts_total[1h]) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Pod restarting frequently"
          description: "Pod {{ $labels.pod }} restarted {{ $value }} times"
```

---

## 📊 Grafana 仪表板

### 主仪表板

```json
{
  "dashboard": {
    "title": "Vlinders Platform Overview",
    "tags": ["overview"],
    "timezone": "browser",
    "panels": [
      {
        "title": "Requests per Second",
        "type": "graph",
        "targets": [{
          "expr": "sum(rate(http_requests_total[5m]))"
        }]
      },
      {
        "title": "P95 Latency",
        "type": "graph",
        "targets": [{
          "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
        }]
      },
      {
        "title": "Error Rate",
        "type": "graph",
        "targets": [{
          "expr": "sum(rate(http_requests_total{status=~\"5..\"}[5m])) / sum(rate(http_requests_total[5m]))"
        }]
      },
      {
        "title": "Active Users",
        "type": "stat",
        "targets": [{
          "expr": "sum(active_users_total)"
        }]
      },
      {
        "title": "GPU Utilization",
        "type": "gauge",
        "targets": [{
          "expr": "avg(gpu_utilization_percent)"
        }]
      },
      {
        "title": "Inference Throughput",
        "type": "graph",
        "targets": [{
          "expr": "sum(rate(inference_requests_total[5m])) by (model)"
        }]
      }
    ]
  }
}
```

---

## 💰 成本分析

### 成本追踪

```python
# cost_tracker.py
class CostTracker:
    """成本追踪"""

    # 成本配置
    COSTS = {
        "gpu_a100_80gb_hour": 3.06,  # USD per hour
        "cpu_core_hour": 0.05,
        "memory_gb_hour": 0.01,
        "storage_gb_month": 0.10,
        "network_gb": 0.09,
    }

    async def calculate_inference_cost(
        self,
        model: str,
        duration_seconds: float,
        gpu_count: int = 1
    ) -> float:
        """计算推理成本"""

        hours = duration_seconds / 3600
        gpu_cost = hours * gpu_count * self.COSTS["gpu_a100_80gb_hour"]

        return gpu_cost

    async def get_tenant_cost(
        self,
        tenant_id: str,
        start_date: date,
        end_date: date
    ) -> Dict:
        """获取租户成本"""

        # 查询使用量
        usage = await self.db.fetch(
            """
            SELECT
                resource_type,
                SUM(quantity) as total
            FROM usage_records
            WHERE tenant_id = $1
              AND recorded_at BETWEEN $2 AND $3
            GROUP BY resource_type
            """,
            tenant_id,
            start_date,
            end_date
        )

        # 计算成本
        total_cost = 0
        breakdown = {}

        for record in usage:
            if record["resource_type"] == "gpu_seconds":
                cost = (record["total"] / 3600) * self.COSTS["gpu_a100_80gb_hour"]
                breakdown["gpu"] = cost
                total_cost += cost

        return {
            "total_cost": total_cost,
            "breakdown": breakdown,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            }
        }
```

---

## 📚 参考资料

- [OpenTelemetry + Prometheus + Grafana](https://grafana.com/blog/2023/07/20/a-practical-guide-to-data-collection-with-opentelemetry-and-prometheus/)
- [FastAPI Observability](https://blueswen.hashnode.dev/enable-observability-for-fastapi-service-with-opentelemetry-prometheus-and-grafana)
- [Kubernetes Observability](https://www.stackgenie.io/kubernetes-observability-prometheus-opentelemetry-grafana/)

---

**状态**: 📝 设计完成
**下一步**: 实施和集成测试
