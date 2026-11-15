# Cloudflare 橙云后的访客 IP

适用于 **Cloudflare → Nginx → TFWatch API 容器**，其中宿主机或容器中的 Nginx 直接接收 Cloudflare 边缘服务器连接。Cloudflare Tunnel、负载均衡器或其他前置代理会改变 Nginx 看到的连接地址，需要按实际链路确认可信代理。

## Nginx

1. 将 [nginx-realip.conf](nginx-realip.conf) 放到 Nginx 容器可读取的位置，在 TFWatch 的 `server` 块中用 `include` 引入。它只从 [Cloudflare 公布的 IPv4 和 IPv6 网段](https://www.cloudflare.com/ips/)接受 `CF-Connecting-IP`。Cloudflare 更新网段后同步这个文件。
2. 在现有反代 TFWatch 的 `location` 中替换对应的 `proxy_set_header` 指令，或引入 [nginx-proxy-headers.conf](nginx-proxy-headers.conf)。保留现有 `proxy_pass`、证书和其他自定义请求头。`X-Forwarded-For` 应由 `$remote_addr` 覆盖，避免把访客提交的转发链传给应用。每个头在同一个 `location` 保留一条设置。

   ```nginx
   # Inside the existing server block
   include /etc/nginx/snippets/tfwatch-cloudflare-realip.conf;

   # Inside the existing location that proxies to TFWatch
   include /etc/nginx/snippets/tfwatch-proxy-headers.conf;
   ```

3. 宿主机上的 Nginx 用 `sudo nginx -t && sudo systemctl reload nginx` 检查并重载。如果 Nginx 在容器里，执行 `docker exec <nginx容器> nginx -t`，通过后用 `docker exec <nginx容器> nginx -s reload` 重载。橙云启用 HTTPS 时，确保 Nginx 的 HTTPS 虚拟主机和证书已就绪，使用 Cloudflare 的 Full (strict) 源站加密模式。

## TFWatch Compose

将 [compose.override.yaml](compose.override.yaml) 放到服务器上与 `compose.yaml` 同级。如果该目录已有 override，只合并 `services.api.command`。在同目录 `.env` 写入 `TFWATCH_NGINX_TRUSTED_IP`，值为 **API 容器实际看到的 Nginx 连接源地址**。

- 宿主机 Nginx 通过 `proxy_pass http://127.0.0.1:8000` 访问 Docker 发布端口时，以 API 日志观察到的直接连接地址为准。例如 Docker 网关为 `172.18.0.1` 且 API 日志显示该地址时，填写 `TFWATCH_NGINX_TRUSTED_IP=172.18.0.1`。保留 `HOST_BIND=127.0.0.1`。重建 Docker 网络后重新核对网关地址。
- 如果 Nginx 和 API 都在共用 Docker 网络且直连，可用以下命令查看 Nginx 所在各网络的地址，并在 Nginx 的部署配置中固定两服务共用网络上的地址。

```sh
docker inspect --format '{{range $name, $net := .NetworkSettings.Networks}}{{println $name $net.IPAddress $net.GlobalIPv6Address}}{{end}}' <nginx容器>
```

使用具体地址，避免 `*` 或允许其他工作负载访问 API 的整个网段。API 端口保持在本机或私有容器网络，公网请求走 Nginx。然后检查 Compose 合并结果并重建 API 容器。

```sh
docker compose config --quiet
docker compose up -d --no-deps --force-recreate api
docker compose logs --tail=30 api
```

确认公网域名的 `/api/health` 返回成功。从两个不同的外网请求同一路径，检查 API 访问日志是否分别记录各自的访客地址。通过未经 Cloudflare 的测试连接带上伪造的 `CF-Connecting-IP` 和 `X-Forwarded-For` 时，日志应继续显示连接的真实来源。验证时可以使用 `/api/health`，无需尝试失败登录。

TFWatch 的登录限流分别按客户端 IP 与邮箱计数。代理配置修复后，不同来源 IP 使用独立的 IP 额度，同一邮箱仍共用账号额度。
