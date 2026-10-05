"""网卡采集：psutil 枚举 + Linux 下读协商速率。"""

from __future__ import annotations

import psutil

from app.services.hardware.base import BaseCollector
from app.utils.sysfs import read_int


class NicCollector(BaseCollector):
    """网卡硬件清单采集器（kind="nic"）。

    数据来源：psutil net_if_stats/net_if_addrs 枚举（剔除 lo 回环）+ Linux 下
    /sys/class/net/<name>/speed 直读协商速率（psutil 速率为 0 时补充）。
    """

    kind = "nic"

    async def collect(self) -> dict:
        """枚举物理网卡及其状态/速率/地址。

        Returns:
            dict: available 表示是否枚举到非 lo 网卡；name 取首卡名（无卡为空串）。
                nics 每项含 name/up/speed_mbps/mtu，有 IPv4 地址时附 ipv4；
                speed_mbps 优先取 /sys 协商速率，psutil 报 0 且 /sys 不可读时为 None。
        """
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
            if read_int(speed_path):
                nic["speed_mbps"] = read_int(speed_path)
            nics.append(nic)
        return {"name": nics[0]["name"] if nics else "", "available": bool(nics), "nics": nics}
