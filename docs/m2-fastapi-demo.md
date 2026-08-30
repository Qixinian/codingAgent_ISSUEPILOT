# IssuePilot M2：FastAPI 邮箱校验案例

## 案例目标

给一个 FastAPI 项目的注册接口增加邮箱格式校验，并保证测试通过。

约束：

- 不新增第三方依赖
- 保持请求和响应字段不变
- 非法邮箱必须由请求模型拒绝并返回 HTTP 422
- 只做完成任务所需的最小修改

## 初始状态

注册请求模型将邮箱声明为普通字符串，因此任何字符串都能通过验证：

```python
class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str
初始测试结果：
1 passed, 2 failed
失败测试：
缺少 @ 的邮箱错误返回 201
缺少域名的邮箱错误返回 201
预期状态码均为 422
执行命令
python -m issuepilot.m2_ultra_cli examples\m2_fastapi_email "读取 TASK.md，给注册接口增加邮箱格式校验，不新增第三方依赖，并保证测试通过"
使用模型：
Spark Ultra-32K
模型通过原生 Function Calling 或兼容工具调用协议操作仓库。
Agent 执行轨迹
step 1: read_file
step 2: list_files
step 3: read_file
step 4: read_file
step 5: run_tests exit_code=1 timed_out=False
step 7: write_file path=app.py
step 8: run_tests exit_code=2 timed_out=False
step 9: write_file path=app.py
step 10: run_tests exit_code=0 timed_out=False
steps=11, completed=True
执行过程：
读取任务说明。
查看仓库文件。
读取注册接口和测试代码。
运行测试，复现邮箱校验失败。
修改 app.py。
第一次修改造成测试收集错误。
Agent 根据错误再次修改文件。
重新运行测试并全部通过。
输出修改说明和测试结果。
最终修改
Agent 在 Pydantic 请求模型中增加字段验证器：
import re

from fastapi import FastAPI, status
from pydantic import BaseModel, field_validator


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        email_regex = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_regex, value):
            raise ValueError("Invalid email format")
        return value
非法邮箱触发 Pydantic 验证错误，由 FastAPI 自动返回 HTTP 422。
最终测试结果
3 passed, 1 warning
通过的测试：
合法邮箱注册成功并返回 HTTP 201
缺少 @ 的邮箱返回 HTTP 422
缺少域名的邮箱返回 HTTP 422
警告来自 FastAPI TestClient 与当前 httpx 版本的弃用提示，不影响本案例功能。
成功标准
检查项	结果
Agent 自动读取任务和代码	通过
Agent 复现初始测试失败	通过
Agent 修改范围限制在目标仓库	通过
Agent 修改注册接口	通过
Agent 运行 pytest	通过
Agent 根据失败结果继续修复	通过
最终测试全部通过	通过
未新增第三方依赖	通过
非法邮箱返回 HTTP 422	通过

失败恢复分析
第一次失败：功能测试失败
第一次执行 pytest 时退出码为 1。原因是注册模型没有邮箱校验，非法邮箱仍然返回 HTTP 201。
Agent 根据测试输出定位到 RegisterRequest.email 字段。
第二次失败：测试收集错误
第一次写入代码后，pytest 退出码变为 2，说明修改后的代码存在语法、导入或测试收集问题。
Agent 没有直接结束任务，而是读取错误信息、再次修改 app.py 并重新运行测试。
最终恢复
第二次修改后 pytest 退出码变为 0，三个测试全部通过。这个过程证明 Agent 能根据工具反馈继续修复，而不是只进行一次代码生成。
安全限制
IssuePilot M2 对工具执行设置了以下限制：
文件读写限制在指定仓库目录内
禁止通过 ../ 访问仓库外文件
测试工具只允许执行固定的 pytest 命令
不允许模型执行任意 Shell 命令
测试执行具有超时限制
工具异常以结构化结果返回给模型
达到最大步骤数后强制停止
只有最近一次测试退出码为 0 才能标记任务完成
结论
该案例完成了 Coding Agent 的最小工程闭环：
理解任务
→ 读取代码
→ 运行测试
→ 复现失败
→ 修改文件
→ 处理修改错误
→ 再次运行测试
→ 测试通过
→ 输出执行报告
相比简单的加法函数案例，该案例更接近真实后端开发任务，能够展示 FastAPI、Pydantic、Function Calling、Agent 循环、权限控制、测试驱动修复和错误恢复能力。

注意：文档中的最终代码使用了 `@classmethod` 和类型标注，比 Agent 当时生成的代码稍规范。如果你希望文档严格复现当时的实际输出，可以删除 `@classmethod`，并将方法签名改为：

```python
def validate_email(cls, value):
不过更建议保留上面的规范版本，并注明它是整理后的最终实现。