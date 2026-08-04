# Reddit 社交媒体数据配置说明

## 📋 概述

Ares 智能研报 的美股社交媒体分析功能依赖 Reddit 离线数据。本文档说明 Reddit 数据的准备方法、数据格式要求以及替代方案。

## ⚠️ 重要说明

### 当前状态

- **Reddit 功能默认不可用**：项目未包含 Reddit 数据，也未提供数据下载脚本
- **源项目情况**：上游项目 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 使用私有数据集 "Tauric TradingDB"，该数据集尚未公开发布
- **自动回退机制**：当 Reddit 数据不可用时，系统会自动使用其他新闻源（Alpha Vantage、Google News 等）

### 影响范围

- **仅影响美股分析**：A 股和港股不使用 Reddit 数据
- **不影响核心功能**：即使没有 Reddit 数据，美股分析仍可正常进行
- **可选功能**：Reddit 数据是增强功能，非必需

## 📁 数据目录结构

Reddit 数据应放置在以下任一目录：

```
data/reddit_data/
├── company_news/          # 公司相关讨论
│   ├── wallstreetbets.jsonl
│   ├── stocks.jsonl
│   └── investing.jsonl
└── global_news/           # 市场整体讨论
    ├── wallstreetbets.jsonl
    ├── stocks.jsonl
    └── investing.jsonl
```

或：

```
tradingagents/dataflows/data_cache/reddit_data/
├── company_news/
└── global_news/
```

## 📄 数据格式要求

### JSONL 文件格式

每个 `.jsonl` 文件包含多行 JSON 对象，每行一个帖子：

```jsonl
{"title": "NVDA earnings beat expectations", "selftext": "Nvidia reported...", "url": "https://reddit.com/...", "ups": 1234, "created_utc": 1704067200}
{"title": "Tesla stock analysis", "selftext": "Looking at TSLA...", "url": "https://reddit.com/...", "ups": 567, "created_utc": 1704070800}
```

### 必需字段

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `title` | string | 帖子标题 | "NVDA earnings beat expectations" |
| `selftext` | string | 帖子正文 | "Nvidia reported Q4 earnings..." |
| `url` | string | 帖子链接 | "https://reddit.com/r/wallstreetbets/..." |
| `ups` | integer | 点赞数 | 1234 |
| `created_utc` | integer | 发布时间（Unix 时间戳） | 1704067200 |

## 🔧 数据获取方法

### 方法 1：等待官方数据集（推荐）

上游项目计划发布 "Tauric TradingDB" 数据集，包含：
- Reddit 历史数据
- Finnhub 新闻数据
- SimFin 财务数据

**状态**：开发中，发布时间未定

**关注渠道**：
- GitHub: https://github.com/TauricResearch/TradingAgents
- 官网: https://tauric.ai/

### 方法 2：使用 Reddit API 自行下载

#### 前置条件

1. **注册 Reddit 应用**
   - 访问：https://www.reddit.com/prefs/apps
   - 创建应用，选择 "script" 类型
   - 获取 `client_id` 和 `client_secret`

2. **安装 praw 库**
   ```bash
   pip install praw
   ```

3. **配置环境变量**
   ```bash
   # .env 文件
   REDDIT_CLIENT_ID=your_client_id_here
   REDDIT_CLIENT_SECRET=your_client_secret_here
   REDDIT_USER_AGENT=Ares 智能研报/1.0
   ```

#### 下载脚本示例

创建 `scripts/download_reddit_data.py`：

```python
import praw
import json
import os
from datetime import datetime, timedelta

# 初始化 Reddit 客户端
reddit = praw.Reddit(
    client_id=os.getenv('REDDIT_CLIENT_ID'),
    client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
    user_agent=os.getenv('REDDIT_USER_AGENT')
)

# 目标 subreddit
subreddits = ['wallstreetbets', 'stocks', 'investing']

# 输出目录
output_dir = 'data/reddit_data/company_news'
os.makedirs(output_dir, exist_ok=True)

# 下载数据
for subreddit_name in subreddits:
    subreddit = reddit.subreddit(subreddit_name)
    output_file = os.path.join(output_dir, f'{subreddit_name}.jsonl')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        # 获取最近 7 天的热门帖子
        for post in subreddit.hot(limit=1000):
            data = {
                'title': post.title,
                'selftext': post.selftext,
                'url': post.url,
                'ups': post.ups,
                'created_utc': int(post.created_utc)
            }
            f.write(json.dumps(data, ensure_ascii=False) + '\n')
    
    print(f'Downloaded {subreddit_name} data to {output_file}')
```

#### 注意事项

- **API 限制**：Reddit API 有严格的速率限制（每分钟约 60 次请求）
- **数据量**：建议分批下载，避免一次性请求过多
- **时间范围**：根据需要调整时间范围（默认 7 天）
- **存储空间**：Reddit 数据可能较大，注意磁盘空间

### 方法 3：使用第三方数据集

#### Pushshift Reddit 数据集

- **网站**：https://files.pushshift.io/reddit/
- **说明**：Reddit 历史数据归档
- **格式**：需要转换为项目所需的 JSONL 格式
- **优点**：数据完整，覆盖时间长
- **缺点**：数据量巨大（TB 级），需要处理和筛选

#### Kaggle 数据集

搜索关键词：
- "Reddit wallstreetbets"
- "Reddit stock discussion"
- "Reddit financial data"

## 🔄 替代方案

如果无法获取 Reddit 数据，系统会自动使用以下替代方案：

### 1. Alpha Vantage 新闻（推荐）

**优点**：
- 官方合作伙伴，API 稳定
- 新闻质量高，覆盖面广
- 免费额度充足（60 次/分钟）

**配置**：
```bash
# .env 文件
ALPHA_VANTAGE_API_KEY=your_api_key_here
```

### 2. Google News

**优点**：
- 免费，无需 API key
- 新闻来源多样
- 实时更新

**缺点**：
- 可能受网络限制
- 需要配置代理

### 3. Finnhub 新闻

**优点**：
- 专业财经新闻
- 支持情绪分析

**配置**：
```bash
# .env 文件
FINNHUB_API_KEY=your_api_key_here
```

## ✅ 验证数据配置

### 检查数据目录

```bash
# 检查目录是否存在
ls -la data/reddit_data/

# 检查文件内容
head -n 5 data/reddit_data/company_news/wallstreetbets.jsonl
```

### 测试数据读取

```python
# 在 Python 中测试
from tradingagents.dataflows.interface import get_reddit_company_news

# 测试读取 NVDA 的 Reddit 讨论
news = get_reddit_company_news("NVDA", "2024-01-01")
print(news)
```

### 查看系统日志

```bash
# 启动分析时查看日志
# 如果 Reddit 数据不可用，会看到回退提示
tail -f logs/tradingagents.log
```

## 🐛 常见问题

### Q1: Reddit 数据目录不存在

**现象**：分析报告中没有 Reddit 讨论内容

**解决方案**：
1. 确认这是正常情况（默认不包含 Reddit 数据）
2. 系统会自动使用其他新闻源
3. 如需 Reddit 数据，按本文档方法准备

### Q2: Reddit API 速率限制

**现象**：下载数据时出现 429 错误

**解决方案**：
```python
# 在下载脚本中添加延迟
import time
time.sleep(1)  # 每次请求后等待 1 秒
```

### Q3: 数据格式错误

**现象**：系统无法读取 Reddit 数据

**解决方案**：
1. 检查 JSONL 格式是否正确（每行一个 JSON 对象）
2. 确认必需字段都存在
3. 验证 Unix 时间戳格式

### Q4: 中文市场能否使用 Reddit？

**回答**：
- A 股和港股不使用 Reddit 数据
- 中文市场使用其他新闻源（Tushare、AkShare、东方财富等）
- 未来可能支持中文社交媒体（雪球、股吧等）

## 📚 相关文档

- [Finnhub 数据配置](./finnhub-news-data-setup.md)
- [数据目录配置](../configuration/data-directory-configuration.md)
- [测试指南](../guides/TESTING_GUIDE.md)
- [v1.0.0-preview 测试计划](../tests/v1.0.0-preview/v1.0.0-preview-test-plan.md)

## 🔗 外部资源

- [Reddit API 文档](https://www.reddit.com/dev/api/)
- [PRAW 文档](https://praw.readthedocs.io/)
- [TauricResearch GitHub](https://github.com/TauricResearch/TradingAgents)
- [Pushshift 数据集](https://files.pushshift.io/reddit/)

## 📝 更新日志

- **2025-01-23**：创建文档，说明 Reddit 数据配置方法和替代方案

