# 部署检查清单和运维手册

**版本**: v1.0
**创建日期**: 2026-02-28
**状态**: 📝 设计阶段

---

## 📋 部署前检查清单

### 基础设施准备

#### Kubernetes 集群
- [ ] Kubernetes 1.28+ 集群已创建
- [ ] kubectl 配置正确，可以访问集群
- [ ] 集群有足够的资源（CPU、内存、存储）
- [ ] GPU 节点已配置并可用
- [ ] NVIDIA GPU Operator 已安装
- [ ] 网络插件已配置（Calico/Cilium）
- [ ] 存储类已配置（gp3/fast-ssd）

#### 域名和证书
- [ ] 域名已注册（api.vlinders.com）
- [ ] DNS 记录已配置
- [ ] SSL 证书已申请（Let's Encrypt/商业证书）
- [ ] 证书已导入 Kubernetes Secrets

#### 外部服务
- [ ] Stripe 账户已创建
- [ ] Stripe API 密钥已获取
- [ ] Stripe Webhook 已配置
- [ ] S3/对象存储已配置
- [ ] 邮件服务已配置（SendGrid/SES）

---

### 配置文件准备

#### Secrets
- [ ] JWT 密钥对已生成（RS256）
- [ ] 数据库密码已生成（强密码）
- [ ] Internal Secret 已生成
- [ ] Stripe 密钥已配置
- [ ] 所有 Secrets 已创建在 Kubernetes

#### ConfigMaps
- [ ] 服务器配置已准备
- [ ] 模型配置已准备
- [ ] 日志配置已准备

---

### 数据库准备

#### PostgreSQL
- [ ] 数据库实例已创建
- [ ] 数据库用户已创建
- [ ] 初始化脚本已准备
- [ ] 备份策略已配置
- [ ] 连接测试通过

#### Redis
- [ ] Redis 集群已部署
- [ ] 持久化已配置
- [ ] 连接测试通过

#### Qdrant
- [ ] Qdrant 实例已部署
- [ ] Collection 已创建
- [ ] 连接测试通过

---

### 模型准备

#### 模型文件
- [ ] 模型已下载到本地
- [ ] 模型文件完整性已验证
- [ ] 模型已上传到持久化存储
- [ ] PVC 已创建并挂载
- [ ] 模型加载测试通过

---

### 监控准备

#### Prometheus
- [ ] Prometheus 已部署
- [ ] 抓取配置已设置
- [ ] 存储已配置
- [ ] 告警规则已配置

#### Grafana
- [ ] Grafana 已部署
- [ ] 数据源已配置
- [ ] 仪表板已导入
- [ ] 告警通知已配置（Slack/PagerDuty）

#### Loki
- [ ] Loki 已部署
- [ ] Promtail 已配置
- [ ] 日志保留策略已设置

---

## 🚀 部署步骤

### Phase 1: 基础设施部署

```bash
# 1. 创建命名空间
kubectl apply -f k8s/namespaces.yaml

# 2. 创建 Secrets
kubectl create secret generic vlinders-secrets \
  --from-literal=postgres-password=<password> \
  --from-literal=internal-secret=<secret> \
  --from-literal=stripe-secret-key=<key> \
  -n vlinders-platform

# 3. 创建 ConfigMaps
kubectl apply -f k8s/configmap.yaml

# 4. 创建存储
kubectl apply -f k8s/storage.yaml

# 5. 等待 PVC 绑定
kubectl get pvc -n vlinders-platform -w
```

### Phase 2: 数据库部署

```bash
# 1. 部署 PostgreSQL
kubectl apply -f k8s/postgres.yaml

# 2. 等待 PostgreSQL 就绪
kubectl wait --for=condition=ready pod \
  -l app=postgres \
  -n vlinders-platform \
  --timeout=300s

# 3. 初始化数据库
kubectl exec -it postgres-0 -n vlinders-platform -- \
  psql -U vlinders -d vlinders -f /init/01_init.sql

# 4. 验证数据库
kubectl exec -it postgres-0 -n vlinders-platform -- \
  psql -U vlinders -d vlinders -c "\dt"

# 5. 部署 Redis
kubectl apply -f k8s/redis.yaml

# 6. 等待 Redis 就绪
kubectl wait --for=condition=ready pod \
  -l app=redis \
  -n vlinders-platform \
  --timeout=300s
```

### Phase 3: 推理服务部署

```bash
# 1. 部署 Ray Cluster
kubectl apply -f k8s/ray-cluster.yaml

# 2. 等待 Ray Head 就绪
kubectl wait --for=condition=ready pod \
  -l ray.io/node-type=head \
  -n vlinders-inference \
  --timeout=600s

# 3. 检查 Ray Dashboard
kubectl port-forward -n vlinders-inference \
  svc/ray-head 8265:8265

# 访问 http://localhost:8265

# 4. 部署推理服务
ray job submit --address http://localhost:8265 \
  --working-dir ./ray-serve \
  -- python serve_config.py

# 5. 验证推理服务
curl http://localhost:8000/v1/models
```

### Phase 4: API Gateway 部署

```bash
# 1. 部署 Kong Gateway
kubectl apply -f k8s/kong-gateway.yaml

# 2. 等待 Kong 就绪
kubectl wait --for=condition=ready pod \
  -l app=kong-gateway \
  -n vlinders-platform \
  --timeout=300s

# 3. 获取 LoadBalancer IP
kubectl get svc kong-gateway -n vlinders-platform

# 4. 配置 DNS
# 将域名指向 LoadBalancer IP

# 5. 测试 API
curl https://api.vlinders.com/v1/models
```

### Phase 5: 监控部署

```bash
# 1. 部署 Prometheus
helm install prometheus prometheus-community/prometheus \
  -n vlinders-monitoring \
  -f k8s/prometheus-values.yaml

# 2. 部署 Grafana
helm install grafana grafana/grafana \
  -n vlinders-monitoring \
  -f k8s/grafana-values.yaml

# 3. 获取 Grafana 密码
kubectl get secret grafana -n vlinders-monitoring \
  -o jsonpath="{.data.admin-password}" | base64 --decode

# 4. 访问 Grafana
kubectl port-forward -n vlinders-monitoring \
  svc/grafana 3000:80

# 5. 导入仪表板
# 访问 http://localhost:3000
# 导入 k8s/grafana-dashboards/*.json
```

---

## ✅ 部署后验证

### 健康检查

```bash
# 1. 检查所有 Pods
kubectl get pods --all-namespaces

# 2. 检查服务状态
kubectl get svc --all-namespaces

# 3. 检查 PVC
kubectl get pvc --all-namespaces

# 4. 检查 GPU 节点
kubectl get nodes -l nvidia.com/gpu=true
```

### 功能测试

```bash
# 1. 测试用户注册
curl -X POST https://api.vlinders.com/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "Test123!",
    "full_name": "Test User",
    "tenant_name": "Test Tenant"
  }'

# 2. 测试用户登录
curl -X POST https://api.vlinders.com/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "Test123!"
  }'

# 3. 测试推理
curl -X POST https://api.vlinders.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "Hello"}
    ]
  }'
```

### 性能测试

```bash
# 1. 安装 k6
brew install k6  # macOS
# 或
sudo apt install k6  # Ubuntu

# 2. 运行负载测试
k6 run tests/load-test.js

# 3. 检查结果
# - P95 延迟 < 500ms
# - 错误率 < 1%
# - 吞吐量 > 1000 req/s
```

---

## 🔧 日常运维

### 监控检查

#### 每日检查
```bash
# 1. 检查集群健康
kubectl get nodes
kubectl top nodes

# 2. 检查 Pod 状态
kubectl get pods --all-namespaces | grep -v Running

# 3. 检查最近的错误日志
kubectl logs -n vlinders-platform \
  -l app=vlinders-api \
  --since=24h | grep ERROR

# 4. 检查 GPU 使用率
kubectl exec -it <ray-worker-pod> -n vlinders-inference -- \
  nvidia-smi
```

#### 每周检查
- [ ] 检查磁盘使用率
- [ ] 检查数据库性能
- [ ] 检查备份状态
- [ ] 审查告警历史
- [ ] 检查成本使用

#### 每月检查
- [ ] 安全补丁更新
- [ ] 证书过期检查
- [ ] 容量规划评估
- [ ] 性能趋势分析
- [ ] 灾难恢复演练

---

### 常见运维任务

#### 扩容 GPU 节点

```bash
# 1. 增加 Ray Worker 副本数
kubectl scale raycluster vlinders-ray-cluster \
  --replicas=5 \
  -n vlinders-inference

# 2. 验证新节点
kubectl get pods -n vlinders-inference \
  -l ray.io/node-type=worker
```

#### 更新模型

```bash
# 1. 下载新模型
python scripts/download_model.py \
  --model meta-llama/Llama-3.1-70B \
  --output /models/llama-3.1-70b

# 2. 上传到 PVC
kubectl cp /models/llama-3.1-70b \
  vlinders-inference/ray-head-0:/models/

# 3. 更新配置
kubectl edit configmap vlinders-config \
  -n vlinders-platform

# 4. 重启 Ray Serve
ray job submit --address http://ray-head:8265 \
  -- python serve_config.py
```

#### 数据库备份

```bash
# 1. 创建备份
kubectl exec -it postgres-0 -n vlinders-platform -- \
  pg_dump -U vlinders vlinders > backup-$(date +%Y%m%d).sql

# 2. 上传到 S3
aws s3 cp backup-$(date +%Y%m%d).sql \
  s3://vlinders-backups/postgres/

# 3. 验证备份
aws s3 ls s3://vlinders-backups/postgres/
```

#### 恢复数据库

```bash
# 1. 下载备份
aws s3 cp s3://vlinders-backups/postgres/backup-20260228.sql \
  ./backup.sql

# 2. 恢复数据库
kubectl exec -i postgres-0 -n vlinders-platform -- \
  psql -U vlinders vlinders < backup.sql

# 3. 验证恢复
kubectl exec -it postgres-0 -n vlinders-platform -- \
  psql -U vlinders -d vlinders -c "SELECT COUNT(*) FROM users;"
```

---

## 🚨 故障处理

### Pod 无法启动

**症状**: Pod 一直处于 Pending 或 CrashLoopBackOff 状态

**排查步骤**:
```bash
# 1. 查看 Pod 详情
kubectl describe pod <pod-name> -n <namespace>

# 2. 查看日志
kubectl logs <pod-name> -n <namespace>

# 3. 查看事件
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```

**常见原因**:
- 资源不足（CPU/内存/GPU）
- 镜像拉取失败
- 配置错误
- 存储挂载失败

---

### GPU 内存不足

**症状**: `CUDA out of memory` 错误

**解决方案**:
```bash
# 1. 降低 GPU 内存使用率
# 编辑 ConfigMap
kubectl edit configmap vlinders-config -n vlinders-platform

# 修改 gpu_memory_utilization 从 0.9 到 0.85

# 2. 重启服务
kubectl rollout restart deployment <deployment-name>

# 3. 或增加 GPU 数量
# 修改 tensor_parallel_size
```

---

### 推理延迟高

**症状**: P95 延迟 > 1s

**排查步骤**:
```bash
# 1. 检查 GPU 利用率
kubectl exec -it <ray-worker-pod> -n vlinders-inference -- \
  nvidia-smi

# 2. 检查队列积压
curl http://ray-head:8265/api/serve/deployments/

# 3. 查看 Prometheus 指标
# 访问 Grafana 查看延迟趋势
```

**解决方案**:
- 启用前缀缓存
- 增加副本数
- 使用量化模型
- 优化批处理大小

---

### 数据库连接失败

**症状**: `could not connect to server` 错误

**排查步骤**:
```bash
# 1. 检查 PostgreSQL Pod
kubectl get pods -n vlinders-platform -l app=postgres

# 2. 检查服务
kubectl get svc postgres -n vlinders-platform

# 3. 测试连接
kubectl exec -it postgres-0 -n vlinders-platform -- \
  psql -U vlinders -d vlinders -c "SELECT 1;"

# 4. 检查连接数
kubectl exec -it postgres-0 -n vlinders-platform -- \
  psql -U vlinders -d vlinders -c \
  "SELECT count(*) FROM pg_stat_activity;"
```

---

## 📊 性能优化

### GPU 利用率优化

**目标**: GPU 利用率 > 85%

**优化措施**:
1. 启用 Continuous Batching
2. 增加 `max_num_seqs`
3. 启用前缀缓存
4. 使用量化模型

### 成本优化

**目标**: 降低 GPU 成本 30%

**优化措施**:
1. 配置 KEDA 自动扩缩容
2. 使用 Spot 实例
3. 优化模型加载策略
4. 实施请求队列

---

## 📚 参考文档

- [Kubernetes 官方文档](https://kubernetes.io/docs/)
- [Ray Serve 文档](https://docs.ray.io/en/latest/serve/)
- [vLLM 文档](https://docs.vllm.ai/)
- [Prometheus 文档](https://prometheus.io/docs/)

---

## 📞 紧急联系方式

- **运维团队**: ops@vlinders.com
- **技术支持**: support@vlinders.com
- **紧急热线**: +1-xxx-xxx-xxxx
- **PagerDuty**: https://vlinders.pagerduty.com

---

**状态**: 📝 设计完成
**维护**: 持续更新
