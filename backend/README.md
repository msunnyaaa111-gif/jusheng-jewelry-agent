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
