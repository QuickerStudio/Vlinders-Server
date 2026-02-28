# 用户服务框架设计文档

**版本**: v1.0
**创建日期**: 2026-02-28
**负责人**: Backend Team
**状态**: 📝 设计阶段

---

## 📋 概述

本文档详细描述 Vlinders Platform 的用户服务框架，包括多租户架构、用户管理、组织管理、订阅计费等核心功能。

### 设计目标

1. **多租户隔离**: 数据完全隔离，支持数千个租户
2. **灵活计费**: 支持多种订阅模式和计费方式
3. **可扩展性**: 支持百万级用户
4. **自助服务**: 用户可自主管理账户和订阅
5. **合规性**: 满足 GDPR、CCPA 等数据保护要求

---

## 🏢 多租户架构

### 架构模式选择

**采用：共享数据库 + Row-Level Security (RLS)**

```
┌─────────────────────────────────────────────────────────────┐
│                    多租户架构                                 │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Tenant A    │  │  Tenant B    │  │  Tenant C    │     │
│  │  (用户1-100) │  │  (用户1-50)  │  │  (用户1-200) │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                 │                 │               │
│         └─────────────────┴─────────────────┘               │
│                           ↓                                  │
│              ┌────────────────────────┐                     │
│              │   Application Layer    │                     │
│              │  (tenant_id 注入)      │                     │
│              └────────────────────────┘                     │
│                           ↓                                  │
│              ┌────────────────────────┐                     │
│              │   PostgreSQL + RLS     │                     │
│              │  (行级安全策略)         │                     │
│              └────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

**优势**:
- ✅ 成本效益高（共享资源）
- ✅ 易于维护（单一数据库）
- ✅ 数据库级隔离（RLS）
- ✅ 支持跨租户分析

**参考**: [PostgreSQL RLS for Multi-Tenant](https://oneuptime.com/blog/post/2026-01-25-row-level-security-postgresql/view)

### 数据库设计

#### 核心表结构

```sql
-- 租户表
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) UNIQUE NOT NULL,  -- 用于子域名
    plan VARCHAR(20) NOT NULL,  -- free, pro, enterprise
    status VARCHAR(20) DEFAULT 'active',  -- active, suspended, deleted
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    email VARCHAR(255) NOT NULL,
    email_verified BOOLEAN DEFAULT FALSE,
    password_hash VARCHAR(255),  -- bcrypt hash
    full_name VARCHAR(100),
    avatar_url TEXT,
    status VARCHAR(20) DEFAULT 'active',
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, email)
);

-- 启用 RLS
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- RLS 策略：用户只能看到自己租户的数据
CREATE POLICY tenant_isolation_policy ON users
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- 设置当前租户 ID 的函数
CREATE FUNCTION set_current_tenant(tenant_uuid UUID) RETURNS void AS $$
BEGIN
    PERFORM set_config('app.current_tenant_id', tenant_uuid::TEXT, false);
END;
$$ LANGUAGE plpgsql;
```

#### 组织和团队

```sql
-- 组织表（一个租户可以有多个组织）
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 组织成员
CREATE TABLE organization_members (
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id UUID NOT NULL REFERENCES users(id),
    role VARCHAR(50) NOT NULL,  -- owner, admin, member, viewer
    joined_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (organization_id, user_id)
);

-- 团队表
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id),
    name VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 团队成员
CREATE TABLE team_members (
    team_id UUID NOT NULL REFERENCES teams(id),
    user_id UUID NOT NULL REFERENCES users(id),
    role VARCHAR(50) NOT NULL,
    joined_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (team_id, user_id)
);

-- 启用 RLS
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON organizations
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

CREATE POLICY tenant_isolation_policy ON teams
    USING (
        organization_id IN (
            SELECT id FROM organizations
            WHERE tenant_id = current_setting('app.current_tenant_id')::UUID
        )
    );
```

### 租户上下文注入

**FastAPI 中间件**:

```python
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import asyncpg

class TenantContextMiddleware(BaseHTTPMiddleware):
    """注入租户上下文"""

    async def dispatch(self, request: Request, call_next):
        # 从 JWT Token 中提取 tenant_id
        token = request.state.token
        tenant_id = token.get("tenant_id")

        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={"error": "Missing tenant_id"}
            )

        # 设置数据库连接的租户上下文
        async with request.app.state.db_pool.acquire() as conn:
            await conn.execute(
                "SELECT set_current_tenant($1)",
                tenant_id
            )

            # 将连接和租户 ID 存储在请求状态中
            request.state.db_conn = conn
            request.state.tenant_id = tenant_id

            response = await call_next(request)
            return response
```

---

## 👤 用户管理

### 用户注册流程

```
1. 用户提交注册信息
   ↓
2. 验证邮箱格式和密码强度
   ↓
3. 检查邮箱是否已存在
   ↓
4. 创建租户（如果是新租户）
   ↓
5. 创建用户账户
   ↓
6. 发送验证邮件
   ↓
7. 用户点击验证链接
   ↓
8. 激活账户
```

**API 设计**:

```python
from pydantic import BaseModel, EmailStr, validator
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserRegistration(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    tenant_name: str  # 新租户名称

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain uppercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain digit')
        return v

@app.post("/auth/register")
async def register_user(
    registration: UserRegistration,
    db: AsyncConnection = Depends(get_db)
):
    """用户注册"""

    # 1. 检查邮箱是否已存在
    existing = await db.fetchrow(
        "SELECT id FROM users WHERE email = $1",
        registration.email
    )
    if existing:
        raise HTTPException(400, "Email already registered")

    # 2. 创建租户
    tenant = await db.fetchrow(
        """
        INSERT INTO tenants (name, slug, plan)
        VALUES ($1, $2, 'free')
        RETURNING id
        """,
        registration.tenant_name,
        slugify(registration.tenant_name)
    )

    # 3. 创建用户
    password_hash = pwd_context.hash(registration.password)
    user = await db.fetchrow(
        """
        INSERT INTO users (tenant_id, email, password_hash, full_name)
        VALUES ($1, $2, $3, $4)
        RETURNING id, email
        """,
        tenant["id"],
        registration.email,
        password_hash,
        registration.full_name
    )

    # 4. 发送验证邮件
    await send_verification_email(user["email"], user["id"])

    return {
        "message": "Registration successful. Please check your email.",
        "user_id": user["id"]
    }
```

### 用户认证

**登录流程**:

```python
from datetime import datetime, timedelta
import jwt

@app.post("/auth/login")
async def login(
    credentials: OAuth2PasswordRequestForm = Depends(),
    db: AsyncConnection = Depends(get_db)
):
    """用户登录"""

    # 1. 查找用户
    user = await db.fetchrow(
        """
        SELECT u.*, t.id as tenant_id, t.plan
        FROM users u
        JOIN tenants t ON u.tenant_id = t.id
        WHERE u.email = $1 AND u.status = 'active'
        """,
        credentials.username
    )

    if not user:
        raise HTTPException(401, "Invalid credentials")

    # 2. 验证密码
    if not pwd_context.verify(credentials.password, user["password_hash"]):
        # 记录失败尝试
        await log_failed_login(user["id"])
        raise HTTPException(401, "Invalid credentials")

    # 3. 检查邮箱是否验证
    if not user["email_verified"]:
        raise HTTPException(403, "Email not verified")

    # 4. 生成 JWT Token
    access_token = create_access_token(
        data={
            "sub": str(user["id"]),
            "tenant_id": str(user["tenant_id"]),
            "email": user["email"],
            "plan": user["plan"]
        }
    )

    refresh_token = create_refresh_token(
        data={"sub": str(user["id"])}
    )

    # 5. 更新最后登录时间
    await db.execute(
        "UPDATE users SET last_login_at = NOW() WHERE id = $1",
        user["id"]
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 900  # 15 minutes
    }

def create_access_token(data: dict) -> str:
    """创建 Access Token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire, "type": "access"})

    return jwt.encode(
        to_encode,
        PRIVATE_KEY,
        algorithm="RS256"
    )
```

### 用户资料管理

```python
class UserProfile(BaseModel):
    full_name: Optional[str]
    avatar_url: Optional[str]
    timezone: Optional[str]
    language: Optional[str]

@app.get("/users/me")
async def get_current_user(
    user: dict = Depends(get_current_user)
):
    """获取当前用户信息"""
    return user

@app.patch("/users/me")
async def update_profile(
    profile: UserProfile,
    user: dict = Depends(get_current_user),
    db: AsyncConnection = Depends(get_db)
):
    """更新用户资料"""

    update_fields = profile.dict(exclude_unset=True)
    if not update_fields:
        return {"message": "No fields to update"}

    # 构建动态 UPDATE 语句
    set_clause = ", ".join([f"{k} = ${i+2}" for i, k in enumerate(update_fields.keys())])
    values = [user["id"]] + list(update_fields.values())

    await db.execute(
        f"UPDATE users SET {set_clause}, updated_at = NOW() WHERE id = $1",
        *values
    )

    return {"message": "Profile updated successfully"}
```

---

## 💳 订阅和计费

### 订阅计划

**计划层级**:

```python
PLANS = {
    "free": {
        "name": "Free",
        "price": 0,
        "limits": {
            "requests_per_month": 1000,
            "max_tokens_per_request": 2048,
            "models": ["gpt-3.5-turbo"],
            "rate_limit": "10/minute"
        }
    },
    "pro": {
        "name": "Pro",
        "price": 49,  # USD per month
        "limits": {
            "requests_per_month": 100000,
            "max_tokens_per_request": 8192,
            "models": ["gpt-3.5-turbo", "gpt-4"],
            "rate_limit": "100/minute"
        }
    },
    "enterprise": {
        "name": "Enterprise",
        "price": "custom",
        "limits": {
            "requests_per_month": "unlimited",
            "max_tokens_per_request": 32768,
            "models": ["all"],
            "rate_limit": "1000/minute"
        }
    }
}
```

### 数据库设计

```sql
-- 订阅表
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    plan VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- active, canceled, past_due
    stripe_subscription_id VARCHAR(100),
    stripe_customer_id VARCHAR(100),
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 使用量记录
CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID REFERENCES users(id),
    resource_type VARCHAR(50) NOT NULL,  -- inference, tokens, storage
    quantity INTEGER NOT NULL,
    metadata JSONB,
    recorded_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_tenant_usage (tenant_id, recorded_at),
    INDEX idx_user_usage (user_id, recorded_at)
);

-- 账单表
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    subscription_id UUID REFERENCES subscriptions(id),
    stripe_invoice_id VARCHAR(100),
    amount_due INTEGER NOT NULL,  -- 分为单位
    amount_paid INTEGER,
    currency VARCHAR(3) DEFAULT 'USD',
    status VARCHAR(20) NOT NULL,  -- draft, open, paid, void
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    due_date TIMESTAMP,
    paid_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### Stripe 集成

**参考**: [Stripe Subscription Integration](https://docs.stripe.com/billing/subscriptions/build-subscriptions)

```python
import stripe

stripe.api_key = STRIPE_SECRET_KEY

class SubscriptionService:
    """订阅管理服务"""

    async def create_subscription(
        self,
        tenant_id: str,
        plan: str,
        payment_method_id: str
    ):
        """创建订阅"""

        # 1. 创建或获取 Stripe Customer
        customer = await self.get_or_create_customer(tenant_id)

        # 2. 附加支付方式
        await stripe.PaymentMethod.attach(
            payment_method_id,
            customer=customer.id
        )

        # 3. 设置为默认支付方式
        await stripe.Customer.modify(
            customer.id,
            invoice_settings={
                "default_payment_method": payment_method_id
            }
        )

        # 4. 创建订阅
        subscription = await stripe.Subscription.create(
            customer=customer.id,
            items=[{"price": PLAN_PRICE_IDS[plan]}],
            payment_behavior="default_incomplete",
            payment_settings={
                "save_default_payment_method": "on_subscription"
            },
            expand=["latest_invoice.payment_intent"]
        )

        # 5. 保存到数据库
        await self.db.execute(
            """
            INSERT INTO subscriptions (
                tenant_id, plan, status,
                stripe_subscription_id, stripe_customer_id,
                current_period_start, current_period_end
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            """,
            tenant_id,
            plan,
            subscription.status,
            subscription.id,
            customer.id,
            datetime.fromtimestamp(subscription.current_period_start),
            datetime.fromtimestamp(subscription.current_period_end)
        )

        return subscription

    async def handle_webhook(self, event: dict):
        """处理 Stripe Webhook"""

        event_type = event["type"]

        if event_type == "invoice.payment_succeeded":
            await self.handle_payment_succeeded(event["data"]["object"])

        elif event_type == "invoice.payment_failed":
            await self.handle_payment_failed(event["data"]["object"])

        elif event_type == "customer.subscription.deleted":
            await self.handle_subscription_deleted(event["data"]["object"])

        elif event_type == "customer.subscription.updated":
            await self.handle_subscription_updated(event["data"]["object"])

@app.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    service: SubscriptionService = Depends()
):
    """Stripe Webhook 端点"""

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(400, "Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(400, "Invalid signature")

    await service.handle_webhook(event)

    return {"status": "success"}
```

### 使用量追踪

```python
class UsageTracker:
    """使用量追踪"""

    async def record_inference(
        self,
        tenant_id: str,
        user_id: str,
        model: str,
        tokens_used: int
    ):
        """记录推理使用量"""

        await self.db.execute(
            """
            INSERT INTO usage_records (
                tenant_id, user_id, resource_type,
                quantity, metadata
            ) VALUES ($1, $2, 'tokens', $3, $4)
            """,
            tenant_id,
            user_id,
            tokens_used,
            json.dumps({"model": model})
        )

        # 更新 Redis 缓存（用于实时限流）
        await self.redis.hincrby(
            f"usage:{tenant_id}:{date.today()}",
            "tokens",
            tokens_used
        )

    async def check_quota(
        self,
        tenant_id: str,
        resource_type: str
    ) -> bool:
        """检查配额"""

        # 1. 获取租户计划
        tenant = await self.db.fetchrow(
            "SELECT plan FROM tenants WHERE id = $1",
            tenant_id
        )

        plan_limits = PLANS[tenant["plan"]]["limits"]

        # 2. 获取当月使用量
        usage = await self.redis.hget(
            f"usage:{tenant_id}:{date.today().strftime('%Y-%m')}",
            resource_type
        )

        current_usage = int(usage or 0)
        limit = plan_limits.get(f"{resource_type}_per_month")

        if limit == "unlimited":
            return True

        return current_usage < limit

    async def get_usage_stats(
        self,
        tenant_id: str,
        start_date: date,
        end_date: date
    ):
        """获取使用统计"""

        stats = await self.db.fetch(
            """
            SELECT
                DATE(recorded_at) as date,
                resource_type,
                SUM(quantity) as total
            FROM usage_records
            WHERE tenant_id = $1
              AND recorded_at BETWEEN $2 AND $3
            GROUP BY DATE(recorded_at), resource_type
            ORDER BY date
            """,
            tenant_id,
            start_date,
            end_date
        )

        return stats
```

### 配额限制中间件

```python
class QuotaMiddleware(BaseHTTPMiddleware):
    """配额检查中间件"""

    async def dispatch(self, request: Request, call_next):
        # 跳过非推理请求
        if not request.url.path.startswith("/inference"):
            return await call_next(request)

        tenant_id = request.state.tenant_id

        # 检查配额
        tracker = UsageTracker(request.app.state.db_pool)
        has_quota = await tracker.check_quota(tenant_id, "requests")

        if not has_quota:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Quota exceeded",
                    "message": "Monthly request limit reached. Please upgrade your plan."
                }
            )

        response = await call_next(request)
        return response
```

---

## 📊 用户分析

### 数据收集

```sql
-- 用户活动表
CREATE TABLE user_activities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    activity_type VARCHAR(50) NOT NULL,
    metadata JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    INDEX idx_tenant_activities (tenant_id, created_at),
    INDEX idx_user_activities (user_id, created_at)
);
```

### 分析查询

```python
@app.get("/analytics/dashboard")
async def get_dashboard_stats(
    tenant_id: str = Depends(get_tenant_id),
    db: AsyncConnection = Depends(get_db)
):
    """获取仪表板统计"""

    stats = await db.fetchrow(
        """
        SELECT
            COUNT(DISTINCT u.id) as total_users,
            COUNT(DISTINCT CASE WHEN u.last_login_at > NOW() - INTERVAL '30 days'
                  THEN u.id END) as active_users,
            SUM(CASE WHEN ur.resource_type = 'tokens'
                THEN ur.quantity ELSE 0 END) as total_tokens,
            COUNT(DISTINCT ur.id) as total_requests
        FROM users u
        LEFT JOIN usage_records ur ON u.id = ur.user_id
        WHERE u.tenant_id = $1
          AND ur.recorded_at > NOW() - INTERVAL '30 days'
        """,
        tenant_id
    )

    return stats
```

---

## 🔐 数据隐私和合规

### GDPR 合规

**数据导出**:

```python
@app.get("/users/me/export")
async def export_user_data(
    user: dict = Depends(get_current_user),
    db: AsyncConnection = Depends(get_db)
):
    """导出用户数据（GDPR 要求）"""

    # 收集所有用户数据
    user_data = await db.fetchrow(
        "SELECT * FROM users WHERE id = $1",
        user["id"]
    )

    activities = await db.fetch(
        "SELECT * FROM user_activities WHERE user_id = $1",
        user["id"]
    )

    usage = await db.fetch(
        "SELECT * FROM usage_records WHERE user_id = $1",
        user["id"]
    )

    # 生成 JSON 文件
    export_data = {
        "user": dict(user_data),
        "activities": [dict(a) for a in activities],
        "usage": [dict(u) for u in usage],
        "exported_at": datetime.utcnow().isoformat()
    }

    return JSONResponse(content=export_data)
```

**数据删除**:

```python
@app.delete("/users/me")
async def delete_account(
    user: dict = Depends(get_current_user),
    db: AsyncConnection = Depends(get_db)
):
    """删除用户账户（GDPR 要求）"""

    # 软删除（保留 30 天）
    await db.execute(
        """
        UPDATE users
        SET status = 'deleted',
            email = CONCAT('deleted_', id, '@deleted.local'),
            deleted_at = NOW()
        WHERE id = $1
        """,
        user["id"]
    )

    # 记录删除请求
    await db.execute(
        """
        INSERT INTO deletion_requests (user_id, requested_at)
        VALUES ($1, NOW())
        """,
        user["id"]
    )

    return {"message": "Account deletion scheduled"}
```

---

## 📚 API 文档

完整的 API 文档将使用 OpenAPI 3.0 规范生成，包括：

- 用户注册和认证
- 用户资料管理
- 组织和团队管理
- 订阅和计费
- 使用量查询
- 数据导出和删除

---

## 参考资料

- [Multi-Tenant Architecture with LiteLLM](https://docs.litellm.ai/docs/proxy/multi_tenant_architecture)
- [PostgreSQL Row-Level Security](https://oneuptime.com/blog/post/2026-01-25-row-level-security-postgresql/view)
- [Stripe Subscription Integration](https://docs.stripe.com/billing/subscriptions/build-subscriptions)
- [Redis Session Management](https://medium.com/@20011002nimeth/session-management-with-redis-a21d43ac7d5a)

---

**状态**: 📝 设计完成
**下一步**: 实施和测试
