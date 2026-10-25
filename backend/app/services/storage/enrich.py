"""磁盘清单富化：lsblk 裸列表 + 别名 + SMART 健康/温度（存储页与健康报告共用）。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.monitor import temperature
from app.services.storage import disk_name
from app.services.storage import volumes as volume_service
from app.utils.validators import smart_health_key


async def enriched_disks(db: AsyncSession) -> list[dict]:
    """lsblk 盘列表就地补 alias/health/temp_c 后返回。

    健康与温度来自 SMART 慢采集缓存（temperature 60s 一轮，零额外 fork）；
    键口径统一走 smart_health_key（nvme0n1 → nvme0）。健康报告此前直接用
    裸 lsblk 列表，磁盘表健康恒 unknown、温度恒 —（评审 B 域 N-2）。
    """
    disks = await volume_service.list_disks()
    aliases = await disk_name.get_alias_map(db)
    health_map = await temperature.disk_health()
    temps = await temperature.disk_temps()
    for d in disks:
        d["alias"] = aliases.get(d.get("serial") or "")
        key = smart_health_key(d.get("device") or "")
        d["health"] = health_map.get(key, "unknown")
        d["temp_c"] = temps.get(key)
    return disks
