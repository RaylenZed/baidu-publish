# 百家号自动化内容发布管理系统

> 基于 Web 的百家号多账号自动化内容生成与发布管理系统

## 功能特性

- **账号管理** - 批量管理百家号账号，Cookie 检测与加密存储
- **AI 写作** - 百度 AIGC 生成 + 润色，支持 partial_content 风控
- **自动发布** - 草稿保存 → 封面搜索 → 正式发布全自动化
- **任务调度** - Cron 定时任务，Misfire 补执行
- **实时监控** - WebSocket 实时日志，任务进度可视化
- **企业微信通知** - 失败/警告/汇总通知

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | FastAPI 0.110+ / Python 3.11 / SQLAlchemy 2.0 |
| 任务队列 | Celery 5.3+ / Celery Beat |
| 数据库 | PostgreSQL 16 |
| 缓存 | Redis 7 |
| 前端 | Vue 3 + Vite + Naive UI + Pinia + Axios |
| 部署 | Docker + Docker Compose |

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repo-url>
cd baidu-publish

# 复制环境变量模板（compose 从 src/backend/.env 读取）
cp src/backend/.env.example src/backend/.env
```

### 2. 配置环境变量

编辑 `src/backend/.env` 文件，至少填入以下必填项：

```bash
# 管理员密码（必填）
ADMIN_PASSWORD=your_admin_password

# JWT 签名密钥（必填，建议 openssl rand -hex 32 生成）
JWT_SECRET_KEY=your-super-secret-jwt-key-change-this

# Cookie 加密密钥（必填，建议 openssl rand -hex 32 生成）
COOKIE_SECRET_KEY=deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef

# 数据库连接（必须使用 asyncpg 驱动格式）
DATABASE_URL=postgresql+asyncpg://bjh_user:bjh_pass@postgres:5432/bjh_db

# Redis 连接
REDIS_URL=redis://redis:6379/0
```

### 3. 启动服务

```bash
# 一键启动全部服务
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f backend
```

### 4. 初始化数据库

```bash
# 执行数据库迁移
docker compose exec backend alembic upgrade head
```

### 5. 访问系统

- 前端：`http://localhost`
- API 文档：`http://localhost/api/docs`
- Redoc：`http://localhost/api/redoc`

默认管理员密码为 `ADMIN_PASSWORD` 环境变量配置的值。

## 服务架构

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx                               │
│                    (反向代理 + 静态资源)                   │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
   ┌────────┐  ┌────────┐  ┌────────┐
   │ Backend │  │ Worker │  │  Beat  │
   │FastAPI  │  │Celery  │  │Celery  │
   └────┬────┘  └────┬────┘  └────┬────┘
        │           │           │
        └───────────┼───────────┘
                    │
          ┌─────────┼─────────┐
          │         │         │
          ▼         ▼         ▼
     ┌────────┐ ┌────────┐ ┌────────┐
     │ Postgres│ │  Redis │ │  Redis │
     │  数据   │ │  队列  │ │  Pub/Sub│
     └────────┘ └────────┘ └────────┘
```

## 目录结构

```
baidu-publish/
├── docker-compose.yml      # Docker Compose 配置
├── .env                   # 环境变量（需自行创建）
├── deploy/                # 部署配置
│   └── nginx.conf        # Nginx 配置
├── src/
│   ├── backend/          # FastAPI 后端
│   │   └── app/
│   │       ├── api/      # API 路由
│   │       ├── core/     # 核心配置
│   │       ├── models/   # SQLAlchemy 模型
│   │       ├── schemas/  # Pydantic DTO
│   │       ├── services/ # 业务逻辑
│   │       ├── workers/  # Celery 任务
│   │       └── ws/       # WebSocket
│   └── frontend/         # Vue3 前端
│       └── src/
│           ├── api/     # API 封装
│           ├── views/  # 页面组件
│           └── store/  # Pinia 状态
└── README.md
```

## 核心 API

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/auth/login | 登录 |
| POST | /api/v1/auth/refresh | 刷新 Token |
| POST | /api/v1/auth/ws-ticket | 获取 WebSocket 票据 |

### 业务

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /api/v1/accounts | 账号列表/新增 |
| GET/POST | /api/v1/tasks | 任务列表/创建 |
| GET | /api/v1/tasks/{id}/logs | 任务日志 |
| WS | /ws/tasks/{id}/logs | 实时日志流（路径不含 /api/v1 前缀）|
| GET/POST | /api/v1/articles | 文章列表 |
| POST | /api/v1/articles/{id}/publish | 发布文章 |
| GET/POST | /api/v1/schedules | 定时任务 |

## 配置说明

### 系统设置项

| 参数 | 默认值 | 说明 |
|------|--------|------|
| aigc_model | ds_v3 | AIGC 模型 |
| max_concurrent_accounts | 1 | 跨账号并发数 |
| daily_limit | 3 | 单账号每日上限 |
| task_timeout_minutes | 15 | 任务总超时 |
| generate_timeout | 240 | 生成超时(秒) |
| polish_timeout | 240 | 润色超时(秒) |
| cover_timeout | 60 | 封面超时(秒) |
| publish_timeout | 60 | 发布超时(秒) |

### Worker 并发对齐

- `docker-compose.yml` 中 Worker 并发由 `CELERY_WORKER_CONCURRENCY` 控制（默认 `1`）。
- 该值需要与系统设置 `max_concurrent_accounts` 保持一致，修改后重启 worker 生效：

```bash
docker compose up -d --force-recreate worker
```

### 品类映射

系统支持 18 个品类，映射到百家号分类：

```python
CATEGORY_TO_BJH = {
    "图书教育": ("教育", "读书"),
    "家用日常": ("生活", "家居"),
    "食品生鲜": ("生活", "美食"),
    "数码家电": ("科技", "数码"),
    # ... 更多品类见 constants.py
}
```

## 运维

### Homelab（无 Nginx）

适用于 DDNS 域名 + 端口访问场景：

```bash
# 1) 配置后端环境变量
cp src/backend/.env.example src/backend/.env

# 2) 配置 homelab compose 变量（DDNS 域名与端口）
cp .env.homelab.example .env.homelab
# 编辑 .env.homelab 中 VITE_API_BASE_URL / VITE_WS_BASE_URL

# 3) 启动（无 Nginx）
docker compose --env-file .env.homelab -f docker-compose.homelab.yml up -d --build
```

访问地址：
- 前端：`http://<DDNS域名>:<FRONTEND_PORT>`
- 后端：`http://<DDNS域名>:<BACKEND_PORT>/api/docs`

注意：
- `src/backend/.env` 的 `CORS_ORIGINS` 需要包含前端地址，例如 `http://<DDNS域名>:15173`
- `CELERY_WORKER_CONCURRENCY` 建议与系统设置 `max_concurrent_accounts` 保持一致

### 常用命令

```bash
# 重启所有服务
docker compose restart

# 查看 Worker 日志
docker compose logs -f worker

# 查看 Beat 日志
docker compose logs -f beat

# 进入后端容器
docker compose exec backend sh

# 查看 Celery 任务队列
docker compose exec worker celery -A app.workers.celery_app inspect active

# 手动执行迁移
docker compose exec backend alembic upgrade head
```

### 数据备份

```bash
# 备份数据库
docker compose exec postgres pg_dump -U bjh_user bjh_db > backup_$(date +%Y%m%d).sql

# 备份 Redis（如果需要）
docker compose exec redis redis-cli SAVE
```

### 日志清理

- TaskLogs：30 天后自动清理（可通过 Celery Beat 配置）
- 系统日志：由 logrotate 管理

## 安全注意事项

1. **Cookie 存储**：使用 AES-256-GCM 加密存储
2. **账号导出**：使用 PBKDF2 + AES-256-GCM 加密
3. **Token 有效期**：2 小时，密码修改后失效
4. **WebSocket**：一次性票据，60 秒有效
5. **登录限流**：5 分钟 10 次，超限锁 15 分钟

## 常见问题

### Q: 任务一直处于 pending 状态
A: 检查 Celery Worker 是否正常运行：`docker compose ps worker`

### Q: Cookie 检测失败
A: 确保 Cookie 包含 `BDUSS=` 字段，且未过期

### Q: 发布失败，提示 errno != 0
A: 百家号 API 返回错误，检查文章内容是否符合平台规范

### Q: 前端无法连接 WebSocket
A: 检查 Nginx 是否配置了 WebSocket 代理，或直接访问前端开发服务器

## 开发

```bash
# 进入后端目录
cd src/backend

# 安装依赖
pip install -r requirements.txt

# 运行测试
pytest

# 进入前端目录
cd src/frontend

# 安装依赖
npm install

# 开发模式
npm run dev
```

## License

MIT License
