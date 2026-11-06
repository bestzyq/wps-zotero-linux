#!/bin/sh
# 确保 WPS ↔ Zotero 桥接代理在运行（监听 127.0.0.1:21931）
# 用法：直接执行本脚本即可，重复执行无副作用。
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1

PORT=21931
PY=""
for cand in /usr/bin/python3 /usr/local/bin/python3; do
    [ -x "$cand" ] && PY="$cand" && break
done
[ -z "$PY" ] && PY=$(command -v python3)
if [ -z "$PY" ]; then
    echo "未找到 python3，请先安装。" >&2
    exit 1
fi

if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":$PORT "; then
    echo "桥接代理已在运行（端口 $PORT）。"
    exit 0
fi

if command -v setsid >/dev/null 2>&1; then
    setsid -f "$PY" "$DIR/proxy.py" >/dev/null 2>&1
else
    nohup "$PY" "$DIR/proxy.py" >/dev/null 2>&1 &
fi

sleep 1
if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -q ":$PORT "; then
    echo "桥接代理已启动（端口 $PORT）。"
else
    echo "启动失败，请手动执行：$PY $DIR/proxy.py" >&2
    exit 1
fi
