# Contract-Review-Pro V1.4（LangGraph Agent + MCP）

面向 WSL2 + OnlyOffice + MinIO + MySQL 的智能合同生成与审查系统。

基于 LangChain 1.x / LangGraph Agent Runtime 构建，通过 MCP（Model Context Protocol）协议将合同分析能力封装为 5 个 LLM 驱动的工具，由 AI Agent 自主编排调用顺序，实现真正的"模型决策 + 工具执行"分离架构。

---

## 目录

- [1. 架构概览](#1-架构概览)
- [2. 技术栈](#2-技术栈)
- [3. 项目结构](#3-项目结构)
- [4. MCP Tools](#4-mcp-tools)
- [5. 调用模式](#5-调用模式)
- [6. 错误处理与日志](#6-错误处理与日志)
- [7. FastAPI 核心接口](#7-fastapi-核心接口)
- [8. 数据模型](#8-数据模型)
- [9. 配置项](#9-配置项)
- [10. 部署指南](#10-部署指南)
  - [10.1 环境要求](#101-环境要求)
  - [10.2 基础服务部署](#102-基础服务部署)
  - [10.3 应用服务部署](#103-应用服务部署)
  - [10.4 OnlyOffice 插件部署](#104-onlyoffice-插件部署)
  - [10.5 验证部署](#105-验证部署)
- [11. 开发指南](#11-开发指南)
- [12. 故障排查](#12-故障排查)
- [13. 参考项目](#13-参考项目)

---

## 1. 架构概览

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                        用户浏览器 (Chrome/Edge)                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │              OnlyOffice Document Server (:9002)                   │  │
│  │  ┌─────────────────────────────────────────────────────────────┐  │  │
│  │  │           OnlyOffice 插件 (右侧边栏)                         │  │  │
│  │  │  contract_id 输入 → "Start Review" → 风险卡片 + 一键采纳     │  │  │
│  │  └──────────────────────────┬──────────────────────────────────┘  │  │
│  └─────────────────────────────┼─────────────────────────────────────┘  │
└────────────────────────────────┼────────────────────────────────────────┘
                                 │ POST /api/review/start
                                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    FastAPI Gateway (:8080)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │
│  │ routes.py    │  │ review.py    │  │ storage.py   │  │ main.py    │ │
│  │ API 路由     │  │ 审查编排     │  │ MinIO 存储   │  │ 全局异常   │ │
│  └──────┬───────┘  └──────┬───────┘  └──────────────┘  │ + 日志     │ │
│         │                 │                             └────────────┘ │
│         │                 ▼                                            │
│         │  ┌──────────────────────────────────┐                        │
│         │  │    langchain_review.py            │                        │
│         │  │    LangGraph Agent 工作流          │                        │
│         │  │    ┌─────────────────────────┐    │                        │
│         │  │    │ ChatOpenAI (gpt-4.1-mini)│    │                        │
│         │  │    │ + MCP Tools 注册          │    │                        │
│         │  │    │ + Agent 自主编排          │    │                        │
│         │  │    └─────────────────────────┘    │                        │
│         │  └──────────────┬───────────────────┘                        │
│         │                 │ SSE 连接                                    │
└─────────┼─────────────────┼────────────────────────────────────────────┘
          │                 ▼
          │  ┌──────────────────────────────────────────────────────────┐
          │  │              MCP Server (:8000/sse)                       │
          │  │  ┌────────────────────────────────────────────────────┐  │
          │  │  │  llm.py — OpenAI SDK 异步调用                      │  │
          │  │  │  (共享 OPENAI_API_KEY / BASE_URL / MODEL)          │  │
          │  │  └────────────────────────────────────────────────────┘  │
          │  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │
          │  │  │ extract_     │ │ risk_        │ │ generate_        │  │
          │  │  │ contract_    │ │ assessment_  │ │ revision_        │  │
          │  │  │ entities     │ │ scan         │ │ clause           │  │
          │  │  └──────────────┘ └──────────────┘ └──────────────────┘  │
          │  │  ┌──────────────┐ ┌──────────────┐                       │
          │  │  │ draft_       │ │ format_to_   │                       │
          │  │  │ contract_    │ │ legal_       │                       │
          │  │  │ from_template│ │ standard     │                       │
          │  │  └──────────────┘ └──────────────┘                       │
          │  └──────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────┐          ┌─────────────────────┐
│  MySQL (:3306)       │          │  MinIO (:9000)       │
│  contracts 表        │          │  contracts bucket    │
│  review_tasks 表     │          │  onlyoffice/ 目录    │
└─────────────────────┘          └─────────────────────┘
```

### 核心组件职责

| 组件 | 职责 | 技术 |
|---|---|---|
| **MCP Server** | 暴露 5 个 LLM 驱动的合同审查与生成 Tools，每个工具内部调用 OpenAI 兼容 API 完成真实分析 | FastMCP + openai SDK |
| **LangGraph Agent** | AI 应用层，连接模型、发现 MCP tools、发起 `tool_calls`、接收 `ToolMessage` 回填、汇总审查结论 | LangChain 1.x + LangGraph |
| **FastAPI Gateway** | OnlyOffice callback、MinIO 落盘、数据库任务状态、触发审查工作流。含全局异常处理和结构化日志 | FastAPI + SQLAlchemy 2.0 |
| **OnlyOffice Plugin** | 右侧边栏展示风险卡片，支持一键采纳将建议条款替换进文档 | OnlyOffice Plugin SDK |

---

## 2. 技术栈

| 层次 | 技术 | 版本 |
|---|---|---|
| 后端框架 | FastAPI | >=0.135 |
| ORM | SQLAlchemy (async) | >=2.0 |
| 数据库 | MySQL (aiomysql) | >=0.3 |
| 对象存储 | MinIO | >=7.2 |
| AI 框架 | LangChain + LangGraph | >=1.2 |
| MCP 适配 | langchain-mcp-adapters | >=0.2.2 |
| LLM SDK | openai | >=2.26 |
| MCP 协议 | mcp | >=1.27 |
| 文档编辑 | OnlyOffice Document Server | - |
| 前端 | OnlyOffice Plugin (HTML/JS) | - |

---

## 3. 项目结构

```text
Contract_Review/
├── README.md                          # 本文件
├── requirements.txt                   # Python 依赖清单
│
├── backend/                           # FastAPI 后端
│   ├── main.py                        # Uvicorn 入口，re-export app
│   └── app/
│       ├── main.py                    # FastAPI 应用工厂，启动事件，全局异常处理
│       ├── api/
│       │   └── routes.py              # API 路由定义
│       │       ├── POST /api/onlyoffice/callback  # OnlyOffice 文件保存回调
│       │       └── POST /api/review/start          # 合同审查入口
│       ├── core/
│       │   └── config.py              # 环境变量配置（数据库、MinIO、MCP、LLM）
│       ├── db/
│       │   ├── database.py            # SQLAlchemy 异步引擎和会话工厂
│       │   └── models.py              # ORM 模型（Contract, ReviewTask, ContractStatus）
│       ├── schemas/
│       │   └── review.py              # Pydantic 请求模型
│       └── services/
│           ├── langchain_review.py    # LangGraph Agent 工作流（两种模式）
│           ├── review.py              # 审查编排器（状态管理 + 日志）
│           └── storage.py             # MinIO 文件存储服务
│
├── mcp_server/                        # MCP 工具服务器
│   ├── main.py                        # MCP Server 入口（SSE 传输）
│   └── app/
│       ├── llm.py                     # LLM 客户端封装（openai SDK，共享环境变量）
│       └── server.py                  # 5 个 MCP 工具定义（LLM 驱动 + 降级 fallback）
│
└── frontend/                          # OnlyOffice 前端插件
    └── plugin/
        ├── config.json                # 插件清单（名称、GUID、入口）
        ├── index.html                 # 侧边栏 HTML 结构
        └── app.js                     # 前端逻辑（API 调用 + 风险卡片渲染）
```

---

## 4. MCP Tools（LLM 驱动）

所有工具内部通过 `openai` SDK 调用 LLM，读取共享环境变量 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL`。

| 工具 | 输入 | 功能 | LLM 降级策略 |
|---|---|---|---|
| `extract_contract_entities` | `text: str` | 提取甲方、乙方、金额、管辖、生效日期、标的 | 返回默认值 + raw_preview |
| `risk_assessment_scan` | `text: str` | 逐条扫描合同，识别所有法律风险点，返回 findings 数组 | 降级到关键词匹配（RISK_KB） |
| `generate_revision_clause` | `risk_type: str`, `original_text?: str` | 针对风险类型生成具体、可直接使用的替代条款 | 返回通用模板条款 |
| `draft_contract_from_template` | `form_data: dict` | 根据合同要素（当事人、标的等）生成完整合同草稿 | 返回简要大纲 |
| `format_to_legal_standard` | `text: str` | 将非正式文本改写为正式法律中文 | 返回简单包装 |

### 工具内部 LLM 调用流程

```text
MCP 工具被调用
  │
  ├── 构建专业 system prompt（法律顾问 / 实体抽取 / 条款起草等角色）
  ├── 截取输入文本（最大 8000 字符）
  │
  ├── call_llm(system, user)
  │   └── openai SDK → ChatCompletion → 返回文本
  │
  ├── 解析 JSON 输出（call_llm_json）
  │   └── 提取 { } 包裹的 JSON 块
  │
  ├── 成功 → 返回结构化结果
  └── 失败 → logger.error + 返回降级 fallback
```

---

## 5. 调用模式

### 推荐模式：LangGraph Agent + MCP

```text
POST /api/review/start
  │
  ▼
FastAPI → 从 MySQL 加载 Contract → status=REVIEWING
  │
  ▼
LangChainReviewWorkflow.review(contract_text)
  │
  ├── _load_agent()
  │   ├── _load_tools() → MultiServerMCPClient → MCP SSE → 发现 5 个工具
  │   ├── _build_chat_model() → ChatOpenAI(model=gpt-4.1-mini, T=0)
  │   └── create_agent(model, tools, system_prompt, response_format)
  │
  ├── agent.ainvoke({messages: [审查请求]})
  │   ┌──────────── Agent 内部循环 ──────────────┐
  │   │  LLM 分析 → tool_calls: [extract_entities]│
  │   │  → MCP tools/call → ToolMessage 回填       │
  │   │  → LLM 分析 → tool_calls: [risk_scan]     │
  │   │  → MCP tools/call → ToolMessage 回填       │
  │   │  → LLM 分析 → tool_calls: [revision_clause]│
  │   │  → MCP tools/call → ToolMessage 回填       │
  │   │  → LLM 输出最终 AgentReviewPayload         │
  │   └────────────────────────────────────────────┘
  │
  ├── 解析 structured_response → {entities, findings, summary}
  └── 返回 {workflow, entities, findings, summary, messages}

FastAPI → 计算 risk_score → 写入 ReviewTask → status=FINISHED
  │
  ▼
返回 JSON 响应给前端
```

### 兼容模式：Direct MCP

保留了 `REVIEW_WORKFLOW_MODE=compat_direct`（兼容旧值 `compat_http`）。
该模式下不会经过 Agent LLM 决策，而是由后端直接通过 MCP tool 做一次顺序化审查，用于降级或联调。

```text
POST /api/review/start
  │
  ▼
直接调用 MCP 工具（无 LLM 编排）
  ├── extract_contract_entities(text) → entities
  ├── risk_assessment_scan(text) → findings
  └── generate_revision_clause(risk_type) × N → proposed_clauses
  │
  ▼
硬编码组装 summary → 返回结果
```

---

## 6. 错误处理与日志

### 全局异常处理

`backend/app/main.py` 注册了全局 `@app.exception_handler(Exception)`，未捕获异常会：
- 返回结构化 JSON：`{"detail": "Internal server error: ExceptionType"}`
- 记录完整堆栈到日志

### 合同状态流转

```text
DRAFT ──(创建)──> REVIEWING ──(成功)──> FINISHED
                    │
                    └──(异常)──> FAILED
```

审查流程中任何未处理异常都会将合同状态置为 `FAILED`，不会卡在 `REVIEWING`。

### 日志体系

| 组件 | 日志模块 | 记录内容 |
|---|---|---|
| FastAPI 入口 | `app` | 启动、数据库连接、全局异常 |
| API 路由 | `app.routes` | 请求到达、OnlyOffice 回调 |
| 审查编排 | `app.review` | 审查开始/结束、风险评分、状态变更 |
| Agent 工作流 | `app.langchain_review` | Agent 创建、工具加载、执行结果 |
| MCP LLM | `mcp.llm` | 模型名、耗时、token 用量 |
| MCP 工具 | `mcp.server` | 工具调用失败、降级 fallback |

日志格式：`2025-01-01 12:00:00 INFO [app.review] Contract xxx review done | task=yyy score=6.0 findings=3`

---

## 7. FastAPI 核心接口

### `POST /api/onlyoffice/callback`

OnlyOffice Document Server 的文件保存回调。

**请求体**（OnlyOffice 格式）：
```json
{
  "status": 2,
  "url": "http://onlyoffice-server/cache/files/...",
  "key": "document-key-xxx"
}
```

**响应**：固定 `{"error": 0}`

**行为**：`status==2` 时下载临时文件并上传到 MinIO `contracts/onlyoffice/{key}.docx`

---

### `POST /api/review/start`

合同审查入口。

**请求体**：
```json
{
  "contract_id": "contract-uuid-xxx",
  "contract_text": "合同正文内容（可选）"
}
```

**响应**：
```json
{
  "contract_id": "contract-uuid-xxx",
  "task_id": "task-uuid-yyy",
  "risk_score": 9.0,
  "findings": [
    {
      "original_text": "甲方应在合同签订后3个工作日内支付全款...",
      "risk_type": "付款条件不明确",
      "severity": "HIGH",
      "legal_basis": "民法典第509条",
      "suggestion": "建议明确付款时间节点、付款方式及逾期付款违约金...",
      "proposed_clause": "甲方应在本合同签订之日起五个工作日内..."
    }
  ],
  "entities": {
    "party_a": "XX科技有限公司",
    "party_b": "YY贸易有限公司",
    "amount": "人民币100万元",
    "jurisdiction": "北京市朝阳区人民法院",
    "effective_date": "2025年1月1日",
    "subject": "技术服务合同"
  },
  "summary": {
    "overall_risk": "HIGH",
    "review_summary": "共识别 3 个风险点，当前整体风险等级为 HIGH。",
    "next_actions": [
      "优先处理高风险和中风险条款，并将替代条款回写到合同草稿中。",
      "在回写后安排一次人工法务复核，确认商业含义未被改变。"
    ]
  },
  "workflow": {
    "mode": "langgraph_agent_mcp",
    "transport": "sse",
    "server_url": "http://127.0.0.1:8000/sse",
    "agent_framework": "langchain_create_agent",
    "model": "gpt-4.1-mini",
    "tool_calls": [...],
    "tools_used": ["extract_contract_entities", "risk_assessment_scan", "generate_revision_clause"]
  },
  "messages": [...],
  "status": "FINISHED"
}
```

### `GET /health`

健康检查接口，返回 `{"status": "ok"}`。

---

## 8. 数据模型

### contracts 表

| 字段 | 类型 | 说明 |
|---|---|---|
| `contract_id` | String(64) PK | 合同唯一标识 |
| `file_name` | String(255) | 文件名 |
| `minio_url` | String(512) | MinIO 存储地址 |
| `status` | Enum | `DRAFT` / `REVIEWING` / `FINISHED` / `FAILED` |
| `created_at` | DateTime | 创建时间 |

### review_tasks 表

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | String(64) PK | 审查任务唯一标识 |
| `contract_id` | String(64) FK | 关联合同 |
| `risk_score` | Float | 风险评分（HIGH=3, MEDIUM=2, LOW=1 累加） |
| `findings_json` | JSON | 完整审查结果（entities + findings + summary） |
| `created_at` | DateTime | 创建时间 |

---

## 9. 配置项

以下环境变量由后端和 MCP Server **共享**：

| 变量 | 默认值 | 必填 | 说明 |
|---|---|---|---|
| `OPENAI_API_KEY` | `""` | **是** | OpenAI API 密钥 |
| `OPENAI_BASE_URL` | `""` | 否 | OpenAI 兼容 API 地址（留空则用官方端点） |
| `OPENAI_MODEL` | `gpt-4.1-mini` | 否 | 模型名称 |
| `REVIEW_WORKFLOW_MODE` | `langchain` | 否 | `langchain`（Agent 模式）或 `compat_direct`（直接调用） |
| `MCP_SSE_URL` | `http://127.0.0.1:8000/sse` | 否 | MCP Server SSE 地址 |
| `DATABASE_URL` | `mysql+aiomysql://root:password@172.27.3.6:3306/contract_review` | 否 | MySQL 连接字符串 |
| `MINIO_ENDPOINT` | `172.27.3.6:9000` | 否 | MinIO 地址 |
| `MINIO_ACCESS_KEY` | `minioadmin` | 否 | MinIO 访问密钥 |
| `MINIO_SECRET_KEY` | `minioadmin` | 否 | MinIO 密钥 |
| `MINIO_BUCKET` | `contracts` | 否 | MinIO 存储桶名称 |

> 如果你使用兼容 OpenAI API 的模型网关（如 Azure OpenAI、Ollama、vLLM 等），配置 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY` 即可，无需修改代码。

---

## 10. 部署指南

### 10.1 环境要求

| 项目 | 最低要求 | 推荐 |
|---|---|---|
| 操作系统 | WSL2 / Linux / macOS | WSL2 (Ubuntu 22.04+) |
| Python | 3.10+ | 3.10 |
| 内存 | 4GB | 8GB+ |
| 磁盘 | 2GB | 10GB+ |
| 网络 | 能访问 OpenAI API 或兼容端点 | 稳定网络 |

### 10.2 基础服务部署

#### 10.2.1 MySQL

```bash
# 使用 Docker 启动 MySQL
docker run -d \
  --name mysql-contract \
  -p 3306:3306 \
  -e MYSQL_ROOT_PASSWORD=password \
  -e MYSQL_DATABASE=contract_review \
  mysql:8.0

# 或使用已有 MySQL 实例，创建数据库
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS contract_review CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

验证连接：
```bash
mysql -u root -ppassword -h 127.0.0.1 -e "USE contract_review; SELECT 1;"
```

#### 10.2.2 MinIO

```bash
# 使用 Docker 启动 MinIO
docker run -d \
  --name minio-contract \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"
```

验证：
```bash
# 浏览器访问 MinIO Console
# http://localhost:9001
# 用户名: minioadmin / 密码: minioadmin
```

#### 10.2.3 OnlyOffice Document Server

```bash
# 使用 Docker 启动 OnlyOffice
docker run -d \
  --name onlyoffice \
  -p 9002:80 \
  -e JWT_ENABLED=false \
  onlyoffice/documentserver
```

验证：
```bash
# 浏览器访问
# http://localhost:9002
# 应看到 OnlyOffice 欢迎页面
```

### 10.3 应用服务部署

#### 10.3.1 环境准备

```bash
# 克隆项目
git clone <repo-url> Contract_Review
cd Contract_Review

# 创建 conda 环境（推荐）
conda create -n env_test python=3.10 -y
conda activate env_test

# 安装依赖
pip install -r requirements.txt
```

#### 10.3.2 配置环境变量

创建 `.env` 文件或直接 export：

```bash
# 必填：LLM 配置
export OPENAI_API_KEY="sk-your-api-key-here"

# 可选：使用兼容 API 网关
export OPENAI_BASE_URL="https://api.openai.com/v1"   # 或你的网关地址
export OPENAI_MODEL="gpt-4.1-mini"

# 可选：覆盖默认服务地址
export DATABASE_URL="mysql+aiomysql://root:password@127.0.0.1:3306/contract_review"
export MINIO_ENDPOINT="127.0.0.1:9000"
export MCP_SSE_URL="http://127.0.0.1:8000/sse"

# 可选：工作流模式
export REVIEW_WORKFLOW_MODE="langchain"   # 或 compat_direct
```

#### 10.3.3 启动 MCP Server

```bash
# 在项目根目录下
cd /path/to/Contract_Review

# 启动 MCP Server（SSE 传输，默认端口 8000）
python mcp_server/main.py
```

预期输出：
```text
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

验证 MCP Server：
```bash
# 检查 SSE 端点是否响应
curl -s http://127.0.0.1:8000/sse -m 3 || echo "SSE endpoint reachable (timeout expected)"
```

#### 10.3.4 启动 FastAPI Gateway

```bash
# 在另一个终端
cd /path/to/Contract_Review

# 启动 Gateway（默认端口 8080）
uvicorn backend.main:app --host 0.0.0.0 --port 8080
```

预期输出：
```text
2025-01-01 12:00:00 INFO [app] Starting Contract Review Gateway ...
2025-01-01 12:00:00 INFO [app] Database tables ensured.
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)
```

验证 Gateway：
```bash
# 健康检查
curl http://127.0.0.1:8080/health
# 预期: {"status":"ok"}
```

### 10.4 OnlyOffice 插件部署

1. 将 `frontend/plugin/` 目录复制到 OnlyOffice Document Server 的插件目录：

```bash
# Docker 环境下
docker cp frontend/plugin/ onlyoffice:/var/www/onlyoffice/documentserver/sdkjs-plugins/contract-review
```

2. 修改 `frontend/plugin/app.js` 中的 `API_BASE` 地址：

```javascript
// 将 API_BASE 改为你的 FastAPI Gateway 地址
const API_BASE = "http://172.27.3.6:8080";
```

3. 重启 OnlyOffice Document Server：

```bash
docker restart onlyoffice
```

4. 在 OnlyOffice 编辑器中，点击插件图标打开右侧边栏，输入 `contract_id` 并点击 "Start Review"。

### 10.5 验证部署

#### 10.5.1 端到端测试

```bash
# 1. 确认所有服务运行中
curl http://127.0.0.1:8080/health                    # FastAPI Gateway
curl -s http://127.0.0.1:8000/sse -m 1 || true       # MCP Server

# 2. 测试审查接口（需要先在 MySQL 中有 contract 记录）
curl -X POST http://127.0.0.1:8080/api/review/start \
  -H "Content-Type: application/json" \
  -d '{
    "contract_id": "test-001",
    "contract_text": "甲方：XX科技有限公司\n乙方：YY贸易有限公司\n\n第一条 标的\n甲方为乙方提供技术服务，具体内容见附件一。\n第二条 价款\n合同总价人民币100万元，乙方应在合同签订后付款。\n第三条 违约责任\n任何一方违约应承担违约责任。\n第四条 争议解决\n双方因本合同产生争议，由合同签订地法院管辖。"
  }'
```

#### 10.5.2 预期结果

成功响应应包含：
- `status`: `"FINISHED"`
- `risk_score`: 大于 0
- `findings`: 非空数组，每项含 `risk_type`、`severity`、`legal_basis`、`suggestion`
- `entities`: 包含识别出的 `party_a`、`party_b`、`amount` 等
- `summary`: 包含 `overall_risk`、`review_summary`、`next_actions`
- `workflow.tools_used`: 列出实际调用的 MCP 工具

#### 10.5.3 检查日志

```bash
# 终端中的日志应显示完整的调用链路：
# INFO [app.routes] Review start | contract_id=test-001
# INFO [app.review] Contract test-001 status -> REVIEWING
# INFO [app.langchain_review] Agent created | model=gpt-4.1-mini tools=5
# INFO [mcp.llm] LLM call ok | model=gpt-4.1-mini | 2.3s | prompt_tokens=1234 completion_tokens=567
# INFO [app.langchain_review] Agent review done | tools_used=[...]
# INFO [app.review] Contract test-001 review done | task=xxx score=6.0 findings=3
```

---

## 11. 开发指南

### 切换工作流模式

```bash
# Agent 模式（默认，推荐）：LLM 自主编排工具调用
export REVIEW_WORKFLOW_MODE=langchain

# 直接调用模式：跳过 LLM 冗余推理，用于调试或降级
export REVIEW_WORKFLOW_MODE=compat_direct
```

### 使用兼容 API 网关

```bash
# Azure OpenAI
export OPENAI_BASE_URL="https://your-resource.openai.azure.com/"
export OPENAI_API_KEY="your-azure-key"
export OPENAI_MODEL="gpt-4o"

# Ollama（本地模型）
export OPENAI_BASE_URL="http://localhost:11434/v1"
export OPENAI_API_KEY="ollama"
export OPENAI_MODEL="qwen2.5:14b"

# vLLM / LiteLLM
export OPENAI_BASE_URL="http://localhost:4000/v1"
export OPENAI_API_KEY="your-key"
export OPENAI_MODEL="your-model"
```

### 添加新的 MCP 工具

1. 在 `mcp_server/app/server.py` 中添加新的 `@mcp.tool()` 函数
2. 如需 LLM 能力，调用 `from app.llm import call_llm, call_llm_json`
3. 添加 try/except 降级逻辑
4. 如需在 Agent 模式中使用，在 `langchain_review.py` 的 `_system_prompt()` 中添加指引

### 修改 Agent 行为

编辑 `backend/app/services/langchain_review.py` 中的 `_system_prompt()` 方法，调整 Agent 的决策约束和调用流程。

---

## 12. 故障排查

### MCP Server 启动失败

```text
错误: ModuleNotFoundError: No module named 'openai'
解决: pip install openai>=2.26
```

### FastAPI 启动时数据库连接失败

```text
错误: Can't connect to MySQL server
解决:
1. 检查 MySQL 是否运行: mysql -u root -ppassword -e "SELECT 1"
2. 检查 DATABASE_URL 环境变量是否正确
3. 检查防火墙是否放行 3306 端口
```

### Agent 调用工具失败

```text
错误: LangChainWorkflowUnavailable: Cannot connect to MCP server
解决:
1. 确认 MCP Server 已启动: curl http://127.0.0.1:8000/sse
2. 检查 MCP_SSE_URL 环境变量
3. 检查 MCP Server 日志是否有 LLM 调用错误
```

### LLM 调用超时或失败

```text
错误: openai.APITimeoutError / openai.APIConnectionError
解决:
1. 检查 OPENAI_API_KEY 是否有效
2. 检查 OPENAI_BASE_URL 是否可访问
3. 检查网络代理设置
4. MCP Server 日志会显示具体错误信息
```

### 审查结果质量不佳

```text
可能原因:
1. 模型能力不足 → 尝试更强的模型（gpt-4o, claude-sonnet 等）
2. 合同文本过长被截断 → 当前限制 8000 字符
3. 合同文本格式混乱 → 预处理清理格式后再传入
```

---

## 13. 参考项目

- https://github.com/CSlawyer1985/contract-review-pro
- https://github.com/xiaodingfeng/contract-review

当前实现借鉴了"审查链路拆分 + Skill 化封装"的思路，并进一步切到 LangChain 1.x / LangGraph Agent Runtime，让 MCP 真正作为工具层接入，而不是被当成普通 HTTP API 调用。
