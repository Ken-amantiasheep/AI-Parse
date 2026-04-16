# S 盘部署与本地更新指南

## 1. 目录结构（S 盘）

在 `S:\Uploading Team\AI-parse` 保持以下结构：

- `current\` 当前线上版本（Junction 或同步目录）
- `releases\vX.Y.Z\` 每次发布的完整版本目录
- `release_manifest.json` 版本元数据（当前版本、发布历史、回滚历史）
- `logs\` 运行日志与发布操作日志（`release_ops.log`）
- `output\` 业务输出

`release_manifest.json` 由发布/回滚脚本自动维护，不建议手工修改。

## 2. 同事端使用方式（改造后）

同事不再直接从 S 盘运行程序。  
统一安装到本机后运行 `start_ai_parse.bat`（或桌面快捷方式），启动器会：

1. 读取本地安装版本
2. 读取 `S:\Uploading Team\AI-parse\release_manifest.json`
3. 检测到新版本时弹窗询问是否更新
4. 用户同意后执行整包覆盖更新（先本地备份，再替换）
5. 启动本地 `app\current\start_gui.bat`

首次安装脚本：

```powershell
S:\Uploading Team\AI-parse\install_client.bat
```

该文件会在每次发布/回滚后自动刷新，始终指向 `current\scripts\client\install_client.ps1`。

## 3. 网关服务部署（同机）

1. 在服务器环境变量中设置：
   - `ANTHROPIC_API_KEY`
   - `INTERNAL_API_TOKEN`
   - `RATE_LIMIT_PER_MIN`（可选）
2. 安装网关依赖：
   - `pip install -r gateway_service\requirements.txt`
3. 手工启动测试：
   - `gateway_service\start_gateway.bat`
4. 健康检查：
   - `http://127.0.0.1:8080/health`
5. 服务化（NSSM）：
   - 运行 `gateway_service\install_gateway_service.ps1`

## 4. 开发端发布新版本

### 4.1 命令行方式

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy_to_s_drive.ps1 `
  -Version v1.2.0 `
  -Operator "Ken.Zhang" `
  -Notes "new parsing rules"
```

发布脚本会自动：

- 拷贝程序到 `releases\v1.2.0`
- 更新 `current`
- 写入 `release_manifest.json`
- 记录发布日志到 `logs\release_ops.log`
- 发布失败时恢复原 `current`

### 4.2 GUI 方式（推荐）

运行：

```bat
scripts\release_manager.bat
```

在界面中可以查看当前版本、发布新版本、查看历史并回滚。

## 5. 回滚版本

### 5.1 命令行方式

```powershell
powershell -ExecutionPolicy Bypass -File scripts\switch_release.ps1 `
  -Version v1.1.0 `
  -Operator "Ken.Zhang" `
  -Reason "urgent rollback"
```

回滚脚本会自动：

- 校验目标版本完整性（关键文件存在）
- 切换 `current` 到目标版本
- 写入 `release_manifest.json` 历史
- 记录 `logs\release_ops.log`
- 失败时自动恢复原 `current`

### 5.2 GUI 方式

在 `scripts\release_manager.bat` 的版本列表里选中目标版本后点“回滚到选中版本”。
