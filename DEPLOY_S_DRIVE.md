# S 盘集中发布指南

## 1. 共享盘目录规范

共享盘根目录：`S:\Uploading Team\AI-parse`

固定结构：

- `release\AI_parse\` 发布包目录
- `metadata\version.json` 线上版本元数据
- `Publisher\` 发布工具副本
- `FIRST_INSTALL.bat` 首次安装入口

## 2. 发布者操作

在开发机项目根目录运行：

```bat
RUN_PUBLISHER.bat
```

发布工具会固定执行：

1. `git pull origin master`
2. 更新 `version.py` 中版本号
3. 构建（compileall）
4. 生成 `version.json`
5. 同步发布包到共享盘 `release\AI_parse`
6. 更新共享盘 `metadata\version.json`
7. 同步 `FIRST_INSTALL.bat` 与发布文档到共享盘

## 3. 客户端安装与更新

同事首次安装：

1. 双击 `S:\Uploading Team\AI-parse\FIRST_INSTALL.bat`
2. 选择安装目录
3. 可选创建桌面快捷方式

日常运行：

- 从本机安装目录运行 `start_gui.bat`（不要直接从共享盘运行）
- 启动时自动检查 `metadata\version.json`
- 有新版本时弹窗确认，确认后由外部 updater 执行覆盖并自动重启

## 4. 网关服务

网关部署和服务化保持原流程，详见：

- `gateway_service\start_gateway.bat`
- `gateway_service\install_gateway_service.ps1`
