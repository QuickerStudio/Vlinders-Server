# Kubernetes 部署配置文档

**版本**: v1.0
**创建日期**: 2026-02-28
**Kubernetes**: 1.28+
**状态**: 📝 设计阶段

---

## 📋 概述

本文档包含 Vlinders Platform 在 Kubernetes 上部署的完整配置文件，包括所有服务、存储、网络和监控组件。

---

## 🏗️ 命名空间

### namespaces.yaml

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: vlinders-platform
  labels:
    name: vlinders-platform
    environment: production

---
apiVersion: v1
kind: Namespace
metadata:
  name: vlinders-inference
  labels:
    name: vlinders-inference
    environment: production

---
apiVersion: v1
kind: Namespace
metadata:
  name: vlinders-monitoring
  labels:
    name: vlinders-monitoring
    environment: production
```

---

## 🔐 Secrets 和 ConfigMaps

### secrets.yaml

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: vlinders-secrets
  namespace: vlinders-platform
type: Opaque
stringData:
  # 数据库
  postgres-url: postgresql://user:password@postgres:5432/vlinders
  redis-url: redis://redis:6379

  # JWT 密钥
  jwt-private-key: |
    -----BEGIN RSA PRIVATE KEY-----
    ...
    -----END RSA PRIVATE KEY-----
  jwt-public-key: |
    -----BEGIN PUBLIC KEY-----
    ...
    -----END PUBLIC KEY-----

  # API 密钥
  internal-secret: your-internal-secret-here

  # Stripe
  stripe-secret-key: sk_live_...
  stripe-webhook-secret: whsec_...

---
apiVersion: v1
kind: Secret
metadata:
  name: model-registry-credentials
  namespace: vlinders-inference
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: <base64-encoded-docker-config>
```

### configmap.yaml

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: vlinders-config
  namespace: vlinders-platform
data:
  server.yaml: |
    server:
      host: 0.0.0.0
      port: 8000
      workers: 4

    logging:
      level: INFO
      format: json

  models.yaml: |
    models:
      - name: gpt-4
        path: /models/llama-3-70b
        tensor_parallel_size: 4
        max_model_len: 32768
        enabled: true

      - name: gpt-3.5-turbo
        path: /models/llama-3-8b
        tensor_parallel_size: 1
        max_model_len: 16384
        enabled: true
```

---

## 💾 持久化存储

### storage.yaml

```yaml
# StorageClass for models
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: fast-ssd
provisioner: kubernetes.io/aws-ebs
parameters:
  type: gp3
  iops: "3000"
  throughput: "125"
volumeBindingMode: WaitForFirstConsumer

---
# PVC for models
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: models-pvc
  namespace: vlinders-inference
spec:
  accessModes:
    - ReadOnlyMany
  storageClassName: fast-ssd
  resources:
    requests:
      storage: 500Gi

---
# PVC for PostgreSQL
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: postgres-pvc
  namespace: vlinders-platform
spec:
  accessModes:
    - ReadWriteOnce
  storageClassName: fast-ssd
  resources:
    requests:
      storage: 100Gi
```

---

## 🗄️ 数据库部署

### postgres.yaml

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: postgres
  namespace: vlinders-platform
spec:
  serviceName: postgres
  replicas: 1
  selector:
    matchLabels:
      app: postgres
  template:
    metadata:
      labels:
        app: postgres
    spec:
      containers:
      - name: postgres
        image: postgres:15-alpine
        ports:
        - containerPort: 5432
          name: postgres
        env:
        - name: POSTGRES_DB
          value: vlinders
        - name: POSTGRES_USER
          value: vlinders
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: vlinders-secrets
              key: postgres-password
        - name: PGDATA
          value: /var/lib/postgresql/data/pgdata
        volumeMounts:
        - name: postgres-storage
          mountPath: /var/lib/postgresql/data
        resources:
          requests:
            cpu: 2000m
            memory: 8Gi
          limits:
            cpu: 4000m
            memory: 16Gi
        livenessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - vlinders
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          exec:
            command:
            - pg_isready
            - -U
            - vlinders
          initialDelaySeconds: 5
          periodSeconds: 5
  volumeClaimTemplates:
  - metadata:
      name: postgres-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 100Gi

---
apiVersion: v1
kind: Service
metadata:
  name: postgres
  namespace: vlinders-platform
spec:
  selector:
    app: postgres
  ports:
  - port: 5432
    targetPort: 5432
  clusterIP: None
```

### redis.yaml

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: redis
  namespace: vlinders-platform
spec:
  serviceName: redis
  replicas: 3
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
          name: redis
        - containerPort: 16379
          name: cluster
        command:
        - redis-server
        - --cluster-enabled
        - "yes"
        - --cluster-config-file
        - /data/nodes.conf
        - --cluster-node-timeout
        - "5000"
        - --appendonly
        - "yes"
        volumeMounts:
        - name: redis-storage
          mountPath: /data
        resources:
          requests:
            cpu: 500m
            memory: 2Gi
          limits:
            cpu: 1000m
            memory: 4Gi
  volumeClaimTemplates:
  - metadata:
      name: redis-storage
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: fast-ssd
      resources:
        requests:
          storage: 10Gi

---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: vlinders-platform
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
    name: redis
  - port: 16379
    targetPort: 16379
    name: cluster
  clusterIP: None
```

---

## 🤖 Ray Cluster 部署

### ray-cluster.yaml

```yaml
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
      num-cpus: '0'
      block: 'true'
    template:
      spec:
        containers:
        - name: ray-head
          image: rayproject/ray-ml:2.9.0-gpu
          ports:
          - containerPort: 6379
            name: gcs
          - containerPort: 8265
            name: dashboard
          - containerPort: 10001
            name: client
          - containerPort: 8000
            name: serve
          resources:
            limits:
              cpu: "8"
              memory: "32Gi"
            requests:
              cpu: "4"
              memory: "16Gi"
          volumeMounts:
          - name: models
            mountPath: /models
            readOnly: true
          - name: config
            mountPath: /app/config
        volumes:
        - name: models
          persistentVolumeClaim:
            claimName: models-pvc
        - name: config
          configMap:
            name: vlinders-config

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
            sizeLimit: 32Gi
        tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule

---
apiVersion: v1
kind: Service
metadata:
  name: ray-head
  namespace: vlinders-inference
spec:
  selector:
    ray.io/node-type: head
  ports:
  - name: dashboard
    port: 8265
    targetPort: 8265
  - name: client
    port: 10001
    targetPort: 10001
  - name: serve
    port: 8000
    targetPort: 8000
```

---

## 🌐 API Gateway

### kong-gateway.yaml

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kong-config
  namespace: vlinders-platform
data:
  kong.yaml: |
    _format_version: "3.0"

    services:
    - name: inference-service
      url: http://ray-head.vlinders-inference:8000
      routes:
      - name: inference-route
        paths:
        - /v1/chat
        - /v1/models
        methods:
        - GET
        - POST
      plugins:
      - name: rate-limiting
        config:
          minute: 100
          policy: redis
          redis_host: redis
      - name: jwt
        config:
          key_claim_name: kid
      - name: prometheus
        config:
          per_consumer: true

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: kong-gateway
  namespace: vlinders-platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app: kong-gateway
  template:
    metadata:
      labels:
        app: kong-gateway
    spec:
      containers:
      - name: kong
        image: kong:3.5
        env:
        - name: KONG_DATABASE
          value: "off"
        - name: KONG_DECLARATIVE_CONFIG
          value: /kong/kong.yaml
        - name: KONG_PROXY_ACCESS_LOG
          value: /dev/stdout
        - name: KONG_ADMIN_ACCESS_LOG
          value: /dev/stdout
        - name: KONG_PROXY_ERROR_LOG
          value: /dev/stderr
        - name: KONG_ADMIN_ERROR_LOG
          value: /dev/stderr
        ports:
        - containerPort: 8000
          name: proxy
        - containerPort: 8443
          name: proxy-ssl
        - containerPort: 8001
          name: admin
        volumeMounts:
        - name: kong-config
          mountPath: /kong
        resources:
          requests:
            cpu: 1000m
            memory: 2Gi
          limits:
            cpu: 2000m
            memory: 4Gi
      volumes:
      - name: kong-config
        configMap:
          name: kong-config

---
apiVersion: v1
kind: Service
metadata:
  name: kong-gateway
  namespace: vlinders-platform
spec:
  type: LoadBalancer
  selector:
    app: kong-gateway
  ports:
  - name: proxy
    port: 80
    targetPort: 8000
  - name: proxy-ssl
    port: 443
    targetPort: 8443
```

---

## 📊 监控栈

### prometheus.yaml

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: vlinders-monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
      evaluation_interval: 15s
      external_labels:
        cluster: 'vlinders-prod'

    scrape_configs:
    - job_name: 'kubernetes-pods'
      kubernetes_sd_configs:
      - role: pod
      relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__

    - job_name: 'ray-serve'
      static_configs:
      - targets: ['ray-head.vlinders-inference:8000']

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: vlinders-monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus
  template:
    metadata:
      labels:
        app: prometheus
    spec:
      containers:
      - name: prometheus
        image: prom/prometheus:v2.48.0
        args:
        - '--config.file=/etc/prometheus/prometheus.yml'
        - '--storage.tsdb.path=/prometheus'
        - '--storage.tsdb.retention.time=15d'
        ports:
        - containerPort: 9090
        volumeMounts:
        - name: config
          mountPath: /etc/prometheus
        - name: storage
          mountPath: /prometheus
        resources:
          requests:
            cpu: 2000m
            memory: 8Gi
          limits:
            cpu: 4000m
            memory: 16Gi
      volumes:
      - name: config
        configMap:
          name: prometheus-config
      - name: storage
        persistentVolumeClaim:
          claimName: prometheus-pvc

---
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  namespace: vlinders-monitoring
spec:
  selector:
    app: prometheus
  ports:
  - port: 9090
    targetPort: 9090
```

---

## 🔄 自动扩缩容

### hpa.yaml

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: kong-gateway-hpa
  namespace: vlinders-platform
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: kong-gateway
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### keda-scaledobject.yaml

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata:
  name: ray-worker-scaler
  namespace: vlinders-inference
spec:
  scaleTargetRef:
    name: vlinders-ray-cluster
    kind: RayCluster
  minReplicaCount: 1
  maxReplicaCount: 10
  cooldownPeriod: 300

  triggers:
  - type: prometheus
    metadata:
      serverAddress: http://prometheus.vlinders-monitoring:9090
      metricName: ray_serve_deployment_queued_queries
      threshold: '10'
      query: |
        sum(ray_serve_deployment_queued_queries)

  - type: prometheus
    metadata:
      serverAddress: http://prometheus.vlinders-monitoring:9090
      metricName: gpu_utilization
      threshold: '80'
      query: |
        avg(gpu_utilization_percent)
```

---

## 🔒 网络策略

### network-policy.yaml

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: vlinders-platform-policy
  namespace: vlinders-platform
spec:
  podSelector:
    matchLabels:
      app: vlinders-api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: vlinders-platform
    - podSelector:
        matchLabels:
          app: kong-gateway
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: vlinders-platform
    ports:
    - protocol: TCP
      port: 5432  # PostgreSQL
    - protocol: TCP
      port: 6379  # Redis
  - to:
    - namespaceSelector:
        matchLabels:
          name: vlinders-inference
    ports:
    - protocol: TCP
      port: 8000  # Ray Serve

---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: vlinders-inference-policy
  namespace: vlinders-inference
spec:
  podSelector:
    matchLabels:
      ray.io/cluster: vlinders-ray-cluster
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: vlinders-platform
    ports:
    - protocol: TCP
      port: 8000
```

---

## 📝 完整部署脚本

### deploy.sh

```bash
#!/bin/bash
set -e

echo "🚀 Deploying Vlinders Platform to Kubernetes..."

# 1. 创建命名空间
echo "📦 Creating namespaces..."
kubectl apply -f namespaces.yaml

# 2. 创建 Secrets
echo "🔐 Creating secrets..."
kubectl apply -f secrets.yaml

# 3. 创建 ConfigMaps
echo "⚙️  Creating configmaps..."
kubectl apply -f configmap.yaml

# 4. 创建存储
echo "💾 Creating storage..."
kubectl apply -f storage.yaml

# 5. 部署数据库
echo "🗄️  Deploying databases..."
kubectl apply -f postgres.yaml
kubectl apply -f redis.yaml

# 等待数据库就绪
echo "⏳ Waiting for databases..."
kubectl wait --for=condition=ready pod \
  -l app=postgres \
  -n vlinders-platform \
  --timeout=300s

kubectl wait --for=condition=ready pod \
  -l app=redis \
  -n vlinders-platform \
  --timeout=300s

# 6. 部署 Ray Cluster
echo "🤖 Deploying Ray Cluster..."
kubectl apply -f ray-cluster.yaml

# 等待 Ray Cluster 就绪
echo "⏳ Waiting for Ray Cluster..."
kubectl wait --for=condition=ready pod \
  -l ray.io/node-type=head \
  -n vlinders-inference \
  --timeout=600s

# 7. 部署 API Gateway
echo "🌐 Deploying API Gateway..."
kubectl apply -f kong-gateway.yaml

# 8. 部署监控
echo "📊 Deploying monitoring stack..."
kubectl apply -f prometheus.yaml

# 9. 配置自动扩缩容
echo "🔄 Configuring autoscaling..."
kubectl apply -f hpa.yaml
kubectl apply -f keda-scaledobject.yaml

# 10. 配置网络策略
echo "🔒 Applying network policies..."
kubectl apply -f network-policy.yaml

echo "✅ Deployment complete!"
echo ""
echo "📊 Check status:"
echo "  kubectl get pods -n vlinders-platform"
echo "  kubectl get pods -n vlinders-inference"
echo "  kubectl get pods -n vlinders-monitoring"
echo ""
echo "🌐 Get LoadBalancer IP:"
echo "  kubectl get svc kong-gateway -n vlinders-platform"
```

---

## 🔍 故障排查

### 常用命令

```bash
# 查看所有 Pods
kubectl get pods --all-namespaces

# 查看 Pod 日志
kubectl logs -f <pod-name> -n <namespace>

# 查看 Pod 详情
kubectl describe pod <pod-name> -n <namespace>

# 进入 Pod
kubectl exec -it <pod-name> -n <namespace> -- /bin/bash

# 查看资源使用
kubectl top nodes
kubectl top pods -n vlinders-inference

# 查看事件
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```

---

**状态**: 📝 设计完成
**下一步**: 测试部署和优化
