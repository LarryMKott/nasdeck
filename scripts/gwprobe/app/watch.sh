#!/bin/bash
# Gateway Probe 网关入口存活采样 v3——由 root crontab 每 10 分钟调用
# （cron 行由 install/upgrade_callback 注册：bash /var/apps/com.test.gatewayprobe/target/watch.sh）
#
# v3 无路径占位符、不自烘焙：真机安装流回调在 /vol2/appcenter-downloads/...-tpk 暂存目录
# 执行且无 TRIM_APPDEST 注入（升级后暂存即清，v2 烘焙进 cron 的暂存路径随之失效）。
# 故此处全部运行时自定位：应用本体走 /var/apps 稳定前门，@appdata 卷位置 glob 探测。
#
# 判据设计（实测：未登录 curl 无论入口存否都返回 200 "invalid token"——网关鉴权
# 在路由解析之前，HTTP 层无判别力；故主判据走存储层）：
#   ALIVE          符号链接在 + gatewaySocket 字段在 + socket 在（服务健康全链路）
#   ENTRY_CLEARED  /var/apps_ui 链接丢失或 config 里 gatewaySocket 字段被清（2026-08 缺陷复现）
#   SOCK_DEAD      入口注册在但探针服务 socket 没了（服务死，与入口无关）
#   SVC_DOWN       trim_http_cgi 网关服务本体不活跃（系统级，非应用问题）
#   HTTP 列为旁证：200=网关应答（未登录态固定 invalid token）；连接失败=网关层异常
TS="$(date '+%Y-%m-%d %H:%M:%S')"

APP_REAL="$(readlink -f /var/apps/com.test.gatewayprobe 2>/dev/null)"
APP_DIR="${APP_REAL}/target"
VAR_DIR="$(ls -d /vol*/@appdata/com.test.gatewayprobe 2>/dev/null | head -n 1)"
[ -z "$VAR_DIR" ] && VAR_DIR="/tmp/gwprobe-var"
mkdir -p "$VAR_DIR" 2>/dev/null

SVC="$(systemctl is-active trim_http_cgi 2>/dev/null)"
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 10 'http://127.0.0.1:5666/app/com.test.gatewayprobe/' 2>/dev/null)"

UI_LINK="/var/apps_ui/com.test.gatewayprobe"
LINK="-"
if [ -L "$UI_LINK" ]; then
    if [ -d "$UI_LINK" ]; then LINK="link-ok"; else LINK="link-BROKEN"; fi
else
    LINK="link-MISSING"
fi

SOCK_STATE="sock-MISSING"
[ -S "${APP_DIR}/gwprobe.sock" ] && SOCK_STATE="sock-present"

FIELD="-"
if [ -r "$UI_LINK/config" ] && grep -q 'gatewaySocket' "$UI_LINK/config" 2>/dev/null; then
    FIELD="field-ok"
else
    FIELD="field-CLEARED"
fi

if [ "$SVC" != "active" ]; then
    VERDICT="SVC_DOWN"
elif [ "$LINK" != "link-ok" ] || [ "$FIELD" != "field-ok" ]; then
    VERDICT="ENTRY_CLEARED"
elif [ "$SOCK_STATE" != "sock-present" ]; then
    VERDICT="SOCK_DEAD"
else
    VERDICT="ALIVE"
fi

echo "${TS} verdict=${VERDICT} svc=${SVC} ${LINK} ${FIELD} ${SOCK_STATE} http=${HTTP_CODE}" >> "${VAR_DIR}/watch.log"
