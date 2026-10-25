# FPK 交付走 CGI 反代，不走飞牛统一网关

应用中心允许第三方应用在飞牛统一网关下挂载入口，但我们实测该入口会被飞牛周期性清空，表现为面板反复 404。因此 `com.dashboard.nasdeck` 改为随包携带 `ui/index.cgi`，由 CGI 脚本把请求转发到本机回环端口（默认 9800，安装向导可改），并据此在 manifest 中省略 `service_port`、设 `checkport=false`，端口占用改由安装回调预检。

**Considered Options**：统一网关挂载（被否，入口会被清空）；对外监听端口（被否，会把杀进程/控风扇接口暴露到局域网）。

**Consequences**：WebSocket 升级经 CGI 通道无法保证穿透，前端必须保留 HTTP 轮询降级；深链刷新依赖后端 SPA 回退把未知路径交还 `index.html`。
