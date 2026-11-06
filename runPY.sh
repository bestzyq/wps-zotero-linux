#!/bin/sh
# 兜底启动脚本：拉起本地的 Zotero 中转代理 proxy.py
# WPS for Linux 一般没有 VBA/JSIDE，正常由 js/zoteroHelper.js 通过
# wps.OAAssist.ShellExecute 直接调用 python3 proxy.py；此脚本作为备用入口。
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd) || exit 1
exec python3 "$DIR/proxy.py" "$@"
