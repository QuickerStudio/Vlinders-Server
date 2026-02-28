# 数据库 Schema 设计文档

**版本**: v1.0
**创建日期**: 2026-02-28
**数据库**: PostgreSQL 15+
**状态**: 📝 设计阶段

---

## 📋 概述

本文档定义 Vlinders Platform 的完整数据库 Schema，包括所有表结构、索引、约束和关系。

### 设计原则

1. **多租户隔离**: 使用 Row-Level Security (RLS)
2. **数据完整性**: 外键约束和检查约束
3. **性能优化**: 合理的索引设计
4. **审计追踪**: 创建时间和更新时间
5. **软删除**: 重要数据使用软删除

---

## 🏢 租户和用户

### tenants (租户表)

```sql
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(50) UNIQUE NOT NULL,
    plan VARCHAR(20) NOT NULL DEFAULT 'free',
    status VARCHAR(20) NOT NULL DEFAULT 'active',

    -- 配置
    settings JSONB DEFAULT '{}',

    -- Stripe 信息
    stripe_customer_id VARCHAR(100),

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP,

    -- 约束
    CONSTRAINT tenants_plan_check CHECK (plan IN ('free', 'pro', 'enterprise')),
    CONSTRAINT tenants_status_check CHECK (status IN ('active', 'suspended', 'deleted'))
);

-- 索引
CREATE INDEX idx_tenants_slug ON tenants(slug);
CREATE INDEX idx_tenants_status ON tenants(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_tenants_stripe_customer ON tenants(stripe_customer_id);

-- 触发器：自动更新 updated_at
CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

---

### users (用户表)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- 基本信息
    email VARCHAR(255) NOT NULL,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash VARCHAR(255),
    full_name VARCHAR(100),
    avatar_url TEXT,

    -- 状态
    status VARCHAR(20) NOT NULL DEFAULT 'active',

    -- 登录信息
    last_login_at TIMESTAMP,
    last_login_ip INET,
    failed_login_attempts INTEGER DEFAULT 0,
    locked_until TIMESTAMP,

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP,

    -- 约束
    CONSTRAINT users_email_tenant_unique UNIQUE(tenant_id, email),
    CONSTRAINT users_status_check CHECK (status IN ('active', 'suspended', 'deleted'))
);

-- 索引
CREATE INDEX idx_users_tenant_id ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_status ON users(status) WHERE deleted_at IS NULL;

-- RLS 策略
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON users
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);

-- 触发器
CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

---

### user_sessions (用户会话表)

```sql
CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Token 信息
    refresh_token_hash VARCHAR(64) NOT NULL,

    -- 设备信息
    user_agent TEXT,
    ip_address INET,

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    last_used_at TIMESTAMP,
    revoked_at TIMESTAMP
);

-- 索引
CREATE INDEX idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX idx_user_sessions_token_hash ON user_sessions(refresh_token_hash);
CREATE INDEX idx_user_sessions_expires_at ON user_sessions(expires_at)
    WHERE revoked_at IS NULL;
```

---

## 🏢 组织和团队

### organizations (组织表)

```sql
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- 基本信息
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- 配置
    settings JSONB DEFAULT '{}',

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP
);

-- 索引
CREATE INDEX idx_organizations_tenant_id ON organizations(tenant_id);

-- RLS
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON organizations
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
```

---

### organization_members (组织成员表)

```sql
CREATE TABLE organization_members (
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 角色
    role VARCHAR(50) NOT NULL,

    -- 时间戳
    joined_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 主键
    PRIMARY KEY (organization_id, user_id),

    -- 约束
    CONSTRAINT org_members_role_check CHECK (role IN ('owner', 'admin', 'member', 'viewer'))
);

-- 索引
CREATE INDEX idx_org_members_user_id ON organization_members(user_id);
CREATE INDEX idx_org_members_role ON organization_members(role);
```

---

### teams (团队表)

```sql
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,

    -- 基本信息
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP
);

-- 索引
CREATE INDEX idx_teams_organization_id ON teams(organization_id);

-- RLS
ALTER TABLE teams ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON teams
    USING (
        organization_id IN (
            SELECT id FROM organizations
            WHERE tenant_id = current_setting('app.current_tenant_id')::UUID
        )
    );
```

---

### team_members (团队成员表)

```sql
CREATE TABLE team_members (
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- 角色
    role VARCHAR(50) NOT NULL,

    -- 时间戳
    joined_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 主键
    PRIMARY KEY (team_id, user_id),

    -- 约束
    CONSTRAINT team_members_role_check CHECK (role IN ('lead', 'member'))
);

-- 索引
CREATE INDEX idx_team_members_user_id ON team_members(user_id);
```

---

## 🔑 权限和角色

### roles (角色表)

```sql
CREATE TABLE roles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- 基本信息
    name VARCHAR(50) UNIQUE NOT NULL,
    description TEXT,

    -- 权限列表
    permissions JSONB NOT NULL DEFAULT '[]',

    -- 是否系统角色
    is_system BOOLEAN NOT NULL DEFAULT FALSE,

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 索引
CREATE INDEX idx_roles_name ON roles(name);

-- 插入系统角色
INSERT INTO roles (name, description, permissions, is_system) VALUES
('super_admin', 'Platform administrator', '["*"]', TRUE),
('tenant_admin', 'Tenant administrator', '["tenant:*", "user:*", "billing:*"]', TRUE),
('developer', 'Developer', '["inference:*", "model:read"]', TRUE),
('analyst', 'Analyst', '["inference:read", "analytics:read"]', TRUE),
('viewer', 'Viewer', '["inference:read"]', TRUE);
```

---

### user_roles (用户角色关联表)

```sql
CREATE TABLE user_roles (
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- 授权信息
    granted_by UUID REFERENCES users(id),
    granted_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 主键
    PRIMARY KEY (user_id, role_id, tenant_id)
);

-- 索引
CREATE INDEX idx_user_roles_user_tenant ON user_roles(user_id, tenant_id);
CREATE INDEX idx_user_roles_role ON user_roles(role_id);
```

---

## 🔑 API Key 管理

### api_keys (API 密钥表)

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- Key 信息
    key_hash VARCHAR(64) NOT NULL UNIQUE,
    key_prefix VARCHAR(20) NOT NULL,
    name VARCHAR(100),

    -- 权限
    permissions JSONB DEFAULT '[]',

    -- 使用信息
    last_used_at TIMESTAMP,
    last_used_ip INET,

    -- 过期
    expires_at TIMESTAMP,

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMP
);

-- 索引
CREATE INDEX idx_api_keys_tenant_id ON api_keys(tenant_id);
CREATE INDEX idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX idx_api_keys_key_hash ON api_keys(key_hash) WHERE revoked_at IS NULL;
CREATE INDEX idx_api_keys_expires_at ON api_keys(expires_at) WHERE revoked_at IS NULL;

-- RLS
ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON api_keys
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
```

---

## 💳 订阅和计费

### subscriptions (订阅表)

```sql
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- 计划信息
    plan VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,

    -- Stripe 信息
    stripe_subscription_id VARCHAR(100) UNIQUE,
    stripe_customer_id VARCHAR(100),

    -- 周期
    current_period_start TIMESTAMP,
    current_period_end TIMESTAMP,

    -- 取消信息
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    canceled_at TIMESTAMP,

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 约束
    CONSTRAINT subscriptions_plan_check CHECK (plan IN ('free', 'pro', 'enterprise')),
    CONSTRAINT subscriptions_status_check CHECK (
        status IN ('active', 'canceled', 'past_due', 'unpaid', 'incomplete')
    )
);

-- 索引
CREATE INDEX idx_subscriptions_tenant_id ON subscriptions(tenant_id);
CREATE INDEX idx_subscriptions_stripe_id ON subscriptions(stripe_subscription_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);
```

---

### invoices (账单表)

```sql
CREATE TABLE invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(id) ON DELETE SET NULL,

    -- Stripe 信息
    stripe_invoice_id VARCHAR(100) UNIQUE,

    -- 金额（分为单位）
    amount_due INTEGER NOT NULL,
    amount_paid INTEGER,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',

    -- 状态
    status VARCHAR(20) NOT NULL,

    -- 周期
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,

    -- 支付信息
    due_date TIMESTAMP,
    paid_at TIMESTAMP,

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 约束
    CONSTRAINT invoices_status_check CHECK (
        status IN ('draft', 'open', 'paid', 'void', 'uncollectible')
    )
);

-- 索引
CREATE INDEX idx_invoices_tenant_id ON invoices(tenant_id);
CREATE INDEX idx_invoices_subscription_id ON invoices(subscription_id);
CREATE INDEX idx_invoices_stripe_id ON invoices(stripe_invoice_id);
CREATE INDEX idx_invoices_status ON invoices(status);
CREATE INDEX idx_invoices_period ON invoices(period_start, period_end);
```

---

## 📊 使用量追踪

### usage_records (使用量记录表)

```sql
CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- 资源类型
    resource_type VARCHAR(50) NOT NULL,

    -- 数量
    quantity INTEGER NOT NULL,

    -- 元数据
    metadata JSONB DEFAULT '{}',

    -- 时间戳
    recorded_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 约束
    CONSTRAINT usage_records_resource_type_check CHECK (
        resource_type IN ('tokens', 'requests', 'storage', 'bandwidth')
    )
);

-- 索引
CREATE INDEX idx_usage_records_tenant_recorded ON usage_records(tenant_id, recorded_at DESC);
CREATE INDEX idx_usage_records_user_recorded ON usage_records(user_id, recorded_at DESC);
CREATE INDEX idx_usage_records_resource_type ON usage_records(resource_type, recorded_at DESC);

-- 分区（按月）
CREATE TABLE usage_records_y2026m02 PARTITION OF usage_records
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- RLS
ALTER TABLE usage_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON usage_records
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
```

---

### usage_quotas (配额表)

```sql
CREATE TABLE usage_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    -- 资源类型
    resource_type VARCHAR(50) NOT NULL,

    -- 配额
    quota_limit INTEGER NOT NULL,
    quota_period VARCHAR(20) NOT NULL,

    -- 当前使用量（缓存）
    current_usage INTEGER DEFAULT 0,

    -- 重置时间
    reset_at TIMESTAMP NOT NULL,

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 约束
    CONSTRAINT usage_quotas_period_check CHECK (
        quota_period IN ('minute', 'hour', 'day', 'month')
    ),
    CONSTRAINT usage_quotas_tenant_resource_unique UNIQUE(tenant_id, resource_type)
);

-- 索引
CREATE INDEX idx_usage_quotas_tenant_id ON usage_quotas(tenant_id);
```

---

## 🤖 推理记录

### inference_requests (推理请求表)

```sql
CREATE TABLE inference_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,

    -- 模型信息
    model VARCHAR(50) NOT NULL,

    -- 请求信息
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,

    -- 性能指标
    latency_ms INTEGER,

    -- 状态
    status VARCHAR(20) NOT NULL,
    error_message TEXT,

    -- 元数据
    metadata JSONB DEFAULT '{}',

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,

    -- 约束
    CONSTRAINT inference_requests_status_check CHECK (
        status IN ('pending', 'processing', 'completed', 'failed')
    )
);

-- 索引
CREATE INDEX idx_inference_requests_tenant_created ON inference_requests(tenant_id, created_at DESC);
CREATE INDEX idx_inference_requests_user_created ON inference_requests(user_id, created_at DESC);
CREATE INDEX idx_inference_requests_model ON inference_requests(model);
CREATE INDEX idx_inference_requests_status ON inference_requests(status);

-- 分区（按月）
CREATE TABLE inference_requests_y2026m02 PARTITION OF inference_requests
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');

-- RLS
ALTER TABLE inference_requests ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_policy ON inference_requests
    USING (tenant_id = current_setting('app.current_tenant_id')::UUID);
```

---

## 📝 审计日志

### audit_logs (审计日志表)

```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,

    -- 操作者
    actor_type VARCHAR(20) NOT NULL,
    actor_id UUID,
    actor_ip INET,

    -- 事件信息
    event_type VARCHAR(50) NOT NULL,
    event_category VARCHAR(20) NOT NULL,

    -- 资源信息
    resource_type VARCHAR(50),
    resource_id UUID,

    -- 操作详情
    action VARCHAR(50) NOT NULL,
    result VARCHAR(20) NOT NULL,

    -- 元数据
    metadata JSONB DEFAULT '{}',

    -- 时间戳
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- 约束
    CONSTRAINT audit_logs_actor_type_check CHECK (
        actor_type IN ('user', 'api_key', 'system')
    ),
    CONSTRAINT audit_logs_event_category_check CHECK (
        event_category IN ('auth', 'user', 'billing', 'inference', 'admin')
    ),
    CONSTRAINT audit_logs_result_check CHECK (
        result IN ('success', 'failure')
    )
);

-- 索引
CREATE INDEX idx_audit_logs_tenant_created ON audit_logs(tenant_id, created_at DESC);
CREATE INDEX idx_audit_logs_actor ON audit_logs(actor_type, actor_id, created_at DESC);
CREATE INDEX idx_audit_logs_event_type ON audit_logs(event_type);
CREATE INDEX idx_audit_logs_resource ON audit_logs(resource_type, resource_id);

-- 分区（按月）
CREATE TABLE audit_logs_y2026m02 PARTITION OF audit_logs
    FOR VALUES FROM ('2026-02-01') TO ('2026-03-01');
```

---

## 🔧 辅助函数

### update_updated_at_column()

```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

---

### set_current_tenant()

```sql
CREATE OR REPLACE FUNCTION set_current_tenant(tenant_uuid UUID)
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.current_tenant_id', tenant_uuid::TEXT, FALSE);
END;
$$ LANGUAGE plpgsql;
```

---

### check_permission()

```sql
CREATE OR REPLACE FUNCTION check_permission(
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
          AND (
              r.permissions ? p_permission
              OR r.permissions ? '*'
          )
    );
END;
$$ LANGUAGE plpgsql;
```

---

## 📊 视图

### v_active_subscriptions (活跃订阅视图)

```sql
CREATE VIEW v_active_subscriptions AS
SELECT
    s.*,
    t.name AS tenant_name,
    t.slug AS tenant_slug
FROM subscriptions s
JOIN tenants t ON s.tenant_id = t.id
WHERE s.status = 'active'
  AND t.deleted_at IS NULL;
```

---

### v_user_permissions (用户权限视图)

```sql
CREATE VIEW v_user_permissions AS
SELECT
    ur.user_id,
    ur.tenant_id,
    r.name AS role_name,
    jsonb_array_elements_text(r.permissions) AS permission
FROM user_roles ur
JOIN roles r ON ur.role_id = r.id;
```

---

## 🔄 数据迁移脚本

### 初始化脚本

```sql
-- 01_init.sql

-- 启用扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 创建辅助函数
-- (见上文)

-- 创建所有表
-- (见上文)

-- 插入初始数据
INSERT INTO roles (name, description, permissions, is_system) VALUES
('super_admin', 'Platform administrator', '["*"]', TRUE),
('tenant_admin', 'Tenant administrator', '["tenant:*", "user:*", "billing:*"]', TRUE),
('developer', 'Developer', '["inference:*", "model:read"]', TRUE),
('analyst', 'Analyst', '["inference:read", "analytics:read"]', TRUE),
('viewer', 'Viewer', '["inference:read"]', TRUE);
```

---

## 📚 参考资料

- [PostgreSQL RLS](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [Multi-Tenant Database Design](https://oneuptime.com/blog/post/2026-01-25-row-level-security-postgresql/view)

---

**状态**: 📝 设计完成
**下一步**: 创建迁移脚本和测试数据
