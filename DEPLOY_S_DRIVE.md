# S 盘共享部署指南

## 1. 目录结构

在 `S:\Uploading Team` 保持以下结构：

- `current\` 当前运行版本（Junction）
- `releases\vX.Y.Z\` 版本目录
- `logs\` 网关与客户端日志
- `output\` 输出文件（建议按用户或日期分子目录）

## 2. 网关服务部署（同机）

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

## 3. 发布新版本

在代码仓库目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy_to_s_drive.ps1 -Version v1.0.0
```

该命令会：

- 拷贝程序到 `S:\Uploading Team\releases\v1.0.0`
- 更新 `S:\Uploading Team\current` 指向新版本

## 4. 回滚版本

```powershell
powershell -ExecutionPolicy Bypass -File scripts\switch_release.ps1 -Version v0.9.5
```

## 5. 客户端启动

用户统一从：

- `S:\Uploading Team\current\start_gui.bat`

启动前会自动执行 `preflight_check.py`：

- 输出目录可写
- 日志目录可写
- 网关健康可达（gateway 模式）
