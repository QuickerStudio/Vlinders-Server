# 安全框架设计文档

**版本**: v1.0
**创建日期**: 2026-02-28
**负责人**: Security Team
**状态**: 📝 设计阶段

---

## 📋 概述

本文档详细描述 Vlinders Platform 的安全框架设计，包括认证、授权、加密、审计等核心安全机制。

### 设计目标

1. **零信任架构**: 永不信任，始终验证
2. **纵深防御**: 多层安全防护
3. **最小权限**: 最小化访问权限
4. **完整审计**: 所有操作可追溯
5. **合规性**: 满足 GDPR、SOC 2 等要求

---

## 🔐 认证系统 (Authentication)

### 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     认证流程                                  │
│                                                              │
│  1. 用户登录                                                  │
│     ↓                                                        │
│  2. OAuth2 Authorization Server                             │
│     ├─ 验证凭据                                              │
│     ├─ 生成 Access Token (JWT, 15分钟)                      │
│     └─ 生成 Refresh Token (30天)                            │
│     ↓                                                        │
│  3. 返回 Tokens                                              │
│     ↓                                                        │
│  4. 客户端携带 Access Token 访问 API                         │
│     ↓                                                        │
│  5. API Gateway 验证 Token                                   │
│     ├─ 验证签名 (RS256)                                      │
│     ├─ 检查过期时间                                          │
│     ├─ 检查撤销列表                                          │
│     └─ 提取用户信息                                          │
│     ↓                                                        │
│  6. 转发到后端服务                                            │
└─────────────────────────────────────────────────────────────┘
```

### OAuth2 + OpenID Connect

**选择理由**:
- 行业标准，成熟稳定
- 支持多种授权流程
- 良好的生态系统

**支持的授权流程**:

1. **Authorization Code Flow** (Web 应用)
   ```
   用户 → 授权页面 → 授权码 → Access Token
   ```

2. **Client Credentials Flow** (服务间调用)
   ```
   Service → Client ID + Secret → Access Token
   ```

3. **Device Code Flow** (CLI/设备)
   ```
   设备 → 设备码 → 用户授权 → Access Token
   ```

### JWT Token 设计

**Access Token** (15分钟有效期):
```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT",
    "kid": "key-2026-02"
  },
  "payload": {
    "iss": "https://auth.vlinders.com",
    "sub": "user_123456",
    "aud": "vlinders-api",
    "exp": 1709136000,
    "iat": 1709135100,
    "tenant_id": "tenant_abc",
    "roles": ["user", "developer"],
    "permissions": ["inference:read", "inference:write"],
    "plan": "pro"
  },
  "signature": "..."
}
```

**Refresh Token** (30天有效期):
```json
{
  "jti": "refresh_xyz789",
  "sub": "user_123456",
  "exp": 1711728000,
  "token_type": "refresh"
}
```

### 密钥管理

**密钥轮换策略**:
- 每 90 天轮换一次签名密钥
- 保留旧密钥 30 天用于验证
- 使用 KMS (AWS KMS / HashiCorp Vault)

**密钥存储**:
```yaml
# Kubernetes Secret
apiVersion: v1
kind: Secret
metadata:
  name: jwt-keys
type: Opaque
data:
  private-key: <base64-encoded-private-key>
  public-key: <base64-encoded-public-key>
```

### API Key 认证

**用于机器对机器调用**:

```
Authorization: Bearer vlinders_sk_live_abc123xyz789
```

**API Key 格式**:
```
vlinders_{env}_{type}_{random}
- env: test / live
- type: sk (secret key) / pk (public key)
- random: 24字符随机字符串
```

**存储**:
```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    key_hash VARCHAR(64) NOT NULL,  -- SHA-256 hash
    key_prefix VARCHAR(20) NOT NULL,  -- 用于显示
    name VARCHAR(100),
    permissions JSONB,
    last_used_at TIMESTAMP,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    revoked_at TIMESTAMP,
    INDEX idx_key_hash (key_hash),
    INDEX idx_tenant_id (tenant_id)
);
```

---

## 🛡️ 授权系统 (Authorization)

### RBAC (Role-Based Access Control)

**角色层级**:
```
Super Admin (平台管理员)
  └─ Tenant Admin (租户管理员)
      ├─ Developer (开发者)
      ├─ Analyst (分析师)
      └─ Viewer (查看者)
```

**权限模型**:
```
资源:操作
- inference:read      # 查看推理结果
- inference:write     # 发起推理请求
- model:read          # 查看模型列表
- model:manage        # 管理模型
- user:read           # 查看用户
- user:manage         # 管理用户
- billing:read        # 查看账单
- billing:manage      # 管理订阅
```

**数据库设计**:
```sql
-- 角色表
CREATE TABLE roles (
    id UUID PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,
    permissions JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 用户角色关联
CREATE TABLE user_roles (
    user_id UUID NOT NULL,
    role_id UUID NOT NULL,
    tenant_id UUID NOT NULL,
    granted_at TIMESTAMP DEFAULT NOW(),
    granted_by UUID,
    PRIMARY KEY (user_id, role_id, tenant_id)
);

-- 权限检查函数
CREATE FUNCTION check_permission(
    p_user_id UUID,
    p_tenant_id UUID,
    p_permission VARCHAR
) RETURNS BOOLEAN AS $$
BEGIN
    RETURN EXISTS (
        SELECT 1
        FROM user_roles ur
        JOIN roles r ON ur.role_id = r.id
        WHERE ur.user_id = p_user_id
          AND ur.tenant_id = p_tenant_id
          AND r.permissions ? p_permission
    );
END;
$$ LANGUAGE plpgsql;
```

### ABAC (Attribute-Based Access Control)

**用于细粒度控制**:

```python
# 策略示例
policy = {
    "effect": "allow",
    "actions": ["inference:write"],
    "resources": ["model:gpt-4"],
    "conditions": {
        "tenant_plan": {"in": ["pro", "enterprise"]},
        "time": {"between": ["09:00", "18:00"]},
        "ip": {"in_range": "10.0.0.0/8"}
    }
}
```

### 权限检查中间件

```python
from fastapi import Depends, HTTPException
from typing import List

async def require_permissions(
    required_permissions: List[str],
    token: dict = Depends(verify_token)
) -> dict:
    """检查用户权限"""
    user_permissions = token.get("permissions", [])

    for perm in required_permissions:
        if perm not in user_permissions:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {perm}"
            )

    return token

# 使用示例
@app.post("/inference")
async def create_inference(
    request: InferenceRequest,
    user: dict = Depends(require_permissions(["inference:write"]))
):
    # 业务逻辑
    pass
```

---

## 🔒 数据加密

### 传输加密 (TLS)

**配置**:
- TLS 1.3 (最低 TLS 1.2)
- 强加密套件: `TLS_AES_256_GCM_SHA384`
- HSTS (HTTP Strict Transport Security)
- Certificate Pinning (移动端)

**Nginx 配置**:
```nginx
server {
    listen 443 ssl http2;
    server_name api.vlinders.com;

    ssl_certificate /etc/ssl/certs/vlinders.crt;
    ssl_certificate_key /etc/ssl/private/vlinders.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256';
    ssl_prefer_server_ciphers on;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
}
```

### 存储加密

**数据库加密**:
- PostgreSQL: `pgcrypto` 扩展
- 敏感字段加密 (AES-256-GCM)

```sql
-- 加密敏感数据
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE user_secrets (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    encrypted_data BYTEA NOT NULL,  -- AES-256-GCM 加密
    encryption_key_id VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 加密函数
CREATE FUNCTION encrypt_data(
    p_data TEXT,
    p_key BYTEA
) RETURNS BYTEA AS $$
BEGIN
    RETURN pgp_sym_encrypt(p_data, p_key, 'cipher-algo=aes256');
END;
$$ LANGUAGE plpgsql;
```

**文件加密**:
- 使用 AWS S3 Server-Side Encryption (SSE-KMS)
- 或客户端加密后上传

---

## 📝 审计日志

### 日志内容

**记录所有敏感操作**:
- 用户登录/登出
- 权限变更
- 数据访问
- 配置修改
- API 调用

**日志格式**:
```json
{
  "timestamp": "2026-02-28T10:30:00Z",
  "event_type": "user.login",
  "actor": {
    "user_id": "user_123",
    "ip": "203.0.113.1",
    "user_agent": "Mozilla/5.0..."
  },
  "resource": {
    "type": "session",
    "id": "session_xyz"
  },
  "action": "create",
  "result": "success",
  "metadata": {
    "mfa_used": true,
    "login_method": "oauth2"
  }
}
```

### 日志存储

**架构**:
```
Application → OpenTelemetry → Loki → Grafana
                            ↓
                        Long-term Storage (S3)
```

**保留策略**:
- 热数据: 30 天 (Loki)
- 温数据: 1 年 (S3 Standard)
- 冷数据: 7 年 (S3 Glacier)

---

## 🚨 安全监控和告警

### 异常检测

**监控指标**:
- 失败登录次数 (> 5次/5分钟)
- 异常 IP 访问
- 权限提升操作
- 大量数据导出
- API 调用异常

**告警规则**:
```yaml
# Prometheus Alert Rules
groups:
  - name: security_alerts
    rules:
      - alert: HighFailedLoginRate
        expr: rate(auth_failed_login_total[5m]) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High failed login rate detected"

      - alert: UnauthorizedAccessAttempt
        expr: rate(api_403_errors_total[1m]) > 10
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Multiple unauthorized access attempts"
```

### 入侵检测

**工具**:
- **Falco**: Kubernetes 运行时安全
- **OSSEC**: 主机入侵检测
- **Snort**: 网络入侵检测

---

## 🔍 安全测试

### 自动化扫描

**工具链**:
- **Trivy**: 容器镜像扫描
- **OWASP ZAP**: Web 应用扫描
- **SonarQube**: 代码质量和安全
- **Dependabot**: 依赖漏洞扫描

**CI/CD 集成**:
```yaml
# GitHub Actions
name: Security Scan
on: [push, pull_request]

jobs:
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Run Trivy
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          severity: 'CRITICAL,HIGH'

      - name: Run OWASP ZAP
        uses: zaproxy/action-baseline@v0.7.0
        with:
          target: 'https://api.vlinders.com'
```

### 渗透测试

**频率**: 每季度一次

**范围**:
- Web 应用
- API 端点
- 基础设施
- 社会工程

---

## 📚 安全最佳实践

### 开发规范

1. **输入验证**: 所有用户输入必须验证
2. **参数化查询**: 防止 SQL 注入
3. **输出编码**: 防止 XSS
4. **CSRF 保护**: 使用 CSRF Token
5. **安全头**: 设置安全相关 HTTP 头

### 运维规范

1. **最小权限**: 遵循最小权限原则
2. **定期更新**: 及时更新依赖和补丁
3. **备份**: 定期备份关键数据
4. **监控**: 24/7 安全监控
5. **应急响应**: 制定安全事件响应计划

---

## 📞 安全联系方式

- **安全团队邮箱**: security@vlinders.com
- **漏洞报告**: https://vlinders.com/security
- **PGP 公钥**: [链接]

---

## 参考资料

- [OAuth2 Best Practices](https://curity.io/blog/api-security-trends-2026/)
- [Microservices Security](https://www.osohq.com/learn/microservices-security)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)

---

**状态**: 📝 设计完成
**下一步**: 实施和测试
