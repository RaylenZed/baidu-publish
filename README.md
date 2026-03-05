# 百家号自动化内容发布管理系统

> Web 化百家号多账号自动化内容生成与发布系统（单管理员）

## 功能特性

- 账号管理：Cookie 加密存储、检测、导入导出
- 任务编排：创建/重试/取消，幂等与防重
- AIGC + 发布：生成、润色、草稿、封面、发布全链路
- 定时调度：Cron 任务与 misfire 补执行
- 实时日志：WebSocket 任务日志回放 + 增量推送
- 审计追踪：`publish_attempts` + `content_events`

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI / Python 3.11 / SQLAlchemy 2.0 |
| 任务队列 | Celery / Celery Beat |
| 数据库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| 前端 | Vue 3 + Vite + Naive UI + Pinia |
| 部署 | Docker Compose（无 Nginx，端口直连） |

## 快速开始

### 1) 准备环境变量

```bash
cp .env.example .env
```

编辑 `.env`，至少设置：

```bash
ADMIN_PASSWORD=你的管理员密码
JWT_SECRET_KEY=建议使用 openssl rand -hex 32 生成
COOKIE_SECRET_KEY=64位十六进制字符串
DATABASE_URL=postgresql+asyncpg://bjh_user:bjh_pass@postgres:5432/bjh_db
REDIS_URL=redis://redis:6379/0
```

如果你使用 DDNS 域名访问，务必同步修改：

```bash
VITE_API_BASE_URL=http://你的域名:18000/api/v1
VITE_WS_BASE_URL=ws://你的域名:18000
CORS_ORIGINS=http://你的域名:15173
```

### 2) 启动服务

```bash
docker compose up -d --build
```

### 3) 查看状态与日志

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f beat
```

### 4) 访问地址

- 前端：`http://<服务器IP或DDNS域名>:15173`
- 后端 API 文档：`http://<服务器IP或DDNS域名>:18000/api/docs`

默认端口可在 `.env` 中通过 `FRONTEND_PORT` / `BACKEND_PORT` 修改。

## 服务结构

- `frontend`：Vite Preview 静态服务（5173）
- `backend`：FastAPI API（8000）
- `worker`：Celery Worker
- `beat`：Celery Beat
- `postgres`：业务数据库
- `redis`：队列 + Pub/Sub

## 目录结构

```text
baidu-publish/
├── docker-compose.yml
├── .env.example
├── src/
│   ├── backend/
│   └── frontend/
└── README.md
```

## 常用运维命令

```bash
# 重建并启动
docker compose up -d --build

# 重启指定服务
docker compose restart backend
docker compose restart worker
docker compose restart beat

# 进入后端容器
docker compose exec backend sh

# 手动执行迁移
docker compose exec backend alembic upgrade head

# 查看任务执行情况
docker compose exec worker celery -A app.workers.celery_app inspect active
```

## 重要说明

- `ADMIN_PASSWORD` 仅在首次初始化 `system_settings` 时生效。
  - 后续改 `.env` 不会自动更新登录密码。
  - 要改密码请在系统设置页修改，或直接更新数据库中的密码哈希。
- `CELERY_WORKER_CONCURRENCY` 建议与系统设置 `max_concurrent_accounts` 保持一致。

## 常见问题

### 1) 登录返回 500

优先检查：

```bash
docker compose logs --tail=200 backend
docker compose logs --tail=200 worker
docker compose logs --tail=200 beat
```

常见原因：

- `.env` 缺少必填项（如 `JWT_SECRET_KEY` / `COOKIE_SECRET_KEY`）
- `COOKIE_SECRET_KEY` 不是 64 位十六进制
- `DATABASE_URL` / `REDIS_URL` 配置错误
- 数据库首次初始化后又修改了 `ADMIN_PASSWORD`，但实际密码未同步更新

### 2) 任务一直 pending

确认 `worker` 正常运行：

```bash
docker compose ps worker
docker compose logs -f worker
```

### 3) WebSocket 连不上

确认：

- `VITE_WS_BASE_URL` 与后端地址一致
- `CORS_ORIGINS` 包含前端访问地址
- 后端 18000 端口可达

## 开发（非容器）

后端：

```bash
cd src/backend
pip install -r requirements.txt
pytest
```

前端：

```bash
cd src/frontend
npm install
npm run dev
```
