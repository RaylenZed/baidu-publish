# 百家号自动化内容发布管理系统 — 产品需求文档 (PRD)

> **版本**: v1.1  
> **日期**: 2026-03-04  
> **状态**: 评审通过（三轮共识后同步更新）

---

# 第一部分：项目背景

## 1. 项目简介

一个基于 Web 的**百家号多账号自动化内容生成与发布管理系统**，通过 AI 自动生成品类软文并发布到百家号，提供可视化任务管理、账号管理、定时调度和运行监控能力。

## 2. 业务背景

### 2.1 业务场景

用户运营百度百家号账号矩阵，计划通过 CPS 返佣模式推广商品盈利。百家号支持 18 个商品分类：图书教育、家用日常、精品服饰、食品生鲜、数码家电、美妆个护、母婴用品、运动户外、鞋靴箱包、汽车用品、珠宝配饰、宠物用品、鲜花园艺、零食干货、粮油调料、医疗保健、家用器械、中医养生。

### 2.2 运营策略

分两阶段执行：

| 阶段 | 目标 | 内容策略 |
|------|------|----------|
| **第一阶段（涨粉期）** | 粉丝量涨到 200+ | 纯内容软文，不带任何商品链接、价格、店铺名 |
| **第二阶段（变现期）** | CPS 返佣变现 | 软文中嵌入 CPS 商品推广链接 |

**当前系统聚焦第一阶段**。

### 2.3 现状与痛点

现有方案是一个命令行 Python 脚本（v7），存在以下问题：

| 痛点 | 描述 |
|------|------|
| **无可视化** | 只能看命令行日志，无法直观掌握全局状态 |
| **无法灵活操控** | 每次需改代码配置才能调整账号、品类、模式，操作门槛高 |
| **无持久化** | 任务结果、文章内容、执行历史不存储，无法回溯 |
| **无定时管理** | 依赖外部 crontab，不可视、不易调整 |
| **Cookie 管理困难** | 过期检测靠人肉、配置靠改代码 |
| **无错误追踪** | 批量执行时单个失败难以定位和重试 |

### 2.4 解决方案

将现有 v7 命令行工具升级为 **Web 管理后台**，核心 API 调用逻辑（百度 AIGC 生成 + 百家号发布）完全复用，外层包装可视化管理和任务调度能力。

## 3. 目标用户

| 用户 | 描述 |
|------|------|
| **系统管理员** | 运营者本人，管理全部账号、配置系统参数、监控运行状态 |

> 当前版本为单用户系统（管理员），不区分多角色。

## 4. 核心目标

| 目标 | 指标 |
|------|------|
| 降低操作门槛 | 所有配置和操作通过 Web 界面完成，**零代码操作** |
| 可视化管控 | 任务进度实时可见，6 步进度条 + 实时日志流 |
| 持久化追溯 | 所有任务记录、文章内容、执行日志落库，可回溯查询 |
| 稳定定时运行 | 支持 Cron 定时调度，可在界面上开关和修改 |
| 快速故障响应 | Cookie 过期自动预警，任务失败支持一键重试 |
| 一键部署 | Docker Compose 一条命令启动全部服务 |

---

# 第二部分：业务设计

## 5. 角色与权限

当前版本为**单角色系统**，仅有管理员角色。

| 角色 | 权限 |
|------|------|
| **管理员** | 全部权限：账号管理、任务执行、文章管理、变量池编辑、定时配置、系统设置 |

**认证方式**：密码登录 → JWT Token 鉴权。密码通过环境变量 `ADMIN_PASSWORD` 配置。

**后续扩展预留**：若未来需要多角色（运营人员 / 只读查看者），可在 accounts 表基础上扩展 users 表和 RBAC 权限体系。

## 6. 功能模块详细描述

### 6.1 仪表盘（Dashboard）

**目的**：一眼掌握系统全局状态。

| 组件 | 内容 |
|------|------|
| **今日统计卡片** | 4 张卡片：成功数 / 失败数 / 待执行数 / 总执行时长 |
| **账号健康度** | 每个账号一行：名称 + Cookie 状态灯（🟢存活 / 🔴过期 / ⚪未检测）+ 上次检测时间 |
| **最近任务流水** | 最新 20 条任务：状态图标 + 账号名 + 品类 + 标题摘要 + 时间 |
| **定时任务下次执行** | 展示最近一个定时任务的触发时间 |

### 6.2 账号管理

**目的**：管理百家号账号矩阵。

#### 6.2.1 账号列表

| 字段 | 说明 |
|------|------|
| 账号名称 | 自定义名称，如"账号1-图书" |
| Cookie | 脱敏展示（`BDUSS=****pcX`），点击可查看/编辑完整值 |
| 绑定品类 | 1-2 个品类标签，如 `图书教育` `食品生鲜` |
| Cookie 状态 | 🟢存活 / 🔴过期 / ⚪未检测 |
| 上次检测时间 | — |
| 操作 | 编辑 / 删除 / 检测Cookie / 立即执行 |

#### 6.2.2 新增/编辑账号

| 字段 | 类型 | 必填 | 校验 |
|------|------|------|------|
| 账号名称 | 文本 | ✅ | 长度 1-50，不重复 |
| Cookie | 多行文本 | ✅ | 必须包含 `BDUSS=` |
| 品类绑定 | 多选（最多2个） | ✅ | 从 18 品类中选择 |

#### 6.2.3 Cookie 一键检测

**逻辑**：调用 `refresh_token()`，尝试从百家号编辑页提取 JWT Token。
- 成功 → 标为 🟢存活，记录检测时间
- 失败 → 标为 🔴过期，触发企微通知

#### 6.2.4 批量操作

- **全部检测**：逐个检测所有账号 Cookie
- **导出配置**：JSON 格式导出所有账号信息
- **导入配置**：JSON 格式批量导入

### 6.3 任务面板（核心模块）

**目的**：创建、监控、管理发布任务。

#### 6.3.1 手动创建任务

**表单字段**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| 选择账号 | 多选复选框 | ✅ | 可选"全部"快捷操作 |
| 品类 | 下拉 | ❌ | 留空则按账号绑定品类自动选择（多品类随机） |
| 运行模式 | 单选 | ✅ | `draft`（仅保存草稿） / `publish`（正式发布） |
| 主题关键词 | 文本 | ❌ | 可选，指定文章主题方向 |
| 指定产品名 | 文本 | ❌ | 可选，指定要出现的产品/品牌 |

**提交后**：为每个选中的账号创建一条独立的 task 记录，进入 Celery 队列执行（同账号串行，跨账号按 `max_concurrent_accounts` 配置并发）。

#### 6.3.2 任务卡片

每条任务以卡片形式展示，包含：

```
┌─────────────────────────────────────────────┐
│  📝 账号1-图书 | 图书教育 | draft           │
│─────────────────────────────────────────────│
│  进度: [✅ Prompt] [✅ AI生成] [⏳ AI润色] [  草稿] [  封面] [  发布]  │
│─────────────────────────────────────────────│
│  标题: 《通勤路上读完这5本书...》              │
│  combo: A3P2S1T4                            │
│  耗时: 45s                                  │
│─────────────────────────────────────────────│
│  [查看日志] [查看文章] [重试] [手动发布草稿]   │
└─────────────────────────────────────────────┘
```

**动态步骤进度**（根据任务模式动态展示）：

| 步骤 | 名称 | 说明 | 模式 |
|------|------|------|------|
| Step 1 | Prompt 构建 | 6 维变量池加权随机抽取 + 拼装 | draft + publish |
| Step 2 | AI 生成初稿 | 百度 AIGC SSE 流式生成 | draft + publish |
| Step 3 | AI 润色降 AI 味 | 百度 AIGC 二次调用润色 | draft + publish |
| Step 4 | 保存草稿 | 百家号 API 保存草稿 | draft + publish |
| Step 5 | 搜索封面 | 正版图库搜索 + 自动裁剪 | 仅 publish |
| Step 6 | 正式发布 | 百家号 API 提交发布 | 仅 publish |

> draft 模式前端仅展示 4 步，publish 模式展示 6 步。draft 模式下 Step 5/6 不展示。

#### 6.3.3 实时日志流

- 任务执行中点击"查看日志"弹出侧边栏
- 通过 **WebSocket** 实时推送 Worker 的逐行日志
- 每条日志含：时间戳 + 级别（INFO/WARN/ERROR）+ 消息内容
- 任务完成后日志固化在数据库，可随时回看

#### 6.3.4 任务列表

| 筛选维度 | 选项 |
|----------|------|
| 状态 | 全部 / 排队中 / 执行中 / 成功 / 失败 / 已取消 / 超时 |
| 账号 | 下拉选择 |
| 品类 | 下拉选择 |
| 日期范围 | 日期选择器 |
| 模式 | draft / publish |

支持批量操作：**重试所有失败** / **发布所有草稿** / **强制转草稿模式**（`force_draft_only`，将 failed 任务降级为仅保存草稿）。

#### 6.3.5 定时任务

| 字段 | 类型 | 说明 |
|------|------|------|
| 任务名称 | 文本 | 如"每日9点发布" |
| Cron 表达式 | 文本 | 如 `0 9 * * *`，旁边显示可读解释 |
| 执行账号 | 多选 | 可选全部 |
| 运行模式 | 单选 | draft / publish |
| 启用状态 | 开关 | 启用后由 Celery Beat 调度 |

定时任务的每次触发记录在任务列表中，标记来源为"定时触发"。

### 6.4 文章管理

**目的**：查看、编辑、管理所有生成的文章。

#### 6.4.1 文章列表

| 字段 | 说明 |
|------|------|
| 标题 | 文章标题 |
| 账号 | 来源账号 |
| 品类 | 所属品类 |
| 状态 | 草稿 / 发布中 / 已发布 / 发布失败 |
| 警告标签 | “内容不完整，需人工确认”（仅 `partial_content` 时显示橙色警告 Tag） |
| combo_id | 变量组合标识 |
| 百家号 ID | article_id |
| 创建时间 | — |

#### 6.4.2 文章详情

- **Markdown 渲染预览**：格式化展示润色后的正文
- **初稿 vs 润色对比**：左右两栏对照展示 AI 初稿和润色后的文章
- **封面图预览**：展示搜索到的封面图
- **元信息**：combo_id 各维度（角度/人设/风格/结构/标题风格/时间场景）

#### 6.4.3 在线编辑

- 对**草稿状态**的文章，提供 Markdown 编辑器
- 编辑后可点击"保存"更新草稿内容，或点击"发布"提交到百家号

### 6.5 变量池管理

**目的**：在线维护文章生成的 6 维随机变量池，无需改代码。

#### 6.5.1 品类专属池

每个品类有独立的：
- **角度池**（ANGLE_POOL）：如图书教育的"书单推荐"、"读后感"等
- **人设池**（PERSONA_POOL）：如图书教育的"通勤看书的上班族"、"全职妈妈"等

#### 6.5.2 通用池

所有品类共用的：
- **风格池**（STYLE_POOL）：轻松日常、走心感悟、干货总结等（8 种）
- **结构池**（STRUCTURE_POOL）：纯叙述体、小标题分段、问答式等（8 种）
- **标题风格池**（TITLE_STYLE_POOL）：疑问式、数字式等（6 种）
- **时间场景池**（TIME_HOOK_POOL）：春天万物复苏、周末午后等（12 种）

#### 6.5.3 编辑界面

- 左侧品类树选择，右侧编辑区
- 每个池项为标签形式，支持添加/删除/拖拽排序
- 新增品类时自动创建空的角度池和人设池模板
- 修改后即时生效（保存到数据库）

#### 6.5.4 组合历史与统计

- 展示每个品类已使用过的 combo_id 列表
- 标注最近 7 天内用过的组合，生成新任务时提示避免短期重复

### 6.6 系统设置

**目的**：全局参数配置。

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| 运行模式 | 单选 | draft | draft = 仅保存草稿，publish = 正式发布 |
| AIGC 模型 | 单选 | ds_v3 | 可选 ds_v3（DeepSeek）/ ernie（文心一言） |
| 账号间延迟 | 数字（秒） | 10 | 多账号执行的间隔时间 |
| 跨账号并发数 | 数字 | 1 | 跨账号同时执行任务数（建议不超过 3） |
| 每日发布上限 | 数字 | 3 | 单账号每日最大发布/草稿数 |
| 总超时时长 | 数字（分钟） | 15 | 单任务最大执行时间，超时自动标记 timeout |
| 生成超时 | 数字（秒） | 240 | AI 生成步骤超时阈值 |
| 润色超时 | 数字（秒） | 240 | AI 润色步骤超时阈值 |
| 封面超时 | 数字（秒） | 60 | 封面搜索步骤超时阈值 |
| 发布超时 | 数字（秒） | 60 | 正式发布步骤超时阈值 |
| 草稿超时 | 数字（秒） | 60 | 草稿保存步骤超时阈值 |
| 企微 Webhook | 文本 | 空 | 企业微信机器人通知地址 |
| 通知级别 | 单选 | 仅失败 | 全部 / 仅失败 / 关闭 |
| 管理员密码 | 密码 | — | 修改登录密码（环境变量初始化） |

### 6.7 系统日志

- 完整的后端运行日志浏览器
- 支持按级别（INFO/WARN/ERROR）、时间范围、关键词筛选
- 日志自动滚动清理（保留最近 30 天）

## 7. 核心业务流程

### 7.1 手动发布主流程

```mermaid
flowchart TD
    A["用户选择账号+品类+模式"] --> B["创建 Task 记录 (status=pending)"]
    B --> C["进入 Celery 队列"]
    C --> D["Worker 拾取任务 (status=running)"]
    D --> E["Step1: 6维变量池随机抽取，拼装 Prompt"]
    E --> F["Step2: 百度AIGC生成初稿 (SSE流式)"]
    F --> G["Step3: 百度AIGC润色降AI味"]
    G --> H["Step4: 提取Token + 保存草稿"]
    H --> I{"模式?"}
    I -->|draft| J["status=success, publish_status=draft"]
    I -->|publish| K["Step5: 搜索封面图+裁剪"]
    K --> L["Step6: 调用发布API"]
    L --> M{"发布结果?"}
    M -->|成功| N["status=success, publish_status=published"]
    M -->|失败| O["status=failed, 记录error"]
```

### 7.2 定时执行流程

```mermaid
flowchart TD
    A["Celery Beat 按 Cron 触发"] --> B["读取 schedule 配置"]
    B --> C["为每个关联账号创建 Task"]
    C --> D["进入 Celery 队列"]
    D --> E["与手动发布相同的 Step1-6 流程"]
    E --> F["结果记录 + 企微通知"]
```

### 7.3 异常处理流程

#### 7.3.1 Cookie 过期

```mermaid
flowchart TD
    A["Step4: refresh_token() 失败"] --> B["标记 task.status=failed"]
    B --> C["标记 account.cookie_status=expired"]
    C --> D["触发企微通知: Cookie失效"]
    D --> E["用户在界面更新Cookie"]
    E --> F["一键重试失败任务"]
```

#### 7.3.2 AIGC 生成超时 / 失败

```mermaid
flowchart TD
    A["AIGC 请求异常"] --> B{"重试次数 < 2?"}
    B -->|是| C["等待 5s 后重试"]
    C --> A
    B -->|否| D["标记 task.status=failed"]
    D --> E["记录错误详情到 task_logs"]
```

#### 7.3.3 发布 API 失败

```mermaid
flowchart TD
    A["publish() 返回 errno != 0"] --> B{"错误类型?"}
    B -->|Token过期| C["自动 refresh_token 后重试 1 次"]
    B -->|其他| D["标记失败, 保留草稿"]
    D --> E["用户可查看草稿内容, 手动修改后重新发布"]
```

### 7.4 草稿手动发布流程

```mermaid
flowchart TD
    A["用户在文章管理页查看草稿"] --> B{"需要修改?"}
    B -->|是| C["在线编辑标题/正文"]
    C --> D["保存编辑"]
    B -->|否| D
    D --> E["点击'发布'按钮"]
    E --> F["后端: refresh_token + 搜索封面 + 发布"]
    F --> G["更新 publish_status=published"]
```

## 8. 业务规则

### 8.1 账号规则

| 规则 ID | 规则描述 |
|---------|----------|
| ACC-01 | 每个账号绑定 **1-2 个**品类，不可超过 2 个 |
| ACC-02 | 账号名称全局唯一 |
| ACC-03 | Cookie 必须包含 `BDUSS=` 字段才允许保存 |
| ACC-04 | Cookie 状态分三种：`active`（存活）、`expired`（过期）、`unchecked`（未检测） |
| ACC-05 | 删除账号时，如有未完成任务（pending/running），需先确认 |

### 8.2 任务执行规则

| 规则 ID | 规则描述 |
|---------|----------|
| TASK-01 | 同一账号的任务**串行执行**，不允许并发（避免百度风控） |
| TASK-02 | 跨账号可配置并发度，默认并发数 1（可在系统设置中调整，建议不超过 3），中间间隔 `ACCOUNT_DELAY` 秒 |
| TASK-03 | 单账号**每日执行上限**默认 3 次（含 draft 和 publish），超限拒绝创建并提示 |
| TASK-04 | 任务状态流转：`pending → running → success/failed/timeout`，`pending → canceled` |
| TASK-05 | `failed`/`timeout` 状态的任务可**重试**，重试时创建新 task（`retry_of_task_id` 追踪链路），原记录保留 |
| TASK-06 | 绑定 2 个品类的账号，未指定品类时**随机选择其中一个** |
| TASK-07 | 任务创建需携带 `idempotency_key`，同 key 5 分钟内去重；同账号 60s 内不允许创建相同品类+模式任务 |
| TASK-08 | 单账号连续失败 3 次自动冷却 30 分钟（风控退避） |
| TASK-09 | 步骤级超时配置：`generate_timeout`(240s)、`polish_timeout`(240s)、`cover_timeout`(60s)、`publish_timeout`(60s)、`draft_timeout`(60s)；总超时 `task_timeout_minutes`(15min) 作为兜底 |
| TASK-10 | **超时回收机制**：Celery Beat 每 2 分钟扫描一次 `running` 状态任务，将 `timeout_at < NOW()` 或 `last_step_at` 超过当前步骤阈值的任务标记为 `timeout`，`error_message` 标注"执行超时/Worker 异常" |
| TASK-11 | **Misfire 补执行策略**：系统重启后，Celery Beat 检查所有 `enabled=true` 的定时任务，若 `next_fire_at < NOW()` 且 `last_fired_at` 距今不超过 24 小时，则**补执行一次**；超过 24 小时的错过不补执行，仅记录 WARN 日志 |

### 8.3 AIGC 调用规则

| 规则 ID | 规则描述 |
|---------|----------|
| AI-01 | 每次 AIGC 调用需先创建对话 (`createDialogue`)，再发送 Prompt (`chat`) |
| AI-02 | SSE 流式读取，取 `is_end=true` 的最终消息为完整内容。30s 无新数据包视为连接断开 |
| AI-03 | AIGC 超时阈值：连接 10s，读取按步骤配置（默认 240s） |
| AI-04 | 超时或异常时自动重试，最多 **2 次**，间隔 5s |
| AI-05 | 润色 Prompt 含品类一致性检查：如果初稿严重跑题，涤色节点会重写 |
| AI-06 | 流中断且已接收部分内容（>500字）时，保存已接收内容并标记 `partial_content`，**统一降级为 draft_only 模式**，需人工确认后才可发布 |
| AI-07 | 失败分类：`timeout`、`connection_error`、`parse_error`、`empty_response` |

### 8.4 发布规则

| 规则 ID | 规则描述 |
|---------|----------|
| PUB-01 | 发布前必须成功获取 JWT Token（`refresh_token`），否则中止 |
| PUB-02 | 草稿保存使用 JSONP 回调格式（`bjhdraft(...)` 需剥离） |
| PUB-03 | 封面图搜索关键词：取标题前 4 个中文字符，失败则用品类名前 4 字 |
| PUB-04 | 封面图搜索失败不阻断发布，允许无封面发布 |
| PUB-05 | 文章分类自动匹配：18 品类 → 百家号文章分类的精确映射表，匹配失败兜底为"生活 > 生活技巧" |
| PUB-06 | 发布 API 的 JSONP 回调为 `bjhpublish(...)`，需剥离后解析 JSON |

### 8.5 变量池规则

| 规则 ID | 规则描述 |
|---------|----------|
| POOL-01 | 角度池和人设池是**品类专属**的（18 品类各一套） |
| POOL-02 | 风格池、结构池、标题风格池、时间场景池是**全品类共用** |
| POOL-03 | 每个池至少需要 **1 个**项目，否则使用默认值 |
| POOL-04 | 随机种子使用 `int(time.time() * 1000) % 2**31`，确保每次不同 |
| POOL-05 | combo_id 格式：`A{角度序号}P{人设序号}S{风格序号}T{标题风格序号}` |
| POOL-06 | 新任务生成时，查询最近 7 天 combo_history，建议避免重复组合（非强制） |

### 8.6 通知规则

| 规则 ID | 规则描述 |
|---------|----------|
| NOTIF-01 | 企微通知级别可配：全部（每条任务）/ 仅失败 / 关闭。**canceled 和 timeout 状态不触发通知**（非异常场景） |
| NOTIF-02 | Cookie 过期检测到后，**始终发送通知**（不受级别限制） |
| NOTIF-03 | 每日定时任务完成后发送**汇总通知**（成功数/失败数/耗时） |
| NOTIF-04 | `partial_content` 降级为草稿时，触发 WARN 级通知（内容不完整，需人工确认） |

---

# 第三部分：数据设计

## 9. 数据模型

### 9.1 ER 关系总览

```mermaid
erDiagram
    accounts ||--o{ tasks : "1:N"
    tasks ||--|| articles : "1:1"
    tasks ||--o{ task_logs : "1:N"
    schedules ||--o{ tasks : "触发"
    accounts }o--o{ schedules : "M:N (schedule_accounts)"
    articles ||--o{ publish_attempts : "1:N"
    tasks ||--o{ content_events : "1:N"

    accounts {
        int id PK
        string name UK
        text cookie_encrypted
        jsonb categories
        string cookie_status
        timestamp cookie_checked_at
        timestamp created_at
        timestamp updated_at
    }

    tasks {
        int id PK
        int account_id FK
        int schedule_id FK "nullable"
        int retry_of_task_id FK "nullable"
        string category
        string mode
        string status
        string error_type "nullable"
        string warning "nullable"
        string combo_id
        string topic_keyword "nullable"
        string product_name "nullable"
        text error_message "nullable"
        timestamp started_at
        timestamp finished_at
        timestamp timeout_at "nullable"
        timestamp last_step_at "nullable"
        timestamp created_at
    }

    articles {
        int id PK
        int task_id FK UK
        string title
        text body_md
        text body_html
        text raw_draft
        string bjh_article_id "nullable"
        text cover_url "nullable"
        string publish_status
        string content_warning "nullable"
        timestamp published_at "nullable"
    }

    task_logs {
        int id PK
        int task_id FK
        string step
        string level
        text message
        timestamp created_at
    }

    schedules {
        int id PK
        string name
        string cron_expr
        string mode
        string timezone
        boolean enabled
        timestamp last_fired_at "nullable"
        timestamp next_fire_at "nullable"
        timestamp created_at
        timestamp updated_at
    }

    schedule_accounts {
        int schedule_id FK "PK"
        int account_id FK "PK"
    }

    variable_pools {
        int id PK
        string pool_type
        string category "nullable"
        jsonb items "对象数组"
        timestamp updated_at
    }

    combo_history {
        int id PK
        int account_id FK
        string category
        string combo_id
        timestamp used_at
    }

    publish_attempts {
        int id PK
        int article_id FK
        jsonb request_summary
        int response_code
        string error_type "nullable"
        text error_message "nullable"
        timestamp attempted_at
    }

    content_events {
        int id PK
        string event_type
        int task_id FK "nullable"
        int account_id FK
        string category
        jsonb payload
        timestamp created_at
    }
```

### 9.2 字段详细说明

#### accounts 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | — |
| name | VARCHAR(50) | UNIQUE, NOT NULL | 账号名称 |
| cookie_encrypted | TEXT | NOT NULL | AES-256 加密后的 Cookie 字符串 |
| categories | JSONB | NOT NULL | 绑定品类列表，如 `["图书教育"]` |
| cookie_status | VARCHAR(10) | DEFAULT 'unchecked' | active / expired / unchecked |
| cookie_checked_at | TIMESTAMP | NULLABLE | 上次 Cookie 检测时间 |
| created_at | TIMESTAMP | DEFAULT NOW() | — |
| updated_at | TIMESTAMP | DEFAULT NOW() | — |

#### tasks 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | — |
| account_id | INT | FK → accounts.id | 所属账号 |
| schedule_id | INT | FK → schedules.id, NULLABLE | 来源定时任务（手动为 null） |
| retry_of_task_id | INT | FK → tasks.id, NULLABLE | 重试来源任务 ID（追踪重试链路） |
| category | VARCHAR(20) | NOT NULL | 本次品类 |
| mode | VARCHAR(10) | NOT NULL | draft / publish |
| status | VARCHAR(15) | NOT NULL, DEFAULT 'pending' | pending / running / success / failed / canceled / timeout |
| error_type | VARCHAR(30) | NULLABLE | 失败细分类型，如 `publish_failed_draft_saved`、`aigc_timeout` 等 |
| warning | VARCHAR(30) | NULLABLE | 警告标记，如 `partial_content`（内容不完整） |
| combo_id | VARCHAR(30) | NULLABLE | 变量组合标识 |
| topic_keyword | VARCHAR(50) | NULLABLE | 用户指定的主题关键词 |
| product_name | VARCHAR(50) | NULLABLE | 用户指定的产品名 |
| error_message | TEXT | NULLABLE | 失败原因 |
| started_at | TIMESTAMP | NULLABLE | 开始执行时间 |
| finished_at | TIMESTAMP | NULLABLE | 完成时间 |
| timeout_at | TIMESTAMP | NULLABLE | 超时截止时间，Worker 拾取时设置 |
| last_step_at | TIMESTAMP | NULLABLE | 最近步骤完成时间，用于步骤级超时判定 |
| created_at | TIMESTAMP | DEFAULT NOW() | — |

#### articles 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | — |
| task_id | INT | FK → tasks.id, UNIQUE | 1:1关联任务 |
| title | VARCHAR(100) | NOT NULL | 文章标题 |
| body_md | TEXT | NOT NULL | 润色后 Markdown 正文 |
| body_html | TEXT | NOT NULL | 转换后的百家号 HTML |
| raw_draft | TEXT | NULLABLE | AI 初稿（对比用） |
| bjh_article_id | VARCHAR(30) | NULLABLE | 百家号 article_id |
| cover_url | TEXT | NULLABLE | 封面图 URL |
| publish_status | VARCHAR(15) | DEFAULT 'draft' | draft / publishing / published / publish_failed |
| content_warning | VARCHAR(30) | NULLABLE | 内容警告标记，如 `partial_content`（SSE 截断）；文章列表显示橙色警告 Tag |
| published_at | TIMESTAMP | NULLABLE | 发布时间 |

#### task_logs 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | — |
| task_id | INT | FK → tasks.id | 所属任务 |
| step | VARCHAR(20) | NOT NULL | prompt / generate / polish / draft / cover / publish |
| level | VARCHAR(10) | NOT NULL | INFO / WARN / ERROR |
| message | TEXT | NOT NULL | 日志内容 |
| created_at | TIMESTAMP | DEFAULT NOW() | — |

#### schedules 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | — |
| name | VARCHAR(50) | NOT NULL | 定时任务名称 |
| cron_expr | VARCHAR(30) | NOT NULL | Cron 表达式 |
| mode | VARCHAR(10) | NOT NULL | draft / publish |
| timezone | VARCHAR(30) | DEFAULT 'Asia/Shanghai' | 时区 |
| enabled | BOOLEAN | DEFAULT true | 启用状态 |
| last_fired_at | TIMESTAMP | NULLABLE | 上次触发时间 |
| next_fire_at | TIMESTAMP | NULLABLE | 下次触发时间 |
| created_at | TIMESTAMP | DEFAULT NOW() | — |
| updated_at | TIMESTAMP | DEFAULT NOW() | — |

> 定时任务与账号的关联通过 `schedule_accounts` 关联表实现（M:N）。

#### schedule_accounts 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| schedule_id | INT | FK → schedules.id, PK | — |
| account_id | INT | FK → accounts.id, PK | — |

> **联合主键**：`(schedule_id, account_id)`。删除账号时 `ON DELETE CASCADE` 自动清理关联。

#### variable_pools 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | — |
| pool_type | VARCHAR(20) | NOT NULL | angle / persona / style / structure / title_style / time_hook |
| category | VARCHAR(20) | NULLABLE | 品类名（null = 通用池） |
| items | JSONB | NOT NULL | 对象数组，结构：`[{value, weight, enabled}]` |
| updated_at | TIMESTAMP | DEFAULT NOW() | — |

> **UNIQUE** 约束：`(pool_type, category)` 组合唯一。

#### combo_history 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | — |
| account_id | INT | FK → accounts.id | — |
| category | VARCHAR(20) | NOT NULL | — |
| combo_id | VARCHAR(30) | NOT NULL | — |
| used_at | TIMESTAMP | DEFAULT NOW() | — |

#### publish_attempts 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | — |
| article_id | INT | FK → articles.id | 所属文章 |
| request_summary | JSONB | NULLABLE | 发布请求参数摘要 |
| response_code | INT | NULLABLE | 百家号 API 响应码 |
| error_type | VARCHAR(30) | NULLABLE | 错误分类 |
| error_message | TEXT | NULLABLE | 错误详情 |
| attempted_at | TIMESTAMP | DEFAULT NOW() | 尝试时间 |

#### content_events 表

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | SERIAL | PK | — |
| event_type | VARCHAR(30) | NOT NULL | task_created / task_succeeded / task_failed / article_published |
| task_id | INT | FK → tasks.id, NULLABLE | 关联任务 |
| account_id | INT | FK → accounts.id | 关联账号 |
| category | VARCHAR(20) | NOT NULL | 品类 |
| payload | JSONB | NULLABLE | 事件上下文快照（combo_id、mode、error_type 等） |
| created_at | TIMESTAMP | DEFAULT NOW() | — |

> 一期仅做数据落盘，不做报表 UI。用于二期效果归因和 A/B 分析的前置数据基础。

### 9.3 索引设计

| 索引 | 说明 |
|------|------|
| `tasks(status, created_at DESC)` | 按状态筛选 + 时间排序 |
| `tasks(account_id, created_at DESC)` | 按账号筛选 + 时间排序 |
| `tasks(category, created_at DESC)` | 按品类筛选 + 时间排序 |
| `articles(publish_status, created_at DESC)` | 按发布状态筛选 |
| `task_logs(task_id, created_at)` | 按任务查日志 |
| `combo_history(account_id, category, used_at DESC)` | 组合去重查询 |
| `content_events(event_type, created_at DESC)` | 按事件类型查询 |
| `publish_attempts(article_id, attempted_at DESC)` | 按文章查发布尝试 |

## 10. 状态定义

### 10.1 Task 状态

```mermaid
stateDiagram-v2
    [*] --> pending : 任务创建
    pending --> running : Worker 拾取
    pending --> canceled : 用户取消
    running --> success : 全流程完成
    running --> failed : 任何步骤异常
    running --> timeout : 执行超时/Worker 崩溃
```

> `failed` 状态的任务可重试，重试时**创建新 task**（原 task 保持 failed），通过 `retry_of_task_id` 字段追踪链路。

| 状态 | 含义 | 可执行操作 |
|------|------|-----------|
| `pending` | 排队等待 | 取消 |
| `running` | 正在执行 | 查看日志 |
| `success` | 执行成功 | 查看文章、查看日志 |
| `failed` | 执行失败 | 重试、查看日志、查看错误（通过 `error_type` 细分失败类型） |
| `canceled` | 已取消 | 查看日志 |
| `timeout` | 执行超时 | 重试、查看日志 |

### 10.2 Article 发布状态

```mermaid
stateDiagram-v2
    [*] --> draft : 草稿保存成功
    draft --> publishing : 用户点击发布
    draft --> draft : 在线编辑
    publishing --> published : 发布成功
    publishing --> publish_failed : 发布失败
    publish_failed --> publishing : 重试发布
    publish_failed --> draft : 编辑后重新保存
```

| 状态 | 含义 |
|------|------|
| `draft` | 已保存草稿，未发布 |
| `publishing` | 发布中（防止重复点击） |
| `published` | 已发布到百家号 |
| `publish_failed` | 发布失败，可修改后重试 |

> `withdrawn`（已撤回）暂不实现——百家号平台侧撤回无对应 API，后续如有需要可扩展。

### 10.3 Account Cookie 状态

| 状态 | 含义 |
|------|------|
| `unchecked` | 新增后未检测 |
| `active` | Cookie 有效 |
| `expired` | Cookie 已过期 |

---

# 第四部分：接口设计

## 11. API 接口清单

**Base URL**: `/api/v1`  
**认证**: 除 `/auth/login` 外，所有接口需 Header `Authorization: Bearer <jwt_token>`

### 11.1 认证

| 方法 | 路径 | 说明 | 请求体 | 响应 |
|------|------|------|--------|------|
| POST | `/auth/login` | 登录 | `{ "password": "xxx" }` | `{ "token": "jwt...", "expires_in": 7200 }` |
| POST | `/auth/refresh` | 刷新 Token | — | `{ "token": "jwt...", "expires_in": 7200 }` |
| POST | `/auth/ws-ticket` | 换取 WebSocket 一次性票据 | — | `{ "ticket": "xxx", "expires_in": 60 }` |

> 登录限流：同 IP 5 分钟内最多 10 次尝试，超限锁定 15 分钟。修改密码后所有已签发 JWT 自动失效（token 版本号机制）。

### 11.2 仪表盘

| 方法 | 路径 | 说明 | 响应 |
|------|------|------|------|
| GET | `/dashboard/stats` | 今日统计 | `{ "success": 3, "failed": 1, "pending": 0, "total_time": 120.5 }` |
| GET | `/dashboard/recent-tasks` | 最近任务 | `[{ "id", "account_name", "category", "status", "title", "created_at" }]` |
| GET | `/dashboard/account-health` | 账号健康度 | `[{ "id", "name", "cookie_status", "cookie_checked_at" }]` |

### 11.3 账号管理

| 方法 | 路径 | 说明 | 请求体/参数 |
|------|------|------|------------|
| GET | `/accounts` | 账号列表 | — |
| POST | `/accounts` | 新增账号 | `{ "name", "cookie", "categories" }` |
| PUT | `/accounts/{id}` | 编辑账号 | `{ "name", "cookie", "categories" }` |
| DELETE | `/accounts/{id}` | 删除账号 | — |
| POST | `/accounts/{id}/check-cookie` | 检测Cookie | — |
| POST | `/accounts/check-all` | 全部检测 | — |
| GET | `/accounts/export` | 导出配置 | — |
| POST | `/accounts/import` | 导入配置 | `[{ "name", "cookie", "categories" }]` |

### 11.4 任务管理

| 方法 | 路径 | 说明 | 请求体/参数 |
|------|------|------|------------|
| GET | `/tasks` | 任务列表 | Query: `status`, `account_id`, `category`, `date_from`, `date_to`, `page`, `size` |
| POST | `/tasks` | 创建任务 | `{ "account_ids": [1,2], "category": "", "mode": "draft", "topic_keyword": "", "product_name": "", "idempotency_key": "uuid" }` |
| GET | `/tasks/{id}` | 任务详情 | — |
| GET | `/tasks/{id}/logs` | 任务日志 | — |
| POST | `/tasks/{id}/retry` | 重试任务 | — |
| POST | `/tasks/{id}/cancel` | 取消任务 | 仅 `pending` 状态可取消 |
| POST | `/tasks/{id}/force-draft` | 强制转草稿模式 | 仅 `failed` 状态，创建新 task 以 draft 模式重跑 |
| POST | `/tasks/retry-failed` | 重试所有失败 | — |
| POST | `/tasks/publish-drafts` | 发布所有草稿 | — |
| WS | `/ws/tasks/{id}/logs` | 实时日志流 | WebSocket（通过 `?ticket=xxx` 一次性票据鉴权） |

### 11.5 文章管理

| 方法 | 路径 | 说明 | 请求体/参数 |
|------|------|------|------------|
| GET | `/articles` | 文章列表 | Query: `account_id`, `category`, `publish_status`, `page`, `size` |
| GET | `/articles/{id}` | 文章详情 | — |
| PUT | `/articles/{id}` | 编辑文章 | `{ "title", "body_md" }` |
| POST | `/articles/{id}/publish` | 手动发布草稿 | — |

### 11.6 定时任务

| 方法 | 路径 | 说明 | 请求体/参数 |
|------|------|------|------------|
| GET | `/schedules` | 定时列表 | — |
| POST | `/schedules` | 创建定时 | `{ "name", "cron_expr", "account_ids", "mode" }` |
| PUT | `/schedules/{id}` | 编辑定时 | `{ "name", "cron_expr", "account_ids", "mode", "enabled" }` |
| DELETE | `/schedules/{id}` | 删除定时 | — |
| POST | `/schedules/{id}/toggle` | 切换启用状态 | — |

### 11.7 变量池

| 方法 | 路径 | 说明 | 请求体/参数 |
|------|------|------|------------|
| GET | `/pools` | 全部变量池 | — |
| GET | `/pools/{pool_type}` | 指定类型的池 | Query: `category`（可选） |
| PUT | `/pools/{pool_type}` | 更新池内容 | `{ "category": "图书教育", "items": [{"value": "书单推荐", "weight": 1, "enabled": true}] }` |
| GET | `/pools/combo-history` | 组合使用历史 | Query: `account_id`, `category`, `days`(默认7) |

### 11.8 系统设置

| 方法 | 路径 | 说明 | 请求体/参数 |
|------|------|------|------------|
| GET | `/settings` | 获取全部配置 | — |
| PUT | `/settings` | 更新配置 | `{ "run_mode", "aigc_model", "account_delay", "daily_limit", "wecom_webhook", "notify_level", "max_concurrent_accounts", "task_timeout_minutes", "generate_timeout", "polish_timeout", "cover_timeout", "publish_timeout", "draft_timeout" }` |
| PUT | `/settings/password` | 修改密码 | `{ "old_password", "new_password" }` |
| GET | `/settings/logs` | 系统日志 | Query: `level`, `date_from`, `date_to`, `keyword`, `page`, `size` |

## 12. 第三方依赖

| 服务 | 用途 | 接口 |
|------|------|------|
| **百度 AIGC** | AI 文章生成 + 润色 | `aigc.baidu.com/aigc/saas/pc/v1/aiNews/*` |
| **百家号发布 API** | 草稿保存、封面图搜索裁剪、正式发布、分类获取 | `baijiahao.baidu.com/pcui/*` + `/materialui/*` + `/aigc/bjh/*` |
| **企业微信 Webhook** | 运行通知（可选） | `qyapi.weixin.qq.com/cgi-bin/webhook/send` |

> 所有第三方接口通过用户配置的 Cookie 进行认证，**无需独立 API Key**。百度 AIGC 复用百家号 Cookie session。

---

# 第五部分：非功能需求

## 13. 技术栈选型

| 层 | 技术 | 版本 | 理由 |
|---|---|---|---|
| **后端框架** | FastAPI | 0.110+ | 异步原生、WebSocket 支持、自动 OpenAPI 文档 |
| **语言** | Python | 3.11 | 复用 v7 已调通的 600+ 行核心 API 集成代码 |
| **ORM** | SQLAlchemy | 2.0 | 成熟稳定，支持 async |
| **数据库迁移** | Alembic | — | SQLAlchemy 配套 |
| **任务队列** | Celery | 5.3+ | 异步任务执行、定时调度（Beat） |
| **消息中间件** | Redis | 7 | Celery broker + WebSocket 通道 |
| **数据库** | PostgreSQL | 16 | 生产级可靠性，JSONB 原生支持 |
| **前端框架** | Vue 3 + Vite | — | 组件化、HMR 开发效率高 |
| **前端 UI 库** | — | — | 根据实际选型（如 Naive UI 或自绘） |
| **Web 服务器** | Nginx | alpine | 反向代理 + 前端静态文件托管 |
| **容器化** | Docker + Docker Compose | — | 一键部署 |

## 14. 安全要求

| 项目 | 要求 |
|------|------|
| **认证** | 密码登录 → JWT Token（access_token 有效期 2h），所有 API 鉴权。支持 `POST /auth/refresh` 续期 |
| **登录限流** | 同 IP 5 分钟内最多 10 次登录尝试，超限锁定 15 分钟 |
| **密码变更** | 修改密码后自动使所有已签发 JWT 失效（token 版本号机制） |
| **Cookie 存储** | AES-256-CBC 加密存储，密钥通过环境变量注入 |
| **前端脱敏** | Cookie 字段仅显示前 6 位 + `****` + 后 4 位 |
| **密码存储** | bcrypt 哈希 |
| **导出加密** | 账号导出采用口令加密：`PBKDF2-HMAC-SHA256`（迭代≥600,000，salt 16B）+ `AES-256-GCM`（IV 12B，含认证标签）。文件格式：`salt+IV+ciphertext+auth_tag`。下载链接一次性或 5 分钟过期，操作记录审计日志 |
| **WebSocket 鉴权** | 通过一次性 `ws_ticket` 票据鉴权（60s 有效、单次消费，存 Redis），避免 JWT 泄漏于 URL |
| **CORS** | 生产环境仅允许同源请求 |
| **传输加密** | 建议 Nginx 配置 HTTPS（用户自行挂证书） |
| **环境变量** | 敏感配置（ADMIN_PASSWORD、COOKIE_SECRET_KEY、DATABASE_URL）通过 `.env` 注入，不入代码库 |

## 15. 性能要求

| 指标 | 要求 | 说明 |
|------|------|------|
| CRUD 接口 | P95 < 200ms | 账号/变量池/设置等简单读写 |
| 列表查询 | P95 < 500ms | 任务列表、文章列表、日志查询（含分页） |
| 统计接口 | P95 < 1000ms | Dashboard 聚合统计 |
| 并发用户 | 1-5 | 单用户系统，不需要高并发 |
| 任务执行时长 | 1-3 min/账号 | 受百度 AIGC 响应速度影响，非系统瓶颈 |
| WebSocket 延迟 | < 500ms | 日志实时推送 |
| 数据保留 | 30 天 | task_logs 自动清理；tasks/articles 永久保留 |

## 16. 部署方案

### 16.1 Docker Compose 服务

```yaml
services:
  nginx:        # 反向代理 + 前端
  backend:      # FastAPI 主应用
  worker:       # Celery Worker
  beat:         # Celery Beat 定时调度
  redis:        # 消息队列
  postgres:     # 数据库
```

### 16.2 数据持久化

| 服务 | Volume |
|------|--------|
| postgres | `pgdata:/var/lib/postgresql/data` |
| redis | 无需持久化（仅消息中间件） |
| backend | 日志文件挂载（可选） |

### 16.3 环境变量

```bash
# .env
ADMIN_PASSWORD=your_admin_password
COOKIE_SECRET_KEY=your_32_byte_hex_key
DATABASE_URL=postgresql://bjh:password@postgres:5432/bjh_db
REDIS_URL=redis://redis:6379/0
AIGC_MODEL=ds_v3
```

### 16.4 启动命令

```bash
# 首次部署
docker compose up -d --build

# 数据库初始化
docker compose exec backend alembic upgrade head

# 查看日志
docker compose logs -f backend worker
```

---

# 第六部分：实施规划

## 17. 分期计划

### Phase 1: 基础骨架（MVP）

**目标**：能跑起来，能管理账号，能手动触发任务看到结果。

| 模块 | 内容 |
|------|------|
| 基础设施 | Docker Compose 6 服务搭建、数据库 Schema、Alembic 迁移 |
| 后端骨架 | FastAPI 项目结构、SQLAlchemy Models、JWT 认证 |
| 账号管理 | CRUD API + Cookie 检测 |
| 核心任务 | v7 核心类迁移为 services、Celery 任务定义、手动创建任务 API |
| 前端骨架 | Vue 3 + 路由 + 布局、登录页、账号管理页、任务列表页 |

### Phase 2: 核心体验

**目标**：任务面板可用、实时日志、文章管理。

| 模块 | 内容 |
|------|------|
| 任务卡片 | 6 步进度展示、状态更新 |
| 实时日志 | WebSocket 推送 + 前端日志流组件 |
| 文章管理 | 列表、详情预览、初稿/润色对比 |
| 重试机制 | 单任务重试、批量重试失败 |
| 草稿发布 | 在线编辑 + 手动发布 |

### Phase 3: 完善功能

**目标**：定时任务、变量池管理、仪表盘统计。

| 模块 | 内容 |
|------|------|
| 定时任务 | CRUD + Celery Beat 集成 + 执行历史 |
| 变量池 | 在线编辑 + combo_id 历史 + 去重提示 |
| 仪表盘 | 统计卡片 + 账号健康度 + 最近任务 |
| 系统设置 | 全局配置管理界面 |
| 企微通知 | 失败通知 + 每日汇总 |

### Phase 4: 安全与部署优化

**目标**：生产就绪。

| 模块 | 内容 |
|------|------|
| Cookie 加密 | AES-256 加解密实现 |
| 生产配置 | Nginx HTTPS 配置模板、Docker 健康检查 |
| 日志管理 | 系统日志浏览器 + 自动清理 |
| 文档 | README + 部署文档 + 环境变量说明 |
| 导入导出 | 账号批量导入/导出 |

## 18. 范围界定

### ✅ 做什么（In Scope）

| 功能 | 说明 |
|------|------|
| 多账号 Web 管理 | 账号 CRUD、Cookie 检测与加密存储 |
| AI 文章生成 | 6 维变量池 + 百度 AIGC 调用（生成 + 润色） |
| 百家号自动发布 | 草稿保存 → 封面图搜索 → 正式发布 |
| 任务面板 | 手动/定时创建、进度监控、实时日志、重试 |
| 文章管理 | 列表、预览、编辑、草稿发布 |
| 变量池在线编辑 | 角度/人设/风格等变量池 CRUD |
| 企微通知 | 失败即时通知 + 每日汇总 |
| Docker 部署 | Docker Compose 一键启动 |

> **声明**：当前系统无支付链路、无资金流转、不涉及佣金结算。二期 CPS 集成时需新增独立的 CPS 数据模型。

### ❌ 不做什么（Out of Scope）

| 功能 | 说明 |
|------|------|
| 第二阶段 CPS 变现 | 商品推广链接嵌入、返佣追踪（未来迭代，二期需新增独立 CPS 数据模型） |
| AI 生图 | 使用百度 text2img 接口自动配图（仅搜索正版图库） |
| 多用户权限 | 当前单管理员，不做 RBAC 多角色（预留扩展） |
| 百家号数据采集 | 不采集文章阅读量、粉丝增长等数据（但通过 `content_events` 表落盘发布事件作为二期分析基础） |
| 移动端适配 | Web 端桌面优先，不单独做移动端 |
| Dify 工作流集成 | 系统独立运行，不再依赖 Dify 平台 |
| Cookie 自动获取 | 用户需手动从浏览器复制 Cookie 粘贴到系统 |
| acs-token 破解 | 继续使用草稿方案绕过，不尝试逆向 acs-token |

---

## 附录：v1.0 → v1.1 评审修改汇总

> 以下为三轮评审（C-001 ~ C-028 + R-001 ~ R-003，共 31 条）达成共识后的修改清单。

### 数据模型变更

| 修改点 | 来源 | 说明 |
|--------|------|------|
| tasks 表新增 `retry_of_task_id` | C-005 | 追踪重试链路，替代错误的 `failed→pending` 状态转换 |
| tasks 表新增 `error_type` | C-017 | 失败细分类型（如 `publish_failed_draft_saved`、`aigc_timeout`） |
| tasks 表新增 `timeout_at` | C-009 | Worker 拾取时设置超时截止时间 |
| tasks 表新增 `last_step_at` | C-025/R-003 | 步骤级超时判定依据 |
| tasks.status 扩展 | C-001/C-017 | 新增 `canceled`、`timeout` 枚举值 |
| schedules 表新增 `timezone`/`last_fired_at`/`next_fire_at` | C-010 | 时区支持 + 触发追踪 |
| 恢复 `schedule_accounts` 关联表 | C-004/R-002 | 替代 JSONB 方案，`ON DELETE CASCADE` 保证一致性 |
| 删除 `schedules.account_ids` JSONB 字段 | C-004/R-002 | 被关联表方案替代 |
| articles.publish_status 扩展 | C-018 | 新增 `publishing`、`publish_failed` 状态 |
| 新增 `publish_attempts` 表 | C-016/C-028 | 轻量审计：记录每次发布 API 的请求摘要、响应码、错误 |
| 新增 `content_events` 表 | C-019/R-001 | 结构化事件落盘（4 类事件），二期归因分析基础 |
| variable_pools.items 升级 | C-020 | 从字符串数组改为 `[{value, weight, enabled}]` 对象数组 |
| 新增 9.3 索引设计 | C-015 | 8 个复合索引覆盖主要筛选排序场景 |

### 状态机变更

| 修改点 | 来源 | 说明 |
|--------|------|------|
| 移除 `failed→pending` 转换 | C-005 | 重试创建新 task，原 task 保持 failed |
| 新增 `pending→canceled` | C-001 | 用户取消排队中任务 |
| 新增 `running→timeout` | C-009/C-017 | Worker 崩溃/超时恢复 |
| Article 状态扩展 | C-018 | `draft→publishing→published`，异常 `publish_failed` |

### 业务规则变更

| 修改点 | 来源 | 说明 |
|--------|------|------|
| TASK-02 跨账号并发可配 | C-007 | 默认 1，最大 3，增加 `max_concurrent_accounts` |
| TASK-07 幂等/去重 | C-002 | `idempotency_key` + 60s 同品类防重 |
| TASK-08 风控退避 | C-007 | 连续失败 3 次冷却 30 分钟 |
| TASK-09 步骤级超时 | C-025/R-003 | 按步骤配置阈值 + 总超时兜底，参数暴露至系统设置 API |
| TASK-10 超时回收机制 | C-009 | Celery Beat 每 2 分钟扫描 running 任务，超时转 timeout |
| TASK-11 Misfire 补执行 | C-010 | 重启后补执行错过的定时任务（24h 内补一次） |
| AI-02 SSE 无数据超时 | C-011 | 30s 无新数据包视为断开 |
| AI-06 partial_content 降级 | C-011/C-026 | 截断内容统一转 draft_only，需人工确认 |
| AI-07 失败分类 | C-011 | timeout/connection_error/parse_error/empty_response |

### API 变更

| 修改点 | 来源 | 说明 |
|--------|------|------|
| 新增 `POST /tasks/{id}/cancel` | C-001 | 取消排队中任务 |
| 新增 `POST /tasks/{id}/force-draft` | C-003 | 强制以 draft 模式重跑 failed 任务 |
| 新增 `POST /auth/refresh` | C-012 | JWT 续期（access_token 2h 有效） |
| 新增 `POST /auth/ws-ticket` | C-022 | WebSocket 一次性票据 |
| `POST /tasks` 新增 `idempotency_key` | C-002 | 防重复提交 |
| WebSocket 改为 ticket 鉴权 | C-014/C-022 | `?ticket=xxx` 替代 `?token=xxx` |
| `PUT /settings` 扩展配置项 | C-007/C-025/R-003 | 新增 `max_concurrent_accounts` + 5 个步骤超时参数 + `task_timeout_minutes` |

### 安全变更

| 修改点 | 来源 | 说明 |
|--------|------|------|
| JWT 有效期 24h → 2h | C-012 | 缩短会话窗口 |
| 登录限流 | C-012 | 5 分钟 10 次，超限锁 15 分钟 |
| 导出加密规范 | C-013/C-027 | PBKDF2 + AES-256-GCM 完整密码学规范 |
| WebSocket ws_ticket | C-014/C-022 | 一次性票据避免 JWT 泄漏于 URL |
| 密码变更失效 | C-012 | 修改密码后所有 token 失效 |

### 功能与性能变更

| 修改点 | 来源 | 说明 |
|--------|------|------|
| 任务步骤动态展示 | C-006 | draft 4 步 / publish 6 步 |
| force_draft_only 动作 | C-003 | 将 failed 任务降级为仅保存草稿 |
| 性能 SLO 分级 | C-008 | CRUD<200ms / 列表<500ms / 统计<1000ms |
| 无支付链路声明 | C-021 | 明确当前不涉及资金流转 |

