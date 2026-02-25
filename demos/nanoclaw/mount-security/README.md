# Demo: NanoClaw — Mount Security

## 目标

用最简代码复现 NanoClaw 的挂载安全校验系统：外部 allowlist + 阻止列表 + symlink 解析 + 权限分级。

## 平台机制角色

挂载安全是 NanoClaw 容器隔离的关键补充——Docker 容器的安全边界由 mount 决定，而 mount 的合法性由本模块校验。核心设计：**安全配置存放在项目目录外**（`~/.config/nanoclaw/mount-allowlist.json`），容器内的 agent 无法修改安全策略，实现"配置不可篡改"。

## 原理

NanoClaw 在启动容器前，对用户请求的额外挂载路径执行 5 层校验：

```
validateMount(hostPath, groupName, isMain)
 ├─ 1. Allowlist 存在？    → 不存在则全部拒绝（fail-closed）
 ├─ 2. 路径解析             → expanduser + resolve(strict=True)
 ├─ 3. 阻止列表匹配？      → .ssh/.gnupg/.aws/.env 等 16+ 模式
 ├─ 4. 在允许的根目录下？   → symlink 解析后的真实路径 vs allowedRoots
 └─ 5. 读写权限             → nonMainReadOnly 强制非 main 组只读
```

**关键设计决策**：
- **Fail-closed**: 没有 allowlist 文件时，所有额外挂载被拒绝
- **Symlink 先解析**: 路径先通过 `resolve()` 解析 symlink，再检查是否在允许范围内，防止 symlink 穿越攻击
- **模式合并**: 用户自定义的 blockedPatterns 与默认 16 个模式合并（不替换）
- **缓存**: allowlist 加载后缓存在内存中，进程生命周期内只读一次

## 运行

```bash
cd demos/nanoclaw/mount-security
uv run python main.py
```

无需外部依赖，使用 tempfile 创建临时目录和 symlink，运行后自动清理。

## 文件结构

```
demos/nanoclaw/mount-security/
├── README.md       # 本文件
├── security.py     # 可复用模块: BLOCKED_PATTERNS + allowlist 加载 + 校验逻辑
└── main.py         # Demo 入口: 5 个场景演示（从 security.py import）
```

## 关键代码解读

### 阻止列表模式匹配

```python
BLOCKED_PATTERNS = [
    ".ssh", ".gnupg", ".gpg", ".aws", ".azure", ".gcloud",
    ".kube", ".docker", "credentials", ".env", ".netrc",
    ".npmrc", ".pypirc", "id_rsa", "id_ed25519", "private_key", ".secret",
]

def _matches_blocked_pattern(real_path, patterns):
    parts = Path(real_path).parts
    for pattern in patterns:
        for part in parts:
            if part == pattern or pattern in part:
                return pattern  # 匹配到，返回命中的模式
    return None
```

### Symlink 解析防穿越

```python
# Expand and resolve -- follows symlinks (Rule 4)
expanded = _expand_path(host_path)       # ~/projects -> /home/user/projects
real_path = str(Path(expanded).resolve(strict=True))  # symlink -> real target

# Check against allowed roots using RESOLVED path, not original
root = _find_allowed_root(real_path, allowlist.allowed_roots)
if root is None:
    return DENY  # Symlink target is outside allowed roots
```

### nonMainReadOnly 权限分级

```python
# Rule 5: Determine effective readonly
effective_readonly = True  # Default: read-only
if root.allow_read_write:
    if not is_main and allowlist.non_main_read_only:
        effective_readonly = True   # Non-main forced read-only
    else:
        effective_readonly = False  # Main group gets read-write
```

### 外部 Allowlist 格式

```json
{
  "allowedRoots": [
    { "path": "~/projects", "allowReadWrite": true, "description": "Dev projects" },
    { "path": "~/docs", "allowReadWrite": false, "description": "Read-only docs" }
  ],
  "blockedPatterns": ["password", "token"],
  "nonMainReadOnly": true
}
```

## 与原实现的差异

| 方面 | 原实现 | 本 Demo |
|------|--------|---------|
| 语言 | TypeScript | Python |
| 日志 | pino (structured logging) | print 输出 |
| 容器路径 | `isValidContainerPath()` 校验 + `/workspace/extra/` 前缀 | 省略（聚焦 host 路径校验） |
| 模板生成 | `generateAllowlistTemplate()` 生成模板 | 省略 |
| 配置路径 | 硬编码 `~/.config/nanoclaw/mount-allowlist.json` | 参数化（方便测试） |
| 缓存 | 模块级变量 + null 双重检查 | 同样用模块级变量 + `clear_cache()` |
| 路径扩展 | `expandPath()` 手动处理 `~/` | `Path.expanduser()` |
| 真实路径 | `fs.realpathSync()` | `Path.resolve(strict=True)` |

## 相关文档

- 分析文档: [docs/nanoclaw.md](../../../docs/nanoclaw.md) — Dimension 11 安全模型
- 原项目: https://github.com/qwibitai/nanoclaw
- 基于 commit: `bc05d5f`
- 核心源码: `src/mount-security.ts` (419 行)
