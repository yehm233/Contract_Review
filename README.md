# Contract-Review-Pro V1.2（敏捷极速版）

面向 WSL2 + OnlyOffice + MinIO + MySQL 的智能合同生成与审查系统。

## 1. 架构概览

```text
Browser(前端页面/插件)
   -> OnlyOffice Document Server (172.27.3.6:9002)
   -> FastAPI Gateway (172.27.3.6:8080)
   -> MinIO OSS (172.27.3.6:9000)
   -> MySQL (172.27.3.6:3306)
   -> MCP Server (127.0.0.1:8000)
```

- **MCP Server**：封装合同审查与生成 Skills。
- **FastAPI Gateway**：OnlyOffice callback、MinIO落盘、数据库任务状态、触发MCP审查。
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
    services/{review.py,storage.py}
  main.py
mcp_server/
  app/server.py
  main.py
frontend/plugin/
  config.json
  index.html
  app.js
```

## 3. MCP Skills（首版可联通 Mock）

- `extract_contract_entities(text)`：抽取甲乙方、金额、管辖等实体。
- `risk_assessment_scan(text)`：风险点扫描，返回风险等级与法律依据。
- `generate_revision_clause(risk_type)`：生成风险替换条款。
- `draft_contract_from_template(form_data)`：表单生成合同初稿。
- `format_to_legal_standard(text)`：商业表述法律化润色。

## 4. FastAPI 核心接口

- `POST /api/onlyoffice/callback`
  - `status==2` 时下载 OnlyOffice 临时文件并上传到 MinIO。
  - 固定返回 `{"error":0}`。
- `POST /api/review/start`
  - 输入：`{"contract_id":"..."}`。
  - 更新合同状态 -> 调用 MCP -> 写入 `review_tasks` -> 返回结构化结果。

## 5. 数据模型

- `contracts(contract_id,file_name,minio_url,status,created_at)`
- `review_tasks(task_id,contract_id,risk_score,findings_json,created_at)`

## 6. 参考项目（集成学习）

- https://github.com/CSlawyer1985/contract-review-pro
- https://github.com/xiaodingfeng/contract-review

当前实现借鉴了“审查链路拆分 + Skill 化封装”的思路，并转换为 MCP Tool 形式，便于后续接入 LangChain/Agent 编排。

## 7. 启动建议

1. 启动 MCP Server：`python mcp_server/main.py`
2. 启动 Gateway：`uvicorn backend.main:app --host 0.0.0.0 --port 8080`
3. 在 OnlyOffice 插件中配置 API 地址（默认 `http://172.27.3.6:8080`）
