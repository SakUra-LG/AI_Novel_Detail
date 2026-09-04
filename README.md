# AI 小说细节生成

一个面向中文小说创作的 RAG + 大语言模型生成项目，目前聚焦两项功能：

1. **中国神话的幽默改写**：保留经典事件链与结局，通过人物对话、情境反差和固定串线角色增强幽默感，并支持同一故事的 1～5 级幽默梯度版本。
2. **武打场景的细节展开**：按“氛围铺垫—持续压制—绝境加深—微小转机—反杀爆发”展开约 1500 字的完整交锋。

项目调用阿里云 DashScope 通义千问生成文本，使用本地 BGE-Large-ZH 模型检索写作素材和专业知识。

## 快速开始

### 1. 创建环境并安装依赖

建议使用 Python 3.10 或更高版本。在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2. 准备本地检索模型

程序默认从 `src/bge_large_zh` 加载模型。该目录体积较大，不进入 Git；首次使用时下载：

```powershell
python -c "from huggingface_hub import snapshot_download; snapshot_download('BAAI/bge-large-zh', local_dir='src/bge_large_zh')"
```

仓库已保留预计算的知识库向量。只要模型目录就绪，无须先重建索引。

### 3. 配置 API Key

真实密钥不能写入代码或提交到 Git。当前 PowerShell 会话中设置：

```powershell
$env:DASHSCOPE_API_KEY="你的 DashScope API Key"
```

可选参数及默认值见 [.env.example](.env.example)。项目不会自动读取 `.env` 文件；若使用它，请由终端或 IDE 注入环境变量。

> 安全提示：旧版本曾在 `config.py` 中硬编码密钥。如果这个仓库曾被共享或推送到远端，应立即在 DashScope 控制台撤销旧密钥并创建新密钥。删除当前文件中的值不能清除 Git 历史。

### 4. 运行

生成单篇幽默神话改写：

```powershell
python run.py myth --prompt "幽默改写后羿射日，保留射九留一的结局，动作细节充分"
```

生成同一神话的 1～5 级幽默版本：

```powershell
python run.py humor-levels --prompt "改写哪吒闹海，保留核心事件链"
```

生成武打场景：

```powershell
python run.py fight --prompt "青年剑客沈砚在雨夜古寺对决拳师韩崇，利用钟绳找到反杀机会"
```

三种命令都可附加 `--output outputs/文件名.txt` 保存结果；`outputs/` 默认被 Git 忽略。

## 仓库结构

```text
.
├── README.md                    # GitHub 项目主页与快速开始
├── requirements.txt            # Python 依赖
├── run.py                       # 推荐的统一命令行入口
├── docs/
│   ├── HUMOR_REWRITE.md         # 幽默神话改写实现与运行说明
│   └── FIGHT_SCENE_EXPANSION.md # 武打细节展开实现与运行说明
├── src/
│   ├── main.py                  # 两项生成流程、提示词、清洗与质量检查
│   ├── config.py                # 环境变量配置
│   ├── embedding_model.py       # 两类检索共用的 BGE 模型实例
│   ├── retrieval_content.py     # 素材语义检索
│   ├── retrieval_profession.py  # 写作知识语义检索
│   ├── build_content_index.py   # 重建素材索引
│   ├── build_profession_index.py# 重建专业知识索引
│   ├── humor_levels/            # 幽默分级生成与轻量验收
│   └── knowledgeBase/           # 素材、人工样本、向量和神话约束
└── examples/
    ├── humor/                   # 全部保留的既有幽默样本与认可正文
    └── fight/                   # 既有武打生成示例
```

## 功能文档

- [幽默神话改写：实现、样本与运行方式](docs/HUMOR_REWRITE.md)
- [武打场景细节展开：实现、提示词结构与运行方式](docs/FIGHT_SCENE_EXPANSION.md)

## 样本与数据

本次整理没有删改既有幽默样本文本：

- `src/knowledgeBase/humor_punchline_examples.txt`：人工筛选的对白笑点，是最重要的幽默参考。
- `src/knowledgeBase/Content.txt` 与 `themes_Content.json`：包含“神话重写·哪吒风格”等 RAG 风格素材。
- `examples/humor/humor-levels/`：后羿片段的 1～5 级幽默示例。
- `examples/humor/legacy-generations/`：历史幽默改写稿，供比较与回归测试。
- `examples/humor/山海二十简/`：二十篇认可正文及总序。
- `examples/fight/`：两份既有武打生成结果。

不要把 `examples/` 当作运行输出目录，也不要在批处理时覆盖这些文件。

## 工作原理概览

```text
用户提示词
  → BGE 向量检索素材与写作知识
  → 注入神话约束 / 幽默样本 / 武打结构模板
  → 通义千问生成
  → 格式清洗、重复与一致性检查
  → 控制台输出或保存到 outputs/
```

神话长篇流程还会生成总纲、三幕和节拍卡，并针对结尾、核心事件、串线角色越权、长度和文本污染进行检查。武打流程采用更直接的单次结构化提示生成。

## 维护说明

- 修改人工样本后，如需让语义检索结果同步变化，运行 `python src/build_content_index.py` 重建素材向量。
- 修改 `Professional.txt` 后，运行 `python src/build_profession_index.py`。
- `src/main.py` 是历史演进形成的单文件核心，功能完整但体积较大；后续重构应先用 `examples/` 做回归对比，避免幽默风格和神话事件链退化。
- API 调用会产生费用。1～5 级幽默模式每级最多重试 3 次，单次任务可能触发多次长文本调用。

## 当前边界

- 必须联网调用 DashScope；BGE 检索在本机执行。
- 首次加载 BGE 模型较慢，CPU 环境也可运行，但速度明显低于 CUDA。
- 自动质量规则只能做初筛，最终文学质量仍需人工通读。
- 仓库未附带开源许可证；对外发布或复用前请由项目负责人补充许可证与数据授权说明。
