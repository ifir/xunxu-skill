# 循序（Xunxu）

循序是一个可移植的 Agent Skill，用于在 macOS 和 Windows 整理杂乱下载目录与文件收集目录。它根据文件名、扩展名、真实格式、元数据及必要的本地内容分析，把散落文件归入清晰目录；在用户授权时，还可生成语义化文件名和二级意图目录。

> 核心安全边界：循序只移动或重命名文件，绝不删除、覆盖、清空或修改文件内容。实际移动前必须展示预演并取得明确确认。

## 功能

- 整理文档资料、电子书、图片、视频、音频、字幕、压缩包、安装包、字体、代码和其它文件。
- 根据用户选择决定是否改名、是否递归整理已有文件夹、是否信任已有名称。
- 对名称含义不清的图片使用视觉理解/OCR，对音视频按需使用元数据、关键帧或语音转写。
- 生成 YYMMDD-意图摘要.原扩展名 格式的新名称，并创建不超过 8 个字符的二级意图目录。
- 使用磁盘任务队列保存分析进度，可在任务中断或上下文压缩后恢复。
- 用有界多进程并行提取文档证据，正文落盘、终端只返回短索引，减少等待和 token 消耗。
- 生成追加式整理日志、意图缓存和独立静态 HTML 报告。

## 分类结构

固定使用 11 个一级分类：

    文档资料/  电子书/  图片/  视频/  音频/  字幕/
    压缩包/    安装包/  字体/  代码/  其它/

允许改名并成功识别意图时，可形成：

    文档资料/合同协议/260309-北京住房租赁合同.doc
    图片/日历/250120-全年公历农历年历.webp
    视频/绘画教程/251215-卡通小猪绘制过程.mov

完整格式清单见 [references/file-types.md](references/file-types.md)。

## 运行环境

- Python 3.10+。
- 核心分类、预演、移动、缓存、报告以及 DOCX/PPTX/XLSX/EPUB 文本提取不需要第三方包。
- macOS 和 Windows 使用相同 Python 脚本；不依赖 Finder、Quick Look、Explorer 或本地 Office。
- 可选 PDF、OCR、转写依赖需由用户明确安装；首次模型下载也需单独授权。

## 安装

| 产品 | 个人 Skill 目录 | 调用方式 | 验证状态 |
|---|---|---|---|
| Codex | `~/.codex/skills/xunxu` | `$xunxu` 或自然语言触发 | 已适配 |
| Claude Code | `~/.claude/skills/xunxu` | `/xunxu` | 已按官方 Agent Skills 目录适配 |
| WorkBuddy | 由具体版本决定 | 由具体版本决定 | 官方本地 Skill 路径尚未核实 |
| 豆包 | 由具体版本决定 | 由具体版本决定 | 官方本地 Skill 路径尚未核实 |

仓库是标准 `SKILL.md + scripts + references` 布局，核心代码不依赖 Codex SDK。WorkBuddy、豆包等产品若支持读取本地 Agent Skill 且能运行 Python，可用通用安装目标；否则不能仅复制目录就声称原生可用。

### macOS / Linux

通过 SSH 克隆到 Codex Skills 目录：

    git clone git@github.com:ifir/xunxu-skill.git ~/.codex/skills/xunxu

或使用 HTTPS：

    git clone https://github.com/ifir/xunxu-skill.git ~/.codex/skills/xunxu

也可从已克隆仓库安全复制，安装器遇到已存在目标会停止，不覆盖：

    python3 scripts/install.py --product codex --dry-run
    python3 scripts/install.py --product codex
    python3 scripts/install.py --product claude
    python3 scripts/install.py --product generic --destination /实际/Skills/目录/xunxu

### Windows PowerShell

    git clone https://github.com/ifir/xunxu-skill.git "$env:USERPROFILE\xunxu-skill"
    cd "$env:USERPROFILE\xunxu-skill"
    py -3 scripts/install.py --product codex --dry-run
    py -3 scripts/install.py --product codex
    py -3 scripts/install.py --product claude
    py -3 scripts/install.py --product generic --destination "C:\实际\Skills\目录\xunxu"

重新启动对应代理或开启新任务后再调用。更详细的平台边界见 [references/platforms.md](references/platforms.md)。

## 使用方式

在支持本地 Agent Skill 的代理中附上或指定目标目录，然后输入“使用 xunxu 帮我整理这个目录”（Claude Code 也可输入 `/xunxu`）。每次新整理任务都会询问：

1. 是否允许修改文件或文件夹名称？
2. 是否允许整理已有文件夹中的文件？
3. 如果允许改名，是否信任已有意义的名称？
4. 可选：哪些名称属于私密文件或文件夹、不读取内容？

示例：

    1. 是；2. 是；3. 否；4. 证件、密码、私人

第四项省略时默认为无私密过滤。

## 名称信任策略

### 信任已有名称

- 名称有明确意义：保留名称，不读取内容。
- 名称是哈希、随机串、相机流水号或表意不清：仍读取必要内容进行意图识别。

### 不信任已有名称

- 名称有意义：把名称作为待验证的弱线索，优先读取最少内容证据；一致即可停止。
- 内容与名称矛盾或证据不足：升级到更深入分析。
- 名称无意义：直接进行标准内容识别。
- 不会仅凭名称生成最终意图。

### 私密名称

- 私密文件不读取内容、不改名，只依据名称和扩展名进行粗粒度分类。
- 私密文件夹整棵子树不遍历、不移动、不改名。

## 安全机制

- 先预演，用户明确确认后才移动。
- 不删除文件或目录，不清理重复文件。
- 不覆盖同名文件，也不自动改名绕过冲突。
- 不执行安装包，不挂载镜像，不解压压缩包。
- 不跟随符号链接。
- 跳过隐藏文件、未完成下载以及最近仍在写入的文件。
- 预演后文件或配置变化时，拒绝或跳过对应操作。
- 移动使用同一文件系统内的原子重命名，不采用复制后删除。
- 文件内容被视为不可信数据，其中的指令不会被执行。

## 内容分析

内容分析能力按格式渐进启用，默认整理脚本不需要第三方 Python 包。

| 脚本 | 用途 |
|---|---|
| scripts/ocr_image.py | 图片 OCR |
| scripts/transcribe_media.py | 音频或视频语音转写 |
| scripts/analyze_media.py | 媒体路由及原始结果缓存 |
| scripts/analyze_document.py | 跨平台提取文本、OOXML、EPUB 和 PDF 文本层 |
| scripts/analyze_batch.py | 多进程批量提取紧凑证据，正文不输出到终端 |

PDF、OCR 和音视频转写的可选依赖统一固定在 [requirements.txt](requirements.txt)：

    python3 -m pip install -r requirements.txt

- PDF 使用 pypdf；纯扫描 PDF 无文本层时仍需额外页面渲染与 OCR，当前会安全降级而不猜测。
- 如果系统已有 `pdftotext`，PDF 会优先走这个快速路径并写入临时文件；否则回退 pypdf。
- XLSX 默认只提取工作表名和每表前 20 行、12 列来判断主题，不启动 pandas 全量分析。
- OCR 使用 paddleocr 3.7.0，还需安装与设备匹配的 PaddlePaddle runtime。
- 转写使用 faster-whisper 1.2.1，通过 PyAV 解码媒体，不要求系统安装 FFmpeg。
- 首次转写通常需要下载模型权重；这是独立网络操作，应由用户明确授权。
- 能力不可用时返回 unavailable 并保留原名，不凭空猜测。

详细流程见 [references/intent-analysis.md](references/intent-analysis.md)。

## 可恢复的长任务

内容分析使用持久任务队列：

    .cache/runs/<run-id>/
    ├── manifest.json
    ├── heartbeat.json
    ├── summary.json
    ├── jobs/
    ├── results/
    ├── failures/
    └── merge.json

每个文件是一项独立任务。进度写入磁盘而不是依赖聊天上下文，因此任务中断后可以恢复。普通失败最多重试两次；文件在分析期间变化时标记为 stale。

环境支持时，可让只读子 Agent 分别处理文档、图片和音视频。子 Agent 只能分析并写逐文件结果；最终预演、移动和改名由主 Agent统一执行。

## 整理产物

    organizer.report.html       静态目录报告
    organizer.change.md         追加式变更日志
    .cache/
    ├── file2intent.md          用户可读意图索引
    ├── .organizer.config.json  本次配置
    ├── .organizer.plan.json    预演计划
    ├── .organizer.state.json   已整理状态
    ├── .organizer.intent.json  机器可读意图缓存
    └── runs/                   可恢复任务记录

静态报告不会打开文件或文件夹。点击文件名会显示原始文件名、当前文件名、最后修改时间、文件大小及精确字节数、当前相对位置。

## 脚本说明

| 脚本 | 用途 |
|---|---|
| scripts/organizer.py | 配置、预演、移动、改名、报告和状态管理 |
| scripts/analyze_document.py | 文本、OOXML、EPUB 与 PDF 证据提取 |
| scripts/analyze_batch.py | 多进程批量证据提取与短索引 |
| scripts/run_queue.py | 创建、领取、完成、恢复和合并分析任务 |
| scripts/ocr_image.py | 本地图片 OCR |
| scripts/transcribe_media.py | 本地音视频语音转写 |
| scripts/analyze_media.py | 媒体分析入口及缓存 |
| scripts/common.py | 文件指纹、时间及 JSON 公共逻辑 |
| scripts/sync_skill.py | 同步安装目录与本仓库 |
| scripts/install.py | Codex、Claude Code 与自定义目标安装 |

通常应通过支持本地 Agent Skill 的代理使用本项目，不建议绕过 Skill 直接执行移动命令。

## 开发与同步

当前约定：

    安装目录：~/.codex/skills/xunxu
    Git 仓库：/Users/zhangzhenlin01/project/xunxu-skill

安装目录同步到仓库：

    python3 ~/.codex/skills/xunxu/scripts/sync_skill.py --source ~/.codex/skills/xunxu --destination /Users/zhangzhenlin01/project/xunxu-skill

检查是否一致：

    python3 ~/.codex/skills/xunxu/scripts/sync_skill.py --source ~/.codex/skills/xunxu --destination /Users/zhangzhenlin01/project/xunxu-skill --check

直接修改仓库版本时，可交换 source 与 destination 反向同步。同步脚本保留仓库的 .git 和 README.md，不会自动提交或推送。

## 测试

    python3 tests/run_all.py

默认测试覆盖 11 个分类、名称策略、私密项、路径安全、冲突保护、幂等执行、跨平台指纹、文档解析、安装器、可恢复队列、静态报告和媒体能力降级。GitHub Actions 在 macOS 与 Windows 上运行 Python 3.10/3.12 矩阵。测试不会下载模型，也不会操作真实下载目录。

## 项目结构

    xunxu-skill/
    ├── SKILL.md
    ├── README.md
    ├── agents/openai.yaml
    ├── references/
    ├── requirements.txt
    ├── scripts/
    └── tests/run_all.py

## 已知边界

- 文件类型清单无法穷尽未来所有格式，未知格式进入“其它”。
- OCR、转写及视觉理解质量取决于本地工具、模型和输入质量。
- 不删除整理后留下的空目录。
- 不负责重复文件删除、压缩包解压、软件安装或跨文件系统搬运。

## 许可证

当前仓库尚未包含许可证文件。公开分发或接受外部贡献前，建议添加明确的开源许可证。
