import http.client
import ipaddress
import json
import re
import socket
import ssl
from urllib.parse import urlsplit


def https_target(url):
    if not url or len(url) > 1500 or not url.isascii() or re.search(r"[\\\s\x00-\x1f\x7f]", url):
        raise ValueError("请输入有效的 HTTPS 地址")
    parts = urlsplit(url)
    if (parts.scheme != "https" or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.fragment or "%" in parts.netloc):
        raise ValueError("请输入有效的 HTTPS 地址")
    return parts.hostname, parts.port or 443, parts.path or "/", parts.query


def publicly_routable(value):
    ip = ipaddress.ip_address(value)
    if not ip.is_global or ip.is_multicast or ip.is_reserved:
        return False
    if ip.version == 6:
        return (ip in ipaddress.ip_network("2000::/3")
                and ip not in ipaddress.ip_network("2001::/23")
                and ip not in ipaddress.ip_network("2002::/16"))
    return True


def resolve_public(host, port):
    addresses = list(dict.fromkeys(result[4][0] for result in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    )))
    if not addresses or not all(publicly_routable(address) for address in addresses):
        raise ValueError("目标地址不可用")
    return addresses


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, port, addresses):
        super().__init__(host, port, timeout=6, context=ssl.create_default_context())
        self.addresses = addresses

    def connect(self):
        error = OSError("连接失败")
        for address in self.addresses[:2]:
            try:
                raw = socket.create_connection((address, self.port), self.timeout)
                try:
                    self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                except OSError:
                    raw.close()
                    raise
                return
            except OSError as failure:
                error = failure
        raise error


def post_json(url, payload, headers=None):
    host, port, path, query = https_target(url)
    connection = PinnedHTTPS(host, port, resolve_public(host, port))
    try:
        connection.request("POST", path + ("?" + query if query else ""),
                           body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                           headers={"Content-Type": "application/json", **(headers or {})})
        response = connection.getresponse()
        if not 200 <= response.status < 300:
            raise ValueError("通知服务拒绝请求")
    finally:
        connection.close()
