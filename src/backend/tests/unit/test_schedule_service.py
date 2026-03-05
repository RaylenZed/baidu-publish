"""
单元测试：schedule_service.py 中不依赖 DB 的纯方法。
涵盖 Cron 校验、下次触发时间计算，以及 recover_misfire 条件逻辑。
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.services.schedule_service import ScheduleService

svc = ScheduleService()


# ── _validate_cron ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expr", [
    "0 22 * * *",      # 每天 22:00
    "*/5 * * * *",     # 每 5 分钟
    "0 9 * * 1-5",     # 工作日 9:00
    "30 8 1 * *",      # 每月 1 日 8:30
])
def test_validate_cron_valid(expr):
    assert svc._validate_cron(expr, "Asia/Shanghai") is True


@pytest.mark.parametrize("expr", [
    "not_a_cron",
    "99 99 99 99 99",
    "",
    "* * * *",         # 缺少一个字段
])
def test_validate_cron_invalid(expr):
    assert svc._validate_cron(expr, "Asia/Shanghai") is False


# ── _calc_next_fire ───────────────────────────────────────────────────────────

def test_calc_next_fire_is_in_future():
    """计算结果必须是将来的时间。"""
    next_fire = svc._calc_next_fire("0 22 * * *", "Asia/Shanghai")
    now_utc = datetime.now(timezone.utc)
    assert next_fire > now_utc


def test_calc_next_fire_is_utc_aware():
    """返回值必须是带时区信息的 UTC datetime。"""
    next_fire = svc._calc_next_fire("*/5 * * * *", "Asia/Shanghai")
    assert next_fire.tzinfo is not None
    assert next_fire.utcoffset().total_seconds() == 0


def test_calc_next_fire_unknown_timezone_falls_back():
    """未知时区降级为 Asia/Shanghai，不抛异常。"""
    next_fire = svc._calc_next_fire("0 8 * * *", "Invalid/Timezone")
    assert next_fire > datetime.now(timezone.utc)


# ── recover_misfire 条件逻辑 ──────────────────────────────────────────────────

class FakeSchedule:
    """最小化 Schedule 模型替身，用于测试条件判断。"""
    def __init__(self, enabled: bool, next_fire_at: datetime):
        self.enabled = enabled
        self.next_fire_at = next_fire_at


def _should_recover(schedule: FakeSchedule, now: datetime) -> bool:
    """
    与 recover_misfire 查询条件对齐的纯 Python 谓词。
    用于验证"24h 内错过的触发且当前已过期"逻辑。
    """
    threshold = now - timedelta(hours=ScheduleService._MISFIRE_THRESHOLD_HOURS)
    return (
        schedule.enabled
        and schedule.next_fire_at >= threshold
        and schedule.next_fire_at <= now
    )


def test_misfire_overdue_within_24h_should_recover():
    now = datetime.now(timezone.utc)
    sch = FakeSchedule(enabled=True, next_fire_at=now - timedelta(hours=1))
    assert _should_recover(sch, now) is True


def test_misfire_overdue_older_than_24h_should_not_recover():
    now = datetime.now(timezone.utc)
    sch = FakeSchedule(enabled=True, next_fire_at=now - timedelta(hours=25))
    assert _should_recover(sch, now) is False


def test_misfire_future_schedule_should_not_recover():
    now = datetime.now(timezone.utc)
    sch = FakeSchedule(enabled=True, next_fire_at=now + timedelta(hours=1))
    assert _should_recover(sch, now) is False


def test_misfire_disabled_schedule_should_not_recover():
    now = datetime.now(timezone.utc)
    sch = FakeSchedule(enabled=False, next_fire_at=now - timedelta(minutes=30))
    assert _should_recover(sch, now) is False


def test_misfire_exactly_at_boundary_should_recover():
    """恰好在 24h 边界上的触发应被补执行。"""
    now = datetime.now(timezone.utc)
    sch = FakeSchedule(enabled=True, next_fire_at=now - timedelta(hours=24))
    assert _should_recover(sch, now) is True
