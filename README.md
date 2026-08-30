# IssuePilot

IssuePilot M1 是一个只读仓库定位 Agent。它提供三个受仓库目录约束的工具：

- `list_files`
- `read_file`
- `search_code`

## 运行

需要 Python 3.11+。在项目目录执行：

```powershell
python -m issuepilot examples/fastapi_app "登录接口定义在哪里？"
```

预期结果包含 `app.py:6` 和对应的 `/login` 代码依据。

## 测试

```powershell
python -m pytest
```

当前 M1 使用确定性的术语选择器，因此无需 API Key。后续里程碑可在保留工具边界的前提下接入支持 Function Calling 的模型。
