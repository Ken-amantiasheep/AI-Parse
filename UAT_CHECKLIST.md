# UAT 验收清单

## 安装与升级验收

- [ ] 首次执行 `scripts\client\install_client.bat` 可成功安装到 `%LocalAppData%\AI-parse`
- [ ] 安装后自动创建桌面快捷方式并可正常启动
- [ ] 启动时可读取 `S:\Uploading Team\AI-parse\release_manifest.json`
- [ ] 远端有新版本时弹出更新确认框
- [ ] 点击“是”后可完成整包覆盖更新并启动新版本
- [ ] 点击“否”后仍可继续使用旧版本
- [ ] S 盘不可达时，若本地已有版本可继续启动

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
- [ ] 使用 `deploy_to_s_drive.ps1` 发布后，`release_manifest.json` 的 `currentVersion` 正确更新
- [ ] 发布失败时 `current` 会自动恢复到发布前版本
- [ ] 使用 `switch_release.ps1` 回滚后可在 5 分钟内完成
- [ ] 回滚失败时 `current` 会自动恢复到回滚前版本
- [ ] `logs\release_ops.log` 可看到发布/回滚记录（操作者、from/to 版本、结果）
