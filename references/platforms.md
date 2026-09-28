# 跨平台与多代理适配

## 支持基线

- Python 3.10 或更高版本。核心分类、预演、移动、日志、HTML 报告和 OOXML/EPUB 文本提取只使用标准库。
- 路径均通过 `pathlib` 处理；不假设 `/Users`、盘符或路径分隔符。移动使用 Python `os.rename`，只允许同一文件系统，不采用复制后删除。
- 生成名称同时遵守 Windows 的非法字符、末尾句点/空格和 `CON`、`NUL` 等保留设备名规则；这些名称在 macOS 上同样可用。
- 缓存指纹使用文件大小、纳秒修改时间与首尾内容采样，不依赖 macOS inode 或 Windows file index，重命名/移动后可复用。
- 图片 OCR 使用 PaddleOCR，音视频转写使用 faster-whisper/PyAV；两者均有 macOS、Windows 运行方式，但运行时、硬件和模型需由用户自行授权安装。
- PDF 文本层由 `pypdf` 提取。扫描 PDF 需额外的 PDF 页面渲染器再交给 OCR；当前核心不会调用 macOS Quick Look、Finder、Windows Explorer 或 Office 自动化。

## 产品安装

`SKILL.md` 保持 Agent Skills 风格，核心脚本不导入 Codex SDK。`agents/openai.yaml` 只是 Codex UI 元数据，其它代理可忽略。

- Codex：个人目录 `~/.codex/skills/xunxu`，显式调用 `$xunxu`；也可按描述自动发现。
- Claude Code：个人目录 `~/.claude/skills/xunxu` 或项目目录 `.claude/skills/xunxu`，显式调用 `/xunxu`。
- WorkBuddy、豆包及其它代理：不同版本没有已核验的统一本地 Skill 安装路径。使用 `scripts/install.py --product generic --destination <该产品实际的 Skills 目录>` 可完成不覆盖式复制；能否自动发现、如何显式调用，以产品版本文档为准。若产品不能读取本地 `SKILL.md` 或运行 Python，它只能参考本仓库流程，不能声称原生运行此 Skill。

安装器在目标已存在时直接停止，不覆盖、不删除。升级应由相应包管理或版本控制流程完成。

## 命令示例

macOS/Linux：

    python3 scripts/install.py --product codex --dry-run
    python3 scripts/install.py --product claude
    python3 scripts/install.py --product generic --destination /path/to/product/skills/xunxu

Windows PowerShell：

    py -3 scripts/install.py --product codex --dry-run
    py -3 scripts/install.py --product claude
    py -3 scripts/install.py --product generic --destination "C:\path\to\product\skills\xunxu"

所有产品都必须遵守同一授权边界：先问配置、只预演、不读取私密内容、用户确认后才移动。
