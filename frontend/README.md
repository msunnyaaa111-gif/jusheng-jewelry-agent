# 钜盛珠宝智能体前端

这是对接现有后端接口的 H5 聊天前端，默认使用：
- `/api/chat/stream` 做流式回复
- `/health` 做后端连通性检查
- `/static` 加载商品图片或二维码

## 启动开发环境

```bash
npm install
npm run dev
```

默认访问地址：

```text
http://127.0.0.1:5173
```

## 构建生产包

```bash
npm run build
```

构建产物在：

```text
dist/
```

## 环境变量

复制 [frontend/.env.example](C:\Users\mSunny_Tp\Desktop\金榕珠宝智能体1\frontend\.env.example) 为 `.env` 或 `.env.production`：

```env
VITE_API_BASE_URL=https://your-backend.up.railway.app
```

本地开发如果继续使用 Vite 代理，可以保持为空。

## Vercel 部署

建议在 Vercel 中把项目根目录设为 `frontend`，并配置环境变量：

- `VITE_API_BASE_URL`

填写时指向已经部署好的后端地址，例如：

```env
VITE_API_BASE_URL=https://your-backend.up.railway.app
```
