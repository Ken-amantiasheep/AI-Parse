# AI-parse 发布与安装说明

## 发布者

1. 运行 `RUN_PUBLISHER.bat`
2. 填写共享盘根目录（默认 `S:\Uploading Team\AI-parse`）
3. 查看线上版本
4. 输入新版本号（如 `1.0.3`）
5. 点击“执行发布”
6. 工具会固定执行：
   - `git pull origin master`
   - 更新 `version.py` 版本
   - 构建（compileall）
   - 生成 `version.json`
   - 同步发布包到 `release/AI_parse`
   - 更新 `metadata/version.json`
   - 同步 `FIRST_INSTALL.bat` 和发布工具到共享盘

## 客户端同事

1. 首次：双击共享盘 `FIRST_INSTALL.bat`
2. 选择安装目录
3. 可选创建桌面快捷方式
4. 日常运行本机 `start_gui.bat`
5. 启动时若发现新版本，会弹窗询问是否更新
