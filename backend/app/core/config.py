"""全局配置：Pydantic Settings，环境变量 NASDECK_ 前缀。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parents[2]


def _version_from_pyproject() -> str:
    """读取应用版本（pyproject.toml 为唯一来源）。

    与 fpk/manifest 经 build_fpk 校验一致；读取失败（如部署形态未携带）回退
    0.0.0：仅影响日志级别通道（dev 前缀 DEBUG），不影响功能。

    Returns:
        str: 语义化版本号；异常时 "0.0.0"。
    """
    try:
        import tomllib

        with open(APP_ROOT / "pyproject.toml", "rb") as f:
            return str(tomllib.load(f)["project"]["version"])
    except Exception:  # noqa: BLE001 文件缺失/损坏按未知版本处理
        return "0.0.0"


class Settings(BaseSettings):
    """全局配置（NASDECK_ 前缀环境变量 + 可选 .env）。

    各字段安全/形态语义见其行内注释（为准）；以下是速览：

    Attributes:
        port (int): 监听端口。
        host (str): 监听地址（缺省仅回环）。
        api_key (str): 直连形态 API Key（空 = 不校验）。
        trim_auth (bool): 飞牛 CGI 反代形态分级鉴权开关。
        proxy_token (str): index.cgi→后端代理信任密钥（空 = 不校验）。
        db_url (str): 数据库连接串（SQLite + WAL）。
        raw_keep_minutes (int): raw 历史点保留分钟数。
        storcli_path (str): storcli 显式路径（空 = 自动探测）。
        log_level (str): 显式日志级别（空 = 按版本通道缺省）。
        app_version (str): 应用版本（pyproject 唯一来源）。
        static_dir (str): FPK 形态前端 dist 目录（空 = 不托管 SPA）。
    """

    model_config = SettingsConfigDict(
        env_prefix="NASDECK_", env_file=APP_ROOT / ".env", extra="ignore"
    )

    port: int = 8766
    # 缺省仅回环：无鉴权形态（api_key 空 + trim_auth 关）绑全网卡会把杀进程/
    # 控风扇的面板暴露到局域网；需要对外时显式设 NASDECK_HOST=0.0.0.0
    host: str = "127.0.0.1"
    api_key: str = ""
    # 飞牛 CGI 反代形态鉴权（NASDECK_TRIM_AUTH=true）：读操作须有 index.cgi 转发的
    # X-Trim-Userid（登录用户），写操作（非 GET）还须 X-Trim-Isadmin=true（管理员）。
    # 详见 dependencies.require_trim_auth
    trim_auth: bool = False
    # 代理共享密钥（NASDECK_PROXY_TOKEN）：index.cgi→后端本机转发凭据。飞牛网关
    # 是否剥离客户端自带 X-Trim-* 头无法在网关侧确认，该密钥保证身份头只能由
    # 持密的 index.cgi 注入（密钥不经过网关，客户端伪造头失效）；空 = 不校验
    # （开发/自托管直连形态）。FPK 由 install_callback 生成落 var/，cmd/main 注入
    proxy_token: str = ""
    db_url: str = f"sqlite+aiosqlite:///{(APP_ROOT / 'data' / 'nasdeck.db').as_posix()}"
    raw_keep_minutes: int = 120
    storcli_path: str = ""
    # 空 = 跟随版本通道缺省（resolved_log_level）：dev 包 DEBUG 便于真机排查采集
    # 链路，正式包 INFO；FPK 形态由配置向导显式选择后写入 runtime.env
    log_level: str = ""
    app_version: str = _version_from_pyproject()
    # FPK 打包形态：指向前端 dist 目录时由本服务托管 SPA；开发形态留空不挂载
    static_dir: str = ""
    # 统一网关形态（NASDECK_UDS）：非空时 uvicorn 监听该 Unix Socket（由飞牛
    # trim_http_cgi 按 ui/config 的 gatewaySocket 声明转发），TCP host/port 不生效。
    # cmd/main 按安装/配置向导的访问模型（var/access_mode）分支导出
    uds: str = ""
    # 网关形态转发前缀（NASDECK_GATEWAY_PREFIX，如 /app/com.dashboard.nasdeck）：
    # 官方文档示例网关不剥前缀转发（应用收到全路径）；非空时挂前缀剥离中间件，
    # 若实测网关已剥前缀（路径不以该前缀开头），中间件原样透传，两种行为均正确
    gateway_prefix: str = ""
    # 前端资源基址（NASDECK_PUBLIC_PATH）：FPK 构建的 index.html 以 /__ND_PREFIX__
    # 为占位符，statics 挂载时按本值一次性替换——CGI 形态 = 完整 cgi 反代前缀，
    # 网关形态 = gateway_prefix，cmd/main 按访问模型导出；空 = 产物即最终形态（开发）
    public_path: str = ""

    @property
    def resolved_log_level(self) -> str:
        """生效日志级别。

        显式配置（NASDECK_LOG_LEVEL / 配置向导）优先；未配置时 dev 前缀包 DEBUG
        （便于真机排查采集链路），正式包 INFO。

        Returns:
            str: 大写级别名（DEBUG/INFO/...）。
        """
        return (self.log_level or ("DEBUG" if self.app_version.startswith("dev") else "INFO")).upper()

    @property
    def storcli_cmd(self) -> str:
        """storcli 可执行解析（探测顺序：显式配置 → PATH → 项目 bin/）。

        Returns:
            str: 可执行路径或兜底名 "storcli64"（缺失时由调用方以 1003 呈现）。
        """
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
