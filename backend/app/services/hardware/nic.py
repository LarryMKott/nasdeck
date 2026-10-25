"""网卡采集：psutil 枚举 + Linux 下读协商速率。"""

from __future__ import annotations

import psutil

from app.services.hardware.base import BaseCollector
from app.utils.sysfs import read_int


class NicCollector(BaseCollector):
    kind = "nic"

    async def collect(self) -> dict:
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        nics = []
        for name, stat in stats.items():
            if name == "lo":
                continue
            nic = {
                "name": name,
                "up": stat.isup,
                "speed_mbps": stat.speed if stat.speed > 0 else None,
                "mtu": stat.mtu,
            }
            for addr in addrs.get(name, []):
                if addr.family.name == "AF_INET":
                    nic["ipv4"] = addr.address
            # sysfs 覆盖：-1（未知）与 65535（ETH_SPEED_UNKNOWN）是驱动占位值，
            # 不滤会把 psutil 已置 None 的速率覆盖成假数（评审 E 域 P2-F）
            speed_path = f"/sys/class/net/{name}/speed"
            speed = read_int(speed_path)
            if speed is not None and 0 < speed < 65535:
                nic["speed_mbps"] = speed
            nics.append(nic)
        return {"name": nics[0]["name"] if nics else "", "available": bool(nics), "nics": nics}
