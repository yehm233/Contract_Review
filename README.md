# Contract-Review-Pro V1.4（LangGraph Agent + MCP）

面向 WSL2 + OnlyOffice + MinIO + MySQL 的智能合同生成与审查系统。

## 1. 架构概览

```text
Browser(前端页面/插件)
   -> OnlyOffice Document Server (172.27.3.6:9002)
   -> FastAPI Gateway (172.27.3.6:8080)
      -> LangChain Review App
         -> MCP Server (127.0.0.1:8000/sse)
            -> extract_contract_entities
            -> risk_assessment_scan
            -> generate_revision_clause
      -> MySQL (172.27.3.6:3306)
      -> MinIO OSS (172.27.3.6:9000)
```

- **MCP Server**：只负责暴露合同审查与生成 Tools。
- **LangChain / LangGraph Agent**：AI 应用层，负责连接模型、发现 MCP tools、发起 `tool_calls`、接收 `ToolMessage` 回填、汇总审查结论。
- **FastAPI Gateway**：OnlyOffice callback、MinIO落盘、数据库任务状态、触发 LangChain 审查工作流。
- **OnlyOffice Plugin**：右侧边栏展示风险并支持一键采纳。

> 说明：当前版本 `JWT_ENABLED=false`，前后端不包含 JWT 签名校验逻辑。

## 2. 项目结构

```text
backend/
  app/
    api/routes.py
    core/config.py
    db/{database.py,models.py}
    schemas/review.py
    services/{langchain_review.py,review.py,storage.py}
  main.py
mcp_server/
  app/server.py
  main.py
frontend/plugin/
  config.json
  index.html
  app.js
```

## 3. MCP Skills（由 AI 应用层调用）

- `extract_contract_entities(text)`：抽取甲乙方、金额、管辖等实体。
- `risk_assessment_scan(text)`：风险点扫描，返回风险等级与法律依据。
- `generate_revision_clause(risk_type)`：生成风险替换条款。
- `draft_contract_from_template(form_data)`：表单生成合同初稿。
- `format_to_legal_standard(text)`：商业表述法律化润色。

## 4. 调用模式

### 推荐模式：LangGraph Agent + MCP

业务接口不再直接请求 `POST /tools/...`。当前推荐链路是一个真正的 Agent 回路：

1. `POST /api/review/start`
2. FastAPI 从数据库取合同信息，并拿到 `contract_text` 或文档摘要
3. `LangChainReviewWorkflow` 通过 `langchain-mcp-adapters` 连接 `MCP Server`
4. `create_agent(...)` 将 MCP tools 注册进 LangGraph agent
5. 模型先输出 `tool_calls`
6. Agent Runtime 执行对应 MCP tool，并将结果包装为 `ToolMessage`
7. `ToolMessage` 回填给模型，继续下一轮决策
8. 循环直到模型停止调用工具，并返回结构化审查结论
9. 结果写入 `review_tasks`

这意味着：

- `MCP Server` 只是一组工具，不承担业务编排职责
- `AI Agent` 才是合同审查流程的入口
- `tool_call -> ToolMessage -> 再推理` 的闭环由 LangGraph Agent Runtime 负责
- 后续接入更多 Agent / RAG / 审批逻辑时，不需要改 MCP Tool 本身

### 兼容模式：Direct MCP

保留了 `REVIEW_WORKFLOW_MODE=compat_direct`，并兼容旧值 `compat_http`。  
该模式下不会经过 LLM 决策，而是由后端直接通过 MCP tool 做一次顺序化审查，用于降级或联调。

## 5. FastAPI 核心接口

- `POST /api/onlyoffice/callback`
  - `status==2` 时下载 OnlyOffice 临时文件并上传到 MinIO。
  - 固定返回 `{"error":0}`。
- `POST /api/review/start`
  - 输入：`{"contract_id":"...","contract_text":"..."}`。
  - `contract_text` 可选，便于前端或解析服务直接传入正文内容。
  - 更新合同状态 -> 调用 LangGraph Agent / Direct MCP Workflow -> 写入 `review_tasks` -> 返回结构化结果。
  - 返回中包含 `workflow` 和 `messages`，便于观察 tool call 轨迹。

## 6. 数据模型

- `contracts(contract_id,file_name,minio_url,status,created_at)`
- `review_tasks(task_id,contract_id,risk_score,findings_json,created_at)`

## 7. 配置项

- `REVIEW_WORKFLOW_MODE=langchain`
- `MCP_SSE_URL=http://127.0.0.1:8000/sse`
- `OPENAI_API_KEY=...`
- `OPENAI_BASE_URL=...`
- `OPENAI_MODEL=gpt-4.1-mini`

如果你使用兼容 OpenAI API 的模型网关，也可以只配置 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY`。

## 8. 依赖安装

```bash
pip install -r requirements.txt
```

## 9. 参考项目（集成学习）

- https://github.com/CSlawyer1985/contract-review-pro
- https://github.com/xiaodingfeng/contract-review

当前实现借鉴了“审查链路拆分 + Skill 化封装”的思路，并进一步切到 LangChain 1.x / LangGraph Agent Runtime，让 MCP 真正作为工具层接入，而不是被当成普通 HTTP API 调用。

## 10. 启动建议

1. 启动 MCP Server：`python mcp_server/main.py`
2. 启动 Gateway：`uvicorn backend.main:app --host 0.0.0.0 --port 8080`
3. 在 OnlyOffice 插件中配置 API 地址（默认 `http://172.27.3.6:8080`）
