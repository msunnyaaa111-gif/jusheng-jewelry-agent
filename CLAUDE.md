# 金榕珠宝 AI 导购智能体

## 项目定位

基于公司货盘表的 AI 珠宝导购前置系统，不是独立商城。通过企业微信等渠道接入，用多轮对话理解用户需求（预算、品类、材质、送礼对象、风格、星座生肖等），从真实货盘中检索商品，输出推荐结果（含商品卡片/二维码），引导用户进入现有小程序完成下单。

技术栈：Python + FastAPI（后端），React + TypeScript + Vite（前端），LongCat LLM API。

## 架构分层

```
消息接入 → 条件解析 → 会话管理 → 商品检索 → 排序打分 → 文案生成 → 响应输出
```

核心模块（按文件）：
- `backend/app/api/routes.py` — API 路由，包含普通/流式对话接口、管理接口
- `backend/app/services/condition_parser.py` — 语义解析引擎，正则启发式 + LLM 双路，提取预算/品类/材质/送礼对象/星座生肖等条件
- `backend/app/services/dialogue_service.py` — 对话编排，合并条件、判断动作类型、生成回复/fallback；含图片分析（`IMAGE_ANALYSIS_SYSTEM_PROMPT` + `_analyze_images`），与条件解析并发执行
- `backend/app/services/recommendation_service.py` — 商品检索与排序，含预算浮动召回、星座生肖规则映射、打分
- `backend/app/services/longcat_client.py` — LLM 调用封装，支持流式/非流式、Omni 多模态格式
- `backend/app/services/product_color_inference_service.py` — 商品图片颜色推断，含缓存
- `backend/app/models/session.py` — SessionState Pydantic 模型，所有条件字段定义
- `backend/app/repositories/product_repository.py` — 货盘加载（Excel + JSON 双路），含嵌入图片提取

## 关键约定

### 动作类型枚举
`GREETING` / `ASK_FOLLOWUP` / `RETRIEVE_AND_RECOMMEND` / `RERANK_AND_RECOMMEND` / `EXPLAIN_NO_RESULT` / `CLARIFY_CONFLICT` / `GENERAL_REPLY`

### 条件优先级（来自 PRD）
- 一级（强过滤）：系统款式、预算（±15%→±20%）、主材质/配石材质、二维码/图片可用性
- 二级（加权排序）：适合人群、显贵款、系统属性、产品优势卖点、折扣
- 三级（辅助加权）：图片分析结果、星座/生肖映射、使用场景、风格倾向

### 品类别名（手链=手串、项链=吊坠）
定义在 `condition_parser.py:CATEGORY_ALIASES`

### 预算规则
统一按 `wholesale_price`（批发裸价），默认 ±15% 浮动，不足 3 款放宽到 ±20%

### 回复模式
- `cards`：返回结构化 JSON → 前端渲染商品卡片
- `text`：LLM 生成 Markdown 文案 → 前端流式展示

### 条件变更必须重算
用户修改预算/款式/材质/送礼对象/风格/星座生肖后，必须重新检索和排序，禁止复用旧推荐结果。

## 环境变量

| 变量 | 说明 | 必需 |
|------|------|------|
| `LONGCAT_API_KEY` | LongCat API 密钥 | 是 |
| `LONGCAT_MODEL` | 默认模型（默认 LongCat-Flash-Chat） | 否 |
| `LONGCAT_VISION_MODEL` | 多模态模型（需含 omni，默认同 LONGCAT_MODEL） | 否 |
| `LONGCAT_API_URL` | API 地址 | 否 |
| `LONGCAT_CONNECT_TIMEOUT_SECONDS` | 连接超时（默认 10） | 否 |
| `LONGCAT_READ_TIMEOUT_SECONDS` | 读取超时（默认 75） | 否 |
| `PRODUCT_JSON_PATH` | 货盘 JSON 路径（优先于 Excel） | 否 |
| `PRODUCT_XLSX_PATH` | 货盘 Excel 路径 | 否 |
| `PRODUCT_COLOR_CACHE_PATH` | 颜色推断缓存路径 | 否 |
| `PRODUCT_COLOR_INFERENCE_LIMIT` | 颜色推断上限（默认 24） | 否 |
| `CORS_ALLOWED_ORIGINS` | 逗号分隔的 CORS 域名 | 否 |

## API 路由

### 对话
- `POST /api/chat/message` — 普通对话，一次性返回完整结果
- `POST /api/chat/stream` — 流式对话，SSE（status/delta/done 事件）

### 管理
- `GET /health` — 健康检查
- `POST /api/admin/catalog/reload` — 重新加载货盘
- `GET /api/admin/catalog/summary` — 货盘摘要
- `GET /api/admin/mappings` — 查看训练映射
- `POST /api/admin/mappings/train` — 新增训练映射
- `GET /api/admin/mappings/examples` — 查看对话训练样本
- `GET /api/admin/chat-logs` — 查看用户对话日志（支持 session_id/user_id/keyword 过滤）
- `GET /api/admin/diagnostics/llm` — LLM 连接诊断（支持 model/temperature 参数）

## 已知问题（已修复，2026-04-30）

### ~~Bug：颜色别名乱码~~ ✅ 已修复
~~`recommendation_service.py:550` 的 `_matches_primary_color_preferences` 方法中，颜色别名映射表的中文字符全部是 UTF-8 乱码。~~ 已替换为正确的 12 色中文别名，补充了黄色/橙色/棕色，同时删除了废弃方法 `_matches_color_preferences`。

### ~~图片上传未打通~~ ✅ 已修复
~~后端 `routes.py:168` 收到 `image_urls` 后未传递到对话服务。~~ 已打通完整链路：routes 透传 → dialogue_service 并发分析 → recommendation_service 参与检索加权。

### ~~错误详情泄露~~ ✅ 已修复
~~LLM 诊断接口将上游 API 原始响应体原样返回前端。~~ 已新增 `_sanitize_error_body` 三层脱敏（JSON 递归 + 正则 token + 高熵检测）。

## 已知技术债务（待修复，需架构决策）

### 会话状态仅存内存
`dialogue_service.py:169-170` 使用 Python dict 存储 sessions/histories，服务重启后所有会话丢失。后续上线需持久化到 Redis 或数据库。

### 缺少速率限制
无请求频率控制，对话接口可被滥用导致 LLM 调用成本失控。需确定限流策略后引入 slowapi 或中间件。

## 最近修复（2026-05-01）

### P0 全修复 | P1 死代码 | P2-7/8/9/10/12 重构与前端
P0（颜色乱码、图片链路、敏感信息）+ P1（死代码删除）+ P2（lru_cache 单例、SCORE_* 常量、追问优先级、前端 localStorage session、前端图片上传）。剩余 2 项需决策后实施。

## 测试

```bash
# 后端测试
cd backend
.\.venv\Scripts\python.exe -m pytest tests/ -v

# 前端开发
cd frontend
npm run dev
```

核心测试文件覆盖：条件解析（30+ 场景）、推荐检索排序、对话编排（包含重排和拒绝浏览）、LongCat 客户端 payload 格式。

## 本地调试

```powershell
# 启动后端
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 命令行实时聊天
.\.venv\Scripts\python.exe live_chat.py
```

## 部署

详见 `DEPLOY_VERCEL_RAILWAY.md`。建议上线前先用 `scripts/export_catalog_bundle.py` 将 Excel 导出为 JSON + catalog_media，避免直接读取超大 Excel。
