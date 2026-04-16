# UAT 验收清单

## 安装与升级验收

- [ ] 首次执行 `FIRST_INSTALL.bat` 可成功安装到指定目录
- [ ] 安装后自动创建桌面快捷方式并可正常启动
- [ ] 启动时可读取 `S:\Uploading Team\AI-parse\metadata\version.json`
- [ ] 远端有新版本时弹出更新确认框
- [ ] 点击“是”后主程序退出并由外部 updater 完成更新后自动重启
- [ ] 点击“否”后仍可继续使用旧版本
- [ ] S 盘不可达时，若本地已有版本可继续启动
- [ ] updater 缺失时可自动生成 fallback updater 并完成更新

## 功能验收

- [ ] Intact 样本至少 2 组可成功生成 JSON
- [ ] CAA 样本至少 2 组可成功生成 JSON
- [ ] GUI 可选择输出目录并正常写入文件
- [ ] 同名输出自动加 `(1)` 后缀

## 并发验收

- [ ] 3-5 人并发生成任务，均可完成
- [ ] 网关日志中有 request_id、company、docs、status

## 异常验收

- [ ] 网关停止时，客户端可给出明确错误提示
- [ ] INTERNAL_API_TOKEN 错误时返回 401
- [ ] ANTHROPIC_API_KEY 无效时返回可读错误
- [ ] 输出目录无权限时 preflight 失败

## 运维验收

- [ ] 网关服务开机自启动成功
- [ ] 使用 `RUN_PUBLISHER.bat` 发布后，`metadata/version.json` 版本正确更新
- [ ] 共享盘产物包含 `release/AI_parse`、`metadata/version.json`、`FIRST_INSTALL.bat`
- [ ] 发布包中包含 `updater/update_and_restart.cmd`
