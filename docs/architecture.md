# 架构

Vue 3 单页应用与 FastAPI API 同源部署。FastAPI 提供构建后的静态前端。独立 Python worker 定时检查到期邀请、写入历史并投递通知。两进程连接同一数据库，部署时先运行 Alembic。数据库时间统一保存为 Unix 秒，浏览器转换为本地时间。

| 数据表 | 用途 |
| --- | --- |
| users, sessions, account_tokens | Argon2id 哈希、服务端会话、一次性邮箱验证及重置令牌 |
| settings | 站点注册、访客访问、检测间隔 |
| apps, invites | 公共软件与唯一 TestFlight 邀请 |
| check_logs, status_events | 每次检测与状态变化，含未知 |
| subscriptions, channels, deliveries | 用户关注、加密渠道配置和持久化投递队列 |

worker 用数据库条件更新取得租约。状态变化和对应投递记录在同一事务中提交。失败检查归为未知，并保留最近一次明确状态以避免恢复后重复通知。检测间隔受站点设置和失败退避控制。投递使用唯一事件键、有限次数重试和稳定的 Webhook 幂等键；下游已接收但确认丢失时，SMTP 等没有幂等协议的渠道仍可能重复。

初始检测可能落在已开放区间中。统计将这样的区间计作观察区间，不推断开始时刻。开放估计只累计间隔正常、两端均检测到开放的采样；未知或采样中断切断区间。Apple 英文邀请页标记是经验规则，页面结构变化时保守归为未知。样本验证使用 /join/otcFpYFW、/join/tGgrnw91、/join/n3nqcarb 及无效邀请码，实时状态会变化。
