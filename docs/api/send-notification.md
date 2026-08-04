# 发送消息接口使用文档

Ares 系统提供两种向**小程序用户**推送站内通知的方式：

| 方式 | 适用场景 | 鉴权 |
|------|----------|------|
| **外部信号 Webhook** | 量化/策略系统自动推送买卖点 | 可选 Token |
| **运营后台 API** | 人工发公告、定向通知 | 管理员 JWT |

**生产环境 Base URL**：`http://47.95.5.18:18888`

---

## 零配置发送指南（当前生产环境）

> **当前状态**：生产环境 `ARES_SIGNAL_TOKEN` 未配置（为空），外部信号接口**无需任何 Token 或登录**，直接 POST 即可推送消息到小程序全员站内信。

适用于：策略程序、企业微信机器人、定时任务等外部系统，自动推送买卖点信号。

### 三步发送

| 步骤 | 操作 |
|------|------|
| 1 | 按格式组装 JSON 请求体（见下方） |
| 2 | `POST http://47.95.5.18:18888/api/ares/signal`，Header 只需 `Content-Type: application/json` |
| 3 | 检查响应 `success: true`，用户在小程序「通知」页即可看到 |

### 消息格式（必须遵守）

`text.content` 须包含以下要素：

| 要素 | 买点 | 卖点 |
|------|------|------|
| 信号标签 | `[关注]` | `[取消关注]` |
| 股票代码 | `6位数字.交易所`，如 `600378.SSE` | 同上 |
| 时间（可选） | `时间: 2026-07-11 10:15:04` | 同上 |

**买点完整示例：**

```json
{
  "msgtype": "text",
  "text": {
    "content": "[关注] 600378.SSE\n时间: 2026-07-11 10:15:04"
  }
}
```

**卖点完整示例：**

```json
{
  "msgtype": "text",
  "text": {
    "content": "[取消关注] 600378.SSE\n时间: 2026-07-11 15:00:00"
  }
}
```

### 最简调用（复制即用）

**curl：**

```bash
curl -X POST "http://47.95.5.18:18888/api/ares/signal" \
  -H "Content-Type: application/json" \
  -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"[关注] 600378.SSE\\n时间: 2026-07-11 10:15:04\"}}"
```

**PowerShell：**

```powershell
$body = @{
  msgtype = "text"
  text    = @{ content = "[关注] 600378.SSE`n时间: 2026-07-11 10:15:04" }
} | ConvertTo-Json -Depth 3

Invoke-RestMethod -Uri "http://47.95.5.18:18888/api/ares/signal" `
  -Method POST -ContentType "application/json" -Body $body
```

**Python：**

```python
import requests

resp = requests.post(
    "http://47.95.5.18:18888/api/ares/signal",
    json={
        "msgtype": "text",
        "text": {"content": "[关注] 600378.SSE\n时间: 2026-07-11 10:15:04"},
    },
    timeout=10,
)
print(resp.status_code, resp.json())
```

> 以上示例均**不需要** `X-Ares-Signal-Token` 或 `Authorization` Header。

### 成功响应

```json
{
  "success": true,
  "message": "信号已推送",
  "data": {
    "notification_id": "abc123...",
    "title": "买点信号 · 600378",
    "notice_type": "buy_signal",
    "recipient_count": 42
  }
}
```

`recipient_count` 为本次触达的小程序用户数。

### 常见错误

| 现象 | 原因 | 处理 |
|------|------|------|
| `content 须包含 [关注]...` | 缺少买点/卖点标签 | 正文加上 `[关注]` 或 `[取消关注]` |
| `未识别股票代码` | 代码格式不对 | 使用 `600378.SSE` 格式（6位数字 + 点 + 交易所） |
| `msgtype 仅支持 text` | msgtype 写错 | 固定为 `"text"` |
| HTTP 429 | 超过限流 | 同一 IP 每分钟最多 120 次，适当降频 |
| 连接失败 | 服务未启动 | 先检查 `curl http://47.95.5.18:18888/api/health` |

### 推送效果

- 买点 → 小程序通知标题：`买点信号 · 600378`
- 卖点 → 小程序通知标题：`卖点信号 · 600378`
- 推送范围：全部小程序用户（`target_type = all`）

### 与配置 Token 后的区别

| 项目 | 当前（未配置 Token） | 配置 Token 后 |
|------|---------------------|---------------|
| 是否需要 Header 鉴权 | **否** | 是，须带 `X-Ares-Signal-Token` 或 `Authorization: Bearer` |
| 请求体格式 | 相同 | 相同 |
| 接口地址 | 相同 | 相同 |

配置 Token 的方法见本文 [第四节](#四配置与安全建议)。

---

## 一、外部买卖点信号 Webhook（完整说明）

外部系统（如企业微信机器人、策略引擎）调用此接口，自动解析买卖点并推送给**全部小程序用户**。

### 1.1 基本信息

| 项目 | 说明 |
|------|------|
| **URL** | `POST /api/ares/signal` |
| **完整地址** | `http://47.95.5.18:18888/api/ares/signal` |
| **Content-Type** | `application/json` |
| **限流** | 120 次/分钟（按 IP） |

### 1.2 鉴权说明

**当前生产环境未配置 Token**，发送方式见上文 [零配置发送指南](#零配置发送指南当前生产环境)，无需任何鉴权 Header。

若在服务器 `.env` 中配置了 `ARES_SIGNAL_TOKEN`，则每次请求须额外携带以下任一 Header：

```
X-Ares-Signal-Token: <your-token>
```

或

```
Authorization: Bearer <your-token>
```

未带 Token 或 Token 错误将返回 HTTP 401。

### 1.3 请求体

兼容企业微信 `text` 消息格式：

```json
{
  "msgtype": "text",
  "text": {
    "content": "[关注] 600378.SSE\n时间: 2026-07-11 10:15:04"
  }
}
```

#### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `msgtype` | string | 是 | 固定为 `"text"` |
| `text.content` | string | 是 | 信号正文，见下方解析规则 |

#### 内容解析规则

| 规则 | 说明 |
|------|------|
| `[关注]` | 买点 → `notice_type = buy_signal` |
| `[取消关注]` | 卖点 → `notice_type = sell_signal` |
| 股票代码 | 格式 `\d{6}.[A-Z]+`，如 `600378.SSE`、`000001.SZSE` |
| 时间（可选） | `时间: yyyy-MM-dd HH:mm:ss` |
| 推送范围 | 固定 `target_type = all`（全员） |

#### 示例

**买点信号：**

```json
{
  "msgtype": "text",
  "text": {
    "content": "[关注] 600378.SSE\n时间: 2026-07-11 10:15:04"
  }
}
```

**卖点信号：**

```json
{
  "msgtype": "text",
  "text": {
    "content": "[取消关注] 000001.SZSE\n时间: 2026-07-11 14:30:00"
  }
}
```

### 1.4 成功响应

**HTTP 200**

```json
{
  "success": true,
  "message": "信号已推送",
  "data": {
    "notification_id": "abc123...",
    "title": "买点信号 · 600378",
    "notice_type": "buy_signal",
    "recipient_count": 42
  }
}
```

### 1.5 错误响应

| HTTP | 原因 | 示例 `detail` |
|------|------|---------------|
| 400 | 内容格式错误 | `content 须包含 [关注]（买点）或 [取消关注]（卖点）` |
| 400 | 股票代码未识别 | `未识别股票代码，格式示例：600378.SSE` |
| 400 | msgtype 不支持 | `msgtype 仅支持 text` |
| 401 | Token 无效 | `无效的信号推送令牌` |
| 429 | 超过限流 | 每分钟超过 120 次 |
| 500 | 服务内部错误 | `信号推送失败: ...` |

### 1.6 调用示例

**当前环境（无 Token）**：见 [零配置发送指南](#零配置发送指南当前生产环境)。

**配置 Token 后（须带鉴权 Header）：**

```bash
curl -X POST "http://47.95.5.18:18888/api/ares/signal" \
  -H "Content-Type: application/json" \
  -H "X-Ares-Signal-Token: your-secret-token" \
  -d '{
    "msgtype": "text",
    "text": {
      "content": "[取消关注] 600378.SSE\n时间: 2026-07-11 15:00:00"
    }
  }'
```

### 1.7 小程序展示效果

- 买点：标题显示为 `买点信号 · 600378`，列表带买点标识
- 卖点：标题显示为 `卖点信号 · 600378`，列表带卖点标识
- 用户在小程序「通知」页可查看、标记已读

### 1.8 相关代码

- 路由：`app/routers/ares_signal.py`
- 解析与推送：`app/services/ares_signal_service.py`
- 限流配置：`app/middleware/rate_limit.py`（`/api/ares/signal` 为 120 次/分钟）

---

## 二、运营后台手动发通知 API

适用于运营人员通过接口或后台 UI 发送公告、定向通知。

### 2.1 登录获取 Token

```bash
curl -X POST "http://47.95.5.18:18888/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

响应中的 `access_token` 用于后续请求：

```json
{
  "success": true,
  "data": {
    "access_token": "eyJ...",
    "token_type": "bearer"
  }
}
```

### 2.2 发送通知

| 项目 | 说明 |
|------|------|
| **URL** | `POST /api/admin/ops/notifications` |
| **完整地址** | `http://47.95.5.18:18888/api/admin/ops/notifications` |
| **鉴权** | `Authorization: Bearer <access_token>`（须管理员账号） |

#### 请求体

```json
{
  "title": "系统维护通知",
  "content": "今晚 22:00-23:00 进行系统维护，期间服务可能短暂不可用。",
  "notice_type": "announcement",
  "target_type": "all"
}
```

#### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `title` | string | 是 | 标题，1–128 字符 |
| `content` | string | 是 | 正文 |
| `notice_type` | string | 否 | 默认 `announcement`；也可 `buy_signal` / `sell_signal` |
| `target_type` | string | 是 | `all` / `membership` / `users` |
| `target_membership_level_id` | string | 条件 | `target_type=membership` 时必填 |
| `target_user_ids` | string[] | 条件 | `target_type=users` 时必填，如 `["1","2","3"]` |

#### 发送范围示例

**全员公告：**

```json
{
  "title": "新功能上线",
  "content": "问股功能已上线，欢迎体验！",
  "notice_type": "announcement",
  "target_type": "all"
}
```

**指定会员等级：**

```json
{
  "title": "VIP 专属福利",
  "content": "本月 VIP 用户享受双倍积分。",
  "notice_type": "announcement",
  "target_type": "membership",
  "target_membership_level_id": "<会员等级ID>"
}
```

**指定用户：**

```json
{
  "title": "账户提醒",
  "content": "您的余额不足，请及时充值。",
  "notice_type": "announcement",
  "target_type": "users",
  "target_user_ids": ["1", "5", "12"]
}
```

#### 成功响应

```json
{
  "success": true,
  "message": "已发送给 42 位用户",
  "data": {
    "id": "notif_xxx",
    "title": "系统维护通知",
    "content": "...",
    "notice_type": "announcement",
    "target_type": "all",
    "status": "published",
    "recipient_count": 42,
    "read_count": 0,
    "created_by": "admin",
    "created_at": "2026-07-13T15:30:00+08:00"
  }
}
```

#### curl 示例

```bash
TOKEN="eyJ..."

curl -X POST "http://47.95.5.18:18888/api/admin/ops/notifications" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "title": "测试通知",
    "content": "这是一条测试消息",
    "notice_type": "announcement",
    "target_type": "all"
  }'
```

### 2.3 其他管理接口

| 方法 | URL | 说明 |
|------|-----|------|
| GET | `/api/admin/ops/notifications` | 分页查询已发通知 |
| POST | `/api/admin/ops/notifications/{id}/revoke` | 撤回通知 |

也可在运营后台 UI 操作：`http://47.95.5.18:18888` → **小程序站内通知** → **发送通知**。

### 2.4 相关代码

- 路由：`app/routers/admin_ops.py`
- 数据模型：`app/models/mp_notification.py`
- 前端页面：`frontend/src/views/Ops/MpNotifications.vue`

---

## 三、两种接口对比

| 对比项 | `/api/ares/signal` | `/api/admin/ops/notifications` |
|--------|-------------------|-------------------------------|
| 调用方 | 外部自动化系统 | 运营后台 / 管理员脚本 |
| 鉴权 | 可选 `ARES_SIGNAL_TOKEN` | 管理员 JWT |
| 内容格式 | 固定文本模板（`[关注]`/`[取消关注]`） | 自由标题+正文 |
| 推送范围 | 固定全员 | 全员 / 会员等级 / 指定用户 |
| 通知类型 | 自动 `buy_signal` / `sell_signal` | 可自定义 `notice_type` |
| 发送人记录 | `ares_signal` | 管理员用户名 |

---

## 四、配置与安全建议

1. **配置信号 Token**：在 `scripts/deploy/env.47.95.5.18.production.env` 中设置：

   ```
   ARES_SIGNAL_TOKEN=your-strong-random-token
   ```

   修改后执行 `./scripts/deploy/deploy_prod.sh backend` 重启后端。

2. **HTTPS**：小程序正式版须配置 HTTPS 合法域名；当前 `http://47.95.5.18:18888` 仅适合开发/体验版。

3. **健康检查**：

   ```bash
   curl http://47.95.5.18:18888/api/health
   ```
