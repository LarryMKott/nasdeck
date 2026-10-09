#!/bin/bash
# CGI 反代入口（fnpackup 同款，真机验证）：飞牛已校验登录态后把请求交给本脚本，
# 本脚本把请求原样转发到本机回环端口（cmd/main 启动的 uvicorn，默认 9800）。
# HTTP_X_TRIM_* 为飞牛注入的可信身份头，转成 header 传给后端供鉴权使用。
# 不走统一网关：飞牛会周期性清空第三方 gateway 入口（实测反复 404），cgi 反代稳定。

cgi_name="index.cgi"

# 转发端口与 cmd/main 同源（安装向导 wizard_port 落盘）：优先读本脚本同目录的
# ui/port 镜像（CGI 由飞牛从应用目录拉起，读自身目录最可靠），回退 @appdata
# 权威副本，最后默认 9800。非法值一律回退，保证代理永不失联。
port_file="$(dirname "$0")/port"
[ -r "$port_file" ] || port_file="/var/apps/com.dashboard.nasdeck/var/port"
nasdeck_port="$(head -n 1 "$port_file" 2>/dev/null | tr -d '[:space:]')"
case "$nasdeck_port" in
    ''|*[!0-9]*) nasdeck_port=9800 ;;
esac
target_url="http://127.0.0.1:${nasdeck_port}"

if [[ "$REQUEST_URI" == *"$cgi_name"* ]]; then
    after_proxy="${REQUEST_URI#*$cgi_name}"

    if [[ "$after_proxy" == *"?"* ]]; then
        target_path=$(echo "$after_proxy" | cut -d'?' -f1)
        target_query=$(echo "$after_proxy" | cut -d'?' -f2-)
    else
        target_path="$after_proxy"
        target_query=""
    fi
else
    after_proxy=""
    target_path=""
    target_query="$QUERY_STRING"
fi

if [ -z "$target_path" ]; then
    target_path="/"
fi

target_url="$target_url$target_path"
if [ -n "$target_query" ]; then
    target_url="$target_url?$target_query"
fi

# 访问模型分派：gateway 形态经 app.sock（--unix-socket）转发——桌面入口的 URL
# 注册可能滞后于形态切换（fnOS 不一定热更新 ui/config），入口双形态可达保证旧
# 图标 URL 永不失效；socket 不在（服务未起/形态文件缺失）自动回退 TCP 路径。
gw_sock=""
access_mode="$(cat /var/apps/com.dashboard.nasdeck/var/access_mode 2>/dev/null)"
if [ "$access_mode" = "gateway" ]; then
    gw_sock="/var/apps/com.dashboard.nasdeck/target/app.sock"
fi
if [ -n "$gw_sock" ] && [ -S "$gw_sock" ]; then
    target_url="http://localhost$target_path"
    if [ -n "$target_query" ]; then
        target_url="$target_url?$target_query"
    fi
fi

curl_args=(-s --include -X "$REQUEST_METHOD")
if [ -n "$gw_sock" ] && [ -S "$gw_sock" ]; then
    curl_args+=(--unix-socket "$gw_sock")
fi
# 代理共享密钥（install_callback 生成，镜像到本目录）：后端凭它确认身份头只能由
# 本脚本注入——网关是否剥离客户端自带 X-Trim-* 头无法保证，密钥不经过网关
proxy_token_file="$(dirname "$0")/proxy_token"
[ -r "$proxy_token_file" ] || proxy_token_file="/var/apps/com.dashboard.nasdeck/var/proxy_token"
nasdeck_proxy_token="$(head -n 1 "$proxy_token_file" 2>/dev/null | tr -d '[:space:]')"
if [ -n "$nasdeck_proxy_token" ]; then
    curl_args+=(-H "X-Nasdeck-Proxy: $nasdeck_proxy_token")
fi
# 注入飞牛用户身份（飞牛已校验登录态，HTTP_X_TRIM_* 为可信身份，转成 header 供后端鉴权）
if [ -n "$HTTP_X_TRIM_USERID" ]; then
    curl_args+=(-H "X-Trim-Userid: $HTTP_X_TRIM_USERID")
    curl_args+=(-H "X-Trim-Username: ${HTTP_X_TRIM_USERNAME:-}")
    curl_args+=(-H "X-Trim-Isadmin: ${HTTP_X_TRIM_ISADMIN:-false}")
fi
if [ -n "$HTTP_COOKIE" ]; then
    curl_args+=(-H "Cookie: $HTTP_COOKIE")
fi
if [ -n "$CONTENT_TYPE" ]; then
    curl_args+=(-H "Content-Type: $CONTENT_TYPE")
fi
curl_args+=("$target_url")

# 带请求体的方法统一把 stdin 转给 curl：只认 POST 会让 PUT/PATCH（风扇曲线、
# 系统设置、告警规则等）收到空 body 而后端 422（审查 2026-09-30 P1）
case "$REQUEST_METHOD" in
    POST|PUT|PATCH|DELETE)
        exec cat | curl "${curl_args[@]}" --data-binary @- --include | sed -e '/^HTTP\/1.1 100/,/^\r\?$/d'
        ;;
    *)
        exec curl "${curl_args[@]}" --include | sed -e '/^HTTP\/1.1 100/,/^\r\?$/d'
        ;;
esac
