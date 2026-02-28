# API 规范文档

**版本**: v1.0
**创建日期**: 2026-02-28
**协议**: REST + OpenAPI 3.0
**状态**: 📝 设计阶段

---

## 📋 概述

本文档定义 Vlinders Platform 的完整 API 规范，遵循 RESTful 设计原则和 OpenAPI 3.0 标准。

### API 设计原则

1. **RESTful**: 使用标准 HTTP 方法和状态码
2. **版本化**: URL 路径包含版本号 `/v1/`
3. **一致性**: 统一的请求/响应格式
4. **安全性**: 所有端点需要认证
5. **向后兼容**: 不破坏现有客户端

---

## 🔐 认证

### Bearer Token

所有 API 请求需要在 Header 中携带 JWT Token：

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...
```

### API Key

机器对机器调用可使用 API Key：

```http
Authorization: Bearer vlinders_sk_live_abc123xyz789
```

---

## 📊 通用响应格式

### 成功响应

```json
{
  "data": {
    // 响应数据
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-02-28T10:30:00Z"
  }
}
```

### 错误响应

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Invalid request parameters",
    "details": [
      {
        "field": "email",
        "message": "Invalid email format"
      }
    ]
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-02-28T10:30:00Z"
  }
}
```

### 错误码

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| `invalid_request` | 400 | 请求参数无效 |
| `unauthorized` | 401 | 未认证 |
| `forbidden` | 403 | 无权限 |
| `not_found` | 404 | 资源不存在 |
| `quota_exceeded` | 429 | 配额超限 |
| `internal_error` | 500 | 服务器错误 |

---

## 🔑 认证 API

### POST /v1/auth/register

用户注册

**请求**:
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!",
  "full_name": "John Doe",
  "tenant_name": "Acme Corp"
}
```

**响应** (201):
```json
{
  "data": {
    "user_id": "user_abc123",
    "email": "user@example.com",
    "tenant_id": "tenant_xyz789",
    "email_verified": false
  }
}
```

---

### POST /v1/auth/login

用户登录

**请求**:
```json
{
  "email": "user@example.com",
  "password": "SecurePass123!"
}
```

**响应** (200):
```json
{
  "data": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJSUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 900
  }
}
```

---

### POST /v1/auth/refresh

刷新 Token

**请求**:
```json
{
  "refresh_token": "eyJhbGciOiJSUzI1NiIs..."
}
```

**响应** (200):
```json
{
  "data": {
    "access_token": "eyJhbGciOiJSUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 900
  }
}
```

---

## 👤 用户 API

### GET /v1/users/me

获取当前用户信息

**响应** (200):
```json
{
  "data": {
    "id": "user_abc123",
    "email": "user@example.com",
    "full_name": "John Doe",
    "avatar_url": "https://cdn.vlinders.com/avatars/abc123.jpg",
    "tenant_id": "tenant_xyz789",
    "roles": ["developer"],
    "created_at": "2026-01-15T10:00:00Z"
  }
}
```

---

### PATCH /v1/users/me

更新用户资料

**请求**:
```json
{
  "full_name": "John Smith",
  "avatar_url": "https://cdn.vlinders.com/avatars/new.jpg"
}
```

**响应** (200):
```json
{
  "data": {
    "id": "user_abc123",
    "email": "user@example.com",
    "full_name": "John Smith",
    "avatar_url": "https://cdn.vlinders.com/avatars/new.jpg",
    "updated_at": "2026-02-28T10:30:00Z"
  }
}
```

---

## 🏢 组织 API

### GET /v1/organizations

列出组织

**查询参数**:
- `page`: 页码（默认 1）
- `limit`: 每页数量（默认 20，最大 100）

**响应** (200):
```json
{
  "data": [
    {
      "id": "org_abc123",
      "name": "Engineering Team",
      "description": "Main engineering organization",
      "member_count": 15,
      "created_at": "2026-01-15T10:00:00Z"
    }
  ],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 1
  }
}
```

---

### POST /v1/organizations

创建组织

**请求**:
```json
{
  "name": "Engineering Team",
  "description": "Main engineering organization"
}
```

**响应** (201):
```json
{
  "data": {
    "id": "org_abc123",
    "name": "Engineering Team",
    "description": "Main engineering organization",
    "created_at": "2026-02-28T10:30:00Z"
  }
}
```

---

## 🤖 推理 API

### POST /v1/chat/completions

聊天推理（OpenAI 兼容）

**请求**:
```json
{
  "model": "gpt-4",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "Hello, how are you?"
    }
  ],
  "max_tokens": 2048,
  "temperature": 0.7,
  "top_p": 0.95,
  "stream": false
}
```

**响应** (200):
```json
{
  "id": "chatcmpl_abc123",
  "object": "chat.completion",
  "created": 1709136000,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! I'm doing well, thank you for asking. How can I help you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 18,
    "total_tokens": 43
  }
}
```

---

### POST /v1/chat/completions (流式)

**请求**:
```json
{
  "model": "gpt-4",
  "messages": [...],
  "stream": true
}
```

**响应** (200, Server-Sent Events):
```
data: {"id":"chatcmpl_abc123","object":"chat.completion.chunk","created":1709136000,"model":"gpt-4","choices":[{"index":0,"delta":{"role":"assistant","content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl_abc123","object":"chat.completion.chunk","created":1709136000,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"chatcmpl_abc123","object":"chat.completion.chunk","created":1709136000,"model":"gpt-4","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

---

### GET /v1/models

列出可用模型

**响应** (200):
```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-4",
      "object": "model",
      "created": 1709136000,
      "owned_by": "vlinders",
      "capabilities": {
        "max_tokens": 32768,
        "supports_streaming": true,
        "supports_function_calling": true
      }
    },
    {
      "id": "gpt-3.5-turbo",
      "object": "model",
      "created": 1709136000,
      "owned_by": "vlinders",
      "capabilities": {
        "max_tokens": 16384,
        "supports_streaming": true,
        "supports_function_calling": true
      }
    }
  ]
}
```

---

## 💳 订阅 API

### GET /v1/subscriptions

获取当前订阅

**响应** (200):
```json
{
  "data": {
    "id": "sub_abc123",
    "tenant_id": "tenant_xyz789",
    "plan": "pro",
    "status": "active",
    "current_period_start": "2026-02-01T00:00:00Z",
    "current_period_end": "2026-03-01T00:00:00Z",
    "cancel_at_period_end": false,
    "created_at": "2026-01-15T10:00:00Z"
  }
}
```

---

### POST /v1/subscriptions

创建订阅

**请求**:
```json
{
  "plan": "pro",
  "payment_method_id": "pm_abc123"
}
```

**响应** (201):
```json
{
  "data": {
    "id": "sub_abc123",
    "plan": "pro",
    "status": "active",
    "client_secret": "seti_abc123_secret_xyz789"
  }
}
```

---

### DELETE /v1/subscriptions/{subscription_id}

取消订阅

**响应** (200):
```json
{
  "data": {
    "id": "sub_abc123",
    "status": "active",
    "cancel_at_period_end": true,
    "canceled_at": "2026-02-28T10:30:00Z"
  }
}
```

---

## 📊 使用量 API

### GET /v1/usage

获取使用量统计

**查询参数**:
- `start_date`: 开始日期（ISO 8601）
- `end_date`: 结束日期（ISO 8601）
- `resource_type`: 资源类型（tokens, requests, storage）

**响应** (200):
```json
{
  "data": {
    "period": {
      "start": "2026-02-01T00:00:00Z",
      "end": "2026-02-28T23:59:59Z"
    },
    "usage": [
      {
        "date": "2026-02-01",
        "resource_type": "tokens",
        "quantity": 125000
      },
      {
        "date": "2026-02-02",
        "resource_type": "tokens",
        "quantity": 98000
      }
    ],
    "total": {
      "tokens": 5420000,
      "requests": 12500
    },
    "limits": {
      "tokens_per_month": 10000000,
      "requests_per_month": 100000
    }
  }
}
```

---

## 🔑 API Key 管理

### GET /v1/api-keys

列出 API Keys

**响应** (200):
```json
{
  "data": [
    {
      "id": "key_abc123",
      "name": "Production API Key",
      "key_prefix": "vlinders_sk_live_abc1",
      "permissions": ["inference:read", "inference:write"],
      "last_used_at": "2026-02-28T09:00:00Z",
      "created_at": "2026-01-15T10:00:00Z"
    }
  ]
}
```

---

### POST /v1/api-keys

创建 API Key

**请求**:
```json
{
  "name": "Production API Key",
  "permissions": ["inference:read", "inference:write"],
  "expires_at": "2027-02-28T00:00:00Z"
}
```

**响应** (201):
```json
{
  "data": {
    "id": "key_abc123",
    "name": "Production API Key",
    "key": "vlinders_sk_live_abc123xyz789",
    "key_prefix": "vlinders_sk_live_abc1",
    "permissions": ["inference:read", "inference:write"],
    "expires_at": "2027-02-28T00:00:00Z",
    "created_at": "2026-02-28T10:30:00Z"
  }
}
```

**⚠️ 警告**: API Key 只会显示一次，请妥善保存！

---

### DELETE /v1/api-keys/{key_id}

撤销 API Key

**响应** (200):
```json
{
  "data": {
    "id": "key_abc123",
    "revoked_at": "2026-02-28T10:30:00Z"
  }
}
```

---

## 📈 分析 API

### GET /v1/analytics/dashboard

获取仪表板统计

**响应** (200):
```json
{
  "data": {
    "period": {
      "start": "2026-02-01T00:00:00Z",
      "end": "2026-02-28T23:59:59Z"
    },
    "metrics": {
      "total_requests": 12500,
      "total_tokens": 5420000,
      "average_latency_ms": 423,
      "error_rate": 0.012,
      "active_users": 45
    },
    "top_models": [
      {
        "model": "gpt-4",
        "requests": 8500,
        "tokens": 3800000
      },
      {
        "model": "gpt-3.5-turbo",
        "requests": 4000,
        "tokens": 1620000
      }
    ]
  }
}
```

---

## 🔄 Webhook

### POST /v1/webhooks

创建 Webhook

**请求**:
```json
{
  "url": "https://example.com/webhook",
  "events": ["inference.completed", "subscription.updated"],
  "secret": "whsec_abc123xyz789"
}
```

**响应** (201):
```json
{
  "data": {
    "id": "webhook_abc123",
    "url": "https://example.com/webhook",
    "events": ["inference.completed", "subscription.updated"],
    "status": "active",
    "created_at": "2026-02-28T10:30:00Z"
  }
}
```

---

### Webhook 事件格式

```json
{
  "id": "evt_abc123",
  "type": "inference.completed",
  "created": 1709136000,
  "data": {
    "object": {
      "id": "inf_xyz789",
      "model": "gpt-4",
      "tokens_used": 1024,
      "latency_ms": 523,
      "status": "completed"
    }
  }
}
```

---

## 📝 分页

所有列表 API 支持分页：

**查询参数**:
- `page`: 页码（从 1 开始）
- `limit`: 每页数量（默认 20，最大 100）

**响应**:
```json
{
  "data": [...],
  "meta": {
    "page": 1,
    "limit": 20,
    "total": 150,
    "total_pages": 8
  }
}
```

---

## 🔍 过滤和排序

**查询参数**:
- `filter[field]`: 过滤条件
- `sort`: 排序字段（前缀 `-` 表示降序）

**示例**:
```
GET /v1/usage?filter[resource_type]=tokens&sort=-date
```

---

## 🚦 限流

**限流规则**:
- Free: 10 req/min
- Pro: 100 req/min
- Enterprise: 1000 req/min

**响应头**:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1709136060
```

**超限响应** (429):
```json
{
  "error": {
    "code": "rate_limit_exceeded",
    "message": "Rate limit exceeded. Please try again later.",
    "retry_after": 60
  }
}
```

---

## 📚 OpenAPI 规范

完整的 OpenAPI 3.0 规范文件：

```yaml
openapi: 3.0.0
info:
  title: Vlinders Platform API
  version: 1.0.0
  description: Enterprise AI Inference Platform
  contact:
    email: api@vlinders.com

servers:
  - url: https://api.vlinders.com/v1
    description: Production
  - url: https://api-staging.vlinders.com/v1
    description: Staging

security:
  - BearerAuth: []

components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT

  schemas:
    Error:
      type: object
      properties:
        error:
          type: object
          properties:
            code:
              type: string
            message:
              type: string
            details:
              type: array
              items:
                type: object

    User:
      type: object
      properties:
        id:
          type: string
        email:
          type: string
        full_name:
          type: string
        created_at:
          type: string
          format: date-time

    # ... 更多 schemas
```

---

## 🔐 安全最佳实践

1. **HTTPS Only**: 所有请求必须使用 HTTPS
2. **Token 过期**: Access Token 15分钟过期
3. **Rate Limiting**: 防止滥用
4. **输入验证**: 严格验证所有输入
5. **CORS**: 配置正确的 CORS 策略

---

## 📞 支持

- **API 文档**: https://docs.vlinders.com/api
- **状态页面**: https://status.vlinders.com
- **支持邮箱**: api-support@vlinders.com

---

**状态**: 📝 设计完成
**下一步**: 实现和测试
