# Demo: eigent — trigger-webhook

## 目标

用最简代码复现 eigent 的 **触发器系统** — Webhook/Slack/Cron 三种外部事件驱动 Agent 任务执行的机制。

## 平台角色

**通道层 + 自治层**（D9/D11）— 触发器是 eigent 平台从被动响应到主动自治的关键机制。Webhook 让外部系统（GitHub、CI/CD）触发 Agent 任务，Cron 实现定时巡检和报告生成，Slack 打通团队协作通道。三种触发器共享统一的执行模型和速率限制。

## 原理

Eigent 的触发器系统分三层：

1. **触发器模型**（`trigger.py`）：`Trigger` 数据模型包含 id、name、type、status、webhook_url、config。每种类型有不同的 config 字段（cron_expression、slack_channel、headers）
2. **CRUD 管理**（`trigger_controller.py`）：创建时检查速率限制（每用户/每项目最大数量），自动生成 webhook_url 和 secret
3. **执行处理**：
   - Webhook：`webhook_controller.py` 验证触发器状态 → 速率限制检查 → 创建 `TriggerExecution` → 异步启动 Agent 任务
   - Cron：Celery Beat 定时扫描活跃的 cron 触发器，匹配时间表达式则触发执行
   - Slack：Slack Bot 接收命令后调用相同的执行流程

## 运行

```bash
cd demos/eigent/trigger-webhook
uv run python main.py
```

无需 API key — 此 demo 不调用 LLM，完全模拟触发和调度流程。

## 文件结构

```
demos/eigent/trigger-webhook/
├── README.md           # 本文件
└── main.py             # TriggerType/Trigger/TriggerExecution/RateLimiter/TriggerManager
```

## 关键代码解读

### handle_webhook() — Webhook 处理流程

```python
def handle_webhook(self, trigger_id, payload):
    trigger = self.triggers.get(trigger_id)       # 1. 查找
    if trigger.status != TriggerStatus.ACTIVE:    # 2. 验证状态
        return error
    ok, msg = self.rate_limiter.check_execution_limit()  # 3. 速率限制
    execution = TriggerExecution(trigger_id, payload)     # 4. 创建执行记录
    execution.status = "running"                  # 5. 启动任务
```

### RateLimiter — 多维速率限制

```python
class RateLimiter:
    MAX_PER_USER = 10              # 每用户最大触发器数
    MAX_PER_PROJECT = 5            # 每项目最大触发器数
    MAX_EXECUTIONS_PER_MINUTE = 30 # 每分钟最大执行数
```

### Cron 调度

```python
def run_cron_check(self, current_minute):
    for trigger in cron_triggers:
        if matches_cron_expression(trigger.config.cron_expression, current_minute):
            self.handle_webhook(trigger.id, {"source": "cron"})
```

## 与原实现的差异

| 方面 | 原实现 | Demo |
|------|--------|------|
| 存储 | PostgreSQL + SQLAlchemy ORM | 内存 dict |
| Cron 调度 | Celery Beat + Redis 消息队列 | 简化的整除匹配 |
| Webhook 验证 | HMAC 签名 + secret 校验 | 仅检查触发器存在和状态 |
| 任务创建 | 异步调用 TaskService.create_task() | 模拟创建 task_id |
| Slack 集成 | Slack Bot SDK + OAuth | 仅定义类型 |
| 速率限制 | Redis 滑动窗口 | 内存时间戳列表 |

**保留的核心**：三种触发器类型、Trigger/TriggerExecution 数据模型、多维速率限制（用户/项目/执行频率）、Webhook 验证-执行流程、Cron 定时扫描。

## 相关文档

- 分析文档: [docs/eigent.md](../../../docs/eigent.md)
- 原项目: https://github.com/eigent-ai/eigent
- 基于 commit: `38f8f2b`
- 核心源码: `server/app/controller/trigger/trigger_controller.py`, `server/app/controller/trigger/webhook_controller.py`
