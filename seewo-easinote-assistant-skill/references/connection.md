# 希沃 MCP 连接与排障

仅在连接客户端或排障时读取。不要加载新建课件的内容和视觉规划。

## 日常入口

```powershell
python scripts/lifecycle/ensure_connected.py
```

该入口幂等完成：检查希沃进程、必要时检测安装并启动、探测可用 MCP 端点、确认 `tools/list` 非空、注册连接配置，并启动退出监控。已经就绪时直接返回。

只有真正访问客户端时才运行连接流程。讨论内容、规划课件和本地 `--validate-only` / `--dry-run` 不要求先连接。

## 就绪判定

依次区分：

1. 希沃进程未运行；
2. 本地端口不可达；
3. MCP 端点可达但工具尚未就绪；
4. `tools/list` 返回非空，连接可用。

只有第 4 种状态可以注册并进入客户端操作。端口可达不等于已登录或已就绪。

若客户端未安装，停止自动流程并引导用户访问 [希沃白板官网](https://easinote.seewo.com)。若端点持续不可用，请用户在客户端完成登录或启用 MCP 后重试；不要反复写配置。

## 分步诊断

只有日常入口失败时才使用：

```powershell
python scripts/lifecycle/lifecycle.py process
python scripts/lifecycle/lifecycle.py detect
python scripts/lifecycle/lifecycle.py show
python scripts/lifecycle/lifecycle.py probe --wait 30 --interval 2 --require-tools
python scripts/lifecycle/lifecycle.py config --status
```

诊断含义：

- `process`：判断客户端进程是否存在；
- `detect`：仅在进程不存在时查找安装；
- `show`：仅用于刚启动但窗口不可见的客户端，不强制打断已运行客户端；
- `probe`：探测候选端口并验证 MCP 工具列表；
- `config --status`：检查本 skill 的连接配置，不修改其他服务。

默认候选端口为 `7916 / 7917 / 13247 / 19463 / 27733`，实际端口必须实时探测，不能写死。端点格式为 `http://127.0.0.1:{port}/mcp`。

## 配置与清理

连接配置位于 `~/.workbuddy/mcp.json`，服务键固定为 `seewo-easinote-assistant-skill`。脚本只增删该键，不覆盖其他 MCP 服务。

新增连接后，若宿主要求信任，请用户在连接器管理页授权。脚本不能把“配置已写入”误报为“宿主已信任”。

`ensure_connected.py` 会启动 `monitor_seewo.py`。客户端完全退出后，监控器只删除仍指向它启动时 URL 的本服务配置，避免旧监控误删新连接。需要手动清理时运行：

```powershell
python scripts/lifecycle/lifecycle.py config --remove
```

配置 JSON 无效或 `mcpServers` 结构异常时必须失败关闭，不覆盖原文件。

## 常见问题

| 现象 | 处理 |
|---|---|
| 检测不到安装 | 确认安装位置；无法自动定位时由用户选择客户端，不猜测可执行文件 |
| 全部端口失败 | 等待客户端启动完成，确认登录和 MCP 开关，再有限重试 |
| 端点可达但无工具 | 客户端服务未就绪，不注册配置 |
| 配置存在但宿主不可用 | 检查连接器信任状态 |
| 客户端退出后配置残留 | 手动执行 `config --remove` 并检查监控是否启动 |
| 多个同名课件或 shell | 停止并让用户确认目标，不自动选择最近项替代；新建课件重导入仅可自动关闭唯一精确同名 shell，并须确认其已消失 |

## 操作边界

- 仅支持 Windows 希沃白板客户端。
- 连接脚本只依赖 Python 标准库。
- 新建课件正式路径为原生 ENBX；连接能力不授权改走 PPTX 导入。
- MCP 成功响应后仍需回读目标 shell、页面、元素或模式。
- `close_current_courseware` 已获客户端支持。日常连接与已有课件调整不依赖它；`build_v2.py` 重导入前会把**全部**精确同名课件逐一关闭并回读确认消失（关闭只结束编辑会话，不删除云端课件），关闭失败或 shell 残留时停止导入，防止工具元素叠到旧文档。
- 未经用户要求不执行云同步，完成后保持 Edit 模式。
