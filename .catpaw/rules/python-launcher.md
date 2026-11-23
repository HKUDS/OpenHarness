---
ruleType: Manual
description: 本地环境优先使用 py 命令运行 Python 脚本
globs: 
---
rule编写规则: https://catpaw.meituan.com/guides/settings/rules

# 本地 Python 命令约定

在 Windows 本地环境中，优先使用 `py` 而非 `python` 来运行 Python 脚本。

## 原因

- **`py`** 是 Windows 上的 Python Launcher（`py.exe`），安装时写入 `C:\Windows\`，始终在 PATH 中。
- **`python`** 的可执行目录可能未加入 PATH（安装时未勾选 "Add Python to PATH"），导致命令不可用。
- `py` 支持多版本选择（如 `py -3.11`、`py -3.12`），更灵活可靠。

## 执行规则

- 运行 Python 脚本时使用 `py script.py` 而非 `python script.py`
- 安装包时使用 `py -m pip install <package>` 而非 `python -m pip install <package>`
- 指定版本时使用 `py -3.x` 格式
- 运行模块时使用 `py -m <module>` 格式
