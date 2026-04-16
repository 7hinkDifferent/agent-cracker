# Hermes Agent — terminal-multibackend

## 目标

用最简代码复现 Hermes 的统一 terminal 抽象：**local / docker / ssh / modal / daytona / singularity** 走同一套工具接口。

## MVP 角色

这是 Hermes MVP 中的**执行环境抽象层**。模型只需要学会调用一个 terminal 工具，具体落到哪个执行后端由 runtime 决定。

## 原理

Hermes 的 terminal 工具不是固定绑在本机 shell 上。它会根据当前配置、平台入口或任务类型，把同一条“运行命令”能力映射到本地 shell、Docker 容器、SSH 远端、Modal 沙箱、Daytona dev environment、Singularity 容器等不同后端。

这种设计的价值在于：模型侧的工具 schema 不变，但运行环境可以替换。也就是说，agent 的 reasoning 与 tool calling 保持稳定，真正变化的是底层 transport 和隔离方式。

## 运行

```bash
uv run python main.py
```

## 文件结构

```text
demos/hermes-agent/terminal-multibackend/
├── README.md
├── main.py
└── terminal_backends.py
```

## 关键代码解读

```python
self.backends = {
    "local": LocalBackend(),
    "docker": MockRemoteBackend("docker", "container"),
    "ssh": MockRemoteBackend("ssh", "remote-host"),
    "modal": MockRemoteBackend("modal", "serverless-sandbox"),
    ...
}
```

Hermes 的关键点不在于某个具体 backend，而在于**同一种 tool schema 背后可以挂多种 backend**。demo 里只有 local 真正执行 shell，其余后端用 mock 表示隔离环境，但接口保持一致。

## 与原实现的差异

- 原版 terminal backend 还有更复杂的连接管理、工作目录同步、环境变量与输出流处理；demo 仅保留统一接口
- 原版部分 backend 会涉及容器镜像、认证与远程会话复用；demo 用静态 mock 输出代替
- 原版与 approval / execute_code / gateway session 有联动；本 demo 只关注 terminal 抽象本身

## 相关文档

- 分析文档: [docs/hermes-agent.md](../../../docs/hermes-agent.md)
- 原项目: https://github.com/NousResearch/hermes-agent
- 基于 commit: `722331a`
- 核心源码: `tools/terminal_tool.py`
