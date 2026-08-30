"""
IssuePilot M2 的命令行启动文件

它本身不负责分析代码或修改文件，而是负责：

- 接收终端命令。
- 读取仓库路径、编程任务、最大执行轮数和模型名称。
- 创建 CodingTools。
- 创建 OpenAICompatibleModel。
- 创建 CodingAgent。
- 执行任务。
- 把最终结果打印到终端。

用户输入终端命令
        ↓
m2_cli.py 解析命令
        ↓
创建 CodingTools
        ↓
创建 OpenAICompatibleModel
        ↓
创建 CodingAgent
        ↓
调用 agent.run(task)
        ↓
模型调用工具查看和修改代码
        ↓
运行测试
        ↓
打印任务结果
"""
from __future__ import annotations

import argparse

from .m2_agent import CodingAgent
from .m2_model import OpenAICompatibleModel
from .m2_tools import CodingTools


def main() -> None:
    parser = argparse.ArgumentParser(description="IssuePilot M2 coding agent")
    parser.add_argument("repository") # 定义第一个位置参数 repository，表示要操作的代码仓库目录。
    parser.add_argument("task") # 定义第二个位置参数 task，表示交给编程智能体的任务。
    parser.add_argument("--max-steps", type=int, default=12) # 设置智能体最多允许进行多少轮模型决策
    parser.add_argument("--model") # 添加 --model 参数
    args = parser.parse_args()
    result = CodingAgent(
        CodingTools(args.repository), # 它会把当前目录设置成智能体可以操作的仓库根目录。工具只能在这个仓库范围内工作，以防止模型访问或修改仓库外的文件。
        OpenAICompatibleModel(args.model), # 创建模型
        args.max_steps,
    ).run(args.task)
    print(result.content) # 打印最终内容
    print(f"steps={result.steps}, completed={result.completed}") # 打印执行状态


if __name__ == "__main__":
    main()
