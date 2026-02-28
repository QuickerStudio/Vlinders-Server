# Vlinders-Server

**版本**: v1.0.0
**状态**: ✅ Phase 1 完成 - 基础推理服务已实现
**最后更新**: 2026-02-28

---

## 📋 概述

Vlinders-Server 是一个基于 vLLM 的高性能大模型推理服务器，专为生产环境设计。

### 核心特性

- ⚡ **高性能推理** - 基于 vLLM 的 PagedAttention 和 Continuous Batching
- 🔧 **易于部署** - Docker 容器化，支持 Kubernetes
- 🎯 **内部服务** - 仅接受来自 Vlinders-API 的内部请求
- 📊 **完善监控** - 健康检查、GPU 监控、日志记录

### 核心定位

> **推理层 + Agent 编排引擎**
>
> 不直接面向用户，只接受来自 Vlinders-API 的内部请求

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境

```bash
cp .env.example .env
# 编辑 .env 设置 INTERNAL_SECRET
```

### 3. 启动服务

```bash
python -m vlinders_server.main
```

详细步骤请查看 [快速开始指南](QUICKSTART.md)

---

## 📚 文档

- [快速开始](QUICKSTART.md) - 5 分钟快速上手
- [部署指南](README_DEPLOY.md) - 完整部署文档
- [项目总结](PROJECT_SUMMARY.md) - 功能清单和技术栈
- [架构设计](Spec/01-架构设计.md) - 详细架构文档
- [vLLM 集成](Spec/03-vLLM集成方案.md) - vLLM 使用指南

---

## 📡 API 端点

### 内部 API (需要认证)

- `POST /internal/chat` - 聊天推理
- `POST /internal/chat/stream` - 流式聊天
- `GET /internal/models` - 模型列表

### 健康检查 (无需认证)

- `GET /health` - 完整健康检查
- `GET /ready` - 就绪检查
- `GET /live` - 存活检查

详细 API 文档: http://localhost:8000/docs

---

## 🐳 Docker 部署

```bash
# 使用 Docker Compose
docker-compose up -d

# 查看日志
docker-compose logs -f vlinders-server
```

---

## 🔧 技术栈

### 核心框架
- Python 3.11+
- vLLM (推理引擎)
- FastAPI (Web 框架)
- Uvicorn (ASGI 服务器)

### 数据存储
- Redis (缓存)
- PostgreSQL (元数据)
- Qdrant (向量数据库)

### 基础设施
- Docker & Docker Compose
- CUDA 12.1+
- NVIDIA GPU

---

## ✅ 已完成功能 (Phase 1)

- ✅ vLLM 推理引擎集成
- ✅ FastAPI 接口层
- ✅ 配置管理系统
- ✅ 健康检查和监控
- ✅ Docker 部署支持
- ✅ 完整文档和测试

---

## 🚧 开发路线图

- **Phase 1** (✅ 完成): 基础推理服务
- **Phase 2** (计划中): Agent 编排系统
- **Phase 3** (计划中): 代码分析引擎
- **Phase 4** (计划中): 高级 Agent 功能
- **Phase 5** (计划中): 生产环境优化

---

## 📞 联系方式

- GitHub: https://github.com/QuickerStudio/Vlinders-Server
- Discord: https://discord.gg/vlinders
- Email: team@vlinders.org

---

**状态**: ✅ Phase 1 完成 - 可用于生产环境
**下一步**: Phase 2 - Agent 编排系统
