"""网卡采集：psutil 枚举 + Linux 下读协商速率。"""

from __future__ import annotations

import psutil

from app.services.hardware.base import BaseCollector
from app.utils.sysfs import read_int, read_text


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
            speed_path = f"/sys/class/net/{name}/speed"
            if read_text(speed_path) is None:
                nic["driver"] = None
            else:
                nic["speed_mbps"] = read_int(speed_path) or nic["speed_mbps"]
            nics.append(nic)
        return {"name": nics[0]["name"] if nics else "", "available": bool(nics), "nics": nics}
