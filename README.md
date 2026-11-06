# WPS-Zotero（Linux / 麒麟 适配版）

让 WPS 文字和 Zotero 10 联动：在 WPS 里插入、编辑、刷新引用和参考文献，文档仍可交给 Windows 上的
MS Word 继续编辑。

## 来源

| 环节 | 项目 |
| --- | --- |
| 原始实现 | [tankwyn/WPS-Zotero](https://github.com/tankwyn/WPS-Zotero)（WPS jsapi + 本地 HTTP 代理） |
| 功能扩展 | [bigben446/Zotero-WPSJS](https://github.com/bigben446/Zotero-WPSJS) |
| 上游参考 | [DreamZouz/Zotero-WPSJS-Mac](https://github.com/DreamZouz/Zotero-WPSJS-Mac)（Zotero 10 通信修复） |

本目录基于 **Zotero-WPSJS-Mac**，把它的 macOS 适配部分改回 Linux 行为。

## 为什么原项目在本机用不了

1. **Zotero 10 会拒绝老客户端的请求**
   Zotero 9 之后收紧了 `/connector/*` 的检查，缺少 `X-Zotero-Connector-API-Version` 头的请求会被直接关掉。
   tankwyn 版的代理没有这个头，于是表现为「点了没反应 / Network error」。
   → 本版沿用 DreamZouz 的修复：代理转发时补 `X-Zotero-Connector-API-Version: 3`。

2. **旧版同步 XHR 会卡住 WPS**
   Zotero 引用对话框打开期间是一次长事务，同步 XHR 会把 WPS 的 JS/UI 事件循环堵死。
   → 本版使用异步 XHR，并对功能区按钮加了重复点击保护。

3. **macOS 的启动方式在 Linux 不成立**
   Mac 版靠 `open -n proxy.app` 起代理，Linux 没有 `open`；WPS for Linux 也没有 macOS 的容器路径。

4. **WPS for Linux 没有 VBA/JSIDE**
   Mac/Windows 版用 `Application.JSIDE` + `Shell()` 宏来拉起 `proxy.exe`，Linux 版没有这套东西，
   所以 `OAAssist.ShellExecute` 在本机实测也拉不起进程（不同 WPS 版本行为不一致）。

## 本版做了哪些改动

| 文件 | 改动 |
| --- | --- |
| `js/zclient.js` | 异步 XHR 事务；Zotero 10 请求头；502/网络错误改为中文可执行提示；`arguments` 缺失与未知命令的防御；出错时记录具体命令名 |
| `js/ribbon.js` | 只在 Windows 才检查 JSIDE 授权；Linux 退出时不关闭代理（改为常驻） |
| `js/zoteroHelper.js` | Linux 分支改用 `OAAssist.ShellExecute` 多写法尝试 + `runPY.sh` 兜底 |
| `js/wpsif.js` | **修掉 `activate()` 里的 macOS 专属代码**（见下）；`getDocData` / `setDocData` 对空值加防御 |
| `js/about.js` | 卸载按钮补 Linux 分支（macOS/Windows 的卸载器在 Linux 不存在） |
| `js/zoteroSet.js` | 路径校验补 Linux 分支（原来会直接抛「不支持的操作系统」） |
| `js/util.js` | 未改动（其 `getAddonPath` 已含 Linux 路径） |
| `proxy.py` | 标准库 HTTP 中转，监听 `127.0.0.1:21931` → 转发到 Zotero 的 `127.0.0.1:23119` |
| `runPY.sh` | 代理启动兜底脚本 |
| `start-proxy.sh` | 一键确保代理在运行（幂等，可反复执行） |
| `install.py` | 重写：Linux 加载项目录、离线 `jsplugins.xml` 注册、登录自启、一键启动 |

### 为什么必须改 `activate()`

上游把 macOS 的「把 WPS 提到前台」逻辑写在了通用的 `activate()` 里：

```js
const appPath = Application.Path;                    // Linux 上为 undefined
const appIndex = appPath.indexOf(".app") + ...       // → TypeError
runServers('openWPS', 'open -a ' + appPathValue);    // open -a 在 Linux 也不存在
```

每次插入引用，事务最后都会走到 `Document.activate`。这一步抛 `TypeError` 后事务中断，
Zotero 那边的集成会话不会被释放，于是之后所有请求都返回 503
`Integration transaction is already in progress`，并且只能重启 Zotero 才能恢复。
这就是「一直报错 TypeError / serving another program」的根因。
本版在 `activate()` 里先判断 `Application.Path` 是否真的包含 `.app`，不是就直接返回。

加载项目录固定为 `wps-zotero_1.0.0`，必须和 `js/util.js` 里 `getAddonPath()` 写死的目录名保持一致。

## 安装

```bash
python3 install.py            # 安装 / 覆盖安装
python3 install.py -u         # 卸载
```

以普通用户身份运行即可。如果用 sudo/root 安装，需要显式指定目标用户家目录：

```bash
sudo WPS_ZOTERO_HOME=/home/<用户> python3 install.py
```

安装会做四件事：

1. 复制加载项到 `~/.local/share/Kingsoft/wps/jsaddons/wps-zotero_1.0.0/`
2. 在 `jsplugins.xml` / `publish.xml` / `authwebsite.xml` 写入注册记录
3. 写 `~/.config/autostart/zotero-wps-proxy.desktop`，登录桌面后自动拉起代理
4. 立即启动一次代理

装完需要**完全退出 WPS 再打开**，功能区末尾才会出现「Zotero」选项卡。

## 使用

1. Zotero → 设置 → 高级 → 勾选「允许此计算机上的其他程序与 Zotero 通信」
   （本机 `extensions.zotero.httpServer.localAPI.enabled` 已为 `true`）
2. 重启 WPS，功能区 → Zotero → Add/Edit Citation
3. 首次会弹出「Zotero 文档选项」，选择参考文献样式（如 GB/T 7714—2015）和语言

## 排错

代理是否在跑：

```bash
~/.local/share/Kingsoft/wps/jsaddons/wps-zotero_1.0.0/start-proxy.sh
ss -tlnp | grep 21931
```

代理 ↔ Zotero 是否通：

```bash
curl --noproxy '*' -X POST http://127.0.0.1:21931/connector/ping
```

返回 Zotero 的 prefs JSON 即为正常。日志在：

```
~/.local/share/Kingsoft/wps/jsaddons/wps-zotero_1.0.0/proxy-diagnostic.log
```

日志只记录操作名、耗时和字节数，不记录文档或引用内容。

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 功能区没有 Zotero 选项卡 | WPS 未重启 / 注册记录没读到 | 完全退出 WPS 重开；检查 `jsplugins.xml` |
| 提示「连不上本地桥接服务」 | 21931 没进程 | 执行 `start-proxy.sh`，或重新登录桌面 |
| 提示「桥接服务连不上 Zotero」 | 23119 没监听 | 启动 Zotero，确认已允许本机程序通信 |
| 提示「Zotero is serving another program」(503) | Zotero 里有个没走完的集成事务 | 退出 Zotero 再打开；本版已修掉最常见的触发点 |
| 提示「文字处理器集成命令已在运行」 | 同上，Zotero 自己弹的模态框 | 先点掉弹窗，再重启 Zotero |
| 引用插入后样式不对 | 文档样式未设置 | 点 Document Preferences 重选样式 |

> 503 的原理：Zotero 的 `/connector/document/*` 同时只允许一个集成事务。事务中途出异常
> （例如插件 JS 抛错、或你在中途取消了对话框），Zotero 不会自动释放，后续请求全部 503。
> 插件修好之后正常不会再触发，但 Zotero 侧一旦卡住只能重启 Zotero。
