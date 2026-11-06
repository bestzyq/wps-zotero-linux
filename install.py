#!/usr/bin/env python3
"""WPS-Zotero 加载项安装器（Linux / 麒麟 适配版）

基于 DreamZouz/Zotero-WPSJS-Mac（其上游为 bigben446/Zotero-WPSJS，
再上游 tankwyn/WPS-Zotero），针对 WPS for Linux 做了适配：

  * 加载项目录固定为 wps-zotero_1.0.0，与 js/util.js 的 getAddonPath 保持一致
  * 注册 jsplugins.xml（离线 jsplugin 模式），无需本地 HTTP 服务器
  * 同时兼容 publish.xml 在线模式所需字段
  * 生成可执行的 runPY.sh 作为代理启动兜底

用法：
    python3 install.py        # 安装 / 覆盖安装
    python3 install.py -u     # 卸载
"""

import getpass
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from proxy import stop_proxy

APPNAME = 'wps-zotero_1.0.0'
VERSION = '1.0.0'
ADDON_NAME = 'wps-zotero'

PKG_PATH = os.path.dirname(os.path.abspath(__file__))
# 可用 WPS_ZOTERO_HOME 显式指定目标用户的家目录（例如以 sudo/root 安装时）
HOME = os.environ.get('WPS_ZOTERO_HOME') or os.path.expanduser('~')

if platform.system() == 'Darwin':
    ADDON_PATH = os.path.join(
        HOME, 'Library/Containers/com.kingsoft.wpsoffice.mac/Data/.kingsoft/wps/jsaddons')
elif platform.system() == 'Windows':
    ADDON_PATH = os.path.join(os.environ['APPDATA'], 'kingsoft', 'wps', 'jsaddons')
else:
    ADDON_PATH = os.path.join(HOME, '.local/share/Kingsoft/wps/jsaddons')

INSTALL_DIR = os.path.join(ADDON_PATH, APPNAME)

XML_PATHS = {
    'jsplugins': os.path.join(ADDON_PATH, 'jsplugins.xml'),
    'publish': os.path.join(ADDON_PATH, 'publish.xml'),
    'authwebsite': os.path.join(ADDON_PATH, 'authwebsite.xml'),
}

# 离线 jsplugin 模式：url 指向 jsaddons 下的加载项目录
JSPLUGIN_RECORD = (
    '<jsplugin name="{name}" type="wps" url="./{dir}" version="{ver}" '
    'enable="enable" install="null"/>'
).format(name=ADDON_NAME, dir=APPNAME, ver=VERSION)

PUBLISH_RECORD = (
    '<jsplugin url="./{dir}" type="wps" enable="enable" install="null" '
    'version="{ver}" name="{name}"/>'
).format(name=ADDON_NAME, dir=APPNAME, ver=VERSION)

AUTHWEBSITE_RECORD = (
    '<website origin="null" name="{name}" status="enable"/>'.format(name=ADDON_NAME)
)

RECORD_PATTERN = re.compile(r'[ \t]*<[^>]*wps-zotero[^>]*/>\s*')


def ensure_xml(path, root, header=True):
    """确保配置文件存在且结构完整。"""
    if os.path.isfile(path):
        with open(path, encoding='utf-8') as f:
            content = f.read()
        if '<%s' % root in content:
            return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    prefix = '<?xml version="1.0" encoding="UTF-8"?>\n' if header else ''
    with open(path, 'w', encoding='utf-8') as f:
        f.write('{prefix}<{root}>\n</{root}>\n'.format(prefix=prefix, root=root))


def strip_records(path):
    """移除本加载项的历史注册记录。"""
    if not os.path.isfile(path):
        return
    with open(path, encoding='utf-8') as f:
        content = f.read()
    new = RECORD_PATTERN.sub('', content)
    if new != content:
        print('清理旧记录：{}'.format(path))
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new)


def add_record(path, root, record):
    """把注册记录插入到根节点的第一个子节点之前。"""
    with open(path, encoding='utf-8') as f:
        content = f.read()
    close_tag = '</%s>' % root
    idx = content.rfind(close_tag)
    if idx == -1:
        content += '\n%s\n' % record
    else:
        content = content[:idx] + record + '\n' + content[idx:]
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def uninstall():
    print('尝试停止已运行的代理进程 ...')
    try:
        stop_proxy()
    except Exception as error:  # 代理未运行时忽略
        print('停止代理时出现提示（可忽略）：{}'.format(error))

    if os.path.isdir(INSTALL_DIR):
        print('删除加载项目录：{}'.format(INSTALL_DIR))
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)

    for name in ('jsplugins', 'publish', 'authwebsite'):
        strip_records(XML_PATHS[name])

    remove_autostart()


def copy_payload():
    if os.path.isdir(INSTALL_DIR):
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    shutil.copytree(
        PKG_PATH, INSTALL_DIR,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.git', '.gitignore'),
    )
    os.chmod(os.path.join(INSTALL_DIR, 'runPY.sh'), 0o755)
    os.chmod(os.path.join(INSTALL_DIR, 'start-proxy.sh'), 0o755)
    os.chmod(os.path.join(INSTALL_DIR, 'proxy.py'), 0o755)
    print('已复制加载项到：{}'.format(INSTALL_DIR))


def python3_path():
    for candidate in ('/usr/bin/python3', '/usr/local/bin/python3'):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which('python3') or 'python3'


AUTOSTART_DIR = os.path.join(HOME, '.config/autostart')
AUTOSTART_FILE = os.path.join(AUTOSTART_DIR, 'zotero-wps-proxy.desktop')


def install_autostart():
    """让代理在登录桌面后自动常驻（走 start-proxy.sh，幂等且自寻 python3）。"""
    if platform.system() == 'Windows':
        return
    launcher = os.path.join(INSTALL_DIR, 'start-proxy.sh')
    content = """[Desktop Entry]
Type=Application
Name=Zotero-WPS 桥接服务
Comment=WPS 文字与 Zotero 之间的本地中转（127.0.0.1:21931）
Exec={launcher}
Terminal=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
""".format(launcher=launcher)
    os.makedirs(AUTOSTART_DIR, exist_ok=True)
    with open(AUTOSTART_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    os.chmod(AUTOSTART_FILE, 0o755)
    print('已注册登录自启：{}'.format(AUTOSTART_FILE))


def remove_autostart():
    if os.path.isfile(AUTOSTART_FILE):
        os.remove(AUTOSTART_FILE)
        print('已移除登录自启配置')


def start_proxy_now():
    """立即后台拉起代理（脱离当前会话）。"""
    payload = os.path.join(INSTALL_DIR, 'proxy.py')
    try:
        subprocess.Popen(
            [python3_path(), payload],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, start_new_session=True,
        )
        print('已启动代理进程（127.0.0.1:21931）')
        time.sleep(1.0)
    except Exception as error:
        print('代理启动失败，可手动执行：{} {}'.format(python3_path(), payload))
        print(error)


def main():
    if platform.system() == 'Linux' and os.geteuid() == 0:
        print('提示：当前以 root 身份运行，加载项将安装到 {} 下。'.format(ADDON_PATH))
        print('      如果平时以普通用户使用 WPS，请改用该用户重新执行本脚本。\n')

    print('=== 卸载已有安装（若有）===')
    uninstall()

    if len(sys.argv) > 1 and sys.argv[1] in ('-u', '--uninstall'):
        print('卸载完成。')
        return 0

    print('\n=== 安装 ===')
    os.makedirs(ADDON_PATH, exist_ok=True)

    ensure_xml(XML_PATHS['jsplugins'], 'jsplugins', header=False)
    ensure_xml(XML_PATHS['publish'], 'jsplugins', header=True)
    ensure_xml(XML_PATHS['authwebsite'], 'websites', header=True)

    copy_payload()

    add_record(XML_PATHS['jsplugins'], 'jsplugins', JSPLUGIN_RECORD)
    add_record(XML_PATHS['publish'], 'jsplugins', PUBLISH_RECORD)
    add_record(XML_PATHS['authwebsite'], 'websites', AUTHWEBSITE_RECORD)
    print('已写入注册配置：jsplugins.xml / publish.xml / authwebsite.xml')

    install_autostart()
    start_proxy_now()

    print('\n安装完成。')
    print('后续检查：')
    print('  1. 完全退出 WPS 后重新打开（否则旧进程不会加载新加载项）')
    print('  2. WPS 文字 → 功能区末尾应出现「Zotero」选项卡')
    print('  3. Zotero 中确认勾选：设置 → 高级 → 允许此计算机上的其他程序与 Zotero 通信')
    print('  4. 代理日志：{}'.format(os.path.join(INSTALL_DIR, 'proxy-diagnostic.log')))
    print('\n卸载：python3 install.py -u')
    return 0


if __name__ == '__main__':
    sys.exit(main())
