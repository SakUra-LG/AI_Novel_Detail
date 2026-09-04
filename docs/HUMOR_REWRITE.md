# 幽默神话改写

## 功能目标

该流程把中国神话改写成可读的中长篇小说文本。它不是任意“魔改”：原神话的关键人物、核心动作、事件先后和结局必须保留，幽默主要来自情境内的对白拆台、生活化反差和角色小狼狈。

支持两种输出：

- 单篇改写：生成一个完整故事。
- 幽默分级：对同一需求生成 1～5 级版本，级别越高，吐槽、互怼和对白笑点越密集。

## 实现方法

核心入口是 `src/main.py` 中的 `generate_myth_rewrite(prompt)`，主要步骤如下：

1. **匹配故事约束**

   根据标题和别名读取 `myth_core_constraints_revised.json`，锁定必须事件、角色动作、结局、禁用人物和禁用设定；同时加载 `myth_thread_protagonist_constraints.json`，限制串线角色“阿满”只能见证、记录和吐槽，不能替主角解决问题。

2. **检索风格素材**

   `retrieval_content.py` 使用 BGE-Large-ZH 把用户提示转换为向量，与 `features_Theme.npy` 做余弦相似度比较。检索结果优先选择“神话重写·哪吒风格”样本。人工对白样本另从 `humor_punchline_examples.txt` 按当前神话筛选。

3. **规划长篇结构**

   模型先生成总纲，再拆为三幕和多张节拍卡。每个节拍被要求包含当前目标、阻碍、行动、直接结果和与下一节的衔接，减少单纯堆字与剧情漂移。

4. **逐幕生成与情感收束**

   第一幕负责背景、动机和准备；第二幕展开核心行动；第三幕处理代价、余波和结局。结尾另加载 `touching_foreshadow_examples.txt` 与 `touching_ending_examples.txt`，避免只有笑点而没有情感落点。

5. **清洗和质量门槛**

   后处理会移除 Markdown、道歉、模型说明、乱码与重复片段，检查核心事件命中、事件顺序、跨神话污染、阿满越权、篇幅和结尾完整性。必要时执行受控修复或重试。

幽默分级由 `src/humor_levels/humor_level_generator.py` 实现。每一级都有笑点数量目标、对白幽默比例和样本注入比例；单级最多尝试 3 次，未完全达标时保留指标最接近的候选。

## 幽默资产（必须保留）

| 路径 | 用途 |
|---|---|
| `src/knowledgeBase/humor_punchline_examples.txt` | 人工笑点对白，按神话标签筛选 |
| `src/knowledgeBase/Content.txt` | 原始写作与风格素材 |
| `src/knowledgeBase/themes_Content.json` | 结构化素材，与预计算向量对应 |
| `examples/humor/humor-levels/` | 1～5 级梯度示例 |
| `examples/humor/legacy-generations/` | 历史生成稿，适合人工比较 |
| `examples/humor/山海二十简/` | 二十篇认可正文与总序 |

新增样本时学习“笑点机制”，不要让模型逐句复制示例。重大牺牲、死亡、分离和担责场景应及时收住幽默。

## 如何运行

先完成根目录 [README](../README.md) 的依赖、BGE 模型和 API Key 配置。

### 单篇改写

```powershell
python run.py myth --prompt "幽默改写大禹治水，保留改堵为疏和三过家门，动作与百姓反应写细"
```

保存到文件：

```powershell
python run.py myth `
  --prompt "幽默改写愚公移山，保持结局与寓意" `
  --output "outputs/愚公移山.txt"
```

### 生成 1～5 级幽默版本

```powershell
python run.py humor-levels --prompt "改写后羿射日，核心是十日并出、射九留一"
```

此模式会自动把各级正文保存到 `outputs/humor_levels/<提示词片段>/`。传入 `--output` 时，还会把五个版本合并保存到指定文本文件。

也可以使用原始交互入口：

```powershell
python src/main.py
```

输入中含“神话”、具体神话名或“山海经”等关键词时进入神话流程；同时含“幽默强度”“1~5级”等表达时进入分级流程。交接后更推荐使用 `run.py` 的显式子命令，避免关键词路由歧义。

## 提示词建议

提示词最好同时说明：故事名、不可改变的核心节点、幽默强弱、希望强化的动作或人物关系、目标使用场景。例如：

```text
幽默改写《哪吒闹海》，保留搅海、杀夜叉与敖丙、哪吒担责和莲花化身。
亲子对白可以活泼，但哪吒担责时收住笑点；战斗动作写清楚，结尾不要现代网络梗。
```

不要在一次提示中混入多个神话标题，否则核心约束匹配和污染检查可能互相冲突。

## 调整与维护

### 修改幽默样本

直接编辑 `src/knowledgeBase/humor_punchline_examples.txt`，每条用 `---` 分隔，并用 `【适用神话：故事名】` 标注。随后运行：

```powershell
python src/build_content_index.py
```

人工对白文件由代码直接读取，本身不依赖向量重建；但如果同时改了 `Content.txt`，必须重建 `features_Theme.npy` 和 `themes_Content.json`。

### 修改神话事实约束

- `myth_core_constraints_revised.json`：核心事件链、必须项、禁用项和结局。
- `myth_thread_protagonist_constraints.json`：阿满的身份、出场方式与越权边界。

JSON 修改后先做语法检查：

```powershell
python -c "import json, pathlib; [json.loads(p.read_text(encoding='utf-8')) for p in pathlib.Path('src/knowledgeBase').glob('*.json')]; print('JSON OK')"
```

## 常见问题

- **启动后长期没有输出**：首次加载两个 BGE 检索模块会占用较多内存并需要时间。
- **提示缺少 API Key**：确认密钥设置在运行 Python 的同一终端会话中。
- **找不到模型**：确认 `src/bge_large_zh/config.json` 等模型文件存在。
- **幽默级别自动验收失败**：轻量验收依赖线索词与中文引号，只是近似指标；应人工比较五个版本，而不是只看 `passed`。
- **故事跑偏或串神话**：提示词只保留一个明确标题，并检查对应核心约束 JSON。
- **成本过高**：先运行单篇模式；分级模式最多会产生 15 次生成调用。
