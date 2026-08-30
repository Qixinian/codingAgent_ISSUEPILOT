"""
支持通过 python -m issuepilot 启动


python -m issuepilot
        ↓
Python寻找 issuepilot/__main__.py
        ↓
从 issuepilot/cli.py 导入 main
        ↓
执行 main()
        ↓
启动IssuePilot命令行程序
"""

from .cli import main

main()

