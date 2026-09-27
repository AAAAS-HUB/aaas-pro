# A股多因子智能选股平台 - 部署指南

## 目录结构

```
aaas-pro/
├── main.py              # FastAPI 后端（注册/登录/静态文件服务）
├── requirements.txt      # Python 依赖
├── railway.json         # Railway 部署配置
├── users.db             # SQLite 用户数据库（自动创建，提交后忽略）
├── static/
│   ├── index.html       # 主页面（含完整选股工作台）
│   ├── schedule.html    # 定时任务页面
│   ├── history.html     # 历史结果页面
│   ├── datasource.html  # 数据源监控页面
│   ├── personal.html    # 个人中心页面
│   └── styles.css       # 样式文件
└── README.md            # 本文件
```

---

## 本地测试

```bash
cd aaas-pro
pip install -r requirements.txt
python main.py
# 访问 http://localhost:8000
```

---

## Railway 部署（免费方案）

### 前提
- 注册 [Railway](https://railway.app)（推荐用 GitHub 登录）
- 将 `aaas-pro` 文件夹 Push 到 GitHub 仓库

### 步骤

**1. 创建新 Project**
- 登录 Railway → 点击 **New Project** → **Deploy from GitHub repo**
- 选择你的仓库

**2. 配置环境变量（重要！）**
- 在 Railway 项目面板 → **Variables** → 添加：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `SECRET_KEY` | `你的64位随机密钥` | JWT 签名密钥，安全随机字符串 |
| `PORT` | `8000` | Railway 自动注入，代码已兼容 |

生成随机密钥：
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**3. 域名绑定（可选）**
- Railway 免费版支持临时域名 `yourproject.up.railway.app`
- 绑定自定义域名 `aaas-pro.cn`：
  - Railway 项目 → **Settings** → **Networking** → **Custom Domains**
  - 添加 `aaas-pro.cn`，按提示配置 DNS

**4. 部署**
- Railway 会自动检测 `railway.json` 并执行构建
- 约 1~2 分钟后上线

---

## API 接口说明

| 接口 | 方法 | 说明 | 认证 |
|------|------|------|------|
| `/api/auth/register` | POST | 注册（用户名/邮箱/密码） | 否 |
| `/api/auth/login` | POST | 登录 | 否 |
| `/api/auth/me` | GET | 当前登录用户信息 | 需要 |
| `/api/auth/logout` | POST | 退出登录 | 需要 |
| `/api/health` | GET | 健康检查 | 否 |

**认证方式**：`Authorization: Bearer <token>` 请求头

---

## 功能说明

- 注册后自动登录，JWT Token 存储在 localStorage
- 7天有效期，过期需重新登录
- SQLite 数据库（users.db）在服务器持久化（Railway 磁盘持久化需另购，或用 Railway Postgres）
- 前端所有页面均为静态 HTML，FastAPI 直接服务

---

## 数据库（可选升级）

当前使用 SQLite，适合小规模（<1000用户）。如需生产级：
- Railway 提供免费 PostgreSQL 插件
- 修改 `DATABASE_URL` 环境变量
- 将 `main.py` 中的 `sqlite3` 替换为 `asyncpg` + SQLAlchemy
