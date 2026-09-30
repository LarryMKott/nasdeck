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
    db_url: str = f"sqlite+aiosqlite:///{(APP_ROOT / 'data' / 'nasdeck.db').as_posix()}"
    raw_keep_minutes: int = 120
    storcli_path: str = ""
    log_level: str = "INFO"
    app_version: str = "dev-0.0.1"
    # FPK 打包形态：指向前端 dist 目录时由本服务托管 SPA；开发形态留空不挂载
    static_dir: str = ""

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
