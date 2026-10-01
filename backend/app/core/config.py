"""全局配置：Pydantic Settings，环境变量 NASDECK_ 前缀。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NASDECK_", env_file=APP_ROOT / ".env", extra="ignore"
    )

    port: int = 8766
    host: str = "0.0.0.0"
    api_key: str = ""
    # 飞牛 CGI 反代形态鉴权（NASDECK_TRIM_AUTH=true）：读操作须有 index.cgi 转发的
    # X-Trim-Userid（登录用户），写操作（非 GET）还须 X-Trim-Isadmin=true（管理员）。
    # 详见 dependencies.require_trim_auth
    trim_auth: bool = False
    db_url: str = f"sqlite+aiosqlite:///{(APP_ROOT / 'data' / 'nasdeck.db').as_posix()}"
    raw_keep_minutes: int = 120
    storcli_path: str = ""
    # 空 = 跟随版本通道缺省（resolved_log_level）：dev 包 DEBUG 便于真机排查采集
    # 链路，正式包 INFO；FPK 形态由配置向导显式选择后写入 runtime.env
    log_level: str = ""
    app_version: str = "dev-0.0.25"
    # FPK 打包形态：指向前端 dist 目录时由本服务托管 SPA；开发形态留空不挂载
    static_dir: str = ""

    @property
    def resolved_log_level(self) -> str:
        """生效日志级别：显式配置（NASDECK_LOG_LEVEL / 向导）优先，未配置时 dev 前缀包 DEBUG。"""
        return (self.log_level or ("DEBUG" if self.app_version.startswith("dev") else "INFO")).upper()

    @property
    def storcli_cmd(self) -> str:
        """storcli 探测顺序：显式配置 → PATH → 项目 bin/ 目录（随包分发的 Linux ELF）。"""
        import shutil

        if self.storcli_path:
            return self.storcli_path
        found = shutil.which("storcli64") or shutil.which("storcli")
        if found:
            return found
        bundled = APP_ROOT / "bin" / "storcli64"
        if bundled.exists():
            return str(bundled)
        return "storcli64"


settings = Settings()
