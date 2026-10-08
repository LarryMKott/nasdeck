#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一网关存活探针服务：监听 ${TRIM_APPDEST}/gwprobe.sock（AF_UNIX）。

任何 GET/POST/HEAD 返回 200 固定体（含 pid 与存活秒数）——入口存活即 200，
入口被清空则网关 404，两者可区分。请求行 + 网关身份头写成 JSON 行落 stdout
（cmd/main 重定向到 TRIM_PKGVAR/app.log），供真机核查网关是否转发
X-Trim-Userid / X-Trim-Isadmin / X-Trim-Username（nasdeck 网关化改造的鉴权依据）。
"""
import json
import os
import socket
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

SOCK_PATH = os.environ.get("GWPROBE_SOCK") or os.path.join(
    os.environ.get("TRIM_APPDEST", "/var/apps/com.test.gatewayprobe/target"), "gwprobe.sock"
)
START_TS = time.time()

# 网关侧应转发的身份头（gateway-registration.md 文档承诺）+ 诊断用旁证
WATCH_HEADERS = (
    "X-Trim-Userid", "X-Trim-Isadmin", "X-Trim-Username",
    "Host", "X-Forwarded-For", "X-Real-IP", "User-Agent",
)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _log(self) -> None:
        record = {
            "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "method": self.command,
            "path": self.path,
        }
        for h in WATCH_HEADERS:
            v = self.headers.get(h)
            if v:
                record[h] = v
        print(json.dumps(record, ensure_ascii=False), flush=True)

    def _respond(self) -> None:
        body = f"gwprobe-alive pid={os.getpid()} up={time.time() - START_TS:.0f}s\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        self._log()
        self._respond()

    def do_POST(self):
        self._log()
        self._respond()

    def do_HEAD(self):
        self._log()
        self._respond()

    def log_message(self, *args):  # 默认格式弃用，_log 的 JSON 行替代
        pass


# AF_UNIX 是 POSIX 标准能力（NAS 上恒有）；守卫只为开发机（Windows Python）可导入本模块做
# Handler 层测试，开发机不会经 main() 走 UDS 绑定
if hasattr(socket, "AF_UNIX"):

    class UDSServer(HTTPServer):
        address_family = socket.AF_UNIX

        def server_bind(self):
            try:
                os.unlink(self.server_address)
            except OSError:
                pass
            super().server_bind()
            # 网关转发进程的 UID 未文档化，0666 保证可连接（探针临时包，从宽）
            os.chmod(self.server_address, 0o666)

else:
    UDSServer = HTTPServer


def main() -> None:
    sys.stderr.write(f"[gwprobe] listening on {SOCK_PATH}\n", )
    sys.stderr.flush()
    UDSServer(SOCK_PATH, Handler).serve_forever()


if __name__ == "__main__":
    main()
