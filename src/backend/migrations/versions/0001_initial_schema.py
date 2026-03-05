"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-04 12:00:00.000000

建立全量初始 Schema：11 张表 + 枚举类型 + 索引。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 枚举类型（按依赖顺序创建）────────────────────────────────────────────

    cookie_status_enum = sa.Enum(
        "active", "expired", "unchecked",
        name="cookie_status_enum",
        create_type=True,
    )
    task_mode_enum = sa.Enum(
        "draft", "publish",
        name="task_mode_enum",
        create_type=True,
    )
    task_status_enum = sa.Enum(
        "pending", "running", "success", "failed", "canceled", "timeout",
        name="task_status_enum",
        create_type=True,
    )
    task_error_type_enum = sa.Enum(
        "aigc_timeout", "connection_error", "parse_error", "empty_response",
        "publish_failed_draft_saved", "token_refresh_failed",
        "timeout", "worker_crash",
        name="task_error_type_enum",
        create_type=True,
    )
    task_warning_enum = sa.Enum(
        "partial_content",
        name="task_warning_enum",
        create_type=True,
    )
    task_step_enum = sa.Enum(
        "prompt", "generate", "polish", "draft", "cover", "publish",
        name="task_step_enum",
        create_type=True,
    )
    log_level_enum = sa.Enum(
        "INFO", "WARN", "ERROR",
        name="log_level_enum",
        create_type=True,
    )
    publish_status_enum = sa.Enum(
        "draft", "publishing", "published", "publish_failed",
        name="publish_status_enum",
        create_type=True,
    )
    content_warning_enum = sa.Enum(
        "partial_content",
        name="content_warning_enum",
        create_type=True,
    )
    pool_type_enum = sa.Enum(
        "angle", "persona", "style", "structure", "title_style", "time_hook",
        name="pool_type_enum",
        create_type=True,
    )
    aigc_model_enum = sa.Enum(
        "ds_v3", "ernie",
        name="aigc_model_enum",
        create_type=True,
    )
    notify_level_enum = sa.Enum(
        "all", "failure_only", "off",
        name="notify_level_enum",
        create_type=True,
    )
    content_event_type_enum = sa.Enum(
        "task_created", "task_succeeded", "task_failed", "article_published",
        name="content_event_type_enum",
        create_type=True,
    )

    # ── accounts 表 ──────────────────────────────────────────────────────────

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("name", sa.String(50), nullable=False, comment="账号名称，全局唯一，长度 1-50"),
        sa.Column("cookie_encrypted", sa.Text(), nullable=False, comment="AES-256-GCM 加密后的 Cookie"),
        sa.Column(
            "categories",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="绑定品类列表（1-2 个）",
        ),
        sa.Column(
            "cookie_status",
            cookie_status_enum,
            nullable=False,
            server_default="unchecked",
            comment="Cookie 状态",
        ),
        sa.Column("cookie_checked_at", sa.DateTime(timezone=True), nullable=True, comment="上次检测时间（UTC）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "ix_accounts_categories_gin",
        "accounts",
        ["categories"],
        postgresql_using="gin",
    )

    # ── system_settings 表 ──────────────────────────────────────────────────

    op.create_table(
        "system_settings",
        sa.Column("id", sa.Integer(), nullable=False, server_default="1", comment="固定为 1（Singleton）"),
        sa.Column("run_mode", task_mode_enum, nullable=False, server_default="draft", comment="全局默认运行模式"),
        sa.Column("aigc_model", aigc_model_enum, nullable=False, server_default="ds_v3", comment="AIGC 模型"),
        sa.Column("account_delay", sa.Integer(), nullable=False, server_default="10", comment="账号间延迟（秒）"),
        sa.Column("max_concurrent_accounts", sa.Integer(), nullable=False, server_default="1", comment="跨账号最大并发数"),
        sa.Column("daily_limit", sa.Integer(), nullable=False, server_default="3", comment="单账号每日最大执行次数"),
        sa.Column("task_timeout_minutes", sa.Integer(), nullable=False, server_default="15", comment="单任务总超时（分钟）"),
        sa.Column("generate_timeout", sa.Integer(), nullable=False, server_default="240", comment="AI 生成超时（秒）"),
        sa.Column("polish_timeout", sa.Integer(), nullable=False, server_default="240", comment="AI 润色超时（秒）"),
        sa.Column("cover_timeout", sa.Integer(), nullable=False, server_default="60", comment="封面搜索超时（秒）"),
        sa.Column("publish_timeout", sa.Integer(), nullable=False, server_default="60", comment="正式发布超时（秒）"),
        sa.Column("draft_timeout", sa.Integer(), nullable=False, server_default="60", comment="草稿保存超时（秒）"),
        sa.Column("wecom_webhook", sa.Text(), nullable=True, comment="企业微信 Webhook URL"),
        sa.Column("notify_level", notify_level_enum, nullable=False, server_default="failure_only", comment="通知级别"),
        sa.Column("admin_password_hash", sa.Text(), nullable=False, comment="管理员密码 bcrypt 哈希"),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1", comment="JWT token 版本号"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── schedules 表 ────────────────────────────────────────────────────────

    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("name", sa.String(50), nullable=False, comment="定时任务名称"),
        sa.Column("cron_expr", sa.String(30), nullable=False, comment="Cron 表达式"),
        sa.Column("mode", task_mode_enum, nullable=False, comment="运行模式"),
        sa.Column("timezone", sa.String(30), nullable=False, server_default="Asia/Shanghai", comment="调度时区"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true", comment="是否启用"),
        sa.Column("last_fired_at", sa.DateTime(timezone=True), nullable=True, comment="上次触发时间（UTC）"),
        sa.Column("next_fire_at", sa.DateTime(timezone=True), nullable=True, comment="下次触发时间（UTC）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── tasks 表 ────────────────────────────────────────────────────────────

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("account_id", sa.Integer(), nullable=False, comment="所属账号 ID"),
        sa.Column("schedule_id", sa.Integer(), nullable=True, comment="来源定时任务 ID，手动触发为 NULL"),
        sa.Column("retry_of_task_id", sa.Integer(), nullable=True, comment="重试来源任务 ID"),
        sa.Column("category", sa.String(20), nullable=False, comment="本次执行品类"),
        sa.Column("mode", task_mode_enum, nullable=False, comment="运行模式"),
        sa.Column("status", task_status_enum, nullable=False, server_default="pending", comment="任务状态"),
        sa.Column("error_type", task_error_type_enum, nullable=True, comment="失败细分类型"),
        sa.Column("warning", task_warning_enum, nullable=True, comment="任务执行级警告"),
        sa.Column("idempotency_key", sa.String(100), nullable=True, comment="幂等 key"),
        sa.Column("combo_id", sa.String(30), nullable=True, comment="变量组合标识"),
        sa.Column("topic_keyword", sa.String(50), nullable=True, comment="主题关键词"),
        sa.Column("product_name", sa.String(50), nullable=True, comment="产品/品牌名"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="失败原因详情"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True, comment="Worker 拾取任务时间（UTC）"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True, comment="任务完成时间（UTC）"),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=True, comment="超时截止时间（UTC）"),
        sa.Column("last_step_at", sa.DateTime(timezone=True), nullable=True, comment="最近步骤完成时间（UTC）"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, comment="任务创建时间（UTC）"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["retry_of_task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_status_created_at", "tasks", ["status", "created_at"])
    op.create_index("ix_tasks_account_id_created_at", "tasks", ["account_id", "created_at"])
    op.create_index("ix_tasks_category_created_at", "tasks", ["category", "created_at"])
    op.create_index("ix_tasks_idempotency_key", "tasks", ["idempotency_key"])

    # ── articles 表 ─────────────────────────────────────────────────────────

    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("task_id", sa.Integer(), nullable=False, comment="关联任务 ID（1:1 唯一）"),
        sa.Column("title", sa.String(100), nullable=False, comment="文章标题"),
        sa.Column("body_md", sa.Text(), nullable=False, comment="润色后 Markdown 正文"),
        sa.Column("body_html", sa.Text(), nullable=False, comment="转换后的百家号 HTML 正文"),
        sa.Column("raw_draft", sa.Text(), nullable=True, comment="AI 初稿原文"),
        sa.Column("bjh_article_id", sa.String(30), nullable=True, comment="百家号平台侧 article_id"),
        sa.Column("cover_url", sa.Text(), nullable=True, comment="封面图 URL"),
        sa.Column(
            "publish_status",
            publish_status_enum,
            nullable=False,
            server_default="draft",
            comment="发布状态",
        ),
        sa.Column("content_warning", content_warning_enum, nullable=True, comment="内容级警告"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True, comment="发布成功时间（UTC）"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id"),
    )
    op.create_index("ix_articles_publish_status_created_at", "articles", ["publish_status", "created_at"])

    # ── task_logs 表 ─────────────────────────────────────────────────────────

    op.create_table(
        "task_logs",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("task_id", sa.Integer(), nullable=False, comment="所属任务 ID"),
        sa.Column("step", task_step_enum, nullable=False, comment="执行步骤"),
        sa.Column("level", log_level_enum, nullable=False, comment="日志级别"),
        sa.Column("message", sa.Text(), nullable=False, comment="日志内容"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_logs_task_id_created_at", "task_logs", ["task_id", "created_at"])

    # ── schedule_accounts 表 ─────────────────────────────────────────────────

    op.create_table(
        "schedule_accounts",
        sa.Column("schedule_id", sa.Integer(), nullable=False, comment="定时任务 ID"),
        sa.Column("account_id", sa.Integer(), nullable=False, comment="账号 ID"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["schedule_id"], ["schedules.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("schedule_id", "account_id"),
        sa.UniqueConstraint("schedule_id", "account_id", name="uq_schedule_accounts"),
    )

    # ── variable_pools 表 ───────────────────────────────────────────────────

    op.create_table(
        "variable_pools",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("pool_type", pool_type_enum, nullable=False, comment="池类型"),
        sa.Column("category", sa.String(20), nullable=True, comment="品类名（NULL=通用池）"),
        sa.Column(
            "items",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="池项目数组 [{value, weight, enabled}]",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pool_type", "category", name="uq_variable_pools_type_category"),
    )

    # ── combo_history 表 ─────────────────────────────────────────────────────

    op.create_table(
        "combo_history",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("account_id", sa.Integer(), nullable=False, comment="使用此组合的账号 ID"),
        sa.Column("category", sa.String(20), nullable=False, comment="品类名"),
        sa.Column("combo_id", sa.String(30), nullable=False, comment="变量组合标识"),
        sa.Column("task_id", sa.Integer(), nullable=True, comment="关联任务 ID"),
        sa.Column("used_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_combo_history_account_category_used_at",
        "combo_history",
        ["account_id", "category", "used_at"],
    )

    # ── publish_attempts 表 ──────────────────────────────────────────────────

    op.create_table(
        "publish_attempts",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("article_id", sa.Integer(), nullable=False, comment="所属文章 ID"),
        sa.Column(
            "request_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="发布请求参数摘要",
        ),
        sa.Column("response_code", sa.Integer(), nullable=True, comment="百家号 API 响应码"),
        sa.Column("error_type", sa.String(30), nullable=True, comment="错误分类"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误详情"),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["article_id"], ["articles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_publish_attempts_article_id_attempted_at",
        "publish_attempts",
        ["article_id", "attempted_at"],
    )

    # ── content_events 表 ───────────────────────────────────────────────────

    op.create_table(
        "content_events",
        sa.Column("id", sa.Integer(), nullable=False, comment="主键"),
        sa.Column("event_type", content_event_type_enum, nullable=False, comment="事件类型"),
        sa.Column("task_id", sa.Integer(), nullable=True, comment="关联任务 ID"),
        sa.Column("account_id", sa.Integer(), nullable=False, comment="关联账号 ID"),
        sa.Column("category", sa.String(20), nullable=False, comment="品类名"),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="事件上下文快照",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_content_events_event_type_created_at",
        "content_events",
        ["event_type", "created_at"],
    )


def downgrade() -> None:
    # 删除顺序：先删依赖表，再删被依赖表
    op.drop_table("content_events")
    op.drop_table("publish_attempts")
    op.drop_table("combo_history")
    op.drop_table("variable_pools")
    op.drop_table("schedule_accounts")
    op.drop_table("task_logs")
    op.drop_table("articles")
    op.drop_table("tasks")
    op.drop_table("schedules")
    op.drop_table("system_settings")
    op.drop_table("accounts")

    # 删除枚举类型
    for enum_name in [
        "content_event_type_enum",
        "notify_level_enum",
        "aigc_model_enum",
        "pool_type_enum",
        "content_warning_enum",
        "publish_status_enum",
        "log_level_enum",
        "task_step_enum",
        "task_warning_enum",
        "task_error_type_enum",
        "task_status_enum",
        "task_mode_enum",
        "cookie_status_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
