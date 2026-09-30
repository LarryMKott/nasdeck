#!/bin/bash
# CGI 反代入口（fnpackup 同款，真机验证）：飞牛已校验登录态后把请求交给本脚本，
# 本脚本把请求原样转发到本机 127.0.0.1:9800（cmd/main 启动的 uvicorn）。
# HTTP_X_TRIM_* 为飞牛注入的可信身份头，转成 header 传给后端供鉴权使用。
# 不走统一网关：飞牛会周期性清空第三方 gateway 入口（实测反复 404），cgi 反代稳定。

cgi_name="index.cgi"
target_url="http://127.0.0.1:9800";

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

curl_args=(-s --include -X "$REQUEST_METHOD")
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

if [ "$REQUEST_METHOD" = "POST" ]; then
    exec cat | curl "${curl_args[@]}" --data-binary @- --include | sed -e '/^HTTP\/1.1 100/,/^\r\?$/d'
else
    exec curl "${curl_args[@]}" --include | sed -e '/^HTTP\/1.1 100/,/^\r\?$/d'
fi
