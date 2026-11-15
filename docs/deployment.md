# Debian / systemd 部署

需要 Python 3.14（含 venv）和 Node.js 24。以下命令假定源代码放在 `/opt/tfwatch`。

```sh
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin tfwatch
sudo install -d -o tfwatch -g tfwatch -m 0750 /var/lib/tfwatch
cd /opt/tfwatch
python3.14 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)
sudo install -m 0600 -o root -g root .env.example /etc/tfwatch.env
cd backend
../.venv/bin/python -m tfwatch.cli key
```

编辑 `/etc/tfwatch.env`，将生成值填入 `ENCRYPTION_KEY`，设置 `DATABASE_URL=sqlite:////var/lib/tfwatch/tfwatch.db`，并将 `PUBLIC_URL` 改为你的 HTTPS 站点地址。也可填写 PostgreSQL 连接串和 SMTP 设置。保留同一密钥供 API 和 worker 使用。

```sh
sudo sh -c 'set -a; . /etc/tfwatch.env; set +a; cd /opt/tfwatch/backend; exec runuser -u tfwatch -- /opt/tfwatch/.venv/bin/python -m alembic upgrade head'
sudo sh -c 'set -a; . /etc/tfwatch.env; set +a; cd /opt/tfwatch/backend; exec runuser -u tfwatch -- /opt/tfwatch/.venv/bin/python -m tfwatch.cli create-admin admin@example.org'
sudo install -m 0644 /opt/tfwatch/deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tfwatch-api tfwatch-worker
curl -f http://127.0.0.1:8000/api/health
```

文件会由 systemd 和上述 shell 命令读取。值包含空格或特殊字符时使用兼容的单引号写法。反代示例（Caddyfile）：

```caddy
tfwatch.example.org {
    reverse_proxy 127.0.0.1:8000
}
```

文件 `frontend/dist/tfwatch-source.tar.gz` 可存放当前部署版本的完整对应源码，或设置 `SOURCE_URL` 指向该版本源码。调整代理拓扑时，只让可信代理传递客户端地址。

## 更新与恢复

- Compose 更新前备份数据库，停止 API 和 worker，并用新版本执行 `docker compose build migrate`。再运行 `docker compose up -d --force-recreate migrate` 与 `docker compose wait migrate`，迁移成功后运行 `docker compose up -d --force-recreate api worker`。
- systemd 更新前备份数据，停止两项服务，更新源码，重新安装依赖、构建前端并执行同一条迁移命令，最后启动两项服务。
- SQLite 在停机后复制数据库和同目录仍存在的 WAL 辅助文件；在线备份使用 SQLite 的备份接口。PostgreSQL 使用 `pg_dump`。同时安全保留环境文件中的加密密钥，换密钥后已有渠道凭据将无法解密。
- 通过 `docker compose logs -f api worker` 或 `journalctl -u tfwatch-api -u tfwatch-worker` 检查运行状态。SMTP 需要 STARTTLS 或 TLS。Webhook 和 ntfy 用户目标必须使用 HTTPS，解析到任何非公网 IP 的目标会被拒绝，且请求不会跟随重定向。
- 默认保留检测历史。检测量较大时请监控数据库空间及 worker 调度延迟。单个通知下游即使接收成功，若确认应答丢失，也可能在重试时收到重复通知。
