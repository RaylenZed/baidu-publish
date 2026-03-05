# 项目宪法（Constitution）

基线来源：`PRD-百家号自动化内容发布管理系统.md`（v1.1，2026-03-04）

## 1. 项目简介

本项目是一个面向单管理员的 Web 化百家号多账号自动化内容发布管理系统，覆盖账号管理、AIGC 生成、草稿/发布、任务调度、监控与审计全流程。

## 2. 技术栈

### 2.1 已在 PRD 明确的技术栈

| 层 | 技术 | 版本/约束 | 说明 |
|---|---|---|---|
| 后端框架 | FastAPI | 0.110+ | 异步接口、WebSocket、OpenAPI |
| 语言 | Python | 3.11 | 复用 `bjh_auto_full_v7.py` 既有能力 |
| ORM | SQLAlchemy | 2.0 | 模型与查询 |
| 迁移 | Alembic | 与 SQLAlchemy 配套 | 数据库版本管理 |
| 任务队列 | Celery | 5.3+ | 异步任务执行 |
| 定时调度 | Celery Beat | 与 Celery 配套 | Cron 触发 |
| 中间件 | Redis | 7 | Celery Broker + ws_ticket + 日志通道 |
| 数据库 | PostgreSQL | 16 | 核心业务数据存储 |
| 前端 | Vue 3 + Vite | 最新稳定版 | 管理台 UI |
| Web 服务器 | Nginx | alpine | 反向代理与静态资源托管 |
| 容器化 | Docker + Docker Compose | - | 一键部署 |
| 第三方服务 | 百家号 API / 百度 AIGC / 企业微信 Webhook | - | 内容生成、发布、告警 |

### 2.2 PRD 未明确但建议采用

| 项目 | 建议 | 理由 |
|---|---|---|
| 前端 UI 组件库 | Naive UI `[建议]` | 与 Vue3 配合成熟，表格/表单/抽屉/通知组件完整，适合中后台 |
| 状态管理 | Pinia `[建议]` | 比 Vuex 更轻量，适合任务面板和日志流状态共享 |
| 前端 HTTP 客户端 | Axios `[建议]` | 拦截器易做 JWT 刷新与统一错误处理 |
| 后端配置管理 | Pydantic Settings `[建议]` | 与 FastAPI 原生协同，便于 `.env` 与类型校验 |
| 测试 | Pytest + httpx + pytest-asyncio `[建议]` | 覆盖 API、异步任务、集成流程 |
| 代码质量 | Ruff + Black + isort + mypy `[建议]` | 提升一致性并控制回归 |
| Markdown 编辑/渲染 | md-editor-v3 `[建议]` | Vue3 原生支持，自带预览和工具栏，用于文章在线编辑 |
| 文本差异对比 | diff2html `[建议]` | 用于初稿 vs 润色的 side-by-side diff 对比视图 |

## 3. 核心架构决策

1. 单角色单租户：当前仅管理员角色，不做 RBAC，所有数据默认为管理员可见。
2. 任务执行模型：同账号强串行，跨账号按 `max_concurrent_accounts` 并发（默认 1，建议不超过 3）。
   - **串行实现**：Worker 执行前通过 Redis 获取账号锁 `account:{account_id}:run_lock`（`SET NX EX`，TTL = 总超时时长），未获取则延迟重试（Celery `retry` + `countdown`）。
   - **并发对齐**：`max_concurrent_accounts` 作为全局并发上限，与 Celery Worker 的 `concurrency` 配置保持一致。系统设置变更后需重启 Worker 生效。
3. 幂等与防重：`idempotency_key` 5 分钟去重 + 同账号 60 秒同品类同模式防重。
   - 幂等 key 存 Redis（TTL 5 分钟），DB 留兜底校验。
   - 每日上限按 `Asia/Shanghai` 时区自然日计算，在 `task_service.create_task()` 中查询 `tasks` 表当日该账号记录数。
   - 连续失败冷却：查询该账号最近 3 条任务状态，若连续 `failed` 则检查 `finished_at + 30min > now()`，在创建前与 Worker 执行前双重校验。
4. 重试语义：重试创建新任务，原任务不回退；通过 `retry_of_task_id` 追踪链路。
5. 状态机基线：
   - Task：`pending -> running -> success/failed/timeout`，并支持 `pending -> canceled`
   - Article：`draft -> publishing -> published`，失败转 `publish_failed`
6. 超时恢复：步骤级超时（生成/润色/封面/发布/草稿）+ 总超时兜底；Beat 每 2 分钟回收超时任务。
7. Misfire 策略：定时任务重启后仅对 24 小时内错过触发补执行一次。
8. 调度建模：`schedules` 与 `accounts` 采用 `schedule_accounts` 关联表（M:N，`ON DELETE CASCADE`）。
9. WebSocket 安全：使用一次性 `ws_ticket`（60 秒、单次消费）替代 URL 直传 JWT。
10. WebSocket 日志链路：
    - Worker 写入 `task_logs` 表后，同步 publish 到 Redis Pub/Sub 频道 `task:{task_id}:logs`。
    - WebSocket handler 连接时先从 DB 回放已有日志（历史），再订阅 Redis 频道推送增量。
    - 支持同任务多客户端订阅，`ws_ticket` 仅用于连接鉴权，不影响广播。
11. 内容风控：`partial_content` 强制降级为 `draft_only`，需人工确认后才可发布。
    - `tasks.warning`：任务执行级警告（记录降级原因，供任务详情展示）。
    - `articles.content_warning`：内容级警告（供文章列表展示橙色警告 Tag，影响能否发布）。
    - `partial_content` 场景双写两个字段。
12. 审计可追踪：
    - `publish_attempts` 记录每次发布调用结果
    - `content_events` 记录关键生命周期事件
13. 安全基线：
    - Access Token 2 小时 + refresh 接口
    - 登录限流（5 分钟 10 次，锁 15 分钟）
    - 导出文件加密（PBKDF2-HMAC-SHA256 + AES-256-GCM）
14. 业务边界：当前无支付链路、无资金流转、无佣金结算。
15. 事务管理：事务边界在 Service 层，使用 `async with session.begin()` 包裹原子操作。跨 Service 调用传递同一 `AsyncSession`。涉及状态更新 + 审计写入的场景强制单事务提交。

## 4. 编码规范

### 4.1 命名规范

| 范围 | 规则 | 示例 |
|---|---|---|
| 数据库表名 | 统一小写复数、`snake_case` | `accounts`, `task_logs`, `publish_attempts` |
| 数据库字段 | 统一 `snake_case` | `retry_of_task_id`, `last_step_at` |
| 主键/外键 | 主键统一 `id`；外键统一 `<entity>_id` | `account_id`, `schedule_id` |
| Python 类名 | `PascalCase` | `TaskService`, `AuthService` |
| Python 函数/变量 | `snake_case` | `create_task`, `max_concurrent_accounts` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_TASK_TIMEOUT_MINUTES` |
| 前端组件文件 | `PascalCase.vue` `[建议]` | `TaskCard.vue` |
| 前端组合式函数 | `useXxx.ts` `[建议]` | `useTaskStream.ts` |

### 4.2 API 规范

1. 路径统一小写、复数资源名、REST 风格，动作型后缀仅用于非 CRUD 行为。  
   示例：`/tasks/{id}/retry`、`/tasks/{id}/force-draft`。
2. API 前缀统一 `/api/v1` `[建议]`，对外文档展示时可省略前缀。
3. 请求/响应统一 JSON；时间字段使用 ISO-8601 字符串。
4. 统一响应结构（`app/common/response.py`）：
   - **成功**：`{ "success": true, "data": <T> }`（无返回体时 `data: null`）
   - **分页**：`{ "success": true, "data": { "items": [...], "total": 150, "page": 1, "size": 20, "pages": 8 } }`
   - **错误**（全局处理器构造）：`{ "success": false, "errorCode": "TASK_TIMEOUT", "message": "...", "requestId": "...", "details": {} }`
   - 路由层只需 `return ApiResponse.ok(data)` 或抛 `AppException` 子类，不直接构造错误体
5. 幂等接口必须接收并记录 `idempotency_key`。
6. 分页规范：
   - 请求参数：`page`（从 1 开始）、`size`（默认 20，最大 100），通过 `Depends(PaginationParams)` 注入
   - 响应通过 `PageData.of(items, total, page, size)` 构造，嵌入 `ApiResponse.ok()` 返回
   - 默认采用偏移分页，超大数据量场景再评估游标分页

### 4.3 异常处理规范

1. 定义 `app/core/exceptions.py`，包含 `AppException(code, message, status_code, details)` 基类及业务子类。
2. 在 `main.py` 注册全局异常处理器，统一转换为 4.2 第 6 条的错误响应结构。
3. Service 层抛业务异常，Route 层不做分散 `try/except`（由全局处理器兜底）。
4. 错误码命名规则：`MODULE_REASON`，如 `TASK_DAILY_LIMIT_EXCEEDED`、`ACCOUNT_COOKIE_EXPIRED`。
5. 已知 `error_type` 枚举值（来源 PRD）：
   - AIGC 类：`aigc_timeout`、`connection_error`、`parse_error`、`empty_response`
   - 发布类：`publish_failed_draft_saved`、`token_refresh_failed`
   - 系统类：`timeout`、`worker_crash`

### 4.4 时间与时区规范

1. 数据库存储统一 `TIMESTAMPTZ` + UTC `[建议]`。
2. 调度与业务展示默认时区 `Asia/Shanghai`（来源 PRD `schedules.timezone` 默认值）。
3. `created_at/updated_at/started_at/finished_at/last_step_at/timeout_at` 一律由后端生成，禁止前端直传。

### 4.5 金额单位规范

1. 当前 PRD 明确无支付链路与资金流转。
2. 若后续新增金额字段，统一使用“分（int64）”存储 `[建议]`，禁止浮点。

### 4.6 DTO 与参数校验规范

1. 后端 DTO 统一使用 Pydantic v2 模型 `[建议]`。
2. 必填项、长度、枚举、范围在 DTO 层显式校验，不依赖前端兜底。
3. 校验基线：
   - `account.name`: `1..50`
   - `cookie`: 必含 `BDUSS=`
   - `categories`: `1..2` 且值在品类枚举内
   - `mode`: `draft|publish`
   - 超时配置：正整数且在合理区间（如 `10..600`）`[建议]`
4. 数据库约束与 DTO 校验双保险：唯一键、外键、非空约束必须落库。

### 4.7 日志与可观测性规范

1. 结构化日志（JSON）`[建议]`，字段至少包含：`ts/level/request_id/task_id/account_id/module/message`。
2. `task_logs` 为业务日志事实来源；系统运行日志与业务日志需区分。
3. 异常必须带 `error_type` 与可追踪上下文。

### 4.8 业务常量规范

1. 18 品类枚举定义在 `core/constants.py` 中，作为后端单一枚举源：
   ```
   图书教育、家用日常、精品服饰、食品生鲜、数码家电、美妆个护、
   母婴用品、运动户外、鞋靴箱包、汽车用品、珠宝配饰、宠物用品、
   鲜花园艺、零食干货、粮油调料、医疗保健、家用器械、中医养生
   ```
2. 品类→百家号文章分类的映射表同样维护在 `core/constants.py`，匹配失败兜底为"生活 > 生活技巧"（PRD PUB-05）。
3. 前端通过 API 拉取品类列表（可在 `/settings` 或独立 `/categories` 端点），**禁止前端本地硬编码复制品类列表**。

### 4.9 Commit Message 规范

采用 Conventional Commits `[建议]`：

1. 格式：`type(scope): subject`
2. `type` 允许：`feat|fix|refactor|perf|docs|test|build|chore`
3. 示例：`feat(tasks): add force-draft endpoint and retry chain`
4. 一次提交只做一类变更；数据库变更必须与 Alembic migration 同步提交。

## 5. 目录结构

```text
src/
  backend/
    app/
      main.py                    # FastAPI 入口，路由注册，生命周期管理，全局异常处理器
      core/
        config.py                # 环境变量与全局配置（Pydantic Settings）
        constants.py             # 业务常量：18 品类枚举、品类→百家号分类映射、error_type 枚举
        exceptions.py            # AppException 基类及业务异常子类
        security.py              # JWT、密码哈希、ws_ticket、Cookie 加解密
        database.py              # DB 会话与连接管理
        logging.py               # 日志初始化与格式
      middleware/
        request_id.py            # 请求级 request_id 注入
        rate_limit.py            # 登录限流（5 分钟 10 次，锁 15 分钟）
      api/
        deps.py                  # 认证鉴权、通用依赖（AsyncSession 注入）
        routes/
          auth.py                # 登录/刷新/ws-ticket
          dashboard.py           # 仪表盘聚合接口
          accounts.py            # 账号 CRUD、cookie 检测、导入导出
          tasks.py               # 任务创建/重试/取消/强制草稿/列表
          task_logs.py           # 任务日志查询
          articles.py            # 文章列表/详情/编辑/手动发布
          schedules.py           # 定时任务 CRUD/启停
          pools.py               # 变量池与组合历史
          settings.py            # 全局配置与密码修改
          system_logs.py         # 系统日志查询
      common/
        response.py              # 统一响应体：ApiResponse[T]、PageData[T]、ErrorResponse、PaginationParams
      models/                    # SQLAlchemy 模型（accounts/tasks/articles/...）
      schemas/                   # Pydantic DTO（请求/响应）；路由专属 schema 按模块命名（auth.py 等）
      repositories/              # 数据访问层（按需使用：仅复杂查询、跨表聚合、可复用事务片段）
      services/
        aigc_service.py          # 百度 AIGC 对话、SSE 解析、失败分类
        bjh_service.py           # 百家号草稿/发布/封面相关 API 封装（含 JSONP 剥离）
        task_service.py          # 任务编排、状态推进、幂等/防重/每日上限/冷却检查
        schedule_service.py      # Cron 计算、misfire 补执行
        pool_service.py          # 变量池加权随机、combo_id 生成
        article_service.py       # 文章保存、发布状态流转、warning 标记
        notify_service.py        # 企微通知（失败/汇总/WARN）
        audit_service.py         # publish_attempts/content_events 写入
      utils/
        jsonp.py                 # JSONP 回调剥离（bjhdraft/bjhpublish）
        cookie.py                # Cookie 加解密工具
        combo.py                 # combo_id 格式化
      workers/
        celery_app.py            # Celery 配置
        tasks.py                 # 异步执行任务入口（含 Redis 账号锁获取）
        beat_jobs.py             # 超时回收与定时补偿作业
      ws/
        task_log_stream.py       # 任务日志 WebSocket 推送（Redis Pub/Sub 订阅）
    migrations/                  # Alembic 迁移脚本
    tests/
      conftest.py                # 测试 fixtures（DB、Redis、Celery mock）
      unit/                      # 单元测试（services、utils）
      integration/               # 集成测试（API 端到端、Worker 流程）
  frontend/
    src/
      main.ts                    # 前端入口
      router/                    # 路由与页面守卫
      store/                     # Pinia 状态管理 [建议]
      api/                       # 后端接口封装
      types/                     # TS 类型定义
      composables/
        useTaskLogStream.ts      # WebSocket 日志流 composable
      views/
        LoginView.vue
        DashboardView.vue
        AccountsView.vue
        TasksView.vue
        ArticlesView.vue
        SchedulesView.vue
        PoolsView.vue
        SettingsView.vue
        SystemLogsView.vue
      components/
        task/
          TaskCard.vue           # 任务卡片与步骤进度
          TaskLogDrawer.vue      # 实时日志抽屉
        article/
          ArticleEditor.vue      # Markdown 编辑器（md-editor-v3）
          ArticleDiff.vue        # 初稿/润色对比（diff2html）
          WarningTag.vue
        common/
          AppLayout.vue
          FilterBar.vue
```

> **v7 核心代码迁移策略**：不单独保留 `v7_legacy/` 目录，将 v7 的 API 调用逻辑迁移到 `services/`（`aigc_service.py`、`bjh_service.py`），必要时在 `utils/` 放兼容适配层，避免双份逻辑长期分叉。

## 6. 开发进度表

> 图例：✅ 完成 | 🔨 进行中 | ⬜ 未开始

| 模块 | 说明 | 状态 |
|---|---|---|
| 基础设施（Docker Compose 6 服务） | `nginx/backend/worker/beat/redis/postgres` + Dockerfile + Nginx 配置 | ✅ |
| 数据库 Schema 与 Alembic | 全量表结构（11 表）+ 索引 + Alembic 配置（env.py/ini/mako） | ✅ |
| 公共基础设施 | `AppException` 异常体系、统一响应格式 `ApiResponse`、中间件、限流 | ✅ |
| 认证模块 | 登录（限流+bcrypt）、JWT 刷新、token_version 失效机制 | ✅ |
| ws_ticket 模块 | 一次性票据签发（Redis TTL 60s）与消费（get+delete） | ✅ |
| 项目骨架（路由 stub） | 所有路由模块空壳注册、服务层 stub、Worker stub | ✅ |
| 账号管理模块 | CRUD、Cookie 检测、导入导出 | ✅ |
| 任务编排模块 | 创建、幂等、防重、状态流转 | ✅ |
| Celery Worker 执行模块 | 6 步执行链路与失败重试 | ✅ |
| 超时回收模块 | 步骤级超时 + 总超时 + 2 分钟扫描 | ✅ |
| 任务面板模块 | 任务卡片、筛选、批量操作 | ⬜ |
| WebSocket 实时日志模块 | 日志推送（Redis Pub/Sub）、历史回放、鉴权 | ✅ |
| 文章管理模块 | 列表、详情、编辑、手动发布、content_warning 确认 | ✅ |
| partial_content 风险控制 | warning 标记、draft_only 降级、人工确认 | ✅ |
| 定时任务模块 | CRUD、启停、Misfire 补执行 | ✅ |
| 仪表盘模块 | 统计卡片、健康度、近期任务 | ✅ |
| 系统日志模块 | 查询、筛选、自动清理 | ✅ |
| 审计模块 | `publish_attempts` + `content_events` 写入 | ✅ |
| 安全加固模块 | Cookie 加密、导出加密（CBC→GCM）、CORS/HTTPS | ✅ |
| 前端工程骨架 | Vue3 + Vite + Naive UI + Pinia + Axios + 7页面 | ✅ |
| 文档与运维脚本 | README、部署文档、环境说明 | ✅ |
| 前端工程骨架 | 路由、布局、鉴权、API 封装 | ⬜ |
| 文档与运维脚本 | README、部署文档、环境说明 | ⬜ |

## 7. 模块依赖与建议开发顺序

基于 PRD Phase 1-4 映射的模块依赖链：

```text
Phase 1（MVP 骨架）:
  基础设施(Docker) → 数据库 Schema → 认证模块 → 账号管理
                                   ↘ 前端工程骨架（可与后端并行）

Phase 2（核心体验）:
  变量池模块 ──┐
  账号管理 ────┤→ 任务编排 → Celery Worker → 超时回收
               │                ↘ WebSocket 实时日志
               │                ↘ 任务面板（前端）
               └→ 文章管理（依赖任务产出的 article 数据）
                   ↘ partial_content 风控

Phase 3（完善功能）:
  定时任务模块（依赖任务编排 + Celery Beat）
  仪表盘模块（依赖 tasks/articles 数据）
  系统设置模块（独立，可并行）
  通知模块（依赖任务状态流转）

Phase 4（安全与部署）:
  安全加固（Cookie 加密、导出加密）
  审计模块（依赖任务/发布流程）
  系统日志模块（独立）
  文档与运维脚本（独立）
```

**可并行开发的模块组**：
- 前端骨架 & 后端骨架（Phase 1）
- 变量池 & 账号管理前端（Phase 2 前置）
- 系统设置 & 系统日志 & 文档（Phase 3/4，互不依赖）

## 8. 关键文件索引

### 基础设施

| 文件 | 职责 |
|---|---|
| `docker-compose.yml` | 6 服务编排入口（nginx/backend/worker/beat/redis/postgres） |
| `src/backend/Dockerfile.backend` | Python 3.11-slim 镜像，含 libpq-dev |
| `deploy/nginx/default.conf` | 反向代理 + SPA 路由 + WebSocket 升级 |
| `src/backend/alembic.ini` | Alembic 配置，DB URL 由 env.py 动态注入 |
| `src/backend/migrations/env.py` | Alembic 异步引擎配置（asyncpg） |
| `src/backend/.env.example` | 所有环境变量说明（含必填/可选分类） |

### 后端核心

| 文件 | 职责 |
|---|---|
| `app/main.py` | FastAPI 入口：路由注册、中间件、异常处理器、WebSocket、健康检查 |
| `app/core/config.py` | Pydantic Settings，`lru_cache` 单例，所有 env 在此声明 |
| `app/core/constants.py` | 18 品类枚举、全部业务枚举、`DEFAULT_*` 常量，**单一枚举源** |
| `app/core/exceptions.py` | `AppException` 基类及所有业务异常子类；`register_exception_handlers()` |
| `app/core/security.py` | `hash_password/verify_password`（bcrypt）、`create/decode_access_token`（JWT）、`encrypt/decrypt_cookie`（AES-256-GCM）、`generate_ws_ticket` |
| `app/core/database.py` | async 引擎、`get_db()` DI、`init_db()`（含 SystemSettings 首次初始化）、`close_db()` |
| `app/common/response.py` | `ApiResponse[T]`、`PageData[T]`、`ErrorResponse`、`PaginationParams`，所有响应体的**单一来源** |
| `app/middleware/request_id.py` | `X-Request-ID` 注入与回传 |
| `app/middleware/rate_limit.py` | Redis 登录限流（5 分钟 10 次，超限锁 15 分钟） |
| `app/api/deps.py` | `get_current_user()`（JWT 验证 + token_version 校验）、`verify_ws_ticket()` |

### 认证

| 文件 | 职责 |
|---|---|
| `app/api/routes/auth.py` | POST `/login`（限流+bcrypt）、POST `/refresh`、POST `/ws-ticket`（Redis 存储） |
| `app/schemas/auth.py` | `LoginRequest`、`TokenResponse`、`WsTicketResponse` |

### 数据模型（11 张表）

| 文件 | 表名 |
|---|---|
| `app/models/account.py` | `accounts`（含 GIN 索引） |
| `app/models/task.py` | `tasks`（含幂等 key、自引用重试链） |
| `app/models/article.py` | `articles` |
| `app/models/task_log.py` | `task_logs` |
| `app/models/schedule.py` | `schedules` + `schedule_accounts`（M:N） |
| `app/models/pool.py` | `variable_pools` + `combo_history` |
| `app/models/audit.py` | `publish_attempts` + `content_events` |
| `app/models/system_settings.py` | `system_settings`（Singleton id=1，含 token_version） |

## 9. 当前待解决问题

（当前为空，开发过程中持续维护）

