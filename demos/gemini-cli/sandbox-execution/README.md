# Sandbox Execution

## 目标

复现 Gemini CLI 的沙箱隔离执行机制，通过容器化或进程隔离限制工具的资源和文件系统访问。

## 原理

Gemini CLI 支持可选的沙箱隔离执行，防止恶意或错误的工具调用损害宿主系统：

1. **沙箱层次**：
   - **进程隔离** — 在独立进程中运行工具（启用 ulimits，RLIMIT_*）
   - **容器隔离** — 使用 Docker/Podman 容器（完整的文件系统隔离）
   - **网络隔离** — 限制出站网络连接

2. **资源限制**：
   - **CPU** — 最多 N 秒执行时间（超时则杀掉进程）
   - **内存** — 限制进程可用内存（防止内存泄漏）
   - **磁盘** — 限制可写入的目录和磁盘大小
   - **进程数** — 限制创建的子进程数

3. **挂载管理**：
   - **只读挂载** — 代码库和配置文件只读
   - **读写挂载** — 工作目录和临时文件目录可写
   - **隔离挂载** — 工具无法访问 `/etc`、`/root` 等敏感目录

4. **命令改写**：
   ```
   原始命令：git clone https://repo.git
   改写后：  git --git-dir=/tmp/xyz clone https://repo.git
   
   防止：
   - 不需要的网络访问
   - 创建持久化数据
   - 访问宿主的 git config
   ```

## 运行

```bash
cd demos/gemini-cli/sandbox-execution/
uv run --with pydantic main.py
```

## 文件结构

```
sandbox-execution/
├── README.md          # 本文件
└── main.py            # 沙箱隔离执行实现 (~380 行)
```

## 关键代码解读

### 1. 沙箱配置
```python
class SandboxConfig:
    """沙箱隔离的配置"""
    isolation_mode: IsolationMode  # 进程/容器/网络
    cpu_timeout_sec: int          # 执行超时
    memory_limit_mb: int          # 内存限制
    disk_limit_mb: int            # 磁盘限制
    allowed_mounts: List[Mount]   # 允许的文件系统挂载
    command_rewrite_rules: List    # 命令改写规则
```

### 2. 资源限制管理
```python
class ResourceLimiter:
    """通过 setrlimit 或容器 API 限制资源"""
    
    async def apply_limits(self, config: SandboxConfig):
        # setrlimit(RLIMIT_CPU, cpu_timeout_sec)
        # setrlimit(RLIMIT_AS, memory_limit_mb * 1024 * 1024)
        # 超时通过 signal.alarm() 或 asyncio.wait_for() 实现
```

### 3. 命令改写规则
```python
class CommandRewriteRule:
    """防止工具执行不安全的操作"""
    pattern: str      # e.g., "^rm" -> "禁止 rm"
    action: str       # "BLOCK" | "REWRITE" | "ALLOW"
    rewrite_to: str   # 改写后的命令（可选）
```

### 4. 容器化执行（Docker 示例）
```python
async def execute_in_sandbox(tool_name: str, params: Dict) -> str:
    """
    通过 Docker 容器执行工具：
    
    1. 创建临时容器
    2. 挂载允许的目录（只读 /repo，读写 /tmp）
    3. 设置资源限制（--cpus，--memory）
    4. 执行命令
    5. 收集输出
    6. 清理容器
    """
    container = await docker_client.create_container(
        image="tool-sandbox:latest",
        mounts=[
            Mount(source="/repo", target="/repo", read_only=True),
            Mount(source="/tmp", target="/tmp", read_only=False),
        ],
        resources=ResourceConfig(
            cpu_limit=1.0,
            memory_limit=512*1024*1024,
        ),
        timeout=config.cpu_timeout_sec,
    )
```

## 与原实现的差异

| 特性 | 原实现 | Demo |
|------|--------|------|
| 隔离方式 | Docker/Podman + 进程隔离 | 进程隔离（setrlimit）+ 命令白名单 |
| 资源限制 | cgroup v2 + kernel limits | Python signal + asyncio.wait_for |
| 网络隔离 | Docker 网络命名空间 | iptables/netfilter 模拟 |
| 文件系统 | chroot + overlayfs | 路径前缀检查 |
| 命令改写 | 完整的命令行解析 | 正则表达式模式匹配 |

## 相关文档

- 基于 commit: [`0c91985`](https://github.com/google-gemini/gemini-cli/tree/0c919857fa5770ad06bd5d67913249cd0f3c4f06)
- 核心源码: `packages/core/src/tools/sandbox.ts`，`packages/core/src/tools/invocation.ts`
- 相关维度: D3（工具系统 - 执行阶段）
- 配套 Demo: [tool-registry-system](../tool-registry-system/) (D3), [message-bus-confirmation](../message-bus-confirmation/) (进阶)
