# TFWatch

自托管的 Apple TestFlight 公开邀请监控。搜索公共软件库，查看开放时间线，并通过自己的邮件、Telegram、ntfy 或 Webhook 接收名额提醒。

## Docker Compose

需要 Docker Engine 与 Compose 插件。在项目根目录执行：

```sh
cp .env.example .env
chmod 600 .env
docker compose build migrate
docker compose run --rm --no-deps migrate python -m tfwatch.cli key
```

将最后一条命令生成的密钥填入 `.env` 的 `ENCRYPTION_KEY`。设定站点的 `PUBLIC_URL`，如 `https://tfwatch.example.org`，再执行：

```sh
docker compose up -d migrate
docker compose wait migrate
docker compose run --rm --no-deps migrate python -m tfwatch.cli create-admin admin@example.org
docker compose up -d api worker
docker compose ps
```

默认本机地址为 `http://localhost:8000`。反向代理应指向 `127.0.0.1:8000` 并提供 HTTPS。管理员登录后可独立关闭新用户注册和访客浏览。第一次提交邀请后，worker 会自动检测。首次检测前显示「待检测」。

Docker 默认使用 SQLite 和命名卷 `tfwatch-data`。使用 PostgreSQL 时，先建立数据库及专用用户，再将 `DATABASE_URL` 设为 `postgresql+psycopg://user:password@db.example.org:5432/tfwatch?sslmode=require`，并确保容器可以连接。用户名或密码含特殊字符时使用 URL 百分号编码。

## 原生 Linux

Debian / systemd 部署、更新与备份见 [部署文档](docs/deployment.md)。环境配置见 [.env.example](.env.example)。

## 通知

- 邮件使用站点 SMTP。用户在账号设置验证自己的邮箱后，可启用邮件渠道或找回密码。
- Telegram 使用你自己的 Bot Token 和 Chat ID。先在 Telegram 内启动该机器人或将它添加到目标聊天。
- ntfy 填写公开可访问的 HTTPS 服务地址及主题，可选填 Bearer Token。
- Webhook 接收 HTTPS POST JSON。常规通知含 `event`、`code`、`status`、`name`、`checked_at`、`url`、`title` 与 `message`。重试沿用相同的 `Idempotency-Key`，接收方可据此去重。
- 关注从已检测到的状态开始显示。之后可选择仅在检测到开放时提醒，或接收其他明确状态变化。投递失败最多尝试五次。

## 本地开发

Python 3.14 和 Node.js 24 是 CI 使用的版本。以下命令适用于 POSIX shell。Windows 上使用 `.venv\Scripts\python.exe`，并用 PowerShell 的 `$env:变量名 = '值'` 方式设置环境变量。

```sh
python -m venv .venv
cd backend
../.venv/bin/python -m pip install -r requirements-dev.txt
../.venv/bin/python -m pytest
../.venv/bin/python -m alembic upgrade head
export ENCRYPTION_KEY="$(../.venv/bin/python -m tfwatch.cli key)"
../.venv/bin/python -m tfwatch.cli create-admin admin@example.org
../.venv/bin/python -m uvicorn tfwatch.main:app --reload
```

另开终端，在 `frontend` 运行 `npm ci`、`npm test` 及 `npm run dev`。Vite 会将 `/api` 转发给 FastAPI。需要检测时，在继承相同 `DATABASE_URL` 与 `ENCRYPTION_KEY` 的终端内，从 `backend` 运行 `../.venv/bin/python -m tfwatch.worker`。生产前端构建命令为 `npm run build`。

## 数据与许可证

时间线展示 TFWatch 的检测时间。时长由相邻开放采样估计，未知和采样中断会打断估计。Apple 可为邀请设置设备等条件，能否加入以 TestFlight 为准。

代码按 [GNU AGPL v3.0](LICENSE) 发布，即 `AGPL-3.0-only`。Docker 默认提供构建对应的源码归档。自行部署修改版时，请提供相应源码，可设置 `SOURCE_URL` 指向与你部署版本相符的源码。TFWatch 与 Apple 无隶属关系。
