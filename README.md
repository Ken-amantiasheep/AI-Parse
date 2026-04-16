# AI Parse - 文档解析工具

从 Autoplus、Quote、MVR、Application Form 生成 Intact 上传所需的 JSON

## 安装

```bash
pip install -r requirements.txt
```

## 配置

1. 复制 `config/config.example.json` 为 `config/config.json`
2. 共享部署推荐使用网关模式（`mode=gateway`），客户端不保存 Anthropic Key
3. 如果使用直连模式（`mode=direct`），在 `config/config.json` 中填入 Anthropic API Key

## 使用

### 方法一：命令行参数

```bash
python main.py --autoplus path/to/autoplus.pdf --quote path/to/quote.pdf --mvr path/to/mvr.pdf --application-form path/to/form.pdf --output output/result.json
```

参数说明：
- `--autoplus`: Autoplus 文档路径
- `--quote`: Quote 文档路径
- `--mvr`: MVR 文档路径
- `--application-form`: Application Form 文档路径
- `--output`: 输出JSON文件路径（可选，默认：output/output.json）
- `--config`: 配置文件路径（可选，默认：config/config.json）

**注意：** 至少需要提供一个文档路径。

### 方法三：S 盘共享部署（推荐）

1. 首次从 `S:\Uploading Team\AI-parse\FIRST_INSTALL.bat` 安装到本机
2. 日常从本机安装目录运行 `start_gui.bat`（或桌面快捷方式）
3. 启动时会自动检查共享盘 `metadata/version.json`
4. 若有新版本会弹窗提示，确认后自动更新并重启
5. 发布流程见 `PUBLISH_README.md`

### 方法二：将文档放入对应文件夹

1. 将文档放入 `documents/` 对应文件夹：
   - `documents/autoplus/` - Autoplus 文档
   - `documents/quote/` - Quote 文档
   - `documents/mvr/` - MVR 文档
   - `documents/application_form/` - Application Form 文档

2. 运行主程序（需要修改代码指定文件路径）

3. 生成的 JSON 文件将保存在 `output/` 文件夹

## 支持的文档格式

- PDF (.pdf)
- Word (.doc, .docx)
- 文本文件 (.txt)

## 项目结构

```
AI_parse/
├── config/              # 配置文件
├── documents/           # 输入文档
│   ├── autoplus/
│   ├── quote/
│   ├── mvr/
│   └── application_form/
├── output/              # 生成的JSON
├── tests/               # 测试文件
├── utils/               # 工具函数
├── main.py              # 主程序
└── requirements.txt     # 依赖包

```
