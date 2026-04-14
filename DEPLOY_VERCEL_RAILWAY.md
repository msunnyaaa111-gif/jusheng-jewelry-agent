# 钜盛珠宝智能体试运营上线说明

这套项目适合先用：
- 前端：Vercel
- 后端：Railway

这样可以先不买域名，直接用平台默认域名对外试用。

## 一、后端部署到 Railway

1. 把代码仓库上传到 GitHub。
2. 在 Railway 新建项目，选择该仓库。
3. 把服务根目录设置为 `backend`。
4. 配置环境变量：

```env
LONGCAT_API_KEY=你的新 key
LONGCAT_MODEL=LongCat-Flash-Chat
PRODUCT_JSON_PATH=/app/backend/data/catalog_bundle/products.json
CORS_ALLOWED_ORIGINS=https://你的前端域名.vercel.app
```

5. 部署完成后，记录 Railway 给你的公网地址，例如：

```text
https://your-backend.up.railway.app
```

6. 打开以下地址确认上线成功：

- `https://your-backend.up.railway.app/health`
- `https://your-backend.up.railway.app/docs`

## 二、前端部署到 Vercel

1. 在 Vercel 新建项目，选择同一个仓库。
2. 把项目根目录设置为 `frontend`。
3. 配置环境变量：

```env
VITE_API_BASE_URL=https://your-backend.up.railway.app
```

4. 部署完成后，Vercel 会给你一个默认地址，例如：

```text
https://your-frontend.vercel.app
```

## 三、上线后验证

依次检查：

1. 打开前端页面，确认能正常进入聊天页。
2. 输入简单开场白，确认能正常追问。
3. 输入一个完整需求，确认能正常返回 3 张卡片和购买建议。
4. 点击商品图片，确认能打开大图。

## 四、当前要注意的一个现实问题

现在货盘 Excel 文件体积很大，如果后面要长期稳定上线，建议尽快把 Excel 数据转成：

- 数据库
或
- 预处理后的 JSON / CSV

这样会比直接带着大 Excel 上平台更稳，也更容易扩容。

当前项目已经支持先导出为：
- `backend/data/catalog_bundle/products.json`
- `backend/data/catalog_media/`

建议上线前先在本地执行一次：

```powershell
cd C:\Users\mSunny_Tp\Desktop\金榕珠宝智能体1\backend
.\.venv\Scripts\python.exe .\scripts\export_catalog_bundle.py
```
