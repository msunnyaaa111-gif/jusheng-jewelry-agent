# 钜盛珠宝智能体后端

当前后端包含：
- `FastAPI` 对话与管理接口
- `LongCat` 大模型调用
- Excel 货盘读取、检索与推荐
- 本地实时调试脚本

## 安装依赖

```bash
pip install -r requirements.txt
```

## 环境变量

复制配置文件：

```bash
copy .env.example .env
```

至少需要填写：
- `LONGCAT_API_KEY`

可选填写：
- `PRODUCT_JSON_PATH`
- `PRODUCT_XLSX_PATH`
- `CORS_ALLOWED_ORIGINS`

其中 `CORS_ALLOWED_ORIGINS` 使用逗号分隔，例如：

```env
CORS_ALLOWED_ORIGINS=https://your-frontend.vercel.app,http://127.0.0.1:5173
```

## 启动后端

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 文档与测试入口

- Swagger UI：`/docs`
- ReDoc：`/redoc`
- 健康检查：`/health`

## 本地实时对话调试

```powershell
powershell -ExecutionPolicy Bypass -File .\live_chat.ps1
```

## 主要接口

- `GET /health`
- `POST /api/chat/message`
- `POST /api/chat/stream`
- `POST /api/admin/catalog/reload`
- `GET /api/admin/catalog/summary`
- `GET /api/admin/mappings`
- `POST /api/admin/mappings/train`
- `GET /api/admin/mappings/examples`
- `GET /api/admin/chat-logs`
- `GET /api/admin/diagnostics/llm`

## 多轮推荐行为

用户在已有商品卡片后要求“有其他推荐吗”“不要这三款”“换一批”“看看别的”时，后端会进入 `RERANK_AND_RECOMMEND`，并排除 `seen_recommended_codes` / `last_recommended_codes` 中已经展示过的商品，避免把同一组三款再次返回。

当用户明确送男友/男朋友等结构化人群需求时，推荐层会优先只返回 `suitable_people` 包含 `男款` 的商品。若当前预算和品类下男款已经展示完，后端先返回无更多匹配说明；用户随后明确表示“依旧这个预算”“还是这个预算”“预算不变”等继续同预算诉求时，下一轮才会放宽到未标注人群但价位和品类接近的备选款。

## 流式响应稳定性

`POST /api/chat/stream` 使用 SSE 返回 `status` / `delta` / `done`。聊天日志写入失败不会中断用户响应，也不会把正常 `done` 替换成 `stream_fallback`；日志异常只记录在后端日志中。

## 导出部署用货盘

如果后面要部署到 Railway，建议先把超大的 Excel 货盘导出成 `JSON + catalog_media`：

```powershell
.\.venv\Scripts\python.exe .\scripts\export_catalog_bundle.py
```

导出后会生成：
- [products.json](C:\Users\mSunny_Tp\Desktop\金榕珠宝智能体1\backend\data\catalog_bundle\products.json)
- [catalog_media](C:\Users\mSunny_Tp\Desktop\金榕珠宝智能体1\backend\data\catalog_media)

部署时优先配置：

```env
PRODUCT_JSON_PATH=/app/backend/data/catalog_bundle/products.json
```

这样上线时就不必继续直接读取超大 Excel。

## Railway 部署

当前目录已经包含 [railway.json](C:\Users\mSunny_Tp\Desktop\金榕珠宝智能体1\backend\railway.json)。

建议在 Railway 中把服务根目录设为 `backend`，然后配置这些环境变量：

- `LONGCAT_API_KEY`
- `LONGCAT_MODEL`
- `PRODUCT_JSON_PATH`
- `PRODUCT_XLSX_PATH`
- `CORS_ALLOWED_ORIGINS`

启动命令已经由 `railway.json` 提供，不需要再单独填写。
