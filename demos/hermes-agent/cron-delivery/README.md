# Hermes Agent — cron-delivery

## 目标

用最简代码复现 Hermes 的 cron 调度路径：**fresh session 执行任务 + skill 注入 + 跨平台 delivery**。

## 原理

Hermes 的 cron 任务不是把旧 session 直接拉起来继续跑，而是为每个 job 启动 fresh session。这样定时任务不会污染用户当前对话，也更适合“每天汇报”“夜间巡检”“无人值守修复建议”这类自治执行。

任务完成后，Hermes 还能把结果送回任意平台入口，例如 Telegram、Slack、邮件或 Home Assistant。于是调度层和通道层被统一到同一个 agent runtime 下。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/cron-delivery/
├── README.md
├── cron_delivery.py
└── main.py
```

## 关键代码解读

```python
def execute(self, job: CronJob) -> str:
    fresh_session_id = f"cron::{job.job_id}"
    result = self.agent_run(job.prompt, job.injected_skills)
    return self.router.send(job.delivery_platform, job.delivery_target, f"[{fresh_session_id}] {result}")
```

这里保留了 Hermes cron 的三个关键点：
- 每次 job 都进入 fresh session
- job 可以携带 skills
- 结果走统一 delivery router 返回到外部平台

## 与原实现的差异

- 原版有真正的 scheduler/tick/jobs.json；demo 只演示单个 job 执行路径
- 原版支持更复杂的 pre-script、失败重试和更多 delivery 目标；demo 只保留主干
- 原版 job 的执行目标是真实 `AIAgent`；demo 用 `fake_agent_run()` 模拟

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `cron/`, `gateway/run.py`
