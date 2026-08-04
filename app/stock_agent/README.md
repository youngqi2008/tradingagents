# 问股 Agent（由 daily_stock_analysis 物理迁入）

本目录包含完整 ReAct 问股 Agent，不再依赖 `daily_stock_analysis/` 目录。

## 结构

- `agent/` — AgentExecutor、LiteLLM 工具调用、13 个行情/分析/搜索工具
- `data_provider/` — 多源行情数据
- `strategies/` — 11 种 YAML 交易策略
- `dsa_config.py` — Agent 配置（读取项目根 `.env`）
- `dsa_storage.py` — Agent 数据层（K 线缓存、新闻、分析历史、LLM 用量等，**MySQL**）
- `search_service.py` / `stock_analyzer.py` — 搜索与技术分析

## 业务集成

- 小程序问股：`app/services/stock_ask_agent_service.py` → `AgentExecutor.chat_with_history`
- 用户会话/消息：MySQL `mp_chat_sessions` / `mp_chat_messages`（`app/services/mp_chat_service.py`）
- Agent 工具缓存/历史：MySQL 表 `stock_daily`、`news_intel`、`analysis_history`、`llm_usage` 等（与主库 `ares_ops` 共用）

## 环境变量

见项目根 `.env`：`AGENT_MODE`、`AGENT_MAX_STEPS`、`MYSQL_*`，以及 DSA 兼容的 LLM Key（如 `DASHSCOPE_API_KEY` / `LITELLM_MODEL` 等）。

## 从旧 SQLite 迁移

若存在 `./data/stock_analysis.db`，可执行：

```bash
python scripts/migrate_stock_agent_sqlite_to_mysql.py
```

迁移完成后可删除 SQLite 文件。
