"""10 分钟级周报调度拍：读计划配置命中窗口即广播（配置读库零 fork，
广播仅命中时发生——默认关闭态每拍只读一行设置）。"""

from __future__ import annotations

import logging

from app.db.session import session_factory
from app.services.report import digest as report_digest

logger = logging.getLogger(__name__)


async def report_10m_tick() -> None:
    """周报调度拍（调度器 10 分钟间隔驱动；异常吞掉不拖垮调度轮）。"""
    try:
        async with session_factory() as db:
            fired = await report_digest.schedule_tick(db)
            await db.commit()
        if fired:
            logger.info("周报已推送")
    except Exception as exc:  # noqa: BLE001
        logger.warning("report_10m 异常: %s", exc)
