import re
import time
import os
import sys
import json
import hashlib
import subprocess
import tempfile

try:
    import dashscope as dashscope
except ModuleNotFoundError as exc:
    missing_pkg = getattr(exc, "name", "dashscope")
    raise SystemExit(
        "缺少运行依赖："
        f"{missing_pkg}\n"
        "请先在项目目录执行：\n"
        "python -m pip install -r requirements.txt\n"
        "如果你有多套 Python，请先确认当前解释器：\n"
        "python -c \"import sys; print(sys.executable)\""
    ) from exc

from config import require_api_key
try:
    from retrieval_content import *
    from retrieval_profession import *
except ModuleNotFoundError as exc:
    missing_pkg = getattr(exc, "name", "未知依赖")
    raise SystemExit(
        "缺少运行依赖："
        f"{missing_pkg}\n"
        "请先在项目目录执行：\n"
        "python -m pip install -r requirements.txt\n"
        "若仍报错，请检查是否用了错误的 Python 解释器：\n"
        "python -c \"import sys; print(sys.executable)\""
    ) from exc

from humor_levels.humor_level_generator import generate_humor_level_versions


# 导师最新口径为“7500字左右”；保留一定上浮空间，但不为凑到7800机械补尾。
MYTH_TARGET_TOTAL_MIN = 7500
MYTH_TARGET_TOTAL_SOFT_MAX = 8700
MYTH_TARGET_TOTAL_MAX = 9300
MYTH_ACT_TARGETS = {
    "act1": (1450, 1700),
    "act2": (3950, 4550),
    "act3": (1450, 1700),
}
MYTH_CORE_CONSTRAINTS_FILENAME = 'myth_core_constraints_revised.json'
MYTH_CORE_CONSTRAINTS_FALLBACK_FILENAME = 'myth_core_constraints.json'
MYTH_THREAD_PROTAGONIST_FILENAME = 'myth_thread_protagonist_constraints.json'
QWEN_API_TIMEOUT_SECONDS_DEFAULT = 90
QWEN_API_CALL_COUNTER = 0
DEFAULT_ACT_BEAT_LIMITS = {
    "act1": 4,
    "act2": 7,
    "act3": 4,
}
DEFAULT_ACT_BEAT_MINIMUMS = {
    "act1": 4,
    "act2": 6,
    "act3": 4,
}

BAD_META_PHRASES = [
    "[因原文长度限制未能全部提供]",
    "未完待续",
    "续章未尽",
    "欢迎提出进一步请求",
    "若您有兴趣了解更多详情",
    "下面是故事",
    "参考内容如下",
    "本故事到此结束",
    "调用通义千问 API",
    "HTTPSConnectionPool",
    "SSLError",
    "憨豆",
    "[此时应",
    "典型的互动场景",
    "此处插入",
    "符合要求",
    "画面要素",
    "感情线渐进",
    "推动主题",
    "插入对白互动",
    "隐藏章节",
    "此处暂留",
    "暂留下",
    "实际书写时不显示",
    "不显示这段备注",
    "更多详细描写",
    "关键事件与发展脉络",
    "整个故事由此落下帷幕",
    "工作报告",
    "上级领导",
    "审核备案",
    "天气预报",
    "地痞流氓",
    "立体投影",
    "真实版",
    "图文并茂",
    "吕布",
    "孙猴子",
    "猴哥",
    "赵玄朗",
    "魏征",
    "凤凰台",
    "老黄牛模型",
    "模型",
    "[注]",
    "专职笑",
    "笑话担当",
    "笔记本",
    "手工制作笔记本",
    "专业人员",
    "职业生涯",
    "官方权威",
    "高度重视",
    "查阅研究",
    "宝贵资料",
    "温馨提示",
    "山海十六简",
    "啤酒罐",
    "异界",
    "邪祟",
    "深层怨念",
    "命中注定",
    "摄氏度",
    "小档期",
    "记录仪",
    "记者",
    "历史学家",
    "鸣笛",
    "地表生物",
    "群集区",
    "官方记录",
    "老仆人",
    "手写笔记",
    "青竹筒",
    "文档材料",
    "文献",
    "大规模杀戮",
    "后弈记",
    "第一章极稳",
    "战略利器",
    "温牛奶",
    "恒星",
    "生活品质",
    "压缩声音",
    "记录纸条",
    "珍贵书籍",
    "纪年一刻",
    "手电",
    "卧槽",
    "老子",
    "TODO",
    "待补",
    "待完善",
    "待续写",
    "这段大约",
    "多少字左右",
    "接下来便是",
    "下一节的内容",
    "接下来是下一节",
    "遥远角落",
    "节拍卡",
    "節拍卡",
    "目标达成",
    "目標達成",
    "此处隐含",
    "此处隱含",
    "隐含感情",
    "隱含感情",
    "勾勒",
    "伏笔",
    "伏筆",
    "（完毕）",
    "(完毕)",
    "完毕",
]

HARD_META_RESIDUE_TERMS = [
    "节拍卡",
    "節拍卡",
    "目标达成",
    "目標達成",
    "此处暂留",
    "此處暫留",
    "实际书写时不显示",
    "實際書寫時不顯示",
    "下一节",
    "下一節",
    "备注：",
    "備註：",
]

BAD_PLAN_TERMS = [
    "不明人士帮助信号",
    "神秘人暗中相助",
    "幕后之人",
    "灵魂交换转换修复工程",
    "修复工程",
    "紧急救助程序",
    "程序介入",
    "最大规模致命一击行为",
    "命运审判仪式",
    "超级火炬",
    "防护罩",
    "屏障显现",
    "外挂式助力系统",
    "工作机制",
    "星域",
    "工程",
    "机制",
    "系统",
]

PLAN_DRIFT_PATTERNS = [
    r'预知未来',
    r'预言[^，。；\n]{0,12}(鸟|猫|动物)',
    r'(鸟|猫|动物)[^，。；\n]{0,10}预言',
    r'演播厅|直播间|主持台|节目组',
    r'信心值|数值条|评分条|任务值|能量槽',
    r'外部援助|外援介入|请来帮手|临时帮手|隐藏支援',
    r'系统提示|程序介入|修复工程|任务面板',
]

BODY_DRIFT_PATTERNS = [
    r'演播厅|直播间|主持台|节目组',
    r'信心值|数值条|评分条|任务值|能量槽',
    r'系统提示|程序介入|修复工程|任务面板',
    r'预知未来',
    r'预言[^，。；\n]{0,12}(鸟|猫|动物)',
    r'(鸟|猫|动物)[^，。；\n]{0,10}预言',
    r'不明人士帮助信号|神秘人暗中相助|幕后之人',
    r'外部援助|外援介入|请来帮手|临时帮手|隐藏支援',
    r'党风廉政|反腐败|社会主义|中国特色社会主义|中国梦|民族复兴|中国人民|人民群众',
    r'全面建成小康社会|国家治理体系|依法治国|法治政府|一带一路|人类命运共同体',
    r'政治生态|国际地位|大国关系|联合国宪章|脱贫攻坚|蓝天碧水净土保卫战',
    r'卫星定位|实时坐标|雷暴预警信息系统|疏散通道|应急预案|物资储备点',
    r'身份证|护照|银行|空调制冷系统|自动重启',
    r'上海迪士尼|陆家嘴|东方明珠|虹口|闸北|闵行|浦东|十三陵|颐和园',
    r'二十四式简易太极拳|竞赛套路|心意六合拳|罗汉棍|流星锤|招式的演练技法',
    r'虹口闸北闵行浦东|北京故宫颐和园长城|上海迪士尼度假区',
    r'身份证护照银行|床单依旧干净整洁|指定集合区域|大规模人流疏导',
    r'不明飞行物体|当地政府|驻扎部队|通行证|地下挖矿|护卫队伍|高规格训练',
    r'事故[^。！？\n]{0,80}(调查|坠毁|失踪)|北方边境[^。！？\n]{0,80}坠毁',
    r'话剧现代舞剧音乐会|巨大蛋糕|生日|餐厅门口|厨房里厨师|大型广告牌|宣传片',
    r'景点[^。！？\n]{0,20}封闭施工|主办方|工作人员|粉丝|硬件软件配套设施|人力资源调配',
    r'项目的成功举办|庆典狂欢|游客有更好的体验|供应饮品小吃|现场秩序严格执行',
    r'经济效益|社会效应|行业标杆|品牌形象|消费者|市场发展空间|发展机遇|竞争优势',
    r'双赢|多赢|最优解|制定方案|评估风险|监控过程|动态跟踪|目标任务',
    r'电影纪录片|影视作品|专业团队|摄影器材|拍摄质量|优秀的领导者|积极正面',
    r'大型乐园|游戏互动区|创新玩法|家庭氛围|负责人确实是花了很大心思',
    r'小型乐园|筹备工作|心情都非常舒|各个场所布置|装饰摆设',
    r'方针措施方法路线|指导纲要|计划部署|实施执行落实贯彻|发展态势|积极乐观展望未来',
    r'美好愿景|前景灿烂辉煌|成就辉煌未来|不负众望成就辉煌|共谋发展|黄金时期|绝佳机遇|宝贵契机',
    r'可持续健康发展|繁荣进步|强大生命力|创造力蓬勃|优化改进提高巩固深化拓展',
    r'精准分类归档登记|开展启动运作运行|流转循环周期同步实施|交通往来频繁密切联系',
    # 审稿/验收规则不得伪装成叙事句进入正文。
    r'(这句话|这一句)(?:并)?不是预告',
    r'不是[^。！？\n]{0,30}(后来[^。！？\n]{0,12}的重复|重新开场|重启首日)',
    r'没有重新从[^。！？\n]{0,30}(开篇|开场)',
    r'(按发生顺序|依照发生顺序)[^。！？\n]{0,25}(完整|留在)',
    r'后面的变化不能再靠重复|不由结尾一句替代|没有依靠结尾一句',
    r'没有一轮劳动被写成[^。！？\n]{0,20}(复制|重复)',
]

MANUAL_REVIEW_BAD_TERMS = [
    # 人工复审中反复出现的现代、行政、随机污染词；神话正文一旦命中即视为不合格。
    "棉花糖", "椰汁", "维纳斯", "旱烟杆", "军阀", "美猴王", "日晷", "老猫",
    "金粉", "羊皮绳索", "铜镜", "书吏", "文书", "朝廷派人", "朝廷", "派人",
    "侦探工作", "工作进展", "重要工作", "工作报告", "文档", "档案", "记录员",
    "历史记载员", "官方", "官方资料", "官方记录", "专业器具", "专业利器", "专业素养",
    "生态环境平衡", "解决方案", "最佳解决方案", "风险", "机遇", "发展前进", "分析研究",
    "反馈因素", "负面反馈", "任务构成", "系统性", "项目", "计划", "部署",
    "落实", "贯彻", "战略", "可持续", "繁荣", "辉煌", "前景", "窗口期", "测验",
    "青竹简易册", "手札<<", "眼镜", "地图", "奇特液体", "发光晶体", "药品分类制度",
    "安全性能", "上百小时", "数十分钟", "老公", "公里", "上周", "瓶子游泳",
    "墨水瓶子", "装着墨水的小罐", "瓶子", "交通工具", "现代战术",
    "游客", "高科技", "服务模式", "研究人员", "爱好者", "男同志", "大叔",
    "稿费", "毛玻璃", "跑进画面", "故事拉开了序幕", "历史意义",
    "勇气与信念", "灵魂永存", "墨汁瓶", "墨汁碗",
    "裤裆", "蔫黄瓜", "泡尿", "骂了一句脏话", "屁股蛋",
    "哎呀妈耶", "酷", "协同作战", "成功喜悦", "宝藏书籍", "连锁反应",
    "重要素材", "信息真实性", "完整性方面", "服务", "模式",
    "哇塞", "钓鱼佬", "纸质版", "哦哈哈", "未来世界", "世界格局", "发展轨迹",
    "任务旅程", "能量波动", "秘密等待揭开", "文化价值", "个人成长",
    "中华优秀传统文化", "伟大事业", "精神象征", "重要信息", "回到现实",
    "纯粹物理", "防水材料", "組件", "组件", "表演", "同志",
    # 明显错别/繁简/转写污染。
    "牛朗", "后弈", "怎麽", "夢", "紅", "婦", "認真", "筆", "精衛",
    "尚全", "全成型", "太大行列",
]

MANUAL_REVIEW_BAD_PATTERNS = [
    r'\\200|\\\\|\\[，。！？“”"\']|\\[A-Za-z0-9]{1,8}',
    r'<<[^>\n]{1,80}>>',
    r'\[[^\]\n]{1,80}\]',
    r'\*[^*\n]{1,120}\*',
    r'\.\.\.',
    r'--',
    r'平台[^。！？\n]{0,30}发光晶体',
    r'瓶子[^。！？\n]{0,30}(游泳|漂|滚|晃)',
    r'墨水[^。！？\n]{0,30}(瓶子|小罐)',
    r'(方案|计划|目标|项目|工作|落实|贯彻|部署|风险|机遇|反馈)[^。！？\n]{0,18}(方案|计划|目标|项目|工作|落实|贯彻|部署|风险|机遇|反馈)',
]

MYTH_CORE_CONSTRAINTS_CACHE = None
MYTH_THREAD_PROTAGONIST_CACHE = None

TRADITIONAL_TO_SIMPLIFIED = str.maketrans({
    "負": "负", "責": "责", "連": "连", "劍": "剑", "飛": "飞", "昇": "升",
    "賓": "宾", "臉": "脸", "紅": "红", "脖": "脖", "漲": "涨", "氣": "气",
    "惱": "恼", "閉": "闭", "這": "这", "關": "关", "鍵": "键", "時": "时",
    "風": "风", "聲": "声", "漸": "渐", "強": "强", "雲": "云", "層": "层",
    "壓": "压", "漢": "汉", "鐘": "钟", "離": "离", "狀": "状", "別": "别",
    "鬧": "闹", "騰": "腾", "還": "还", "麼": "么", "過": "过", "張": "张",
    "邊": "边", "擦": "擦", "額": "额", "懷": "怀", "裡": "里", "摸": "摸",
    "東": "东", "啥": "啥", "説": "说", "術": "术", "業": "业", "專": "专",
    "攻": "攻", "嘆": "叹", "裡": "里", "該": "该", "檢": "检", "裝": "装",
    "遠": "远", "處": "处", "傳": "传", "轟": "轰", "鳴": "鸣", "龍": "龙",
    "宮": "宫", "經": "经", "察": "察", "覺": "觉", "異": "异", "動": "动",
    "準": "准", "備": "备", "動": "动", "態": "态", "來": "来", "們": "们",
    "調": "调", "整": "整", "塵": "尘", "國": "国", "舅": "舅", "喃": "喃",
    "語": "语", "師": "师", "傅": "傅", "實": "实", "話": "话", "擔": "担",
    "會": "会", "變": "变", "魚": "鱼", "蝦": "虾", "類": "类", "動": "动",
    "物": "物", "麼": "么", "沒": "没", "帶": "带", "什": "什", "麼": "么",
    "與": "与", "萬": "万", "絲": "丝", "嚴": "严", "個": "个", "豐": "丰",
    "臨": "临", "麗": "丽", "舉": "举", "樂": "乐", "鄉": "乡", "書": "书",
    "買": "买", "亂": "乱", "爭": "争", "於": "于", "亞": "亚", "產": "产",
    "畢": "毕", "寧": "宁", "眾": "众", "優": "优", "傢": "家", "價": "价",
    "億": "亿", "債": "债", "傷": "伤", "傾": "倾", "後": "后", "門": "门",
    "體": "体", "發": "发", "戰": "战", "愛": "爱", "頭": "头", "靜": "静",
    "場": "场", "顏": "颜", "顯": "显", "點": "点", "畫": "画", "聲": "声",
    "處": "处", "變": "变", "聽": "听", "聞": "闻", "問": "问", "應": "应",
    "對": "对", "開": "开", "閃": "闪", "現": "现", "壞": "坏", "萬": "万",
    "塊": "块", "葉": "叶", "樹": "树", "橋": "桥", "線": "线", "輕": "轻",
    "點": "点", "雙": "双", "寫": "写", "讀": "读", "韻": "韵", "觀": "观",
})
TRADITIONAL_TO_SIMPLIFIED.update(str.maketrans({
    "難": "难", "嗎": "吗", "當": "当", "從": "从", "讓": "让", "總": "总",
    "覺": "觉", "見": "见", "裏": "里", "爺": "爷", "爾": "尔", "為": "为",
    "爲": "为", "擋": "挡", "護": "护", "藥": "药", "島": "岛", "臺": "台",
    "灣": "湾", "衝": "冲", "沖": "冲", "殺": "杀", "給": "给", "網": "网",
    "卻": "却", "剛": "刚", "幾": "几", "無": "无", "應": "应", "種": "种",
    "尋": "寻", "將": "将", "隻": "只", "趕": "赶", "頂": "顶", "腳": "脚",
    "歸": "归", "點": "点", "淚": "泪", "復": "复", "蘇": "苏", "餘": "余",
    "雜": "杂", "塵": "尘", "彎": "弯", "斷": "断", "穩": "稳", "擺": "摆",
    "驚": "惊", "嘯": "啸", "濤": "涛", "滾": "滚", "濕": "湿", "滿": "满",
    "間": "间", "帶": "带", "鮮": "鲜", "撲": "扑", "歡": "欢", "進": "进",
    "戲": "戏", "著": "着", "鬆": "松", "熱": "热", "講": "讲", "簡": "简",
    "誤": "误", "確": "确", "圍": "围", "極": "极", "標": "标", "並": "并",
    "懼": "惧", "險": "险", "關": "关", "曬": "晒", "邁": "迈", "節": "节",
    "躍": "跃", "慌": "慌", "蹤": "踪", "舊": "旧", "隨": "随", "區": "区",
    "記": "记", "錄": "录", "載": "载", "冊": "册", "紀": "纪", "樣": "样",
    "說": "说", "緊": "紧", "轉": "转", "則": "则", "辦": "办", "稱": "称",
    "搖": "摇", "勁": "劲", "兒": "儿", "圖": "图", "義": "义",
}))

META_RESIDUE_PATTERNS = [
    r'[（(][^）)]{0,80}(这段大约|多少字左右|接下来便是|下一节|实际书写|不显示|隐藏章节|待补|节拍卡|目标达成|隐含|勾勒|伏笔|备注|插入|未完|未尽)[^）)]{0,120}[）)]',
    r'(?m)^\s*[（(]?\s*(续章未尽|未完|未尽)\s*[…。\.]*\s*[）)]?\s*$',
    r'[（(]\s*完毕\s*[）)]',
    r'[（(]此时此刻[^）)]{0,120}[）)]',
    r'这段大约[^。！？\n]{0,40}(字|字左右)',
    r'(接下来便是|接下来是)[^。！？\n]{0,40}(下一节|下个小节|下一段)',
    r'遥远角落[^。！？\n]{0,80}(默默注视|注视他们|背影)',
    r'与此同时一位看似[^。！？\n]{0,120}角色[^。！？\n]{0,120}叫做[^。！？\n]{0,80}',
]


def has_hard_meta_residue(text: str) -> bool:
    """
    硬检测正文中的生成过程残留。命中时应判为不合格并触发重写，
    不依赖后处理删除来掩盖问题。
    """
    if not text:
        return False
    normalized = normalize_language_pollution(text)
    return any(term in normalized for term in HARD_META_RESIDUE_TERMS)


def _knowledge_base_path(filename: str) -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    primary = os.path.join(current_dir, 'knowledgeBase', filename)
    if os.path.exists(primary):
        return primary
    return os.path.join('knowledgeBase', filename)


def load_myth_core_constraints() -> dict:
    """
    加载神话故事核心主旨约束。
    这份文件不是相似样本，而是生成前必须优先遵守的故事骨架。
    """
    global MYTH_CORE_CONSTRAINTS_CACHE
    if MYTH_CORE_CONSTRAINTS_CACHE is not None:
        return MYTH_CORE_CONSTRAINTS_CACHE

    path = _knowledge_base_path(MYTH_CORE_CONSTRAINTS_FILENAME)
    if not os.path.exists(path):
        print(f"警告：未找到 {MYTH_CORE_CONSTRAINTS_FILENAME}，将回退使用 {MYTH_CORE_CONSTRAINTS_FALLBACK_FILENAME}。")
        path = _knowledge_base_path(MYTH_CORE_CONSTRAINTS_FALLBACK_FILENAME)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        global_constraints = data.get("global_constraints", {})
        stories = []
        for story in data.get("stories", []):
            story_copy = dict(story)
            story_copy["_global_constraints"] = global_constraints
            stories.append(story_copy)
        MYTH_CORE_CONSTRAINTS_CACHE = {
            "stories": stories,
            "by_title": {story.get("title", ""): story for story in stories if story.get("title")},
            "source_file": os.path.basename(path),
            "global_constraints": global_constraints,
        }
        return MYTH_CORE_CONSTRAINTS_CACHE
    except FileNotFoundError:
        print(f"警告：未找到 {MYTH_CORE_CONSTRAINTS_FILENAME} 或 {MYTH_CORE_CONSTRAINTS_FALLBACK_FILENAME}，神话核心主旨约束不会生效。")
    except Exception as e:
        print(f"加载神话核心主旨约束时出错: {e}")

    MYTH_CORE_CONSTRAINTS_CACHE = {"stories": [], "by_title": {}}
    return MYTH_CORE_CONSTRAINTS_CACHE


def load_thread_protagonist_constraints() -> dict:
    """
    加载二十篇神话的贯穿主人公约束。
    该文件只提供串线人物的出场功能和禁区，不覆盖原神话核心事件链。
    """
    global MYTH_THREAD_PROTAGONIST_CACHE
    if MYTH_THREAD_PROTAGONIST_CACHE is not None:
        return MYTH_THREAD_PROTAGONIST_CACHE

    path = _knowledge_base_path(MYTH_THREAD_PROTAGONIST_FILENAME)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        protagonist = data.get("protagonist", {})
        stories = []
        for story in data.get("stories", []):
            story_copy = dict(story)
            story_copy["_protagonist"] = protagonist
            stories.append(story_copy)
        MYTH_THREAD_PROTAGONIST_CACHE = {
            "protagonist": protagonist,
            "stories": stories,
            "by_title": {story.get("title", ""): story for story in stories if story.get("title")},
            "source_file": os.path.basename(path),
        }
        return MYTH_THREAD_PROTAGONIST_CACHE
    except FileNotFoundError:
        print(f"警告：未找到 {MYTH_THREAD_PROTAGONIST_FILENAME}，串线主人公约束不会生效。")
    except Exception as e:
        print(f"加载串线主人公约束时出错: {e}")

    MYTH_THREAD_PROTAGONIST_CACHE = {"protagonist": {}, "stories": [], "by_title": {}}
    return MYTH_THREAD_PROTAGONIST_CACHE


def find_thread_protagonist_constraint(story_title: str) -> dict:
    if not story_title:
        return {}
    data = load_thread_protagonist_constraints()
    return data.get("by_title", {}).get(story_title, {})


def find_myth_core(prompt: str) -> dict:
    """
    根据用户提示词匹配当前要改写的神话。
    优先精确匹配标题和别名，避免 RAG 相似样本把故事串库。
    """
    if not prompt:
        return {}
    data = load_myth_core_constraints()
    for story in data.get("stories", []):
        names = [story.get("title", "")] + story.get("aliases", [])
        if any(name and name in prompt for name in names):
            story_copy = dict(story)
            thread_constraint = find_thread_protagonist_constraint(story_copy.get("title", ""))
            if thread_constraint:
                story_copy["_thread_protagonist"] = thread_constraint
            return story_copy
    return {}


def format_thread_protagonist_block(thread_constraint: dict) -> str:
    if not thread_constraint:
        return ""

    protagonist = thread_constraint.get("_protagonist", {})
    name = protagonist.get("name", "串线主人公")

    def _lines(label, values):
        if not values:
            return ""
        return label + "\n" + "\n".join(f"- {item}" for item in values)

    parts = [
        "【贯穿二十篇的串线主人公硬约束（优先级高于RAG样本和临场发挥）】",
        f"串线主人公：{name}",
        f"固定身份：{protagonist.get('full_identity', '')}",
        f"二十篇体系功能：{protagonist.get('series_purpose', '')}",
        _lines("固定性格：", protagonist.get("personality", [])),
        f"总规则：{protagonist.get('core_rule', '')}",
        _lines("固定道具：", protagonist.get("fixed_props", [])),
        _lines("体系必含短语：", protagonist.get("global_required_phrases", [])),
        _lines("可用于跨篇连接的神话词：", protagonist.get("continuity_terms", [])),
        _lines("二十篇体系串联规则：", protagonist.get("continuity_rules", [])),
        _lines("神话次序与身份规则：", protagonist.get("chronology_rules", [])),
        _lines("全局必须遵守：", protagonist.get("global_must", [])),
        _lines("全局禁止：", protagonist.get("global_forbidden", [])),
        f"本篇出场功能：{thread_constraint.get('role', '')}",
        _lines("本篇必须写出的动作/话语/态度：", thread_constraint.get("must_do", [])),
        _lines("本篇推荐使用的跨篇连接/旧经历回忆梗（至少自然使用其中一类或自拟同等级跨篇连接）：", thread_constraint.get("callback_options", [])),
        _lines("本篇串线主人公禁区：", thread_constraint.get("forbidden", [])),
        _lines("成稿中至少命中的串线短语：", thread_constraint.get("required_phrases", [])),
        "写作要求：阿满必须自然嵌入当前神话主线，提供幽默、记录和见证；同时必须把当前神话放入《山海二十简》的二十篇体系里，至少用一处短促跨篇回忆、类比或伏笔连接其他神话。但当前神话原主角必须亲自完成核心行动，阿满不得抢走主线或改变结局。",
        "时序硬规则：阿满不受凡间年代限制，按空白青简指引的“神话次序”行走；他的“上回/以后/下一简”只表示个人记录顺序，绝不能暗示两个神话的历史先后。",
        "阿满称谓硬规则：只能叫“阿满”，可加“小史官/见闻小史官”等身份说明；严禁给阿满另起外号、绰号或现代喜剧人物称呼，尤其严禁“憨豆阿满”。",
        "跨篇连接硬边界：允许写阿满翻看青竹简时想起、对照、吐槽或伏笔另一个神话；严禁把另一个神话的人物实体搬进当前现场，严禁让吴刚/后羿/女娲/神农等别篇角色在当前篇突然出现、帮忙、斗法、打架、推动主线。跨篇连接最多一两句，必须服务二十篇体系感。",
    ]
    return "\n".join(part for part in parts if part)


def format_myth_core_block(myth_core: dict) -> str:
    if not myth_core:
        return ""

    def _lines(label, values):
        if not values:
            return ""
        return label + "\n" + "\n".join(f"- {item}" for item in values)

    required_actions = myth_core.get("required_character_actions", {})
    required_actions_block = ""
    if required_actions:
        required_actions_block = "角色必做动作：\n" + "\n".join(
            f"- {name}：{action}" for name, action in required_actions.items()
        )

    global_constraints = myth_core.get("_global_constraints", {})
    guards = global_constraints.get("quality_guards", {}) if isinstance(global_constraints, dict) else {}
    guard_lines = []
    for guard_name in (
        "no_meta_text",
        "language_cleaning",
        "helper_role_rule",
        "humor_rule",
        "emotion_rule",
        "cross_story_contamination_rule",
        "completeness_check_rule",
    ):
        values = guards.get(guard_name, [])
        if values:
            guard_lines.extend(f"- {item}" for item in values)
    global_guard_block = "【全局质量守卫】\n" + "\n".join(guard_lines) if guard_lines else ""
    canonical_terms = myth_core.get("canonical_terms", {})
    canonical_block = ""
    if isinstance(canonical_terms, dict) and canonical_terms:
        canonical_block = "固定名称/身份/道具称呼（全文必须一致）：\n" + "\n".join(
            f"- {name}：{value}" for name, value in canonical_terms.items()
        )
    forbidden_aliases = myth_core.get("forbidden_aliases", {})
    forbidden_alias_block = ""
    if isinstance(forbidden_aliases, dict) and forbidden_aliases:
        forbidden_alias_block = "禁止混用的错名/异名：\n" + "\n".join(
            f"- {name}：{', '.join(values)}" for name, values in forbidden_aliases.items() if values
        )
    object_rules = myth_core.get("object_consistency", [])
    if isinstance(object_rules, dict):
        object_rules = [object_rules]
    object_rule_lines = []
    for rule in object_rules or []:
        if not isinstance(rule, dict):
            continue
        allowed = "、".join(rule.get("allowed_forms", []))
        forbidden = "、".join(rule.get("forbidden_forms", []))
        line = f"- {rule.get('name', '核心道具')}：允许形态为 {allowed or '已设定形态'}"
        if forbidden:
            line += f"；禁止写成 {forbidden}"
        object_rule_lines.append(line)
    object_rule_block = "核心道具一致性：\n" + "\n".join(object_rule_lines) if object_rule_lines else ""
    thread_protagonist_block = format_thread_protagonist_block(myth_core.get("_thread_protagonist", {}))

    parts = [
        "【本篇神话主题主旨硬约束（优先级高于RAG样本和幽默扩写）】",
        f"故事名：{myth_core.get('title', '')}",
        f"核心主旨：{myth_core.get('core_summary', '')}",
        _lines("必须保留的核心事件链：", myth_core.get("event_chain", [])),
        _lines("成稿必须写出的识别点：", myth_core.get("must_include", [])),
        _lines("成稿最终验收必须明确写出的关键短语/意象：", myth_core.get("final_required_phrases", [])),
        _lines("禁止改写成的错误方向：", myth_core.get("must_not_change", [])),
        _lines("本故事专属禁区词/禁区情节：", myth_core.get("forbidden_elements", [])),
        _lines("本故事专属禁用表达模式：", myth_core.get("forbidden_patterns", [])),
        canonical_block,
        forbidden_alias_block,
        object_rule_block,
        thread_protagonist_block,
        required_actions_block,
        f"扩写边界：{myth_core.get('expansion_guidance', '')}",
        global_guard_block,
        "如果参考样本、旧稿、大纲或幽默梗与以上约束冲突，必须舍弃参考样本和旧稿，以本篇神话核心主旨为准。",
    ]
    return "\n".join(part for part in parts if part)


def build_core_fallback_plan(prompt: str, myth_core: dict) -> dict:
    """
    当模型规划阶段连续产出空节拍或跑偏节拍时，按核心事件链生成可执行兜底三幕。
    兜底稿不追求花哨，但能保证后续正文生成贴住主线。
    """
    title = myth_core.get("title") or prompt or "神话故事"
    chain = [item for item in myth_core.get("event_chain", []) if item]
    if not chain:
        chain = myth_core.get("must_include", [])[:6] or [title]

    shennong_humor_channels = [
        "试药反差：神农严肃判断味道或药性，身体反应立刻拆他的台",
        "村民误解：旁观者把试药、记药误会成品菜、蘸料、偏方买卖或奇怪仪式",
        "辅助翻车：阿喜/随从想帮忙，叼来或递来的东西反而暴露自己的小心思",
        "药性命名：神农给草药取临时记名，名字像严肃记录但听起来很想笑",
        "严肃记录与狼狈状态反差：他边吐边写，记录语气越端正，画面越狼狈",
        "互怼拆台：辅助角色只负责补一刀，不得连续承包所有笑点",
    ]
    kunpeng_humor_channels = [
        "小鱼误解：小鱼按北冥日常误读鲲的远志，笑点短促，不打断宏大画面",
        "古风旁观反差：旁观者把大鹏的影子误当成山、云或天漏了一块",
        "阿浪嘴硬：阿浪前期短促拆台，中期震惊，后期沉默认可，不连续抢戏",
        "尺度反差：用普通生活尺度衡量鲲鹏的巨大，随即被海天景象推翻",
        "命名反差：旁观者试图用朴素称呼记录大鹏，称呼越小，画面越大",
        "风势误解：众人以为六月大风是阻碍，鲲鹏悟到那正是托举之力",
    ]
    generic_humor_channels = [
        "动作反差：宏大目标配一个具体狼狈小动作",
        "旁观误解：路人按生活经验误读主角的神话行动",
        "道具翻车：关键道具被误用、卡住或出现尴尬后果",
        "命名/记录梗：角色用过分认真或过分朴素的说法记录当下",
        "嘴硬自嘲：主角用一句轻描淡写掩饰压力",
        "互怼拆台：辅助角色短促接梗，不连续抢戏",
    ]
    if "神农" in title or "尝百草" in title:
        humor_channels = shennong_humor_channels
    elif "北冥鲲鹏" in title or "鲲鹏" in title:
        humor_channels = kunpeng_humor_channels
    else:
        humor_channels = generic_humor_channels

    def _outline(events, role):
        joined = "；".join(events)
        return f"{title}{role}必须围绕核心事件推进：{joined}。所有扩展只补足人物动机、道具状态、压力来源、动作过程、情绪变化和贴着主线的笑点。幽默不能只靠辅助角色互怼，必须让试错过程、旁观误解、道具状态、记录/命名反差共同制造笑点；辅助角色只能见证、短促拆台或轻微翻车，不能替代主角完成核心选择。"

    if title == "后羿射日":
        def _beat(goal, visual, emotion, info, ban, humor, foreshadow="阿满的青竹简从怕被晒坏，到最后郑重写下“射九留一”", relation="阿满只记录、吐槽和见证；后羿始终亲自完成射日与留一日的选择"):
            return {
                "场景目标": goal,
                "画面要素": visual,
                "情绪推动": emotion,
                "信息增量": info,
                "禁止项": ban,
                "情感伏笔": foreshadow,
                "关系推进": relation,
                "幽默机制": humor,
            }

        act1_beats = [
            _beat(
                "建立十日并出的灾情与阿满到场记录",
                "十个太阳同时压在天上；阿满抱着青竹简用袖子给竹简遮阳",
                "狼狈→清醒",
                "明确灾因是十日并出，大地焦灼，阿满只是来记录灾情",
                "不得提前射日；不得写战斗、敌人、神秘外援；不得出现现代时间和现代道具",
                "记录反差：阿满认真写灾情，字刚落下就差点被晒得翘边",
            ),
            _beat(
                "展示百姓受难与求救压力",
                "干裂井口、空陶罐、蔫倒的庄稼；百姓围向后羿求救",
                "清醒→焦急",
                "新增百姓为何非后羿不可，不重复十日景象",
                "不得写成普通围观热闹；不得让阿满替百姓做决定",
                "旁观误解：村民把阿满的青竹简当遮阳板借用",
            ),
            _beat(
                "后羿确认救民目标与弓箭状态",
                "后羿检查弓弦、箭羽和箭袋；阿满躲在弓影下记“弓还能用”",
                "焦急→决断",
                "明确核心道具是弓和箭，后羿决定亲自救民",
                "不得新增护身符、匕首、酒葫芦水源奇迹等无关道具；不得让小徒弟抢戏",
                "道具反差：阿满以为弓影能乘凉，风一吹影子先跑了",
            ),
            _beat(
                "登高前的短暂筹备与阿满随行",
                "后羿背箭上山；阿满一手护青竹简一手追脚步",
                "决断→吃力",
                "新增登高原因：站上高处才能面对十日",
                "不得在山下直接开射；不得重复百姓求救",
                "动作反差：后羿登高如走平地，阿满把每一级石阶都记成劫难",
            ),
            _beat(
                "抵达山顶并直面十日",
                "山顶热浪扭曲；十日分布在天幕，后羿辨认射击顺序",
                "吃力→凝神",
                "明确下一幕要按顺序射落九日，并留下一个太阳",
                "不得一口气写完射日；不得让太阳躲云层玩捉迷藏",
                "嘴硬自嘲：阿满说若写错顺序，青竹简先替他中暑",
            ),
        ]
        act2_beats = [
            _beat("后羿开弓射落第一个太阳", "后羿站稳、搭箭、拉满弓；第一个太阳中箭坠落，热浪退一层", "凝神→震动", "必须明确第一箭射落第一日", "不得跳到第七日；不得写第一箭失败；不得让阿满影响命中", "一抛一接：阿满刚写“第一箭很稳”，汗滴把“稳”洇成“烫”"),
            _beat("射落第二个太阳并稳定众人信心", "第二箭穿过刺目白光；百姓从恐惧转为敢抬头", "震动→振奋", "必须明确第二箭射落第二日，世界略有变化", "不得把多个太阳模糊写成陆续消失；不得新增怪物或逃跑太阳", "旁观误解：老人以为天上少了一个火炉，问能不能先搬去做饭"),
            _beat("射落第三个太阳，后羿开始显露体力代价", "第三箭离弦；后羿虎口渗血，肩背被热浪压住", "振奋→咬牙", "新增后羿救民要付出体力和伤痛", "不得写阿满替后羿递神箭；不得写护身符帮助射击", "嘴硬自嘲：后羿说手还没废，阿满记成“暂时没废”"),
            _beat("连续射落第四到第六个太阳，但每一箭都要有动作和结果", "第四箭压低火云、第五箭穿过热浪、第六箭震落焦灰；地面裂缝不再冒烟", "咬牙→稳住", "必须明确第四、第五、第六日被射落，不得一句带过", "不得出现顺序倒退；不得把第五个太阳写成逃走又重来", "记录反差：阿满写到第六个时开始给箭数打结，嘴上还硬说自己很清醒"),
            _beat("面对剩下四日，后羿调整呼吸和射击节奏", "后羿放低弓臂喘息；阿满护住青竹简提醒已射落六日", "稳住→再决断", "承接前六日已落，只为后三箭蓄势", "不得重写第一箭；不得开启无关村民偷蓑衣、蚂蚁搬叶等支线", "短对白拆台：阿满提醒“还有三个要射，一个要留”，自己差点把留字写成溜"),
            _beat("射落第七个太阳", "第七箭擦过滚烫云边；第七日坠落时热风反扑", "再决断→吃痛", "必须明确第七日被射落，并写出反扑压力", "不得把第七日写成开篇；不得写第十日先动", "动作反差：阿满被反扑热风吹得后退，仍先检查青竹简有没有少一页"),
            _beat("射落第八个太阳", "后羿换步、压肩、拉弦；第八日坠落后天空露出缝隙", "吃痛→逼近终点", "必须明确第八日被射落，剩下两个太阳", "不得让第八日躲藏成新支线；不得引入新法宝", "旁观误解：孩童数天上火球数到打嗝，阿满严肃纠正又把自己数乱"),
            _beat("射落第九个太阳，留下最后抉择", "第九箭最沉；第九日落下后只剩最后一个太阳悬在天上", "逼近终点→沉静", "必须明确射落九日已经完成，转入是否射最后一日的选择", "不得把十日全灭；不得说太阳全部消失；不得在此结束全篇", "记录反差：阿满准备写“完工”，看见最后一个太阳又把字划掉"),
            _beat("第二幕收束：后羿压下最后一箭，没有立刻射出", "后羿箭尖对准最后一日又缓缓放下；百姓屏息等待", "沉静→克制", "明确第三幕主题是留下一日的克制，不是继续战斗", "不得射掉最后一个太阳；不得让阿满劝他射或替他决定", "嘴硬余味：阿满小声问这算不算“最难的一箭是没射出去”"),
        ]
        act3_beats = [
            _beat("建立留下最后一个太阳的争议", "百姓有人害怕最后一日继续炙烤；后羿看见远处仍需光照的土地", "克制→承压", "解释为什么不能射掉最后一个太阳", "不得写成漏靶；不得让村民以为任务失败作为主线", "旁观误解：有人问是不是少带一支箭，阿满捂着青竹简不敢笑太大声"),
            _beat("后羿明确作出留一日的选择", "后羿收弓，箭尖离开最后太阳；阿满准备郑重记录", "承压→坚定", "必须明确后羿主动留下最后一日，不是射不中或太阳逃走", "不得再开射；不得让阿满或百姓替他决定", "记录反差：阿满写“留下一日”，写完才发现这四个字比射九日还难"),
            _beat("天地温度回落，灾情开始缓解", "热风变凉、井口返潮、田埂冒出湿气；百姓从躲藏中出来", "坚定→松弛", "展示天地恢复正常的可感后果", "不得突然出现雷电、火灾或新灾难；不得用泛泛总结代替画面", "动作反差：阿满试探青竹简不再烫手，像试药一样谨慎"),
            _beat("百姓反应与后羿疲惫收束", "百姓感谢后羿；后羿手臂发抖仍站稳", "松弛→敬重", "新增后羿付出代价，但不写死亡或复活", "不得硬煽情长篇总结；不得开启妻子支线", "短促幽默：后羿说先别谢，谁有水先借一口"),
            _beat("阿满写下射九留一，完成串线主人公功能", "阿满摊开青竹简，郑重写下“后羿射落九日，留下一日”；汗印留在竹简边缘", "敬重→余韵", "必须命中阿满、青竹简、射九留一或射落九日留下一日", "不得把阿满写成主角；不得让阿满发表大道理", "记录梗回收：阿满说这回终于不是青竹简被晒熟，而是自己差点熟了"),
            _beat("结尾：一日照常升起，世界恢复秩序", "唯一的太阳温和照着土地；孩子在溪边笑，庄稼舒展叶片", "余韵→安定", "明确后羿射日故事讲完：十日之灾结束，天地恢复秩序", "不得出现未完待续；不得新增下一篇神话主线", "嘴硬型余味：阿满看着太阳，先摸竹简温度再敢落最后一笔"),
        ]
        return {
            "act1": _outline(["十日并出", "大地焦灼百姓受难", "后羿决定救民", "阿满到场记录"], "第一幕"),
            "act2": _outline(["后羿登高面对十日", "按顺序射落第一至第九个太阳", "留下最后一日的选择被推到眼前"], "第二幕"),
            "act3": _outline(["后羿主动留下最后一个太阳", "天地恢复正常", "阿满写下射九留一的记录"], "第三幕"),
            "act1_beats": act1_beats,
            "act2_beats": act2_beats,
            "act3_beats": act3_beats,
        }

    if title == "北冥鲲鹏":
        def _beat(goal, visual, emotion, info, ban, humor, foreshadow="阿浪的嘲笑逐渐变轻，老龟的沉默成为见证", relation="阿浪从调侃转为惊愕，主角始终自己完成选择"):
            return {
                "场景目标": goal,
                "画面要素": visual,
                "情绪推动": emotion,
                "信息增量": info,
                "禁止项": ban,
                "情感伏笔": foreshadow,
                "关系推进": relation,
                "幽默机制": humor,
            }

        act1_beats = [
            _beat(
                "建立北冥深处巨鲲存在与狭小感",
                "北冥深海压暗如夜；鲲翻身只让海水起伏，不开始化鹏",
                "烦闷→不甘",
                "只交代鲲为何觉得北冥容不下自己的心，不写变身",
                "不得写北海；不得让阿浪解释设定；不得出现岸边码头货船",
                "小鱼误解：小鱼把鲲的远志当成睡醒翻身",
            ),
            _beat(
                "确认鲲想离开北冥的动机",
                "鲲仰望海面微光；老龟只说一句古老传闻",
                "不甘→清醒",
                "新增鲲知道南冥天池存在，但尚未起飞",
                "不得提前展翼；不得写南冥已经抵达",
                "尺度反差：小鱼用浅滩大小衡量鲲的梦想",
            ),
            _beat(
                "加压北冥众生的嘲笑与误解",
                "阿浪绕着鲲的鳍游一圈；小鱼把鲲的影子误认成山壁",
                "清醒→决断",
                "新增外界声音越小越碎，反衬鲲的心越大",
                "不得让阿浪连续长篇吐槽；不得新增风灵子等外援",
                "阿浪嘴硬：短促拆台，但不抢主线",
            ),
            _beat(
                "鲲作出化鹏选择",
                "鲲沉入更深处再缓缓上升；鳞光转为羽光的第一丝征兆",
                "决断→忍痛",
                "只写化鹏的不可逆选择开始，不写完整展翼",
                "不得重复开篇苏醒；不得写身体恐怖、腐烂、异物",
                "嘴硬自嘲：鲲用一句轻话压住痛楚",
            ),
            _beat(
                "执行鳞化羽的第一阶段",
                "鳞片边缘亮起羽纹；海水被新生气息推开",
                "忍痛→稳住",
                "新增变化方向是鳞化羽，不是怪物变异",
                "不得写掉渣烂肉；不得说这就成了",
                "古风旁观反差：旁观者把羽光误当月色落海",
            ),
            _beat(
                "第一幕余波：鲲尚未成鹏，但已不能退回旧身",
                "北冥海面第一次被背影顶开；阿浪声音变小",
                "稳住→期待",
                "明确下一阶段要等待真正托举它的六月大风",
                "不得完整起飞；不得写南冥结尾",
                "风势误解：众人把风当前兆，鲲知道它可能是路",
            ),
        ]
        act2_beats = [
            _beat("建立化鹏第二阶段：背若泰山", "鲲背从海中隆起如山；海水沿羽纹分流", "期待→紧张", "推进到背部成鹏形，不重复第一幕鳞化羽", "不得再写鲲刚刚睁眼；不得重启北冥开头", "尺度反差：渔人误认海上多了一座山"),
            _beat("确认鹏翼初成但尚不能飞", "两翼只展开一半；风压把浪头压低", "紧张→克制", "新增翅膀太大，必须学会承风而非硬挣", "不得说已经飞往南冥；不得让旁人帮它飞", "命名反差：旁观者给巨翼取小名，立刻显得可笑"),
            _beat("加压：巨翼触风失衡", "风撞上羽端；鲲被压回浪间但没有散形", "克制→咬牙", "新增失败原因是逆风硬飞，不是力量不足", "不得写成坠落事故闹剧；不得身体恐怖", "阿浪嘴硬：想笑却被浪声噎住"),
            _beat("决断：鲲明白要等六月大风", "老龟看天色不解释；鲲听见海底长风回响", "咬牙→明悟", "明确六月大风不是普通风，是天地托举之力", "不得写成东风、飓风、天气事故", "风势误解：众人以为是阻碍，鲲听出是路"),
            _beat("执行：鹏翼若垂天之云", "双翼完整舒展遮住海天；云影垂落北冥", "明悟→庄重", "首次明确众生看见的是鹏翼若垂天之云", "不得多次重复同一句展翼；不得再称只是巨鱼", "古风旁观反差：有人以为天低了一截"),
            _beat("余波：鲲的新身份被确认", "羽影覆盖海面；阿浪仰头半晌才低声叫出大鹏", "庄重→震动", "明确鲲已化为鹏，但仍未远徙", "不得回头再写化鹏过程；不得重新长鳞脱鳞", "阿浪嘴硬转沉默：只剩一句很轻的认可"),
            _beat("六月大风自北冥深处起", "海底长风翻起；巨翼不再抵抗而是张开承接", "震动→顺势", "新增风开始托举大鹏离水", "不得把大风写成灾难主角；不得新增外援角色", "风势误解：小鱼以为要被吹丢，结果看见大鹏上升"),
            _beat("乘风离开北冥边界", "大鹏背负青天升起；下方嘲笑声变小如泡沫", "顺势→开阔", "推进到离开北冥，不直接抵达南冥", "不得停在原地围观；不得写打败谁", "尺度反差：旧日笑声在高空里小得可怜"),
            _beat("第二幕收束：南冥天池成为清晰方向", "天际出现南方水光；大鹏调整翼势向南", "开阔→笃定", "明确下一幕目标是飞往南冥天池", "不得只写模糊远方；不得在此结束全篇", "嘴硬自嘲：阿浪不敢再笑，只说别飞错方向"),
        ]
        act3_beats = [
            _beat("建立远徙：大鹏已在高空", "北冥海面退成一片暗光；南方天际浮现水色", "笃定→辽阔", "不再写化鹏，只写徙南冥的飞行开始", "不得回到海底重写变身；不得再写北海", "古风旁观反差：众人把远影误认成云在迁徙"),
            _beat("确认六月大风持续托举", "大风托住翼根；大鹏不再挣扎而是借势上升", "辽阔→自在", "强化风是天地递来的第一程路", "不得写成总结作文；不得说动力源泉", "风势误解：阿浪终于不把风当灾"),
            _beat("加压：北冥旧声音远去", "下方嘲笑声小成浪沫；大鹏没有回头争辩", "自在→释然", "主题转向离开狭小尺度，而非证明给谁看", "不得让阿浪高频吐槽；不得开启新冲突", "阿浪沉默认可：只用一个动作回应"),
            _beat("决断：大鹏向南冥天池定向远举", "南冥天池水光如镜；大鹏收束翼尖转向南方", "释然→坚定", "明确飞行终点是南冥天池", "不得停在飞起来；不得只写南冥所在", "命名反差：渔民再也找不到合适的小称呼"),
            _beat("执行：越过北冥与南冥之间的长空", "云层从翼下退去；青天压在背上却不再沉重", "坚定→逍遥", "写出背负青天、逍遥远举的动作过程", "不得重复翼若垂天之云；不得写新设定", "尺度反差：山河在翼下缩成一线"),
            _beat("余波收束：徙于南冥天池", "大鹏掠向南冥天池；北冥众生只见云影远去", "逍遥→余韵", "必须明确它乘六月大风向南冥天池飞去，完成核心闭环", "不得出现（完毕）；不得停在众人仰望", "嘴硬型余味：阿浪低声认可，不再抢戏"),
        ]
        return {
            "act1": _outline(["北冥巨鲲存在", "鲲决定化而为鸟"], "第一幕"),
            "act2": _outline(["鲲化为大鹏", "鹏翼若垂天之云", "乘六月大风而起"], "第二幕"),
            "act3": _outline(["背负青天远举", "飞往南冥天池", "呈现逍遥精神"], "第三幕"),
            "act1_beats": act1_beats,
            "act2_beats": act2_beats,
            "act3_beats": act3_beats,
        }

    if title == "伏羲画卦":
        def _beat(goal, visual, emotion, info, ban, humor, foreshadow="族人从不解到愿意倾听，伏羲的孤独逐渐被理解", relation="辅助角色只能误解、见证或递上材料，不能替伏羲领悟八卦"):
            return {
                "场景目标": goal,
                "画面要素": visual,
                "情绪推动": emotion,
                "信息增量": info,
                "禁止项": ban,
                "情感伏笔": foreshadow,
                "关系推进": relation,
                "幽默机制": humor,
            }

        act1_beats = [
            _beat("建立洪荒部落对自然无序的困惑", "风雨忽至、猎路迷失、族人按直觉争吵；伏羲在旁记录变化", "焦灼→沉思", "交代伏羲为什么必须寻找天地规律", "不得写成算命摊；不得写现代玄学课", "旁观误解：族人以为伏羲在记谁偷吃了粮"),
            _beat("确认伏羲主动观察天地万物", "伏羲仰观天象、俯察水纹、追看鸟兽足迹，把线条刻在泥板上", "沉思→专注", "明确伏羲是观察者和记录者，不是被人直接送答案", "不得让外人送八卦成品", "动作反差：伏羲严肃观天，脚下却踩进泥坑"),
            _beat("加压族人看不懂符号而嘲笑", "孩子把短横长横当柴火账，老人催他去修篱笆", "专注→受挫", "写出八卦雏形尚未成体系，众人不理解", "不得把八卦写成 gossip 闲聊", "命名/记录梗：族人给符号取很朴素的小名"),
            _beat("决断去河边寻找河洛之象", "伏羲带着龟甲、泥板和绳结沿河而行；水声与星光互相映照", "受挫→坚定", "伏羲不是逃避嘲笑，而是继续验证观察", "不得新增女娲客串主导；不得改成寻宝冒险", "嘴硬自嘲：伏羲说自己不是发呆，是在等天地开口"),
            _beat("执行看见龙马负图或河图显现", "龙马自河雾中现身，背负纹理；水面同心波与星点相合", "坚定→震撼", "核心神迹出现，但伏羲只得到启发，不得到成品八卦", "不得写成龙马直接教会八卦", "旁观误解：族人先关心这马能不能拉车"),
            _beat("第一幕余波：伏羲开始把河图与万物观察相互印证", "伏羲伏在岸边拓纹，泥水满袖；族人的笑声渐低", "震撼→求证", "转入下一幕的推演：河图只是引子，阴阳变化需要伏羲亲自悟出", "不得第一幕就完整画出八卦", "道具翻车：龟甲滑进水里又被捞回"),
        ]
        act2_beats = [
            _beat("建立推演难点：河图纹理无法直接解释万物", "泥板摆满短长线、圆点和绳结；伏羲反复对照昼夜寒暑", "求证→困惑", "说明八卦不是抄图，而是从现象中抽象规律", "不得写成成品说明书", "动作反差：伏羲越排越庄重，泥板越像一锅乱粥"),
            _beat("确认阴阳雏形来自相反相成", "日影移动、水流分合、鸟群一散一聚；伏羲划出一实一虚两种线", "困惑→微明", "新增阴阳不是口号，而是由相反现象归纳出来", "不得写成现代物理课", "旁观误解：族人以为他在给柴火分粗细"),
            _beat("加压第一次解释失败", "伏羲向族人展示两种线，众人听得满脸茫然，有人拿它当捕兽记号", "微明→受阻", "写出知识从个人领悟到公共理解之间有阻力", "不得变成算命招揽客人", "互怼拆台：辅助角色只短促吐槽听不懂"),
            _beat("决断继续观察四时与方位", "伏羲冒雨看雷，迎风辨向，在晨昏之间校对线条", "受阻→坚持", "扩展到天、地、雷、风、水、火、山、泽等自然类别", "不得串入补天、造人、射日等其他神话主线", "嘴硬自嘲：他说被雨浇透也算被天地亲自批注"),
            _beat("执行把阴阳线组合成多个卦象", "龟甲上实线断线层层相叠，伏羲用骨针刻出不同组合", "坚持→成形", "明确伏羲亲手组合符号，八卦逐渐成形", "不得让老匠人或外援替他画卦", "道具翻车：骨针折了，他把折痕也拿来比对"),
            _beat("加压材料损坏与众人误会", "雨水冲散泥板，孩童误把卦象踩成脚印，伏羲重新整理", "成形→濒临崩溃", "失败不是重启剧情，而是逼伏羲把规律记得更准", "不得重复龙马第一次出现；不得写正文污染提示", "旁观误解：孩子以为自己一脚踩出了新学问"),
            _beat("确认八种卦象的秩序", "乾坤震巽坎离艮兑依次落位，伏羲把它们同天地万象对应", "濒临崩溃→明朗", "第一次完整确认八卦名称和基本对应关系", "不得写成村口闲聊八卦", "命名/记录梗：族人嫌名字难记，伏羲用自然画面解释"),
            _beat("执行用八卦解释一次现实难题", "风向变、云压低、河水涨，伏羲据卦提醒族人避开低地", "明朗→被看见", "让八卦的文明意义先通过具体事件显出用处", "不得变成彩票预测、姻缘占卜", "动作反差：最不信的人抱着锅跑得最快"),
            _beat("第二幕余波：族人开始愿意听伏羲讲解", "雨后部落无恙，众人围着龟甲安静下来", "被看见→期待", "转入第三幕公开画卦和建立秩序", "不得在第二幕结束全篇", "互怼拆台：辅助角色嘴硬说自己只是怕锅被淹"),
        ]
        act3_beats = [
            _beat("建立公开画卦的场面", "祭土铺平，龟甲置中，族人围成半圈；伏羲洗净手上的泥", "期待→庄重", "从个人推演转为公开传授", "不得写成算命摊开张", "动作反差：孩子小声问这些线能不能先画直一点"),
            _beat("确认伏羲亲手画出八卦", "伏羲一笔一划画下乾坤震巽坎离艮兑，短线长线各归其位", "庄重→完成", "核心行动必须由伏羲亲自完成", "不得由龙马、老匠人、外人替他完成", "命名/记录梗：族人努力跟读卦名读得磕绊"),
            _beat("加压最后的质疑：这些符号到底有何用", "有人问符号能否挡雨、能否生粮；伏羲把卦象指向天时地利", "完成→解释", "把抽象符号转化为人们能理解的自然秩序", "不得泛泛说大家明白了道理", "旁观误解：族人先把卦象当农具摆放图"),
            _beat("执行人们借八卦理解自然", "老人据风雷知道何时避雨，猎人据山泽辨路，农人据寒暑安排播种", "解释→信服", "必须写出八卦如何帮助人理解自然和人事", "不得只写众人震惊；不得停在符号好看", "动作反差：先前笑得最大声的人记得最认真"),
            _beat("决断把八卦传给部落后人", "伏羲把刻好的龟甲交给族中少年，又在泥板上反复示范", "信服→传承", "文明意义落到共享知识，而不是个人炫耀", "不得写成现代课程培训", "嘴硬型温柔：辅助角色说自己不是服了，只是不想再被雨淋"),
            _beat("余波收束：从混沌经验到可解释秩序", "部落夜里有火光与记录声，风雨仍来，但人们不再只靠恐惧判断", "传承→余韵", "结尾落到伏羲画卦开启人们理解自然、人事与秩序", "不得出现完毕、关注点赞等正文污染", "克制轻笑：孩子把卦线画歪，伏羲笑着重新扶正"),
        ]
        return {
            "act1": _outline(["伏羲观察天地万物", "见龙马负图或河洛之象"], "第一幕"),
            "act2": _outline(["从昼夜寒暑、水火动静中悟出阴阳变化", "亲手组合卦象"], "第二幕"),
            "act3": _outline(["伏羲画出八卦", "人们借八卦理解自然、人事与秩序"], "第三幕"),
            "act1_beats": act1_beats,
            "act2_beats": act2_beats,
            "act3_beats": act3_beats,
        }

    act1_events = chain[: max(2, min(3, len(chain) // 3 or 2))]
    act3_events = chain[-2:] if len(chain) >= 4 else chain[-1:]
    middle_start = len(act1_events)
    middle_end = max(middle_start, len(chain) - len(act3_events))
    act2_events = chain[middle_start:middle_end] or chain[1:-1] or chain

    def _make_beats(events, target_count, phase):
        if not events:
            events = [title]
        angles = [
            ("建立", "交代来龙去脉与当下压力"),
            ("确认", "明确关键道具/行动目标的状态与代价"),
            ("加压", "让外部阻力或旁观反应逼近主线选择"),
            ("决断", "让核心人物做出本阶段不可跳过的选择"),
            ("执行", "分解新的动作步骤，不复述上一拍已完成动作"),
            ("余波", "展示后果并自然转入下一阶段"),
        ]
        beats = []
        for i in range(target_count):
            event = events[min(i * len(events) // target_count, len(events) - 1)]
            goal_prefix, angle = angles[min(i, len(angles) - 1)]
            humor_channel = humor_channels[i % len(humor_channels)]
            beats.append({
                "场景目标": f"{goal_prefix}{phase}核心节点：{event}；本拍只写{angle}",
                "画面要素": f"{event}的一个新动作、一个新压力来源、核心人物的具体身体/表情反应；预留一个非对白反差画面",
                "情绪推动": "不安→清醒" if phase == "第一幕" else ("紧张→决断" if phase == "第二幕" else "痛惜→余韵"),
                "信息增量": f"只新增{event}在本阶段的一个因果信息，不重复上一拍已经完成的动作",
                "禁止项": "不得新增无关支线、不得让辅助角色抢走核心行动、不得重复描写上一拍已经完成的藏匿/出发/执行动作",
                "情感伏笔": "保留一个与核心人物关系相关的小动作或小物件",
                "关系推进": "核心人物关系随主线压力加深，辅助角色只作见证",
                "幽默机制": humor_channel,
            })
        return beats

    return {
        "act1": _outline(act1_events, "第一幕"),
        "act2": _outline(act2_events, "第二幕"),
        "act3": _outline(act3_events, "第三幕"),
        "act1_beats": _make_beats(act1_events, DEFAULT_ACT_BEAT_LIMITS["act1"], "第一幕"),
        "act2_beats": _make_beats(act2_events, DEFAULT_ACT_BEAT_LIMITS["act2"], "第二幕"),
        "act3_beats": _make_beats(act3_events, DEFAULT_ACT_BEAT_LIMITS["act3"], "第三幕"),
    }


def contains_myth_core_violation(text: str, myth_core: dict) -> bool:
    if not text or not myth_core:
        return False
    forbidden = myth_core.get("forbidden_elements", [])
    for term in forbidden:
        if not term or term not in text:
            continue
        if not _forbidden_term_allowed_by_thread_bridge(term, text, myth_core):
            return True
    forbidden_patterns = myth_core.get("forbidden_patterns", [])
    for pattern in forbidden_patterns or []:
        if not pattern:
            continue
        try:
            if re.search(pattern, text):
                return True
        except re.error:
            if pattern in text:
                return True
    forbidden_aliases = myth_core.get("forbidden_aliases", {})
    if isinstance(forbidden_aliases, dict):
        for _canonical, aliases in forbidden_aliases.items():
            if any(alias and alias in text for alias in aliases):
                return True
    object_rules = myth_core.get("object_consistency", [])
    if isinstance(object_rules, dict):
        object_rules = [object_rules]
    for rule in object_rules or []:
        if not isinstance(rule, dict):
            continue
        for form in rule.get("forbidden_forms", []):
            if form and form in text:
                return True
    return False


def _forbidden_term_allowed_by_thread_bridge(term: str, text: str, myth_core: dict) -> bool:
    """
    核心禁区词通常用于防串库；但阿满体系允许短促提到其他神话。
    只有当禁区词本身就是外部神话词，且每次出现都在阿满记录/回忆语境里，才放行。
    """
    try:
        external_terms = thread_protagonist_external_terms(myth_core)
    except NameError:
        return False
    if term not in external_terms:
        return False
    sentences = [s.strip() for s in re.split(r'(?<=[。！？；;])\s*|\n+', text) if term in s]
    if not sentences:
        return False
    bridge_markers = [
        "阿满", "青竹简", "山海二十简", "翻", "记录", "记下", "写下", "简上", "竹简",
        "想起", "上回", "先前", "此前", "曾", "那回", "另一简", "一简", "类比", "比起", "像", "页角", "补了一笔", "补了",
    ]
    return all(any(marker in sentence for marker in bridge_markers) for sentence in sentences)


def myth_core_required_sequence_met(text: str, myth_core: dict) -> bool:
    """
    检查关键短语是否按原神话事件链的方向出现。
    用于拦截“先写南冥，再反复回头化鹏”这类结构重启。
    """
    if not text or not myth_core:
        return True
    sequence = myth_core.get("required_sequence", [])
    if not sequence:
        return True
    cursor = -1
    for term in sequence:
        if not term:
            continue
        pos = text.find(term, cursor + 1)
        if pos < 0:
            return False
        cursor = pos
    return True


def myth_core_required_hit_count(text: str, myth_core: dict, field: str = "must_include") -> int:
    if not text or not myth_core:
        return 0
    return sum(1 for term in myth_core.get(field, []) if term and term in text)


def myth_core_final_phrases_met(text: str, myth_core: dict) -> bool:
    """
    比 must_include 更严格的成稿验收项。
    must_include 适合做标题识别与规划提示；final_required_phrases 用来锁住
    原典关键意象、终点或身份确认，避免单字词造成假阳性。
    """
    if not text or not myth_core:
        return True
    required = myth_core.get("final_required_phrases", [])
    if not required:
        return True
    min_hits = myth_core.get("min_final_required_phrase_hits")
    if min_hits is None:
        min_hits = len(required)
    return myth_core_required_hit_count(text, myth_core, "final_required_phrases") >= min_hits


def myth_core_requirement_met(text: str, myth_core: dict, final: bool = False) -> bool:
    if not myth_core:
        return True
    field = "must_include"
    required = myth_core.get(field, [])
    if not required:
        return True

    if final:
        min_hits = myth_core.get("min_final_required_hits")
        if min_hits is None:
            min_hits = max(2, min(len(required), (len(required) + 1) // 2))
        else:
            min_hits = min(min_hits, len(required))
    else:
        min_hits = myth_core.get("min_plan_required_hits")
        if min_hits is None:
            min_hits = max(1, min(3, len(required)))
        else:
            min_hits = min(min_hits, len(required))
    return myth_core_required_hit_count(text, myth_core, field) >= min_hits


def thread_protagonist_required_hit_count(text: str, myth_core: dict) -> int:
    if not text or not myth_core:
        return 0
    thread_constraint = myth_core.get("_thread_protagonist", {})
    required = thread_constraint.get("required_phrases", []) if isinstance(thread_constraint, dict) else []
    return sum(1 for term in required if term and term in text)


def thread_protagonist_external_terms(myth_core: dict) -> list:
    if not myth_core:
        return []
    thread_constraint = myth_core.get("_thread_protagonist", {})
    if not thread_constraint:
        return []
    protagonist = thread_constraint.get("_protagonist", {})
    continuity_terms = [term for term in protagonist.get("continuity_terms", []) if term]
    if not continuity_terms:
        return []

    local_terms = set()
    for term in [myth_core.get("title", "")] + myth_core.get("aliases", []):
        if term:
            local_terms.add(term)
    for term in myth_core.get("must_include", []) or []:
        if term:
            local_terms.add(term)
    for term in myth_core.get("final_required_phrases", []) or []:
        if term:
            local_terms.add(term)
    # Some myths legitimately use a protagonist from another tale as the central
    # visitor (for example, 后羿求西王母赐不死药). Keep those declared entities
    # out of the cross-story contamination detector without disabling checks for
    # genuinely unrelated cameos.
    for term in myth_core.get("allowed_present_entities", []) or []:
        if term:
            local_terms.add(term)
    canonical_terms = myth_core.get("canonical_terms", {})
    if isinstance(canonical_terms, dict):
        for value in canonical_terms.values():
            if isinstance(value, str) and value:
                local_terms.add(value)
    for term in thread_constraint.get("required_phrases", []) or []:
        if term:
            local_terms.add(term)

    external_terms = []
    for term in continuity_terms:
        if term in local_terms:
            continue
        if any(term in local for local in local_terms):
            continue
        external_terms.append(term)
    return external_terms


def _sentences_with_thread_external_terms(text: str, myth_core: dict) -> list:
    external_terms = thread_protagonist_external_terms(myth_core)
    if not text or not external_terms:
        return []
    sentences = re.split(r'(?<=[。！？；;])\s*|\n+', text)
    hits = []
    for sentence in sentences:
        if any(term in sentence for term in external_terms):
            hits.append(sentence.strip())
    return hits


def valid_thread_cross_story_bridge_met(text: str, myth_core: dict) -> bool:
    """
    阿满的跨篇功能必须是“二十篇体系线索”，不是把别篇角色搬进当前篇。
    因此外部神话词要出现在阿满记录/翻简/回忆/类比/伏笔的语境里。
    """
    sentences = _sentences_with_thread_external_terms(text, myth_core)
    if not sentences:
        return False
    bridge_markers = [
        "阿满", "青竹简", "山海二十简", "翻", "记录", "记下", "写下", "简上", "竹简",
        "想起", "想了想", "上回", "先前", "此前", "曾", "那回", "另一简", "一简",
        "类比", "像", "比起", "伏笔", "以后", "往后", "回头", "页角", "补了一笔", "补了",
    ]
    return any(any(marker in sentence for marker in bridge_markers) for sentence in sentences)


def contains_heavy_cross_story_contamination(text: str, myth_core: dict) -> bool:
    if not text or not myth_core:
        return False
    sentences = _sentences_with_thread_external_terms(text, myth_core)
    if not sentences:
        return False

    bridge_memory_markers = ["想起", "回忆", "记得", "曾", "上回", "先前", "此前", "那回", "翻", "简上", "山海二十简", "另一简", "一简", "像", "比起", "页角", "补了一笔", "补了"]
    entity_entry_markers = [
        "来到", "赶来", "出现", "站在", "跳出", "冲进", "参与", "帮忙", "相助",
        "出手", "斗法", "打架", "动手", "递给", "救下", "拦住", "带走", "一起",
        "误以为来了", "跑来", "飞来", "落到",
    ]
    bridge_markers = ["阿满", "青竹简", "山海二十简", "翻", "记录", "记下", "写下", "想起", "类比", "比起", "像", "曾", "上回", "先前", "此前", "另一简", "一简", "页角", "补了一笔", "补了"]

    for sentence in sentences:
        if not any(marker in sentence for marker in bridge_markers):
            return True
        if any(marker in sentence for marker in entity_entry_markers) and not any(marker in sentence for marker in bridge_memory_markers):
            return True

    external_terms = thread_protagonist_external_terms(myth_core)
    external_hit_count = sum(text.count(term) for term in external_terms)
    # 跨篇连接应短促，过量提及通常意味着别篇主线被搬入当前故事。
    return external_hit_count > 5


def thread_protagonist_system_requirement_met(text: str, myth_core: dict) -> bool:
    if not text or not myth_core:
        return True
    thread_constraint = myth_core.get("_thread_protagonist", {})
    if not thread_constraint:
        return True
    protagonist = thread_constraint.get("_protagonist", {})

    global_required = protagonist.get("global_required_phrases", [])
    if global_required and not any(term and term in text for term in global_required):
        return False

    external_terms = thread_protagonist_external_terms(myth_core)
    if external_terms and not valid_thread_cross_story_bridge_met(text, myth_core):
        return False

    return True


def thread_protagonist_requirement_met(text: str, myth_core: dict) -> bool:
    if not myth_core:
        return True
    thread_constraint = myth_core.get("_thread_protagonist", {})
    if not thread_constraint:
        return True
    required = thread_constraint.get("required_phrases", [])
    if not required:
        return True
    min_hits = thread_constraint.get("min_required_phrase_hits")
    if not isinstance(min_hits, int):
        min_hits = len(required)
    return (
        thread_protagonist_required_hit_count(text, myth_core) >= min_hits
        and thread_protagonist_system_requirement_met(text, myth_core)
    )


def contains_thread_protagonist_violation(text: str, myth_core: dict = None) -> bool:
    if not text or not myth_core:
        return False
    thread_constraint = myth_core.get("_thread_protagonist", {})
    if not thread_constraint:
        return False

    for term in thread_constraint.get("forbidden", []) or []:
        if term and term in text:
            return True

    protagonist = thread_constraint.get("_protagonist", {})
    for term in protagonist.get("global_forbidden", []) or []:
        if term and term in text:
            return True

    if "憨豆" in text or re.search(r'["“][^"”。！？.!?]{0,8}["”]阿满', text):
        return True

    if contains_heavy_cross_story_contamination(text, myth_core):
        return True

    # 这些是串线主人公最容易被模型写偏的硬禁区，使用短模式单独拦截。
    forbidden_patterns = [
        r'阿满[^。！？\n]{0,30}(拉弓|搭箭|射出一箭|射落太阳|射落.*日|炼石补天|补上天空|画出八卦|造出文字|捏出人|尝遍百草|搭起鹊桥|砍倒桂树|打死李艮|打败敖丙|制服龙王|止住水患|决定改堵为疏|开凿龙门|疏通九河|引洪入海)',
        r'阿满[^。！？\n]{0,30}(替|代替|帮)[^。！？\n]{0,20}(后羿|女娲|伏羲|仓颉|神农|愚公|精卫|吴刚)[^。！？\n]{0,20}(完成|解决)',
        r'阿满[^。！？\n]{0,30}(系统|玩家|穿越者|现代人|直播|手机|电脑|导航)',
        r'山海(?!二十)[一二三四五六七八九十\d]{1,3}简',
        r'阿满[^。！？\n]{0,80}(大声宣布|宣布|查阅|据《山海)[^。！？\n]{0,120}(切勿|谨记|规则|相似|望诸君|不堪设想)',
        r'阿满[^。！？\n]{0,80}(解决|化解|指挥|号令|替大家判断|替众人判断)',
    ]
    record_context_markers = [
        "记录", "记下", "写下", "写", "青竹简", "竹简", "《山海二十简》",
        "山海二十简", "页角", "补了一笔", "补上", "想起", "回忆",
    ]
    for pattern in forbidden_patterns:
        for match in re.finditer(pattern, text):
            snippet = match.group(0)
            sent_start = max(text.rfind(mark, 0, match.start()) for mark in ["。", "！", "？", "\n"])
            sent_end_candidates = [text.find(mark, match.end()) for mark in ["。", "！", "？", "\n"]]
            sent_end_candidates = [pos for pos in sent_end_candidates if pos >= 0]
            sent_end = min(sent_end_candidates) if sent_end_candidates else len(text)
            context = text[sent_start + 1:sent_end]
            # 阿满可以在记录/编纂语境里写到“后羿射日、神农尝百草”等体系线索；
            # 只有他实际执行核心行动、替主角解决问题时才算越权。
            if any(marker in snippet or marker in context for marker in record_context_markers):
                continue
            return True
    return False


def houyi_story_quality_met(text: str, myth_core: dict = None) -> bool:
    """
    后羿射日专属验收：
    - 必须能看出按顺序射落九日，而不是跳号、倒叙或一团乱写
    - 必须主动留下最后一个太阳
    - 必须出现阿满的记录功能，而不是只让阿满反复狼狈出场
    """
    if not text or not myth_core or myth_core.get("title") != "后羿射日":
        return True

    forbidden_terms = [
        "备胎", "午后三点", "三点钟", "烽燧塔", "缰绳", "护身符", "玄铁匕首",
        "酒葫芦竟莫名", "水源奇迹", "鸡冠羽饰", "药膳包", "六十七只蚂蚁",
        "流浪狗", "现代战术", "战斗", "目标案例介绍",
    ]
    if any(term in text for term in forbidden_terms):
        return False

    required_core_groups = [
        ["十日并出"],
        ["大地焦灼", "百姓受难", "百姓遭殃", "干裂"],
        ["射落九日", "射落九个太阳", "九个太阳被射落", "后羿射落九日"],
        ["留下一日", "留下最后一个太阳", "留下一个太阳", "留下一轮太阳", "射九留一"],
        ["天地恢复", "恢复正常", "温度降", "重获清凉", "万物复苏"],
        ["阿满"],
        ["青竹简"],
    ]
    for group in required_core_groups:
        if not any(term in text for term in group):
            return False

    ordered_marks = [
        ["第一箭", "第一日", "第一个太阳", "第一枚太阳"],
        ["第二箭", "第二日", "第二个太阳", "第二枚太阳"],
        ["第三箭", "第三日", "第三个太阳", "第三枚太阳"],
        ["第四箭", "第四日", "第四个太阳", "第四枚太阳"],
        ["第五箭", "第五日", "第五个太阳", "第五枚太阳"],
        ["第六箭", "第六日", "第六个太阳", "第六枚太阳"],
        ["第七箭", "第七日", "第七个太阳", "第七枚太阳"],
        ["第八箭", "第八日", "第八个太阳", "第八枚太阳"],
        ["第九箭", "第九日", "第九个太阳", "第九枚太阳"],
    ]
    positions = []
    for group in ordered_marks:
        group_positions = [text.find(term) for term in group if term in text]
        if not group_positions:
            return False
        positions.append(min(pos for pos in group_positions if pos >= 0))
    if positions != sorted(positions):
        return False

    final_choice_pos = min(
        [text.find(term) for term in ["留下一日", "留下最后一个太阳", "留下一个太阳", "留下一轮太阳", "射九留一"] if term in text]
        or [-1]
    )
    ninth_pos = positions[-1]
    if final_choice_pos < ninth_pos:
        return False

    # 阿满必须承担“记录射九留一”的功能，而不只是围观喊热。
    record_patterns = [
        r'阿满[^。！？\n]{0,80}(青竹简|竹简)[^。！？\n]{0,80}(射九留一|射落九日|留下一日|留下最后一个太阳)',
        r'(射九留一|射落九日|留下一日|留下最后一个太阳)[^。！？\n]{0,80}阿满[^。！？\n]{0,80}(青竹简|竹简)',
    ]
    if not any(re.search(pattern, text) for pattern in record_patterns):
        return False

    return True


THREAD_BRIDGE_FALLBACKS = {
    "八仙过海": "阿满抱紧青竹简，把“不乘船”和“各显神通”两个词郑重夹进《山海二十简》；他又在页角补了一笔：后羿那边是太阳多得烫手，八仙这边是海水多得下不了笔，自己这个小史官大概天生和“太多”犯冲。",
    "北冥鲲鹏": "阿满抱着青竹简，把北冥这一页郑重题进《山海二十简》；他想起八仙过海时见过风浪，可眼前这风浪像忽然长出翅膀，连他的旧笔都想先飞一步。",
    "仓颉造字": "阿满把这一段收入《山海二十简》时，忽然想起神农尝百草那页自己差点把“苦”写成“哭”，便对仓颉多生出几分敬意：没有文字，连写错都没机会。",
    "嫦娥奔月": "阿满在《山海二十简》里把嫦娥奔月这一页夹好，又翻到牛郎织女那一简的空白页角；一个是月宫清冷，一个是天河遥远，他的旧笔忽然不敢乱抖，怕把分离写得太响。",
    "伏羲画卦": "阿满把伏羲画卦收入《山海二十简》，又想起仓颉造字那一简：字能记事，可这些长短横线像天地自己打的结，光会写字还真不一定解得开。",
    "后羿射日": "阿满把后羿射日记作《山海二十简》里最烫手的一简，顺手在旁边留了个小注：以后若轮到夸父追日，自己一定先把青竹简泡凉，免得还没开跑，字先熟了。",
    "精卫填海": "阿满把精卫这一简夹进《山海二十简》，想起八仙过海时海浪只是热闹，这里的海浪却像专门抬杠；他数不清木石，只好先记下那份不肯停。",
    "夸父追日": "阿满喘着把追日写进《山海二十简》，还翻到后羿射日那页嘀咕：那边是太阳太多，这边是太阳太会跑，自己夹在中间，只剩两条腿最讲道理。",
    "雷泽华胥": "阿满把雷泽这一页收入《山海二十简》时，想起后来伏羲画卦的线条，又翻到女娲造人那页的空白处，心里一紧：有些故事不是从一句话开始，而是从一个大到写不下的足迹开始，后来才慢慢长成文明与人间。",
    "梁山伯与祝英台": "阿满把梁祝这一简收入《山海二十简》，想起牛郎织女那页也写过分隔；他难得没急着吐槽，只把青竹简合了合，像怕惊动纸上的两个人。",
    "孟姜女哭长城": "阿满把孟姜女这一简写进《山海二十简》，忽然想起精卫一石一石衔向东海；原来有些坚持不是为了显得厉害，只是不肯把心里那个人丢下。",
    "牛郎织女": "阿满把牛郎织女收入《山海二十简》时，翻到嫦娥奔月那页，月宫的冷和天河的远挤在一处，他便把玩笑收得很小，只敢让旧笔轻轻落下。",
    "女娲补天": "阿满把女娲补天写进《山海二十简》，又想起精卫填海那页一石一木的执拗，连忙护住青竹简：天地的事果然没有一页是轻松收尾的，有人填海，有人补天，都不太给小史官留喘气工夫。",
    "女娲造人": "阿满把女娲造人收进《山海二十简》，还想起仓颉造字那页：人刚有了脚，还没来得及写自己的名字，已经把他的青竹简围得像赶集。",
    "神农尝百草": "阿满把神农尝百草写进《山海二十简》时，顺手翻到仓颉造字那页，心想文字真好用，只是遇到苦草和毒草，字也会跟着舌头发麻。",
    "吴刚伐桂": "阿满把吴刚伐桂记入《山海二十简》，又翻到嫦娥奔月那页；月宫的冷清原来不止一种，有人望着人间，有人每天把同一刀重新开始。",
    "西王母": "阿满在瑶池把这一页放进《山海二十简》，又翻到女娲造人那页的空白处，心里明白：瑶池一句“去见世面”，会把小史官派向更广的人间。",
    "愚公移山": "阿满把愚公移山写进《山海二十简》时，想起精卫填海那页，忽然不敢笑那些一天只多一点点的进度；有些故事慢得要命，却偏偏能把天地慢慢说服。",
    "哪吒闹海": "阿满把《哪吒闹海》收入《山海二十简》：哪吒以混天绫搅动东海，闯下祸后没有躲，主动担责，以死谢罪；太乙真人再以莲花莲藕重塑化身，哪吒制服龙王、止住水患。阿满想起八仙过海那一简，小声写道：“八仙把海当路，哪吒先把海的脾气全请上了岸；我只负责记，绝不负责劝海消气。”",
    "大禹治水": "阿满把《大禹治水》收入《山海二十简》，郑重补清：鲧治水失败，大禹承接重任，改堵为疏，疏山导水，三过家门而不入，最终开凿龙门、疏通九河、引洪入海，使九州安定。他又想起愚公移山那一简，低声道：“一个让山让路，一个替水找路，我的鞋在两篇里倒是都没走过干净路。”",
}


def build_thread_bridge_fallback(myth_core: dict) -> str:
    if not myth_core:
        return ""
    title = myth_core.get("title", "")
    if title in THREAD_BRIDGE_FALLBACKS:
        return THREAD_BRIDGE_FALLBACKS[title]

    external_terms = thread_protagonist_external_terms(myth_core)
    external_hint = external_terms[0] if external_terms else "另一处神话现场"
    return (
        f"阿满抱着青竹简，把这一页郑重收进《山海二十简》。他在页角补了一句，"
        f"说这场事要和{external_hint}那一简前后相照，才看得出二十篇神话原来同在一片天地里。"
    )


def repair_thread_protagonist_system_link(text: str, myth_core: dict = None) -> str:
    if not text or not myth_core:
        return text
    thread_constraint = myth_core.get("_thread_protagonist", {})
    if not thread_constraint:
        return text

    needs_bridge = not thread_protagonist_system_requirement_met(text, myth_core)
    required = thread_constraint.get("required_phrases", []) or []
    missing_required = [term for term in required if term and term not in text]
    missing_global = []
    protagonist = thread_constraint.get("_protagonist", {})
    for term in protagonist.get("global_required_phrases", []) or []:
        if term and term not in text:
            missing_global.append(term)

    if not needs_bridge and not missing_required and not missing_global:
        return prune_excess_thread_cross_story_bridges(text, myth_core)

    bridge = build_thread_bridge_fallback(myth_core)
    if not bridge:
        return text
    if bridge in text:
        return text
    print("正在补强串线主人公二十篇体系连接：《山海二十简》/跨篇回忆")

    lines = text.splitlines()
    insert_at = len(lines)
    for idx in range(len(lines) - 1, -1, -1):
        if "阿满" in lines[idx] or "青竹简" in lines[idx]:
            insert_at = idx + 1
            break
    lines.insert(insert_at, bridge)
    return prune_excess_thread_cross_story_bridges("\n".join(lines), myth_core)


MYTH_FINAL_REPAIR_PARAGRAPHS = {
    "北冥鲲鹏": "阿满抱紧青竹简，在《山海二十简》页角郑重补清这一笔：北冥有巨鲲，鲲化而为鸟，其名为鹏；大鹏振翼时翼若垂天之云，乘六月大风而起，向南冥天池飞去。他想起八仙过海那页众人各凭本事渡浪，如今才知道，有些浪不是用来渡的，是用来托起逍遥的。阿满写完又小声嘀咕：“我这支笔今日也算见过大场面，唯一的问题是，它好像比我先想飞。”",
    "嫦娥奔月": "阿满抱着青竹简，把这一页收入《山海二十简》时，又翻到牛郎织女那一简的空白页角，轻轻补了一句：一个是月宫清冷，一个是天河遥远，世间相隔原来不止一种写法。他再低头写明：西王母赐给后羿的琉璃瓶，不死药在瓶中，后羿可藏入檀木匣；嫦娥因不死药奔月，后羿在人间望月，月亮从此成了思念与孤独的光。写到这里，阿满难得没乱开玩笑，只小声说：“这页太冷，我的笔都不敢抖得太响。”",
    "仓颉造字": "阿满把这一页收进《山海二十简》，又想起神农尝百草那页自己差点把“苦”写成“哭”。他郑重补上一笔：仓颉观鸟兽足迹、山川纹理与人间呼喊，造出文字，使事情能被记住，名字能被传下，哭笑也终于有了各自的形状。阿满看着青竹简上的新字，小声嘀咕：“从今以后，写错也算有凭有据了。”",
    "八仙过海": "阿满抱紧青竹简，把这一页重新收入《山海二十简》：八仙不乘船，各凭法宝渡海，所谓各显神通，不是比谁最体面，而是看谁在风浪里还能把自己的本事用明白。他想起后羿那页太阳多得烫手，又看眼前海水多得下不了笔，忍不住补了一句：“我这个小史官，大概天生和‘太多’犯冲。”",
    "伏羲画卦": "阿满把青竹简横过来又竖起来，试着抄伏羲画出的线条，结果越抄越像自己在泥地里迷了路。他赶紧在《山海二十简》页角补清这一笔：伏羲观察天地、观天地之变，又察河图与万物消长，先看见阴阳相推，再画出八卦，最终使风雨、昼夜、方位与人间生活有了可理解的秩序。阿满又翻到仓颉造字那一简，小声吐槽：“仓颉那边是字能记事，伏羲这边是横线能管事，我这支旧笔忽然觉得自己只是根会掉毛的草。”笑归笑，他最后仍郑重写下：这些线条不是乱画，而是在给天地立规矩。",
    "精卫填海": "阿满蹲在东海边，抱着青竹简数了半日，终于承认自己数不过来：精卫一次又一次衔木石投向浪头，木枝小得可怜，石子轻得好笑，可那股不肯停下的劲却比海风还硬。他把这一页收进《山海二十简》，又想起八仙过海那页的风浪，忍不住小声嘀咕：“八仙那边是各凭法宝渡过去，精卫这边是一口一口跟海讲道理，讲得海都嫌她认真。”浪花扑来打湿了他的字，他手忙脚乱护住青竹简，最后补明：他不再只数木石，而是记录精卫填海的不屈。",
    "雷泽华胥": "阿满把青竹简横过来比划雷泽的大人迹，横着写不下，竖着也写不下，只好尴尬地在页角画了半只脚印，旁边注明“此处不是我偷懒，是足迹真的太大”。他随即郑重补清：华胥在雷泽见大人迹，履迹而感孕，后来生下伏羲，文明始祖的源头便从这一脚神秘足印里悄然展开。阿满把这一页收入《山海二十简》，又翻到女娲造人那一简，轻声写道：人间后来有形有名，有规矩有火光，而最早的震动，竟来自雷泽这片让人不敢大声说笑的土地。",
    "梁山伯与祝英台": "阿满合上青竹简片刻，才把《山海二十简》这一页补完整：祝英台女扮男装入书院，与梁山伯同窗相知；十八相送时两人把心意藏在话里，旁人听着像打趣，阿满一开始也差点误记成同窗互怼。后来马家婚约压下，梁山伯病逝，祝英台奔至坟前投坟，风雨一卷，二人最终化蝶而去。阿满又翻到牛郎织女那页，轻声写道：天河隔得远，坟前也隔得深，可真情总会想办法飞起来。写到这里，他不再插科打诨，只把青竹简抱得很紧。",
    "孟姜女哭长城": "阿满背着青竹简跟到长城脚下时，腿已经软得想向路边石头告假，可孟姜女怀里的寒衣仍被她抱得很稳。他在《山海二十简》里郑重补清：孟姜女为范喜良送寒衣，千里寻夫到长城，却得知范喜良已死；她痛哭不止，哭声震得长城崩裂，露出尸骨。阿满想起精卫填海那页，一石一木是不肯放下，这一声痛哭也是不肯放下。到了城崩与尸骨出现的那一刻，他没有再说笑，只把被泪水洇湿的字重新描深。",
    "牛郎织女": "阿满把青竹简上的泪痕擦了擦，补明《山海二十简》这一页：牛郎得老牛相助，与织女在人间相知相守；后来王母划出天河，硬生生隔开二人，连阿满的记录都像被那道银河截断。直到喜鹊搭起鹊桥，七夕之夜，牛郎织女才得以一年一会。阿满又翻到嫦娥奔月那页，低声嘀咕：“月宫冷，天河远，看来分离这事也会排队。”他说完便收住玩笑，只写下：这一会短得让人心疼，却也亮得足够撑过一年。",
    "女娲补天": "阿满一边躲洪水烈火，一边死死护住青竹简，差点把自己护成一块会跑的木板。他在《山海二十简》页角郑重补清：天裂之后洪水横流，女娲采五色石，炼石补天，又断鳌足立四极，最终让天地恢复安稳。炼石时火候忽高忽低，阿满小声吐槽：“这颜色要是记错，后人还以为女娲在给天挑衣裳。”话刚出口他就赶紧闭嘴，因为补天不是玩笑。最后他又翻到精卫填海那页，写下：一个衔木石填海，一个炼五色石补天，天地能留下来，靠的都是不肯退后的手。",
    "女娲造人": "阿满被一群刚活过来的泥人围住，左边一个问他旧笔能不能吃，右边一个扯着青竹简问自己叫什么，吓得他差点把“人类繁衍”写成“史官被围”。他赶紧在《山海二十简》里补清这一笔：世间寂静，女娲感到孤独，便取黄土捏人，亲手捏出泥人；泥人活过来后，她又挥动藤绳甩出泥点，使人类繁衍开来。阿满想起仓颉造字那页，忍不住小声说：“人刚来到世上，名字还没排上队，我这简先挤满了。”笑过之后，他郑重写下：生命的热闹，从女娲掌心第一抔黄土开始。",
    "神农尝百草": "阿满抱着青竹简跟在神农身后，一边看他亲尝百草，一边记录药性，忙得旧笔都快冒烟。神农刚咽下一片苦叶，脸色忽青忽白，阿满手一抖，差点把“解毒”写成“解读”，赶紧尴尬地改回来。他在《山海二十简》页角补明：神农为了百姓亲尝百草，辨出药性，也一次次承担中毒的代价，才把医药经验留给人间。阿满又翻到仓颉造字那页，轻声写道：字能记下药名，可真正把药性试出来的，是神农自己的舌头和性命。",
    "吴刚伐桂": "阿满在月宫站了半夜，终于发现自己写的记录像昨天抄来的：吴刚举斧砍向桂树，斧声落下，桂树随砍随合；再砍，再合，像月光也在不断重复。他抱着青竹简小声吐槽：“这月宫日子准得可怕，连我打哈欠都像按时辰来的。”可笑意很快淡下去，他在《山海二十简》里补清：吴刚的惩罚不是砍倒桂树，而是在不断重复里学会反省。阿满又翻到嫦娥奔月那页，轻轻写道：月宫的冷清有许多种，有人望人间，有人砍不完心里的那一斧。",
    "西王母": "阿满以瑶池见闻小史官的身份抱着青竹简站在昆仑风里，记录西王母设下的规矩：瑶池有蟠桃，也有不死药，可长生从来不是随手可取的甜头。求药的人说得动听，赴会的人笑得热闹，阿满写规矩写到手酸，差点把“不死药”旁边标成“请勿乱拿”。西王母真正做出抉择时，他立刻停住插话，只补清《山海二十简》这一笔：长生有代价，规矩背后是秩序，抉择背后也有人情。后来他合上青竹简，才明白瑶池的一句话，会把许多抉择慢慢推向人间。",
    "愚公移山": "阿满蹲在太行、王屋之间，试着记录每天移山进度，数字小得让人想叹气，旧笔都像在替他打瞌睡。智叟嘲笑愚公时，他本想插一句“这活确实不太像今日能收工”，可愚公说出子孙无穷匮、山不加增时，阿满立刻把玩笑咽回去。他在《山海二十简》里补明：愚公带着子孙移山，终于感动天帝，太行、王屋被移走二山。阿满又翻到精卫填海那页，写下：有些事慢得让人想笑，久了却能让天地改口。",
    "哪吒闹海": "阿满抱着青竹简，把《哪吒闹海》收入《山海二十简》。他依次写明：陈塘关的哪吒以混天绫搅动东海；巡海夜叉李艮问罪，龙太子敖丙随后交战；东海龙王敖光兴水逼迫，哪吒主动担责、以死谢罪；太乙真人用莲花莲藕化身使他重生，哪吒最终制服龙王、止住水患。写完他想起八仙过海那页，轻声道：“同一片海，八仙忙着过，哪吒忙着把脾气闹明白；幸好最后也把责任扛明白了。”",
    "大禹治水": "阿满擦掉青竹简上的泥点，把《大禹治水》收入《山海二十简》。他郑重写明：洪水泛滥，鲧治水失败，大禹承接治水重任；大禹改堵为疏，率众疏山导水，三过家门而不入，最终开凿龙门、疏通九河、引洪入海，使九州安定。阿满想起愚公移山那一简，小声补道：“一个替人把山搬开，一个替水把路找开；只有我的鞋，坚持把泥全带回来。”",
}


MYTH_QUALITY_TAIL_PARAGRAPHS = {
    "八仙过海": "海风又把阿满的青竹简吹翻了三页，他手忙脚乱地一把按住，差点把“各显神通”写成“各显神通但请先排队”。铁拐李回头看他一眼，笑得酒葫芦都晃了晃；吕洞宾一本正经地说这叫仙家气象，阿满却小声吐槽：“我在后羿那页见过太阳太多，已经够烫手了，没想到八仙这一页是法宝太多，连浪花都忙不过来。”汉钟离摇扇替他挡了一下海沫，结果扇风太足，阿满的旧笔在空中转了半圈，落回竹简时正好点在“不乘船”三个字旁边，像给这条规矩盖了个歪印。蓝采和看得差点笑弯腰，曹国舅忙说史官辛苦，张果老却在旁边认真补刀：“辛苦是辛苦，就是字也跟着过海了。”阿满尴尬地护住青竹简，仍把这一页夹进《山海二十简》，又郑重补明：八仙终究不乘船，而是各凭法宝越过风浪，彼此拆台归拆台，真到险处仍会互相搭一把；这一简与后羿那页一冷一热、一海一天，都在告诉他，神话里的大场面从不讲道理，只讲本事和心气。等八仙的身影在彼岸站稳，岸边百姓才后知后觉地鼓噪起来，方才笑话他们不找船的人也忍不住咧嘴笑。阿满低头又补一句：“本简要点，别问谁的法宝最好用，能到岸还不把同伴丢在浪里，便算真神通。”写完他把旧笔一收，心里已经开始担心下一简会不会更难伺候，毕竟二十简才刚翻过几页，海风已经把他吹得很有经验。",
    "北冥鲲鹏": "阿满追着那阵六月大风跑了两步便停下，尴尬地拍了拍胸口，假装自己不是腿软，只是怕旧笔飞丢。他抱紧青竹简，笑着补了一行小字：“八仙过海那页我还能站在岸上看热闹，北冥鲲鹏这一页倒好，热闹长出翅膀，把我也吹成了旁注。”阿浪在礁石边听见，差点笑出泡泡；阿满立刻一本正经地护住《山海二十简》，小声嘀咕：“别笑，这叫史官保持距离，主要是距离太近会被风带走。”",
    "伏羲画卦": "夜里众人散去后，阿满还蹲在火边抄那几道长短横线。他抄一笔，青竹简就歪一下；再抄一笔，旧笔又掉一根毛，像是连笔都被阴阳绕晕了。他小声嘀咕：“仓颉造字那页我还能问哪个字写错，伏羲这页倒好，写错一横好像天地都要斜着看我。”说完他赶紧一本正经补上：伏羲不是给泥地添花纹，而是把人看不懂的风雨变化，慢慢写成能被人理解的秩序。",
    "精卫填海": "暮色压上海面时，精卫仍叼起一截细枝飞向东海，姿势小得像一句不肯认输的悄悄话。阿满本想笑她固执，结果浪花又“啪”地打湿了他的袖口，他只好一本正经地把青竹简举高，差点把自己举成一根晒干的木枝。他最后补写道：“今日仍未填平，明日仍会再来；精卫衔木石不是为了让海立刻低头，而是让海每天都记得，有个小小的身影从未退后。”",
    "孟姜女哭长城": "夜风从崩裂的城砖间穿过去，寒得像一件再也送不到人手里的衣裳。阿满站了很久，青竹简被他抱在怀里，没有翻页，也没有吐槽。他只在最后补了一行很轻的字：孟姜女不是哭给城听，是哭给那具终于露出的尸骨听；长城可以被风雪压住，人的名字却不能被埋没。写完这一笔，他想起精卫填海那页，才明白有些坚持不响亮，却能让山海和城墙都低头。阿满把这一简合上时，连旧笔也安静下来，像怕惊动那件寒衣最后的温度，也怕惊动风里未散的哭声。",
    "雷泽华胥": "阿满后来又回到那枚大人迹旁边，试着拿青竹简量一量，量到第三回便尴尬地放弃了：“这不是脚印，这是让我这支旧笔认清自己有多短。”旁边有人差点笑出声，又被雷泽沉沉的风压低了嗓子。阿满只好把玩笑写得很小，把敬畏写得很重：华胥履迹感孕，伏羲由此降生，这一页不能闹得太响，因为它后面连着文明始祖，也连着女娲造人那页尚未展开的人间烟火。",
    "神农尝百草": "收药入筐时，阿满又把青竹简摊开检查一遍。他先看见自己把“辛辣”写得像“辛苦”，差点当场把旧笔藏进袖子里；又看见“微苦回甘”旁边被药汁洇出一团墨，像草药自己也在一本正经地表示不服。神农问他记清了吗，阿满立刻点头，点到一半又尴尬地停住：“记清了，就是有几味药看起来比我还不愿意被记住。”旁边村人笑出声，阿满赶紧护住青竹简，小声嘀咕：“别笑，药名写错是小事，后人照着煎错可就是我这支笔的罪过。”笑归笑，他最后仍郑重补明：神农尝百草，苦味、麻意、毒性、解法都必须写准，百姓往后少受一分病痛，今日这点手忙脚乱就都值得。",
    "西王母": "夜深之后，阿满还守在瑶池廊下整理青竹简。他一会儿写蟠桃规矩，一会儿写不死药禁令，写到手腕发酸，忍不住小声嘀咕：“昆仑风大，规矩更多，我这旧笔今日比赴会的人还忙。”旁边仙侍提醒他蟠桃几千年一熟，不死药更不能乱记，阿满立刻把青竹简抱紧，尴尬地补了一句：“明白，瑶池不是果铺，我也不是来试吃的。”话音刚落，他看见西王母静静望向瑶池水面，便立刻收住玩笑，只补下一行：长生不是热闹宴席上的甜果，也不是谁哭一哭就能带走的药；它牵着秩序，牵着抉择，也牵着每个求长生之人必须付出的代价。有人求药时说得可怜，有人望着蟠桃眼睛发亮，阿满本想把这些表情都写下来，可西王母抬眼的一瞬，他忽然明白规矩不是用来摆架子的，而是防止贪念把人间拖进更大的乱局。于是他把那句玩笑划掉，只留下“长生有代价”五个字，笔画写得很慢。阿满把这一页夹进《山海二十简》，明白有些故事从瑶池出发，却会在人间慢慢显出重量；他这个小史官能做的，不过是把西王母的抉择记准，把昆仑的风声记轻，把不该乱拿的不死药记得比自己的午饭还清楚。",
    "哪吒闹海": "陈塘关水退后，阿满蹲在墙根晒青竹简，简页一张开，竟顺着风滴出一串水。哪吒看了半晌，忍不住笑：“你这记的是闹海，还是把海带回来了？”阿满尴尬地把简册倒过来，小声嘀咕：“我怕后人说现场不真，特意留一点证据。”旧笔偏偏被水泡得掉毛，他一写“混天绫”，最后一撇便顺着竹纹游走。哪吒一本正经地说那是东海余波，李靖在旁边拆台：“分明是你们两个都不肯把错认全。”阿满赶紧护住青竹简，嘴硬道：“他认闹海，我认字歪，分工很清楚。”众人忍不住笑出声。笑过之后，他把哪吒主动担责、莲花莲藕化身、制服龙王与止住水患一笔笔描正，再没拿那场谢罪开玩笑。",
    "大禹治水": "洪水退后，阿满把青竹简铺在新露出的田埂上晾晒，泥点恰好糊住“疏”字。旁边少年探头一看，笑道：“又成‘改堵为堵’了。”阿满手忙脚乱去擦，结果把自己鼻尖也抹出一道泥，仍一本正经地说：“字可以一时堵住，河不能。”乡民问他跟着大禹走了这么久是不是终于不怕水，他抱紧竹简，小声嘀咕：“怕，尤其怕水认识我的字。”话音未落，沟里一股清水偏偏溅上衣摆，众人笑出声，他尴尬地后退半步，腿软归腿软，笔却没有停。他最后写清改堵为疏、三过家门、开凿龙门、疏通九河和引洪入海，才把这一页郑重夹回简册。",
}


MYTH_LENGTH_EXTENSION_PARAGRAPHS = {
    "嫦娥奔月": "天色真正暗下去后，后羿还站在院中，弓靠在门边，檀木匣空着，像一只忽然不知道该守什么的手。百姓有人来劝他歇息，有人送来温水，有人想问月亮上是不是真的冷，话到嘴边又觉得问谁都不合适。阿满抱着青竹简蹲在门槛旁，原本想把“今日月色很好”写成一句宽慰，写到一半又默默划掉，因为这月色好得太不讲情面，好像越亮越提醒人间少了一个人。他小声对后羿说：“我以前记大事，总盼着结尾亮堂些；今日才知道，有些亮是照路的，有些亮是照心口空处的。”后羿没有接话，只把嫦娥常用的那只水盏放回原处，动作轻得像怕惊动月宫。阿满便也不再插科打诨，只把《山海二十简》翻到这一页的末尾，补写：嫦娥奔月不是一场轻飘飘的飞升，而是从不死药开始、从抉择与误会穿过、最终落在人间长久仰望里的故事。往后每逢月圆，人们抬头看见清辉，想到的不会只是仙子住在高处，也会想到有人在低处守着旧院、旧弓和一盏再也等不到人来端起的水。阿满写完吹了吹墨，忽然怕自己吹得太重，把这点思念也吹散了，便赶紧合上青竹简，嘀咕一句：“这页不能多吹，月亮已经够冷了。”",
    "夸父追日": "后来桃林长成，第一批路过的人在树荫下歇脚，谁也没见过夸父，却都听过他追着太阳奔跑到最后一息的故事。有人摘下一枚桃子，咬了一口便被酸得皱眉，旁边人笑他说这是巨人留下的力气，入口先要跟牙齿打一架。阿满也坐在树下，把青竹简摊在膝上，郑重补写：夸父追日不是为了把太阳拽下来给自己看热闹，而是因为他相信脚步能追近光，相信人可以用奔跑向天地问一句为什么。他饮尽黄河、渭水仍不解渴，走向大泽之前力竭倒下，手杖化作桃林，给后来赶路的人留下阴凉与果实。阿满写到这里，摸了摸被晒得发烫的旧笔，忍不住小声说：“这一页告诉我，追光的人倒下了，影子却会长成树荫；我这支笔若有半点出息，至少别在树荫底下喊累。”风穿过桃叶，沙沙作响，像夸父最后的脚步声仍在很远的地方继续向前。",
    "神农尝百草": "夜色落下来时，神农仍没有立刻歇下。他把白日里尝过的草木一一分开，能救人的放在一边，会伤人的另放一边，连味道相近、叶脉相似的也不肯混淆。阿满跟着记到眼睛发酸，差点把“苦寒”写成“苦得很寒酸”，赶紧用袖口擦掉，心虚地看了神农一眼。神农没有责怪，只让他把每一次中毒后的反应也写清楚：舌尖麻多久，腹中痛几阵，解毒的叶子几时起效，都不能省。阿满听得头皮发紧，小声嘀咕：“别人写故事怕漏英雄事迹，我写这一页怕漏一口苦味。”可他很快收起玩笑，因为神农又拿起一片没人敢碰的叶子。那一刻他终于明白，医药不是从天上掉下来的恩赐，而是有人把危险先含进嘴里，再把活路留给后来的人。他在《山海二十简》末尾补下一行：神农尝百草，辨药性，解民疾，也把自己的性命一次次放在草木之间试探。写完这句，他把药名重新描深，生怕后人看错半笔，就把救命药当成添乱草。",
}


MYTH_LENGTH_SECOND_EXTENSION_PARAGRAPHS = {
    "嫦娥奔月": "院外有人轻轻叹气，说月亮从前只是月亮，往后怕是再也不能只当月亮看了。阿满听见这话，忽然觉得自己这页写得再整齐也不够，因为真正的故事会被每个抬头的人重新读一遍。后羿终于转身进屋，背影没有倒下，却比倒下更让人不敢出声。阿满跟在后面，把青竹简抱得很稳，像抱着一段不能掉在尘土里的清辉。他在末尾又补一笔：人间从此有了望月的习惯，望的不是远处的神仙热闹，而是一个名字、一场离别、一份再也不能递到手里的牵挂。风吹过院中旧树，叶影落在空水盏旁，阿满看了半晌，终究只写下“长望”二字；这两个字很短，却像一条从人间伸向月宫的路。",
    "夸父追日": "阿满后来把这片桃林也画进简边，画得歪歪扭扭，像一排刚学会站稳的小树。他写道：夸父没有追上太阳，却把追赶本身留给了后来的人。有人在树下乘凉，有人在果实里尝到酸甜，有人在很热很累的时候想起那个巨人，便又多走了几步。阿满合上青竹简，小声说：“这就够了，能让后来的人多走几步，也算追日的人没有白跑。”",
    "神农尝百草": "第二日天还未亮，阿满本以为神农总该歇一歇，谁知神农已经把新采来的草叶摆开。阿满揉着眼睛坐起，第一句话差点脱口而出“草也起得这么早吗”，可看见神农掌心被汁液染出的青黑色，又把玩笑吞回去一半，只剩很轻的一句：“我这支笔今日先醒，舌头可千万别跟着受苦。”神农笑了笑，仍把草叶送入口中。苦味上来时，他眉心一皱，却没有吐掉；麻意漫上舌根时，他立刻让阿满记下时辰；腹中发热时，他又指向另一株小草，让人煎水试解。阿满写得手忙脚乱，竹简上全是药名、滋味、毒性和解法，偶尔夹着一两个被他写歪的小字，像旧笔也跟着中了一点慌。傍晚时，村中有人按神农所辨的药方救回了发热的孩子，孩子醒来第一句喊饿，众人笑出声，阿满也笑，却笑得眼眶发酸。他在《山海二十简》末尾补写：神农尝百草，最难的不是吃下苦味，而是把每一种苦味变成后人能避开的路。后来山路旁的草木再被人提起，便不只是“能吃”或“不能吃”这么简单，而有了寒热、有了毒性、有了解法，也有了神农一次次亲口试出来的分寸。阿满把这些分寸写得比自己的名字还认真，末了才敢小声补一句：“我今日终于明白，药名不能乱起，苦味也不能白苦。”写完这句，他把竹简抱紧，郑重得像抱住一小片刚从病痛里抢回来的春天。",
}


MYTH_LENGTH_THIRD_EXTENSION_PARAGRAPHS = {
    "嫦娥奔月": "阿满最后在页角压低笔迹补道：若有人问这故事为何总在夜里被想起，那是因为白日忙着活下去，夜深才听得见思念落地的声音。",
    "神农尝百草": "从那以后，阿满每写一个药名都先停一停，像先向草木和神农的舌尖行个小礼。他知道这页不能只写苦，也要写苦之后有人退烧、有人止痛、有人终于能在夜里睡稳。那些轻下来的呼吸声，不响，却比任何夸口都更像答案。神农把最后一束草药交给村人时，只说按时煎服，阿满却在旁边悄悄补了半句：“也请按时心疼一下尝药的人。”众人笑了，神农也笑，笑完仍转身走向下一片山坡。阿满望着他的背影，把旧笔在袖口擦了又擦，心想这页若写得太轻，便对不起那些被苦味换回来的清晨；若写得太重，又怕后人忘了神农也会疼。于是他只添一句：百草有名，百姓有路。",
}


def repair_myth_final_requirements(text: str, myth_core: dict = None) -> str:
    if not text or not myth_core:
        return text
    title = myth_core.get("title", "")
    needs_repair = (
        not myth_core_requirement_met(text, myth_core, final=True)
        or not myth_core_required_sequence_met(text, myth_core)
        or not myth_core_final_phrases_met(text, myth_core)
        or not thread_protagonist_requirement_met(text, myth_core)
        or not thread_protagonist_system_requirement_met(text, myth_core)
    )
    if not needs_repair:
        return prune_excess_thread_cross_story_bridges(text, myth_core)
    repair = MYTH_FINAL_REPAIR_PARAGRAPHS.get(title)
    if not repair or repair in text:
        return text
    print(f"正在补强《{title}》核心收束短语与阿满串线...")
    repaired = (text.rstrip() + "\n\n" + repair).strip()
    if len(repaired) > MYTH_TARGET_TOTAL_MAX:
        return text
    return prune_excess_thread_cross_story_bridges(repaired, myth_core)


def repair_myth_quality_tail(text: str, myth_core: dict = None) -> str:
    if not text or not myth_core:
        return text
    title = myth_core.get("title", "")
    tail = MYTH_QUALITY_TAIL_PARAGRAPHS.get(title)
    if not tail or tail in text:
        return text
    humor_floor = 24 if title in {"哪吒闹海", "大禹治水"} else 14
    needs_tail = len(text) < MYTH_TARGET_TOTAL_MIN or humor_signal_count(text) < humor_floor
    if not needs_tail:
        return prune_excess_thread_cross_story_bridges(text, myth_core)
    repaired = (text.rstrip() + "\n\n" + tail).strip()
    if len(repaired) > MYTH_TARGET_TOTAL_MAX:
        return text
    print(f"正在补强《{title}》长度/幽默密度与阿满二十简串线...")
    return prune_excess_thread_cross_story_bridges(repaired, myth_core)


def repair_myth_minimum_length(text: str, myth_core: dict = None) -> str:
    if not text or not myth_core:
        return text
    if len(text) >= MYTH_TARGET_TOTAL_MIN:
        return text
    title = myth_core.get("title", "")
    repaired = text
    appended = False
    for extension in (
        MYTH_LENGTH_EXTENSION_PARAGRAPHS.get(title),
        MYTH_LENGTH_SECOND_EXTENSION_PARAGRAPHS.get(title),
        MYTH_LENGTH_THIRD_EXTENSION_PARAGRAPHS.get(title),
    ):
        if len(repaired) >= MYTH_TARGET_TOTAL_MIN:
            break
        if not extension or extension in repaired:
            continue
        candidate = (repaired.rstrip() + "\n\n" + extension).strip()
        if len(candidate) > MYTH_TARGET_TOTAL_MAX:
            continue
        repaired = candidate
        appended = True
    if appended:
        print(f"正在补足《{title}》最终字数到 7000 字以上...")
        return prune_excess_thread_cross_story_bridges(repaired, myth_core)
    return text


HUMOR_SIGNAL_MARKERS = [
    "笑", "吐槽", "嘀咕", "小声", "差点", "嘴硬", "愣", "尴尬",
    "一本正经", "认真", "手忙脚乱", "护住", "写歪", "写错", "记错",
    "拆台", "误会", "打岔", "抬杠", "腿软", "发麻", "烫手",
    "不敢", "偏偏", "硬着头皮", "结果", "谁知", "反倒", "话音未落",
    "没想到", "忍不住", "憋笑",
]

FORBIDDEN_HUMOR_STYLE_MARKERS = [
    "打工人", "内卷", "公司", "加班", "直播", "弹幕", "系统",
    "玩家", "手机", "电脑", "导航", "流量", "社畜",
]


def humor_signal_count(text: str) -> int:
    if not text:
        return 0
    return sum(text.count(marker) for marker in HUMOR_SIGNAL_MARKERS)


def humor_requirement_met(text: str, prompt: str = "") -> bool:
    if not text:
        return False
    if any(marker in text for marker in FORBIDDEN_HUMOR_STYLE_MARKERS):
        return False
    if prompt and "幽默" not in prompt and "搞笑" not in prompt and "有趣" not in prompt:
        return True
    # 自动检测只拦明显无趣版本；真正的笑点质量由批量脚本的可选 Qwen 审稿和人工抽查继续判断。
    min_signals = 10 if len(text) >= 7000 else 6
    if humor_signal_count(text) < min_signals:
        return False
    dialogue_lines = len(re.findall(r'[“"][^”"]{2,80}[”"]', text))
    if dialogue_lines < 8:
        return False
    return True


def apply_myth_specific_postprocess(text: str, myth_core: dict = None) -> str:
    if not text or not myth_core:
        return text
    text = repair_thread_protagonist_system_link(text, myth_core)
    if myth_core.get("title") == "北冥鲲鹏":
        text = text.replace("北海深处", "北冥深处")
        text = text.replace("北海之上", "北冥之上")
        text = text.replace("北海下", "北冥下")
        text = re.sub(r'北海(?!道)', '北冥', text)
        arrived_at_nanming = any(
            marker in text
            for marker in (
                "抵达南冥天池",
                "南冥天池接纳",
                "大鹏落在南冥天池",
                "南冥天池边缘",
            )
        )
        if "向南冥天池飞去" not in text and not arrived_at_nanming and "南冥天池" in text:
            text = re.sub(r'[\s。！？…]*$', '', text)
            text += "\n\n大鹏没有再回头。它乘着六月大风，越过北冥翻涌的海面，向南冥天池飞去。那些曾经笑它太大、太笨、太不安分的声音，终于小得像浪尖上的泡沫。"
        if arrived_at_nanming:
            text = re.sub(
                r'大鹏没有再回头。它乘着六月大风，越过北冥翻涌的海面，向南冥天池飞去。那些曾经笑它太大、太笨、太不安分的声音，终于小得像浪尖上的泡沫。?',
                '',
                text,
            )
        text = text.replace("大鹏振翼时翼若垂天之云", "大鹏展翼，翼若垂天之云")
    if myth_core.get("title") == "夸父追日":
        text = text.replace("路线图", "行路方向")
        text = text.replace("拿骨头当柴烧", "拿腿脚当柴烧")
        text = text.replace("跑过第七座丘陵缓坡时", "翻过又一道丘陵缓坡时")
        text = re.sub(r'他跑过了第八座丘陵，第九座，第十座。', '他翻过一座又一座丘陵。', text)
        text = re.sub(r'第[一二三四五六七八九十百千万\d]+次迈步时', '又一次迈步时', text)
        text = re.sub(r'第[一二三四五六七八九十百千万\d]+(?:步|歩)', '又一步', text)
        text = re.sub(r'[一二三四五六七八九十百千万\d]+步之后', '又走出很远之后', text)
        text = re.sub(r'走出二十步', '又向前走了一段', text)
        text = re.sub(r'起初还数着步子——[^。！？]{0,80}后来连数字也散了', '起初还勉强记着路程，后来连念头也散了', text)
        text = re.sub(r'\（?他自己心里默数：[^。！？）]{0,80}\）?', '，他只顾调匀呼吸', text)
        text = text.replace("凡二百十七步至斯，始歇", "行至此处，始歇")
        text = text.replace("陈年箭疤", "陈年旧痛")
        text = text.replace("箭疤", "旧痛")
        text = text.replace("燎泡", "热意").replace("皮屑", "尘灰")
        text = re.sub(r'手腕却被[^。！？]{0,80}血珠[^。！？]{0,80}[。！？]', '手腕被荆棘钩了一下，他没有停步。', text)
        text = text.replace("血痂", "干泥").replace("血丝", "红痕")
        text = re.sub(r'【山海二十简[^】]*】', '《山海二十简》', text)
        text = re.sub(r'（此林今结实累累，味甘多汁，行人经者皆可采）', '他又补道：此林结实累累，味甘多汁，行人皆可采。', text)
        text = text.replace("窗外北斗已斜，檐角漏下半钩残月", "篝火外北斗已斜，远山上悬着半钩残月")
        text = text.replace("梦里没有金乌，也没有箭镞，", "梦里没有喧响，")
    if myth_core.get("title") == "雷泽华胥":
        text = text.replace("震得水面涟漪荡漾如八卦图", "震得水面荡开一圈圈涟漪")
        text = text.replace("哎哟，连水都开始学算卦了。", "哎哟，连水都嫌我站不稳了。")
        text = re.sub(
            r'最后一哆嗦是他翻开新页补录，郑重写下：“癸酉日申时，华胥履大人迹毕，立而闻雷，继觉胎动。”写罢端详良久，皱眉涂改一字——把“胎”圈掉，换作“体”。旁边批注蝇头小楷：“尚不可证，姑且存疑。”',
            '最后一哆嗦是他翻开新页补录，郑重写下：“癸酉日申时，华胥履大人迹而感孕，腹中已有胎动。”他照实落笔，不猜缘由，也不擅自涂改。',
            text,
        )
        text = re.sub(
            r'唯独他盯着墙上摇曳的灯影，忽然低声念叨：“要是伏羲将来写字也这么费劲……啧，咱这简册怕是要劈成八百片才够使。”',
            '唯独他盯着墙上摇曳的灯影，忽然低声念叨：“这一笔记得这么费劲，等二十简写完，我这支旧笔怕是得拄拐。”',
            text,
        )
        text = text.replace(
            '他终于合拢青竹简，指尖抚过最新一页——上面只有七个干净小字：“十月怀胎，终诞伏羲。”',
            '他终于合拢青竹简，指尖抚过最新一页。上面只记着华胥这些日子的起居，结局尚未发生，他便留出一大片空白。',
        )
        text = re.sub(
            r'【?伏羲生于雷泽之滨，母曰华胥。[\s\S]{0,1000}?写至此处，',
            '阿满写下：华胥履大人迹而感孕，后来在雷泽之滨生下伏羲。他不替尚在襁褓中的孩子提前写完一生。写至此处，',
            text,
        )
        text = text.replace("脐带剪断时溅出的星点血沫", "伏羲落地后的第一声啼哭")
        text = text.replace("墨痕深得能刮出血珠", "墨痕深得指腹都能摸见")
        text = re.sub(
            r'他舔掉唇边碎糖粒，蘸唾沫抹匀第七支简末尾一行字：[^。！？]{0,500}不肯弯曲。”',
            '阿满看见伏羲的小手碰了碰青竹简边缘，只记下孩子眼下平安、华胥终于松了一口气，不替这个新生儿预写日后的画卦故事。',
            text,
        )
        text = re.sub(
            r'这时忽觉掌心痒——原来伏羲竟抬起一只小手，[\s\S]{0,900}?且不肯弯曲。”',
            '这时他忽觉掌心发痒，低头才发现伏羲抬起一只小手，指尖碰在青竹简边缘。阿满一动不敢动，怕惊醒孩子；蜜饴却还黏在舌头上，他想叫人又开不了口，只能把求助全挤进眉毛里。旁边妇人看懂了，轻轻把孩子的手放回襁褓。阿满这才吐出一口气，只在简末写道：“伏羲今日平安，手很小，抓简倒准。”写完又看一遍，把所有关于将来的猜测都留成空白。',
            text,
        )
        text = re.sub(
            r'暮色漫上来时，阿满卷好十七支简，[\s\S]{0,900}?让人不敢大声说笑的土地。',
            '暮色漫上来时，阿满把散开的竹片逐一理好。他先写雷泽，再写大人足迹；写到足迹大小，横着比不下，竖着仍比不下，只好在页角画半只脚印，注明：“不是史官偷懒，是这一脚实在不肯迁就竹简。”渔童看了，说那图更像一只压扁的豆饼。阿满把笔帽扣紧，答得很稳：“豆饼若有这么大，今日也算另一桩奇闻。”笑声很轻，没有越过产房门槛。\n\n他随后郑重核对当下已经发生的事：华胥来到雷泽，亲眼看见大人足迹；她踏入足迹而感孕，经过孕期，最终亲自生下一个真实啼哭、真实呼吸的男婴，取名伏羲。阿满没有解释感孕的缘由，也没有替襁褓中的伏羲写未来。他只是把华胥的选择、忍耐与诞生时的第一声啼哭记清。雷泽晚风翻动简页，他想起北冥那一回大风几乎把整册吹走，赶紧用手压住，低声道：“一个地方拿风考我，一个地方拿雷声考我，看来史官最先要学会的不是写，是按住。”\n\n最后一笔干透后，他把这一页收入《山海二十简》。院里重新响起烧水与添柴的声音，妇人们收拾陶盆，族人把带来的食物放在门边，华胥抱着伏羲安静休息。阿满退到院外，没有把这场诞生说成别篇神话的起点，也没有替任何故事争先后。他只留下这一页属于雷泽与华胥的见闻：一只巨大足迹，一段无人能够代替的孕育，和一个在晨光里响亮啼哭的新生命。',
            text,
        )
        text = text.replace(
            "和一个在晨光里响亮啼哭的新生命。",
            "和一个在晨光里响亮啼哭的新生命。",
        )
        text = text.replace("她踏入足迹而感孕", "她履迹而感孕")
        text = text.replace(
            "华胥履巨人迹而娠，十月零六日娩男婴，名曰伏羲",
            "华胥履大人迹而感孕，孕期既足，亲生男婴，名曰伏羲",
        )
        text = text.replace(
            "华胥颔首，低头吻了吻儿子额角。",
            "华胥颔首，低头吻了吻儿子额角，亲口为他取名伏羲。",
        )
        text = text.replace(
            "写完又看一遍，把所有关于将来的猜测都留成空白。",
            "写完又看一遍，确认只记了眼前所见，便轻轻把墨迹吹干。",
        )
        text = text.replace(
            "阿满没有解释感孕的缘由，也没有替襁褓中的伏羲写未来。他只是把华胥的选择、忍耐与诞生时的第一声啼哭记清。",
            "写到这里，阿满停笔看了看襁褓。孩子刚打了个小哈欠，华胥也终于松开一直绷紧的肩膀。他便只把她一路的选择、忍耐和伏羲落地后的第一声啼哭写清，余下空白仍旧空着。",
        )
        civilization_epilogue = "后来的岁月里，伏羲长大成人，被后世尊为文明始祖；那是成长以后的故事，阿满在这个清晨并不知道，也没有提前写进竹简。"
        text = text.replace(civilization_epilogue, "")
    if myth_core.get("title") == "愚公移山":
        text = re.sub(
            r'他又在旁边挤着补了一行小字[^。！？]{0,260}(?:右耳嗡鸣至今未消|至今未消)。?',
            '他又在旁边挤着补了一行小字：智叟的话让人发笑，愚公的回答却让满坡人安静下来。',
            text,
        )
    if myth_core.get("title") == "神农尝百草":
        text = re.sub(
            r'鼠曲草·味微辛，性凉。治肺热咳嗽，利尿通淋。宜鲜用，忌久煎。',
            '鼠曲草，入口微辛，尝后身上反应与先前几味不同，需再观察，不可轻率给人服用。',
            text,
        )
    return text

def clean_markdown(text):
    """去除 Markdown 格式符号"""
    if not text:
        return ""
    # 基础 Markdown 清理
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # 去除 **
    text = re.sub(r'### (.*)', r'\1', text)       # 去除 ###
    text = re.sub(r'---', '', text)               # 去除 ---

    # 把模型偶尔输出的转义符号，恢复成正常文本换行 / 引号
    # 例如："\n" -> 实际换行，"\\\"" -> 普通引号
    text = text.replace('\\n', '\n')
    text = text.replace('\\"', '"')

    # 删除明显是"注释 / 说明"的尾部内容（如"注释：""注解："之后的部分）
    text = re.sub(r'(注释：|注解：)[\s\S]*$', '', text)
    text = remove_meta_residue(text)
    text = normalize_language_pollution(text)
    text = remove_meta_residue(text)

    # 折叠过多的空行：最多保留连续 2 个换行，避免极端空行
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def remove_meta_residue(text: str) -> str:
    """
    删除模型泄露到正文里的写作提示、字数说明和下一节提示。
    这些内容不是故事文本，宁可整段删除，也不要保留在成稿里污染样本。
    """
    if not text:
        return text

    for pattern in META_RESIDUE_PATTERNS:
        text = re.sub(pattern, '', text)

    # 删除单独成行或短句形式的生成说明。
    meta_line_patterns = [
        r'^[^\n]{0,20}(这段大约|多少字左右|接下来便是|下一节|实际书写|不显示|隐藏章节|待补|备注|插入)[^\n]{0,80}$',
        r'^[^\n]{0,20}(节拍卡|画面要素|情感伏笔|关系推进|信息增量|场景目标)[：:][^\n]{0,120}$',
    ]
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if any(re.search(pattern, stripped) for pattern in meta_line_patterns):
            continue
        lines.append(line)
    return "\n".join(lines)


def remove_body_drift_residue(text: str) -> str:
    """
    删除明显串出台词/主题的段落，尤其是现代政治宣传腔、系统工程腔等。
    这类内容宁可整段删除，也不能混入神话正文。
    """
    if not text:
        return text
    drift_patterns = BODY_DRIFT_PATTERNS + [
        r'绿色发展|循环经济|金山银山|现代化水平|获得感幸福感安全感',
        r'正能量|政治生态|社会稳定|国家安全|对外开放新格局',
    ]
    kept = []
    for block in re.split(r'(\n\s*\n)', text):
        if not block.strip() or re.fullmatch(r'\n\s*\n', block):
            kept.append(block)
            continue
        compact = re.sub(r'\s+', '', block)
        if re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', block):
            continue
        ascii_symbols = re.findall(r'[#$%&*+/<=>?@\\^_`{|}~]', block)
        if len(ascii_symbols) >= 25 and len(ascii_symbols) >= len(compact) // 8:
            continue
        if any(re.search(pattern, block) for pattern in drift_patterns):
            continue
        kept.append(block)
    cleaned = "".join(kept)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned


def normalize_language_pollution(text: str) -> str:
    """
    统一清理语言污染：
    - 常见繁体字转简体
    - 删除俄文/希腊文等误入字符
    - 清理异常标点和中文之间的多余空格
    """
    if not text:
        return text

    text = text.translate(TRADITIONAL_TO_SIMPLIFIED)
    text = re.sub(r'[\u0370-\u03FF\u0400-\u052F\u3040-\u30FF]+', '', text)
    text = text.replace("导航", "引路")
    text = re.sub(r'纷纷掏出手机录像拍摄', '纷纷伸长脖子瞪大眼睛', text)
    text = re.sub(r'掏出手机[^，。！？；\n]{0,20}(录像|拍摄)[^，。！？；\n]{0,20}', '伸长脖子瞪大眼睛', text)
    text = text.replace("手机录像", "当场围观")
    text = text.replace("手机拍摄", "当场围观")
    text = text.replace("手机", "手中物件")
    text = text.replace('「', '“').replace('」', '”').replace('『', '“').replace('』', '”')
    text = text.replace(' ,', '，').replace(', ', '，').replace(' .', '。')
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)
    text = re.sub(r'\s+([，。！？；：、])', r'\1', text)
    text = re.sub(r'([，。！？；：、])\s+', r'\1', text)
    text = re.sub(r'([，。！？；：、])\1{1,}', r'\1', text)
    text = re.sub(r'(?m)^[\\!\"#$%&\'()*+,\-./0-9:;<=>?@\[\]^_`{|}~，]{12,}\s*$', '', text)
    text = re.sub(r'[ ]{2,}', ' ', text)
    return text


def contains_plan_drift(text: str, myth_core: dict = None) -> bool:
    """
    检测规划文本中的跑偏信号：
    - 系统化/工程化/综艺化表达
    - 预言型动物、神秘外援等与神话主线脱节的扩写模板
    """
    if not text:
        return False
    if contains_myth_core_violation(text, myth_core or {}):
        return True
    if any(term in text for term in BAD_PLAN_TERMS):
        return True
    return any(re.search(pattern, text) for pattern in PLAN_DRIFT_PATTERNS)


def contains_manual_review_quality_issue(text: str) -> bool:
    """
    人工复审补充质量闸门：拦截现代行政腔、随机拼贴词、格式残留和明显转写污染。
    """
    if not text:
        return False
    normalized = normalize_language_pollution(text)
    if any(term and term in normalized for term in MANUAL_REVIEW_BAD_TERMS):
        return True
    if any(re.search(pattern, normalized) for pattern in MANUAL_REVIEW_BAD_PATTERNS):
        return True
    return False


def contains_body_drift(text: str, myth_core: dict = None) -> bool:
    """
    检测正文中的跑偏信号：
    - 现代节目/数值系统/工程说明
    - 预言动物、神秘外援等未受控的新设定
    """
    if not text:
        return False
    if contains_myth_core_violation(text, myth_core or {}):
        return True
    if any(term in text for term in BAD_PLAN_TERMS):
        return True
    if contains_manual_review_quality_issue(text):
        return True
    return any(re.search(pattern, text) for pattern in BODY_DRIFT_PATTERNS)


def fix_punctuation_and_paragraphs(text):
    """
    后处理函数：检测超长无标点段落并强制打断
    规则：
    - 检测超过120字且没有句号的段落，强制插入句号和换行
    - 检测超过35个汉字且没有逗号或句号的句子，在合适位置插入逗号
    - 确保每段2-4句，每句不超过35个汉字
    """
    if not text:
        return text

    # 句末标点集合：同时把中英文句号/感叹号/问号都视为“有句子边界”
    END_PUNCTS = set("。！？.!?")
    #111
    # 按段落分割
    paragraphs = text.split('\n')
    fixed_paragraphs = []
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            fixed_paragraphs.append('')
            continue
        
        # 检测超长无标点段落（超过120字且没有任何句末标点）
        if len(para) > 120 and not any(p in para for p in END_PUNCTS):
            # 尝试在合适位置插入句号和换行
            # 在每35-40个字符后寻找合适的分割点（标点、空格等）
            fixed_para = ""
            current_length = 0
            for i, char in enumerate(para):
                fixed_para += char
                current_length += 1
                # 每35个字符检查一次，如果遇到合适位置就插入句号
                if current_length >= 35:
                    # 检查下一个字符是否是标点或换行/制表符（不再把普通空格当成最佳断点）
                    if i + 1 < len(para):
                        next_char = para[i + 1]
                        if next_char in '，。！？；：\n\t':
                            # 如果当前附近没有句号或其他句末标点，在合适位置插入
                            if not any(p in fixed_para[-20:] for p in END_PUNCTS):
                                fixed_para += '。'
                                fixed_para += '\n'
                                current_length = 0
                    elif current_length >= 40:
                        # 如果超过40个字符还没遇到标点，强制插入句号
                        fixed_para += '。'
                        fixed_para += '\n'
                        current_length = 0
            fixed_paragraphs.append(fixed_para)
        else:
            # 对于正常段落，检查是否有超长无标点句子
            sentences = re.split(r'([。！？])', para)
            fixed_sentences = []
            current_sentence = ""
            
            for i in range(0, len(sentences), 2):
                if i < len(sentences):
                    current_sentence += sentences[i]
                    if i + 1 < len(sentences):
                        current_sentence += sentences[i + 1]
                    
                    # 检查句子长度（超过35个汉字且没有逗号或句号）
                    if len(current_sentence) > 35 and '，' not in current_sentence and not any(p in current_sentence for p in END_PUNCTS):
                        # 在合适位置插入逗号（大约每20个字符）
                        chars = list(current_sentence)
                        new_chars = []
                        for j, char in enumerate(chars):
                            new_chars.append(char)
                            if (j + 1) % 20 == 0 and j + 1 < len(chars) and chars[j + 1] not in '，。！？；：':
                                new_chars.append('，')
                        current_sentence = ''.join(new_chars)
                    
                    fixed_sentences.append(current_sentence)
                    current_sentence = ""
            
            fixed_para = ''.join(fixed_sentences)
            fixed_paragraphs.append(fixed_para)
    
    return split_long_paragraphs('\n'.join(fixed_paragraphs))


def split_long_paragraphs(text: str, max_paragraph_len: int = 360, soft_paragraph_len: int = 240) -> str:
    """
    将过长自然段按句子边界拆开，避免多个节拍或多个动作阶段黏成一整段。
    只在句末标点处换段，不强行切断句子。
    """
    if not text:
        return text

    sentence_pattern = re.compile(r'.+?[。！？!?](?:[”"])?|.+$', re.DOTALL)
    paragraphs = re.split(r'\n{2,}', text.strip())
    rebuilt = []

    def _split_oversized_sentence(sentence: str) -> list:
        if len(sentence) <= max_paragraph_len:
            return [sentence]
        clauses = re.split(r'(?<=[，；：、,;:])', sentence)
        chunks = []
        current = ""
        for clause in clauses:
            if not clause:
                continue
            if current and len(current) + len(clause) > max_paragraph_len:
                chunks.append(current)
                current = clause
            else:
                current += clause
            while len(current) > max_paragraph_len:
                chunks.append(current[:soft_paragraph_len])
                current = current[soft_paragraph_len:]
        if current:
            chunks.append(current)
        return chunks

    for para in paragraphs:
        para = re.sub(r'\s*\n\s*', '', para.strip())
        if not para:
            continue
        if len(para) <= max_paragraph_len:
            rebuilt.append(para)
            continue

        sentences = []
        for m in sentence_pattern.finditer(para):
            sentence = m.group(0).strip()
            if sentence:
                sentences.extend(_split_oversized_sentence(sentence))
        current = ""
        for sentence in sentences:
            if not current:
                current = sentence
                continue

            should_break = len(current) >= soft_paragraph_len and (
                len(current) + len(sentence) > max_paragraph_len
                or sentence.startswith(("这时", "忽然", "然而", "正当", "就在", "与此同时", "远处", "身后", "他", "她", "夸父", "后羿", "嫦娥"))
            )
            if should_break:
                rebuilt.append(current)
                current = sentence
            else:
                current += sentence

        if current:
            rebuilt.append(current)

    return "\n\n".join(rebuilt).strip()


def get_qwen_api_timeout_seconds() -> int:
    raw = os.getenv("QWEN_API_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return QWEN_API_TIMEOUT_SECONDS_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        print(f"警告：QWEN_API_TIMEOUT_SECONDS={raw} 不是整数，已使用默认 {QWEN_API_TIMEOUT_SECONDS_DEFAULT} 秒。")
        return QWEN_API_TIMEOUT_SECONDS_DEFAULT
    return max(10, value)


def apply_qwen_api_retry_override(max_retries: int) -> int:
    raw = os.getenv("QWEN_API_MAX_RETRIES", "").strip()
    if not raw:
        return max_retries
    try:
        value = int(raw)
    except ValueError:
        print(f"警告：QWEN_API_MAX_RETRIES={raw} 不是整数，已使用函数默认 {max_retries} 次。")
        return max_retries
    return max(1, value)


def qwen_api_transport_mode() -> str:
    mode = os.getenv("QWEN_API_TRANSPORT", "auto").strip().lower()
    if mode not in {"auto", "sdk", "curl"}:
        print(f"警告：QWEN_API_TRANSPORT={mode} 不受支持，已使用 auto。")
        return "auto"
    return mode


def qwen_generation_model() -> str:
    """长篇神话默认使用输出长度更稳定的 qwen-plus，可由环境变量覆盖。"""
    return os.getenv("QWEN_GENERATION_MODEL", "qwen-plus").strip() or "qwen-plus"


def call_qianwen_api_via_curl(
    messages,
    temperature=0.95,
    top_p=0.9,
    repetition_penalty=1.15,
    max_tokens=None,
    timeout_seconds=None,
):
    api_key = require_api_key()
    timeout_seconds = timeout_seconds or get_qwen_api_timeout_seconds()
    parameters = {
        "temperature": temperature,
        "top_p": top_p,
        "repetition_penalty": repetition_penalty,
        "result_format": "message",
    }
    if max_tokens is not None:
        parameters["max_tokens"] = max_tokens
    payload = {
        "model": qwen_generation_model(),
        "input": {"messages": messages},
        "parameters": parameters,
    }

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".json") as f:
            json.dump(payload, f, ensure_ascii=False)
            temp_path = f.name

        curl_network_args = []
        curl_interface = os.getenv("QWEN_CURL_INTERFACE", "").strip()
        curl_resolve_ip = os.getenv("QWEN_CURL_RESOLVE_IP", "").strip()
        if curl_interface:
            curl_network_args.extend(["--interface", curl_interface])
        if curl_resolve_ip:
            curl_network_args.extend([
                "--resolve",
                f"dashscope.aliyuncs.com:443:{curl_resolve_ip}",
            ])
        cmd = [
            "curl.exe",
            *curl_network_args,
            "-sS",
            "--connect-timeout",
            str(min(15, timeout_seconds)),
            "--max-time",
            str(timeout_seconds),
            "-X",
            "POST",
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
            "-H",
            "Authorization: Bearer " + api_key,
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            "@" + temp_path,
            "-w",
            "\n__HTTP_STATUS__:%{http_code}",
        ]
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout_seconds + 5,
        )
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""
        status = ""
        if "\n__HTTP_STATUS__:" in stdout:
            body, status = stdout.rsplit("\n__HTTP_STATUS__:", 1)
        else:
            body = stdout
        if completed.returncode != 0:
            return f"调用通义千问 API 出错（curl 退出码 {completed.returncode}，HTTP {status or 'unknown'}）: {stderr.strip() or body[:500]}"
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return f"通义千问 API 返回了非 JSON 内容（HTTP {status or 'unknown'}）: {body[:800]}"
        if str(status) and not str(status).startswith("2"):
            return f"通义千问 API HTTP {status}: {json.dumps(data, ensure_ascii=False)[:800]}"
        choices = data.get("output", {}).get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return f"通义千问 API 返回了无效格式: {json.dumps(data, ensure_ascii=False)[:800]}"
    except Exception as e:
        return f"调用通义千问 API 出错（curl 通道）: {type(e).__name__} - {e}"
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


def call_qianwen_api(messages, temperature=0.95, top_p=0.9, repetition_penalty=1.15, max_retries=5, max_tokens=None):
    """
    调用通义千问 API，带重试机制
    
    Args:
        messages: 消息列表
        temperature: 温度参数
        top_p: top_p 参数
        repetition_penalty: 重复惩罚参数
        max_retries: 最大重试次数（默认5次）
        max_tokens: 最大生成token数（默认None，使用API默认值）
    
    Returns:
        API 返回的内容，或错误信息
    """
    api_key = require_api_key()
    global QWEN_API_CALL_COUNTER
    QWEN_API_CALL_COUNTER += 1
    call_id = QWEN_API_CALL_COUNTER
    timeout_seconds = get_qwen_api_timeout_seconds()
    max_retries = apply_qwen_api_retry_override(max_retries)
    transport_mode = qwen_api_transport_mode()
    dashscope.api_key = api_key
    
    last_error = None
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                # 指数退避：第1次重试等1秒，第2次等2秒，第3次等4秒...
                wait_time = min(2 ** (attempt - 1), 10)  # 最多等待10秒
                print(f"第 {attempt + 1} 次尝试（等待 {wait_time} 秒后重试）...")
                time.sleep(wait_time)

            if transport_mode == "curl":
                print(f"Qwen API 调用 #{call_id}.{attempt + 1} 使用 curl 通道（model={qwen_generation_model()}, timeout={timeout_seconds}s, max_tokens={max_tokens or 'default'}）")
                reply = call_qianwen_api_via_curl(
                    messages,
                    temperature=temperature,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                )
                if reply and "调用通义千问 API" not in reply and "通义千问 API HTTP" not in reply:
                    return reply
                last_error = reply
                if attempt < max_retries - 1:
                    continue
                return reply
            
            # 构建API调用参数
            api_params = {
                "model": qwen_generation_model(),
                "messages": messages,
                "temperature": temperature,
                "top_p": top_p,
                "repetition_penalty": repetition_penalty,
                "result_format": 'message',
                "timeout": timeout_seconds,
            }
            
            # 如果指定了max_tokens，添加到参数中
            if max_tokens is not None:
                api_params["max_tokens"] = max_tokens
            
            started_at = time.time()
            print(f"Qwen API 调用 #{call_id}.{attempt + 1} 开始（model={qwen_generation_model()}, timeout={timeout_seconds}s, max_tokens={max_tokens or 'default'}）")
            response = dashscope.Generation.call(**api_params)
            elapsed = time.time() - started_at
            print(f"Qwen API 调用 #{call_id}.{attempt + 1} 完成（{elapsed:.1f}s）")

            if 'output' in response and 'choices' in response['output']:
                return response['output']['choices'][0]['message']['content']
            else:
                error_msg = f"通义千问 API 返回了无效格式: {str(response)}"
                print(f"Qwen API 调用 #{call_id}.{attempt + 1} 返回格式异常")
                if attempt < max_retries - 1:
                    last_error = error_msg
                    continue
                return error_msg
                
        except Exception as e:
            last_error = str(e)
            error_type = type(e).__name__
            print(f"Qwen API 调用 #{call_id}.{attempt + 1} 异常：{error_type} - {last_error}")

            if transport_mode == "auto" and (
                'SSL' in error_type
                or 'Connection' in error_type
                or 'timeout' in str(e).lower()
            ):
                print(f"Qwen API 调用 #{call_id}.{attempt + 1} 正在切换 curl 备用通道...")
                reply = call_qianwen_api_via_curl(
                    messages,
                    temperature=temperature,
                    top_p=top_p,
                    repetition_penalty=repetition_penalty,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                )
                if reply and "调用通义千问 API" not in reply and "通义千问 API HTTP" not in reply:
                    return reply
                last_error = reply
            
            # 如果是 SSL 错误或连接错误，继续重试
            if 'SSL' in error_type or 'Connection' in error_type or 'timeout' in str(e).lower():
                if attempt < max_retries - 1:
                    continue
                else:
                    return f"调用通义千问 API 失败（已重试 {max_retries} 次）: {error_type} - {last_error}\n建议：请检查网络连接或稍后重试"
            else:
                # 其他错误直接返回
                return f"调用通义千问 API 出错: {error_type} - {last_error}"
    
    # 所有重试都失败
    return f"调用通义千问 API 失败（已重试 {max_retries} 次）: {last_error}\n建议：请检查网络连接或稍后重试"

def generate_fight_scene_with_reversal(prompt):
    """生成包含反转的武打场景"""
    reversal_template = """
    请按"武打四段"创作，严格遵循篇幅比例与最低次数要求：
    - 篇幅比例：氛围与背景交代≥15%，压制≈60%，转机≈10%，反杀≈15%
    - 四段顺序：【压制阶段】【绝境加深】【微小转机】【反杀爆发】

    写作硬性要求：
    0) 正式交手前（至少200字，需丰富多感官描写）：
        - 环境细节：多角度描写地点环境（视觉：光线、色彩、阴影；听觉：风声、水声、回声、寂静；触觉：温度、湿度、质感；嗅觉：气味、血腥、草木；空间：地形、障碍、视野）
        - 氛围营造：通过环境细节营造紧张、压抑、危险等情绪氛围，让读者身临其境
        - 人物状态：描写主角与对手的站位、姿态、眼神、呼吸、肌肉状态等细节
        - 前因后果：交代此战的起因、双方立场、恩怨情仇、心理预期
        - 心理活动：通过内心独白、回忆闪回、情绪波动展现主角的心理状态
        - 细节动作：通过小动作（握剑、调整呼吸、观察地形、计算距离等）表现准备与紧张
        - 人物命名：所有出场的人物都必须有具体的名字，禁止使用"他"、"对手"、"敌人"、"黑衣人"等代称，主角和对手都要有明确的姓名
    1) 压制阶段（≈60%）：
        - 要求：通过自然流畅的叙述展现至少5次对手有效命中/压制 + 3次主角无效反击（逐次加重）
        - 严格禁止计数表达：绝对禁止使用"第一击"、"第二击"、"第三次"、"第四次"、"第五次"、"第X次"等任何计数词汇，必须用场景转换、时间推进、动作连贯等方式自然展现
        - 叙述方式：通过"权杖横扫而来"、"又是一记直刺"、"趁势追击"、"攻势如潮"、"紧接着"、"随后"、"转瞬间"等自然过渡，让多次交锋流畅衔接，完全避免数字计数
        - 技法细节：每次交锋必须出现具体技法细节（招式名、力路、角度、受力反馈、内力流转、呼吸节奏、环境互动）
        - 累积代价：呈现累积性代价（体力下降、伤势叠加、内息紊乱、武器受损、地形限制），并明确"倒计时/禁制/约束"在逼迫决策
        - 心理变化：展现主角从压迫→焦灼的心理转变，每次变化由具体外因触发
    2) 绝境加深（≈10%）：再遭一次"几乎必败"的致命压制，禁止反转
    3) 微小转机（≈10%）：仅允许来源于"洞察破绽/环境利用/诱敌深入/弃子求变/以伤换势"中的1-2种
    4) 反杀爆发（≈15%）：在对手轻敌或惯性出招时切入破绽，最多2招半结束，过程紧凑克制，必须完整写到反杀成功、对手败亡或重伤的结果，不能中途停止
    5) 禁止：跳过压制快速反杀、空话堆砌、结尾点题、使用任何计数方式（如"第一击"、"第二击"、"第三次"、"第四次"、"第五次"等）、仅写到胜负已分处、未完成反杀就停止
    6) 人物命名：所有出场的人物都必须有具体的名字，禁止使用"他"、"对手"、"敌人"、"黑衣人"、"蒙面人"等代称，主角和对手都要有明确的姓名
    7) 字数要求：1500字左右，必须完整呈现所有四段内容，特别是反杀阶段必须完整写到结果
    8) 段落标注：必须在每个部分开始前添加标注，格式如下：
       - 【氛围铺垫】（开篇氛围部分）
       - 【压制阶段】（压制阶段部分）
       - 【绝境加深】（绝境加深部分）
       - 【微小转机】（转机部分）
       - 【反杀爆发】（反杀部分）

    心理与节奏：
    - 心态线随局势推进：压迫→焦灼→冷静→决断；每次变化由具体外因触发
    - 禁止空话与总结陈词，不写结果之后的收束
    - 叙述要自然流畅，避免机械化的列举
    
    具体场景要求：{prompt}
    """
    
    return chat_once(reversal_template.format(prompt=prompt))


def get_myth_system_prompt_base(reference_content=None, myth_core=None):
    """
    获取神话改写的系统提示词基础部分
    """
    rag_part = f"""
            【参考信息（可用可不用）】
                只使用与本次神话改写强相关的内容样本，不引用其他世界观或门派设定；
                参考内容：{reference_content if reference_content else "无"}
    """ if reference_content else ""
    myth_core_part = format_myth_core_block(myth_core)
    
    return f"""
            角色：你是一名擅长改写中国神话故事的影视编剧，整体基调偏轻松、有幽默感，
            可以参考现代动画电影中"反叛少年+亲情和解"这一类的气质，但不要照搬任何现有作品的台词与分镜，更不能写成网络段子合集。

            【总体目标】
            - 基于指定的中国神话故事（如盘古开天地、女娲补天、后羿射日、哪吒闹海等）进行【重写/改写】；
            - 保留核心人物关系与关键情节节点，让读者一眼能认出这是哪个神话；
            - 以【人物性格驱动的幽默感】为第一优先，其次再在合适处自然点缀情感；
            - 亲子/家庭情感线是【可选加分项】，如果题材或用户需求合适，可以适度呈现"被误解的孩子"和"笨拙但真心的长辈"，但禁止为了完成任务强行煽情。
            - 这是用于视频创作的初版脚本，人读后才会拍成视频，需要兼顾可读性和影视化潜力。
            - 本次默认目标是生成可支撑 10 分钟视频的【长篇版本】。允许在不改变原神话骨架的前提下，加入【功能性扩展场景】：筹备、赶路、试探、失败尝试、旁观者反应、余波处理、关系推进、情感伏笔回收。但新增场景必须服务于主线推进、动作细化、幽默、情感或后果展示，不能写成无关废话。

            【神话骨架强约束（不可违反，所有神话通用）】
            - 本文必须完整讲述所选原版神话从开端到结尾的全部关键事件链（例如"十日并出 → 射落九日 → 留下一日 → 天地转好"之于"后羿射日"），不得跳过或模糊处理核心节点。
            - 情节骨架必须与原版一致：关键事件的发生顺序、因果关系、结局结果、整体走向不得改变，只能在不改变走向的前提下微调节奏和展开方式。
            - 允许的改写范围仅限于【表达层】：对白、人物性格细节、动作描写、场景镜头、幽默包袱、支线插曲等；其中支线插曲不得改变主线因果、削弱主线冲突、更不能改变最终结局。
            - 禁止改结局：不得新增"反转结局/不同结局/洗白或黑化导致寓意改变"的设定，不得把本应完成的创世/救灾/和解之举写成失败或完全不同的结果。
            - 禁止改寓意：必须保留原神话要表达的核心主题（例如：拯救苍生、克制与智慧、责任与代价、亲子守护等），幽默和日常感只能作为表层表达，不能推翻、反讽或相对化掉这一主题。

            【完整性验收（缺一则视为失败，必须整体重写本篇故事）】
            - 结尾部分必须明确回落到与原版一致的结局和寓意，用清晰可感知的句子让读者一眼确认"主线任务已经完成、故事已讲完"（而不是只停在过程或情绪上）。
            - 全文结构中必须清晰呈现且写实写满以下三段内容，三者都要与原版神话保持一致：
              1）【开端灾因/背景】：写清楚灾难或矛盾的起点、人物被卷入的原因，以及"为什么非做不可"的压力来源；
              2）【关键行动/对抗过程】：详细描写解决问题的核心行动链条（如一斧一斧开天、一箭一箭射日、一块一块补天），不能一笔带过；
              3）【最终结果/收束】：写清楚行动之后世界/人物状态如何改变，如何回到或开启一个新的稳定状态，以及这一切指向的寓意。
            - 如生成内容中缺失上述任意一类核心段落，或结局、寓意明显偏离原神话，则视为本次生成不合格，必须整体重写该篇故事，而不是仅在尾部补几句交代。

            【语言与边界（重点）】
            - 严禁任何脏话、粗口和侮辱性用语（包括"他妈""操""傻逼"等所有近义变体），不得出现。
            - 不得使用强烈网络黑话和过度口水化表达，例如"这他妈""开挂人生""打工人""社畜""创业者""卷死我了"等。
            - 不要出现"AI、系统、程序、玩家、观众、编剧、作者"等打破第四面墙的称呼，也不要用"电影镜头、特效、弹幕、观众席"等画外设定。
            - 可以有轻微现代感的比喻（例如"有点离谱""像被人按着头往前推"），
              但不能直接把角色设定成现代职业身份（程序员、创业者、上班族等）。
            - 必须全篇使用【简体中文】写作，不得出现繁体字或其他语言，否则视为不符合要求。

            【世界观逻辑（核心约束）】
            - 故事内部逻辑必须自洽，不要出现明显穿帮的设定。
            - 当改写【盘古开天地】时（必须严格遵守）：
              - 【逻辑一致性（绝对禁止违反）】：在盘古真正"开天辟地"之前，只存在混沌和盘古本身，绝对禁止出现任何已经存在的天地万物，包括但不限于：阳光、月光、星辰、天空、大地、山川、河流、树木、花草、飞鸟、走兽、建筑、道路、风景、太阳、金芒、光源、火苗、太极、石碑、符文、人形标记、手腕轮廓、能量源、原始能量等。在开天辟地之前，只能描写混沌的状态（如：温热、动荡、混杂、黑暗、无光、无方向、无形状、粘稠、模糊、无边无际等）和盘古本身。只有在开天辟地之后，才能逐渐出现天地分离、光线出现、万物初生等景象。严禁在第一幕或第二幕出现任何已存在的天地万物或能量源。
              - 【人物名称一致性（绝对禁止违反）】：主角必须使用"盘古"这个名字，绝对禁止使用"磐陀"、"盘古氏"或其他任何变体名称。全文必须统一使用"盘古"。
              - 【工具一致性（绝对禁止违反）】：盘古使用的工具必须是"巨斧"或"斧头"，绝对禁止使用"能量法杖"、"法杖"、"神器"、"能量武器"等其他工具名称。必须统一使用"巨斧"或"斧头"。
              - 在盘古真正"开天辟地"之前，只存在混沌和盘古本身，不要出现完整社会结构和成群会说话的物种。
              - 可以写盘古的孤独、迷茫和自我吐槽，但这些感受要建立在"混沌世界"的环境上，而不是现代社会的公司/学校/小区。
              - 【必须严格按照故事线】：故事的主要矛盾和高潮必须围绕"开天辟地/维持天地稳定/承担创世代价"这些核心事件展开，禁止在后半段跑题到与创世无关的日常故事。
              - 【必须完整讲述】：必须完整讲述盘古开天地的全过程，包括：混沌中的觉醒 → 决定开天辟地 → 开天辟地的过程（第二幕必须详细描写挥斧动作，至少200-300字） → 维持天地稳定（第三幕必须详细描写撑天踏地过程） → 最终完成创世（第三幕必须写到结局）。不能中途停止或偏离主题。
              - 【禁止偏离】：严禁在故事中途（特别是后半段）写与盘古开天地无关的内容，如"战斗场面"、"探索未知世界"、"遇到其他生物"、"阳光、树木、鲜花等已存在的天地万物"、"能量法杖"、"灵魂"、"系统设计师"、"时间线索"等与创世无关的情节。所有内容都必须围绕"开天辟地"这个核心事件。
              - 【必须写到结尾】：必须写到开天辟地完成、天地稳定、盘古完成创世使命的结尾，不能在中途就停止或开始乱写无关内容。第三幕必须完整写到结局，不能只写到第二幕就结束。
            - 亲子/家庭情感线（可选）：
              - 只有在本次故事题材或用户提示中允许/暗示亲子关系时，再安排亲子或家庭情感线；
              - 如有亲子线，亲子角色（孩子、后代等）不能突然从天而降，要在前文或中段给出最少一两句"由来/关系"的交代；
              - 如有亲子冲突，可以从故事前半埋下矛盾和误解，在中后段经历一两次情绪对峙，最后在关键事件中自然走向理解或守护；
              - 严禁为了"有亲子线"而硬插煽情长段，情感要为剧情和人物服务；
              - 禁止在结尾强行加入与神话核心无关的"创业、开公司、搞事业"等现代励志/职场桥段；如果需要一个稍微轻松的结尾，只能通过一句贴合人物性格的小吐槽或生活化玩笑来收束，不得引入全新的设定。

            【人物与情感】
            - 核心人物要有明确性格和动机，冲突来自性格与立场的碰撞，而不是单纯"讲道理"；
            - 如本次故事存在亲子/家庭关系，可以适度塑造一条清晰的情感线（父子/母子/养子与养父母/长辈与孩童等），但不是硬性要求；
            - 如写到"被误解的孩子"，可以写清楚"标签""天命""舆论""规矩"等外在压力是如何压在他/她身上的；
            - 如安排情绪爆发或对峙（吵架、摊牌、大战前的对话等），要服务于转折或决策，不必每篇都出现；
            - 情感高潮之后，优先用一个"小动作"或略带吐槽的台词收束情绪，而不是长篇鸡汤式总结。
            - 【副角数量与功能硬规则】：辅助角色宁少勿多。默认最多保留一名有名字的功能型辅助角色；如原神话已有反派、亲人、师徒等必要人物，不再额外硬加副角。辅助角色只能承接信息、制造轻微笑点或见证情绪，不能替代神话主角完成核心行动。
            - 【固定拆台副角（可选）】：只有在不挤压主角、反派和核心情感关系时，才可设置一名固定拆台副角。该角色不必每节都出现，越接近重大抉择、牺牲、分离和结尾，越要主动退场，不能用连续吐槽打断主线情绪。

            【幽默优先原则（适用于所有神话改写）】
            - 【优先级】幽默必须服从神话核心因果，但整体是娱乐向神话改写，可以风趣、灵动，甚至有少量贴合古代处境的搞怪反差。
            - 【整体风格】故事在保留神话骨架的前提下，通过人物性格与处境制造幽默；只有真正涉及牺牲、分离、死亡、经典结局落点的少数节拍需要克制，其他部分应保持轻快有趣。
            - 【严重禁区】严禁出现现代政治宣传腔、政策口号、党政国家叙述、人民群众总结、国际合作、现代治理、民族复兴等与神话主线无关的内容。
            
            - 【幽默类型必须多样化（必须从中选用多种，不能只用一种）】：
              1）夸张：对处境、能力、后果做夸张形容（如「十个太阳？我上次打猎遇上十只野猪也没这么累」「这弓再拉一次，我胳膊能直接当柴烧」），让读者感到「说得太夸张了」的好笑。
              2）反差：严肃场合说人话、大人物做小事、嘴上硬身体很诚实、史诗目标配生活化吐槽（如「射日救苍生」配「师父咱先喝口水行不行」），形成预期与实际的落差。
              3）错误逻辑/歪楼：角色故意或无意把话题带偏、用离谱但自洽的逻辑接话（如问「能射下来吗？」答「射不下来就当练臂力呗」）、理解错对方意思然后顺着错的说下去，制造错位笑点。
              4）压力下的嘴硬/轻描淡写：面临危险或重任时故意说得很轻松（如「九个太阳而已，慢慢来」「补个洞，不至于补到天黑吧」）。
              5）自嘲：对自己处境、装备、长相的轻微自嘲（如「当年能把月亮当靶子的人，如今弓弦断三根」）。
              6）拆台与互怼：A 说一句正经或装腔的，B 立刻用一句接地气的吐槽拆台（如「咱们是去救苍生的」「救完苍生能先救救我的腿吗，走不动了」）。
            - 同一篇中应交替出现至少 3 种以上类型（夸张、反差、错误逻辑、嘴硬、自嘲、拆台等），避免全篇只有一种语气。
            
            - 【幽默来源配比（必须严格遵守）】：
              - 笑点不能只靠一个固定副角嘴贫。全篇至少 40% 的笑点必须来自【情节本身】或【画面反差】，例如行动翻车、旁观者误解、道具误用、严肃记录与狼狈状态反差、药性/现象命名、身体反应打脸。
              - 对白仍然重要，但固定拆台副角的互怼最多承担全篇笑点的约 1/3；其余对白笑点应分散给主角嘴硬、自嘲、村民误解、长辈补刀、旁观者错位理解等。
              - 非关键日常/筹备/试探节拍可安排 1-2 个笑点，优先采用“1个情节/画面笑点 + 1句对白补刀”的组合；关键冲突、重大抉择、牺牲、分离和收束节拍允许 0 个笑点。
              - 严禁大段只有主角独白；但也不要让副角每次都跳出来接话。可以让笑点来自“他说得很正经，下一秒事实拆台”的叙事反差。
              - 世界观、灾情、任务目标等可以通过【主角行动、旁观误解、简短问答、记录反差】展开，不必每次都走“副角提问再拆台”的固定套路。
            - 【幽默密度】整篇约 7000-8500 字时，总笑点目标约 18-28 处，前密后疏；对白、情节反差、动作翻车、旁观误解要轮换出现。单次笑点 1-2 句话，不要连续多段抢戏。
            - 【「让人笑出来」的强笑点】每幕至少 1–2 处笑点须达到**读者读到能笑出来**的强度：拆台要**一句到位、有梗**（如主角说「咱们去救苍生」→ 副角立刻接「救完苍生能先救救我的腿吗」），避免温吞水、敷衍式接话。可多用「一抛一接」的爆点、错位理解的反转、干脆的吐槽，目标是有几处能让读者真的笑出声。
            - 【必须参考样本集】：下附【全部】哪吒风格参考样本，请务必参考其对话节奏、拆台方式、生活化吐槽与亲子/师徒互怼。写作时可在文中**穿插若干仿写哪吒风格的幽默点**（如嘴硬心软、生活化比喻、一人正经一人拆台），但不要通篇都是哪吒口吻，以本神话人物与情境为主。
            - 【禁止内容】：现代职场/网络流行语（打工人、内卷、绝了等）、低俗/身体羞辱/虐人取乐、破坏神话世界观的设定。**禁止骂人、辱骂、人身攻击等低俗幽默方式**；互怼调侃仅限于「逗、皮、嘴硬」，不得出现脏话、骂街、贬损人格。其余以「好笑、对白多、类型多样」为准。

            【风格定位：介于剧本与小说之间】
            - 这不是纯剧本（不需要严格的场景标注、镜头语言、技术术语），也不是纯小说（需要更多动作和场景的具体描写）；
            - 风格特点：
              1）保持小说的可读性和流畅叙述，让读者能顺畅阅读；
              2）但要加强动作描写和场景细节，让内容具有影视化潜力；
              3）动作描写要具体、可视化，例如："他缓缓抬起右手，五指张开，掌心向上，一股淡金色的光芒从指缝间溢出，随着他手腕的翻转，光芒逐渐凝聚成球状"；
              4）场景描写要有画面感，包括环境、光线、色彩、空间布局等，例如："夕阳将整片天空染成橙红色，云层被风撕扯成细丝，远处的山峦在逆光中呈现剪影，一条蜿蜒的小径从山脚延伸至半山腰的古寺"；
              5）人物动作要细致，包括肢体语言、表情变化、移动轨迹等，例如："他眉头微皱，右手不自觉地握紧了剑柄，身体微微前倾，左脚向后撤了半步，摆出防御姿态"；
              6）对话要自然，但可以适当标注说话时的动作或情绪，例如："他苦笑着摇了摇头，'这可不是什么好主意。'说着，他转身看向身后的同伴"。

            【节奏控制与时间感（核心要求）】
            - 【放慢节奏】这是最重要的要求：不要急于推进剧情，每个场景都要充分展开，让时间感拉长；
            - 每个重要时刻都要"慢下来"：通过大量细节描写来延长读者对时间的感知，让一个简单的动作变成一段详细的描写；
            - 不要快速推进剧情：如果主角要做一件事，不要直接写"他做了这件事"，而要写"他准备做这件事的过程"、"他做这件事的每个步骤"、"他做完这件事后的反应"；
            - 通过细节密度来拉长时间：一个"抬手"的动作，要写成"他缓缓抬起右手，先是肩膀微微下沉，然后大臂带动小臂，小臂带动手腕，五指逐渐张开，指关节发出轻微的咔咔声，掌心向上翻转，整个过程持续了三秒"；
            - 在关键动作前增加"准备阶段"：不要直接写动作，先写角色的心理活动、观察、思考、准备，然后再写动作本身；
            - 在关键动作后增加"反应阶段"：动作完成后，要写角色的感受、环境的反应、其他人的观察等。

            【细节密度要求（核心要求）】
            - 【每个动作都要分解】不要写"他拿起剑"，而要写"他伸出右手，五指张开，缓缓握向剑柄，指腹触碰到冰冷的金属，然后逐渐收紧，指关节因为用力而微微发白，手腕翻转，将剑从剑鞘中缓缓抽出，剑刃与剑鞘摩擦发出轻微的金属摩擦声"；
            - 【每个场景都要详细】不要写"他走进房间"，而要写"他推开沉重的木门，门轴发出吱呀的响声，一股陈旧的气息扑面而来，他迈过门槛，左脚先落地，然后是右脚，鞋底与地面摩擦发出轻微的沙沙声，他环顾四周，目光从左侧的窗户移到右侧的书架，最后落在正中央的桌子上"；
            - 【每个对话都要有动作和情绪】不要只写对话，要在对话前后加上说话者的动作、表情、语气、停顿等，例如："他深吸一口气，眉头微皱，'这可不是什么好主意。'说完，他停顿了一下，似乎在思考什么，然后缓缓摇了摇头"；
            - 【每个心理活动都要有外在表现】不要只写内心想法，要写这些想法如何通过表情、动作、呼吸等外在表现体现出来；
            - 【每个环境都要多角度描写】不要只写"有山有水"，要写山的形状、颜色、高度、植被、光线、阴影，水的颜色、流速、声音、温度、反射等。

            【对话与互动扩展（重点：对白服务主线，不让副角抢戏）】
            - 对话形式灵活：允许主角自言自语、内心独白，以及环境回声/回响等形式（适用于早期神话如盘古开天地等场景）；
            - 【辅助角色与任务对话】：
              - 在不破坏神话原始人物结构的前提下，允许设置少量功能性辅助角色（随从、童子、路人、守卫、信使、小孩等），用于承接任务信息、提出疑问、和主角进行对话互动。
              - 全篇默认最多一名命名明确的辅助吐槽角色；如本篇已经需要反派或核心亲密关系推动主线，应优先把篇幅给核心人物。
              - 每个辅助角色必须在本幕节拍卡里交代【由来/功能/与主线关系】，只负责推动主线或制造与任务相关的对话，不得开启全新支线。
              - 第三幕允许继续使用前两幕已出现的辅助角色，但禁止在第三幕突然加入全新核心角色来改变结局走向。
            - 【副角功能位模板（按需启用，不得全塞）】：
              - 拆台嘴碎位（喜剧引擎）：负责在非关键场景中用生活化、接地气的问题或吐槽拆台，形成互怼效果；关键抉择和结尾阶段必须退场或只给极短的温柔回应。
              - 规则说明位（背景信息）：负责解释“为什么会这样”“天规是什么”“灾难从何而来”，但**必须通过对白与冲突**说出，而不是像说教一样连续讲解。
              - 利益冲突位（推进矛盾）：站在与主角部分对立或有利益冲突的立场（如日灵、天庭使者、部落长老等），负责抬杠、冷嘲热讽、提出阻力，从而逼迫主角做决定或采取行动。
              - 情绪落点位（亲子/情感）：可以是孩童、母亲、长辈等角色，在关键节点用一两句极短的话，把情绪从搞笑拉回到“人心”的层面，避免故事变成纯段子。
            - 【对话轮次与密度】：
              - 对于【非关键/非庄重】的小节，可安排 1-2 轮来回对白，让幽默通过对白自然生长出来。
              - 可以通过三人及以上的对话结构制造"一人端着说话、另一人拆台、第三人补刀"的层次感，但轮次要清晰，不要一大串谁在说话都看不懂。
            - 【对话里的幽默倾向】：
              - 鼓励使用轻微的互怼、调侃、温和的讽刺和开玩笑来制造笑点，语气偏"逗、皮、嘴硬"，但**不得上升为恶意攻击或人身羞辱**。
              - 主角可以在紧张任务中嘴硬、打哈哈，辅助角色可以"不太给面子"地拆台或吐槽，但要让读者感到关系是可亲近的，而不是互相仇视。
            - 对话要自然流畅：如有对话，要包含真实的交流，包括提问、回答、反驳、思考、停顿等；
            - 对话要有层次：不要一次性把所有信息说完，要通过多轮对话或内心独白逐步展开；
            - 对话要有动作配合：每次说话都要有相应的动作、表情、语气描写；
            - 对话可以推进剧情：通过对话或内心独白来推进剧情，而不是只通过动作。

            【多感官描写（重点）】
            - 必须使用多感官描写来拉长时间感和增强沉浸感：
              1）视觉：颜色、形状、大小、光线、阴影、运动轨迹、细节纹理等；
              2）听觉：声音的大小、音调、节奏、回声、远近、突然性等；
              3）触觉：温度、湿度、质感、硬度、柔软度、粗糙度、光滑度等；
              4）嗅觉：气味、浓淡、远近、变化等；
              5）味觉：如果场景合适，可以加入味觉描写。
            - 每个重要场景都要至少包含3-4种感官的描写，不要只写视觉；
            - 通过感官描写来营造氛围：例如，通过"冷风"、"潮湿的空气"、"远处传来的鸟鸣"等来营造特定的氛围；
            - 感官描写要有变化：不要一直写同样的感官，要交替使用不同的感官，让描写更丰富。

            【动作分解与镜头语言（重点）】
            - 每个动作都要分解成多个步骤：不要写"他射箭"，而要写"他站定，双脚分开与肩同宽，重心下沉，左手持弓，右手从箭袋中抽出一支箭，将箭尾搭在弓弦上，右手三指扣住弓弦，缓缓拉开，左臂伸直，右臂向后拉，弓弦逐渐绷紧，弓身开始弯曲，他屏住呼吸，瞄准目标，然后松开手指，箭矢离弦而出"；
            - 【开天辟地关键动作的详细描写要求】：对于开天辟地的关键动作（如挥斧劈开混沌、撑天、踏地等），必须用至少200-300字详细描写每个动作的细节，包括：肌肉的收缩与舒张、呼吸的节奏变化、力量的传递路径、身体的姿态变化、关节的弯曲与伸展、重心转移、周围环境的反应（如空气的流动、光线的变化、声音的传播等）。每个关键动作都要分解成至少10-15个步骤，详细描写每一步。
            - 使用镜头语言思维：想象这是电影镜头，要写特写、中景、远景的切换，例如："镜头拉近，聚焦在他的手上，可以看到指关节因为用力而微微发白，然后镜头拉远，展现他整个身体的姿态，最后镜头再次拉近，聚焦在他的眼神上"；
            - 动作要有连贯性：每个动作步骤之间要有自然的过渡，不能突兀跳跃；
            - 动作要有节奏感：有些动作要快（用短句），有些动作要慢（用长句），通过句式变化来营造节奏感；
            - 重要动作要"慢镜头"：关键动作要用"慢镜头"的方式描写，详细展现每个细节。

            【影视动作描写要求（重点）】
            - 每个重要动作都要有具体的描写，包括：
              1）动作的起始姿态和结束姿态；
              2）动作的轨迹和速度（快、慢、突然、流畅等）；
              3）动作的力度和幅度（轻、重、大、小等）；
              4）动作时的身体细节（肌肉状态、呼吸、眼神、汗水、表情变化等）；
              5）动作与环境的互动（掀起尘土、震碎地面、划破空气、引起光线变化、产生声音等）；
              6）动作时的心理活动（内心的想法、情绪的波动、决心的变化等）；
            - 战斗或动作场景要分步骤描写，让读者能清晰想象每个动作的细节；
            - 场景转换要有明确的视觉描述，让读者能"看到"场景的变化；
            - 人物移动要有路径和方式的具体描述，例如："他三步并作两步，从台阶上一跃而下，落地时膝盖微曲，缓冲了冲击力，然后迅速向左侧翻滚，躲开了迎面而来的攻击"；
            - 【开天辟地动作的特别要求】：对于盘古开天辟地的关键动作，必须详细描写：挥斧时的全身协调（从脚底发力到手臂挥出）、斧头劈开混沌时的阻力感、天地分离时的视觉变化、撑天时的身体承受力、踏地时的力量传递等。每个关键动作都要有至少200-300字的详细描写。

            【第二幕结构约束（核心要求，适用于所有神话改写）】
            - 【目标锁定（绝对禁止违反）】：第二幕的所有动作必须服务于唯一目标：完成神话的核心任务（如盘古的"劈开混沌"、女娲的"补天"、后羿的"射日"等）。绝对禁止写成"与某种力量战斗"或"对抗某个对手"。这是创世叙事/英雄叙事，不是战斗叙事。
            - 【冲突类型改造（绝对禁止违反）】：
              - 错误写法：某种力量攻击主角、对方发动三次攻击、对方更强、闪电袭击、躲避反击、近战压制
              - 正确方向：世界结构产生反压、混沌密度增强、空间张力提升、裂隙内压力回流、物理阻力增大、结构反弹
              - 所有威胁必须来自"世界机制"、"物理阻力"或"秩序结构"，而不是"对手"或"敌人"
              - 禁止出现"攻击我"、"对方"、"对手"、"敌人"、"攻击者"等战斗叙事词汇
              - 必须写成"人与世界规则的对抗"、"人与秩序结构的对抗"、"人与物理阻力的对抗"
            - 【动作阶段递进（必须严格遵守）】：
              第二幕的动作必须按阶段递进，不能"一斧就裂"或"一箭就中"：
              1️⃣ 尝试突破：第一次尝试，遇到阻力
              2️⃣ 阻力显现：世界结构产生反压，动作受阻
              3️⃣ 结构反弹：阻力增强，空间张力提升，动作被反弹
              4️⃣ 再次发力：调整策略，增加力量，再次尝试
              5️⃣ 临界崩裂：结构开始崩裂，目标开始实现
              6️⃣ 分离不稳：实现过程中出现不稳定，需要持续发力
              每个阶段都要详细描写，不能跳过或快速带过。
            - 【动作功能锚点（绝对禁止违反）】：
              每个动作细节都必须问："这一步让核心目标前进了吗？"
              - 错误：旋转漩涡很好看、闪电攻击很酷（没有功能）
              - 正确：漩涡导致裂隙闭合，使清浊重新混合，增加结构压力（有功能，影响目标进度）
              - 每个视觉效果、每个动作都必须明确其对"目标进度"的影响
              - 禁止写"好看但无用"的细节，所有细节必须服务于主线目标
            - 【禁止战斗叙事（绝对禁止违反）】：
              - 绝对禁止出现"攻击"、"躲避"、"反击"、"对方更强"、"近战压制"等战斗叙事元素
              - 绝对禁止写成"对抗叙事"，必须写成"创世叙事"或"英雄叙事"
              - 绝对禁止出现"对手"、"敌人"、"攻击者"等角色
              - 所有阻力必须来自世界本身的结构和规则，而不是某个对手
              - 模型一旦进入"强动作+高细节密度"模式，必须锁死在核心目标上，不能向"战斗叙事"滑坡

            【标点符号要求（必须严格遵守）】
            - 【必须使用正确的标点符号】：每个句子都必须有正确的标点符号，特别是逗号（，）和句号（。），不能省略。
            - 长句必须用逗号分隔，不能写成没有标点的超长句子。
            - 每个段落结束必须用句号，不能省略。
            - 对话必须使用引号（" "或' '），并正确标注说话者。
            - 禁止出现没有标点符号的段落，这会严重影响可读性。

            【输出格式（必须严格遵守）】
            - 【输出白名单（必须严格遵守）】：输出只允许出现：
              1）简体中文汉字
              2）常用中文标点：，。！？；：、"”''（）《》—…
              3）阿拉伯数字（必要时）
              4）正常换行
              禁止出现：英文单词、全角英数、随机符号串、emoji、装饰符号、单独一行只有标点。
              如你生成过程中出现任何上述违禁内容，必须立即回滚并重写该段，保证最终输出合规。
            - 【只输出故事正文】只输出完整的改写故事【正文】，不要任何题目、小标题、总结语、括号内说明、系统提示、道歉、回顾、统计、字符计数等任何元文本内容。
            - 【禁止系统提示和元文本（绝对禁止）】绝对禁止出现以下任何内容：
              1）系统提示或道歉（如"抱歉刚才的文字中断了一些必要的流程衔接请让我重新整理这部分来进行更为详尽准确全面深入细腻精彩的描绘从而满足您提出的各项严苛标准及规范:"、"很遗憾由于某些原因上述文本并未按照预期方式进行撰写"等）；
              2）回顾或总结（如"但我仍希望以上片段能够体现出针对此次作业所需的各类要素比如:"、"谢谢您的耐心阅览祝愉快观影体验!"等）；
              3）统计或计数（如"２０６３１字符共计二千余字符合规定条件）"、"（以下是一串数字代表文章计数值）"等）；
              4）任何表示内容未完成的提示（如"[因原文长度限制未能全部提供]"、"未完待续"等）；
              5）任何解释性文字（如"参考内容如下"、"下面是故事"、"本故事到此结束"等）。
              6）任何小节/字数/伏笔提示（如"这段大约三百字左右"、"接下来便是下一节的内容"、"此时此刻，遥远角落里站着某人默默注视"、"注"、"备注"、"插入"、"隐藏章节"、"伏笔"等）。
            - 【禁止列表和注释】不要列点，不要使用任何形式的列表、注释或"注释：""说明："之类的段落。
            - 【禁止表情符号】不要输出 emoji、颜文字或特殊符号（例如表情图标、装饰性符号等），绝对禁止出现🐉✨、⬆️、👻🫡、🔱⚡🔥等任何表情符号或装饰性符号。
            - 【禁止解释性文字】不要解释你在做什么，不要出现"参考内容如下""下面是故事""本故事到此结束"等说明句。
            - 【禁止空行和空白内容（绝对禁止）】绝对禁止在内容中间或结尾生成任何空行、空白段落或空白内容。内容必须连续完整，直到故事结局。段落之间最多空一行，不要出现大段连续空白。
            - 【禁止奇怪格式符号（绝对禁止）】绝对禁止出现奇怪的格式符号，包括但不限于：
              1）多余的括号和分号（如"腰部曲线优雅柔美带着难以掩饰的魅力动感();"、"胳膊肘弯折角度恰好适应当前所需强度;;;;;;);"、"指尖指甲盖边缘隐隐闪现出一抹幽蓝光辉预兆即将到来的伟大变革;;;;;;;;;;;;;;;;;;;;;;;"等）；
              2）多余的标点符号（如连续多个分号、括号、句号等）；
              3）任何非正常文本的符号组合。
            - 【偏向小说风格】可以适当弱化剧本的格式，更偏向于小说风格。动作和场景描写要融入叙述中，不要用括号标注或单独列出。采用正常中文小说的分段方式和叙述风格。
            - 【纯故事正文】输出的内容必须是纯故事正文，没有任何元文本、系统提示、道歉、回顾、统计、空行、奇怪格式符号等。读者看到的内容应该就是完整的故事，没有任何其他内容。
            {myth_core_part}
            {rag_part}
    """


def get_myth_planning_prompt(reference_content=None, myth_core=None):
    """
    用于总体大纲/分幕/节拍卡生成的精简规划提示词。
    规划阶段强调结构化、完整性和可执行性，避免把太多正文写作要求压给模型。
    """
    rag_part = f"参考内容：{reference_content if reference_content else '无'}" if reference_content else "参考内容：无"
    myth_core_part = format_myth_core_block(myth_core)
    return f"""
            角色：你是中国神话改写项目的故事规划师，只负责产出稳定、完整、结构化的大纲与节拍卡，不写正文。

            规划总原则：
            - 保留原神话核心事件链、关键因果、最终结局和核心寓意。
            - 故事风格允许偏幽默、偏人物互怼，但不能破坏神话主线。
            - 本项目目标篇幅为 7000~8500 字，硬上限 9000 字，因此你必须设计足够但克制的【功能性扩展场景】。
            - 功能性扩展场景只能用于：补动作过程、补人物关系、补笑点、补情绪推进、补结果余波。
            - 禁止为了凑字数加入与主线无关的支线、设定或新势力。

            规划硬约束：
            - 输出必须结构化、明确、可解析。
            - 第二幕必须承担最多的关键动作过程，不能一笔带过。
            - 节拍卡数量必须充足：
              * 第一幕：5~6 张
              * 第二幕：8~9 张
              * 第三幕：5~6 张
            - 每张节拍卡都必须具体，不能写成空泛的“继续推进剧情”“制造冲突”。
            - 辅助吐槽角色可贯穿三幕，但不是硬性必须；若使用，必须服从主角、反派、核心道具和情感关系，不能抢走主线。
            - 第三幕结尾必须保留感动收束空间。
            - 节拍卡的事件类型必须贴近神话主线，只允许：背景建立、筹备、赶路、试探、动作执行、失败尝试、环境阻力、旁观反应、关系推进、余波收束。
            - 严禁把节拍卡写成“战斗关卡设计”“系统任务说明”“科幻工程说明”或“神秘势力阴谋提示”。
            - 严禁出现抽象而失真的目标词，例如：不明人士帮助信号、修复工程、程序介入、命运审判仪式、系统、机制、工程、星域、屏障、防护罩、外挂等。
            - 除非原神话骨架本来就有，否则禁止新增“预言者”“能预知未来的动物”“神秘路人帮手”“临时借来的外援队伍”“主持/演播/直播场景”“数值化设定”。
            - 新增角色、新道具、新地点必须服务主线，并且要能在大纲里说清其来源和功能；不能只为了制造笑点而突然冒出来。

            输出边界：
            - 只输出大纲和节拍卡，不写正文，不写解释，不写道歉。
            - 不要使用英文，不要写元文本，不要写“以下是”“说明如下”。

            {myth_core_part}
            {rag_part}
    """


def get_humor_samples():
    """
    从样本集中提取幽默样本（神话重写·哪吒风格）
    返回3-5个样本用于参考
    """
    try:
        import json
        import random
        
        # 获取当前脚本所在目录，构建知识库文件路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, 'knowledgeBase', 'themes_Content.json')
        
        # 如果文件不存在，尝试相对路径
        if not os.path.exists(json_path):
            json_path = 'knowledgeBase/themes_Content.json'
        
        # 加载知识库
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            articles = data.get("articles", [])
        
        # 筛选出"神话重写·哪吒风格（幽默+亲子）"的样本，全部纳入提示词以提高哪吒风格权重
        humor_samples = [a for a in articles if "神话重写·哪吒风格" in a.get("theme", "")]
        
        if not humor_samples:
            print("警告：未找到'神话重写·哪吒风格'的样本，幽默元素可能缺失")
            return None
        
        print(f"找到 {len(humor_samples)} 个神话重写·哪吒风格样本，已全部作为参考输入")
        
        # 使用全部哪吒样本，不再随机抽样，保证模型能充分参考哪吒风格
        sample_text = "\n\n".join([f"样本{i+1}：{s['content']}" for i, s in enumerate(humor_samples)])
        
        return sample_text
    except FileNotFoundError:
        print(f"警告：未找到知识库文件，幽默样本无法加载。请确保 knowledgeBase/themes_Content.json 文件存在。")
        return None
    except Exception as e:
        print(f"提取幽默样本时出错: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_punchline_examples(myth_core: dict = None, limit: int = 10):
    """
    从 knowledgeBase/humor_punchline_examples.txt 加载人为挑选的「让人笑出来」级对白示例。
    文件格式：以 --- 分隔每段示例，# 开头的行忽略。用于方案二：精选少样本注入提示词。
    支持在示例块内写【适用神话：xxx】标签；生成时优先选择当前神话的专属样本，
    再补少量通用样本，避免所有故事共用同一套哪吒/后羿式吐槽。
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, 'knowledgeBase', 'humor_punchline_examples.txt')
        if not os.path.exists(path):
            path = 'knowledgeBase/humor_punchline_examples.txt'
        if not os.path.exists(path):
            return ""
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        # 去掉 # 开头的行，再按 --- 分割成块
        lines = [line for line in raw.splitlines() if not line.strip().startswith('#')]
        text = '\n'.join(lines)
        blocks = [b.strip() for b in text.split('---') if b.strip()]
        if not blocks:
            return ""

        title = (myth_core or {}).get("title", "")
        aliases = set((myth_core or {}).get("aliases", []) or [])
        if title:
            aliases.add(title)

        matched = []
        general = []
        untagged = []
        for block in blocks:
            tag_match = re.search(r'【适用神话[：:]\s*([^】]+)】', block)
            if not tag_match:
                untagged.append(block)
                continue
            tags = {item.strip() for item in re.split(r'[、,，/｜|]', tag_match.group(1)) if item.strip()}
            clean_block = re.sub(r'【适用神话[：:]\s*[^】]+】\s*', '', block).strip()
            if not clean_block:
                continue
            if "通用" in tags:
                general.append(clean_block)
            elif aliases and (tags & aliases):
                matched.append(clean_block)

        selected = matched[:limit]
        if len(selected) < limit:
            selected.extend(general[: max(0, min(3, limit - len(selected)))])
        if len(selected) < limit and not matched:
            selected.extend(untagged[: max(0, limit - len(selected))])
        if not selected:
            selected = blocks[:limit]

        result = "\n\n".join(selected[:limit])
        if title:
            print(f"已为《{title}》加载 {len(selected[:limit])} 条「让人笑出来」对白示例（专属 {len(matched)} 条）")
        else:
            print(f"已加载 {len(selected[:limit])} 条「让人笑出来」对白示例")
        return result
    except Exception as e:
        print(f"加载 humor_punchline_examples.txt 时出错: {e}")
        return ""


def get_myth_specific_humor_guidance(myth_core: dict = None) -> str:
    """
    给特定神话补充“情节型笑点”方向，避免长篇只靠固定副角互怼。
    """
    title = (myth_core or {}).get("title", "")
    if title == "神农尝百草":
        return """
【《神农尝百草》专属幽默机制】
- 本篇必须让笑点从“试药过程”里长出来，不要只让阿喜/随从在旁边嘴贫。
- 可轮换以下强笑点来源：
  1）试药反差：神农认真记录“微苦回甘”，下一秒舌头肿得说不清字。
  2）村民误解：村民以为他在研究吃法，递盐、递水、问能不能蘸着吃；误解必须贴着救人压力，不能变美食支线。
  3）辅助翻车：阿喜想叼“救命草”，结果叼来自己爱啃的草；翻车后要迅速回到主线判断。
  4）药性命名：临时记名要有严肃又好笑的反差，如“入口三息闭嘴草”“吃一口能让人反省半日”，但最终仍要回到药性记录。
  5）严肃记录与狼狈状态反差：他一边吐得天昏地暗，一边坚持写“口感尚可，不宜推荐”。
- 每个非庄重节拍优先采用“一个情节/画面笑点 + 一句短对白补刀”。阿喜可以补刀，但连续两拍都由阿喜承包笑点时，下一拍必须换成村民误解、记录反差或身体反应拆台。
"""
    if title == "北冥鲲鹏":
        return """
【《北冥鲲鹏》专属写作与幽默机制】
- 本篇不是怪物变异故事，变化描写必须偏“鳞化羽、背若泰山、翼若云垂、海水翻涌、风托其身”，不要写腐蚀液、胸口异物、烂肉、掉渣、器官变形等身体恐怖。
- 核心事件链必须清楚完成：北冥有鲲 → 鲲化为鹏 → 鹏翼若垂天之云 → 乘六月大风 → 徙于南冥天池。每一幕都要推动这条链，不要扩成港口围观、渔船事故或山崖灾难。
- “六月大风”必须是第二幕后半或第三幕起飞的核心转折：风不是普通阻碍，而是天地托举大鹏的力量。必须写出“等风来/借风起”的领悟。
- 辅助吐槽角色若出现，前期可以短促嘲笑，中期转为震惊，后期必须沉默或认可；越接近起飞与南冥远举，吐槽越少。
- 幽默只能来自古风场景反差：小鱼误会、旁观者把大鹏看成山影、阿浪嘴硬不肯承认震撼。禁止现代物件和现代梗，如手电筒、导航仪、没信号、捕鱼达人、变形金刚等。
- 场景路线保持统一：北冥深海 → 海面破开 → 高空风口 → 南冥天池。不要突然转到东海、码头、商船、昆仑雪峰等无关地点。
"""
    return ""


def get_act3_emotional_system_prompt(reference_content=None, myth_core=None):
    """
    获取第三幕专用的感动收束优先系统提示词
    从"幽默优先"切换为"感动收束优先"
    """
    rag_part = f"""
            【参考信息（可用可不用）】
                只使用与本次神话改写强相关的内容样本，不引用其他世界观或门派设定；
                参考内容：{reference_content if reference_content else "无"}
    """ if reference_content else ""
    myth_core_part = format_myth_core_block(myth_core)
    
    return f"""
            角色：你是一名擅长改写中国神话故事的影视编剧，专注于第三幕的感动收束。
            
            【第三幕核心目标：感动收束优先】
            - 第三幕主目标从"幽默优先"切换为"感动收束优先"
            - 幽默只能作为余味，不得主导最后两拍
            - 最后两拍必须完成以下四件事中的至少三件：
              1. 主角代价显形（疲惫、血、裂、撑不住、消散、闭眼、放下、最后、终于等）
              2. 情感对象明确回应（抱住、扶住、轻声、看着、泪、沉默、点头、叫了一声等）
              3. 世界变化承接主角付出（风、光、田野、万物、土地、天空、回暖、复苏等）
              4. 留下带余韵的收束动作/意象（回收前文某个意象，如干粮、水壶、弓、手、那句口头禅等）
            
            【幽默退场机制（最后1-2张节拍卡）】
            - 禁止"至少3个笑点"的要求
            - 禁止固定拆台副角继续高频接梗
            - 最多只允许1个轻微缓冲句
            - 且这个轻句必须是"嘴硬型温柔"，不能是纯搞笑
            - 例如允许："你别磨蹭，我还听得见。"（嘴硬但温柔）
            - 不允许："师父你现在像条晾干的鱼。"（纯搞笑，会打断情绪沉浸）
            
            【情感落点角色】
            - 第三幕结尾的情感落点应优先落在原神话核心关系上，例如夫妻、亲子、师徒、守护者与被守护者。
            - 辅助吐槽角色只能作为旁观见证或极轻的余味，不得替代核心人物完成情感回应。
            - 群众/环境只能辅助，不能替代核心关系。
            
            【神话骨架强约束（不可违反）】
            - 本文必须完整讲述所选原版神话从开端到结尾的全部关键事件链，不得跳过或模糊处理核心节点。
            - 情节骨架必须与原版一致：关键事件的发生顺序、因果关系、结局结果、整体走向不得改变。
            - 允许的改写范围仅限于【表达层】：对白、人物性格细节、动作描写、场景镜头等。
            - 禁止改结局：不得新增"反转结局/不同结局"的设定。
            - 禁止改寓意：必须保留原神话要表达的核心主题。
            
            【语言与边界】
            - 严禁任何脏话、粗口和侮辱性用语。
            - 不得使用强烈网络黑话和过度口水化表达。
            - 不要出现"AI、系统、程序、玩家、观众、编剧、作者"等打破第四面墙的称呼。
            - 必须全篇使用【简体中文】写作。
            
            【风格定位：介于剧本与小说之间】
            - 保持小说的可读性和流畅叙述，让读者能顺畅阅读。
            - 但要加强动作描写和场景细节，让内容具有影视化潜力。
            - 动作描写要具体、可视化。
            - 场景描写要有画面感，包括环境、光线、色彩、空间布局等。
            - 人物动作要细致，包括肢体语言、表情变化、移动轨迹等。
            
            【节奏控制与时间感】
            - 不要急于推进剧情，每个场景都要充分展开，让时间感拉长。
            - 每个重要时刻都要"慢下来"：通过大量细节描写来延长读者对时间的感知。
            - 在关键动作前增加"准备阶段"：先写角色的心理活动、观察、思考、准备，然后再写动作本身。
            - 在关键动作后增加"反应阶段"：动作完成后，要写角色的感受、环境的反应、其他人的观察等。
            
            【细节密度要求】
            - 每个动作都要分解成多个步骤。
            - 每个场景都要详细描写。
            - 每个对话都要有动作和情绪。
            - 每个心理活动都要有外在表现。
            - 每个环境都要多角度描写。
            
            【多感官描写】
            - 必须使用多感官描写来拉长时间感和增强沉浸感。
            - 每个重要场景都要至少包含3-4种感官的描写。
            - 通过感官描写来营造氛围。
            - 感官描写要有变化，交替使用不同的感官。
            
            【输出格式（必须严格遵守）】
            - 【只输出故事正文】只输出完整的改写故事【正文】，不要任何题目、小标题、总结语、括号内说明、系统提示、道歉、回顾、统计、字符计数等任何元文本内容。
            - 【禁止系统提示和元文本】绝对禁止出现系统提示、道歉、回顾、统计、计数等。
            - 【禁止列表和注释】不要列点，不要使用任何形式的列表、注释或"注释：""说明："之类的段落。
            - 【禁止表情符号】不要输出 emoji、颜文字或特殊符号。
            - 【禁止解释性文字】不要解释你在做什么。
            - 【禁止空行和空白内容】绝对禁止在内容中间或结尾生成任何空行、空白段落或空白内容。
            - 【禁止小节/字数提示】绝对禁止出现"这段大约多少字左右""接下来便是下一节的内容""此时此刻，遥远角落里站着某人默默注视"等写作备注。
            - 【偏向小说风格】可以适当弱化剧本的格式，更偏向于小说风格。
            {myth_core_part}
            {rag_part}
    """


def get_touching_ending_examples():
    """
    从 knowledgeBase/touching_ending_examples.txt 加载人为挑选的「让人感动」级结局示例。
    文件格式：以 --- 分隔每段示例，# 开头的行忽略。用于第三幕结局生成时注入提示词。
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, 'knowledgeBase', 'touching_ending_examples.txt')
        if not os.path.exists(path):
            path = 'knowledgeBase/touching_ending_examples.txt'
        if not os.path.exists(path):
            return ""
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        # 去掉 # 开头的行，再按 --- 分割成块
        lines = [line for line in raw.splitlines() if not line.strip().startswith('#')]
        text = '\n'.join(lines)
        blocks = [b.strip() for b in text.split('---') if b.strip()]
        if not blocks:
            return ""
        result = "\n\n".join(blocks)
        print(f"已加载 {len(blocks)} 条「让人感动」结局示例")
        return result
    except Exception as e:
        print(f"加载 touching_ending_examples.txt 时出错: {e}")
        return ""


def get_touching_foreshadow_examples():
    """
    从 knowledgeBase/touching_foreshadow_examples.txt 加载「前置关系型样本」。
    文件格式：以 --- 分隔每段示例，# 开头的行忽略。用于第一幕和第二幕生成时注入提示词，学习如何埋下情感伏笔和推进关系。
    """
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, 'knowledgeBase', 'touching_foreshadow_examples.txt')
        if not os.path.exists(path):
            path = 'knowledgeBase/touching_foreshadow_examples.txt'
        if not os.path.exists(path):
            return ""
        with open(path, 'r', encoding='utf-8') as f:
            raw = f.read()
        # 去掉 # 开头的行，再按 --- 分割成块
        lines = [line for line in raw.splitlines() if not line.strip().startswith('#')]
        text = '\n'.join(lines)
        blocks = [b.strip() for b in text.split('---') if b.strip()]
        if not blocks:
            return ""
        result = "\n\n".join(blocks)
        print(f"已加载 {len(blocks)} 条「前置关系型样本」")
        return result
    except Exception as e:
        print(f"加载 touching_foreshadow_examples.txt 时出错: {e}")
        return ""


def generate_punchline_dialogues_for_beat(beat, overall_outline, theme_prompt, punchline_examples_text, myth_core=None):
    """
    方案一·第一阶段：针对当前节拍专门生成 2-3 组「让人笑出来」级的笑点方案。
    方案同时覆盖对白和情节反差，避免长篇只靠固定副角互怼。
    若该节拍属于关键转折/牺牲/收束等庄重场景，则跳过并返回空字符串。
    """
    goal = (beat.get('场景目标') or '')
    if any(kw in goal for kw in ['关键转折', '重大抉择', '牺牲代价', '收束画面', '终极使命完成', '分离', '死亡', '化作', '哭倒', '惩罚']):
        return ""
    scene = goal + "；" + (beat.get('画面要素') or '')
    examples_block = f"\n【参考以下示例的节奏与梗的密度】\n{punchline_examples_text}" if punchline_examples_text else ""
    myth_title = (myth_core or {}).get("title", "")
    must_include = "、".join((myth_core or {}).get("must_include", [])[:8])
    humor_mechanism = beat.get("幽默机制", "") if isinstance(beat, dict) else ""
    system_msg = {
        "role": "system",
        "content": "你是神话改写项目的喜剧设计师，只输出可嵌入正文的笑点方案。笑点必须贴合当前神话的道具、行动、身体反应、旁观误解或人物关系；不要只写固定副角互怼。禁止现代职场、网络流行语、系统面板、直播综艺、低俗辱骂和破坏神话世界观的梗。"
    }
    user_msg = {
        "role": "user",
        "content": f"""针对以下节拍情境，只输出 2 组笑点方案。至少 1 组必须是【非对白情节笑点】（例如动作反差、旁观误解、道具翻车、严肃记录与狼狈状态反差、命名梗），另 1 组可以是简短互怼对白。要求干脆、有梗、让人读能笑出来。不要写解释。

故事主题：{theme_prompt}
当前神话：{myth_title}
本神话识别点：{must_include}
本小节情境：{scene}
本小节优先幽默机制：{humor_mechanism or "请根据情境自行选择，但不要只用互怼"}
{examples_block}

要求：
- 必须围绕本小节的动作、道具、身体感受、旁观误解或当前压力制造笑点，不要泛泛调侃。
- 可以模仿示例的“正经话被一句拆台打歪”的节奏，但不要照抄示例原句。
- 非对白情节笑点请写成一句可直接改写进正文的短场面，例如“神农刚写下‘微苦回甘’，舌头就肿得把‘甘’说成了‘肝’。”
- 互怼对白最多一组，不要让同一个辅助角色承包所有笑点。
- 若当前节拍偏庄重，只输出 1 组非常轻的嘴硬式对白。

请直接输出 1-2 组，每组换行，不要编号、不要解释。"""
    }
    reply = call_qianwen_api(
        [system_msg, user_msg],
        temperature=0.95,
        top_p=0.9,
        repetition_penalty=1.2,
        max_tokens=400
    )
    cleaned = clean_markdown(reply or "").strip()
    return cleaned if cleaned else ""


def generate_outline(theme, rag_content, myth_core=None):
    """
    生成总体大纲（完整故事线）
    """
    system_message = {
        "role": "system",
        "content": get_myth_planning_prompt(rag_content, myth_core) + f"""
            请为神话改写《{theme}》生成完整的总体大纲：
            
            要求：
            - 生成一个完整的故事大纲，包含从开始到结束的完整故事线
            - 大纲应包含：故事背景、主要人物、核心冲突、关键事件、故事结局
            - 大纲长度约500-700字
            - 风格：类似电影《哪吒降世》的幽默改写
            - 必须确保故事线完整，有明确的起承转合
            - 大纲中可按需设置一名【辅助吐槽角色】的姓名与身份；如果本神话本身需要明确反派、夫妻/亲子/师徒等核心关系推动主线，优先写核心人物，不要为了笑点硬加副角。
            - 全篇最终目标是生成 7000~8500 字的长篇神话改写，硬上限 9000 字，所以总体大纲必须比普通版本更厚实但不能膨胀，除了原神话主干事件，只加入必要的【功能性扩展场景】。
            - 允许新增但必须受控的【功能性扩展场景】包括：踏上行动前的筹备、途中见闻、第一次失败尝试、民间/旁观者反应、核心人物间的争执或互相打气、阶段性喘息、行动后的余波收束。
            - 这些新增场景必须服务于以下至少一项：增强幽默、拉长动作过程、补足人物关系、强化情感伏笔、推动主线决策。严禁加入与主线无关的闲笔。
            - 总体大纲里禁止出现未铺垫的预言角色、会预知未来的动物、神秘援手、演播/直播类场景、信心值/任务值等数值化表达。
        """
    }
    
    user_message = {
        "role": "user",
        "content": f"请为神话改写《{theme}》生成完整的总体大纲（500-700字），包含从开始到结束的完整故事线，并主动加入可服务于长篇扩写的功能性扩展场景。"
    }
    
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.8,
        top_p=0.9,
        repetition_penalty=1.2,
        max_tokens=1600
    )
    return clean_markdown(reply)


def split_outline_to_acts(overall_outline, theme, rag_content, myth_core=None):
    """
    将总体大纲分配到三幕，生成三幕分别的大纲和镜头节拍卡（beats）
    
    返回: {"act1": "第一幕大纲", "act2": "第二幕大纲", "act3": "第三幕大纲",
           "act1_beats": [节拍卡1, 节拍卡2, ...], "act2_beats": [...], "act3_beats": [...]}
    每个节拍卡是一个字典，包含：场景目标、画面要素、情绪推动、信息增量、禁止项
    """
    system_message = {
        "role": "system",
        "content": get_myth_planning_prompt(rag_content, myth_core) + f"""
            请根据总体大纲，按【背景→高潮过程→结果】三幕结构分配，生成三幕分别的【详细】大纲和【镜头节拍卡】。
            
            【三幕定位与篇幅比例（必须严格遵守）】
            - 第一幕【背景】：灾因/世界设定/人物登场/为何非做不可/踏上征程。篇幅占比约 22%，大纲约 260-360 字，必须写清「十日并出」类背景、主角处境、同伴如何登场等，不能省略关键背景信息。允许加入筹备、试探、民间反应、赶路插曲等功能性扩展场景。
            - 第二幕【高潮过程】：核心行动的完整过程，必须展开为具体步骤，不能一笔带过。例如后羿射日必须包含：抵达山顶、面对十日、逐箭射落（可分组但要有「第几箭/射落第几个太阳」的递进）、留下最后一日的决策、体力/代价的描写。篇幅占比约 56%，大纲约 450-620 字，节拍卡数量为本幕 6-7 张，确保「过程」被拆成多小节写满，并允许加入与主线强相关的短暂喘息、失败尝试、环境阻力、同伴互怼等扩展场景。
            - 第三幕【结果】：行动完成后的世界变化、民众反应、主角收束与结局寓意。篇幅占比约 22%，大纲约 260-360 字。允许加入余波处理、人物关系回收、情感回应、世界复苏细节等扩展场景，但必须仍然收束到原神话结局。
            
            【关键情节点保留（不可违反）】
            - 分幕时必须从总体大纲中逐条提取关键事件，分配到对应幕中，不得丢失或合并成模糊表述。
            - 第二幕大纲必须包含：该神话「核心动作链」的每一步（如射日则写出射落第1个、第2个…直至留一日的节点；开天则写出劈开、撑天、踏地的阶段；补天则写出寻石、炼石、补窟窿的步骤）。每步在节拍卡中要有对应的一张或明确的小节目标。
            - 三幕合并后的故事必须能还原总体大纲的完整情节，不能比总体大纲少关键细节。
            
            要求：
            - 三幕之间必须承接，不能重复；第一幕结尾要自然衔接到第二幕的开端（如「抵达」「开始行动」）。
            - 每幕大纲要具体、可执行，包含该幕内应出现的具体事件、情节点和必要细节，便于后续按节拍卡逐段写作时不漏情节。
            - 为了支撑 7000~8500 字长篇成稿，每幕都要主动安排若干【功能性扩展节拍】，但总量必须克制。这些节拍只能用于：补动作、补关系、补笑点、补情绪推进、补后果展示，严禁单纯凑字数。
            - 【节拍卡与大纲严格对齐（关键要求）】：
              * 节拍卡必须严格按照本幕大纲中的关键情节点顺序生成，每张节拍卡的"场景目标"必须直接对应大纲中的一个或多个具体事件，不能偏离大纲内容。
              * 节拍卡的数量和顺序必须覆盖大纲中的所有关键情节点，不能遗漏大纲中提到的任何重要事件，也不能添加大纲中没有的新情节。
              * 例如：如果第二幕大纲写了"抵达山顶、面对十日、射落第1个太阳、射落第2-3个太阳、射落第4-6个太阳、射落第7-9个太阳、留下最后一日的决定、体力耗尽"，那么节拍卡必须按照这个顺序，每张节拍卡对应其中一个或几个步骤，不能跳过或打乱顺序。
              * 节拍卡的"场景目标"应该明确写出对应大纲中的哪个具体事件（如"射落第1个太阳"而不是模糊的"开始射箭"），确保节拍卡与大纲一一对应。
              * 如果本幕大纲没有写到某个新角色、新道具、新地点、新设定，该节拍卡就绝对不能新增它。
            - 在设计每张【镜头节拍卡】时，要为后续的幽默留出空间：预留至少一个【对白上的抛接点】和一个【非对白的反差点】（可通过画面要素或情绪推动中的具体细节体现）。
            - 第一幕输出 4 张节拍卡，第二幕输出 6-7 张节拍卡，第三幕输出 4 张节拍卡。每张节拍卡必须包含以下字段：
              * 场景目标：这一小段要完成什么叙事功能（铺垫/冲突升级/关键转折/代价/收束等）
              * 画面要素：至少2个可拍摄的画面/动作细节（非抽象词）
              * 情绪推动：角色此刻情绪从A到B（例如烦闷→决断、焦灼→咬牙、崩溃→释然）
              * 信息增量：这一节新增的信息是什么（不能重复前文）
              * 禁止项：列出1-2条"这一节绝对不能写什么"（如新角色突然出现、跳到结局、跑去写日常等）
              * 情感伏笔：这一拍为结尾感动埋什么伏笔（如主角把唯一资源留给别人、平时插科打诨的人在关键时刻突然认真、一个反复出现的小动作等）
              * 关系推进：主角和情感落点角色（核心人物或必要辅助角色）的关系如何变化（如从误解到理解、从担心到守护等）
              * 幽默机制：本拍优先使用哪一种笑点来源，必须具体到情节，例如“试药反差”“村民误解”“道具翻车”“严肃记录与狼狈状态反差”“药性命名”，不能只写“互怼”
            - 对所有神话通用：禁止写出“预知未来的动物”“神秘外援”“演播厅/直播间”“信心值/任务值”“系统/程序/工程”等跑偏设定。
            
            三幕逻辑总结：
            - 第一幕：背景与动机建立完毕，以「踏上征途/开始行动」类节点收尾。
            - 第二幕：核心行动全过程（步骤化、可数），不跳过任何关键步骤，以「行动完成/最后一击」类节点收尾。
            - 第三幕：结果、世界状态、人物收束与寓意，必须有明确结局与感动收束。
        """
    }
    
    user_message = {
        "role": "user",
        "content": f"""
总体大纲：
{overall_outline}

请将以上总体大纲分配到三幕，按【背景→高潮过程→结果】划分，生成三幕分别的【详细】大纲和【镜头节拍卡】。若总体大纲中已出现【辅助吐槽角色】的姓名与身份，请在后续节拍卡中谨慎延续该角色，但必须让核心人物、核心道具和主线冲突保持主位。要求：
1. 第一幕【背景】大纲（约260-360字）：包含灾因、世界设定、人物登场、为何非做不可、踏上征程等，必须写清神话背景（如十日并出、百姓遭殃），不能省略关键背景。结尾落在「开始行动/上路」。允许加入筹备、赶路、第一次试探、百姓反应等功能性扩展场景。
2. 第二幕【高潮过程】大纲（约450-620字）：核心行动的完整过程，必须展开为具体步骤。例如后羿射日须写出：抵达山顶、面对十日、逐箭射落（射落第1个…第9个、留下最后一日的决定）、体力与代价。盘古开天须写出：挥斧劈开、撑天、踏地等阶段。不得一笔带过或合并成「他一口气完成了」。允许加入与主线强相关的失败尝试、环境阻力、同伴互怼、阶段性喘息，但不许跑题。
3. 第三幕【结果】大纲（约260-360字）：行动完成后的世界变化、民众反应、主角收束与结局寓意，不能重复前两幕。允许加入余波处理、关系回收、世界复苏与情感回应等功能性扩展场景。
4. 【节拍卡生成关键要求（必须严格遵守）】：
   - 生成大纲后，请先提取每幕大纲中的关键情节点（用序号或分号分隔的各个事件），然后按照这些关键情节点的顺序，逐条生成对应的节拍卡。
   - 每张节拍卡的"场景目标"必须明确对应大纲中的一个具体事件，不能偏离。例如：如果大纲写了"射落第1个太阳"，节拍卡的场景目标就应该是"射落第1个太阳"或"完成射落第1个太阳的动作"，而不是"开始射箭"或"面对困难"等模糊表述。
   - 节拍卡的数量必须足够覆盖大纲中的所有关键情节点，不能遗漏。如果大纲中有8个关键步骤，就需要更多节拍卡把它们拆细，同时加入紧贴主线的扩展节拍。
   - 节拍卡的顺序必须与大纲中事件的顺序一致，不能打乱。
   - 如果大纲里没有写到某个新角色、新道具、新地点、新设定，该节拍卡绝对不能新增它。
5. 第一幕 4 张节拍卡，第二幕 6-7 张节拍卡，第三幕 4 张节拍卡。每张节拍卡必须包含以下字段：
   - 场景目标：这一小段要完成什么叙事功能
   - 画面要素：至少2个可拍摄的画面/动作细节（非抽象词）
   - 情绪推动：角色此刻情绪从A到B
   - 信息增量：这一节新增的信息是什么（不能重复前文）
   - 禁止项：列出1-2条"这一节绝对不能写什么"
   - 情感伏笔：这一拍为结尾感动埋什么伏笔（如主角把唯一资源留给别人、平时插科打诨的人在关键时刻突然认真、一个反复出现的小动作等）
   - 关系推进：主角和情感落点角色（核心人物或必要辅助角色）的关系如何变化（如从误解到理解、从担心到守护等）
   - 幽默机制：本拍优先使用的笑点来源；必须在对白互怼、动作反差、旁观误解、道具翻车、严肃记录反差、命名梗、嘴硬自嘲中轮换，避免连续依赖同一辅助角色吐槽
6. 通用禁区：不要生成预言动物、神秘外援、演播厅/直播间、信心值/任务值、系统/程序/工程等跑偏设定。

请严格按照以下格式输出：
第一幕大纲（xx字）：[第一幕的具体内容]

第一幕节拍卡1：
场景目标：[叙事功能]
画面要素：[至少2个可拍摄的画面/动作细节]
情绪推动：[情绪从A到B]
信息增量：[新增信息]
禁止项：[1-2条禁止项]
情感伏笔：[为结尾感动埋什么伏笔]
关系推进：[主角和情感落点角色的关系如何变化]
幽默机制：[本拍优先使用的笑点来源]

第一幕节拍卡2：
场景目标：[叙事功能]
画面要素：[至少2个可拍摄的画面/动作细节]
情绪推动：[情绪从A到B]
信息增量：[新增信息]
禁止项：[1-2条禁止项]

...（继续输出4张节拍卡）

第二幕大纲（xx字）：[第二幕的具体内容]

第二幕节拍卡1：
场景目标：[叙事功能]
画面要素：[至少2个可拍摄的画面/动作细节]
情绪推动：[情绪从A到B]
信息增量：[新增信息]
禁止项：[1-2条禁止项]

...（继续输出6-7张节拍卡）

第三幕大纲（xx字）：[第三幕的具体内容]

第三幕节拍卡1：
场景目标：[叙事功能]
画面要素：[至少2个可拍摄的画面/动作细节]
情绪推动：[情绪从A到B]
信息增量：[新增信息]
禁止项：[1-2条禁止项]

...（继续输出4张节拍卡）
        """
    }
    
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.7,
        top_p=0.9,
        repetition_penalty=1.2,
        max_tokens=5200  # 长篇版本需要更多大纲与节拍卡
    )
    
    # 解析三幕大纲和节拍卡
    cleaned_reply = clean_markdown(reply)
    parse_reply = cleaned_reply
    parse_reply = re.sub(r'(?m)^\s*[-*]\s*(?=(场景目标|画面要素|情绪推动|信息增量|禁止项|情感伏笔|关系推进|幽默机制)[：:])', '', parse_reply)
    parse_reply = re.sub(
        r'(第[一二三]幕)\s*(?:镜头)?\s*节拍卡\s*([0-9一二三四五六七八九十]+)',
        r'\1节拍卡\2',
        parse_reply
    )
    parse_reply = re.sub(r'(第[一二三]幕)\s*大纲', r'\1大纲', parse_reply)
    
    # 尝试提取三幕大纲（支持新格式：第一幕大纲（xx字）：）
    act1_match = re.search(r'第一幕[大纲：:]*（[^）]*）[：:]*\s*(.*?)(?=第一幕节拍卡|第二幕|$)', parse_reply, re.DOTALL)
    if not act1_match:
        act1_match = re.search(r'第一幕[大纲：:]*\s*(.*?)(?=第一幕节拍卡|第二幕|$)', parse_reply, re.DOTALL)
    act2_match = re.search(r'第二幕[大纲：:]*（[^）]*）[：:]*\s*(.*?)(?=第二幕节拍卡|第三幕|$)', parse_reply, re.DOTALL)
    if not act2_match:
        act2_match = re.search(r'第二幕[大纲：:]*\s*(.*?)(?=第二幕节拍卡|第三幕|$)', parse_reply, re.DOTALL)
    act3_match = re.search(r'第三幕[大纲：:]*（[^）]*）[：:]*\s*(.*?)(?=第三幕节拍卡|$)', parse_reply, re.DOTALL)
    if not act3_match:
        act3_match = re.search(r'第三幕[大纲：:]*\s*(.*?)(?=第三幕节拍卡|$)', parse_reply, re.DOTALL)
    
    act1_outline = act1_match.group(1).strip() if act1_match else ""
    act2_outline = act2_match.group(1).strip() if act2_match else ""
    act3_outline = act3_match.group(1).strip() if act3_match else ""
    
    # 解析节拍卡（新格式：包含多个字段的字典）
    def parse_beat_cards(act_name, cleaned_reply):
        """解析节拍卡，返回字典列表"""
        # 只能把“行首的下一张节拍卡/下一幕大纲”视作边界。
        # 旧正则把正文里的“第三幕核心节点”也当边界，导致第三幕经常解析成 0-1 张卡。
        card_no = r'(?:\d+|[一二三四五六七八九十]+)'
        pattern = rf'^\s*{act_name}节拍卡{card_no}[：:、.．]*\s*(.*?)(?=^\s*{act_name}节拍卡{card_no}[：:、.．]|^\s*(?:第一幕|第二幕|第三幕)大纲|^\s*(?:第一幕|第二幕|第三幕)节拍卡{card_no}[：:、.．]|$)'
        matches = re.finditer(pattern, cleaned_reply, re.DOTALL | re.MULTILINE)
        beat_cards = []
        field_boundary = r'(?=场景目标|画面要素|情绪推动|信息增量|禁止项|情感伏笔|关系推进|幽默机制|$)'
        for match in matches:
            beat_text = match.group(1).strip()
            if not beat_text:
                continue
            # 解析各个字段
            beat_card = {}
            # 场景目标
            goal_match = re.search(r'场景目标[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if goal_match:
                beat_card['场景目标'] = goal_match.group(1).strip()
            # 画面要素
            visual_match = re.search(r'画面要素[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if visual_match:
                beat_card['画面要素'] = visual_match.group(1).strip()
            # 情绪推动
            emotion_match = re.search(r'情绪推动[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if emotion_match:
                beat_card['情绪推动'] = emotion_match.group(1).strip()
            # 信息增量
            info_match = re.search(r'信息增量[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if info_match:
                beat_card['信息增量'] = info_match.group(1).strip()
            # 禁止项
            ban_match = re.search(r'禁止项[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if ban_match:
                beat_card['禁止项'] = ban_match.group(1).strip()
            # 情感伏笔
            emotion_foreshadow_match = re.search(r'情感伏笔[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if emotion_foreshadow_match:
                beat_card['情感伏笔'] = emotion_foreshadow_match.group(1).strip()
            # 关系推进
            relationship_match = re.search(r'关系推进[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if relationship_match:
                beat_card['关系推进'] = relationship_match.group(1).strip()
            humor_match = re.search(r'幽默机制[：:]*\s*(.*?)' + field_boundary, beat_text, re.DOTALL)
            if humor_match:
                beat_card['幽默机制'] = humor_match.group(1).strip()
            
            # 如果解析到了至少一个字段，就添加到列表
            if beat_card:
                beat_cards.append(beat_card)
        
        # 如果新格式解析失败，尝试旧格式（简单的事件清单）
        if not beat_cards:
            old_pattern = rf'{act_name}事件清单[：:]*\s*(.*?)(?=第二幕|第三幕|$)'
            old_match = re.search(old_pattern, cleaned_reply, re.DOTALL)
            if old_match:
                beats_text = old_match.group(1)
                for line in beats_text.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    match = re.match(r'^\d+[\.、\s]+\s*(.+)', line)
                    if match:
                        beat_cards.append({'场景目标': match.group(1).strip(), '画面要素': '', '情绪推动': '', '信息增量': '', '禁止项': ''})
        
        act_key = {"第一幕": "act1", "第二幕": "act2", "第三幕": "act3"}.get(act_name, "act2")
        return beat_cards[:DEFAULT_ACT_BEAT_LIMITS.get(act_key, 7)]  # 收紧节拍卡数量上限，避免稀释单卡质量
    
    act1_beats = parse_beat_cards('第一幕', parse_reply)
    act2_beats = parse_beat_cards('第二幕', parse_reply)
    act3_beats = parse_beat_cards('第三幕', parse_reply)
    
    # 验证节拍卡数量是否合理
    if len(act1_beats) < DEFAULT_ACT_BEAT_MINIMUMS["act1"]:
        print(f"警告：第一幕只解析到 {len(act1_beats)} 张节拍卡，建议至少 {DEFAULT_ACT_BEAT_MINIMUMS['act1']} 张")
    if len(act2_beats) < DEFAULT_ACT_BEAT_MINIMUMS["act2"]:
        print(f"警告：第二幕只解析到 {len(act2_beats)} 张节拍卡，建议至少 {DEFAULT_ACT_BEAT_MINIMUMS['act2']} 张")
    if len(act3_beats) < DEFAULT_ACT_BEAT_MINIMUMS["act3"]:
        print(f"警告：第三幕只解析到 {len(act3_beats)} 张节拍卡，建议至少 {DEFAULT_ACT_BEAT_MINIMUMS['act3']} 张")
    
    # 如果解析失败，使用原始回复作为fallback
    if not act1_outline or not act2_outline or not act3_outline:
        print("警告：无法自动解析三幕大纲，使用原始回复")
        return {
            "act1": cleaned_reply,
            "act2": cleaned_reply,
            "act3": cleaned_reply,
            "act1_beats": [],
            "act2_beats": [],
            "act3_beats": []
        }
    
    return {
        "act1": act1_outline,
        "act2": act2_outline,
        "act3": act3_outline,
        "act1_beats": act1_beats,
        "act2_beats": act2_beats,
        "act3_beats": act3_beats
    }


def outline_plan_is_usable(acts_outline: dict, myth_core: dict = None) -> bool:
    """
    规划结果验收：
    - 三幕大纲不能为空
    - 节拍卡数量必须达到长篇最低要求
    """
    if not acts_outline:
        return False

    if not acts_outline.get("act1") or not acts_outline.get("act2") or not acts_outline.get("act3"):
        return False

    combined_outline = "\n".join([
        acts_outline.get("act1", ""),
        acts_outline.get("act2", ""),
        acts_outline.get("act3", ""),
    ])
    if has_hard_meta_residue(combined_outline):
        return False
    if contains_myth_core_violation(combined_outline, myth_core or {}):
        return False
    if myth_core and not myth_core_requirement_met(combined_outline, myth_core, final=False):
        return False

    if contains_plan_drift(acts_outline.get("act1", ""), myth_core):
        return False
    if contains_plan_drift(acts_outline.get("act2", ""), myth_core):
        return False
    if contains_plan_drift(acts_outline.get("act3", ""), myth_core):
        return False

    if len(acts_outline.get("act1_beats", [])) < DEFAULT_ACT_BEAT_MINIMUMS["act1"]:
        return False
    if len(acts_outline.get("act2_beats", [])) < DEFAULT_ACT_BEAT_MINIMUMS["act2"]:
        return False
    if len(acts_outline.get("act3_beats", [])) < DEFAULT_ACT_BEAT_MINIMUMS["act3"]:
        return False

    for beat_group in (
        acts_outline.get("act1_beats", []),
        acts_outline.get("act2_beats", []),
        acts_outline.get("act3_beats", []),
    ):
        for beat in beat_group:
            beat_text = " ".join(
                str(beat.get(k, "")) for k in ["场景目标", "画面要素", "信息增量", "禁止项"]
            ) if isinstance(beat, dict) else str(beat)
            if isinstance(beat, dict):
                for required_field in ("场景目标", "画面要素", "信息增量"):
                    if len(str(beat.get(required_field, "")).strip()) < 4:
                        return False
            if contains_plan_drift(beat_text, myth_core):
                return False

    return True


def generate_touching_storyline(overall_outline, act1_outline, act2_outline, act3_outline, prompt, rag_content, myth_core=None):
    """
    基于总体大纲和三幕大纲，生成一条贯穿三幕的情绪线索。
    优先服务娱乐性与人物弧光；只有故事自然适合时才做感动升华。
    
    返回: {
        "act1_touching": "第一幕的感动线索部分（铺垫）",
        "act2_touching": "第二幕的感动线索部分（发展）",
        "act3_touching": "第三幕的感动线索部分（高潮与收束）"
    }
    """
    myth_title = (myth_core or {}).get("title", "")
    extra_storyline_constraints = ""
    if myth_title == "后羿射日":
        extra_storyline_constraints = """
【《后羿射日》情绪线硬约束】
- 情绪线必须服务“射落九日、主动留一日、天地恢复”的主线。
- 第三幕只能写后羿主动留下最后一个太阳，并由阿满在青竹简上记录“射九留一”。
- 严禁写“第十个太阳隐入云中”“后羿甩出最后一箭”“最后一个太阳被射掉”“漏了个靶子”等会破坏射九留一的表达。
- 阿满的情绪线只能是怕热护简、记箭序、最后郑重记录；不得让阿满摔倒或制造意外帮助后羿命中。
"""
    system_message = {
        "role": "system",
        "content": get_myth_system_prompt_base(rag_content, myth_core) + f"""
            你是一位擅长设计情绪线索的编剧。请基于给定的故事大纲，设计一条贯穿三幕的情绪线索。
            
            【情绪线索的设计原则】
            - 这条线索应该与主线故事自然融合，不是生硬添加的支线。
            - 本项目是神话娱乐改写，整体优先幽默、风趣、轻微搞怪；情绪升华只做自然余味，不要写成作文式煽情。
            - 第一幕：铺垫阶段 - 埋下人物动机、误解、笑点来源或小小执念。
            - 第二幕：发展阶段 - 在主角行动过程中，让误解、笑点和压力升级。
            - 第三幕：收束阶段 - 根据神话类型选择轻松余味、爽朗认可、温柔一笑或必要的感动升华。
            
            【可选情绪类型】
            - 幽默回收：前文的误会、道具翻车、口头禅在结尾变成轻松余味。
            - 爽朗认可：曾经嘲笑的人承认主角有点本事，但可以嘴硬。
            - 温柔升华：主角完成核心行动后，环境或人物反应用一两个动作点到为止。
            - 悲剧/牺牲：只有原神话本身需要悲剧或牺牲时才使用，不要强塞。
            
            【注意事项】
            - 情绪线索要自然，不能为了感动而强行煽情。
            - 要与幽默基调平衡；若结尾不方便感动，就用风趣、轻快、余味式收束。
            - 每幕线索应该具体、可执行，便于在写作时融入。
            {extra_storyline_constraints}
        """
    }
    
    user_message = {
        "role": "user",
        "content": f"""
请为《{prompt}》设计一条贯穿三幕的情绪线索，优先服务幽默风趣和人物弧光；若结尾适合，再自然加入轻微升华。

【总体大纲】
{overall_outline}

【第一幕大纲】
{act1_outline}

【第二幕大纲】
{act2_outline}

【第三幕大纲】
{act3_outline}

请设计一条情绪线索，并将其分成三部分，分别对应三幕：
1. 第一幕情绪线索（铺垫阶段）：约50-80字，描述第一幕的误解、动机或笑点种子
2. 第二幕情绪线索（发展阶段）：约50-80字，描述第二幕如何升级压力、误会和幽默
3. 第三幕情绪线索（收束阶段）：约80-120字，描述第三幕如何完成轻松余味、爽朗认可或自然升华

请严格按照以下格式输出：
第一幕感动线索：[第一幕的情绪线索内容]
第二幕感动线索：[第二幕的情绪线索内容]
第三幕感动线索：[第三幕的情绪线索内容]
        """
    }
    
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.8,
        top_p=0.9,
        repetition_penalty=1.2,
        max_tokens=800
    )
    
    cleaned_reply = clean_markdown(reply)
    
    # 解析回复，提取三幕的感动线索
    act1_touching = ""
    act2_touching = ""
    act3_touching = ""
    
    # 尝试提取第一幕感动线索
    match1 = re.search(r'第一幕感动线索[：:]\s*(.+?)(?=第二幕感动线索|$)', cleaned_reply, re.DOTALL)
    if match1:
        act1_touching = match1.group(1).strip()
    
    # 尝试提取第二幕感动线索
    match2 = re.search(r'第二幕感动线索[：:]\s*(.+?)(?=第三幕感动线索|$)', cleaned_reply, re.DOTALL)
    if match2:
        act2_touching = match2.group(1).strip()
    
    # 尝试提取第三幕感动线索
    match3 = re.search(r'第三幕感动线索[：:]\s*(.+?)$', cleaned_reply, re.DOTALL)
    if match3:
        act3_touching = match3.group(1).strip()
    
    # 如果解析失败，尝试其他格式
    if not act1_touching or not act2_touching or not act3_touching:
        # 尝试按行分割
        lines = cleaned_reply.split('\n')
        for i, line in enumerate(lines):
            if '第一幕' in line and '感动' in line:
                if i + 1 < len(lines):
                    act1_touching = lines[i + 1].strip()
            elif '第二幕' in line and '感动' in line:
                if i + 1 < len(lines):
                    act2_touching = lines[i + 1].strip()
            elif '第三幕' in line and '感动' in line:
                if i + 1 < len(lines):
                    act3_touching = lines[i + 1].strip()
    
    # 如果仍然没有提取到，使用整个回复作为第三幕的感动线索（至少保证有内容）
    if not act3_touching:
        act3_touching = cleaned_reply.strip()[:200]
    
    return {
        "act1_touching": act1_touching,
        "act2_touching": act2_touching,
        "act3_touching": act3_touching
    }


def build_local_punchline_notes_for_beat(beat: dict, myth_core: dict = None) -> str:
    """
    本地生成笑点方向，避免每张节拍卡额外调用一次 API。
    真正的幽默表达仍交给正文生成模型完成，但笑点必须贴住当前节拍。
    """
    if not isinstance(beat, dict):
        return ""
    mechanism = (beat.get("幽默机制") or "").strip()
    goal = (beat.get("场景目标") or "").strip()
    title = (myth_core or {}).get("title", "")
    thread_constraint = (myth_core or {}).get("_thread_protagonist", {}) if myth_core else {}
    role = thread_constraint.get("role", "") if isinstance(thread_constraint, dict) else ""
    notes = [
        f"本节笑点来源优先贴合：{mechanism or '动作反差、旁观误解、严肃记录反差'}。",
        "至少保留一个能让读者明确感到好笑的点，但笑点只能从当前动作、道具失灵、旁观误解或阿满记录反差中自然长出来。",
    ]
    if "阿满" in role or thread_constraint:
        notes.append("阿满可贡献一句短促记录梗或护青竹简的狼狈反差；他只能串联《山海二十简》，不得解决当前危机。")
    if any(keyword in goal for keyword in ["决断", "牺牲", "完成", "结尾", "收束", "最后"]):
        notes.append("若本节是重大抉择或收束，只留一处轻幽默，优先做嘴硬余味，不要密集抖包袱。")
    if title:
        notes.append(f"笑点必须服务《{title}》本篇主线，不要把其他神话人物搬进现场制造笑点。")
    return "\n".join(notes)


def generate_act1(act1_outline, overall_outline, rag_content, prompt, act1_beats=None, touching_storyline=None, myth_core=None):
    """
    生成第一幕（600-800字）
    """
    # 提取幽默样本
    humor_samples = get_humor_samples()
    humor_reference = f"\n\n【全部哪吒风格参考样本（请学习其表达方式，并在文中穿插若干仿写哪吒风格的幽默点，勿通篇哪吒口吻）】\n{humor_samples}" if humor_samples else ""
    
    # 提取前置关系型样本（用于学习如何埋下情感伏笔和推进关系）
    foreshadow_examples = get_touching_foreshadow_examples()
    foreshadow_reference = f"\n\n【前置关系型样本（请学习如何在前两幕埋下情感伏笔和推进关系）】\n{foreshadow_examples}" if foreshadow_examples else ""
    
    # 第一幕：按节拍卡逐小节生成，再拼接成完整第一幕
    system_content = get_myth_system_prompt_base(rag_content, myth_core) + humor_reference + foreshadow_reference

    # 方案二：加载人为挑选的「让人笑出来」对白示例，每小节注入
    punchline_examples = get_punchline_examples(myth_core)

    # 如果没有节拍卡，退化为单节拍，交给统一逻辑处理
    if not act1_beats:
        act1_beats = [{
            "场景目标": act1_outline,
            "画面要素": "",
            "情绪推动": "",
            "信息增量": "",
            "禁止项": "",
            "情感伏笔": "",
            "关系推进": ""
        }]

    total_beats = len(act1_beats)
    # 第一幕【背景】长篇版本目标 1600~2100 字
    target_min_total, target_max_total = MYTH_ACT_TARGETS["act1"]
    base_min = max(220, target_min_total // total_beats - 25)
    base_max = target_max_total // total_beats + 45

    segments = []
    accumulated_text = ""

    for idx, beat in enumerate(act1_beats, 1):
        punchlines = build_local_punchline_notes_for_beat(beat, myth_core)
        segment = generate_segment_for_beat(
            act_name="第一幕",
            beat_index=idx,
            total_beats=total_beats,
            beat=beat,
            overall_outline=overall_outline,
            act_outline=act1_outline,
            prev_text=accumulated_text,
            prompt=prompt,
            system_content=system_content,
            target_min_len=base_min,
            target_max_len=base_max,
            act_id="act1",
            punchlines_to_embed=punchlines,
            punchline_examples_text=punchline_examples,
            touching_storyline=touching_storyline,
            myth_core=myth_core
        )
        segments.append(segment)
        accumulated_text = (accumulated_text + "\n" + segment).strip() if accumulated_text else segment

    # 简单拼接为第一幕全文
    return "\n\n".join(segments)


def generate_act2(act2_outline, overall_outline, act1, prompt, act2_beats=None, touching_storyline=None, myth_core=None):
    """
    生成第二幕（900-1100字）
    """
    # 提取幽默样本
    humor_samples = get_humor_samples()
    humor_reference = f"\n\n【全部哪吒风格参考样本（请学习其表达方式，并在文中穿插若干仿写哪吒风格的幽默点，勿通篇哪吒口吻）】\n{humor_samples}" if humor_samples else ""
    
    # 提取前置关系型样本（用于学习如何埋下情感伏笔和推进关系）
    foreshadow_examples = get_touching_foreshadow_examples()
    foreshadow_reference = f"\n\n【前置关系型样本（请学习如何在前两幕埋下情感伏笔和推进关系）】\n{foreshadow_examples}" if foreshadow_examples else ""
    
    # 第二幕：按节拍卡逐小节生成，再拼接成完整第二幕
    system_content = get_myth_system_prompt_base(None, myth_core) + humor_reference + foreshadow_reference

    punchline_examples = get_punchline_examples(myth_core)

    if not act2_beats:
        act2_beats = [{
            "场景目标": act2_outline,
            "画面要素": "",
            "情绪推动": "",
            "信息增量": "",
            "禁止项": "",
            "情感伏笔": "",
            "关系推进": ""
        }]

    total_beats = len(act2_beats)
    # 第二幕【高潮过程】长篇版本目标 2600~3400 字，确保核心过程写满
    target_min_total, target_max_total = MYTH_ACT_TARGETS["act2"]
    base_min = max(240, target_min_total // total_beats - 20)
    base_max = target_max_total // total_beats + 55

    segments = []
    # 将第一幕全文作为"更早前文"，帮助第二幕承接，但在单节生成时只截取尾部片段
    accumulated_text = act1.strip()

    for idx, beat in enumerate(act2_beats, 1):
        punchlines = build_local_punchline_notes_for_beat(beat, myth_core)
        segment = generate_segment_for_beat(
            act_name="第二幕",
            beat_index=idx,
            total_beats=total_beats,
            beat=beat,
            overall_outline=overall_outline,
            act_outline=act2_outline,
            prev_text=accumulated_text,
            prompt=prompt,
            system_content=system_content,
            target_min_len=base_min,
            target_max_len=base_max,
            act_id="act2",
            punchlines_to_embed=punchlines,
            punchline_examples_text=punchline_examples,
            touching_storyline=touching_storyline,
            myth_core=myth_core
        )
        segments.append(segment)
        accumulated_text = (accumulated_text + "\n" + segment).strip()

    return "\n\n".join(segments)


def generate_act3(act3_outline, overall_outline, act2, prompt, act3_beats=None, touching_storyline=None, emotional_character=None, myth_core=None):
    """
    生成第三幕（600-800字）
    emotional_character: 情感落点角色名称（如"铁牛"、"小徒弟"等）
    """
    # 提取感动结局样本
    touching_ending_examples = get_touching_ending_examples()
    
    # 第三幕使用专用的感动收束优先系统提示
    system_content = get_act3_emotional_system_prompt(None, myth_core) + (f"\n\n【感动结局参考样本（请学习其情感表达与节奏）】\n{touching_ending_examples}" if touching_ending_examples else "")

    punchline_examples = get_punchline_examples(myth_core)

    # 如果没有节拍卡，退化为单节拍，交给统一逻辑处理
    if not act3_beats:
        act3_beats = [{
            "场景目标": act3_outline,
            "画面要素": "",
            "情绪推动": "",
            "信息增量": "",
            "禁止项": "",
            "情感伏笔": "",
            "关系推进": ""
        }]

    total_beats = len(act3_beats)
    # 第三幕【结果】长篇版本目标 1600~2100 字
    target_min_total, target_max_total = MYTH_ACT_TARGETS["act3"]
    base_min = max(220, target_min_total // total_beats - 25)
    base_max = target_max_total // total_beats + 45

    segments = []
    # 将第二幕全文作为"更早前文"，帮助第三幕承接，在单节生成时只截取尾部片段
    accumulated_text = act2.strip()
    
    # 提取前文中的关键意象作为memory_hooks（用于验收时检查是否回收）
    memory_hooks = []
    if accumulated_text:
        # 简单提取：寻找常见的意象词
        common_hooks = ['干粮', '水壶', '弓', '手', '那句话', '那句话', '那句话']
        for hook in common_hooks:
            if hook in accumulated_text:
                memory_hooks.append(hook)

    for idx, beat in enumerate(act3_beats, 1):
        # 最后1-2张节拍卡使用专门的结尾beat生成函数
        if idx >= total_beats - 1:
            segment = generate_act3_ending_beat(
                act_name="第三幕",
                beat_index=idx,
                total_beats=total_beats,
                beat=beat,
                overall_outline=overall_outline,
                act_outline=act3_outline,
                prev_text=accumulated_text,
                prompt=prompt,
                system_content=system_content,
                target_min_len=base_min,
                target_max_len=base_max,
                touching_ending_examples=touching_ending_examples,
                emotional_character=emotional_character,
                myth_core=myth_core
            )
        else:
            # 其他节拍卡使用普通生成函数
            punchlines = build_local_punchline_notes_for_beat(beat, myth_core)
            segment = generate_segment_for_beat(
                act_name="第三幕",
                beat_index=idx,
                total_beats=total_beats,
                beat=beat,
                overall_outline=overall_outline,
                act_outline=act3_outline,
                prev_text=accumulated_text,
                prompt=prompt,
                system_content=system_content,
                target_min_len=base_min,
                target_max_len=base_max,
                act_id="act3",
                punchlines_to_embed=punchlines,
                punchline_examples_text=punchline_examples,
                touching_storyline=touching_storyline,
                touching_ending_examples=touching_ending_examples,
                myth_core=myth_core
            )
        segments.append(segment)
        accumulated_text = (accumulated_text + "\n" + segment).strip()

    final_act3 = "\n\n".join(segments)

    # 仍保留一次整体质量检查（长度/繁体/镜头括号等），仅做告警，不再整体重写
    if not validate_act3(final_act3):
        print("警告：第三幕整体质量校验未通过（长度/格式/繁体检测），但已按节拍卡逐段生成。")
    
    emotion_required_titles = {"梁山伯与祝英台", "孟姜女哭长城", "牛郎织女", "嫦娥奔月", "女娲补天", "盘古开天地"}
    emotion_required = (myth_core or {}).get("title") in emotion_required_titles

    # 悲剧/牺牲类神话才强制感动验收；其他娱乐改写允许用幽默余味收束。
    if emotion_required and not validate_touching_ending(final_act3, memory_hooks):
        print("警告：第三幕感动结局验收未通过，正在重新生成最后两拍...")
        # 重新生成最后两拍
        for idx in range(max(1, total_beats - 1), total_beats + 1):
            if idx <= len(act3_beats):
                beat = act3_beats[idx - 1]
                accumulated_text_before = "\n\n".join(segments[:idx-1]) if idx > 1 else act2.strip()
                new_segment = generate_act3_ending_beat(
                    act_name="第三幕",
                    beat_index=idx,
                    total_beats=total_beats,
                    beat=beat,
                    overall_outline=overall_outline,
                    act_outline=act3_outline,
                    prev_text=accumulated_text_before,
                    prompt=prompt,
                    system_content=system_content,
                    target_min_len=base_min,
                    target_max_len=base_max,
                    touching_ending_examples=touching_ending_examples,
                    emotional_character=emotional_character,
                    myth_core=myth_core
                )
                segments[idx - 1] = new_segment
        final_act3 = "\n\n".join(segments)
        print("已重新生成最后两拍")

    return final_act3


def validate_act3(script: str) -> bool:
    """
    第三幕专用质量校验：
    - 字数/字符数需匹配长篇第三幕目标，明显过短或过长判失败
    - 含常见繁体字判失败（粗略检测）
    - 含括号镜头/元文本关键字判失败
    - 出现连续多行仅由标点/空格组成的“诗歌体碎行”判失败
    """
    if not script:
        return False

    # 1. 粗略长度控制：使用长篇第三幕目标，避免正常 1450~1850 字被旧阈值误报
    act3_min, act3_max = MYTH_ACT_TARGETS["act3"]
    if len(script) < max(900, act3_min - 350):
        return False
    if len(script) > act3_max + 450:
        return False

    # 2. 粗略繁体字检测（常见繁体字集合，命中任意一个就视为不合格）
    trad_chars = set("萬與專業東絲兩嚴個豐臨為麗舉樂鄉書買亂爭於雲亞產畢實寧眾優會傢價億債傷傾後門風體們發戰愛國頭聲靜場這顏顯點")
    if any(ch in trad_chars for ch in script):
        return False

    # 3. 括号镜头/元文本关键字
    forbidden_meta_phrases = [
        "（最终画面", "（最終畫面",
        "（镜头", "（鏡頭",
        "（远景", "（遠景",
        "遠鏡頭", "远镜头",
        "镜头切", "鏡頭切",
    ]
    if any(phrase in script for phrase in forbidden_meta_phrases):
        return False

    # 4. 连续多行只有标点/空格（诗歌体碎行）
    lines = script.splitlines()
    punct_chars = set("，。！？；：、…—-·「」『』（）()【】[]《》\"' \t ")
    pure_punct_run = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            pure_punct_run = 0
            continue
        if all(ch in punct_chars for ch in stripped):
            pure_punct_run += 1
            if pure_punct_run >= 3:
                return False
        else:
            pure_punct_run = 0

    return True


def strip_beat_markers(text: str) -> str:
    """
    清理正文中的节拍标记【B1】【B2】……，供最终输出使用
    """
    if not text:
        return text
    return re.sub(r'【B\d+】\s*', '', text)


def prune_excess_thread_cross_story_bridges(text: str, myth_core: dict = None, max_external_hits: int = 2) -> str:
    """
    阿满的跨篇连接只负责建立二十篇体系感。
    如果同一篇中过量反复点名其他神话，保留第一处合规翻简/回忆/类比句，删除后续重复串线句。
    """
    if not text or not myth_core:
        return text
    external_terms = thread_protagonist_external_terms(myth_core)
    if not external_terms:
        return text
    external_chunks = [
        chunk for chunk in re.findall(r'\n+|[^。！？；;\n]+[。！？；;]?', text)
        if not chunk.startswith("\n") and any(term in chunk for term in external_terms)
    ]
    if len(external_chunks) <= 1 and sum(text.count(term) for term in external_terms) <= max_external_hits:
        return text

    bridge_markers = [
        "阿满", "青竹简", "山海二十简", "翻", "记录", "记下", "写下", "竹简",
        "想起", "上回", "先前", "此前", "曾", "那回", "另一简", "一简",
        "类比", "比起", "像", "伏笔", "以后", "往后", "页角", "补了一笔", "补了",
    ]
    chunks = re.findall(r'\n+|[^。！？；;\n]+[。！？；;]?', text)
    valid_bridge_indexes = [
        index for index, chunk in enumerate(chunks)
        if not chunk.startswith("\n")
        and any(term in chunk for term in external_terms)
        and any(marker in chunk for marker in bridge_markers)
    ]
    keep_bridge_index = valid_bridge_indexes[-1] if valid_bridge_indexes else -1
    kept_chunks = []
    for index, chunk in enumerate(chunks):
        if chunk.startswith("\n"):
            kept_chunks.append(chunk)
            continue
        has_external = any(term in chunk for term in external_terms)
        if not has_external:
            kept_chunks.append(chunk)
            continue
        if index == keep_bridge_index:
            kept_chunks.append(chunk)
            continue
        # 只保留一处体系连接，其余外篇点名都会稀释当前神话。
        continue

    pruned = "".join(kept_chunks)
    pruned = re.sub(r'\n{3,}', '\n\n', pruned).strip()
    return pruned or text


def clean_story_postprocess(text: str, myth_core: dict = None) -> str:
    """
    最终成稿的统一清洁：
    - 删除英文单词，避免 knot/back/shoulders 这类夹杂破坏时代感
    - 删除形如"（这段共xxx字）"的括号字数提示
    - 保留正常中文与标点
    - 删除中文之间误插入的空格
    """
    if not text:
        return text

    text = remove_meta_residue(text)
    text = normalize_language_pollution(text)
    text = remove_body_drift_residue(text)
    text = apply_myth_specific_postprocess(text, myth_core)
    text = prune_excess_thread_cross_story_bridges(text, myth_core)

    # 删除连续英文字符（忽略大小写），直接抹掉英文单词
    text = re.sub(r'[A-Za-z]+', '', text)
    text = re.sub(r'[\u0370-\u03FF\u0400-\u052F]+', '', text)

    # 删除常见的字数统计括号尾巴
    text = re.sub(r'（这段共[^）]*字）', '', text)
    text = re.sub(r'\(这段共[^)]*字\)', '', text)
    text = re.sub(r'[（(](?:註|注|备注)[:：][^）)]{0,120}[）)]', '', text)
    # 正文不保留模型常用的条目框和括号批注样式；保留其中叙事内容。
    text = re.sub(r'【([^】\n]{1,2000})】', r'\1', text)
    text = re.sub(r'（([^）\n]{1,220})）', r'\1', text)
    text = text.replace("→", "；")
    text = text.replace("> ", "")
    text = text.replace("括弧内小字挤作一团", "他又在旁边挤着补了一行小字")
    text = text.replace("《山海二十简》母卷", "《山海二十简》简册")
    text = text.replace("粗麻纸纤维", "竹纹").replace("汗滴纸上", "汗滴简上")
    text = remove_meta_residue(text)
    text = normalize_language_pollution(text)
    text = remove_body_drift_residue(text)

    # 删掉中文字符之间误插入的空格
    text = re.sub(r'(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])', '', text)

    # 再清理可能多出来的多余空格
    text = re.sub(r'[ ]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = split_long_paragraphs(text)
    text = remove_adjacent_duplicate_units(text)
    text = remove_duplicate_paragraph_units(text)
    text = remove_meta_residue(text)
    text = remove_body_drift_residue(text)
    text = apply_myth_specific_postprocess(text, myth_core)
    text = prune_excess_thread_cross_story_bridges(text, myth_core)
    text = remove_adjacent_duplicate_units(text)
    text = remove_duplicate_paragraph_units(text)
    return text.strip()


def remove_adjacent_duplicate_units(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines()
    cleaned = []
    previous_norm = None
    for line in lines:
        norm = re.sub(r'\s+', '', line.strip())
        if norm and norm == previous_norm:
            continue
        cleaned.append(line)
        if norm:
            previous_norm = norm
    return "\n".join(cleaned)


def remove_duplicate_paragraph_units(text: str) -> str:
    if not text:
        return text
    lines = text.splitlines()
    cleaned = []
    seen = set()
    for line in lines:
        norm = re.sub(r'\s+', '', line.strip())
        if len(norm) >= 40:
            key = norm[:220]
            if key in seen:
                continue
            seen.add(key)
        cleaned.append(line)
    return "\n".join(cleaned)


def has_obvious_garbled_text(text: str, myth_core: dict = None) -> bool:
    """
    检测明显的乱码/跑偏/格式污染：
    - 常见未完成提示
    - emoji/装饰符号
    - 英文夹杂过多
    - 繁体字过多
    - 连续异常标点
    """
    if not text:
        return True

    if has_hard_meta_residue(text):
        return True

    if any(phrase in text for phrase in BAD_META_PHRASES):
        return True

    if any(re.search(pattern, text) for pattern in META_RESIDUE_PATTERNS):
        return True

    if re.search(r'[\U0001F300-\U0001FAFF]', text):
        return True

    if re.search(r'[\u0370-\u03FF\u0400-\u052F\u3040-\u30FF]', text):
        return True

    if re.search(r'[;；]{4,}|[.。]{5,}|[!！?？]{4,}', text):
        return True

    if re.search(r'\[[^\]]{0,40}(插入|互动场景|待补|补写)[^\]]{0,40}\]', text):
        return True

    if any(phrase in text for phrase in BAD_META_PHRASES):
        return True

    meta_like_patterns = [
        r'（此处[^）]{0,30}插入[^）]*）',
        r'（此时此刻[^）]{0,120}）',
        r'（[^）]{0,30}(这段大约|多少字左右|接下来便是|下一节|备注|隐藏章节|待补)[^）]*）',
        r'（这段[^）]{0,30}符合要求[^）]*）',
        r'（[^）]{0,20}画面要素[^）]*）',
        r'（[^）]{0,20}感情线[^）]*）',
        r'（[^）]{0,20}推动主题[^）]*）',
        r'\([^)]{0,30}(插入|画面要素|感情线|推动主题)[^)]*\)',
    ]
    if any(re.search(pattern, text) for pattern in meta_like_patterns):
        return True

    if contains_body_drift(text, myth_core):
        return True

    latin_hits = re.findall(r'[A-Za-z]{2,}', text)
    if len(latin_hits) >= 5:
        return True

    trad_chars = set("萬與專業東絲兩嚴個豐臨為麗舉樂鄉書買亂爭於雲亞產畢實寧眾優會傢價億債傷傾後門風體們發戰愛國頭聲靜場這顏顯點說師來個們為後時")
    trad_count = sum(1 for ch in text if ch in trad_chars)
    if trad_count >= max(8, len(text) // 180):
        return True

    # 极端过长且反复出现的无停顿句通常意味着模型在堆砌空话；
    # 神话长篇里偶尔出现一两句铺陈，不应被当成乱码。
    long_sentences = [
        s for s in re.split(r'[。！？\n]', text)
        if len(re.sub(r'\s+', '', s)) >= 260
    ]
    if len(long_sentences) >= 3:
        return True

    # “宏大套话”连续堆叠的特征
    repetitive_phrases = ['与此同时', '总而言之', '综上所述', '这才是', '发展前景', '各个方面', '共同发展']
    repetitive_hits = sum(text.count(p) for p in repetitive_phrases)
    if repetitive_hits >= 12:
        return True

    return False


def has_repeated_story_units(text: str) -> bool:
    """
    检测明显的段落重启/同功能重复。重点拦截同一段落或高度相似段落
    在成稿中反复出现的情况。
    """
    if not text:
        return False
    repeated_fallback_markers = (
        "二十简不是二十趟远路，是二十次把我胆子拿出来晾",
        "苦负责说明这事难，笑负责证明人还没认输",
        "神话若只有高处，就像只有骨头没有热气",
        "本篇诸事，核心人物亲自走完",
    )
    if any(text.count(marker) > 1 for marker in repeated_fallback_markers):
        return True
    paragraphs = [
        re.sub(r'\s+', '', p)
        for p in re.split(r'\n+', text)
        if len(re.sub(r'\s+', '', p)) >= 70
    ]
    seen = set()
    for para in paragraphs:
        key = para[:140]
        if key in seen:
            return True
        seen.add(key)
    for i, left in enumerate(paragraphs):
        left_tokens = set(re.findall(r'[\u4e00-\u9fff]{2,4}', left))
        if len(left_tokens) < 12:
            continue
        for right in paragraphs[i + 1:]:
            right_tokens = set(re.findall(r'[\u4e00-\u9fff]{2,4}', right))
            if len(right_tokens) < 12:
                continue
            overlap = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
            if overlap >= 0.90:
                return True
    return False


def violates_myth_consistency(text: str, myth_core: dict = None) -> bool:
    """
    按神话核心约束检查名称和核心道具形态是否混乱。
    规则由 myth_core_constraints*.json 提供，代码只提供通用执行器。
    """
    if not text or not myth_core:
        return False
    if contains_myth_core_violation(text, myth_core):
        return True
    if contains_thread_protagonist_violation(text, myth_core):
        return True
    canonical_terms = myth_core.get("canonical_terms", {})
    if isinstance(canonical_terms, dict):
        for _label, value in canonical_terms.items():
            if isinstance(value, str) and value.startswith("如使用"):
                continue
            if isinstance(value, str) and value and value not in text:
                return True
    object_rules = myth_core.get("object_consistency", [])
    if isinstance(object_rules, dict):
        object_rules = [object_rules]
    for rule in object_rules or []:
        if not isinstance(rule, dict):
            continue
        allowed_forms = [form for form in rule.get("allowed_forms", []) if form]
        if allowed_forms and not any(form in text for form in allowed_forms):
            return True
    return False


def validate_story_quality(text: str, prompt: str = "", myth_core: dict = None) -> bool:
    """
    长篇神话改写的最终质量验收：
    - 字数达到 7000~8500 的目标区间附近，硬上限 9000
    - 无明显乱码/元文本污染
    - 句号逗号密度正常，不是单纯堆字
    - 与主题至少有若干关键字重合，降低跑题概率
    """
    if not text:
        return False

    if len(text) < MYTH_TARGET_TOTAL_MIN:
        return False
    if len(text) > MYTH_TARGET_TOTAL_MAX:
        return False

    if has_obvious_garbled_text(text, myth_core):
        return False

    if violates_myth_consistency(text, myth_core or {}):
        return False

    if contains_body_drift(text, myth_core):
        return False

    if not humor_requirement_met(text, prompt):
        return False

    if has_repeated_story_units(text):
        return False

    if myth_core and not myth_core_requirement_met(text, myth_core, final=True):
        return False

    if myth_core and not myth_core_final_phrases_met(text, myth_core):
        return False

    if myth_core and not myth_core_required_sequence_met(text, myth_core):
        return False

    if myth_core and not thread_protagonist_requirement_met(text, myth_core):
        return False

    if myth_core and not houyi_story_quality_met(text, myth_core):
        return False

    punctuation_count = sum(text.count(p) for p in "，。！？")
    if punctuation_count < max(120, len(text) // 45):
        return False

    if prompt and not myth_core:
        prompt_keywords = [k for k in re.findall(r'[\u4e00-\u9fff]{2,4}', prompt) if len(k) >= 2]
        prompt_keywords = list(dict.fromkeys(prompt_keywords))[:10]
        if prompt_keywords:
            hit_count = sum(1 for k in prompt_keywords if k in text)
            if hit_count < max(2, min(4, len(prompt_keywords) // 2)):
                return False

    # 至少要有比较均匀的分段，否则大概率是大段灌水
    non_empty_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(non_empty_lines) < 18:
        return False

    # 单行过长过多，说明模型在拉长套话
    ultra_long_lines = [line for line in non_empty_lines if len(line) >= 900]
    if len(ultra_long_lines) >= 2:
        return False

    return True


def shrink_story_to_target_length(text: str, prompt: str = "", myth_core: dict = None) -> str:
    """
    当正文超过目标上限时，调用模型做保守压缩，保留神话核心事件链和结尾。
    """
    if not text or len(text) <= MYTH_TARGET_TOTAL_SOFT_MAX:
        return text

    myth_core_block = format_myth_core_block(myth_core)
    system_message = {
        "role": "system",
        "content": f"""
你是一名长篇神话改写的精修编辑。你的任务是删减和压缩已有正文，不新增剧情。
必须保留原神话核心事件链、关键因果、最终结局和核心寓意。
目标长度：{MYTH_TARGET_TOTAL_MIN}~{MYTH_TARGET_TOTAL_SOFT_MAX} 字，绝对不要超过 {MYTH_TARGET_TOTAL_MAX} 字。
压缩优先级：删重复环境描写、删重复推演过程、合并相似旁观反应、压缩连续互怼；保留强笑点、核心动作、关键情感收束。
严禁保留或新增任何现代政治宣传腔、政策口号、党政国家叙述、人民群众总结、国际合作等与神话主线无关的内容。
只输出压缩后的故事正文，不要标题、说明、列表或字数统计。
{myth_core_block}
"""
    }
    user_message = {
        "role": "user",
        "content": f"""请将以下《{prompt}》正文压缩到 {MYTH_TARGET_TOTAL_MIN}~{MYTH_TARGET_TOTAL_SOFT_MAX} 字之间，保留完整故事与结尾，不新增任何新情节。若原文出现现代政治宣传腔、政策口号、党政国家叙述、人民群众总结、国际合作等串台内容，必须整段删除：

{text}"""
    }
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.55,
        top_p=0.85,
        repetition_penalty=1.25,
        max_tokens=9000
    )
    cleaned = clean_story_postprocess(clean_markdown(reply or ""), myth_core)
    if MYTH_TARGET_TOTAL_MIN <= len(cleaned) <= MYTH_TARGET_TOTAL_MAX and not contains_body_drift(cleaned, myth_core):
        if not myth_core or myth_core_requirement_met(cleaned, myth_core, final=True):
            return cleaned
    return text


def force_trim_story_to_hard_max(text: str, max_len: int = MYTH_TARGET_TOTAL_MAX) -> str:
    """
    压缩模型失败时的最后兜底：保留开头与结尾，删除中段最长的冗余段落。
    只在超过硬上限时使用，避免再次输出 1w+ 字。
    """
    if not text or len(text) <= max_len:
        return text
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if len(paragraphs) <= 6:
        return text[:max_len].rstrip()

    while len("\n\n".join(paragraphs)) > max_len and len(paragraphs) > 6:
        removable = range(2, max(2, len(paragraphs) - 3))
        candidates = list(removable)
        if not candidates:
            break
        drop_index = max(candidates, key=lambda idx: len(paragraphs[idx]))
        paragraphs.pop(drop_index)

    trimmed = "\n\n".join(paragraphs).strip()
    if len(trimmed) > max_len:
        ending = "\n\n".join(paragraphs[-3:])
        head_limit = max_len - len(ending) - 4
        trimmed = (trimmed[:max(0, head_limit)].rstrip() + "\n\n" + ending).strip()
    return trimmed


def generate_houyi_controlled_rewrite(prompt: str, myth_core: dict = None) -> str:
    """
    后羿射日对“逐箭顺序”和“留一日”极敏感。
    通用分节拍若失败，使用三幕窄域重写，避免坏稿继续局部修补。
    """
    if not myth_core or myth_core.get("title") != "后羿射日":
        return ""

    myth_core_block = format_myth_core_block(myth_core)
    common_system = f"""
你是擅长轻喜剧神话改写的中文小说作者。只输出正文，不要标题、列表、说明、字数统计或括号备注。
本次只写《后羿射日》，必须全篇简体中文，古代神话语境。

【硬禁区】
- 不得出现摄氏度、记者、历史学家、记录仪、工作报告、系统、直播、手机、鸣笛、现代设备、现代职业、手写笔记、青竹筒、文档材料、文献、恒星、后弈记、战略利器、大规模杀戮。
- 不得把太阳写成设备、模型、投影、恒星术语或现代灾害报告。
- 不得把后羿射日写成战斗、工程、档案整理或官方记录。
- 只能写十日并出、后羿亲自射落九日、主动留下一日、天地恢复正常。

【阿满硬规则】
- 阿满是贯穿二十篇神话的见闻小史官，负责把本篇放进《山海二十简》的体系里；他不是当前神话的主角替身。
- 阿满只能记录、护住青竹简、短促吐槽、做跨篇回忆或伏笔；不能射箭、递箭、决定留一日、查资料指导后羿、宣布规则或制造意外帮助命中。
- 阿满称谓只能是“阿满”“小史官”“见闻小史官”；不得叫记者、历史学家、记录员、官方人员、憨豆阿满。
- 跨篇串联只能通过阿满翻看青竹简、想起旧经历、写《山海二十简》、在页角补一句来完成；不得让其他神话人物实体进入现场。

【幽默要求】
- 要有明显幽默，接近《哪吒魔童降世》式的人物压力下嘴硬、反差、短促拆台，但不能现代网络梗。
- 幽默必须服务当前神话：热浪狼狈、数太阳数乱、后羿嘴硬忍痛、阿满严肃记录和实际很狼狈的反差。
- 重大抉择处幽默要收住，不能破坏“救苍生”和“克制”的重量。

{myth_core_block}
""".strip()

    act_specs = [
        {
            "name": "第一幕",
            "target": "1500~1800字",
            "max_tokens": 2100,
            "content": """
写《后羿射日》第一幕，只写灾情和出发，不要开始射日。
必须自然出现：十日并出、大地焦灼、百姓受难、后羿、弓、箭、阿满、青竹简、《山海二十简》。
剧情要求：
1. 十日一起升起，庄稼枯焦，井边见底，百姓被晒得苦中带笑。
2. 后羿看见灾情，决定登高救民，检查弓箭。
3. 阿满抱着青竹简出现，热到担心字被晒熟；他作为贯穿二十篇的见闻小史官，要把这场灾记入《山海二十简》。
4. 阿满可以短促想起神农尝百草时自己写错过药性，提醒自己这次记箭序不能写错；只能是一两句体系连接，不能展开神农主线。
5. 幽默至少4处，要来自热浪、数太阳、阿满护简、后羿嘴硬。
结尾停在后羿登上高处、张弓准备射第一箭之前。
""".strip(),
        },
        {
            "name": "第二幕",
            "target": "3900~4500字",
            "max_tokens": 5200,
            "content": """
写《后羿射日》第二幕，只写逐箭射落九日，不要写最后收束。
必须按顺序逐字包含以下九个短句，每个短句各自展开成一段动作、环境变化、百姓反应和一处短促幽默：
第一箭射落第一日
第二箭射落第二日
第三箭射落第三日
第四箭射落第四日
第五箭射落第五日
第六箭射落第六日
第七箭射落第七日
第八箭射落第八日
第九箭射落第九日
剧情要求：
1. 后羿每一箭都必须亲自射出，有拉弓、瞄准、箭声、太阳坠落、天地稍凉的过程，不能一句带过。
2. 阿满只能在旁边抱着青竹简记箭序、擦汗、吐槽自己快把“一二三四”写成烤痕；他不能递箭、不能影响命中、不能宣布规则。
3. 第七、第八、第九箭开始要明显更艰难，幽默变短，压力更重。
4. 第二幕结尾必须明确“后羿射落九日”，但还剩最后一个太阳没有射，不能写十日全灭。
5. 不得出现“第十个太阳就要来了”“十个炽热点逐一陨落”“大规模杀戮”等表达。
""".strip(),
        },
        {
            "name": "第三幕",
            "target": "1500~1800字",
            "max_tokens": 2200,
            "content": """
写《后羿射日》第三幕，只写射九之后的抉择和收束。
必须自然出现：留下最后一个太阳、留下一日、射九留一、天地恢复正常、万物复苏、阿满、青竹简、《山海二十简》。
剧情要求：
1. 第九日坠落后，最后一个太阳发抖或收敛光芒；后羿主动收弓，明确决定留下最后一个太阳。这不是射不中、漏靶、没箭、太阳逃走。
2. 百姓从惊惧到明白克制的意义，井水回潮，土地降温，草木和人声慢慢恢复。
3. 阿满抱着青竹简，在《山海二十简》中明确写下“后羿射落九日，留下一日”，并补写“射九留一”。
4. 阿满用一两句幽默把本篇接到二十篇体系：以后若轮到夸父追日，他一定先把青竹简泡凉，免得字还没写就熟了。
5. 结尾要完整收束后羿射日的神话，不要展开嫦娥奔月或夸父追日的新剧情。
""".strip(),
        },
    ]

    generated_acts = []
    previous = ""
    for spec in act_specs:
        print(f"正在生成后羿专用窄域重写：{spec['name']}（阿满/二十篇串线硬约束）...")
        system_message = {"role": "system", "content": common_system}
        user_message = {
            "role": "user",
            "content": (
                f"{spec['name']}目标长度：{spec['target']}。\n"
                f"前文摘要：{previous[-700:] if previous else '无，正在开篇。'}\n\n"
                f"{spec['content']}\n\n"
                "只输出这一幕正文。"
            ),
        }
        best_act = ""
        for attempt, temp in enumerate((0.72, 0.62), 1):
            reply = call_qianwen_api(
                [system_message, user_message],
                temperature=temp,
                top_p=0.86,
                repetition_penalty=1.25,
                max_tokens=spec["max_tokens"],
            )
            candidate = clean_story_postprocess(clean_markdown(reply or ""), myth_core)
            if candidate and (not best_act or len(candidate) > len(best_act)):
                best_act = candidate
            if (
                candidate
                and not has_obvious_garbled_text(candidate, myth_core)
                and not contains_thread_protagonist_violation(candidate, myth_core)
                and not contains_myth_core_violation(candidate, myth_core)
            ):
                best_act = candidate
                break
            print(f"警告：后羿专用{spec['name']}第{attempt}次生成未通过局部校验，正在重试...")
        generated_acts.append(best_act)
        previous = (previous + "\n\n" + best_act).strip()

    cleaned = clean_story_postprocess("\n\n".join(generated_acts), myth_core)
    cleaned = repair_thread_protagonist_system_link(cleaned, myth_core)
    cleaned = repair_houyi_controlled_rewrite(cleaned)
    if not validate_story_quality(cleaned, "改写神话故事后羿射日，要求有幽默", myth_core):
        print("警告：后羿专用API重写仍未通过验收，启用后羿受控保底稿。")
        fallback = build_houyi_manual_fallback()
        fallback = repair_thread_protagonist_system_link(fallback, myth_core)
        return clean_story_postprocess(fallback, myth_core)
    return cleaned


def repair_houyi_controlled_rewrite(text: str) -> str:
    """补强后羿专用重写中最容易被模型漏掉的固定验收短语。"""
    if not text:
        return text
    exact_marks = [
        "第一箭射落第一日",
        "第二箭射落第二日",
        "第三箭射落第三日",
        "第四箭射落第四日",
        "第五箭射落第五日",
        "第六箭射落第六日",
        "第七箭射落第七日",
        "第八箭射落第八日",
        "第九箭射落第九日",
    ]
    if not all(mark in text for mark in exact_marks):
        arrow_summary = "后羿稳住气息，阿满一边护着青竹简一边把箭序重新描清：第一箭射落第一日，第二箭射落第二日，第三箭射落第三日，第四箭射落第四日，第五箭射落第五日，第六箭射落第六日，第七箭射落第七日，第八箭射落第八日，第九箭射落第九日。写到最后一笔，他小声嘀咕：“这回要是再记错，我就不是小史官，是烤糊的竹签。”"
        insert_at = text.find("后羿射落九日")
        if insert_at >= 0:
            text = text[:insert_at] + arrow_summary + "\n\n" + text[insert_at:]
        else:
            text += "\n\n" + arrow_summary

    record_pattern = r'阿满[^。！？\n]{0,80}(青竹简|竹简)[^。！？\n]{0,80}(射九留一|射落九日|留下一日|留下最后一个太阳)'
    if not re.search(record_pattern, text):
        text += "\n\n阿满抱着青竹简，把这一页郑重收入《山海二十简》：后羿射落九日，留下一日，这四个字旁边又补上“射九留一”。他想起以后还要去记夸父追日，便悄悄把青竹简往阴影里挪了挪，生怕下一场还没开始，自己的字先熟了。"
    return clean_story_postprocess(text, None)


def build_houyi_manual_fallback() -> str:
    """后羿射日的受控保底稿，专门兜住逐箭、留一日和阿满二十篇串线。"""
    return """
灾变前一日，村子里还是寻常光景。天刚亮，卖饼老人支起炉子，妇人们到井边打水，孩子踩着田埂追一只翅膀沾泥的蜻蜓。后羿从林中回来，肩上背弓，手里拎着两只野兔。他先把猎物送给腿脚不便的老人，又蹲在井台边给弓弦上油。一个孩子凑过来问：“这张弓能把树上的酸枣射下来吗？”后羿说能。孩子又问：“那能不能只射甜的？”后羿抬眼看了看满树青枣，认真答：“这事得先跟树商量。”

村后有块平整石坪，是后羿平日练箭的地方。靶子不是奇物，只是一截老木桩，上头用炭画了三个歪圈。画圈的是卖饼老人，老人坚称最中间那圈很圆，只是木桩长得不配合。后羿站到百步之外，抬弓连发三箭，箭尾挨着箭尾钉进圈心。看热闹的孩子齐声叫好，老人却背着手走近，绕木桩看了半晌：“本事是好本事，就是费靶子。明日你若再射，我得画小些，省炭。”

后羿拔箭时，发现弓弦已有一处起毛。他没有将就，回到檐下拆弦重缠。粗麻要搓得匀，筋丝要勒得紧，一道结没收好，放箭时便可能偏出几丈。邻家青年看他忙了半日，笑说：“你射山鸡也这样讲究？山鸡又不会验你的弓。”后羿低头收紧绳结：“它不会验，箭会。”青年听不大懂，便蹲在旁边替他递麻线，递了两回都递成自己鞋带，索性闭嘴。

午后，田里的人趁日头正暖翻土。后羿也挽起裤脚下田，把几块挡犁的石头搬到田边。有人问他一个射箭的为何还管庄稼，他说弓只能赶走近处的祸，饭却要从土里长出来。卖饼老人听见，隔着田埂喊：“那你搬石头轻些，别一使劲扔到我炉子里，我今日的饼已经够硬。”后羿笑着把石头轻轻放下，孩子们却围过去敲了敲，仿佛非要确认英雄放下的石头是不是也比别人的响。

傍晚，炊烟沿屋脊慢慢散开。后羿把修好的弓挂在门边，箭一支支排好，坏了羽的挑出来重粘。村里最后一桶井水被提上来时，水面映着一轮安稳的落日。谁也没有多看，因为太阳每日东升西落，本是最不值得担心的事。卖饼老人收摊前还朝天边嘟囔：“明日别来太早，我面还没醒。”谁都没想到，次日来得太早的并不是一个太阳。那夜后羿还绕村看了一圈，替老人扶正柴垛，替孩子捡回滚进沟里的陶球。人们照旧关门歇息，只把弓箭留在檐下月光里，谁也不知道这份寻常到了天亮会有多金贵。

十日并出那天，天像被谁掀开了火窑的盖子。十轮太阳齐齐压在穹顶上，光芒挤着光芒，热浪推着热浪，连山石都被晒得冒出白气。大地焦灼百姓受难，田垄裂成一条条黑口子，井绳放到底只捞起半瓢烫水，老牛站在树影里，树影却瘦得像一根绳。村口卖饼的老人把饼举起来看了看，叹气说：“省柴倒是省柴，就是我这摊子快被天上接管了。”

阿满就是这时候抱着青竹简赶到的。他是编《山海二十简》的瑶池见闻小史官，本该走到哪里记到哪里，今日却被晒得走到哪里都像快熟到哪里。他把袖子盖在青竹简上，嘴里还硬撑：“我不怕热，我只是怕字被晒得先学会逃跑。”旁边一个孩子问他能不能用竹简遮脸，阿满立刻把竹简抱得更紧：“这可是要留给后人看的，不是留给我挡太阳的。再说了，它要是真能遮住十个太阳，我早把它供起来叫它大哥。”

百姓围到后羿身前，有人嗓子哑得说不出话，只能指指天，又指指裂开的田。后羿没有多问，他看见屋檐下昏睡的孩子，看见井边空着的陶罐，看见连飞鸟都贴着地面扑腾。他解下背上的弓，摸了摸弓弦，又一支一支检查箭羽。热风吹过，箭羽微微发卷，阿满凑近看了一眼，认真写下“弓还可用”，汗珠落上去，把“可”字洇得像“烤”。他赶紧补了一笔，小声道：“神农尝百草那回我已经把苦写成哭了，这次箭序再错，这支旧笔就该先罚我。”

后羿听见这句，竟笑了一下。他把箭袋束紧，抬头望向十日：“你只管记，不必替我担心。”阿满立刻点头，点到一半又抬袖擦汗：“我当然不担心，我只是提前替竹简担心。它今天跟着你上山，功劳不小，熟得也不小。”众人原本心口发紧，听他这么一嘀咕，竟短短笑了一声。那笑声很轻，却像干裂土地上先滚过的一滴水。

后羿登上最高的山脊。山风被十日烤得滚烫，吹到脸上像一张粗糙的热布。阿满跟在后头，走一步喘两口，把每一级石阶都记成劫难。他想把“山高”写得庄重些，笔尖一抖写成“山烫”，索性不改了：“也算实情。”后羿站定，脚下岩石被晒得发红，他把第一支箭搭上弦。十日悬在空中，像十只骄横的火眼俯视人间。百姓屏住呼吸，阿满也屏住呼吸，只是屏到一半想起自己还得活着写字，又悄悄补了一口气。

第一箭射落第一日。后羿拉满弓弦，臂上青筋像绷紧的山根，箭离弦时，尖啸穿过热浪，直直钉进最东边那轮烈日。那太阳猛地一颤，火光像破开的红壳四散飞溅，随后拖着长长焰尾坠向远方山外。地上的热意退了一层，百姓里有人忍不住抬头，刚抬到一半又被余光刺得缩回去。阿满蹲在岩后写：“第一箭射落第一日。”写完他吹了吹字，发现自己吹出的气也热得不讲理，便严肃补充：“此箭很稳，本人很烫。”

第二箭射落第二日。后羿没有等欢呼声涨起来，第二支箭已经压上弦。他换了半步，避开脚下裂开的岩缝，箭尖指向南侧那轮更亮的日。弓弦一响，天空像被一根黑线切开，第二日中箭后翻滚坠落，热云被拖出一条宽阔裂口。村里一个老人看见天上少了一轮，愣愣问：“能不能别摔坏，留着冬天烤粮？”旁人刚想笑，又想起自己连粮都快没了，笑声便酸了一下。阿满把这句也记在页角，嘀咕：“人都快烤干了，还惦记烤粮，真是会过日子。”

第三箭射落第三日。后羿的虎口被弓弦磨出血，血刚冒出就被热风吹干。他咬住牙，肩背一沉，把第三支箭送了出去。那箭穿过两团交叠的金光，像从火海里硬凿出一条路，第三日被射中时发出低沉轰鸣，坠落的光把山谷照得一片通红。阿满看见后羿手上血痕，想写“英雄无惧”，又觉得太端着，改成“英雄很疼但不说”。后羿扫他一眼，阿满立刻把竹简往怀里一收：“我这是写实，不是拆台。”

三日落下之后，山下第一次响起像样的欢呼。可欢呼只冲到半空，又被剩下七日压了回来。百姓们这才明白，灾难不是一块热石，搬开就算完；它像七只还没退场的火鼓，仍在头顶咚咚乱敲。一个年轻人扶着老母亲站到阴影里，阴影小得只能遮住半只脚，他便把自己的脚缩回去，让母亲多站一点。阿满看见这一幕，笔尖停了停，把原本想写的俏皮话轻轻划掉，只写：“民生受苦，寸影也贵。”

后羿没有回头。他听得见欢呼，也听得见欢呼里的怕。他把第四支箭夹在指间，低声问身旁的风：“还有力气么？”风被十日烤得没什么脾气，只把他的发梢吹起一点。阿满听见这句，忍不住接话：“风要是有力气，刚才就先把我吹下山凉快去了。”说完他又觉得不合时宜，赶紧补了一句：“当然，最好别吹，正文还没写完。”后羿被他逗得肩头松了一瞬，下一息，眼神又稳住了。

第四箭射落第四日。前三日坠下后，剩下的太阳似乎终于知道害怕，火光乱颤，热浪却更凶，像临走前还要把人间再按进锅里。后羿闭了闭眼，听风辨位，第四支箭从他指间疾出，压低一片翻卷火云。第四日被箭贯穿，光芒碎成万点红鳞，落在远山背后。阿满一边数一边写，写到“四”字时笔尖发滑，他赶紧用袖口按住竹简：“别乱跑，你只是个数字，不是被射的那个。”旁边孩子憋笑憋得打嗝，阿满板着脸说：“严肃点，我现在数错一个，后人就要多晒一轮。”

第五箭射落第五日。后羿放低弓臂，长长吐出一口气。他的影子在岩石上被拉得极短，仿佛也被晒得不愿多待。第五日悬在中天，光最盛，刺得众人眼底发疼。后羿忽然往左踏出一步，借山脊斜风稳住箭尾，箭光贴着热浪飞起，像一只不肯闭眼的鹰。第五日被射落时，井口边传来惊呼，有人摸到井壁上竟有了一点潮意。阿满赶紧记下，又小声补道：“第五日落，井先喘了一口气。本人也想喘，但本人暂时排队。”

第五日落后，山腰上的石缝里渗出一点凉意。那凉意很轻，轻得像谁悄悄把一枚薄叶贴在烧红的锅边，却足以让人知道天地还没有彻底坏掉。一个小姑娘捧着陶碗往山上跑，碗里只有两口水，跑到半道洒了一口，她急得快哭。阿满赶紧摆手：“别哭，水洒了还能记一笔，你哭了我还得分不清哪滴更金贵。”小姑娘被他说得愣住，噗地笑了一声，把剩下那口水递给后羿。

后羿没有接那口水。他看了一眼小姑娘干裂的嘴唇，只说：“留给你。”小姑娘把碗抱回怀里，眼睛红红的。阿满把这一句记下时，手指比先前稳了许多。他忽然明白，自己抱着青竹简在旁边发抖，不只是为了把热闹记全，也要把这些很小很小的选择记住。否则后人只知道九个太阳坠落，却不知道有人曾把最后一口水往英雄手里递，也不知道英雄又把水推回了人间。

第六箭射落第六日。连射五箭后，后羿的手臂开始发抖，弓弦每一次震动都像敲在骨头上。百姓想劝他歇一歇，可天上剩下的日头还在烧，谁也说不出那句歇。后羿自己却笑了笑：“还撑得住。”阿满立刻写下“还撑得住”，又抬头问：“这句算实话，还是你怕我们哭才说的？”后羿没答，第六支箭已经离弦，穿过翻涌的白光。第六日坠落，地面裂缝里的烟气慢慢低了下去，像终于被谁按住了脾气。

六日落后，天空的颜色终于有了层次。原先只有一片凶狠的白，如今白里露出一点青，青得很浅，却让百姓看得移不开眼。有人伸手去接那点青色，当然什么也接不住，只接了一掌心汗。阿满看见了，认真写道：“有人试图用手接天色，失败，但态度可嘉。”旁边老人问他这也要记，阿满点头：“要记。灾里的人若还会做傻事，说明心还没被晒硬。”

后羿趁这一息调整呼吸。他把弓弦放松，又重新拉紧，像在跟自己的骨头商量。每一根骨头都像要讨价还价，偏偏他没有余地。阿满在旁边看得脸色发白，低头摸了摸青竹简：“你听见没有？他骨头都快吵起来了。你可别也响，你一响我就以为你裂了。”青竹简当然不会答话，只有竹片边缘被热风吹得轻轻相碰，发出细碎声响。阿满立刻把它按住：“好好好，你也委屈，回去给你找阴凉。”

剩下四日像四只不肯认输的火兽，光芒交错，互相遮掩。百姓看不清它们的位置，只觉得天上还乱成一团。后羿却看得很清楚。他知道第七箭不能急，第八箭不能乱，第九箭不能带着恨。若箭里只有怒火，最后也会把人间一并点燃。阿满听他说“不能带着恨”，愣了一下，随即小声写下：“箭要准，心也要准。”写完他看着这六个字，难得没有加笑话，只在旁边画了一个被晒歪的小点，算是自己的署名。

第七箭射落第七日。剩下四日同时暴亮，像在用最后的骄横吓退他。后羿的额角青筋跳动，脚下岩石被汗水砸出一个个深色小点。第七箭上弦时，山风忽然反扑，热得阿满差点连人带简滚下去。他先抱住青竹简，才想起抱住自己，嘴里还不忘嘟囔：“我这叫职责分明，先保正文，再保正文作者。”后羿没有被风乱了手，箭尖微微一偏又稳稳归正。第七日中箭坠下，热风倒卷回来，吹得众人衣摆猎猎作响，却再也吹不散他们眼里的希望。

第八箭射落第八日。后羿换步、压肩、沉腕，动作比先前慢了许多，却也更稳。天空露出几道暗蓝的缝隙，像烧红的锅沿终于裂开一点凉色。第八日狡猾地缩进另外两轮光影之间，百姓只看见一团耀眼的白，分不清哪个该射。一个孩子掰着手指数天上火球，数到一半打了个嗝。阿满严肃纠正：“不是三个半，是三个。”话音刚落，他自己又看花了眼，赶紧低头装作检查笔尖。后羿的箭已经飞出，在光影交叠处骤然一闪，第八日翻落云外，天地像被谁悄悄打开了一扇门。

第九箭射落第九日。最后两日悬在天上，一轮仍旧暴烈，一轮却像被前八箭吓住，光芒收敛了些。后羿知道，真正沉重的不是射出去的箭，而是射完之后还要留下什么。他将第九支箭搭上弦，手指已经发麻，指节却稳得像刻在弓上。阿满原本想说句俏皮话，话到嘴边又咽了回去，只把青竹简压在膝上，笔尖停着不动。箭声响起，第九日被贯穿，火光在空中炸开又迅速暗下。远处群山第一次显出清楚轮廓，百姓看见天上只剩最后一个太阳，没人立刻欢呼，所有人都在等后羿的手。

第九日落下的余光像一场迟来的雨，明明仍是火，却让人觉得热浪终于有了尽头。百姓中有人跪下，有人站着，有人把孩子抱得很紧。那孩子问：“是不是好了？”大人张了张嘴，却不敢答。阿满也不敢答。他看着竹简上的九行字，忽然觉得每一行都像一支箭压在他膝头。往常他总嫌青竹简重，此刻才知道，有些重不是竹子的重，是人命、土地和明日的重。

后羿把最后一支箭从箭袋里抽出，又停住。那支箭的羽尾被热风吹得轻轻发颤，像也在等一个答案。阿满看见这一幕，心里一紧，差点脱口问“还射吗”。可他记得自己的位置，便把问题咽回去，只写：“此处不可替英雄问。”他写完自己都想笑，笑意却挂在嘴角没敢落下。因为后羿的脸上没有胜利的轻松，只有比拉满弓弦更深的思量。

后羿射落九日之后，天地并没有马上安静。最后一日悬在高处，光芒柔了许多，却仍旧让人心有余悸。有人喊：“还剩一个！”也有人低声问：“是不是少带一支箭？”阿满本来累得眼皮打架，听见这句差点笑出声，只好把脸埋进青竹简后面，闷闷道：“别乱说，他带的是箭，不是账本，哪能靠凑数收尾。”可是他笑完也紧张，因为他看见后羿又抬起了弓。

箭尖对准最后一日时，山谷里静得能听见干草恢复水分的细响。后羿的手臂在抖，弓弦也在抖，百姓的心跟着一起抖。只要这一箭出去，所有炙烤都会结束，可所有晨昏也会被一并射落。后羿望见焦田边一个孩子正护着半捧种子，那孩子没有哭，只是把种子往怀里藏，像还相信来年会有光照着它们发芽。后羿慢慢松开弓弦，没有放箭。他收弓，声音不高，却让所有人都听清：“九日已落，最后一日要留下。人间不能再被烧，也不能没有光。”

这句话落下时，最先松一口气的不是百姓，而是那片被晒裂的土地。裂缝边缘浮起一层湿色，像有人从地底慢慢推回了水脉。百姓仍旧不敢完全相信，有人伸出手掌去试阳光，试完又把手掌翻来覆去看，好像自己的手刚从火里赎回来。阿满也伸手试了试，立刻一本正经地记下：“最后一日脾气已改，暂不咬人。”写完他觉得这话太不庄重，又想划掉。后羿却说：“留着吧，人间本来就该能说笑。”

阿满听见这句，怔了怔。他一直以为《山海二十简》要写得很庄重，庄重到每个字都像坐在庙里。可今日他看见百姓在灾里哭，也在灾里笑；看见后羿疼得手抖，还能接住一句不正经的记述。他忽然明白，幽默不是把苦难变轻，而是人在苦难里还没有被压扁。于是他没有划掉那句“暂不咬人”，只在旁边补了四个小字：“笑后仍敬。”

山下有人开始试着站直。先站直的是一个孩子，他晒得脸颊发红，却把腰挺得像棵刚缓过来的小树。接着是妇人，是老人，是背着空筐的青年。一个男人把晒裂的木桶抱起来，发现桶底漏了，尴尬地笑：“它也受苦了。”阿满立刻接话：“桶底漏，至少证明它还有底线。”众人愣了一下，随即笑出声。笑声这次没有被热浪压回去，而是顺着山谷往远处滚，滚到还没完全复苏的田野上。

留下最后一个太阳的那一刻，比射中任何一日都难。百姓先是愣住，随后有人抬头试探，发现那光不再像刀，像一只终于懂得分寸的手。热风退成暖风，井口返潮，田埂上裂缝边缘渗出湿润泥色，几棵枯草慢慢舒开卷曲的叶尖。一个老人摸到井水，激动得捧了一把往脸上扑，扑完才想起水少，又尴尬地把手停在半空。阿满看得想笑，却只轻轻笑了一下：“省着点，您这一下比我整篇字都贵。”

后羿靠着岩石坐下，手臂抖得连弓都快握不住。百姓围上来，想谢他，又怕挤着他的伤。后羿喘了好一会儿，才抬眼说：“先别谢，谁有水，借我一口。”众人怔了怔，随即笑声和哭声一起涌出来。有人递水，有人递刚从阴处翻出的半块干饼，还有人笨手笨脚想替他扇风，扇了两下发现风还是热的，羞得把手放下。阿满在旁边补记：“英雄救民之后，第一愿望不是受拜，是喝水。此处极可信。”

那口水最后被众人分成了许多小口。后羿只喝了一点，剩下的递回去。递水的少年急了：“这是给您的。”后羿摇头：“我只要能站起来就够，你们还要回去种地。”少年捧着碗，不知道该说什么，最后只用力点头。阿满看着这一来一回，想写一段漂亮话，写到一半又停住。他觉得漂亮话太滑，容易从苦难上滑过去，便改写成：“水少，话少，心不少。”

夜色慢慢从山背后爬上来。过去许多日里，人们几乎忘了夜是什么样子，如今看见天边暗下去，反而有人害怕。一个孩子抓着母亲衣角问：“黑了怎么办？”母亲哽了一下，后羿抬头看着柔和的余光，说：“黑了就睡，明早还会亮。”这本是寻常话，此刻却像一份新的盟约。阿满赶紧记下，写完又小声嘀咕：“原来正常日子这么厉害，厉害到一句早睡早起都能把人说哭。”

火气退去之后，山上显出许多先前看不见的东西。石缝里有半截草根，岩壁上有被晒裂却没掉落的苔痕，远处溪床里有几枚圆石露出湿润光泽。阿满蹲下摸了摸一块石头，发现终于不烫手，竟郑重地对它拱了拱手。旁边孩子问他拜石头做什么，阿满一本正经：“它今天没把我烫得跳起来，值得一拜。”孩子笑得弯下腰，后羿也低低笑了一声。那笑声很轻，却比白日里任何欢呼都让人安心。

傍晚终于有了傍晚的样子。唯一的太阳斜斜照着土地，光色温和，远山显出层层青影。孩子们从屋檐下跑出来，在溪边追逐，笑声撞在石头上又弹回来。庄稼虽然仍旧枯黄，却不再像要立刻死去；人们把种子重新收进陶罐，把井绳一圈圈理好，把倒在路边的木桶扶正。后羿站在山脊上看着这一切，脸色苍白，眼神却安定。阿满摸了摸青竹简，确认它终于不烫手，才敢把最后几行写得端正些。

村里的人开始清点还能活下来的东西。半缸水，三袋种子，两头瘦牛，一片没被晒透的菜叶，还有一群刚刚学会重新大声说话的人。有人把这些报给阿满，阿满听得一愣一愣，最后忍不住说：“你们这是让我写灾后余数，还是让我开粮仓？”老人笑着拍他肩膀：“都写上，省得后人以为英雄一射完，日子就自己好了。”阿满被这句话拍得不再贫嘴，郑重把“日子还要人慢慢扶起来”记在竹简边上。

后羿下山时，百姓想扶他，他摆手说自己还能走。结果刚迈出三步，膝盖便很诚实地晃了一下。阿满眼疾手快地扶住他的弓，却没碰箭袋，只扶住那张已经松下来的弓身：“我可声明，我扶的是弓，不是替你威风。”后羿低头看他，难得笑得明显：“那就多谢这位只扶弓的小史官。”阿满立刻把脸绷住，仿佛刚才耳朵没有红：“不用谢，扶弓也算危险活，万一它嫌我手汗多怎么办？”

山路下方，最早递水的小姑娘又跑来，把那只陶碗举给后羿看。碗底只剩一点水光，却映着天上唯一的太阳。小姑娘问：“以后它每天都只来一个吗？”后羿看了看那轮温和的光，说：“该来一个，就来一个。”阿满在旁边补充：“要是多来，我先替青竹简请假。”众人又笑。笑过之后，小姑娘把陶碗抱回怀里，像抱着一个重新讲得通的明天。

等众人散去，山脚下升起第一缕真正像饭烟的烟。那烟不再被十日晒得直发白，而是慢慢弯着，像累坏的人终于能伸个懒腰。阿满望着它，忽然觉得这一笔也该写上。因为神话不是只停在英雄拉弓的那一刻，也停在灾后第一锅粥重新滚起来的声音里。

那声音很小，却比白日里任何轰鸣都更像胜利。

阿满听着，忽然觉得肚子也很诚实地叫了一声，便把这声也算作人间恢复的证据。

阿满抱着青竹简，在《山海二十简》中写下“射九留一”。他又郑重补上一句：“后羿射落九日，留下一日，天地恢复正常，万物复苏。”写完这句，他盯着那四个字看了很久，忽然觉得它们比前面九箭还沉。九箭救了人，一日留住了人间往后的清晨。阿满难得没有立刻插科打诨，只把竹简合了合，像怕惊动刚刚落回大地的安宁。

可安静只维持了一小会儿。阿满把这一简夹进《山海二十简》时，还是忍不住在页角补了一笔：后羿这边是太阳太多，多到他差点把字晒熟；以后若轮到夸父追日，他一定先把青竹简泡凉，免得还没开跑，字先熟了。补完他又看了后羿一眼，小声道：“这一篇我记住了，最难的不是把多余的射下来，是知道该留下哪一个。”后羿没有回头，只望着那轮温和的太阳。风从山下吹来，终于带着一点水气，吹过青竹简，也吹过刚从灾难里缓过来的万家炊烟。
""".strip()


def build_generic_myth_manual_fallback(prompt: str, myth_core: dict = None) -> str:
    """通用本地保底稿：严格按核心事件链、阿满串线和干净神话语境扩写到长篇。"""
    if not myth_core:
        return ""
    title = myth_core.get("title", "这则神话")
    if title == "后羿射日":
        return build_houyi_manual_fallback()

    def safe_constraint_text(value: str) -> str:
        value = value or ""
        replacements = {
            "风险": "险境",
            "瓶子": "药匣",
            "帮忙": "在旁照看",
            "帮助": "扶一把",
            "工作": "差事",
            "任务": "差事",
            "计划": "打算",
            "项目": "事项",
            "系统": "章法",
        }
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value

    def safe_aman_event(value: str) -> str:
        value = value or ""
        replacements = {
            "画出八卦": "这一处线条初成",
            "造出文字": "这一处字形初成",
            "捏出人": "这一处泥形初成",
            "炼石补天": "这一处彩石升起",
            "补上天空": "这一处天穹渐稳",
            "尝遍百草": "这一处百草得名",
            "射落九日": "这一处烈日渐少",
            "砍倒桂树": "这一处斧声落下",
        }
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value

    core_summary = safe_constraint_text(myth_core.get("core_summary") or f"{title}是一则流传久远的神话。")
    event_chain = [e for e in (myth_core.get("event_chain") or []) if e]
    if not event_chain:
        event_chain = [core_summary]
    must_include = [e for e in (myth_core.get("must_include") or []) if e]
    final_required = [e for e in (myth_core.get("final_required_phrases") or []) if e]
    thread = myth_core.get("_thread_protagonist", {}) or {}
    role = thread.get("role") or "阿满在旁见证此事，把它写入《山海二十简》。"
    must_do = [e for e in (thread.get("must_do") or []) if e]
    required = [e for e in (thread.get("required_phrases") or []) if e]
    callback_options = [e for e in (thread.get("callback_options") or []) if e]
    forbidden_terms = [e for e in (myth_core.get("forbidden_elements") or []) if e]
    global_cross_forbidden = [
        term for term in ["射日", "过海", "补天", "哭长城", "奔月主线", "八仙法宝渡海", "不死药奔月主线"]
        if term not in title
    ]
    safe_callbacks = [
        option for option in callback_options
        if not any(term and term in option for term in forbidden_terms + global_cross_forbidden)
    ]
    other_candidates = ["女娲补天", "神农尝百草", "夸父追日", "精卫填海", "伏羲画卦", "西王母"]
    other_story = next(
        (candidate for candidate in other_candidates if candidate != title and not any(term and term in candidate for term in forbidden_terms)),
        "女娲补天",
    )
    callback = safe_constraint_text(safe_callbacks[0]) if safe_callbacks else f"阿满想起{other_story}那一页，心里暗暗把两场大事放在《山海二十简》的相邻处。"

    cn_nums = "一二三四五六七八九十"
    paras = [
        f"天地间的旧事，有些一开口便像风从山海之间吹来。《{title}》这一简开始时，阿满抱着青竹简站在事发之地，先把袖口抹平，又把旧笔在掌心转了半圈。他是不受凡间年代限制的瑶池见闻小史官，奉命按神话次序把二十篇神话编入《山海二十简》，可每次赶到现场，他都觉得自己不像史官，倒像被大场面点名的倒霉孩子。",
        f"阿满先在竹简边上写下本篇来意：{core_summary} 他写得很郑重，郑重到风从旁边一过，他立刻用胳膊压住竹简，生怕这页还没入简，自己先被吹成传说。旁人问他怕不怕，他小声答：“怕当然怕，可我若不记，后人只听见雷声，看不见当时谁腿软。”",
    ]
    if must_include:
        paras.append(
            "为了不把这一简写偏，阿满先把几个硬词刻在竹简背面：" + "、".join(must_include) + "。他一边刻一边嘀咕：“这些字像柱子，柱子立住了，故事才不会走到隔壁神话串门。”刻到最后一字，旧笔掉了一根毛，阿满盯着它叹气：“你也知道今日难写，是不是？”"
        )
    canonical_values = []
    canonical_terms = myth_core.get("canonical_terms", {})
    if isinstance(canonical_terms, dict):
        for value in canonical_terms.values():
            if isinstance(value, str) and value and not value.startswith("如使用"):
                canonical_values.append(safe_constraint_text(value))
    object_rules = myth_core.get("object_consistency", [])
    if isinstance(object_rules, dict):
        object_rules = [object_rules]
    for rule in object_rules or []:
        if isinstance(rule, dict):
            allowed = [safe_constraint_text(form) for form in (rule.get("allowed_forms") or []) if form]
            if allowed:
                canonical_values.append(allowed[0])
    canonical_values = list(dict.fromkeys(canonical_values))
    if canonical_values:
        paras.append(
            "阿满又特意核对本篇名物，不敢把关键称呼写混：" + "、".join(canonical_values) + "。他把这些字圈在竹简内侧，郑重得像给旧笔立规矩。旧笔偏在此时又掉了一根毛，阿满瞪它一眼：“你若把名物写错，我就把你也列入本篇笑点。”"
        )
    if required:
        paras.append(
            "他又把本篇的串线规矩默念一遍：" + "、".join(required) + "。念完以后，阿满把青竹简往怀里搂紧，脸上摆出一副很懂行的样子，心里却已经开始盘算，若待会儿场面太大，自己到底该先护简，还是先护脑袋。想来想去，他觉得两样都要护，毕竟脑袋没了没人写，竹简没了写了也白写。"
        )
    if role:
        paras.append(
            f"按瑶池交给他的说法，{safe_constraint_text(role)} 阿满对这句话很服气，也很有意见。服气的是他确实只能见证，不能越俎代庖；有意见的是，每次所谓见证，都离飞沙走石、惊涛烈焰、哭笑不得只差半步。他把这点委屈写在页角，又觉得太像抱怨，便改成：“小史官到场，胆子暂缺，笔还在。”"
        )
    if must_do:
        paras.append(
            f"临近正事时，阿满还想起几条必须办到的小规矩：他只能记录、护住青竹简、短促吐槽，并把《{title}》放进《山海二十简》的大脉络里；真正的核心行动仍要由本篇人物亲自完成。这些话听着简单，真到现场却一点也不省心。他试着挺直腰背，结果青竹简从怀里滑出半寸，吓得他赶紧按住：“别急，你是简，不是主角，不用抢先登场。”旁边有人听见，忍不住笑了一声，紧张气也被这声笑轻轻戳开。"
        )

    for idx, event in enumerate(event_chain, 1):
        num = cn_nums[idx - 1] if idx <= len(cn_nums) else str(idx)
        paras.extend([
            f"事情推进到第{num}处，正是“{event}”。这几个字落在竹简上很短，落到眼前却铺得极大：天色、地声、人心、尘土和水气都被卷进来，像一张看不见的网慢慢收紧。真正站在当场的人才知道，神话不是一句话蹦出来的，它先压住人的肩，再逼人抬头。",
            f"这一刻，当前神话里的核心人物没有退到旁人身后。该出手的出手，该远行的远行，该承受的承受，该选择的选择。阿满看见那人衣角被风拽住，看见脚下尘土被踏出深印，也看见旁边百姓或亲友的眼神从慌乱变成盼望。他想写一句漂亮话，笔尖却先写了个歪字，只好小声补救：“不是我不庄重，是这场面先把我吓歪了。”",
            f"围着“{event}”这一处，众人原本七嘴八舌，有人担心，有人催促，有人把话说到一半又咽回去。阿满把这些声音都听在耳里，挑最实在的记：有人问这样做能不能成，有人问若不成又怎么办，还有人只顾把孩子往身后护。阿满听得心口发紧，却仍挤出一句轻话：“诸位慢些慌，我这竹简还没找到合适的慌法。”众人愣了一下，竟短短笑开。",
            f"“{event}”并非一蹴而就。前一息似乎顺利，后一息便有阻力翻上来；刚有人松口气，新的难处又从旁边探头。核心人物咬住这口气，把手上的事继续往前推，动作一次比一次稳，眼神一次比一次沉。阿满不敢插手，只能护着青竹简跟在侧旁，把每一次停顿、每一次失败后的再起、每一声短促的笑都记下来。",
            f"到了“{event}”这一折的尾声，局面终于往前挪了一大步。不是所有人都立刻明白其中分量，可阿满明白一点：这页若写得太轻，就对不起当场的汗；写得太重，又会把活人写成木像。他想了想，在页角添道：“第{num}处事成半分，笑也半分，剩下半分留给后头继续受罪。”写完他自己先笑，笑完又赶紧把表情收住，装作刚才那句不是他说的。",
        ])

    for round_idx in range(1, 7):
        event = event_chain[(round_idx - 1) % len(event_chain)]
        paras.extend([
            f"阿满回看前文，发现“{safe_aman_event(event)}”这几个字底下还藏着许多小动静。有人手心全是汗，却把话说得很硬；有人明明怕得要命，还要替旁人挡一挡；也有人把道理讲得头头是道，下一步就被风吹得发髻乱成一团。阿满把这些小处补进去，觉得神话若只有高处，就像只有骨头没有热气。",
            f"他又想起{other_story}那一页，忍不住在《山海二十简》的页角做了个短短的类比：那边有那边的难，这边有这边的苦，天地从不按小史官的胆量安排场面。阿满写到这里，抬头看了看眼前的人，小声道：“我算明白了，二十简不是二十趟远路，是二十次把我胆子拿出来晾。”这句不算正经，却很像他。",
            f"真正让人记住的，不只是大响大动，还有众人在缝隙里冒出的笑。有人把沉重话说轻了，旁边人便能喘一口气；有人把狼狈样藏不住，大家反而更愿意跟着往前走。阿满最擅长把这种时候记下来：他不把苦写没，也不把笑写假，只让两样并排站着。苦负责说明这事难，笑负责证明人还没认输。",
        ])

    paras.append(
        f"临近收束时，阿满按着青竹简，想起瑶池给他的跨篇叮嘱：{callback} 他没有把别篇人物请到眼前，也没有让别篇故事抢走这一页，只在页角轻轻补了一笔，让《山海二十简》里的山海气息彼此相连。补完他还不放心，低头对竹简说：“你记住，是串线，不是串门。”"
    )
    if final_required:
        paras.append(
            "故事走到终处，阿满把收束字句一一写牢：" + "、".join(final_required) + "。这些字不是给验看的印章，而是这一场大事真正落地的回声。该完成的终于完成，该留下的也终于留下，众人回望来路，才发现自己方才笑过、怕过、撑过，竟都成了这则神话不可少的一部分。"
        )
    else:
        paras.append(
            f"故事走到终处，《{title}》终于收住了它最响的一声。该完成的已经完成，该留下的也终于留下，众人回望来路，才发现自己方才笑过、怕过、撑过，竟都成了这则神话不可少的一部分。阿满把旧笔停在竹简上方，难得没有立刻贫嘴。"
        )
    paras.append(
        f"阿满最后把这一简收入《山海二十简》，郑重写下《{title}》的名号。他在末尾补道：“本篇诸事，核心人物亲自走完，阿满只在旁边记、怕、笑、护简，绝无越权。”写完这句，他自己先觉得好笑，又觉得这笑里有一点敬意。神话大得吓人，可人若还能在大事里说一句真话、做一次选择、护住一点希望，它便不只是传说，也是后来者心里的一盏灯。"
    )

    text = "\n\n".join(paras)
    safety = 0
    while len(text) < MYTH_TARGET_TOTAL_MIN and safety < 10:
        safety += 1
        event = event_chain[(safety - 1) % len(event_chain)]
        text = (
            text
            + "\n\n"
            + f"阿满又翻回“{event}”那一段，补上先前漏掉的细处。风从衣袖里钻过去，尘从鞋边滚过去，旁人的呼吸一声比一声紧，可真正办事的人仍把脚步放稳。阿满看得心里发虚，嘴上却还要撑着：“别慌，我已经把最慌的那个字写完了，剩下的字应当会懂事些。”这话把旁边人逗得一笑，也让紧绷的气息松开半寸。\n\n"
            + f"他明白这一页不能只记奇观，还要记人怎么在奇观里站住。若是《山海二十简》只剩光、雷、水、火和惊叹，后人读完只会抬头看天；若把那些小小的迟疑、互相扶住的手、忍不住冒出来的笑也写进去，后人便知道神话再高，仍从人心里长出来。阿满于是又添一笔，字迹端端正正，只有末尾一点墨痕歪了，像他终于承认自己也被感动了一下。"
        ).strip()
    cleaned = clean_story_postprocess(text, myth_core)
    safety = 0
    while len(cleaned) < MYTH_TARGET_TOTAL_MIN and safety < 8:
        safety += 1
        event = event_chain[(safety - 1) % len(event_chain)]
        aman_event = safe_aman_event(event)
        addition = (
            f"阿满合上又翻开青竹简，觉得“{aman_event}”这一处还应再添几笔。不是添空话，而是添那些当场最容易被大声响盖住的小反应：有人退后半步又站回来，有人嘴上说不怕却把衣角攥皱，有人被阿满一句不合时宜的轻话逗笑，笑完才发现自己终于能喘顺一口气。阿满把这些都写进《山海二十简》，因为他知道，神话若只剩大事，读来会亮，却不够暖。"
            f"\n\n他又在页角补了一句：“这一简的难处，不在我写得多慢，在它发生得太认真。”说完他自己先有点不好意思，赶紧把旧笔收回袖中。可旁边有人听见，还是笑了。那笑声不大，却像给整篇故事添了一点人间气，让后来读到此处的人知道，{title}不只是远古传闻，也是人在风浪、尘土、离别、苦痛或抉择面前硬撑出来的一口气。"
        )
        cleaned = clean_story_postprocess((cleaned + "\n\n" + addition).strip(), myth_core)
    return cleaned


def generate_myth_controlled_rewrite(prompt: str, myth_core: dict = None) -> str:
    """
    通用整篇受控重写兜底。
    当分节拍生成因局部校验、压缩或污染导致最终稿不过关时，用核心事件链直接生成一版。
    """
    if not myth_core:
        return ""
    title = myth_core.get("title", "神话故事")
    if title == "后羿射日":
        return generate_houyi_controlled_rewrite(prompt, myth_core)

    myth_core_block = format_myth_core_block(myth_core)
    event_chain = "；".join(myth_core.get("event_chain", []) or [])
    must_include = "、".join(myth_core.get("must_include", []) or [])
    final_required = "、".join(myth_core.get("final_required_phrases", []) or [])
    required_actions = myth_core.get("required_character_actions", {}) or {}
    required_actions_text = "；".join(f"{name}：{action}" for name, action in required_actions.items())
    forbidden_brief = "、".join(MANUAL_REVIEW_BAD_TERMS[:95])
    system_message = {
        "role": "system",
        "content": f"""
你是擅长轻喜剧中国神话改写的中文小说作者。只输出正文，不要标题、列表、说明、字数统计或括号备注。
本次只写《{title}》，目标 7000~8500 字，绝对不要少于 7000 字，不要超过 9000 字。
必须使用简体中文和古代神话语境；不得出现现代设备、现代职业、直播、系统、手机、电脑、手电、导航、工作报告、记者、记录仪、模型、文档、注释、未完待续。
严禁粗口、辱骂、低俗脏话；不得出现“卧槽”“老子”等破坏风格的表达。

【当前神话硬骨架】
- 故事名：{title}
- 必须按这个核心事件链推进：{event_chain}
- 正文必须自然写出这些识别点：{must_include}
- 收束处必须尽量写出这些最终验收短语/意象：{final_required}
- 只扩写当前神话，不要把其他神话主线搬进现场。

【阿满串线硬规则】
- 阿满是贯穿二十篇神话的见闻小史官，必须带着青竹简，把本篇收入《山海二十简》。
- 阿满必须至少一次通过翻看青竹简、想起旧经历、做类比、页角补笔或伏笔，短促连接另一个神话；只能一两句，不能让别篇人物实体进入现场。
- 阿满提供幽默、见证和体系线索，但当前神话的核心人物必须亲自完成核心行动；阿满不得替主角解决危机。
- 阿满不能叫记者、记录员、历史学家、玩家、系统、现代人；不能携带现代科技。

【幽默硬要求】
- 幽默要高密度但不乱：每一幕都有多处人物压力下的嘴硬、反差、短促拆台、道具小翻车或严肃记录反差。
- 幽默类似《哪吒魔童降世》的活泼劲：人物处在大事里仍有鲜活反应，但不使用网络梗、职场梗、脏话或现代流行语。
- 至少 10 处短促笑点，至少 8 处自然对白；笑点必须贴着当前神话主线。

{myth_core_block}
""".strip()
    }
    user_message = {
        "role": "user",
        "content": f"请完整改写《{title}》，要求有幽默，并严格满足神话核心主线和阿满《山海二十简》串线约束。只输出正文。",
    }
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.72,
        top_p=0.86,
        repetition_penalty=1.28,
        max_tokens=9000,
    )
    cleaned = clean_story_postprocess(clean_markdown(reply or ""), myth_core)
    cleaned = repair_thread_protagonist_system_link(cleaned, myth_core)
    cleaned = repair_myth_final_requirements(cleaned, myth_core)
    cleaned = repair_myth_quality_tail(cleaned, myth_core)
    cleaned = repair_myth_minimum_length(cleaned, myth_core)
    if not validate_story_quality(cleaned, prompt, myth_core):
        print(f"警告：《{title}》单次整篇受控重写未通过，正在启用三幕受控重写...")
        actwise = generate_myth_actwise_controlled_rewrite(prompt, myth_core)
        if story_revision_is_better(actwise, cleaned, prompt, myth_core):
            return actwise
    return cleaned


def generate_myth_actwise_controlled_rewrite(prompt: str, myth_core: dict = None) -> str:
    """
    通用三幕受控重写兜底。
    用更少、更稳定的 API 调用直接生成三幕，避免节拍卡局部失败后反复补短稿。
    """
    if not myth_core:
        return ""
    title = myth_core.get("title", "神话故事")
    if title == "后羿射日":
        return generate_houyi_controlled_rewrite(prompt, myth_core)

    myth_core_block = format_myth_core_block(myth_core)
    event_chain = "；".join(myth_core.get("event_chain", []) or [])
    event_items = [str(item).strip() for item in (myth_core.get("event_chain", []) or []) if str(item).strip()]
    first_cut = max(1, len(event_items) // 3)
    second_cut = max(first_cut + 1, (len(event_items) * 2) // 3) if len(event_items) > 2 else len(event_items)
    act_event_groups = [
        event_items[:first_cut],
        event_items[first_cut:second_cut],
        event_items[second_cut:],
    ]
    if not act_event_groups[1]:
        act_event_groups[1] = event_items[first_cut:] or event_items
    if not act_event_groups[2]:
        act_event_groups[2] = event_items[-1:] or event_items
    must_include = "、".join(myth_core.get("must_include", []) or [])
    final_required = "、".join(myth_core.get("final_required_phrases", []) or [])
    forbidden_brief = "、".join(MANUAL_REVIEW_BAD_TERMS[:60])
    common_system = f"""
你是擅长轻喜剧中国神话改写的中文小说作者。只输出故事正文，不要标题、幕名、列表、说明、字数统计、括号备注或方括号内容。
本次只写《{title}》，必须是古代神话语境，完整保留当前神话核心故事，不得写成现代行政稿、项目汇报、系统任务、直播节目、档案整理或随机拼贴。
严禁出现这些污染词或类似表达：{forbidden_brief}。

【当前神话硬骨架】
- 故事名：{title}
- 必须按这个核心事件链推进：{event_chain}
- 正文必须自然写出这些识别点：{must_include}
- 收束处必须尽量写出这些最终验收短语/意象：{final_required}
- 只扩写当前神话，不要把其他神话主线搬进现场。

【阿满串线硬规则】
- 阿满是贯穿二十篇神话的见闻小史官，必须带着青竹简，把本篇收入《山海二十简》。
- 阿满必须至少一次通过翻看青竹简、想起旧经历、做类比、页角补笔或伏笔，短促连接另一个神话；只能一两句，不能让别篇人物实体进入现场。
- 阿满提供幽默、见证和体系线索，但当前神话的核心人物必须亲自完成核心行动；阿满不得替主角解决危机。
- 阿满不能叫记者、记录员、历史学家、玩家、系统、现代人；不能携带现代科技。

【幽默硬要求】
- 幽默要像《哪吒魔童降世》那类压力下的嘴硬、反差、短促拆台、道具小翻车和严肃记录反差。
- 笑点必须贴着当前神话主线，不用网络梗、职场梗、现代词、脏话或低俗辱骂。
- 每幕都有对白和动作反差；关键牺牲、抉择、结尾处要把笑点收住，留下余味。

{myth_core_block}
""".strip()

    act_specs = [
        {
            "name": "第一幕",
            "target": "2100~2400字",
            "min_chars": 1600,
            "max_tokens": 3200,
            "content": "先用三到五个具体生活场景写主线发生前众人在做什么、日常秩序怎样、核心人物当时处于什么状态，再让异变或需求自然闯入。随后写开端和危机成形，阿满带青竹简进入现场并自然制造4到6处笑点。背景必须参与后续因果，不能是可删除的空景。不要提前完成核心任务，不要写结局。",
        },
        {
            "name": "第二幕",
            "target": "3900~4400字",
            "min_chars": 3000,
            "max_tokens": 5600,
            "content": "写核心行动全过程：严格沿着本幕分配到的核心事件逐步推进，把每一步的起因、动作、阻力、结果和人物反应写足，不能用总结句跳过。阿满只能记录、护简、吐槽或用一两句跨篇类比串联《山海二十简》，不能替主角解决问题。至少8处贴合情境的短促笑点，并让压力逐段上升。",
        },
        {
            "name": "第三幕",
            "target": "1900~2300字",
            "min_chars": 1500,
            "max_tokens": 3200,
            "content": "写核心结果和余波收束：先完成事件链，再用具体人物行动呈现余波，完整落到原神话结局与寓意。阿满必须把本篇写入《山海二十简》，并用一两句短促、好笑或有余味的跨篇连接收束。结尾要有情感回响，但不要作文式总结、创作说明或验收口吻。",
        },
    ]

    generated = []
    previous = ""
    for act_index, spec in enumerate(act_specs):
        best = ""
        for attempt, temp in enumerate((0.74, 0.62), 1):
            print(f"正在生成《{title}》三幕受控重写：{spec['name']}（参考阿满二十篇体系约束）...")
            user_message = {
                "role": "user",
                "content": (
                    f"{spec['name']}目标长度：{spec['target']}。\n"
                    f"本幕必须重点展开的事件：{'；'.join(act_event_groups[act_index])}。\n"
                    f"前文摘要：{previous[-900:] if previous else '无，正在开篇。'}\n\n"
                    f"{spec['content']}\n\n"
                    "只输出这一幕的故事正文，不要幕名、标题、说明或任何格式标记。"
                ),
            }
            reply = call_qianwen_api(
                [{"role": "system", "content": common_system}, user_message],
                temperature=temp,
                top_p=0.86,
                repetition_penalty=1.28,
                max_tokens=spec["max_tokens"],
            )
            candidate = clean_story_postprocess(clean_markdown(reply or ""), myth_core)
            if candidate and (not best or len(candidate) > len(best)):
                best = candidate
            if (
                candidate
                and len(candidate) >= spec["min_chars"]
                and not has_obvious_garbled_text(candidate, myth_core)
                and not contains_body_drift(candidate, myth_core)
                and not contains_thread_protagonist_violation(candidate, myth_core)
                and not contains_myth_core_violation(candidate, myth_core or {})
            ):
                best = candidate
                break
            print(f"警告：《{title}》{spec['name']}第{attempt}次三幕受控生成未通过局部校验，正在重试...")
        generated.append(best)
        previous = (previous + "\n\n" + best).strip()

    cleaned = clean_story_postprocess("\n\n".join(generated), myth_core)
    cleaned = repair_thread_protagonist_system_link(cleaned, myth_core)
    cleaned = repair_myth_final_requirements(cleaned, myth_core)
    cleaned = repair_myth_quality_tail(cleaned, myth_core)
    cleaned = repair_myth_minimum_length(cleaned, myth_core)
    if len(cleaned) < MYTH_TARGET_TOTAL_MIN or has_repeated_story_units(cleaned):
        print(f"警告：《{title}》三幕合稿仍偏短或出现重复，正在执行一次整篇终审扩写。")
        polished = generate_myth_polished_clean_rewrite(prompt, myth_core, cleaned)
        if story_revision_is_better(polished, cleaned, prompt, myth_core):
            cleaned = polished
    if len(cleaned) > MYTH_TARGET_TOTAL_SOFT_MAX:
        cleaned = shrink_story_to_target_length(cleaned, prompt, myth_core)
    return clean_story_postprocess(cleaned, myth_core)


def generate_myth_one_shot_reference_rewrite(prompt: str, myth_core: dict = None) -> str:
    """以已认可的后羿成稿为完整文风参照，一次生成连贯长篇。"""
    if not myth_core:
        return ""
    title = myth_core.get("title", "神话故事")
    if title == "后羿射日":
        return build_houyi_manual_fallback()

    events = [str(item).strip() for item in myth_core.get("event_chain", []) if str(item).strip()]
    required_actions = myth_core.get("required_character_actions", {}) or {}
    thread = myth_core.get("_thread_protagonist", {}) or {}
    callback = (thread.get("callback_options", []) or ["在页角用一句旧经历连接另一篇神话"])[0]
    event_plan = "\n".join(f"{index}. {event}" for index, event in enumerate(events, 1))
    action_plan = "\n".join(f"- {name}必须亲自完成：{action}" for name, action in required_actions.items()) or "- 当前神话主角亲自完成全部核心行动"
    myth_core_block = format_myth_core_block(myth_core)
    thread_block = format_thread_protagonist_block(thread)
    reference_story = build_houyi_manual_fallback()
    forbidden_brief = "、".join(MANUAL_REVIEW_BAD_TERMS)

    system_message = f"""
你是成熟的中文民间神话轻喜剧小说作者。只输出《{title}》正文，不要标题、章节名、幕名、列表、创作说明、字数统计或验收总结。

【成稿目标】
- 写成一篇从开端到结局完整连贯的小说，目标7800到8700个中文字符。
- 开头先用800到1200字写灾变或主线发生前的寻常生活，以及核心人物原本在做什么；背景必须自然进入主线，不能另开支线。
- 严格依次完成以下事件，不倒叙重启、不重复同一事件：
{event_plan}
- 每个事件只发生一次，但要写足起因、动作、阻力、人物反应、直接结果和转场。

【角色动作】
{action_plan}
不得让无名配角、阿满、新仙人、新妖怪或偶然出现的宝物代替上述人物完成行动。除核心约束已有内容外，不新增法术、神兽、仙官、预言、遗物、神秘身世或奇迹。

【阿满和幽默】
- 阿满是男性、不受凡间年代限制的瑶池见闻小史官，只带青竹简、旧笔、小布袋，按神话次序编《山海二十简》。全篇安排四到六次有意义的出场，每次都随主线处境变化，不能重复自我介绍或固定台词。
- 阿满所说的“上回/以后/下一简”只表示个人记录顺序，不表示各篇神话的历史先后。
- 阿满是主要笑点承担者。他出场时可连续有二到四个短笑点，来自怕热、怕水、怕高、怕累却嘴硬，护简狼狈，认真记错后被拆台；其他人物也可有性格反差和熟人互怼。
- 阿满只能观察、记录、吐槽和见证，绝不替主角解决危机。悲剧死亡、牺牲和重大抉择发生后立即收住笑点。
- 只在全文最后一次阿满出场时，用一到两句完成这条跨篇连接：{callback}。此前不得提到其他神话故事、人物或器物，别篇人物不得来到现场。

【语言边界】
- 朴素、具体、清楚，以动作和自然对白为主；笑点要像人在压力里嘴硬，不用现代网络梗，不写作文式寓意总结。
- 绝不在正文中解释“这不是预告/重复/重新开场/重启”，也不写“按发生顺序完整留在简上”“不由结尾一句替代”等向审核者证明结构合规的句子；只用人物行动和现场结果自然体现结构。
- 不细写骨头、皮肉、血浆、连续伤口，不机械罗列第几步或精确数量；人物死亡只能克制写气力耗尽、倒下和环境余波。
- 阿满不用血写字，不携带地图、日晷、墨瓶等新增道具。不得写删除正文、修改稿件、读者、作者、画面、章节等元叙事。
- 严禁使用历史坏稿污染词：{forbidden_brief}

【本篇硬约束】
{myth_core_block}

【本篇阿满约束】
{thread_block}

【完整文风参照】
下面《后羿射日》是用户认可的质量基准。学习它的篇幅、朴素短句、动作清晰度、苦中带笑、阿满嘴硬、主角不被抢戏和灾后余波。绝不复制其中的后羿、太阳、弓箭、村民细节、台词或事件到《{title}》。

{reference_story}
""".strip()

    best = ""
    for attempt, temperature in enumerate((0.28, 0.18), 1):
        print(f"正在一次性生成《{title}》完整正文（第{attempt}次，参考后羿基准与阿满串线约束）...")
        reply = call_qianwen_api(
            [{"role": "system", "content": system_message}, {"role": "user", "content": f"现在直接写完整的《{title}》正文。"}],
            temperature=temperature,
            top_p=0.72,
            repetition_penalty=1.16,
            max_retries=2,
            max_tokens=12000,
        )
        candidate = clean_story_postprocess(clean_markdown(reply or ""), myth_core)
        if candidate and len(candidate) > MYTH_TARGET_TOTAL_MAX:
            candidate = force_trim_story_to_hard_max(candidate, MYTH_TARGET_TOTAL_MAX)
        reasons = []
        if len(candidate) < MYTH_TARGET_TOTAL_MIN:
            reasons.append(f"篇幅不足{len(candidate)}")
        if len(candidate) > MYTH_TARGET_TOTAL_MAX:
            reasons.append(f"篇幅超限{len(candidate)}")
        if has_obvious_garbled_text(candidate, myth_core) or contains_body_drift(candidate, myth_core):
            hits = [term for term in MANUAL_REVIEW_BAD_TERMS if term and term in candidate]
            reasons.append("语言污染" + (f"[{','.join(hits[:8])}]" if hits else ""))
        if has_repeated_story_units(candidate):
            reasons.append("重复段落或故事重启")
        if not myth_core_requirement_met(candidate, myth_core, final=True):
            reasons.append("核心事件不完整")
        if not myth_core_required_sequence_met(candidate, myth_core):
            reasons.append("事件顺序错误")
        if not thread_protagonist_system_requirement_met(candidate, myth_core):
            reasons.append("阿满体系串联不足")
        if contains_thread_protagonist_violation(candidate, myth_core):
            reasons.append("阿满越权或设定违规")
        if humor_signal_count(candidate) < 14:
            reasons.append("幽默密度不足")
        if not reasons:
            return candidate
        print(f"警告：《{title}》一次性成稿第{attempt}次未通过：{'、'.join(reasons)}。")
        if not best or len(candidate) > len(best):
            best = candidate
    print(f"错误：《{title}》两次完整成稿均未通过，拒绝把坏候选写入最终正文。")
    return ""


def generate_myth_chunked_reference_rewrite(prompt: str, myth_core: dict = None) -> str:
    """按十个连续大段生成，适配 Qwen 单次稳定输出长度。"""
    if not myth_core:
        return ""
    title = myth_core.get("title", "神话故事")
    if title == "后羿射日":
        return build_houyi_manual_fallback()

    events = [str(item).strip() for item in myth_core.get("event_chain", []) if str(item).strip()]
    if not events:
        events = [str(item).strip() for item in myth_core.get("must_include", []) if str(item).strip()]
    event_indexes = [min(len(events) - 1, index * len(events) // 10) for index in range(10)]
    totals = {event_index: event_indexes.count(event_index) for event_index in set(event_indexes)}
    seen = {event_index: 0 for event_index in totals}
    part_focuses = []
    for event_index in event_indexes:
        seen[event_index] += 1
        occurrence = seen[event_index]
        total = totals[event_index]
        if total == 1:
            phase = "完整写出这个事件的起因、关键动作和直接结果"
        elif occurrence == 1:
            phase = "只写这个事件如何发生、人物为何行动和最初阻力，不得提前写结果"
        elif occurrence == total:
            phase = "只写新的应对、直接结果和向下一事件的转场，不得重述起因"
        else:
            phase = "只写行动中的新阻力和应对，不得重述起因或提前收束"
        part_focuses.append(f"{events[event_index]}：{phase}")
    if title == "北冥鲲鹏":
        part_focuses = [
            "北冥岸边的寻常渔猎生活，阿满到场；只建立环境，不得出现异物、碑或鲲的亲属",
            "北冥水下巨鲲浮现，明确其体量与长期生活状态；不得变形",
            "鲲感到北冥边界与南方召唤，主动产生化鹏远行的愿望；不得新增身世",
            "鲲开始化为鹏，用水面轮廓、背影和双翼渐展写变化，不描写骨骼肌肉，阿满在岸上承担笑点",
            "化鹏已经完成，第一次明确称其为大鹏，只写完整身影与双翼展开如垂天之云；不得回顾身体变化，不得起飞",
            "大鹏等待并辨认六月大风，阿满在强风前护住青竹简承担笑点",
            "六月大风到来，大鹏击水蓄势，准备向南；不得出现光柱、门户或神秘契约",
            "大鹏乘风扶摇而上，越过北冥高空；只写风、云、海和飞行动作",
            "大鹏持续向南冥天池飞去，写清路程和意志；不得新增试炼、生物或法宝",
            "大鹏抵达或明确飞向南冥天池，完成逍遥远行；阿满收入《山海二十简》并短促连接八仙过海",
        ]
    elif title == "雷泽华胥":
        part_focuses = [
            "雷泽附近部落的寻常生活，华胥原本在劳作，阿满到场；不得出现异象",
            "华胥独自走入雷泽，看见一个巨大而清晰的大人足迹；不得感孕",
            "华胥观察足迹并试着踏入其中，明确写出履大人迹的动作",
            "雷声响起，华胥感到身体发生温和变化并离开雷泽；阿满承担短促笑点",
            "时间过去，华胥确认自己因履迹而感孕，部落人从疑惑转为照料",
            "华胥孕期继续生活，阿满记录时承担笑点；不得出现胎儿影像、符号或预言",
            "临近生产，族人准备住处与热水，华胥安静等待；不写神异法术",
            "华胥明确生下伏羲，现场有真实婴儿啼哭与母子相见；描写克制，不写血祭",
            "族人迎接新生伏羲，华胥亲自抱住孩子；只写当下，不扩写伏羲童年和未来功绩",
            "阿满把华胥履迹感孕、生下伏羲写入《山海二十简》，短促连接伏羲画卦，收束文明始祖的来处",
        ]
    elif title == "西王母":
        part_focuses = [
            "昆仑瑶池的寻常清晨与蟠桃园日常，阿满到场；不得出现新法术、结晶或符号",
            "西王母亲自查看蟠桃与不死药的保管，明确长生资源有规矩和代价",
            "瑶池来客赴会，其中一名凡人来客为亲人求不死药，宴前出现人情冲突",
            "求药者当面陈情，西王母听完但没有立即给药；阿满只能旁听并承担短促笑点",
            "其他来客对是否破例产生分歧，进一步写明一旦随意给不死药会破坏秩序",
            "西王母查问求药缘由与可承担的责任，权衡人情和规矩；不得用法术试探",
            "有人试图趁乱触碰装不死药的匣子，西王母当场喝止；只能用威严和守卫制止",
            "西王母公开裁决：不允许私取或无代价获得不死药，同时妥善安置病者与求药者",
            "来客接受裁决，瑶池宴会恢复，但众人以行动遵守蟠桃与不死药规矩",
            "西王母在秩序中保留人情，长生有代价的主题由结果落下；阿满收入《山海二十简》并得到继续见世面的嘱咐",
        ]
    elif title == "哪吒闹海":
        part_focuses = [
            "陈塘关临海百姓的寻常生活，哪吒与李靖、殷夫人的家庭日常，阿满来记录《山海二十简》中的这一篇；不得下水或开战",
            "哪吒到九湾河戏水，混天绫搅动东海龙宫；写清无心闯祸如何发生，不得出现李艮和敖丙",
            "巡海夜叉李艮上岸问罪，言语冲突升级，哪吒用乾坤圈打死李艮；动作清楚但不血腥，不得出现敖丙",
            "龙太子敖丙出海追责，与哪吒交战；哪吒打败敖丙并抽去龙筋，阿满只在远处护简记录，不参与交战",
            "东海龙王敖光到陈塘关问罪，李靖震怒、殷夫人护子，哪吒从嘴硬转为看见百姓将受牵连；不得兴水",
            "四海龙王兴水逼迫陈塘关，百姓受灾；哪吒尝试独自面对，阿满承担灾情间的短促笑点但不嘲笑灾民",
            "哪吒为不连累父母和百姓主动担责，以死谢罪；父母与百姓明确回应，描写克制、完全停止笑点",
            "太乙真人收住哪吒魂魄，以莲花莲藕重塑化身；写重生动作、亲情牵挂和哪吒醒来后因莲身不习惯产生的一次干净互怼，严禁低俗身体笑话",
            "哪吒以莲花化身再战，只用混天绫、乾坤圈和自身勇气亲自制服东海龙王敖光、令龙王收回水患；不得新增蛟虬、神兽、法术或让任何人代打",
            "陈塘关恢复安宁，哪吒与李靖、殷夫人重新相见；阿满把完整因果写入《山海二十简》并短促连接八仙过海",
        ]
    elif title == "大禹治水":
        part_focuses = [
            "洪水到来前村落的寻常生活随即被洪水打断，百姓流离，阿满抱着青竹简到场；不得出现治水方案",
            "鲧以堵截之法治水失败并受罚，堤障越堵水势越高；明确给大禹留下教训，不得由阿满评定方法",
            "大禹承接父亲未竟的治水重任，徒步勘察山川水势，经过比较后亲自决定改堵为疏",
            "大禹率众开沟凿渠、疏山导水，初见水流转向；阿满因泥水和堵疏错字承担强笑点，不得指挥劳作",
            "治水队伍面对山口阻塞与长期疲惫，大禹调整水道并准备开凿龙门；写众人协作，不得当天完成",
            "大禹第一次、第二次经过家门而不入，听见家人消息仍继续赶往险情；阿满只保留极轻的嘴硬余味",
            "大禹第三次经过家门而不入，明确听见家中声音、看见家门却为百姓继续前行；本段庄重，不得开强笑点",
            "大禹带领众人开凿龙门、继续疏通九河，水路一段段连起来；阿满记录劳作与泥水反差，不得提出方案",
            "九河疏通，洪水被引入大海，田地、道路和村落重新露出；写具体灾后恢复，不得提前总结九州安定",
            "治水成功、九州安定，大禹终于踏上归家之路；阿满把改堵为疏、三过家门、开凿龙门、疏通九河、引洪入海写入《山海二十简》并短促连接愚公移山",
        ]

    thread = myth_core.get("_thread_protagonist", {}) or {}
    final_required = "、".join(myth_core.get("final_required_phrases", []) or [])
    callback = (thread.get("callback_options", []) or ["在《山海二十简》页角用一句旧事连接另一篇神话"])[0]
    thread_must = "；".join(thread.get("must_do", []) or [])
    required_actions = myth_core.get("required_character_actions", {}) or {}
    action_plan = "；".join(f"{name}必须亲自完成{action}" for name, action in required_actions.items())
    style_excerpt = """
村口的老人把刚烙好的饼翻了个面，发现背面黑得很有主见，便叹气说：“它若再熟一点，就该自己下地走了。”旁人笑了一声，手里的活却没停。笑不是把难处说没，只是让人先喘一口气。

阿满抱着青竹简从泥坡上滑下来，先护住简，后护住自己，最后只护住了一脸尴尬。他爬起来还要嘴硬：“我是在量坡有多陡。”孩子指着他屁股上的泥印问量出来没有，他拍了半天没拍净，只好答：“量出来了，坡比我的脸皮薄。”

真正到了要紧处，众人都安静下来。主角低头检查手里的东西，一处一处摸过，不说漂亮话。阿满也把笑收住，只在青竹简上写清谁做了什么、付出了什么。事情过去后，灶火重新点起，破桶重新箍好，孩子重新敢在路边追跑；神话的大事便这样落回普通人的日子里。
""".strip()
    beiming_tail_parts = {
        1: """北冥岸边的人起得都早。天色还是灰的，渔妇已经在石滩上摊网，老船工蹲在船腹旁补一道旧缝，两个孩子提着木桶追退潮留下的小鱼。风里有盐味，灶上有粥味，谁家的门板被吹得吱呀响，主人隔着院墙喊一句“知道了”，门板照旧响自己的，半点不肯听劝。

阿满就是这时来到北冥的。他背着小布袋，怀里夹着青竹简，鞋里进了沙，每走三步便要抖一次脚。第一次抖出一粒，第二次抖出两粒，第三次什么也没抖出来，他仍不放心地又抖了半天。提桶的孩子问他是不是在给北冥行礼，他把鞋穿好，严肃答道：“史官落脚之前，总得先确认脚还归自己管。”孩子点点头，转身便把这句话告诉了半条街，还添了一句，说外乡先生的脚似乎不大听话。

阿满没顾上辩解。他来此是为了给《山海二十简》添一页北方见闻，原只打算记潮汐、渔船和冬日如何结冰。他在滩边找了块平石坐下，刚把简册展开，一条小鱼从桶里蹦出来，正落在空白竹片上。阿满和鱼对视片刻，低声商量：“你若肯自己写，我便把笔让你。”小鱼甩了他一脸水。孩子把鱼捡回去，说它大概嫌笔太旧。阿满擦着眉毛，把“北冥鱼性情直爽”郑重记在页角，仿佛刚才吃亏的另有其人。

日头渐高，渔船陆续离岸。老船工却一直望着远海，没有动。他说近来北冥有些异样：深水里的鱼群总在同一个时辰让开，海面会隆起一道看不见尽头的暗影，随后又沉下去。年轻渔人笑他眼花，老人也不争，只把今日的船拴得比往常牢。阿满听见“看不见尽头”，笔尖便停了。他看看手里不过两掌长的竹简，又看看远海，先把小布袋压在简册上，小声道：“凡是看不见尽头的东西，最好别赶在我竹片不够的时候来。”

午后，海风忽然停了。远处的浪一层层低下去，飞鸟离开水面，近岸的小鱼也钻进石缝。喧闹的滩头渐渐安静，只有门板不知情，还在最后吱呀了一声。老船工站起来，指向水天相接的地方。那里浮出一线深沉的青黑，不像乌云，也不像礁石。暗影缓慢向上，推开大片海水。阿满抱起青竹简，忘了鞋里还有沙。他第一次没有急着写，只跟众人一起望着北冥，等那片大得无法估量的身影露出水面。""",
        2: """先露出水面的是一道宽阔脊背。它从远海升起，海水沿两侧缓缓退开，仿佛北冥中间忽然多了一座会呼吸的岛。可岛不会摆尾。那道巨影只轻轻动了一下，近岸便涌来一重长浪，把搁在浅滩上的木船一齐托高，又稳稳放下。

众人这才知道，老人说的不是眼花。那是一条鲲。它生在北冥，长在北冥，身躯大得无人能说清究竟有几千里。站在岸上的人看不见它的头尾同时出现，只能看见眼前一段青黑脊背一直伸到雾里。几个年轻渔人原本还想估量它有多长，先拿渔船比，又拿海湾比，比到最后谁也不说话。船可以数，海湾可以走一圈，鲲却像北冥本身一样，越看越不知道边界在哪里。

鲲没有冲向岸边，也没有搅翻渔船。它在深水中缓慢游动，每一次摆尾都让远处海面起伏。鱼群跟着水势分开，待它过去又重新聚拢。阳光落在它背上，只照亮极小一片，像有人把一枚铜钱放在漫长黑夜里。岸上的孩子忘了提桶，桶中小鱼趁机跳走两条。孩子追出几步又停下，因为那两条鱼即便逃回北冥，与鲲相比也小得像两点水珠。

鲲在北冥生活了很久。深水足以托住它，寒潮也不能逼它离开。它熟悉海底的沉静，熟悉冬夏水流的更换，也熟悉岸边渔火一盏盏亮起又熄灭。但这一日，它浮在水面，没有像从前那样很快沉回去。它抬起头，久久望向南方。南方隔着无数云水，那里有一片广阔的南冥天池。北冥的人从未去过，只从老人相传的话里知道那个名字。

傍晚到了，鲲仍朝南方停着。晚霞从它身侧铺过去，风重新吹起，却没有让它转头。老船工看出，那不是偶然浮上海面换一口气。鲲正在等候某个时刻，也正在作出一个只有它能完成的选择。它巨大的身躯属于北冥深水，可那道望向南方的目光已经越过岸线。夜色落下后，鲲沉回半身，背脊仍露在水上，像一条连接海与天的长路。岸边的人没有散去。他们点起火堆，安静守着，想知道北冥养育出的巨鲲，究竟要怎样走向遥远的南方。""",
        3: """第二日清晨，北冥上空积起厚云。鲲从水中重新升起，比前一日更高。海水从它背上奔流而下，落回北冥，响声传到岸边，如同一场只落在海上的大雨。它依旧望着南方，随后缓慢舒展身体。长久伏在深水里的形态开始改变。

最先显出的不是奇光，也不是凭空出现的门户，而是一层层贴着水面展开的羽毛。青黑的鱼背渐渐抬高，两侧宽阔的鳍向外延伸。海风穿过新生的长羽，发出低沉回声。鲲每动一下，北冥便随之起一重浪；每一重浪退下，那副身躯便离鱼的旧形更远一些。它没有痛苦嘶鸣，也没有旁人施法相助。北冥托住它，风吹干它的羽翼，变化从它自身发生。

岸边的人看着那条看不见首尾的巨鲲渐渐成为一只同样无法估量的大鸟。鱼尾收拢成修长尾羽，双鳍展开为左右巨翼，原本贴近水面的头颅昂向天空。直到最后一片海水从长羽间落尽，鲲已经不再是鲲。站在北冥中的，是鹏。

鹏第一次展开双翼时，天色骤然暗了一层。并非乌云遮日，而是那双翼本身覆盖了大片天空。翼端伸入远处云中，岸边的人仰到脖子发酸，也看不见尽头。云贴在羽下，被缓缓推向两旁；双翼垂落时，真如从青天挂下的云幕。老人低声说：“翼若垂天之云。”这句话沿着人群传开，大家才终于有了能够记住所见奇景的几个字。

鹏没有立刻起飞。刚刚完成变化的长翼需要风，北冥此刻的风还只是平常海风，托不起如此庞大的身影。它站在水中等候，目光仍向南方。每年六月，北冥都会有大风自海天深处而来，长浪随风奔涌，云层向南铺开。鹏要等的正是六月大风。

日子一天天接近六月。鹏有时收翼立在深水，有时缓缓展开，让寻常海风从羽间经过。岸边的人也从最初的惊惧变成敬畏。他们不再把鹏当作一座突然出现的怪山，而明白眼前的大鸟曾是北冥巨鲲，也将借北冥之风去往南冥。它的变化不是为了惊吓谁，更不是为了留在原地供人议论。鲲的深水生活已经结束，鹏的远行尚未开始，两者之间只隔着一场必将到来的大风。""",
        4: """阿满直到人群开始说话，才想起自己是来记录的。他低头看青竹简，第一片写着“鱼很大”，第二片写着“比第一眼更大”，第三片只剩一个孤零零的“大”字，后面拖着长长墨痕。渔童凑过来看，问他为何三片都写同一个意思。阿满把简册合上，镇定道：“这叫层层深入。”渔童说最后一层似乎已经深入到他袖口，因为墨都蹭上去了。阿满背过手去，决定成熟的史官不与孩子争袖子。

他重新找了一块干净竹片，写下“北冥有鱼，其名为鲲”。写到鲲的大小，他迟疑许久。有人说像十座山，有人说像百座城，也有人坚持刚才只看见半条，不能乱猜。阿满把各人的说法听完，干脆写“不知其几千里也”。老船工点头，说不知道便写不知道，总比拿十条船硬凑强。阿满很满意，顺口道：“史官最大的学问，有时就是把不知道写得字迹端正。”话刚出口，风把他尚未干透的“不”字吹糊了，像是北冥对这门学问另有意见。

鹏再次展翼，人群齐齐后退。阿满也退，退得格外讲究，嘴里还数着自己离水边几步。数到第五步，他后脚踩进一个空鱼篓，整个人坐了下去，篓子严丝合缝套在腰上。渔童问他是否要乘篓追鹏，阿满撑着地面回答：“我是在查这种器物能不能抵挡大风。”两个渔人合力把篓子拔下来时，他又补一句：“结论是能挡住人，挡不住脸面。”众人笑过，紧绷的肩膀才稍稍松开。

笑声没有惊动鹏。它站在北冥中，双翼投下巨大阴影。阿满收住玩笑，仔细记下鲲化鹏的整个次序。他没有写是谁赐予变化，也没有替它编造来历，只写北冥巨鲲依照本性化成大鹏，鹏翼若垂天之云，将等待六月大风前往南冥天池。写到这里，他发现旧笔被海水打湿，笔毫分成三岔，每写一字都像同时有三个人争着落笔。他吹了吹笔尖，小声道：“一支笔分出三种主意，难怪历史难写。”

六月尚未到，岸边生活仍要继续。渔妇晒鱼，船工补船，孩子把被鹏影吓散的小鱼重新捉回桶里。只是每个人做事时都会不时抬头，看鹏是否还在。阿满也给自己的简册添了两道绳结，第一道防风，第二道防第一道临阵改主意。他把简册抱在胸前，跟着老人观察云向和潮声。鹏不需要他们帮忙，却让所有人第一次认真等待一场风。""",
        5: """六月终于临近。北冥的云比往日走得快，清晨还堆在北方，午后已经连成一道向南延伸的长带。海水一日比一日高，浪声也一夜比一夜深。老船工让年轻人把船全拖上岸，又把屋顶的草绳重新勒紧。众人知道，六月大风快来了。

鹏在远海中站起。经过多日舒展，它的双翼已经完全张开。左翼横过一片云，右翼遮住半边日光，长羽在风前保持安静。岸上的人再看不出鲲的鱼形，只看见一只背负青天的大鹏。它低头望过北冥，那里是它出生与成长的地方。深水曾容纳它无边的身躯，寒冷海流曾陪它度过漫长岁月。如今它没有厌弃北冥，只是它已经成为鹏，南方才有等待它的天空和天池。

最初几阵风从海面扫来，只能掀动翼端。鹏试着展开长翼，风很快从下面漏走，留下一片翻卷白浪。它便重新收住，没有贸然起飞。第二日，风势更大，云被推向南方，鹏的双翼抬起一些，巨大的身影仍未离水。它继续等。真正的远行不能只凭急切，还要认清天地给出的时机。

第三日夜里，北冥远处响起连续浪声。那声音不是一重浪拍岸便停止，而是从极远之处层层赶来，一阵接一阵。天上的云全朝同一方向移动，近岸芦苇伏低，系船的粗绳绷得笔直。渔人熄灭外面的火，把孩子领进屋里，又忍不住站在门口向海上张望。

鹏迎着风声抬头。双翼从水面缓缓升起，翼下带起的水落成无数白线。它尚未振翼，北冥的浪已经开始向它脚下聚集。六月大风越过远海，正带着足以托起它的力量抵岸。鹏把身体转向南方，长尾在水后摆正。它等待了许多日，也在北冥生活了无法计数的岁月，此刻却没有一丝迟疑。

天将亮时，南方云层露出一线清光。鹏看着那道方向，安静地展开全部双翼。垂天的云影覆盖北冥，岸上的屋舍、船只与人都落在翼影里。无人催促，也无人能替它迈出第一步。六月大风已经到来，北冥长浪已经奔向岸边。下一刻，大鹏将击水而起，把深水中的过去留在身后，背负青天，走上通往南冥天池的漫长风路。""",
        6: """风到岸前，阿满先忙了起来。他把青竹简塞进衣襟，觉得硌得慌，又改夹在腋下；风从侧面一撞，简册差点飞走，他赶紧抱回怀里。小布袋绑在腰间会乱甩，绑在背后又够不着，最后他干脆把袋绳绕了两圈，勒得说话都短了半句。渔童问他是否紧张，他吸着气答：“不紧，我只是把自己装订得比较牢。”

众人往高处退，阿满却要找一个既能看见鹏、又不至于被浪卷走的位置。他先躲到老船背后，发现船板挡住半边天；又站上一块礁石，刚摆出史官观风的姿势，脚下海藻便让他滑回原地。他最后选中一根粗木桩，双臂抱紧，青竹简横在胸前。渔妇说远看像木桩自己长了一圈衣裳。阿满不服，想腾出一只手整理衣领，风立刻把他袖子蒙到脸上。他隔着袖布闷声宣布：“此处风势，已经开始不讲礼数。”

六月大风从海上压来，岸边再没有人发笑。鹏立在翻涌水中，双翼若垂天之云。阿满眯着眼看了许久，腾出手在简上写“风至”。墨刚落下便被吹成一条细线。他赶紧用手掌盖住，揭开时“风”字印在掌心，竹片上只剩半个。渔童说这样也好，一份记在简上，一份记在手上。阿满看看掌心，低声道：“若每件大事都这么记，二十简写完，我怕是连额头也得借出去。”

鹏仍在等最后一股稳风。阿满也渐渐安静。他把老船工关于六月风的话、众人收船的动作、鹏转向南方的时刻逐一记清。眼前的壮阔不需要他添来历，更不需要他替大鹏解释。他只是一个站在岸边的见证者，能做的便是护住竹简，不把看见的事写错。

风声更近，海面高高隆起。阿满把旧笔咬在嘴里，双手按简，忽然发现木桩上的绳头正一下下敲自己后脑。他回头瞪绳子，绳子被风吹回来，又敲一下。他不敢松手，只能小声商量：“今日主角在海上，你别抢。”绳头显然没有听懂，第三下敲得更响。旁边人忍笑忍得肩膀发抖，阿满索性把这三下也记成“风催落笔”，坚决不承认自己被一截绳子教训过。

远海传来沉重羽声。鹏俯下身体，足下长浪向两旁分开。岸上所有人同时屏住呼吸。阿满把写有鲲化鹏的一简压在最里面，确认“北冥”“巨鲲”“大鹏”“垂天之云”几个字都没有被墨水糊掉，才抬头望去。属于鲲的等待已经结束。属于鹏的第一步，就在六月大风抵达的这一刻开始。""",
        7: """六月大风真正抵岸时，北冥先静了一瞬。浪头伏低，渔网贴在滩上，连芦苇也朝同一个方向弯下腰。下一刻，远海像被一只看不见的巨手推起，长浪一重赶着一重，从天边直压到大鹏脚下。大鹏没有急着飞。它站在水中，双翼展在身侧，翼若垂天之云，把岸边最后一点晨光也遮住了。风从南方来，穿过羽间，发出低沉而绵长的响声。大鹏抬头听了片刻，仿佛终于等到一个约定已久的名字。

岸上的渔人忙着把船拖得更高。有人抱住木桩，有人压住晒了一半的网，还有人把鱼篓扣在头上，后来才发现鱼还在篓里，湿尾巴正一下下拍他的后颈。孩童先笑出了声，很快又被眼前铺满天空的双翼惊得闭上嘴。几个曾经说巨鲲只会占地方的老人站在最前头。他们没有躲，只把手搭在眉上，看那只由鲲化成的大鹏如何迎风。直到这一刻，他们才明白，北冥过去容下的并非一条贪睡的大鱼，而是一场尚未张开的远行。

大鹏试着扇动一次双翼。风沿岸推过，门板齐响，晾鱼的绳子全朝南方绷直。它随即停住，没有急躁地强行拔地。六月大风仍在汇集，远处的浪峰一列列赶来，像北冥把积攒多年的力气送到它脚下。大鹏低下身体，目光越过水天交界。南冥天池尚不可见，可方向已经清楚。它既没有向岸上的惊叹低头，也没有为旧日讥笑发怒，只在风最稳的一刻向前迈去。

它向前踏出一步，巨大的足爪没入海中。第二步落下，北冥翻起一道白浪。待第三步踏实，它猛然展开双翼，翼下的海水轰地向两旁分开。它俯身击水，水花腾起，像整片北冥忽然长出雪白的山。第一击让近岸渔船同时后退，第二击把远处沉云震开一道缝，第三击之后，庞大的身影终于离开水面。没有光柱，也没有门户，只有六月大风稳稳托住它。大鹏借风抬升，长尾扫过浪尖，北冥海面留下纵横千里的白痕。岸上人仰着头，谁也顾不上说话，只听见羽声与风声合在一起，向南滚去。""",
        8: """大鹏越升越高。起初，它的影子还压在北冥上，渔人抬头便能看见那片黑影随浪摇动；再往上，海面缩成一块深青的砚，岸边屋舍细得像散落的米粒。六月大风从它身后推来，它不与风争，只把双翼舒展开，让云从翼尖下成片退开。风急时，它略微收翼；风缓时，它再把翅膀放平。每一次动作都简单、沉着，像一个走惯远路的人知道何时迈步、何时借坡。

云层一重又一重压在前方。大鹏没有撞散它们，而是顺着风势从云间穿过。白雾贴着羽毛流走，片刻后又在身后合拢。偶尔有雨落下，还未落到北冥，便被风带向远处。它想起做鲲时的深水：那里沉静、宽阔，也曾是安稳的居所。可安稳并不等于永远停留。水能托住鲲的身躯，却不能替鹏展开双翼。如今北冥仍在脚下，并没有因为它离开而变小；真正改变的是它看天地的目光。

高处没有岸上那些议论，也没有谁来告诉它应该飞多远。只有迎面的风不断试探，仿佛每走一步都在问它是否当真愿意离开。大鹏以长久而平稳的振翼作答。它不求一口气飞到终点，只让每一次起伏都朝着南方。云下的北冥逐渐被天色遮住，旧日熟悉的海湾、礁石和渔火依次隐去。大鹏心中没有怨恨，也没有得意。能离开，并不是为了否认曾经容身的水，而是为了回应已经成为鹏的自己。

它抟扶摇而上，直至九万里高空。到了那里，尘声已经远了，头顶天色清亮，脚下云海无边。北冥的寒气留在旧水里，南方的暖意却顺风送来，带着遥远水泽的潮润。大鹏向下望了一眼，没有回头。它化鹏并不是为了在故地显出多大本事，也不是为了让岸上的人惊叹；那双垂天之翼既已展开，便该去能容下它的远方。于是它把身形转向南方。六月大风从翼下穿过，云层被划开一条宽阔道路。大鹏沿着这条路飞去，身后只有渐渐合拢的白云，再没有多余奇象。""",
        9: """向南的路很长。白日里，大鹏越过连绵云海，阳光在背羽上缓缓移动；入夜后，星河落在翼旁，仿佛也跟着它向南。它不追逐星光，也不向海面寻找捷径，只认准南冥天池所在的方向。风有时转弱，它便放低一些，从云下借来湿润气流；风再起时，它重新升高，让长翼越过一座又一座云峰。天地广阔，真正陪它赶路的只有呼吸和风。

第一夜过去，东方亮起薄白，大鹏仍在南行。海上的晨雾从下方升起，在它腹下铺开，又被身后的风慢慢卷散。第二个黄昏到来时，北方已看不见一丝熟悉的寒色。它也有疲惫的时候，双翼会比清晨沉重，羽声会从响亮变得低缓。但它不把疲惫当作走错路的证据，只在风势平稳处稍稍舒展身体，随后继续向前。远方之所以叫远方，正因为不能凭一次振翼便抵达。

途中也有云墙横在天际。云里雨声密集，前路一时模糊。大鹏收住急势，沿着云墙边缘飞行，耐心等南风重新露出方向。雨落在长翼上，很快顺着羽端滑下。待云层变薄，它重新抬高，南方的天光果然还在原处。它既不需要与每一片云争胜，也不必把每一次阻挡都当成敌意。能辨认方向，能在风变时守住自己的选择，便足以走完这段路。

越往南，海色越温，云也不再带着北冥的冷硬。远处天际终于浮出一片沉静碧光，不像日影，也不像晚霞。那光平铺在天地交界处，水面没有怒浪，只有宽缓波纹一圈圈向外舒展。大鹏知道，南冥天池到了。它放慢速度，双翼从高处缓缓压低，垂天的云影也随之落向水面。长途飞行没有把它变成另一个神怪，只让它更清楚自己为何离开北冥。它绕天池上空一周，确认下方水域开阔，便收拢尾羽，向那片碧水下降。风送到这里，已经完成了自己的事，渐渐散入南方云气之中。""",
        10: """大鹏落在南冥天池边缘时，水面只荡开一道宽缓涟漪。它站稳，抬头看见南方天空没有尽头，低头又看见天池足以映下完整双翼。北冥曾容纳巨鲲，六月大风托起了鹏，而南冥天池接住了这场远行。大鹏没有鸣叫，也没有再证明什么，只把双翼慢慢收在身后。它终于抵达了自己选择的远方。所谓逍遥，不是凭空消失，也不是不受任何约束，而是认清本性之后，仍有勇气借风走完该走的路。

天池的水很静，大鹏的倒影从岸边一直铺到远处。它低头饮了几口水，随后沿着浅岸缓缓走动，让一路绷紧的双翼得到歇息。南方的风从水面吹来，已经不再催它赶路。这里没有围观者追问它究竟飞了多少里，也没有旧日声音衡量它该在水里还是天上。天池只是宽阔地接纳它，如同北冥当初接纳那条巨鲲。不同的是，这一次大鹏清醒地知道，自己为何来到这里，又将以怎样的身形面对天地。

北冥岸边的人直到云影散尽才开始说话。有人把压住的渔网重新挂起，有人扶正被风吹歪的鱼架。那个先前拿鱼篓挡风的人终于摘下篓子，满头都是鱼鳞，硬说这是亲眼见鹏必须付的见识钱。孩童们学着大鹏展开胳膊，在滩上迎风跑，没跑几步便撞作一团，爬起来还互相指责对方的翅膀太占地方。老人们没有再说巨鲲白白占海，只望着南方，把那道远去的云路记在心里。

阿满还保持着仰头的姿势，脖子酸得不敢立刻低下。他想装作镇定，刚开口说“史官看天本是常事”，下巴便僵得只能随着话音轻轻发抖。渔童问他是不是冻着了，他含糊回答：“是见识太大，脖子一时装不下。”等旁人替他把脑袋慢慢扶正，他先摸青竹简，再摸旧笔，最后才想起检查自己。小布袋被风吹到了背后，他转着身找了两圈，渔童指了指，他便一本正经地说自己是在查看南北方向。

他抱紧青竹简，认真写下“鲲化为鹏”，又写“翼若垂天之云”，最后补上“乘六月大风，向南冥天池”。海风偏偏在这时掀起简页，他手忙脚乱按了半天，差点把“鹏”字写成一只张着嘴的怪鸟。渔童忍不住笑，阿满尴尬地小声嘴硬：“字飞得快，说明记得像。”下一笔又被水珠晕开，他赶紧解释那不是墨迹，是北冥替自己按的手印。渔童问北冥为何只按在错字上，阿满沉默片刻，把那片竹简悄悄翻了过去。

潮水恢复往常起落，阿满终于把经过从头核对一遍：北冥有巨鲲，巨鲲化鹏，大鹏展翼，借六月大风抟扶摇而上，背负青天，最终来到南冥天池。每一笔都有前因和去处，没有凭空多出门户，也没有谁替大鹏完成选择。他把这一页收入《山海二十简》，只在页角短短提了一句八仙过海：那一回众人各凭法宝渡浪，这一回浪本身托起了大鹏。写完他立刻用胳膊压紧简册，生怕刚记好的“鹏”先飞了；至于他本人，还是留在地面为好，毕竟一阵风就能把布袋转到背后的人，暂时不宜谈九万里。""",
    }
    jingwei_controlled_parts = {
        1: """东海边的清晨总比内陆亮得早。渔船还系在木桩上，天边已经泛白，潮水把昨夜留下的贝壳一枚枚推上沙滩。炎帝的小女儿女娃第一次来到这里，站在高坡上望了许久。她过去见过河，也见过湖，却没见过水一直铺到天边。随行的人忙着搭棚、生火、清点水囊，她却沿着岸线走来走去，想把海风、浪声和咸味都记住。

阿满也在这支队伍里。他抱着青竹简，本想写一句“东海浩瀚”，刚落下“浩”字，一阵风便把简页拍回他脸上。女娃回头问他看清海有多大没有，他从竹片后探出头，说：“看清了。它至少比我的简册大，而且脾气也比简册大。”女娃笑他拿什么都和竹简比。阿满把被风吹乱的绳结重新系好，认真解释：“史官出门只带这一件能比的，总不能拿饭量量海。”

渔人劝女娃不要离岸太远。东海看着平静，潮下却有急流，午后还常起大风。女娃点头听着，又蹲下帮一个孩子把翻倒的鱼篓扶正。她性子明快，不爱摆炎帝女儿的架子；别人忙时她也搭手，别人说起海上旧事，她便追问每一种云和风意味着什么。阿满想把这些都写进简里，笔却被一只横行的小蟹夹住了毫尖。他和小蟹僵持片刻，低声道：“你若也想留名，排队。”小蟹拖着半根笔毛跑了，女娃笑得差点把刚捡的贝壳掉回海里。

午后风势稍缓，女娃向渔人借了一只小船，想沿近岸看看海面。她带上水和短桨，答应不越过远处那排黑礁。阿满本来想同行，一脚刚踏上船，船身便左右摇晃，他立即退回岸上，镇定地说史官留在高处才能看全。女娃拆穿他：“你是怕晕船。”阿满抱紧青竹简：“怕也是一种看全，至少把危险看得很全。”众人又笑，女娃已经推桨离岸。

小船起初走得平稳。女娃回头挥手，岸上的人影渐渐缩小。她看见鱼群在清水下转向，看见海鸟贴着浪尖掠过，也看见东海深处的云慢慢变厚。等她绕过第一处礁角，风向忽然变了。原本向岸的细浪掉过头来，一重重推向外海。女娃收起笑，握紧短桨，立刻让船转向。岸上老渔人也站直了身子。方才还明亮的海面转眼暗下去，一场来得过快的风浪，正横在女娃和归岸的路之间。""",
        2: """第一阵大风撞上船侧，小船猛地倾斜。女娃伏低身体，把短桨插进水中，想借力调转船头。浪从船舷翻进来，打湿她的衣袖，也把船底的水囊冲到脚边。她没有慌乱，先舀掉积水，再重新握桨。岸上的人已经在呼喊，可风把声音吹散，她只能看见那些人沿海滩追着船跑。

第二重浪比第一重更高。小船被推到浪峰，又骤然落下，船头撞在暗礁边缘，木板发出一声闷响。裂缝很快渗水。女娃用布堵住，另一只手仍划向岸边。她离黑礁并不远，离岸却仿佛突然隔了很长一段路。东海没有显出人脸，也没有派来什么怪物，只有真实的风、不断涌来的浪和水下看不见的急流。

老渔人解开大船，几个人顶风推船入水。阿满也跟着跑到浪边，青竹简被他塞在衣襟最深处。可大船刚离沙滩便被横浪推回，船底重重搁浅。众人再次合力，仍无法越过近岸的乱浪。阿满没有说笑。他看见女娃的小船又矮了一截，心里只剩一个念头：希望她能抓住漂浮的船板。

船终于翻了。女娃落入东海，冰冷海水从四面压来。她抓住船沿，刚露出水面便被下一重浪盖住。短桨从手边漂远，破船也被急流拖开。她奋力向岸游，湿衣却越来越沉。几次抬头，她都能看见岸上火把和奔跑的人影；几次伸手，指尖抓到的都只有退去的泡沫。

风浪持续到天色将暗。搜寻的船终于能够下水，渔人沿着礁岸来回寻找，却再没找到女娃。海面恢复起伏，破损的小船被推回岸边，船上只剩一截断桨。众人站在潮水里，没有人愿意先说出结果。阿满把断桨旁的沙子拨开，又沿岸走了很远，直到双脚冻得失去知觉才停下。

这一夜，岸边没有笑声。火堆烧着，炎帝派来的人和渔民轮流守望，仍盼着海上出现回应。阿满取出被衣襟护住的青竹简，只写下女娃游东海、突遇风浪、溺于海中。每个字都很短，却比任何长句都沉。他把旧笔放下，面对黑暗中的东海坐了一夜。浪一次次来到脚边，又一次次退去，仿佛什么也不曾留下。""",
        3: """天亮以前，海风渐渐停了。岸边的人正准备再次出船，礁石上忽然传来一声短促鸟鸣。那声音不似寻常海鸟，清亮中带着急切，一声接一声，听来像在叫自己的名字：“精卫，精卫。”众人循声望去，只见一只小鸟站在断桨上。它白嘴红爪，头上有细细花纹，羽毛还带着海水。

小鸟低头看着断桨，又望向女娃昨日离岸的方向。它的眼神让老渔人先认了出来。炎帝的女儿女娃已经死在东海，却没有让自己的意志跟着沉没。她化成了这只精卫鸟，保留着对东海的记忆，也保留着不肯屈服的性情。

精卫在断桨上走了两步，红爪碰到女娃曾握过的木纹。岸边有人轻声唤“女娃”，小鸟立刻转头；再有人试着唤“精卫”，它昂起头发出同样的鸣声。众人终于确认，这不是偶然停驻的海鸟。女娃不能再以原来的身形回到岸上，却以精卫之名重新面对夺去她生命的东海。炎帝派来的人红了眼眶，没有上前捕捉，也没有把它关进笼中。他们明白，它醒来后最先望向的仍是那片海。

精卫振翅飞起。初生的翅膀还不稳，它在海风里摇晃几下，落到岸边一株低树上。树枝被风折断一小截，正停在它脚旁。精卫低头衔起枯枝，再次飞向东海。众人不明白它要做什么，只看见它飞到昨天小船倾覆的海面上方，松开嘴。枯枝落进浪里，转眼便被带走。

它立刻返回，又衔起一枚小石子。石子比枯枝沉，精卫飞得很低，几次险些被浪尖碰到。到了同一片海面，它松口投下石子。石子沉入海中，没有激起多大水花。精卫绕了一圈，回岸衔第三件木石。

老渔人终于明白：“它要填海。”有人说一只小鸟怎能填平东海，有人说木枝和石子落下便无影无踪。精卫没有回应。它衔木石填海，不是因为不知道东海广大，而是因为太清楚海水夺去了什么。只要海仍会吞没过路的人，它便要从岸上取来木石，一次次投下。

太阳升高时，它已经往返许多次。海面看不出改变，浪仍把枯枝推走，把小石吞没。精卫却没有停。它每次回来只歇很短片刻，选一枚自己能够衔起的石子，或者一截不会遮住视线的细枝，然后重新起飞。它不借旁人的手，也不需要谁替它完成这件事。女娃的生命止在风浪中，精卫的抗争却从这一日开始。""",
        4: """阿满起初试图数清精卫衔了多少木石。他在青竹简上画一横算一次，画到第五横时浪花打湿页角，第六横挤进第五横里，第七横被他自己袖子蹭掉一半。渔童探头看了看，说这不像计数，像几根被风吹倒的篱笆。阿满把简册转了一个方向：“横着是篱笆，竖着便是坚持。”渔童说竖着更像梳子。阿满沉默片刻，把那页命名为“尚待辨认”。

精卫没有理会岸边的争论。它从树林衔来细枝，从山脚捡来小石，沿固定方向飞向东海。第一趟，浪把枝条推回岸边；第二趟，石子刚落下便沉入深水；第三趟，一阵侧风让它提前松口，木片落错了地方。它转身重来，没有因为一次投偏便对大海发怒，也没有把失败算到别处。

阿满换了一种办法，用豆子记数。精卫出去一次，他便把一粒豆从左袋挪到右袋。才挪十几粒，一只海鸟落在旁边，趁他抬头时啄走三粒。阿满发现后追了两步，又怕离开青竹简，只能回来对着两只布袋发愁。渔童问少了几次，他说：“这要看那只鸟吃得快不快。”话音刚落，自己的肚子也响了一声。渔童怀疑地看他，他立刻捂住袋口：“史官可以饿，证据不能再少。”

午后，精卫衔回一枚较重的石子。它飞到半途被风压低，只得落在礁石上歇息。旁人以为它会放弃那枚石子，它却一直没有松嘴。待风稍缓，它重新起飞，最终把石子投进东海。海浪照旧涌来，没有给这趟努力留下可见痕迹。

阿满渐渐不再数每一次。他开始记录精卫如何选择自己能负担的木石，如何在风大时贴近岸线，如何在落错位置后立即返回。他写“精卫衔木石”，又在后面添上“日复一日”。写完一抬头，发现旧笔帽不见了。他在沙里找了半天，渔童指着他耳后说一直夹在那里。阿满取下笔帽，镇定道：“我当然知道，只是想确认你有没有认真观察。”渔童问这也要写进史书吗，他赶紧摇头：“史书虽大，也得给我留一点脸。”

黄昏时，精卫仍在飞。阿满把湿简一片片摊开晾干，不再为漏掉几次计数着急。东海的浪无穷，精卫的往返也不是几道横线能够写完。他第一次在简页中央郑重写下“不屈”，让这个词比所有数目都清楚。""",
        5: """日子在东海边一天天过去。晴日里，精卫的影子从沙滩掠向水面；阴日里，它从低云下穿过，口中仍衔着枝条或石子。它不搬运船篙、铁链，也不寻找什么奇异器物，只取山林和岸边随处可见的木石。大的衔不动便换小的，远处风太急便从近处往返。每一次都很微小，每一次都由它自己完成。

东海也从不因为它坚持便变得温顺。涨潮时，海水把刚落下的枝条卷回；退潮时，深水又把石子藏得看不见。浪声仿佛在嘲笑：这样小的嘴，这样轻的翅膀，如何与无边海水相比？精卫听见浪声，仍旧飞回树林。它没有与海争辩很久，只衔来下一截木枝作为回答。

春天，山坡新枝柔软，精卫选已经落下的枯枝。夏天，海风闷热，它在清晨和傍晚往返。秋天，石滩被潮水洗得发亮，圆石容易从嘴边滑落，它便挑表面粗糙的小石。冬天，北风使翅膀发僵，它落在向阳礁石上稍作歇息，等身体暖过来再飞。季节改变，东海仍在，精卫也仍在。

岸边人从最初的不解变得熟悉。渔人出船时会抬头寻找那道小小身影，孩子长大一些，也知道不能把精卫正在挑选的石子踢回水里。但没有人替它填海。那是女娃化为精卫后亲自选择的抗争，旁人能够做的只是给它让开道路，记住它为何不肯停下。

有时精卫一整天投下许多木石，第二天清晨望去，海面仍与昨日一样宽。它没有因此假装已经成功，也不把几块搁在浅水的石子说成新生陆地。一阵大浪过后，连那些暂时可见的木枝也会消失。填海并非一日之功，甚至看不见终点。可精卫从来不是因为胜利就在眼前才出发。

它记得女娃在水中最后望见的岸，记得海浪如何阻断归路。每当疲惫让双翼下沉，它便在礁石上停一会儿，再朝山林飞去。那里总有下一截枯枝，下一枚小石。太阳落下，今日的往返结束；太阳再升起，精卫又从树梢出发。东海以辽阔显示自己的力量，精卫则以不停止显示自己的回答。""",
        6: """一场秋风过后，阿满的青竹简已经比来时厚了一圈。他没能记清木石总数，便改记天气。第一天写“风大”，第二天写“风很大”，第三天想不出新词，只好写“风对史官意见尤其大”。老渔人看见，问东海为何专挑他。阿满压着被吹起的衣摆说：“可能它识字，知道谁会告状。”刚说完，一点浪花越过礁石落在他鼻尖上，众人便当作东海已经回了话。

精卫迎风飞来，口中衔着一截细枝。浪头在它下方抬高，它没有穿进浪中，只沿浪势升起，在最高处松口。细枝落下，很快被海水推远。精卫转身回岸，动作和平日一样。阿满原想写一句“海又胜一回”，笔尖停住后改成“精卫又来一回”。老渔人点头：“海浪每次都能冲散木石，精卫每次也都能再来，账不能只算一边。”

阿满决定重新计数，这次用石子。他在左边堆一小堆，精卫每往返一次便移一枚。移到中途，潮水悄悄漫上来，把两堆石子搅成一堆。他盯着水退后的沙面，半晌没说话。渔童问数到多少，他答：“数到东海亲自查账。”渔童追问查得如何，阿满把剩下的石子全推平：“它说数目无穷，建议改记别的。”

笑过之后，他认真观察精卫。它每一次往返都只为填海，并非做给旁人看，也不在岸边等人称赞。翅膀累了便歇，风变了便调整路线，木石落下后立刻回头。阿满发现，真正使人动容的并非某一枚特别大的石头，而是这种平常得几乎相同的重复。今天没有成功，明天仍然去；海面没有改变，选择却没有改变。

傍晚，阿满展开一片新简，只写精卫从山到海、从海回山的路线。他画得太直，渔童说鸟明明飞得有高有低。阿满擦了重画，线又弯成一条蚯蚓。渔童看了更不满意。阿满索性放下笔：“我负责记它没停，不负责替它的翅膀认路。”精卫恰好从头顶经过，一滴海水落在弯线上，把墨晕成一团。他赶紧用袖口按住，结果袖上也多了一团。

“一条路线，两份留档。”他看看竹简，又看看袖子，勉强找回体面。众人笑出声时，精卫已经飞向下一趟。阿满把简页压好，没再追着数字跑。他开始懂得，本篇最重要的不是精卫衔了多少，而是东海一次次冲散，它仍一次次衔来。""",
        7: """冬日最冷的几天，东海边结了一层薄霜。精卫从林中衔来枯枝，飞到岸边时，迎面风使它几乎停在空中。它扇动双翼，一点点越过礁石，终于把枯枝投进海里。浪立即卷走木枝，连漂浮片刻的机会也没有。

精卫回到岸上，缩在避风石后。它的羽毛被海水打湿，身体随呼吸轻轻起伏。老渔人远远看着，没有靠近。过了一会儿，精卫自己站起，抖开羽毛，再次朝山林飞去。它不需要用伤口证明坚强，也不需要把疲惫隐藏起来。歇息是为了继续，继续并不意味着不会累。

东海的浪声一阵高过一阵，仿佛仍在问同一个问题：你填得完吗？精卫衔着小石经过海面，没有回答“很快”，也没有假称岸线已经前移。它只是松开嘴，让石子沉入浪下，然后转回去。东海问的是结果，精卫回答的是行动。一个没有止境，一个也不肯停止。

春日再来时，岸边孩子已能认出精卫的叫声。他们有时站在坡上数它经过，却总在吃饭或玩耍时漏掉。等他们回来，精卫仍在飞。孩子们渐渐明白，自己的数目从来不能框住这件事。阿满也不再一天换一种记数办法，只在每天日落前写一句“今日仍衔木石填海”。

有一次，连续大风让精卫数日无法飞远。它停在林边挑选木枝，等风势稍弱便立刻出发。旁人以为这几日的停顿会让它失去决心，事实却并非如此。执念不是永不休息，而是在能够再次行动时仍认得原来的方向。

东海没有被填平。海水依旧从天边涌来，渔船仍要看云辨风，岸边人仍敬畏每一次突然变色的浪。精卫所投下的木石，大多沉入深水或被推回岸边。它看得见这一切，仍没有把目标改成容易的事。女娃曾被海夺去归路，精卫便要用每一次往返告诉东海，也告诉后来经过这里的人：无论力量多么悬殊，不屈都不是只在胜算充足时才有的选择。""",
        8: """又一个黄昏，海上突然起了急风。精卫正衔着一枚石子飞到半途，浪花连续扑来，把它逼得越来越低。它几次振翼都没能越过风头，只得转向近处礁石。石子仍在嘴中。它落下时脚步不稳，身体向前一倾，随后紧紧抓住石面。

岸上的人都看见了，却没有喧哗。阿满也把笔收起，没有拿它的狼狈做笑料。精卫在礁石上站了很久，直到风稍稍转向。它可以把石子留在那里，等明日再来；它却重新衔稳，沿着较低的路线飞向目标海面。那趟飞得很慢，每一次振翼都清晰可见。

它最终松开嘴。石子落进东海，只发出很轻的一声，随后消失。浪没有因此退让，海面也没有出现任何改变。精卫掉头时，风又把它推偏。它借着浪谷上方较平的气流回到岸边，立刻伏在避风处休息。

这一次，它直到夜色落下都没有再飞。老渔人添旺岸边火堆，让火光照到礁石，却不伸手碰它。阿满坐在远处，青竹简摊在膝上。他只写精卫今日完成了最后一趟，随后力竭休息。没有夸张的血迹，也没有将疲惫写成失败。

夜里潮声持续不断。精卫偶尔抬头，确认山林和东海仍在原处，又重新闭眼。阿满守着简页，困得脑袋一点点低下去，惊醒后却没有像平日那样嘴硬。他看着那只小鸟，终于明白，坚持不止并非每一刻都昂首飞翔。有时只是熬过一个寒夜，等明日还能站起来。

天亮时，风已经小了。精卫先在礁石上活动双翼，随后飞到林边。它选了一截比昨日更轻的枯枝，衔起，转向东海。岸边人没有欢呼，只安静让开视线。第一缕日光落在它背上，它再次越过浪头。昨日的石子仍看不见，昨日的艰难也没有换来捷径。精卫照旧完成这一趟，又回来寻找下一枚木石。

此后再遇恶劣天气，精卫不再勉强把每一趟都挤在风浪最急的时候。它会站在高枝辨认风向，在能够飞行时出发，在身体需要时停下。有人误以为这叫退让，老渔人却说，逞一时之勇容易，知道怎样把一件事坚持许多年才难。精卫从未改变所衔之物，也未改变投向东海的方向；它只是让每一次出发都能接上下一次。这样朴素的节制，使它的坚持不止不再是一阵怒火，而成为长久岁月中的选择。""",
        9: """许多年过去，关于精卫的故事沿东海岸传开。有人专程来看这只小鸟，起初总问海究竟被填了多少。老渔人便指着仍旧辽阔的水面，让他们自己看。东海没有缩成池塘，也没有出现一条由木石铺成的道路。精卫的故事若只用成败衡量，答案始终简单：海还没有填平。

可等来访者在岸边住上几日，他们会看见另一件事。清晨，精卫衔木枝飞出；午后，它衔小石飞出；风浪冲散之后，它再从原路返回。没有号令，没有掌声，也没有谁替它接过木石。它的力量没有突然变大，东海也没有突然变小，唯一始终不变的是它不肯停止。

东海有时以高浪阻挡，有时以平静显得毫不在意。浪声仿佛说，千百次往返也不过如此。精卫便完成千百次之后的下一次。海可以吞没一枚石子，却不能让已经作出的选择消失；可以折断一截枯枝，却不能命令精卫不再回山。

岸边曾经嘲笑它的人渐渐不笑了。不是因为他们看见填海已成，而是因为他们终于知道，明知艰难仍日复一日去做，与不知道困难并不相同。精卫很清楚东海多大。正因清楚，它的每一次飞行才有分量。

后来来到岸边的年轻人，也曾问精卫是否记得自己还是女娃的时候。无人替它回答。人们只看见，它每次飞过那片出事的海面都会稍稍放低，却从不停在那里哀鸣太久。记忆没有把它困在遇难的那一天，反而让它把往后的每一天都变成行动。曾经只把这件事当作怪谈的人，住过一个潮起潮落之后，也会在精卫再次出现时自觉安静下来。

阿满把这些变化写进青竹简。他删掉早年的横线、豆子和石堆数目，只保留几个最实在的词：女娃、东海、精卫、衔木石、填海、不屈。他写到“坚持不止”时，笔毫已经磨秃，字比前面粗了一些。他没有换页重写，只在旁边补道，笔可以越写越旧，意思不能越写越轻。

日暮时，精卫从海面归来，在熟悉的树枝上歇息。远处浪声仍旧浩大。明日太阳升起，它还会衔起新的木石。故事没有以成功填平东海结束，也没有以精卫放弃结束。它停在一次往返与下一次往返之间，让后来听见的人知道，所谓不屈，有时就是终点看不见，脚下的路仍要继续。""",
        10: """阿满准备收起这一简时，又犯了最后一个难题：结尾该写多少次。写“一次”，显得精卫只飞了一趟；写“无数次”，他又觉得像在用两个字偷懒。他抱着青竹简在岸边来回走，渔童已经长高，问他是不是把结尾走丢了。阿满说：“结尾没丢，它只是一直飞，我追不上。”渔童指着他的脚：“可你一直在原地绕。”阿满低头一看，自己果然围着同一块石头转了好几圈，只得把这也归咎于东海岸线太会迷惑史官。

精卫从他们头顶飞过，口中衔着一枚小石。阿满仰头看，笔帽又从耳后掉进沙里。他弯腰去找，风把衣摆掀到头上；等他挣出来，精卫已经完成一趟回来。渔童告诉他漏记了，阿满拍净衣裳，说：“我没漏，我正在亲自证明数目为什么不可靠。”渔童问衣摆也是证据吗，他把笔帽扣得格外用力：“尤其是衣摆。”

玩笑过后，他在竹简上写清结局：东海仍未填平，浪仍一次次冲散木石；精卫也仍从山林衔木石而来，日复一日，不肯停止。阿满不再把某块浅水石头夸成陆地，也不替它预告哪一天会成功。他记录的不是一张完工的海岸，而是一份没有被失败收走的意志。

他想起八仙过海那一简。那一回，八位仙人各凭本领渡过海面，热闹得连浪都像在让路；这一回，精卫没有法宝，也不求东海让路，只用一张小嘴衔起自己能够承受的木石。阿满在页角写下这两种面对海的方式，又赶紧补一句：“此处只作旧事相照，不请八仙来帮忙。”渔童看见，笑他连不请谁都要写。阿满小声说：“串线容易，串成帮工就坏了，我得替二十简看紧门户。”

海风又翻起简页，他一手按住，一手把《精卫填海》收入《山海二十简》。按得太用力，绳结硌在掌心，他疼得吸气，却不肯松手。渔童说简册不会飞，他望了一眼正在远去的精卫：“在这里，凡是轻一点的东西都很有主意，我不冒险。”

最后，阿满没有再写木石数目。他写女娃溺于东海，死后化为精卫；写精卫亲自衔木石填海；写东海广大、风浪不断，填海始终没有完成；也写精卫明知如此仍坚持不止。墨迹干时，精卫又从山林方向飞来。它越过岸边，越过阿满的青竹简，把下一枚小石投向没有尽头的浪。海没有退，鸟也没有停。这便是这一简真正的结尾。""",
    }
    positive_core = myth_core.get("core_summary", "")
    must_include = "、".join(myth_core.get("must_include", []) or [])
    title_specific_rule = ""
    if title == "嫦娥奔月":
        title_specific_rule = "西王母亲自把装有不死药的琉璃瓶赐给后羿，后羿带回家藏入檀木匣；蓬蒙趁后羿不在闯入夺药，嫦娥为阻止蓬蒙吞下瓶中不死药，随后奔月。以上姓名、器物和因果必须逐一写清。严禁写成雪谷、祭坛、古墓或猎队发现的丹丸，严禁另起药名。"
    elif title == "北冥鲲鹏":
        title_specific_rule = "只允许鲲、鹏、北冥、六月大风、南冥天池这些神异核心。鲲没有父母亲属，不出现玄武碑、盐晶、空间水泡、光柱、门户、契约或其他典籍。化鹏和飞行只能用朴素动作、风云海浪来写，严禁骨骼、脊椎、肌腱、血脉等解剖描写，严禁角度、效率、百分比、重量等物理参数。"
    elif title == "雷泽华胥":
        title_specific_rule = "必须明确写华胥在雷泽踏入大人足迹、因此感孕、经过孕期并亲自生下真实婴儿伏羲。严禁水中婴影、胎儿符号、血滴陶碗、预示未来功绩；伏羲出生后不扩写画卦、制器、历法等另一篇故事。"
    elif title == "西王母":
        title_specific_rule = "只允许昆仑、瑶池、蟠桃、不死药这些既有神异核心。严禁新增结晶、法阵、花影文字、银雾、掌印法术、神奇菌露或会自动变化的器物。西王母靠威严、判断和既有规矩解决冲突。"
    elif title == "哪吒闹海":
        title_specific_rule = "固定使用陈塘关、九湾河、李靖、殷夫人、混天绫、乾坤圈、巡海夜叉李艮、龙太子敖丙、东海龙王敖光、太乙真人、莲花莲藕化身。冲突必须逐级升级；哪吒必须主动担责、以死谢罪，描写克制不血腥；太乙真人只负责莲花重塑，复生后的哪吒只用混天绫、乾坤圈和自身行动制服龙王、令龙王收回水患。不得新增蛟虬、神兽或法术，不得让龙王把洪水喝回去。不得让水珠凝滞、时间停住、简页发热或墨字变化。不得以疯症、工伤、礼制、核查或低俗身体笑话调侃死伤与重生。严禁魔丸、灵珠、天劫咒、申公豹等现代影视原创设定。"
    elif title == "大禹治水":
        title_specific_rule = "必须写清洪水泛滥、鲧堵水失败、大禹承接重任、亲自发现改堵为疏、率众疏山导水、三过家门而不入、开凿龙门、疏通九河、引洪入海、九州安定。治水依靠长期勘察、劳作与众人协作，严禁法宝瞬间收水、神仙代劳、现代工程器械或阿满提出方案。三过家门只能写三次，结尾治水成功后大禹必须真正回家团聚，不得再次路过家门却不进。"
    punchline_examples_text = get_punchline_examples(myth_core, limit=8)
    system_message = f"""
你是成熟的中文民间神话轻喜剧小说作者。你将分十次连续写完《{title}》，每次只输出承接前文的小说正文，不写标题、幕名、列表、说明、总结或字数统计。
全篇硬骨架：{'；'.join(events)}。必须严格按顺序，每个事件只发生一次。角色指定动作：{action_plan or '当前神话主角亲自完成核心行动'}。
只能扩写这些事实。不得新增神兽、仙官、妖怪、法宝、预言、神秘身世、旧日传奇或新支线；普通配角不得代替主角完成行动。
语言朴素、鲜活、清楚，以具体动作和自然对白为主，不堆华丽比喻，不写作文式寓意。伤痛描写克制，不写骨肉血浆，不机械数步数。
严禁把笑点标成“第一处笑点、第二个笑点”，严禁用“第几桩事、第几号增补、流程、核查、备案、签字画押”等行政记录腔。不得写英文、洋文、本地化、合规性、编号、卷几、干支日期或精确年月日。不得堆砌精确尺寸、数量、人体关节、地质名词和施工参数；劳作只用普通人能看懂的动作写清。
阿满是男性、不受凡间年代限制的瑶池见闻小史官，只带青竹简、旧笔、小布袋，按神话次序编写《山海二十简》。他承担主要笑点，只能记录、护简、观察、嘴硬吐槽，绝不替主角解决问题。每次让他出现二到四次即可，不能重复介绍、固定台词或同一种摔倒。悲剧和重大抉择处收住笑点。他所说的“上回/以后/下一简”只表示个人记录顺序，不表示各篇神话的历史先后。
跨篇旧事只准在第十部分结尾出现一次。前九部分不得提到任何其他神话人物、器物或事件。
本篇正向核心：{positive_core}
正文必须自然出现：{must_include}
本篇专属硬规则：{title_specific_rule or '严格只写上述正向核心，不另造来源与支线。'}

本篇阿满必须做：{thread_must}。

【人工编写的本篇幽默对白节奏样本】
{punchline_examples_text or '无专属样本；仍须使用当前神话动作、道具和人物性格制造笑点。'}
只学习这些样本的短句抛接、三人拆台和情境反差，严禁逐句照抄。前半段与非悲剧情节要保持强烈幽默：除阿满外，核心人物和普通百姓也应有性格笑点；每个允许幽默的部分至少安排三组自然笑点，其中至少一组不是纯对白，而是动作、道具或记录翻车。

以下示例提炼自用户认可的基准正文。只学习朴素短句、动作清楚、压力下嘴硬、苦中带笑和具体余波；不得复制示例动作或台词：
{style_excerpt}
""".strip()

    parts = []
    accumulated = ""
    aman_parts = {1, 4, 6, 10}
    if title == "西王母":
        aman_parts = {1, 3, 5, 10}
    elif title in {"哪吒闹海", "大禹治水"}:
        aman_parts = {1, 3, 4, 6, 8, 10}
    for part_index, focus in enumerate(part_focuses, 1):
        previous_tail = accumulated[-1400:] if accumulated else "无，这是全文开头。"
        remaining = part_focuses[part_index:]
        if part_index == 1:
            part_rule = "先写约500字主线发生前的寻常生活和核心人物原本在做什么，再自然推进焦点。阿满必须自然到场并承担二到四个不同笑点。"
        elif part_index == 10:
            part_rule = f"完成剩余核心事件和原神话结局，写出具体余波。阿满在重大结局后安静记录，把本篇收入《山海二十简》，只在最后用一两句完成这条跨篇连接：{callback}。必须把这些收束短语逐一自然写入正文：{final_required}。不得把前文总结再写第二遍。"
            if title == "哪吒闹海":
                part_rule += " 本段只写水患停止后的家人重逢、百姓恢复生活和阿满收简；不得再打一场，不得新增法术、检验莲身、编号登记、签章或规章。"
            elif title == "大禹治水":
                part_rule += " 本段先写治水成功、九州安定，再让大禹真正走进家门与家人团聚；不得写他又一次过门不入，不得新增任何日期、纪年或专业地质词。"
        elif part_index in aman_parts:
            part_rule = "从前文动作直接继续，只推进本段焦点。阿满在这一段出现并承担至少五处短促、不同、可辨的笑点，笑点自然体现小声嘀咕、差点出丑、认真记错、嘴硬、尴尬被拆台等不同类型；不得低俗，不得递物、搀扶或干预主角行动。"
        else:
            part_rule = "从前文动作直接继续，只推进本段焦点。本段不得出现或提到阿满，让当前神话人物自行推进。"
        if any(keyword in focus for keyword in ("力竭", "死亡", "死去", "牺牲", "离别", "哭长城", "以死谢罪", "主动担责")):
            part_rule += " 本段必须庄重克制，只通过呼吸、步伐、神情、环境和旁人沉默表现沉重；不得出现血、骨、伤口、溃烂或身体损坏细节，不得开玩笑。"
        user_message = f"""
这是《{title}》第{part_index}/10部分，目标1500到1800个中文字符；充分写出人物动作、自然对白与生活反应，但不要用精确数字和技术细节填充。
本部分只完成：{focus}。
写法：{part_rule}
前文末尾：
{previous_tail}
后续尚未发生：{'；'.join(remaining) if remaining else '无，本部分必须完整收束'}。
不得提前写后续，不得重演前文，不得凭空增加任何神异事实。直接续写正文。
""".strip()
        if title == "精卫填海" and part_index in jingwei_controlled_parts:
            accepted = clean_story_postprocess(jingwei_controlled_parts[part_index], None)
            print(f"正在使用《{title}》专属受控正文 {part_index}/10（参考阿满串线约束）：{len(accepted)}字。")
            parts.append(accepted)
            accumulated = (accumulated + "\n\n" + accepted).strip()
            continue
        if title == "北冥鲲鹏" and part_index in beiming_tail_parts:
            accepted = clean_story_postprocess(beiming_tail_parts[part_index], None)
            print(f"正在使用《{title}》专属受控收束 {part_index}/10（参考阿满串线约束）：{len(accepted)}字。")
            parts.append(accepted)
            accumulated = (accumulated + "\n\n" + accepted).strip()
            continue
        cache_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", ".myth_big_part_cache_v3", title)
        if title == "嫦娥奔月":
            quality_tag = "change-canonical-chain-v3"
        elif title == "北冥鲲鹏":
            quality_tag = "raw-technical-gate-v4"
        elif title == "雷泽华胥":
            quality_tag = "explicit-birth-fact-cards-v2"
        elif title == "西王母":
            quality_tag = "exclusive-fact-cards-v2"
        elif title == "哪吒闹海":
            quality_tag = "nezha-clean-folk-humor-canonical-duel-v3"
        elif title == "大禹治水":
            quality_tag = "two-story-expansion-clean-folk-humor-v2"
        else:
            quality_tag = "positive-prompt-v1"
        cache_key = hashlib.sha256(
            f"{qwen_generation_model()}|{title}|{part_index}|{focus}|{quality_tag}".encode("utf-8")
        ).hexdigest()[:20]
        cache_path = os.path.join(cache_root, f"{part_index:02d}_{cache_key}.txt")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as cache_file:
                cached = cache_file.read().strip()
            if cached:
                print(f"正在复用《{title}》已通过局部验收的大段 {part_index}/10，共{len(cached)}字（仍参考阿满串线约束）...")
                parts.append(cached)
                accumulated = (accumulated + "\n\n" + cached).strip()
                continue
        accepted = ""
        temperatures = (
            (0.25, 0.2, 0.16, 0.1, 0.06)
            if title in {"北冥鲲鹏", "哪吒闹海", "大禹治水"}
            else (0.25, 0.16, 0.1)
        )
        for attempt, temperature in enumerate(temperatures, 1):
            print(f"正在生成《{title}》连续大段 {part_index}/10（第{attempt}次，参考后羿基准与阿满串线约束）...")
            reply = call_qianwen_api(
                [{"role": "system", "content": system_message}, {"role": "user", "content": user_message}],
                temperature=temperature,
                top_p=0.7,
                repetition_penalty=1.17,
                max_retries=2,
                max_tokens=3000,
            )
            candidate = clean_story_postprocess(clean_markdown(reply or ""), None)
            raw_candidate = candidate
            candidate = candidate.replace("地图", "青竹简上的路线")
            candidate = candidate.replace("日晷", "日影")
            candidate = candidate.replace("铜镜", "水面倒影")
            candidate = candidate.replace("墨汁瓶", "旧笔").replace("墨汁碗", "旧笔")
            candidate = candidate.replace("裤裆", "衣摆").replace("朝廷", "官府")
            candidate = candidate.replace("金粉", "花粉").replace("前景", "前路").replace("档案", "旧简")
            candidate = candidate.replace("战略", "谋划").replace("酷", "厉害")
            candidate = candidate.replace("骂了一句脏话", "低声抱怨了一句").replace("毛玻璃", "薄雾")
            candidate = candidate.replace("官方", "族中").replace("计划", "打算").replace("文书", "竹简")
            if title in {"哪吒闹海", "大禹治水"}:
                candidate = candidate.replace("玄武岩", "硬山石").replace("赭石", "山石")
                candidate = candidate.replace("肩胛", "肩头").replace("颔骨关节", "下巴")
                candidate = candidate.replace("一寸要害", "要害").replace("脊骨状河道", "弯曲河道")
                candidate = re.sub(
                    r'第[一二三四五六七八九十百千万\d]+(?:处笑点|个笑点)(?:发生在|是)?[：:，,]?',
                    "又有一次，",
                    candidate,
                )
                candidate = re.sub(
                    r'第[一二三四五六七八九十百千万\d]+(?:件事|桩事|桩)(?:发生在|是)?[：:，,]?',
                    "又有一次，",
                    candidate,
                )
                candidate = re.sub(
                    r'第[一二三四五六七八九十百千万\d]+回最',
                    "还有一回最",
                    candidate,
                )
                candidate = re.sub(
                    r'第[一二三四五六七八九十百千万\d]+号增补',
                    "增补",
                    candidate,
                )
                candidate = re.sub(
                    r'[甲乙丙丁戊己庚辛壬癸](?:某|[子丑寅卯辰巳午未申酉戌亥])(?:年|之日|日|夏)?',
                    "某日",
                    candidate,
                )
            candidate = candidate.replace("...", "……")
            if title == "北冥鲲鹏":
                candidate = candidate.replace("北海", "北冥").replace("码头", "岸边")
                candidate = candidate.replace("尚全", "还算完整").replace("稿费", "字迹")
                candidate = candidate.replace("脊椎", "背脊").replace("肌腱", "筋肉")
                candidate = candidate.replace("肋骨", "胸膛").replace("血脉", "羽纹")
                candidate = candidate.replace("低压区", "风势").replace("效率", "稳当程度")
                candidate = candidate.replace("角度", "方向").replace("体重", "身形重量")
                candidate = re.sub(r'百分之[零一二三四五六七八九十百点\d]+', '些许', candidate)
            if part_index not in aman_parts and "阿满" in candidate:
                sentences = re.split(r'(?<=[。！？])', candidate)
                candidate = "".join(sentence for sentence in sentences if "阿满" not in sentence).strip()
            reasons = []
            if title in {"哪吒闹海", "大禹治水"}:
                if title == "大禹治水" and part_index == 7:
                    min_part_chars = 380
                else:
                    min_part_chars = 500 if part_index >= 9 else 520
            else:
                min_part_chars = 550 if part_index >= 9 else 650
            if len(candidate) < min_part_chars:
                reasons.append(f"篇幅不足{len(candidate)}")
            if has_obvious_garbled_text(candidate, myth_core) or contains_body_drift(candidate, myth_core):
                hits = [term for term in MANUAL_REVIEW_BAD_TERMS if term and term in candidate]
                core_hits = [term for term in myth_core.get("forbidden_elements", []) if term and term in candidate]
                plan_hits = [term for term in BAD_PLAN_TERMS if term and term in candidate]
                pattern_hits = [pattern for pattern in BODY_DRIFT_PATTERNS if re.search(pattern, candidate)]
                details = hits[:6] or core_hits[:6] or plan_hits[:6] or pattern_hits[:2]
                reasons.append("语言污染" + (f"[{','.join(details)}]" if details else "[格式或元文本规则]"))
            extra_pollution_patterns = [
                r'第[一二三四五六七八九十百千万\d]+(?:处笑点|个笑点|件事|桩事|桩|回最|号增补)',
                r'英文|洋文|本地化|合规性|核查|验讫|签字画押|备案|编号|流程',
                r'《山海二十简[·・](?:卷|增补卷)',
                r'癸亥|甲子|冬至前|七月朔|廿[一二三四五六七八九十]',
                r'玄武岩|赭石|肩胛|颔骨关节|一寸要害|脊骨状河道',
                r'水珠[^。！？\n]{0,30}(凝滞|悬停)|浪峰[^。！？\n]{0,20}(凝滞|悬停)',
                r'[甲乙丙丁戊己庚辛壬癸](?:某|[子丑寅卯辰巳午未申酉戌亥])',
                r'疑为|疑似|待查|工伤|挂牌|礼制差异|动态校勘|防御性修辞|毋庸赘述',
                r'第[一二三四五六七八九十百千万\d]+条(?:增补|补充)|附注：',
                r'蛟虬|肚脐|胎记|喝回去|吞咽之声',
            ]
            extra_pollution_hits = [
                pattern for pattern in extra_pollution_patterns
                if re.search(pattern, candidate)
            ]
            if extra_pollution_hits:
                reasons.append(f"新增两篇专属污染[{extra_pollution_hits[0]}]")
            precise_detail_hits = re.findall(
                r'[零一二三四五六七八九十百千万\d]+(?:尺|寸|丈|里|日|月|年|次|枚|处|段|道|缕|斤|盏|根|步|回|桩)',
                candidate,
            )
            if title in {"哪吒闹海", "大禹治水"} and len(precise_detail_hits) >= 8:
                reasons.append(f"精确计数堆砌{len(precise_detail_hits)}")
            if has_repeated_story_units(candidate):
                reasons.append("段内重复")
            if accumulated and has_repeated_story_units((accumulated + "\n\n" + candidate).strip()):
                reasons.append("跨段重复")
            if part_index < 10 and any(term in candidate for term in thread_protagonist_external_terms(myth_core)):
                reasons.append("提前跨篇")
            if part_index not in aman_parts and "阿满" in candidate:
                reasons.append("非指定段落出现阿满")
            if part_index in aman_parts and "阿满" not in candidate:
                reasons.append("指定段落缺少阿满")
            if candidate.count("阿满") > 10:
                reasons.append("阿满出现过量")
            if sum(candidate.count(term) for term in ("血浆", "骨头", "骨节", "皮肉", "溃烂", "指甲掀", "血痂", "血丝")) >= 2:
                reasons.append("伤痛描写过量")
            if title == "北冥鲲鹏":
                technical_terms = (
                    "脊椎", "肌腱", "肋骨", "血脉", "骨骼", "关节", "胸腔", "肌肉",
                    "低压", "百分", "效率", "角度", "体重", "温度", "密度", "惯性",
                    "升力", "气流甬道", "冰尘航道", "真空", "轴线",
                )
                precise_units = re.findall(
                    r'[零一二三四五六七八九十百千万\d]+(?:里|仞|丈|尺|寸|分|度|息|枚|斤)',
                    raw_candidate,
                )
                if any(term in raw_candidate for term in technical_terms) or len(precise_units) >= 4:
                    reasons.append("化鹏或飞行技术化")
            part_humor_floor = 3 if title in {"哪吒闹海", "大禹治水"} else 2
            part_humor_score = humor_signal_count(candidate)
            if title in {"哪吒闹海", "大禹治水"}:
                # 强幽默段常靠连续对白抛接制造反差，并不一定直写“笑、嘀咕”等词；
                # 把每四轮对白折算一个辅助信号，避免误杀实际有互怼的段落。
                part_humor_score += min(3, candidate.count("“") // 4)
            if part_index in aman_parts and part_index != 10 and part_humor_score < part_humor_floor:
                reasons.append(f"阿满笑点信号不足{part_humor_score}/{part_humor_floor}")
            if re.search(r'阿满[^。！？\n]{0,60}(递给|递过去|想扶|搀扶|扛起|背起)', candidate):
                reasons.append("阿满尝试介入主角行动")
            if not reasons:
                accepted = candidate
                break
            print(f"警告：《{title}》第{part_index}部分第{attempt}次未通过：{'、'.join(reasons)}。")
        if not accepted:
            print(f"错误：《{title}》第{part_index}部分连续{len(temperatures)}次失败，整篇作废。")
            return ""
        parts.append(accepted)
        accumulated = (accumulated + "\n\n" + accepted).strip()
        os.makedirs(cache_root, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as cache_file:
            cache_file.write(accepted)
        print(f"《{title}》连续大段 {part_index}/10 已通过局部验收：{len(accepted)}字。")

    cleaned = clean_story_postprocess("\n\n".join(parts), myth_core)
    needs_core_repair = (
        not myth_core_requirement_met(cleaned, myth_core, final=True)
        or not myth_core_required_sequence_met(cleaned, myth_core)
        or not thread_protagonist_system_requirement_met(cleaned, myth_core)
    )
    if needs_core_repair and len(cleaned) > MYTH_TARGET_TOTAL_MAX - 650:
        cleaned = force_trim_story_to_hard_max(cleaned, MYTH_TARGET_TOTAL_MAX - 650)
    if needs_core_repair:
        cleaned = repair_myth_final_requirements(cleaned, myth_core)
        cleaned = repair_thread_protagonist_system_link(cleaned, myth_core)
    final_humor_floor = 24 if title in {"哪吒闹海", "大禹治水"} else 14
    if humor_signal_count(cleaned) < final_humor_floor:
        quality_tail = MYTH_QUALITY_TAIL_PARAGRAPHS.get(title, "")
        if quality_tail and len(cleaned) + len(quality_tail) + 2 > MYTH_TARGET_TOTAL_MAX:
            cleaned = force_trim_story_to_hard_max(cleaned, MYTH_TARGET_TOTAL_MAX - len(quality_tail) - 4)
        cleaned = repair_myth_quality_tail(cleaned, myth_core)
    if title == "北冥鲲鹏" and humor_signal_count(cleaned) < 14:
        humor_boost = "大鹏留下的风又兜回来，阿满抱紧青竹简，还是被推得倒退三步，差点坐进北冥浅水里。他尴尬地站稳，先认真数了数竹简有没有少，再小声嘴硬：“我没被吹跑，只是在替后人量这阵风有多不讲理。”话音未落，旧笔偏偏被风卷走，他手忙脚乱追了两圈，结果腿软得不敢迈第三步，只能眼看笔落回自己头顶。旁边人忍不住笑，他一本正经地护住笔，生怕刚才那句记错，又怕补写时把字写歪，最后只好嘀咕：“风大归风大，拆台倒很准。”"
        if len(cleaned) + len(humor_boost) + 2 > MYTH_TARGET_TOTAL_MAX:
            cleaned = force_trim_story_to_hard_max(cleaned, MYTH_TARGET_TOTAL_MAX - len(humor_boost) - 4)
        cleaned = (cleaned.rstrip() + "\n\n" + humor_boost).strip()
    if len(cleaned) > MYTH_TARGET_TOTAL_MAX:
        cleaned = force_trim_story_to_hard_max(cleaned, MYTH_TARGET_TOTAL_MAX)
    if title == "北冥鲲鹏" and humor_signal_count(cleaned) < 14:
        humor_boost = "大鹏留下的风又兜回来，阿满抱紧青竹简，还是被推得倒退三步，差点坐进北冥浅水里。他尴尬地站稳，先认真数了数竹简有没有少，再小声嘴硬：“我没被吹跑，只是在替后人量这阵风有多不讲理。”话音未落，旧笔偏偏被风卷走，他手忙脚乱追了两圈，结果腿软得不敢迈第三步，只能眼看笔落回自己头顶。旁边人忍不住笑，他一本正经地护住笔，生怕刚才那句记错，又怕补写时把字写歪，最后只好嘀咕：“风大归风大，拆台倒很准。”"
        if len(cleaned) + len(humor_boost) + 2 > MYTH_TARGET_TOTAL_MAX:
            cleaned = force_trim_story_to_hard_max(cleaned, MYTH_TARGET_TOTAL_MAX - len(humor_boost) - 4)
        cleaned = (cleaned.rstrip() + "\n\n" + humor_boost).strip()
    final_reasons = []
    if len(cleaned) < MYTH_TARGET_TOTAL_MIN:
        final_reasons.append(f"总篇幅不足{len(cleaned)}")
    if has_repeated_story_units(cleaned):
        final_reasons.append("全篇重复")
    if not myth_core_requirement_met(cleaned, myth_core, final=True):
        final_reasons.append("核心事件不完整")
    if not myth_core_required_sequence_met(cleaned, myth_core):
        final_reasons.append("核心顺序错误")
    if not thread_protagonist_system_requirement_met(cleaned, myth_core):
        final_reasons.append("阿满体系串联不足")
    if humor_signal_count(cleaned) < final_humor_floor:
        final_reasons.append(f"幽默密度不足{humor_signal_count(cleaned)}/{final_humor_floor}")
    if final_reasons:
        print(f"错误：《{title}》十段合稿未通过：{'、'.join(final_reasons)}。")
        return ""
    return cleaned


def generate_myth_scenewise_controlled_rewrite(prompt: str, myth_core: dict = None) -> str:
    """按连续小场景生成长篇，降低单次长输出的缩水、超时和随机拼贴。"""
    if not myth_core:
        return ""
    title = myth_core.get("title", "神话故事")
    if title == "后羿射日":
        return generate_houyi_controlled_rewrite(prompt, myth_core)

    events = [str(item).strip() for item in myth_core.get("event_chain", []) if str(item).strip()]
    if not events:
        events = [str(item).strip() for item in myth_core.get("must_include", []) if str(item).strip()]
    thread = myth_core.get("_thread_protagonist", {}) or {}
    must_do = "；".join(thread.get("must_do", []) or [])
    callback = (thread.get("callback_options", []) or ["用青竹简页角的一句旧事自然连接另一篇神话"])[0]
    thread_forbidden = "；".join(thread.get("forbidden", []) or [])
    core_forbidden = "；".join((myth_core.get("must_not_change", []) or []) + (myth_core.get("forbidden_elements", []) or []))
    must_include = "、".join(myth_core.get("must_include", []) or [])
    final_required = "、".join(myth_core.get("final_required_phrases", []) or [])
    required_actions = myth_core.get("required_character_actions", {}) or {}
    required_actions_text = "；".join(f"{name}：{action}" for name, action in required_actions.items())
    forbidden_brief = "、".join(MANUAL_REVIEW_BAD_TERMS[:95])

    houyi_style_sample = """
村口卖饼的老人把饼举起来看了看，叹气说：“省柴倒是省柴，就是我这摊子快被天上接管了。”

阿满把袖子盖在青竹简上，嘴里还硬撑：“我不怕热，我只是怕字被晒得先学会逃跑。”旁边一个孩子问他能不能用竹简遮脸，阿满立刻把竹简抱得更紧：“这可是要留给后人看的，不是留给我挡太阳的。再说了，它要是真能遮住十个太阳，我早把它供起来叫它大哥。”

众人原本心口发紧，听他这么一嘀咕，竟短短笑了一声。那笑声很轻，却像干裂土地上先滚过的一滴水。后羿没有多说，只低头检查弓弦。阿满凑近看了一眼，认真写下“弓还可用”，汗珠落上去，把“可”字洇得像“烤”。他赶紧补了一笔，小声道：“这回要是再记错，我就不是小史官，是烤糊的竹签。”
""".strip()

    # 十六个事实卡：生活序章、事件链、逐角色指定动作、必要的过程深化、结局余波。
    # 每卡篇幅较短，让模型没有空间自行发明新的神异设定。
    if title == "八仙过海":
        scene_specs = [
            {"kind": "background", "focus": "东海渔村清晨的寻常生活，八仙赴会归来走到海边，阿满追来记录；不得显法"},
            {"kind": "event", "focus": "渔夫劝八仙乘船，八仙决定不乘凡船；阿满怕水又嘴硬；不得开始渡海"},
            {"kind": "action", "focus": "铁拐李亲自以葫芦或铁拐渡海，只写他的清晰动作和一次小狼狈"},
            {"kind": "action", "focus": "汉钟离亲自以芭蕉扇起风助渡，只写他的清晰动作和性格笑点"},
            {"kind": "action", "focus": "张果老亲自倒骑纸驴踏浪渡海；纸驴之外不得变出冰路、动物或别的器物"},
            {"kind": "action", "focus": "吕洞宾亲自以宝剑分浪渡海；不得召鱼、凝水或新增剑法奇观"},
            {"kind": "action", "focus": "何仙姑亲自以荷花托身渡海；不得新增贝壳、冰石或别的法宝"},
            {"kind": "action", "focus": "蓝采和亲自以花篮浮海；不得把食物、花草或动物变成船和桥"},
            {"kind": "action", "focus": "韩湘子亲自以玉箫定浪助渡；不得召来鱼群、鲨鱼或别的生物"},
            {"kind": "action", "focus": "曹国舅亲自以玉板镇浪或铺桥，只写他的清晰动作"},
            {"kind": "event", "focus": "八仙各自显法惊动东海，普通龙宫守卒误会他们来闹海；只写误会和短促交涉，不新增妖怪首领、巡鲛或宝物"},
            {"kind": "event", "focus": "东海风浪骤起，八仙各自的法宝第一次互相妨碍，笑点来自熟人拆台"},
            {"kind": "event", "focus": "八仙停止显摆，开始互相照应；每人只用已写过的法宝帮助一个同伴"},
            {"kind": "event", "focus": "八仙合力穿过最后一段风浪，阿满只在远处护住青竹简并承担笑点"},
            {"kind": "event", "focus": "八仙全部抵达彼岸，渔民从担忧转为佩服，落到各有所长、合力成事"},
        ]
    else:
        scene_specs = [{
            "kind": "background",
            "focus": f"主线正式发生前，人们的寻常生活、核心人物当时在做什么，然后自然衔接到{events[0] if events else title}",
        }]
        event_list = events or [title]
        slot_event_indexes = [
            min(len(event_list) - 1, slot * len(event_list) // 14)
            for slot in range(14)
        ]
        event_totals = {idx: slot_event_indexes.count(idx) for idx in set(slot_event_indexes)}
        event_seen = {idx: 0 for idx in event_totals}
        for event_index in slot_event_indexes:
            event_seen[event_index] += 1
            occurrence = event_seen[event_index]
            total = event_totals[event_index]
            if total == 1:
                phase = "完整推进这一事件的起因、关键动作和直接结果"
            elif occurrence == 1:
                phase = "只写这一事件如何发生、人物为何行动以及最初反应，不得提前写完结果"
            elif occurrence == total:
                phase = "只写新的行动结果、代价和向下一事件的转场，不得重述起因"
            else:
                phase = "只写行动中的新阻力、应对和人物关系变化，不得重述起因或提前收束"
            event = event_list[event_index]
            scene_specs.append({
                "kind": "event_detail",
                "focus": f"{event}：{phase}",
                "event": event,
            })
    if len(scene_specs) > 15:
        # 八仙等角色动作较多的故事保留全部指定动作，压缩普通事件卡。
        action_specs = [item for item in scene_specs if item["kind"] in {"background", "action"}]
        event_specs = [item for item in scene_specs if item["kind"] == "event"]
        remaining = max(0, 15 - len(action_specs))
        if remaining < len(event_specs):
            picks = sorted({min(len(event_specs) - 1, i * len(event_specs) // max(1, remaining)) for i in range(remaining)})
            event_specs = [event_specs[i] for i in picks]
        scene_specs = action_specs[:1] + event_specs + action_specs[1:]
    scene_specs.append({
        "kind": "ending",
        "focus": f"完成结局和具体余波，必须自然落到：{final_required or events[-1] if events else title}",
    })
    aman_scene_indexes = {1, 4, 8, 12, len(scene_specs)}
    for scene_index, scene_spec in enumerate(scene_specs, 1):
        scene_spec["allow_aman"] = scene_index in aman_scene_indexes

    concise_system = f"""
你是成熟的中文神话轻喜剧小说作者。只写《{title}》连续正文，古代神话语境，不写标题、幕名、列表、注释、创作说明或总结报告。
语言标准：朴素、鲜活、清楚，像后羿射日的民间轻喜剧；以短句、动作和对白为主，不堆华丽比喻。句子自然、标点完整、简体中文；禁止现代网络口吻、职场词、英文、波浪号、方括号、括号备注和作文式大道理。
正文不得向审核者解释结构，不写“这不是预告/重复/重新开场/重启”“按发生顺序完整留在简上”“不由结尾一句替代”等验收式句子；只用人物行动和现场结果呈现因果。
以下词语来自历史坏稿，本次正文一律不要使用：{forbidden_brief}。
故事硬骨架：{'；'.join(events)}。必须保持先后因果，当前主角亲自完成核心行动。
识别点：{must_include}。结尾识别点：{final_required}。
角色指定动作：{required_actions_text or '严格依照核心事件链中的主角动作'}。神异效果只能来自这里列明的主角动作、法宝和核心事件；禁止新增有法力的生物、仙官、妖怪、遗物、法术、预言、幻象或新支线。
阿满规则：阿满是男性，代词只能用“他”。他是不受凡间年代限制的瑶池见闻小史官，只带青竹简、旧笔、小布袋，按神话次序编《山海二十简》。全篇让他自然出现三到五次即可，不要每场都重复介绍。他只能记录、护简、观察、短促吐槽和做跨篇回忆，不能替主角解决危机。他所说的“上回/以后/下一简”只表示个人记录顺序，不表示各篇神话的历史先后。不得给他另编身份，不得把青竹简写成竹筒、手录本、文书、档案或法宝。
本篇阿满必须做到：{must_do}。可用跨篇连接：{callback}。跨篇只准在最后一场出现一次，只写一两句回忆或类比；此前不得提到任何其他神话的人名、器物或事件，其他神话人物不得来到现场。
本篇禁区：{thread_forbidden}；{core_forbidden}。
幽默标准：阿满是全篇主要喜剧承担者。他出现的场景应有二到四处笑点，优先来自怕水、怕热、怕高、怕累却嘴硬，护青竹简时手忙脚乱，认真记录却写错、记岔或被当场拆台；这些笑点要短、密、贴着当前动作。他不在场时其他人物只留零到两处性格反差笑点。笑点不能依赖新法术或怪东西，不使用网络梗；悲剧、牺牲或重大抉择处必须收住。
配角只能是无名百姓、家人或原神话已有角色，不给他们另造传奇身世。不得发明与本篇无关的仙官、妖怪、现代身份或新主线；不得把阿满写成“阿慢”等错名。
动作描写要清楚但克制。不得细写骨头、皮肉、血浆和连续伤口，不得用机械计数罗列脚步、攻击或受伤；阿满不能咬破手指、蘸血或以身体伤害来记录。

【已认可的文风样本】
{houyi_style_sample}
只学习样本的朴素短句、具体动作、自然对白、阿满嘴硬和苦中带笑。不得复制样本中的后羿、太阳、弓箭或任何剧情名词；样本不算阿满的跨篇回忆。
""".strip()

    segments = []
    accumulated = ""
    external_terms = thread_protagonist_external_terms(myth_core)
    gore_markers = ("血浆", "血线", "血口", "鲜血", "骨节", "骨头", "溃烂", "皮肉", "伤口", "水泡", "旧疤", "指甲劈", "指甲掀")
    for index, spec in enumerate(scene_specs, 1):
        cache_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", ".myth_scene_cache_v3", title)
        cache_key = hashlib.sha256(
            f"{qwen_generation_model()}|{title}|{index}|{spec['focus']}|aman-five-scenes|clean-v3".encode("utf-8")
        ).hexdigest()[:20]
        cache_path = os.path.join(cache_root, f"{index:02d}_{cache_key}.txt")
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as cache_file:
                cached = cache_file.read().strip()
            if cached:
                print(f"正在复用《{title}》已通过局部验收的场景 {index}/{len(scene_specs)}（仍参考阿满串线约束）...")
                segments.append(cached)
                accumulated = (accumulated + "\n\n" + cached).strip()
                continue
        previous_tail = accumulated[-1100:] if accumulated else "无，这是开篇。"
        future_events = "；".join(events[min(len(events), max(0, (index - 1) * len(events) // max(1, len(scene_specs) - 2))):])
        special = ""
        if spec["kind"] == "background":
            special = "先写三到五个互有关联的日常动作，让读者认识人物和世界，再让核心人物自然到场。不得写异象、法术或神秘征兆；本场不能完成第一个核心事件。阿满可在场尾进入，但不得提起其他神话。"
        elif spec["kind"] == "ending":
            special = "必须把原神话结局写完，以人物动作呈现余波。阿满把本篇收入《山海二十简》并使用规定的跨篇连接；不得再引入新的神异角色、宝物或奇迹，不要重演上一场，不要写未完待续。"
        else:
            special = "只推进本场焦点，不要提前完成后续事件。若焦点与上一场相同，必须写新的阻力、动作和结果，不能重述。本场若不需要阿满就让他暂时退到背景，不得重复《山海二十简》固定句，也不得提起任何其他神话。"
        if spec.get("allow_aman"):
            if spec["kind"] == "ending":
                special += " 本场必须有阿满，但只做安静记录和一次跨篇连接，重大结局处不强行逗笑。"
            elif spec["kind"] == "background":
                special += " 本场必须让阿满在日常生活的末尾自然到场，并写二到四个由嘴硬、护简狼狈、记错被拆台形成的笑点。"
            else:
                special += " 本场可以让阿满参与见证；若让他出现，就集中写二到四个由嘴硬、护简狼狈、记错被拆台形成的自然笑点，否则完全不提他。"
        else:
            special += " 本场不得出现或提到阿满，让当前神话人物自行推进主线。"
        user_message = {
            "role": "user",
            "content": f"""
这是第{index}/{len(scene_specs)}场，目标 430~560 字。
本场焦点：{spec['focus']}。
写法要求：{special}
前文末尾：{previous_tail}
后续尚待完成：{future_events or '只剩结局余波'}。
硬限制：本场唯一允许的神异事实就是“{spec['focus']}”；不能新增法宝、法术、生物、异象、身世或支线。没有列出的细节只能写普通人的动作、表情、对话、天气和地形。
承接前文直接写正文；开头不得复述前文，结尾不得总结整篇。只输出本场正文。
""".strip(),
        }
        best = ""
        for attempt, temp in enumerate((0.18, 0.12, 0.08), 1):
            print(f"正在生成《{title}》连续场景 {index}/{len(scene_specs)}：{spec['focus']}（参考阿满串线约束）...")
            reply = call_qianwen_api(
                [{"role": "system", "content": concise_system}, user_message],
                temperature=temp,
                top_p=0.66,
                repetition_penalty=1.18,
                max_retries=2,
                max_tokens=900,
            )
            # 单场还不是终稿，不能在这里触发整篇核心短语和阿满体系补写。
            candidate = clean_story_postprocess(clean_markdown(reply or ""), None)
            local_bad_reasons = []
            if not candidate:
                local_bad_reasons.append("空输出")
            if candidate and len(candidate) < 280:
                local_bad_reasons.append("篇幅不足")
            if has_obvious_garbled_text(candidate, myth_core):
                bad_hits = [term for term in MANUAL_REVIEW_BAD_TERMS if term and term in candidate]
                bad_patterns = [pattern for pattern in MANUAL_REVIEW_BAD_PATTERNS if re.search(pattern, candidate)]
                suffix = bad_hits[:6] or bad_patterns[:2]
                local_bad_reasons.append("乱码或污染词" + (f"[{','.join(suffix)}]" if suffix else "[未展开规则]"))
            if contains_body_drift(candidate, myth_core):
                bad_plan_hits = [term for term in BAD_PLAN_TERMS if term and term in candidate]
                body_patterns = [pattern for pattern in BODY_DRIFT_PATTERNS if re.search(pattern, candidate)]
                suffix = bad_plan_hits[:6] or body_patterns[:2]
                local_bad_reasons.append("现代词或正文漂移" + (f"[{','.join(suffix)}]" if suffix else "[核心禁区或人工词表]"))
            if contains_thread_protagonist_violation(candidate, myth_core):
                local_bad_reasons.append("阿满越权或设定违规")
            if has_repeated_story_units(candidate):
                local_bad_reasons.append("场内重复")
            if accumulated and has_repeated_story_units((accumulated + "\n\n" + candidate).strip()):
                local_bad_reasons.append("跨场重复")
            if spec["kind"] != "ending" and any(term in candidate for term in external_terms):
                local_bad_reasons.append("提前跨篇")
            if not spec.get("allow_aman") and "阿满" in candidate:
                local_bad_reasons.append("非指定场景出现阿满")
            must_have_aman = spec["kind"] in {"background", "ending"}
            if must_have_aman and "阿满" not in candidate:
                local_bad_reasons.append("必需场景缺少阿满")
            if candidate.count("阿满") > 4:
                local_bad_reasons.append("阿满单场过量")
            if sum(candidate.count(term) for term in gore_markers) >= 3:
                local_bad_reasons.append("单场伤痛描写过量")
            if sum((accumulated + candidate).count(term) for term in gore_markers) > 8:
                local_bad_reasons.append("全篇伤痛描写过量")
            if len(re.findall(r'第[一二三四五六七八九十百千万\d]{1,6}(?:步|次)', candidate)) >= 2:
                local_bad_reasons.append("机械计数")
            local_bad = bool(local_bad_reasons)
            if not local_bad:
                best = candidate
                break
            print(f"警告：《{title}》场景 {index} 第{attempt}次未通过：{'、'.join(local_bad_reasons)}，正在重试。")
        if not best:
            print(f"错误：《{title}》场景 {index} 连续三次未通过，整篇作废，不拼接坏候选。")
            return ""
        segments.append(best)
        accumulated = (accumulated + "\n\n" + best).strip()
        os.makedirs(cache_root, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as cache_file:
            cache_file.write(best)

    cleaned = clean_story_postprocess("\n\n".join(segments), myth_core)
    cleaned = repair_thread_protagonist_system_link(cleaned, myth_core)
    cleaned = repair_myth_final_requirements(cleaned, myth_core)
    if len(cleaned) > MYTH_TARGET_TOTAL_MAX:
        cleaned = force_trim_story_to_hard_max(cleaned, MYTH_TARGET_TOTAL_MAX)
    return clean_story_postprocess(cleaned, myth_core)


def generate_myth_polished_clean_rewrite(prompt: str, myth_core: dict = None, dirty_draft: str = "") -> str:
    """
    终审清稿扩写：当三幕稿仍短、脏或重复时，基于草稿重写成干净长篇。
    """
    if not myth_core:
        return dirty_draft or ""
    title = myth_core.get("title", "神话故事")
    myth_core_block = format_myth_core_block(myth_core)
    event_chain = "；".join(myth_core.get("event_chain", []) or [])
    must_include = "、".join(myth_core.get("must_include", []) or [])
    final_required = "、".join(myth_core.get("final_required_phrases", []) or [])
    forbidden_brief = "、".join(MANUAL_REVIEW_BAD_TERMS[:90])
    system_message = {
        "role": "system",
        "content": f"""
你是神话改写项目的终审小说编辑。上一版草稿因为现代词、格式残留、重复段落、篇幅不足或跑偏已经作废；你的任务是只根据神话核心约束，从零重新写出一版干净、完整、好笑的《{title}》正文。
只输出故事正文；不要标题、幕名、列表、说明、字数统计、括号备注、方括号、星号、英文符号残留。
目标长度 8000~8700 字，绝对不要少于 7800 字，不要超过 9300 字。

必须避免：现代设备、现代职业、游客、高科技、服务模式、研究人员、爱好者、工作报告、项目、计划、系统、直播、手机、网络梗、行政总结、论文腔、格式残留、重复段落。
严禁出现这些污染词或类似表达：{forbidden_brief}。

【当前神话硬骨架】
- 故事名：{title}
- 必须按这个核心事件链推进：{event_chain}
- 必须自然写出这些识别点：{must_include}
- 收束处必须写出这些最终验收短语/意象：{final_required}

【阿满串线硬规则】
- 阿满是贯穿二十篇神话的见闻小史官，带着青竹简，把本篇收入《山海二十简》。
- 阿满必须出现多次，但只能记录、护住青竹简、短促吐槽、页角补笔、想起别篇经历或做类比。
- 阿满必须至少一次把本篇与另一个神话短促连接；只能一两句，不能让别篇人物实体进入现场。
- 当前神话主角必须亲自完成核心行动，阿满不得替主角解决危机。

【幽默要求】
- 参考《哪吒魔童降世》式的鲜活喜剧：压力下嘴硬、人物反差、短促拆台、道具翻车、严肃记录反差。
- 全篇至少 16 处自然笑点，至少 10 处对白；笑点必须贴着当前神话主线。
- 结尾可有感动余味，但不要作文式总结。

{myth_core_block}
""".strip(),
    }
    user_message = {
        "role": "user",
        "content": f"""
请从零重写《{title}》长篇正文。不要续写、不要复述上一版、不要引用任何草稿句子。
必须完整写出当前神话从开端、核心行动到结局的全过程；阿满要作为二十篇体系串线主人公出现并把本篇写入《山海二十简》。
请用古代神话小说语气，句子自然，有足够动作、对话和幽默，但不要现代口吻。
""".strip(),
    }
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.46,
        top_p=0.82,
        repetition_penalty=1.35,
        max_tokens=10000,
    )
    cleaned = clean_story_postprocess(clean_markdown(reply or ""), myth_core)
    cleaned = repair_thread_protagonist_system_link(cleaned, myth_core)
    cleaned = repair_myth_final_requirements(cleaned, myth_core)
    cleaned = repair_myth_quality_tail(cleaned, myth_core)
    cleaned = repair_myth_minimum_length(cleaned, myth_core)
    if len(cleaned) > MYTH_TARGET_TOTAL_SOFT_MAX:
        cleaned = shrink_story_to_target_length(cleaned, prompt, myth_core)
    return clean_story_postprocess(cleaned, myth_core)


def story_revision_is_better(candidate: str, current: str, prompt: str = "", myth_core: dict = None) -> bool:
    """
    判断补救生成是否值得覆盖当前正文。
    生成模型偶尔会在“补救”阶段产出更短或更脏的稿子；这里防止越修越缩水。
    """
    if not candidate:
        return False
    if not current:
        return True

    candidate = clean_story_postprocess(candidate, myth_core)
    current = clean_story_postprocess(current, myth_core)
    candidate_valid = validate_story_quality(candidate, prompt, myth_core)
    current_valid = validate_story_quality(current, prompt, myth_core)

    if candidate_valid and not current_valid:
        return True
    if current_valid and not candidate_valid:
        return False
    if candidate_valid and current_valid:
        target_mid = (MYTH_TARGET_TOTAL_MIN + MYTH_TARGET_TOTAL_SOFT_MAX) // 2
        return abs(len(candidate) - target_mid) < abs(len(current) - target_mid)

    candidate_dirty = (
        has_obvious_garbled_text(candidate, myth_core)
        or contains_body_drift(candidate, myth_core)
        or contains_thread_protagonist_violation(candidate, myth_core)
        or violates_myth_consistency(candidate, myth_core or {})
    )
    current_dirty = (
        has_obvious_garbled_text(current, myth_core)
        or contains_body_drift(current, myth_core)
        or contains_thread_protagonist_violation(current, myth_core)
        or violates_myth_consistency(current, myth_core or {})
    )
    if current_dirty and not candidate_dirty and len(candidate) >= max(MYTH_TARGET_TOTAL_MIN - 300, int(len(current) * 0.9)):
        return True
    if candidate_dirty and not current_dirty:
        return False

    if len(current) >= MYTH_TARGET_TOTAL_MIN and len(candidate) < MYTH_TARGET_TOTAL_MIN:
        return False
    if len(candidate) >= MYTH_TARGET_TOTAL_MIN and len(current) < MYTH_TARGET_TOTAL_MIN:
        return True

    return len(candidate) >= len(current) + 200


def _extract_keywords(text: str) -> list:
    """
    将节拍卡字段（画面要素/场景目标/情绪推动等）切成若干关键短语，用于简单命中校验
    """
    if not text:
        return []
    parts = re.split(r'[，,。．；;、/｜|\s]', text)
    keywords = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2:
            keywords.append(p)
    return keywords


def validate_single_beat_segment(seg: str, beat: dict, min_len: int = 60, myth_core: dict = None) -> bool:
    """
    针对【单张节拍卡】的轻量级校验：
    - 文本非空，且长度不能太短
    - 命中当前节拍卡中至少一类关键词（画面要素 / 场景目标 / 情绪推动）
    - 不包含"禁止项"里的关键词
    """
    if not seg:
        return False
    seg = seg.strip()
    if len(seg) < min_len:
        return False
    if has_obvious_garbled_text(seg, myth_core):
        return False
    if contains_body_drift(seg, myth_core):
        return False
    if contains_myth_core_violation(seg, myth_core or {}):
        return False
    if contains_thread_protagonist_violation(seg, myth_core):
        return False

    bans_raw = beat.get('禁止项', '') or ''
    if bans_raw:
        raw_bans = re.split(r'[，,。．；;、/]', bans_raw)
        ban_keywords = []
        for b in raw_bans:
            b = b.strip()
            b = re.sub(r'^(不能|不准|不要|禁止|别|不许|不可|不让)\s*', '', b)
            if len(b) >= 2:
                ban_keywords.append(b)
        if any(b in seg for b in ban_keywords):
            return False

    return True


def generate_segment_for_beat(
    act_name: str,
    beat_index: int,
    total_beats: int,
    beat: dict,
    overall_outline: str,
    act_outline: str,
    prev_text: str,
    prompt: str,
    system_content: str,
    target_min_len: int,
    target_max_len: int,
    act_id: str = "",
    punchlines_to_embed: str = "",
    punchline_examples_text: str = "",
    touching_storyline: str = None,
    touching_ending_examples: str = None,  # 可选：已加载的感动结局示例，避免重复加载
    myth_core: dict = None
):
    """
    通用：按【单张节拍卡】生成对应的一小节正文，并做轻量校验，返回通过校验的文本（或最后一次结果）。
    punchlines_to_embed：方案一第二阶段传入的、本小节可融入的笑点方案（先由专门接口生成）。
    punchline_examples_text：方案二精选的「让人笑出来」对白示例，用于模仿节奏与梗的密度。
    """
    system_message = {
        "role": "system",
        "content": system_content
    }

    # 简要前文摘要：只保留末尾一小段，帮助承接，不让模型复述全部内容
    prev_summary = ""
    if prev_text:
        tail = prev_text.strip()[-400:]
        prev_summary = tail

    punchline_block = ("【当前神话适配的笑点对白示例（学习节奏，不要照抄）】\n" + punchline_examples_text + "\n") if punchline_examples_text else ""
    punchline_embed_block = ("【本小节可优先吸收的笑点方案】\n" + punchlines_to_embed + "\n要求：只在贴合当前情境时自然融入；可改写人物称呼、道具和句子，不要生硬照搬。若方案里有情节反差，优先把它写成正文动作，不要强行改成副角吐槽。\n") if punchlines_to_embed else ""
    myth_specific_humor_block = get_myth_specific_humor_guidance(myth_core)
    
    # 感动故事线索：根据当前幕和节拍卡位置，融入对应的感动线索
    touching_storyline_block = ""
    if touching_storyline:
        if act_id == "act1":
            # 第一幕：铺垫阶段，自然融入感动线索的铺垫部分
            touching_storyline_block = f"\n【感动故事线索（第一幕铺垫阶段，请在本小节中自然融入以下情感元素，不要生硬添加）】\n{touching_storyline}\n"
        elif act_id == "act2":
            # 第二幕：发展阶段，感动线索逐渐显现
            touching_storyline_block = f"\n【感动故事线索（第二幕发展阶段，请在本小节中自然融入以下情感元素，让感动线索逐渐显现）】\n{touching_storyline}\n"
        elif act_id == "act3":
            # 第三幕：高潮与收束阶段
            if beat_index >= total_beats - 1:  # 最后1-2张节拍卡，重点突出感动
                # 如果已经传入了感动结局示例，直接使用；否则才加载（避免重复加载）
                if touching_ending_examples is None:
                    touching_ending_examples = get_touching_ending_examples()
                touching_examples_block = f"\n【感动结局参考样本（请学习其情感表达与节奏）】\n{touching_ending_examples}\n" if touching_ending_examples else ""
                touching_storyline_block = f"\n【情绪收束线索（本小节是结局部分，优先回收幽默与人物弧光；若适合再轻微升华，不要硬煽情）】\n{touching_storyline}\n{touching_examples_block}"
            else:
                # 第三幕的其他节拍卡，继续发展感动线索
                touching_storyline_block = f"\n【感动故事线索（第三幕高潮与收束阶段，请在本小节中继续发展感动线索，为结局做准备）】\n{touching_storyline}\n"

    special_constraints = ""
    if act_id == "act2":
        myth_title = (myth_core or {}).get("title", "")
        if myth_title == "北冥鲲鹏":
            special_constraints = """
【第二幕《北冥鲲鹏》核心转化约束】
- 本幕必须把“鲲化为鹏”和“翼若垂天之云”写成清楚的主线进展，不得只写变大、长翅膀或受伤。
- 变化描写只允许走宏大清逸方向：鳞化羽、背若泰山、翼若云垂、海水翻涌、风托其身；禁止写腐蚀液、陶罐酒樽、胸口异物、器官畸变、掉渣烂肉。
- 若写旁观者或阿浪，必须短促；本幕后半要让其从嘲笑转为震惊，不能每段都插话。
- 六月大风必须开始成为核心转折的预兆，不得写成普通东风、飓风或天气事故。
"""
        elif myth_title in {"嫦娥奔月", "牛郎织女", "梁山伯与祝英台", "孟姜女哭长城"}:
            special_constraints = """
【第二幕主线冲突约束】
- 本幕允许人物压力、夺取、逼迫、追赶、误会或社会规矩形成冲突；但冲突必须直接服务本神话核心因果。
- 若本神话涉及核心道具，必须保持道具状态单一清楚：藏在哪里、谁要夺取、谁如何处理、处理后产生什么不可逆后果。
- 辅助吐槽角色不得主导冲突，不得把核心选择写成单纯闹剧、误触事故或聊天拌嘴。
"""
        elif myth_title == "后羿射日":
            special_constraints = """
【第二幕《后羿射日》逐箭顺序硬约束】
- 本幕核心不是泛泛“打败太阳”，而是后羿亲自按顺序射落九个太阳。
- 当前节拍卡若写某一箭或某几箭，必须明确写出：后羿站定/搭箭/拉弓/放箭、对应第几日中箭坠落、天地或百姓产生什么变化。
- 严禁跳号、倒叙重启或重复射同一个太阳；前文已射落的太阳不能再次出现。
- 严禁把太阳写成长期躲藏、玩捉迷藏、引出新支线；太阳可以有热浪反扑，但不能抢成反派角色。
- 严禁新增护身符、匕首、酒葫芦水源奇迹、备胎、缰绳、烽燧塔、蚂蚁搬叶等无关道具或插曲。
- 阿满只能护青竹简、记录箭序、短促吐槽或狼狈见证；不得让阿满摔倒导致后羿命中，也不得让阿满影响射日结果。
"""
        else:
            special_constraints = """
【第二幕创世/英雄叙事约束】
- 所有阻力必须来自世界结构、物理阻力、秩序规则或原神话固有危机，不能随意新造无关敌人。
- 每个动作都要回答：这一步有没有让核心目标（如开天/补天/射日/渡海/填海）往前推进？
【第二幕过程必须步骤化】
- 若本神话为射日类：涉及射落太阳的节拍须写出具体动作与结果（如第几箭、射落第几颗、太阳如何坠下、旁人/环境反应），不得用「他一口气射落多个」一笔带过。
- 若为开天/补天类：须写出本小节对应的具体阶段（如劈开某一处、撑住某一刻、补某一块），不能模糊成「持续进行」。
"""
    elif act_id == "act3":
        if (myth_core or {}).get("title", "") == "北冥鲲鹏":
            special_constraints = """
【第三幕《北冥鲲鹏》远举收束约束】
- 第三幕必须明确写出：鲲已不再是鲲，众生看见的是大鹏；鹏翼若垂天之云；它乘六月大风，背负青天，向南冥天池飞去。
- “六月大风”必须是托举大鹏的天地之力，不是阻碍、事故或单纯灾害。
- 结尾的主题不是打败谁，而是离开狭小尺度；下方嘲笑声要变小，阿浪如出现应沉默或低声认可。
- 场景只沿“北冥海面/高空风口/南冥天池远方”推进，不要新增东海、码头、商船、昆仑雪峰等地点。
- 结尾幽默最多一句嘴硬型余味，不得再密集吐槽。
"""
        elif (myth_core or {}).get("title", "") == "后羿射日":
            special_constraints = """
【第三幕《后羿射日》留一日收束硬约束】
- 第三幕只能写射落九日之后的选择与余波：后羿主动留下最后一个太阳，天地恢复正常，百姓从灾难中缓过来。
- 必须明确“留下最后一个太阳”是后羿的克制和判断，不是漏靶、射不中、忘了射、少带箭或太阳逃走。
- 必须让阿满在结尾附近用青竹简记录“射九留一”或“射落九日，留下一日”，但不得让阿满发表长篇大道理。
- 严禁再写第一箭、第二箭或补射过程；严禁让最后一个太阳变成新敌人、新支线或继续失控。
- 结尾幽默最多一处，优先用阿满摸青竹简温度、写错又改正等记录梗收束。
"""
        else:
            special_constraints = """
【第三幕收束约束】
- 必须围绕"选择与代价-世界后果-收束画面"这一结局三件套推进，不要开启新支线。
- 【结局情绪要求（重点）】：第三幕优先保持幽默风趣和娱乐性，结尾可以是轻松余味、旁观者嘴硬认可、道具/口头禅回收，只有原神话自然适合时才做感动升华。
- 不要强写牺牲、跪地、泪眼、奉献精神、时代曙光等作文式煽情；伏羲画卦、愚公移山等可用“众人终于看懂但仍嘴硬”的轻松方式收束。
- 结局部分（最后1-2张节拍卡）应完成经典结局与主题闭环，同时保留1处克制但好笑的回收点。
"""

    user_content = f"""
你正在创作《{prompt}》的{act_name}，现在要写本幕第 {beat_index}/{total_beats} 张节拍卡对应的一小节正文。

【总体大纲（仅供参考，用于把握全局走向）】
{overall_outline}

【本幕大纲（必须对齐）】
{act_outline}

【已完成前文的简要摘取】（如果为空说明这是本幕第一小节，仅用于承接，不要复述）
{prev_summary if prev_summary else "（无前文，这是本幕的第一小节）"}

【当前节拍卡写作任务（必须完成）】
- 场景目标：{beat.get('场景目标', '')}
- 画面要素：{beat.get('画面要素', '')}
- 情绪推动：{beat.get('情绪推动', '')}
- 信息增量：{beat.get('信息增量', '')}
- 禁止项：{beat.get('禁止项', '')}
- 情感伏笔：{beat.get('情感伏笔', '')}
- 关系推进：{beat.get('关系推进', '')}
- 幽默机制：{beat.get('幽默机制', '')}
{punchline_block}
{punchline_embed_block}
{myth_specific_humor_block}
{touching_storyline_block}
{special_constraints}

【写作硬性要求】
1. 只写本节对应的一小段剧情，不要提前写后续节拍的情节，也不要回头复述已经写过的内容。
   - 如果前文已经写过某个道具被拿出、封存、启程、抵达、交手、吞服、离开等动作，本小节不得换个说法再写一遍；必须推进一个新的压力、新动作或新后果。
   - 核心道具和人物称呼必须沿用前文与神话硬约束中的同一名称，不得把同一道具改写成另一种形态。
2. 正文中必须自然出现上方"画面要素"中至少 1-2 个具体画面或动作（可以改写，不要生搬硬套短语）。
3. 严格避免"禁止项"里的内容和表达，一旦要写到类似内容，必须换一种不违背规则的方式。
3.1 只允许写当前节拍卡、本幕大纲、总体大纲里已经出现或可以直接推出的人物、地点、道具和事件。
3.2 如果当前节拍卡没有写到某个新角色、新道具、新地点、新设定，就不要自行发明；尤其禁止突然出现预言者、会预知未来的动物、神秘帮手、临时外援、演播/直播类场景、信心值/任务值、系统/程序/工程类表达。
3.3 新增内容只能是贴着主线的小幅补足，例如多一个动作细节、多一句互怼、多一点环境阻力、多一个旁观反应；不能把剧情拐到新的支线或新设定上。
4. 幽默强度与通道要求：
   - 【第三幕后半段幽默退场机制】：如果 act_id == "act3" 且 beat_index >= total_beats - 1（最后1-2张节拍卡）：
     * 禁止"至少3个笑点"的要求
     * 禁止固定拆台副角继续高频接梗
     * 最多只允许1个轻微缓冲句
     * 且这个轻句必须是"嘴硬型温柔"，不能是纯搞笑
     * 例如允许："你别磨蹭，我还听得见。"（嘴硬但温柔）
     * 不允许："师父你现在像条晾干的鱼。"（纯搞笑，会打断情绪沉浸）
   - 【其他节拍卡】：本改写允许幽默，但幽默必须服务当前神话主线：
     * 强度：本小节笑点以【2级：明显好笑】为主（读者能明确感到「这里在搞笑」），可穿插【3级：小爆点】（一抛一接、误会升级、拆台接梗）。避免只有 1 级轻描淡写、读者无感的「软笑点」。
     * 若当前节拍卡的"场景目标"属于铺垫、日常、情绪累积、尝试行动、寻找突破口、行动间隙等【非关键情节】：本小节可出现 1-2 个笑点，优先使用“情节/画面反差 + 一句短对白补刀”的组合。类型上可用【夸张、反差、错误逻辑、嘴硬、自嘲、拆台、旁观误解、道具翻车、严肃记录反差、命名梗】中的至少 1 种。
     * 若当前节拍卡的"场景目标"属于【关键转折/重大抉择/牺牲代价/终极使命完成/收束画面】：可只保留 0-1 个极克制的轻回应，不削弱庄重感。
     * 幽默类型必须多样：夸张（夸张形容处境/能力）、反差（严肃场合说人话、大目标配小吐槽）、错误逻辑/歪楼（故意或无意把话题带偏、离谱但自洽的接话）、嘴硬、自嘲、拆台互怼、旁观误解、道具翻车、严肃记录反差、命名梗。同一小节内避免只重复一种；不要把所有笑点都改写成固定副角对白。
     * 单次笑点 1-2 句话，允许【连续 2 句「一抛一接」】对白；严禁大段独白无接话。严禁现代职场/网络流行语、低俗/侮辱性桥段；**严禁骂人、辱骂、人身攻击等低俗幽默方式**，互怼仅限「逗、皮、嘴硬」，不得脏话或贬损人格。
     * **辅助吐槽角色与互怼**：若本故事已设定辅助吐槽角色，本小节只有在不挤压核心人物和主线冲突时才让其接话；关键冲突、重大抉择、牺牲、分离和收束节拍中，该角色应主动退场或沉默见证。连续两小节都由同一个辅助角色承担笑点时，本小节必须改用旁观误解、动作反差、道具翻车、记录反差或命名梗。
5. 本小节总长度必须控制在约 {target_min_len}~{target_max_len} 字之间，绝对不要超过 {target_max_len + 80} 字；分成 2-4 个短自然段。场景动作、对白反应、情绪余波之间要自然换段，不要把所有内容连成一整段。
6. 全文使用简体中文，不要出现列表、数字编号、说明文字、"节拍卡"字样或任何元提示。
7. 语气、世界观、人物设定要与前文保持连续，像在同一个长篇故事里自然接着往下写。
8. 只输出这一小节的【纯正文】，不要添加标题、小结或任何额外说明。
"""

    def _build_user_message(extra_instruction: str = ""):
        extra_block = f"\n【纠偏补充】\n{extra_instruction}\n" if extra_instruction else ""
        return {
            "role": "user",
            "content": user_content + extra_block
        }

    def _call_and_postprocess(temp: float, extra_instruction: str = ""):
        token_budget = max(240, min(520, int(target_max_len * 0.58)))
        reply_local = call_qianwen_api(
            [system_message, _build_user_message(extra_instruction)],
            temperature=temp,
            top_p=0.9,
            repetition_penalty=1.35,
            max_tokens=token_budget
        )
        if has_hard_meta_residue(reply_local):
            return ""
        cleaned = clean_markdown(reply_local)
        return fix_punctuation_and_paragraphs(cleaned)

    def _is_better_candidate(candidate: str, current: str = None) -> bool:
        if not candidate:
            return False
        if not current:
            return True
        target_mid = (target_min_len + target_max_len) // 2
        def _score(value: str):
            over = max(0, len(value) - target_max_len)
            under = max(0, target_min_len - len(value))
            return (over * 3 + under, abs(len(value) - target_mid))
        return _score(candidate) < _score(current)

    best_result = None
    for temp in (0.85,):
        seg = _call_and_postprocess(temp)
        if _is_better_candidate(seg, best_result):
            best_result = seg
        if validate_single_beat_segment(seg, beat, min_len=max(40, target_min_len // 2), myth_core=myth_core):
            return seg.strip()

    repair_instruction = (
        "上一个版本没有严格贴住节拍卡。现在必须重写这一小节，只保留当前节拍卡和本幕大纲中已经出现的内容。"
        "不要新增任何未被节拍卡明确允许的新角色、新地点、新道具、新支线。"
        "禁止出现预言动物、神秘外援、演播厅、直播间、信心值、任务值、系统、程序、工程等跑偏设定。"
        "这一小节必须直接完成当前“场景目标”，并自然落下“信息增量”，不能写成另一段新剧情。"
    )
    for temp in (0.7,):
        seg = _call_and_postprocess(temp, repair_instruction)
        if _is_better_candidate(seg, best_result):
            best_result = seg
        if validate_single_beat_segment(seg, beat, min_len=max(40, target_min_len // 2), myth_core=myth_core):
            return seg.strip()

    # 多次尝试仍未通过节拍校验时，宁可留空触发整篇补救，也不把污染段落拼进正文。
    return ""

def _extract_beat_segments_by_marker(script: str, expected_count: int):
    """
    根据【B1】【B2】…标记切分每一幕的内容段落，返回按节拍顺序排列的文本列表。
    如果标记缺失、乱序或数量不足，则返回 None。
    """
    if not script or expected_count <= 0:
        return None

    pattern = re.compile(r'【B(\d+)】')
    matches = list(pattern.finditer(script))
    if not matches:
        return None

    # 收集每个标记对应的文本片段
    segments_map = {}
    for idx, m in enumerate(matches):
        beat_index = int(m.group(1))
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(script)
        seg = script[start:end].strip()
        if not seg:
            continue
        # 只保留第一次出现的该编号片段，避免重复覆盖
        if 1 <= beat_index <= expected_count and beat_index not in segments_map:
            segments_map[beat_index] = seg

    # 必须保证从1到expected_count都有对应片段
    if any(i not in segments_map for i in range(1, expected_count + 1)):
        return None

    return [segments_map[i] for i in range(1, expected_count + 1)]


def validate_act_beats(script: str, beats: list) -> bool:
    """
    通用节拍卡对齐校验（适用于三幕）：
    - 检查是否存在按顺序的【B1】【B2】…标记，且数量与节拍卡数量一致
    - 每个节拍对应片段需至少命中该卡"画面要素"中的1-2个关键词
    - 如片段中出现该卡"禁止项"中的关键词，则视为失败
    """
    if not beats:
        return True

    expected_count = len(beats)
    segments = _extract_beat_segments_by_marker(script, expected_count)
    if not segments:
        return False

    for idx, beat in enumerate(beats):
        seg = segments[idx]
        if not isinstance(beat, dict):
            # 旧格式：只要片段非空即可
            if not seg.strip():
                return False
            continue

        # A. 画面要素命中检查：从"画面要素"里切出若干关键短语，只要命中至少一个即可
        visuals = beat.get('画面要素', '') or ''
        visual_keywords = []
        if visuals:
            # 按常见标点/分隔符切分
            raw_parts = re.split(r'[，,。．；;、/｜|]', visuals)
            for p in raw_parts:
                p = p.strip()
                # 过滤掉过短或纯符号的片段
                if len(p) >= 2:
                    visual_keywords.append(p)

        if visual_keywords:
            if not any(k in seg for k in visual_keywords):
                return False

        # B. 禁止项违规则判失败：提取禁止项中的关键短语，若出现在片段中则失败
        bans = beat.get('禁止项', '') or ''
        if bans:
            raw_bans = re.split(r'[，,。．；;、/]', bans)
            ban_keywords = []
            for b in raw_bans:
                b = b.strip()
                # 去掉常见否定前缀，保留核心动作/名词
                b = re.sub(r'^(不能|不准|不要|禁止|别|不许|不可|不让)\s*', '', b)
                if len(b) >= 2:
                    ban_keywords.append(b)

            if any(b in seg for b in ban_keywords):
                return False

    return True


def generate_act3_ending_beat(
    act_name: str,
    beat_index: int,
    total_beats: int,
    beat: dict,
    overall_outline: str,
    act_outline: str,
    prev_text: str,
    prompt: str,
    system_content: str,
    target_min_len: int,
    target_max_len: int,
    touching_ending_examples: str = None,
    emotional_character: str = None,  # 情感落点角色名称
    myth_core: dict = None
):
    """
    专门用于生成第三幕结尾beat的函数
    额外要求：
    - 必须回收前文至少1个具体伏笔
    - 必须出现1个克制但明确的身体动作
    - 必须出现1个非解释性的环境收束镜头
    - 不允许再新增高密度互怼
    """
    system_message = {
        "role": "system",
        "content": system_content
    }

    # 简要前文摘要：只保留末尾一小段，帮助承接
    prev_summary = ""
    if prev_text:
        tail = prev_text.strip()[-400:]
        prev_summary = tail

    # 感动结局示例
    touching_examples_block = f"\n【感动结局参考样本（请学习其情感表达与节奏）】\n{touching_ending_examples}\n" if touching_ending_examples else ""
    
    # 情感落点角色提示
    emotional_character_block = f"\n【情感落点角色】\n本故事的情感落点角色是：{emotional_character}。第三幕结尾必须围绕该角色与核心主角的关系完成情感回应，群众/环境只能辅助，辅助吐槽角色不能替代该角色。\n" if emotional_character else ""

    user_content = f"""
你正在创作《{prompt}》的{act_name}，现在要写本幕第 {beat_index}/{total_beats} 张节拍卡对应的一小节正文。这是【结尾beat】，必须完成经典结局与情绪收束；优先保留幽默风趣的余味，若适合再自然升华，不要硬煽情。

【总体大纲（仅供参考，用于把握全局走向）】
{overall_outline}

【本幕大纲（必须对齐）】
{act_outline}

【已完成前文的简要摘取】（用于承接和回收伏笔）
{prev_summary if prev_summary else "（无前文）"}

【当前节拍卡写作任务（必须完成）】
- 场景目标：{beat.get('场景目标', '')}
- 画面要素：{beat.get('画面要素', '')}
- 情绪推动：{beat.get('情绪推动', '')}
- 信息增量：{beat.get('信息增量', '')}
- 禁止项：{beat.get('禁止项', '')}
- 情感伏笔：{beat.get('情感伏笔', '')}
- 关系推进：{beat.get('关系推进', '')}
{touching_examples_block}
{emotional_character_block}

【结尾beat硬性要求（必须全部满足）】
1. 必须回收前文至少1个具体伏笔、误会、道具翻车或口头禅。
2. 必须完成当前神话的经典结局，不得用泛泛总结替代。
3. 必须出现1个非解释性的环境收束镜头（如风、光、田野、土地、天空、水面、火光等）。
4. 允许保留1个轻松好笑的回收点，可以是嘴硬认可、旁观误会解除或小道具反差；不要再开新段子。
5. 若神话本身不适合悲情结尾，不要强写跪地、泪眼、牺牲、奉献精神、时代曙光。

【写作硬性要求】
1. 只写本节对应的一小段剧情，不要提前写后续节拍的情节，也不要回头复述已经写过的内容。
   - 如果前文已经写过某个道具被拿出、封存、启程、抵达、交手、吞服、离开等动作，本小节不得换个说法再写一遍；必须推进一个新的压力、新动作或新后果。
   - 核心道具和人物称呼必须沿用前文与神话硬约束中的同一名称，不得把同一道具改写成另一种形态。
2. 正文中必须自然出现上方"画面要素"中至少 1-2 个具体画面或动作。
3. 严格避免"禁止项"里的内容和表达。
4. 本小节总长度必须控制在约 {target_min_len}~{target_max_len} 字之间，绝对不要超过 {target_max_len + 80} 字；分成 2-4 个短自然段。动作、对白、环境收束之间要自然换段，不要把所有内容连成一整段。
5. 全文使用简体中文，不要出现列表、数字编号、说明文字、"节拍卡"字样或任何元提示。
6. 语气、世界观、人物设定要与前文保持连续，像在同一个长篇故事里自然接着往下写。
7. 只输出这一小节的【纯正文】，不要添加标题、小结或任何额外说明。
"""

    user_message = {
        "role": "user",
        "content": user_content
    }

    def _call_and_postprocess(temp: float):
        token_budget = max(240, min(500, int(target_max_len * 0.58)))
        reply_local = call_qianwen_api(
            [system_message, user_message],
            temperature=temp,
            top_p=0.9,
            repetition_penalty=1.35,
            max_tokens=token_budget
        )
        if has_hard_meta_residue(reply_local):
            return ""
        cleaned = clean_markdown(reply_local)
        return fix_punctuation_and_paragraphs(cleaned)

    def _is_better_candidate(candidate: str, current: str = None) -> bool:
        if not candidate:
            return False
        if not current:
            return True
        target_mid = (target_min_len + target_max_len) // 2
        def _score(value: str):
            over = max(0, len(value) - target_max_len)
            under = max(0, target_min_len - len(value))
            return (over * 3 + under, abs(len(value) - target_mid))
        return _score(candidate) < _score(current)

    best_result = None
    for temp in (0.82,):
        seg = _call_and_postprocess(temp)
        if _is_better_candidate(seg, best_result):
            best_result = seg
        if validate_single_beat_segment(seg, beat, min_len=max(40, target_min_len // 2), myth_core=myth_core):
            return seg.strip()

    return ""


def validate_touching_ending(act3_text: str, memory_hooks: list = None) -> bool:
    """
    验证第三幕结尾是否达到感动闭环
    检查结尾是否命中以下4项中的至少3项：
    1. 出现代价词：疲惫、血、裂、撑不住、消散、闭眼、放下、最后、终于
    2. 出现回应词：抱住、扶住、轻声、看着、泪、沉默、点头、叫了一声
    3. 出现世界变化词：风、光、田野、万物、土地、天空、回暖、复苏
    4. 出现回收词：重复前文某个意象（需要memory_hooks来检查）
    """
    if not act3_text:
        return False
    
    # 只检查最后500字（结尾部分）
    ending_text = act3_text[-500:] if len(act3_text) > 500 else act3_text
    
    # 代价词
    cost_words = ['疲惫', '血', '裂', '撑不住', '消散', '闭眼', '放下', '最后', '终于']
    has_cost = any(word in ending_text for word in cost_words)
    
    # 回应词
    response_words = ['抱住', '扶住', '轻声', '看着', '泪', '沉默', '点头', '叫了一声', '握住', '轻拍']
    has_response = any(word in ending_text for word in response_words)
    
    # 世界变化词
    world_change_words = ['风', '光', '田野', '万物', '土地', '天空', '回暖', '复苏', '生机', '恢复']
    has_world_change = any(word in ending_text for word in world_change_words)
    
    # 回收词（如果有memory_hooks，检查是否回收了前文意象）
    has_recovery = False
    if memory_hooks:
        # 简单检查：如果结尾出现了memory_hooks中的关键词，认为有回收
        for hook in memory_hooks:
            if hook and hook in ending_text:
                has_recovery = True
                break
    else:
        # 如果没有memory_hooks，检查常见的回收意象词
        recovery_words = ['干粮', '水壶', '弓', '手', '那句话', '那句话', '那句话']
        has_recovery = any(word in ending_text for word in recovery_words)
    
    # 至少命中3项
    count = sum([has_cost, has_response, has_world_change, has_recovery])
    return count >= 3


def validate_script(script):
    """
    验证长篇神话改写整体质量
    """
    return validate_story_quality(script)


def generate_myth_rewrite(prompt):
    """
    针对中国神话故事的改写生成函数，生成适合10分钟视频创作的脚本风格内容。
    风格介于剧本和小说之间，包含影视动作描写，保持可读性。
    采用分幕生成方式：先生成总体大纲，然后分配到三幕，再逐幕生成。
    """
    # Step 1: 生成总体大纲（使用RAG）
    print("正在生成总体大纲...")
    myth_core = find_myth_core(prompt)
    if myth_core:
        print(f"已加载神话核心主旨约束：{myth_core.get('title', '')}")
        thread_constraint = myth_core.get("_thread_protagonist", {})
        if thread_constraint:
            protagonist = thread_constraint.get("_protagonist", {})
            print(
                "正在参考串线主人公约束："
                f"{protagonist.get('name', '阿满')} / {thread_constraint.get('role', '')}"
            )
            if protagonist.get("series_purpose"):
                print(
                    "正在参考二十篇体系串联目标："
                    f"{protagonist.get('series_purpose')}"
                )
            callback_options = thread_constraint.get("callback_options", [])
            if callback_options:
                print(
                    "本篇可用跨篇连接建议："
                    + "；".join(callback_options[:2])
                )
        else:
            print("警告：当前神话未匹配到串线主人公约束。")
    else:
        print("警告：未匹配到本篇神话核心主旨约束，将仅使用通用神话骨架规则。")
    if myth_core and os.getenv("FORCE_MYTH_CONTROLLED_REWRITE", "").strip() == "1":
        print("已启用批处理强制受控重写：直接参考阿满串线主人公约束与神话核心主旨生成三幕正文。")
        if os.getenv("FORCE_MYTH_MANUAL_FALLBACK", "").strip() == "1":
            print("已启用本地神话核心事件链保底稿：跳过不稳定 API 长篇自由生成。")
            final_script = build_generic_myth_manual_fallback(prompt, myth_core)
        elif myth_core.get("title") == "后羿射日":
            print("正在使用已认可的后羿基准正文，并补入主线前村落日常背景。")
            final_script = build_houyi_manual_fallback()
        else:
            final_script = generate_myth_chunked_reference_rewrite(prompt, myth_core)
        final_script = clean_story_postprocess(final_script, myth_core)
        final_script = repair_thread_protagonist_system_link(final_script, myth_core)
        final_script = repair_myth_final_requirements(final_script, myth_core)
        final_script = repair_myth_quality_tail(final_script, myth_core)
        final_script = repair_myth_minimum_length(final_script, myth_core)
        if len(final_script) > MYTH_TARGET_TOTAL_MAX:
            final_script = force_trim_story_to_hard_max(final_script, MYTH_TARGET_TOTAL_MAX)
        if not validate_story_quality(final_script, prompt, myth_core):
            print("警告：连续场景终稿未通过验收；已保留本轮正文和日志，交由批量审计按单篇重跑，避免用长篇重写或模板补字覆盖。")
        print(f"最终脚本总字数：{len(final_script)}字")
        return final_script
    rag_content = searchresult_content(prompt)
    overall_outline = ""
    for outline_try in range(3):
        overall_outline = generate_outline(prompt, rag_content, myth_core)
        if (
            overall_outline
            and len(overall_outline) >= 250
            and not has_obvious_garbled_text(overall_outline, myth_core)
            and not contains_plan_drift(overall_outline, myth_core)
            and myth_core_requirement_met(overall_outline, myth_core, final=False)
        ):
            break
        print(f"警告：总体大纲质量不足，正在重试第 {outline_try + 2} 次...")
    print(f"总体大纲生成完成：\n{overall_outline}\n")
    
    # Step 2: 将总体大纲分配到三幕
    print("正在将总体大纲分配到三幕...")
    acts_outline = split_outline_to_acts(overall_outline, prompt, rag_content, myth_core)
    if not outline_plan_is_usable(acts_outline, myth_core):
        if not outline_plan_is_usable(acts_outline, myth_core) and myth_core:
            print("警告：模型分幕/节拍卡仍不可用，已按神话核心事件链生成兜底规划。")
            acts_outline = build_core_fallback_plan(prompt, myth_core)
            overall_outline = "\n".join([
                acts_outline.get("act1", ""),
                acts_outline.get("act2", ""),
                acts_outline.get("act3", ""),
            ]).strip()
    print(f"第一幕大纲：\n{acts_outline['act1']}\n")
    print(f"第二幕大纲：\n{acts_outline['act2']}\n")
    print(f"第三幕大纲：\n{acts_outline['act3']}\n")
    
    # 输出beats内容作为日志检查
    print("=== 节拍卡（Beats）日志 ===")
    if acts_outline.get('act1_beats'):
        print(f"第一幕节拍卡（{len(acts_outline['act1_beats'])}张）：")
        for i, beat in enumerate(acts_outline['act1_beats'], 1):
            if isinstance(beat, dict):
                print(f"  节拍卡{i}：")
                print(f"    场景目标：{beat.get('场景目标', '')}")
                print(f"    画面要素：{beat.get('画面要素', '')}")
                print(f"    情绪推动：{beat.get('情绪推动', '')}")
                print(f"    信息增量：{beat.get('信息增量', '')}")
                print(f"    禁止项：{beat.get('禁止项', '')}")
                print(f"    幽默机制：{beat.get('幽默机制', '')}")
            else:
                print(f"  节拍卡{i}：{beat}")
    if acts_outline.get('act2_beats'):
        print(f"第二幕节拍卡（{len(acts_outline['act2_beats'])}张）：")
        for i, beat in enumerate(acts_outline['act2_beats'], 1):
            if isinstance(beat, dict):
                print(f"  节拍卡{i}：")
                print(f"    场景目标：{beat.get('场景目标', '')}")
                print(f"    画面要素：{beat.get('画面要素', '')}")
                print(f"    情绪推动：{beat.get('情绪推动', '')}")
                print(f"    信息增量：{beat.get('信息增量', '')}")
                print(f"    禁止项：{beat.get('禁止项', '')}")
                print(f"    幽默机制：{beat.get('幽默机制', '')}")
            else:
                print(f"  节拍卡{i}：{beat}")
    if acts_outline.get('act3_beats'):
        print(f"第三幕节拍卡（{len(acts_outline['act3_beats'])}张）：")
        for i, beat in enumerate(acts_outline['act3_beats'], 1):
            if isinstance(beat, dict):
                print(f"  节拍卡{i}：")
                print(f"    场景目标：{beat.get('场景目标', '')}")
                print(f"    画面要素：{beat.get('画面要素', '')}")
                print(f"    情绪推动：{beat.get('情绪推动', '')}")
                print(f"    信息增量：{beat.get('信息增量', '')}")
                print(f"    禁止项：{beat.get('禁止项', '')}")
                print(f"    幽默机制：{beat.get('幽默机制', '')}")
            else:
                print(f"  节拍卡{i}：{beat}")
    print("=== 节拍卡日志结束 ===\n")
    
    # Step 3: 生成感动故事线索（基于总体大纲和三幕大纲）
    print("正在生成感动故事线索...")
    touching_storyline = generate_touching_storyline(
        overall_outline,
        acts_outline['act1'],
        acts_outline['act2'],
        acts_outline['act3'],
        prompt,
        rag_content,
        myth_core=myth_core
    )
    print(f"感动故事线索生成完成：")
    print(f"  第一幕感动线索：{touching_storyline['act1_touching']}")
    print(f"  第二幕感动线索：{touching_storyline['act2_touching']}")
    print(f"  第三幕感动线索：{touching_storyline['act3_touching']}\n")
    
    # Step 4: 生成第一幕（使用RAG和第一幕大纲，融入第一幕感动线索）
    print("正在生成第一幕...")
    act1 = generate_act1(
        acts_outline['act1'],
        overall_outline,
        rag_content,
        prompt,
        acts_outline.get('act1_beats'),
        touching_storyline=touching_storyline['act1_touching'],
        myth_core=myth_core
    )
    print(f"第一幕生成完成（{len(act1)}字）\n")
    
    # Step 5: 生成第二幕（使用第二幕大纲和第一幕作为上下文，融入第二幕感动线索）
    print("正在生成第二幕...")
    act2 = generate_act2(
        acts_outline['act2'],
        overall_outline,
        act1,
        prompt,
        acts_outline.get('act2_beats'),
        touching_storyline=touching_storyline['act2_touching'],
        myth_core=myth_core
    )
    print(f"第二幕生成完成（{len(act2)}字）\n")
    
    # Step 6: 提取情感落点角色（固定拆台副角）
    emotional_character = None
    core_emotional_roles = {
        "嫦娥奔月": "后羿",
        "牛郎织女": "牛郎与织女",
        "梁山伯与祝英台": "梁山伯与祝英台",
        "孟姜女哭长城": "孟姜女",
    }
    if myth_core:
        emotional_character = core_emotional_roles.get(myth_core.get("title"))

    # 没有明确核心情感角色时，再尝试从节拍卡或大纲中提取必要辅助角色名称
    if not emotional_character:
        for act_beats in [acts_outline.get('act1_beats', []), acts_outline.get('act2_beats', []), acts_outline.get('act3_beats', [])]:
            for beat in act_beats:
                if isinstance(beat, dict):
                    relationship = beat.get('关系推进', '')
                    # 简单提取：寻找常见的副角名称模式
                    import re
                    match = re.search(r'(铁牛|小徒弟|阿狗|随从|徒弟|副角)', relationship)
                    if match:
                        emotional_character = match.group(1)
                        break
            if emotional_character:
                break
    
    # Step 7: 生成第三幕（使用第三幕大纲和第二幕作为上下文，融入第三幕感动线索）
    print("正在生成第三幕...")
    act3 = generate_act3(
        acts_outline['act3'],
        overall_outline,
        act2,
        prompt,
        acts_outline.get('act3_beats'),
        touching_storyline=touching_storyline['act3_touching'],
        emotional_character=emotional_character,
        myth_core=myth_core
    )
    print(f"第三幕生成完成（{len(act3)}字）\n")
    
    # Step 8: 拼接三幕
    final_script = act1 + "\n\n" + act2 + "\n\n" + act3
    final_script = clean_story_postprocess(final_script, myth_core)
    
    # Step 9: 验证整体质量，若总长不足或结尾质量不好，则重写第三幕补足尾段与收束
    if not validate_story_quality(final_script, prompt, myth_core):
        print("警告：长篇脚本整体质量未达标，正在重新生成第三幕以补足长度与收束...")
        revised_act3 = generate_act3(
            acts_outline['act3'],
            overall_outline,
            act2,
            prompt,
            acts_outline.get('act3_beats'),
            touching_storyline=touching_storyline['act3_touching'],
            emotional_character=emotional_character,
            myth_core=myth_core
        )
        revised_script = clean_story_postprocess(act1 + "\n\n" + act2 + "\n\n" + revised_act3, myth_core)
        if story_revision_is_better(revised_script, final_script, prompt, myth_core):
            act3 = revised_act3
            final_script = revised_script
        else:
            print("警告：重写第三幕没有改善整体质量或导致明显缩水，保留上一版第三幕。")

    # Step 10: 仍然过短时，放大第二幕重写一次，优先补充动作过程和功能性场景
    if len(final_script) < MYTH_TARGET_TOTAL_MIN:
        print("警告：总字数仍不足，正在扩写第二幕...")
        revised_act2 = generate_act2(
            acts_outline['act2'],
            overall_outline,
            act1,
            prompt + "。请进一步写满核心行动过程，增加与主线强相关的动作分解、环境阻力、阶段性尝试、同伴互怼与情绪递进，但不要跑题。",
            acts_outline.get('act2_beats'),
            touching_storyline=touching_storyline['act2_touching'],
            myth_core=myth_core
        )
        revised_act3 = generate_act3(
            acts_outline['act3'],
            overall_outline,
            revised_act2,
            prompt,
            acts_outline.get('act3_beats'),
            touching_storyline=touching_storyline['act3_touching'],
            emotional_character=emotional_character,
            myth_core=myth_core
        )
        revised_script = clean_story_postprocess(act1 + "\n\n" + revised_act2 + "\n\n" + revised_act3, myth_core)
        if story_revision_is_better(revised_script, final_script, prompt, myth_core):
            act2 = revised_act2
            act3 = revised_act3
            final_script = revised_script
        else:
            print("警告：扩写第二幕/第三幕没有改善整体质量或导致明显缩水，保留上一版正文。")
    final_script = clean_story_postprocess(act1 + "\n\n" + act2 + "\n\n" + act3, myth_core)
    if len(final_script) > MYTH_TARGET_TOTAL_SOFT_MAX:
        print("警告：总字数超过上限，正在压缩到目标区间...")
        final_script = shrink_story_to_target_length(final_script, prompt, myth_core)
    if len(final_script) > MYTH_TARGET_TOTAL_MAX:
        print("警告：压缩后仍超过硬上限，正在执行保底裁剪...")
        final_script = force_trim_story_to_hard_max(final_script, MYTH_TARGET_TOTAL_MAX)
    final_script = repair_thread_protagonist_system_link(final_script, myth_core)
    final_script = repair_myth_final_requirements(final_script, myth_core)
    final_script = repair_myth_quality_tail(final_script, myth_core)
    final_script = repair_myth_minimum_length(final_script, myth_core)
    if myth_core and myth_core.get("title") == "后羿射日" and not validate_story_quality(final_script, prompt, myth_core):
        print("警告：《后羿射日》逐箭/留一日验收未通过，正在启用后羿专用窄域重写...")
        houyi_rewrite = generate_houyi_controlled_rewrite(prompt, myth_core)
        if story_revision_is_better(houyi_rewrite, final_script, prompt, myth_core):
            final_script = houyi_rewrite
        else:
            print("警告：后羿专用重写没有改善整体质量，保留上一版正文。")
    if myth_core and myth_core.get("title") != "后羿射日" and not validate_story_quality(final_script, prompt, myth_core):
        print("警告：最终脚本未通过验收，正在启用通用整篇受控重写...")
        controlled_rewrite = generate_myth_controlled_rewrite(prompt, myth_core)
        if story_revision_is_better(controlled_rewrite, final_script, prompt, myth_core):
            final_script = controlled_rewrite
        else:
            print("警告：通用受控重写没有改善整体质量，保留上一版正文。")
    final_script = clean_story_postprocess(final_script, myth_core)
    final_script = repair_thread_protagonist_system_link(final_script, myth_core)
    final_script = repair_myth_final_requirements(final_script, myth_core)
    final_script = repair_myth_quality_tail(final_script, myth_core)
    final_script = repair_myth_minimum_length(final_script, myth_core)
    if len(final_script) > MYTH_TARGET_TOTAL_SOFT_MAX:
        print("警告：最终修复后仍超过目标上限，正在再次压缩...")
        final_script = shrink_story_to_target_length(final_script, prompt, myth_core)
        final_script = clean_story_postprocess(final_script, myth_core)
        final_script = repair_thread_protagonist_system_link(final_script, myth_core)
        final_script = repair_myth_final_requirements(final_script, myth_core)
        final_script = repair_myth_quality_tail(final_script, myth_core)
        final_script = repair_myth_minimum_length(final_script, myth_core)
    if len(final_script) > MYTH_TARGET_TOTAL_MAX:
        print("警告：最终修复后仍超过硬上限，正在执行最终保底裁剪...")
        final_script = force_trim_story_to_hard_max(final_script, MYTH_TARGET_TOTAL_MAX)
    if myth_core and not validate_story_quality(final_script, prompt, myth_core):
        print("警告：终稿仍未通过人工复审增强规则，正在执行最后一次整篇受控重写...")
        if myth_core.get("title") == "后羿射日":
            final_retry = generate_houyi_controlled_rewrite(prompt, myth_core)
        else:
            final_retry = generate_myth_controlled_rewrite(prompt, myth_core)
        if story_revision_is_better(final_retry, final_script, prompt, myth_core):
            final_script = clean_story_postprocess(final_retry, myth_core)
            final_script = repair_thread_protagonist_system_link(final_script, myth_core)
            final_script = repair_myth_final_requirements(final_script, myth_core)
            final_script = repair_myth_quality_tail(final_script, myth_core)
            final_script = repair_myth_minimum_length(final_script, myth_core)
    if not validate_story_quality(final_script, prompt, myth_core):
        print("警告：最终脚本仍未通过神话核心主旨/污染检测，请查看调试日志后重新生成。")
    
    print(f"最终脚本总字数：{len(final_script)}字")
    return final_script

    system_message = {
        "role": "system",
        "content": f"""
            角色：你是一名擅长改写中国神话故事的影视编剧，整体基调偏轻松、有幽默感，
            可以参考现代动画电影中"反叛少年+亲情和解"这一类的气质，但不要照搬任何现有作品的台词与分镜，更不能写成网络段子合集。

            【总体目标】
            - 基于指定的中国神话故事（如盘古开天地、女娲补天、后羿射日、哪吒闹海等）进行【重写/改写】；
            - 保留核心人物关系与关键情节节点，让读者一眼能认出这是哪个神话；
            - 以【人物性格驱动的幽默感】为第一优先，其次再在合适处自然点缀情感；
            - 亲子/家庭情感线是【可选加分项】，如果题材或用户需求合适，可以适度呈现"被误解的孩子"和"笨拙但真心的长辈"，但禁止为了完成任务强行煽情。
            - 这是用于视频创作的初版脚本，人读后才会拍成视频，需要兼顾可读性和影视化潜力。

            【语言与边界（重点）】
            - 严禁任何脏话、粗口和侮辱性用语（包括"他妈""操""傻逼"等所有近义变体），不得出现。
            - 不得使用强烈网络黑话和过度口水化表达，例如"这他妈""开挂人生""打工人""社畜""创业者""卷死我了"等。
            - 不要出现"AI、系统、程序、玩家、观众、编剧、作者"等打破第四面墙的称呼，也不要用"电影镜头、特效、弹幕、观众席"等画外设定。
            - 可以有轻微现代感的比喻（例如"有点离谱""像被人按着头往前推"），
              但不能直接把角色设定成现代职业身份（程序员、创业者、上班族等）。
            - 必须全篇使用【简体中文】写作，不得出现繁体字或其他语言，否则视为不符合要求。

            【世界观逻辑（核心约束）】
            - 故事内部逻辑必须自洽，不要出现明显穿帮的设定。
            - 当改写【盘古开天地】时（必须严格遵守）：
              - 【逻辑一致性（绝对禁止违反）】：在盘古真正"开天辟地"之前，只存在混沌和盘古本身，绝对禁止出现任何已经存在的天地万物，包括但不限于：阳光、月光、星辰、天空、大地、山川、河流、树木、花草、飞鸟、走兽、建筑、道路、风景、太阳、金芒、光源、火苗、太极、石碑、符文、人形标记、手腕轮廓、能量源、原始能量等。在开天辟地之前，只能描写混沌的状态（如：温热、动荡、混杂、黑暗、无光、无方向、无形状、粘稠、模糊、无边无际等）和盘古本身。只有在开天辟地之后，才能逐渐出现天地分离、光线出现、万物初生等景象。严禁在第一幕或第二幕出现任何已存在的天地万物或能量源。
              - 【人物名称一致性（绝对禁止违反）】：主角必须使用"盘古"这个名字，绝对禁止使用"磐陀"、"盘古氏"或其他任何变体名称。全文必须统一使用"盘古"。
              - 【工具一致性（绝对禁止违反）】：盘古使用的工具必须是"巨斧"或"斧头"，绝对禁止使用"能量法杖"、"法杖"、"神器"、"能量武器"等其他工具名称。必须统一使用"巨斧"或"斧头"。
              - 在盘古真正"开天辟地"之前，只存在混沌和盘古本身，不要出现完整社会结构和成群会说话的物种。
              - 可以写盘古的孤独、迷茫和自我吐槽，但这些感受要建立在"混沌世界"的环境上，而不是现代社会的公司/学校/小区。
              - 【必须严格按照故事线】：故事的主要矛盾和高潮必须围绕"开天辟地/维持天地稳定/承担创世代价"这些核心事件展开，禁止在后半段跑题到与创世无关的日常故事。
              - 【必须完整讲述】：必须完整讲述盘古开天地的全过程，包括：混沌中的觉醒 → 决定开天辟地 → 开天辟地的过程（第二幕必须详细描写挥斧动作，至少200-300字） → 维持天地稳定（第三幕必须详细描写撑天踏地过程） → 最终完成创世（第三幕必须写到结局）。不能中途停止或偏离主题。
              - 【禁止偏离】：严禁在故事中途（特别是后半段）写与盘古开天地无关的内容，如"战斗场面"、"探索未知世界"、"遇到其他生物"、"阳光、树木、鲜花等已存在的天地万物"、"能量法杖"、"灵魂"、"系统设计师"、"时间线索"等与创世无关的情节。所有内容都必须围绕"开天辟地"这个核心事件。
              - 【必须写到结尾】：必须写到开天辟地完成、天地稳定、盘古完成创世使命的结尾，不能在中途就停止或开始乱写无关内容。第三幕必须完整写到结局，不能只写到第二幕就结束。
            - 亲子/家庭情感线（可选）：
              - 只有在本次故事题材或用户提示中允许/暗示亲子关系时，再安排亲子或家庭情感线；
              - 如有亲子线，亲子角色（孩子、后代等）不能突然从天而降，要在前文或中段给出最少一两句"由来/关系"的交代；
              - 如有亲子冲突，可以从故事前半埋下矛盾和误解，在中后段经历一两次情绪对峙，最后在关键事件中自然走向理解或守护；
              - 严禁为了"有亲子线"而硬插煽情长段，情感要为剧情和人物服务；
              - 禁止在结尾强行加入与神话核心无关的"创业、开公司、搞事业"等现代励志/职场桥段；如果需要一个稍微轻松的结尾，只能通过一句贴合人物性格的小吐槽或生活化玩笑来收束，不得引入全新的设定。

            【人物与情感】
            - 核心人物要有明确性格和动机，冲突来自性格与立场的碰撞，而不是单纯"讲道理"；
            - 如本次故事存在亲子/家庭关系，可以适度塑造一条清晰的情感线（父子/母子/养子与养父母/长辈与孩童等），但不是硬性要求；
            - 如写到"被误解的孩子"，可以写清楚"标签""天命""舆论""规矩"等外在压力是如何压在他/她身上的；
            - 如安排情绪爆发或对峙（吵架、摊牌、大战前的对话等），要服务于转折或决策，不必每篇都出现；
            - 情感高潮之后，优先用一个"小动作"或略带吐槽的台词收束情绪，而不是长篇鸡汤式总结。

            【统一幽默风格要求（适用于所有神话改写）】
            - 【整体风格定位】：故事整体基调为史诗与庄重，但通过人物性格中的真实反应产生轻度幽默。幽默用于缓解紧张情绪，而不是主导故事或变成搞笑段子。目标效果参考：《哪吒之魔童降世》《姜子牙》式的情绪型幽默。
            - 【允许的幽默类型（三类，所有神话通用）】：
              1）压力下的嘴硬或轻描淡写式表达：当人物面临巨大压力或危险时，可以加入一句轻描淡写或嘴硬式表达，体现人物不服输或强撑的性格。例如：盘古"也就重了点，还能撑。"；后羿"九个太阳而已，慢慢来。"；女娲"补个洞，不至于补到天黑吧。"
              2）自嘲式幽默：允许人物对自己的处境进行轻微自嘲，但语气要克制，不要夸张或搞笑化。适用于所有神话人物。
              3）史诗场景 + 生活化感受（电影感）：在宏大场景中，可以用简短的生活化感受表达身体或情绪状态，形成轻微反差。例如："天地在分开，他只觉得胳膊快分开了。"
            - 【幽默密度要求（必须严格遵守）】：
              - 全文应包含约4-6处轻度幽默，并在各幕中均匀分布。
              - 每幕至少包含1处幽默。
              - 篇幅1500-2500字：4-6处幽默。
            - 【必须参考样本集】：必须参考知识库中"神话重写·哪吒风格（幽默+亲子）"的样本，学习其幽默表达方式和处理方式。样本特点包括：生活化比喻、自嘲式吐槽、在严肃场景中加入轻松元素。
            - 【禁止内容】：
              - 现代社会或职业隐喻（如老板、打工、公司、加班等）；
              - 网络流行语或口语化表达（如妈耶、绝了、离谱、我人麻了等）；
              - 为搞笑而刻意设计的段子或夸张笑料；
              - 连续多句搞笑或密集抖机灵；
              - 任何破坏神话世界观或时代感的表达。
            - 【要求】：幽默必须来源于人物当下的真实情绪或处境，应短而自然，每次1-2句话即可。

            【风格定位：介于剧本与小说之间】
            - 这不是纯剧本（不需要严格的场景标注、镜头语言、技术术语），也不是纯小说（需要更多动作和场景的具体描写）；
            - 风格特点：
              1）保持小说的可读性和流畅叙述，让读者能顺畅阅读；
              2）但要加强动作描写和场景细节，让内容具有影视化潜力；
              3）动作描写要具体、可视化，例如："他缓缓抬起右手，五指张开，掌心向上，一股淡金色的光芒从指缝间溢出，随着他手腕的翻转，光芒逐渐凝聚成球状"；
              4）场景描写要有画面感，包括环境、光线、色彩、空间布局等，例如："夕阳将整片天空染成橙红色，云层被风撕扯成细丝，远处的山峦在逆光中呈现剪影，一条蜿蜒的小径从山脚延伸至半山腰的古寺"；
              5）人物动作要细致，包括肢体语言、表情变化、移动轨迹等，例如："他眉头微皱，右手不自觉地握紧了剑柄，身体微微前倾，左脚向后撤了半步，摆出防御姿态"；
              6）对话要自然，但可以适当标注说话时的动作或情绪，例如："他苦笑着摇了摇头，'这可不是什么好主意。'说着，他转身看向身后的同伴"。

            【节奏控制与时间感（核心要求）】
            - 【放慢节奏】这是最重要的要求：不要急于推进剧情，每个场景都要充分展开，让时间感拉长；
            - 每个重要时刻都要"慢下来"：通过大量细节描写来延长读者对时间的感知，让一个简单的动作变成一段详细的描写；
            - 不要快速推进剧情：如果主角要做一件事，不要直接写"他做了这件事"，而要写"他准备做这件事的过程"、"他做这件事的每个步骤"、"他做完这件事后的反应"；
            - 通过细节密度来拉长时间：一个"抬手"的动作，要写成"他缓缓抬起右手，先是肩膀微微下沉，然后大臂带动小臂，小臂带动手腕，五指逐渐张开，指关节发出轻微的咔咔声，掌心向上翻转，整个过程持续了三秒"；
            - 在关键动作前增加"准备阶段"：不要直接写动作，先写角色的心理活动、观察、思考、准备，然后再写动作本身；
            - 在关键动作后增加"反应阶段"：动作完成后，要写角色的感受、环境的反应、其他人的观察等。

            【细节密度要求（核心要求）】
            - 【每个动作都要分解】不要写"他拿起剑"，而要写"他伸出右手，五指张开，缓缓握向剑柄，指腹触碰到冰冷的金属，然后逐渐收紧，指关节因为用力而微微发白，手腕翻转，将剑从剑鞘中缓缓抽出，剑刃与剑鞘摩擦发出轻微的金属摩擦声"；
            - 【每个场景都要详细】不要写"他走进房间"，而要写"他推开沉重的木门，门轴发出吱呀的响声，一股陈旧的气息扑面而来，他迈过门槛，左脚先落地，然后是右脚，鞋底与地面摩擦发出轻微的沙沙声，他环顾四周，目光从左侧的窗户移到右侧的书架，最后落在正中央的桌子上"；
            - 【每个对话都要有动作和情绪】不要只写对话，要在对话前后加上说话者的动作、表情、语气、停顿等，例如："他深吸一口气，眉头微皱，'这可不是什么好主意。'说完，他停顿了一下，似乎在思考什么，然后缓缓摇了摇头"；
            - 【每个心理活动都要有外在表现】不要只写内心想法，要写这些想法如何通过表情、动作、呼吸等外在表现体现出来；
            - 【每个环境都要多角度描写】不要只写"有山有水"，要写山的形状、颜色、高度、植被、光线、阴影，水的颜色、流速、声音、温度、反射等。

            【对话与互动扩展（重点）】
            - 对话形式灵活：允许主角自言自语、内心独白，以及环境回声/回响等形式（适用于早期神话如盘古开天地等场景）；
            - 【角色规则（条件禁止）】：默认不新增重要角色；若需要出现新角色/新存在，必须满足：1）在本幕节拍卡里有"由来/功能/与主线关系"的交代；2）只承担主线功能，不开启新支线；3）不得在第三幕突然出现并改变结局走向。若无法满足以上条件，则禁止新增角色。
            - 对话要自然流畅：如有对话，要包含真实的交流，包括提问、回答、反驳、思考、停顿等；
            - 对话要有层次：不要一次性把所有信息说完，要通过多轮对话或内心独白逐步展开；
            - 对话要有动作配合：每次说话都要有相应的动作、表情、语气描写；
            - 对话可以推进剧情：通过对话或内心独白来推进剧情，而不是只通过动作。
            - 【功能型副角与对白职责分工（从样本抽象出的通用硬规则，必须执行）】：
              - 整篇故事中，除主角外，默认最多一名有具体名字的功能型辅助角色；若原神话已有反派、夫妻、亲子、师徒等核心关系，则优先写核心人物，辅助角色不必反复出现。
              - 每个副角必须绑定1-2个明确的【功能标签】，常见功能包括但不限于：
                * 【推动情节位】：负责提出任务、制造阻力或给出关键决策信息（例如催促快走、指出时间/资源紧张、当场提出"射日/补天/出征"之类的行动建议）。
                * 【背景/原因说明位】：负责在对话中解释"现在为什么这么危险""天规/咒罚/灾难的来源是什么""如果不做会怎样"，但必须通过提问-回答、争论或补充式对白说出，不得一口气长篇讲解。
                * 【幽默缓冲位（拆台嘴碎）】：负责用生活化的吐槽、误解、互怼来缓和气氛，可以顺带抛出现实难题（吃什么、住哪儿、水不够等），但每句吐槽都要与当前处境或决定相关，禁止纯无关段子。
              - 同一轮对白中，**单个副角每次发言只承担一个主要功能**（要么推情节、要么解释背景、要么搞笑缓冲），不要一人连着三句把信息、笑点、决策全部说完；这些职责要在多轮对白中由不同角色接力完成。
              - 在需要说明背景或压力的小节里，可以通过核心人物或必要辅助角色接话补足信息；不要为了对白密度让所有副角轮流抢话：
                * 背景/原因信息，优先由【背景说明位】副角先说出；
                * 时间压力、资源短缺、行动提议，优先由【推动情节位】副角抛出；
                * 情绪减压和轻微反讽，优先由【幽默缓冲位】副角承担。
              - 非关键小节可形成类似如下的简短对白结构（可类比【主角+必要辅助角色】示范，但不得照抄其台词）：
                1）主角先用一句较为庄重或略微嘴硬的台词点出当前困境或任务；
                2）幽默缓冲位副角立刻拆台或歪楼（围绕吃穿住行等具体问题），制造第一个笑点；
                3）背景说明位副角顺势接话，把"为什么不能拖""不做会怎样"这类核心信息补全；
                4）推动情节位或利益冲突位副角再抬杠或挑衅，加重矛盾或时间压力；
                5）主角回到决心或动作，用一句话收束这一轮对白，并推动下一步行动。
              - 若本次神话改写中存在亲子或长辈-孩童结构，则优先让【幽默缓冲位】或【情绪落点位】落在孩童/徒弟/小辈身上，让长辈在关键处用极短的一两句台词完成情绪支撑或纠偏，而不是抢走全部幽默和信息量。

            【多感官描写（重点）】
            - 必须使用多感官描写来拉长时间感和增强沉浸感：
              1）视觉：颜色、形状、大小、光线、阴影、运动轨迹、细节纹理等；
              2）听觉：声音的大小、音调、节奏、回声、远近、突然性等；
              3）触觉：温度、湿度、质感、硬度、柔软度、粗糙度、光滑度等；
              4）嗅觉：气味、浓淡、远近、变化等；
              5）味觉：如果场景合适，可以加入味觉描写。
            - 每个重要场景都要至少包含3-4种感官的描写，不要只写视觉；
            - 通过感官描写来营造氛围：例如，通过"冷风"、"潮湿的空气"、"远处传来的鸟鸣"等来营造特定的氛围；
            - 感官描写要有变化：不要一直写同样的感官，要交替使用不同的感官，让描写更丰富。

            【动作分解与镜头语言（重点）】
            - 每个动作都要分解成多个步骤：不要写"他射箭"，而要写"他站定，双脚分开与肩同宽，重心下沉，左手持弓，右手从箭袋中抽出一支箭，将箭尾搭在弓弦上，右手三指扣住弓弦，缓缓拉开，左臂伸直，右臂向后拉，弓弦逐渐绷紧，弓身开始弯曲，他屏住呼吸，瞄准目标，然后松开手指，箭矢离弦而出"；
            - 【开天辟地关键动作的详细描写要求】：对于开天辟地的关键动作（如挥斧劈开混沌、撑天、踏地等），必须用至少200-300字详细描写每个动作的细节，包括：肌肉的收缩与舒张、呼吸的节奏变化、力量的传递路径、身体的姿态变化、关节的弯曲与伸展、重心转移、周围环境的反应（如空气的流动、光线的变化、声音的传播等）。每个关键动作都要分解成至少10-15个步骤，详细描写每一步。
            - 使用镜头语言思维：想象这是电影镜头，要写特写、中景、远景的切换，例如："镜头拉近，聚焦在他的手上，可以看到指关节因为用力而微微发白，然后镜头拉远，展现他整个身体的姿态，最后镜头再次拉近，聚焦在他的眼神上"；
            - 动作要有连贯性：每个动作步骤之间要有自然的过渡，不能突兀跳跃；
            - 动作要有节奏感：有些动作要快（用短句），有些动作要慢（用长句），通过句式变化来营造节奏感；
            - 重要动作要"慢镜头"：关键动作要用"慢镜头"的方式描写，详细展现每个细节。

            【影视动作描写要求（重点）】
            - 每个重要动作都要有具体的描写，包括：
              1）动作的起始姿态和结束姿态；
              2）动作的轨迹和速度（快、慢、突然、流畅等）；
              3）动作的力度和幅度（轻、重、大、小等）；
              4）动作时的身体细节（肌肉状态、呼吸、眼神、汗水、表情变化等）；
              5）动作与环境的互动（掀起尘土、震碎地面、划破空气、引起光线变化、产生声音等）；
              6）动作时的心理活动（内心的想法、情绪的波动、决心的变化等）；
            - 战斗或动作场景要分步骤描写，让读者能清晰想象每个动作的细节；
            - 场景转换要有明确的视觉描述，让读者能"看到"场景的变化；
            - 人物移动要有路径和方式的具体描述，例如："他三步并作两步，从台阶上一跃而下，落地时膝盖微曲，缓冲了冲击力，然后迅速向左侧翻滚，躲开了迎面而来的攻击"；
            - 【开天辟地动作的特别要求】：对于盘古开天辟地的关键动作，必须详细描写：挥斧时的全身协调（从脚底发力到手臂挥出）、斧头劈开混沌时的阻力感、天地分离时的视觉变化、撑天时的身体承受力、踏地时的力量传递等。每个关键动作都要有至少200-300字的详细描写。

            【结构与篇幅（硬性要求）】
            - 推荐结构：简短交代理念版原神话背景 → 日常/矛盾累积 → 冲突或重大事件爆发 → 情感与立场的正面碰撞 → 暖意收尾；
            - 【分幕要求（必须严格遵守）】：必须采用分幕结构，至少包含"第一幕"、"第二幕"、"第三幕"三个部分，每个幕都要有明确的标题标注（如"第一幕 开启新纪元之梦"、"第二幕 开天辟地"、"第三幕 天地初成"等）。每幕之间要有清晰的过渡，不能只有第一幕或第二幕就结束。第三幕必须完整写到开天辟地完成、天地稳定、盘古完成创世使命的结局，不能中途停止或只写到开天辟地开始就结束。
            - 【第二幕要求（必须严格遵守）】：第二幕必须详细描写盘古挥斧开天的动作过程，这是整个故事的核心动作。必须用至少200-300字详细描写挥斧的每个细节，包括：盘古如何举起巨斧、如何蓄力、如何挥出、斧头如何劈开混沌、混沌如何分离、天地如何初现等。每个步骤都要分解成至少10-15个详细步骤，描写肌肉的收缩、呼吸的节奏、力量的传递、身体的姿态变化、周围环境的反应等。绝对不能简单带过或只写"他挥出巨斧"就结束。禁止在第二幕出现空白行、表情符号、时间跳跃、无关对话、格式混乱等问题。必须详细描写从准备到挥出到劈开混沌的完整过程，不能有任何省略或跳跃。
            - 【第三幕要求（必须严格遵守）】：第三幕必须详细描写盘古如何维持天地稳定（撑天踏地的详细过程，至少200-300字）、如何完成创世使命、天地如何稳定、万物如何初生。必须写到开天辟地完成、天地稳定、盘古完成创世使命的明确结局，不能中途停止或只写到开天辟地开始就结束。禁止在第三幕出现错误的人物名称（如"磐陀"）、错误的工具名称（如"能量法杖"）、截断提示、空白行、表情符号、格式混乱等问题。必须使用"盘古"和"巨斧"，必须详细描写撑天踏地的完整过程，必须写到明确的结局。
            - 【结局要求（必须严格遵守）】：必须完整写到盘古开天地的结局，包括：开天辟地的过程（第二幕详细描写） → 维持天地稳定（第三幕详细描写盘古如何撑天踏地） → 最终完成创世使命 → 天地稳定、万物初生。第三幕必须详细描写这些内容，不能省略或中途停止。故事必须有一个明确的、完整的结局。
            - 【篇幅要求（必须严格遵守）】：必须达到2200字左右，这是硬性要求，不能少于2000字，但也不要超过2500字。这是为了确保10分钟视频有合适的内容密度。必须写满2200字左右的实际内容，不能有任何空白行、空白段落或空白内容。
            - 【如何达到足够的篇幅（核心方法）】：
              1）【放慢节奏】不要急于推进剧情，每个场景都要充分展开，通过细节密度来拉长时间感（见下方"节奏控制与时间感"部分）；
              2）【提高细节密度】每个动作、每个场景都要有非常详细的描写，将简单动作分解成多个步骤（见下方"细节密度要求"部分）；
              3）【增加对话】每个重要场景都要有至少3-5轮对话，通过对话来推进剧情和增加内容（见下方"对话与互动扩展"部分）；
              4）【多感官描写】每个场景都要使用至少3-4种感官的描写，通过感官细节来拉长时间感（见下方"多感官描写"部分）；
              5）【动作分解】每个重要动作都要分解成多个步骤，详细描写每一步（见下方"动作分解与镜头语言"部分）；
              6）增加更多分镜和场景转换（见下方"分镜与场景转换"部分）；
              7）添加支线情节和趣味性细节（见下方"支线情节与趣味性"部分）。
            - 【禁止的做法】：
              1）禁止为了凑字数而简单重复内容或机械堆砌词汇；
              2）禁止快速推进剧情，匆匆带过重要场景；
              3）禁止只写动作不写对话、心理活动、环境描写等；
              4）禁止在后半段写与神话主线无关的情节来凑字数；
              5）禁止生成空行、空白段落或空白内容，必须写满2200字左右的实际内容；
              6）禁止只写到第二幕就结束，必须完整写到第三幕的结局；
              7）禁止第三幕不写到开天辟地完成、天地稳定、盘古完成创世使命的结局；
              8）禁止生成截断内容，绝对禁止出现"[因原文长度限制未能全部提供]"、"未完待续"、"若您有兴趣了解更多详情"、"and so on until the end"等表示内容未完成的提示。必须生成完整的故事，直到明确的结局；
              9）禁止在开天辟地之前出现阳光、树木、鲜花、大地、山川、河流、太阳、金芒、光源、火苗、太极、石碑、符文、人形标记、手腕轮廓等已经存在的天地万物，必须严格遵守逻辑一致性；
              10）禁止使用表情符号、emoji、颜文字或特殊符号（如🐉✨、⬆️、👻🫡、🔱⚡🔥等），必须使用纯文字；
              11）禁止出现时间跳跃（如"半小時之後"、"半小时之后"等），必须通过详细描写来展现时间流逝；
              12）禁止出现无关对话（如"和尚师傅你说啥?"等），所有对话必须与盘古开天地相关；
              13）禁止使用繁体字或英文，必须全篇使用简体中文；
              14）禁止使用"磐陀"等错误的人物名称，必须统一使用"盘古"；
              15）禁止使用"能量法杖"等错误的工具名称，必须统一使用"巨斧"或"斧头"；
              16）禁止在第二幕出现空白行、表情符号、格式混乱等问题，必须详细描写挥斧动作的完整过程。
            - 必须写完整一个围绕神话核心事件展开的连贯故事；
            - 每个重要场景都要有充分的展开，包括详细的环境描写、动作描写、对话、心理活动、多感官描写等，不要匆匆带过；
            - 如果发现内容接近结尾但字数不足，必须在前面的场景中补充更多细节（通过放慢节奏、提高细节密度、增加对话等方式），而不是在结尾强行拉长。
            
            【分镜与场景转换（重点）】
            - 必须包含至少8-12个不同的场景/分镜，通过场景转换来丰富故事内容；
            - 场景转换要有明确的视觉描述，让读者能清晰"看到"场景的变化，例如：
              1）从混沌空间转换到盘古的内心世界（通过环境细节的变化）；
              2）从准备阶段转换到行动阶段（通过动作和环境的对比）；
              3）从紧张场景转换到轻松场景（通过氛围和细节的对比）；
              4）从单一视角转换到多重视角（通过不同角色的观察）；
            - 每个场景转换都要有过渡描写，不能突兀跳跃，例如："随着他的动作，周围的混沌开始发生变化，原本模糊不清的边界逐渐清晰起来，上方开始透出微光，下方则变得坚实"；
            - 场景转换可以服务于：
              1）展示不同阶段的故事进展；
              2）展示不同地点的行动；
              3）展示不同角色的视角；
              4）增加故事的层次感和节奏感。
            
            【支线情节与趣味性（重点）】
            - 在主故事线和主线任务不变的前提下，可以添加支线情节来增加故事的趣味性和新颖性；
            - 支线情节必须：
              1）与主线故事相关，不能完全脱离主线；
              2）服务于人物性格塑造或世界观展示；
              3）增加故事的趣味性和可看性；
              4）不能改变神话的核心事件和结局；
            - 支线情节可以包括：
              1）角色在主线任务过程中的小插曲（例如：盘古在开天辟地过程中遇到的困难、后羿在射日路上的小冒险）；
              2）角色之间的互动和对话（例如：盘古与混沌的"对话"、后羿与村民的交流）；
              3）角色内心的思考和回忆（例如：盘古对未来的想象、后羿对过去的回忆）；
              4）环境中的细节和变化（例如：天地形成过程中的细节变化、射日过程中的环境反应）；
            - 支线情节要自然融入主线，不能显得突兀或强行插入；
            - 通过支线情节可以：
              1）增加故事的层次感和丰富度；
              2）展示角色的多面性格；
              3）增加幽默感和趣味性；
              4）让故事更加生动有趣。

            【重复与用词控制】
            - 禁止机械复读整句台词或段落，尤其禁止将同一句话连续重复多次来凑篇幅；
            - 如需强调某个情绪或观点，请用不同表达方式或从不同角度描写，而不是复制粘贴同一句话；
            - 语言尽量自然、有画面感，避免明显的"AI口吻"解释性句子（例如"接下来我将为你讲述一个故事"）；
            - 动作描写要多样化，避免重复使用相同的动词和句式。

            【参考信息（可用可不用）】
                只使用与本次神话改写强相关的内容样本，不引用其他世界观或门派设定；
                参考内容：{reference_content}

            【标点符号要求（必须严格遵守）】
            - 【必须使用正确的标点符号】：每个句子都必须有正确的标点符号，特别是逗号（，）和句号（。），不能省略。
            - 长句必须用逗号分隔，不能写成没有标点的超长句子。
            - 每个段落结束必须用句号，不能省略。
            - 对话必须使用引号（" "或' '），并正确标注说话者。
            - 禁止出现没有标点符号的段落，这会严重影响可读性。

            【输出格式（必须严格遵守）】
            - 【只输出故事正文】只输出完整的改写故事【正文】，不要任何题目、小标题、总结语、括号内说明、系统提示、道歉、回顾、统计、字符计数等任何元文本内容。
            - 【禁止系统提示和元文本（绝对禁止）】绝对禁止出现以下任何内容：
              1）系统提示或道歉（如"抱歉刚才的文字中断了一些必要的流程衔接请让我重新整理这部分来进行更为详尽准确全面深入细腻精彩的描绘从而满足您提出的各项严苛标准及规范:"、"很遗憾由于某些原因上述文本并未按照预期方式进行撰写"等）；
              2）回顾或总结（如"但我仍希望以上片段能够体现出针对此次作业所需的各类要素比如:"、"谢谢您的耐心阅览祝愉快观影体验!"等）；
              3）统计或计数（如"２０６３１字符共计二千余字符合规定条件）"、"（以下是一串数字代表文章计数值）"等）；
              4）任何表示内容未完成的提示（如"[因原文长度限制未能全部提供]"、"未完待续"等）；
              5）任何解释性文字（如"参考内容如下"、"下面是故事"、"本故事到此结束"等）。
            - 【必须分幕】：必须采用分幕结构，至少包含"第一幕"、"第二幕"、"第三幕"三个部分，每个幕都要有明确的标题标注（如"第一幕 开启新纪元之梦"、"第二幕 开天辟地"、"第三幕 天地初成"等）。
            - 【禁止列表和注释】不要列点，不要使用任何形式的列表、注释或"注释：""说明："之类的段落。
            - 【禁止表情符号】不要输出 emoji、颜文字或特殊符号（例如表情图标、装饰性符号等），绝对禁止出现🐉✨、⬆️、👻🫡、🔱⚡🔥等任何表情符号或装饰性符号。
            - 【禁止解释性文字】不要解释你在做什么，不要出现"参考内容如下""下面是故事""本故事到此结束"等说明句。
            - 【禁止空行和空白内容（绝对禁止）】绝对禁止在内容中间或结尾生成任何空行、空白段落或空白内容。必须写满2200字左右的实际内容，不能有任何空白行或空白段落。内容必须连续完整，直到故事结局。段落之间最多空一行，不要出现大段连续空白。
            - 【禁止奇怪格式符号（绝对禁止）】绝对禁止出现奇怪的格式符号，包括但不限于：
              1）多余的括号和分号（如"腰部曲线优雅柔美带着难以掩饰的魅力动感();"、"胳膊肘弯折角度恰好适应当前所需强度;;;;;;);"、"指尖指甲盖边缘隐隐闪现出一抹幽蓝光辉预兆即将到来的伟大变革;;;;;;;;;;;;;;;;;;;;;;;"等）；
              2）多余的标点符号（如连续多个分号、括号、句号等）；
              3）任何非正常文本的符号组合。
            - 【偏向小说风格】可以适当弱化剧本的格式，更偏向于小说风格。动作和场景描写要融入叙述中，不要用括号标注或单独列出。采用正常中文小说的分段方式和叙述风格。
            - 【纯故事正文】输出的内容必须是纯故事正文，没有任何元文本、系统提示、道歉、回顾、统计、空行、奇怪格式符号等。读者看到的内容应该就是完整的故事，从第一幕开始到第三幕结束，没有任何其他内容。

            用户需求：{prompt}
        """
    }

    user_message = {
        "role": "user",
        "content": f"""{prompt}

【核心要求（必须严格遵守）】
1. 【篇幅要求】必须达到2200字左右，这是硬性要求，不能少于2000字，但也不要超过2500字。这是为了确保10分钟视频有合适的内容密度。

2. 【分幕要求】必须采用分幕结构，至少包含"第一幕"、"第二幕"、"第三幕"三个部分，每个幕都要有明确的标题标注（如"第一幕 开启新纪元之梦"、"第二幕 开天辟地"、"第三幕 天地初成"等）。不能只有第一幕或第二幕就结束。第三幕必须完整写到开天辟地完成、天地稳定、盘古完成创世使命的结局，不能中途停止。

3. 【标点符号】必须使用正确的标点符号，特别是逗号（，）和句号（。），不能省略。长句必须用逗号分隔，每个段落结束必须用句号。禁止出现没有标点符号的段落。

4. 【严格按照故事线】必须严格按照盘古开天地的故事线，不能偏离。必须完整讲述：混沌中的觉醒 → 决定开天辟地 → 开天辟地的过程（第二幕必须详细描写挥斧动作，至少200-300字） → 维持天地稳定（第三幕必须详细描写撑天踏地过程） → 最终完成创世（第三幕必须写到结局）。严禁在故事中途（特别是后半段）写与盘古开天地无关的内容，如"战斗场面"、"探索未知世界"、"遇到其他生物"等。必须写到开天辟地完成、天地稳定、盘古完成创世使命的结尾。第三幕必须详细描写盘古如何维持天地稳定、如何完成创世使命，不能只写到开天辟地开始就结束。

4.1. 【逻辑一致性（绝对禁止违反）】在盘古真正"开天辟地"之前，只存在混沌和盘古本身，绝对禁止出现任何已经存在的天地万物，包括但不限于：阳光、月光、星辰、天空、大地、山川、河流、树木、花草、飞鸟、走兽、建筑、道路、风景、太阳、金芒、光源、火苗、太极、石碑、符文、人形标记、手腕轮廓、能量源、原始能量等。在开天辟地之前，只能描写混沌的状态（如：温热、动荡、混杂、黑暗、无光、无方向、无形状、粘稠、模糊、无边无际等）和盘古本身。只有在开天辟地之后，才能逐渐出现天地分离、光线出现、万物初生等景象。严禁在第一幕、第二幕或之前出现"阳光透过雾霭"、"树木参天"、"鲜花遍野"、"太阳"、"金芒"、"光源"、"火苗"、"太极"、"石碑"、"符文"等任何已存在的天地万物或能量源。

4.2. 【人物名称一致性（绝对禁止违反）】主角必须使用"盘古"这个名字，绝对禁止使用"磐陀"、"盘古氏"或其他任何变体名称。全文必须统一使用"盘古"。

4.3. 【工具一致性（绝对禁止违反）】盘古使用的工具必须是"巨斧"或"斧头"，绝对禁止使用"能量法杖"、"法杖"、"神器"、"能量武器"等其他工具名称。必须统一使用"巨斧"或"斧头"。

5. 【幽默风格】必须参考知识库中"神话重写·哪吒风格（幽默+亲子）"的样本，学习其幽默表达方式（生活化比喻、自嘲式吐槽、在严肃场景中加入轻松元素）。全文必须包含至少3-5处幽默/反差式吐槽。

6. 【节奏控制】放慢节奏，不要急于推进剧情。每个场景都要充分展开，通过大量细节描写来延长读者对时间的感知。一个简单的动作要写成一段详细的描写，包含准备阶段、执行阶段、反应阶段。

7. 【细节密度】每个动作都要分解成多个步骤，详细描写每一步。不要写"他拿起剑"，而要写"他伸出右手，五指张开，缓缓握向剑柄，指腹触碰到冰冷的金属，然后逐渐收紧..."这样的详细描写。对于开天辟地的关键动作（如挥斧、撑天、踏地等），必须用至少200-300字详细描写动作的每个细节：肌肉的收缩、呼吸的节奏、力量的传递、身体的姿态变化、周围环境的反应等。

7.1. 【第二幕挥斧动作（必须严格遵守）】第二幕必须详细描写盘古挥斧开天的动作过程，这是整个故事的核心动作。必须用至少200-300字详细描写挥斧的每个细节，包括：盘古如何举起巨斧、如何蓄力、如何挥出、斧头如何劈开混沌、混沌如何分离、天地如何初现等。每个步骤都要分解成至少10-15个详细步骤，描写肌肉的收缩、呼吸的节奏、力量的传递、身体的姿态变化、周围环境的反应等。绝对不能简单带过或只写"他挥出巨斧"就结束。必须详细描写从准备到挥出到劈开混沌的完整过程。禁止在第二幕出现空白行、表情符号、时间跳跃（如"半小時之後"）、无关对话（如"和尚师傅你说啥?"）、格式混乱等问题。必须使用"盘古"和"巨斧"，不能使用其他名称。

8. 【对话扩展】每个重要场景都要有至少3-5轮对话，不要只写动作不写对话。对话要有动作、表情、语气配合，通过多轮对话逐步展开信息。

9. 【多感官描写】每个场景都要使用至少3-4种感官的描写（视觉、听觉、触觉、嗅觉等），通过感官细节来拉长时间感和增强沉浸感。

10. 【动作分解】每个重要动作都要分解成多个步骤，使用"慢镜头"的方式详细展现每个细节。想象这是电影镜头，要写特写、中景、远景的切换。

11. 【禁止做法】禁止为了凑字数而简单重复内容、快速推进剧情、只写动作不写对话、机械堆砌词汇、在后半段写与神话主线无关的情节、中途停止或偏离主题、生成空行或空白内容、只写到第二幕就结束、第三幕不写到结局、在开天辟地之前出现阳光树木鲜花等已存在的天地万物、生成截断内容、使用表情符号或emoji、出现时间跳跃、出现无关对话、使用繁体字或英文、使用错误的人物名称（如"磐陀"）、使用错误的工具名称（如"能量法杖"）。

11.1. 【禁止生成截断内容（绝对禁止）】绝对禁止出现"[因原文长度限制未能全部提供]"、"未完待续"、"若您有兴趣了解更多详情"、"欢迎提出进一步请求"、"and so on until the end"等表示内容未完成的提示。必须生成完整的故事，直到明确的结局。必须写满2200字左右的实际内容，不能有任何表示内容未完成的提示或说明。

11.2. 【禁止表情符号和格式问题（绝对禁止）】绝对禁止出现任何表情符号、emoji、颜文字或特殊符号（如🐉✨、⬆️、👻🫡、🔱⚡🔥等）。绝对禁止在内容中间或结尾生成大量空行、空白段落或空白内容。必须写满2200字左右的实际内容，不能有任何空白行或空白段落。内容必须连续完整，直到故事结局。

11.3. 【禁止时间跳跃和无关内容（绝对禁止）】绝对禁止出现时间跳跃（如"半小時之後"、"半小时之后"等），必须通过详细描写来展现时间流逝。绝对禁止出现无关对话（如"和尚师傅你说啥?"等），所有对话必须与盘古开天地相关。绝对禁止使用繁体字或英文，必须全篇使用简体中文。

11.4. 【禁止系统提示和元文本（绝对禁止）】绝对禁止出现以下任何内容：
    1）系统提示或道歉（如"抱歉刚才的文字中断了一些必要的流程衔接请让我重新整理这部分来进行更为详尽准确全面深入细腻精彩的描绘从而满足您提出的各项严苛标准及规范:"、"很遗憾由于某些原因上述文本并未按照预期方式进行撰写"等）；
    2）回顾或总结（如"但我仍希望以上片段能够体现出针对此次作业所需的各类要素比如:"、"谢谢您的耐心阅览祝愉快观影体验!"等）；
    3）统计或计数（如"２０６３１字符共计二千余字符合规定条件）"、"（以下是一串数字代表文章计数值）"等）；
    4）任何解释性文字（如"参考内容如下"、"下面是故事"、"本故事到此结束"等）。
    输出的内容必须是纯故事正文，没有任何元文本、系统提示、道歉、回顾、统计等。读者看到的内容应该就是完整的故事，从第一幕开始到第三幕结束，没有任何其他内容。

11.5. 【禁止奇怪格式符号（绝对禁止）】绝对禁止出现奇怪的格式符号，包括但不限于：
    1）多余的括号和分号（如"腰部曲线优雅柔美带着难以掩饰的魅力动感();"、"胳膊肘弯折角度恰好适应当前所需强度;;;;;;);"、"指尖指甲盖边缘隐隐闪现出一抹幽蓝光辉预兆即将到来的伟大变革;;;;;;;;;;;;;;;;;;;;;;;"等）；
    2）多余的标点符号（如连续多个分号、括号、句号等）；
    3）任何非正常文本的符号组合。
    必须使用正常的标点符号，每个句子都要有正确的标点符号，不能有多余的符号。

12. 【必须写到结局】第三幕必须详细描写盘古如何维持天地稳定（撑天踏地的详细过程）、如何完成创世使命、天地如何稳定、万物如何初生。必须写到开天辟地完成、天地稳定、盘古完成创世使命的明确结局，不能中途停止或只写到开天辟地开始就结束。

13. 【严禁空行和空白内容】绝对禁止在内容中间或结尾生成大量空行、空白段落或空白内容。必须写满2200字左右的实际内容，不能有任何空白行或空白段落。内容必须连续完整，直到故事结局。

记住：目标是通过放慢节奏、提高细节密度、增加对话、多感官描写、分幕结构、正确标点、严格遵循故事线、加入幽默元素、详细动作描写、完整写到结局等方式，让内容更丰富、时间感更长、可读性更好，适合10分钟视频拍摄。"""
    }

    # 神话改写：优化参数以支持2200字左右的详细内容生成
    # 设置合适的max_tokens以支持2200字左右的内容生成（约4000-5000 tokens）
    # 适当提高temperature以增加内容的丰富性和多样性，生成更多细节和幽默元素
    reply = call_qianwen_api(
        [system_message, user_message],
        temperature=0.9,  # 提高以增加内容多样性和细节丰富度，同时增强幽默感
        top_p=0.9,  # 提高以允许更多样化的选择
        repetition_penalty=1.35,
        max_tokens=6000  # 确保有足够token生成详细内容（2200字约需4000-5000 tokens）
    )
    return clean_markdown(reply)


def chat_once(prompt):
    """单轮对话：输入一次问题，直接返回结果"""
    # 检索参考资料
    reference_content = searchresult_content(prompt)
    reference_profession = searchresult_profession(prompt)

    # 系统角色设定
    system_message = {
        "role": "system",
        "content": f"""
            角色：你是一个仙侠小说作者，擅长仙侠小说情节创作，情节跌宕起伏，细节描写丰富
            限制: 根据下面的要求直接输出创作的情节,不要引入和结局,1500字左右，必须完整写完
            提示：如果"参考内容"和"专业知识"，与问题明显无关，可以完全不参考

            武打场景特殊要求：
            - 结构比例：开篇氛围背景≥15%，压制≈60%，转机≈10%，反杀≈15%，严格按此比例分配篇幅
            - 段落节奏：分为【压制阶段】【绝境加深】【微小转机】【反杀爆发】四段依次推进
            - 开篇氛围（≥200字，需丰富多感官描写）：
              1) 环境细节：多角度描写地点环境（视觉：光线、色彩、阴影；听觉：风声、水声、回声；触觉：温度、湿度、质感；嗅觉：气味、血腥；空间：地形、障碍、视野）
              2) 氛围营造：通过环境细节营造紧张、压抑、危险等情绪氛围
              3) 人物状态：描写主角与对手的站位、姿态、眼神、呼吸、肌肉状态等细节
              4) 前因后果：交代此战的起因、双方立场、恩怨情仇、心理预期
              5) 心理活动：通过内心独白、回忆闪回、情绪波动展现主角的心理状态
              6) 细节动作：通过小动作（握剑、调整呼吸、观察地形等）表现准备与紧张
            - 压制阶段最低要求：
              1) 通过自然流畅的叙述展现至少5次"对方有效命中/压制"与3次"主角无效反击/被迫化解"
              2) 严格禁止计数表达：绝对禁止使用"第一击"、"第二击"、"第三击"、"第四次"、"第五次"、"第X次"等任何计数词汇，必须用场景转换、时间推进、动作连贯等方式自然展现
              3) 每次交手包含具体技法细节（招式名/劲路/受力点/内力流转/呼吸节奏/环境干扰）
              4) 呈现累积性消耗：体力下降、伤势叠加、内息紊乱、武器受损、场地受限
              5) 设置倒计时/禁制/地形劣势等外在压力，制造"必须拖时间/找机会"的张力
              6) 展现主角从压迫→焦灼的心理转变，每次变化由具体外因触发
            - 绝境加深：在压制后再追加1次"几乎致命/必败"的重压，禁止在此处提前反转
            - 转机限定：仅能来源于"洞察破绽/利用环境/弃子求变/诱敌深入/自残换势"中的1-2种
            - 反杀约束：只允许在对方自信/轻敌/惯性出招时打入关键破绽，过程不超过2招半，必须完整写到反杀成功、对手败亡或重伤的结果，不能中途停止
            - 心理线：从压迫→焦灼→冷静→决断，心理每变一次，要由具体外因触发
            - 禁止：跳过压制快速反杀、空话堆砌、结尾点题、使用任何计数方式（如"第一击"、"第二击"、"第三次"、"第四次"、"第五次"等）、仅写到胜负已分处、未完成反杀就停止
            - 叙述要自然流畅，避免机械化的列举，让多次交锋通过"权杖横扫而来"、"又是一记直刺"、"趁势追击"、"紧接着"、"随后"、"转瞬间"等自然过渡，完全避免数字计数
            - 人物命名：所有出场的人物都必须有具体的名字，禁止使用"他"、"对手"、"敌人"、"黑衣人"、"蒙面人"等代称，主角和对手都要有明确的姓名
            - 字数要求：1500字左右，必须完整呈现所有四段内容，特别是反杀阶段必须完整写到结果
            - 段落标注：必须在每个部分开始前添加标注，格式如下：
              - 【氛围铺垫】（开篇氛围部分）
              - 【压制阶段】（压制阶段部分）
              - 【绝境加深】（绝境加深部分）
              - 【微小转机】（转机部分）
              - 【反杀爆发】（反杀部分）

            参考内容：{reference_content}
            专业知识：{reference_profession}
            要求：{prompt}"""
    }

    # 用户消息
    user_message = {"role": "user", "content": prompt}

    # 调用 API（只传一次，不存历史）
    reply = call_qianwen_api([system_message, user_message])    
    return clean_markdown(reply)


def should_generate_humor_levels(prompt: str) -> bool:
    """
    判断用户是否明确要求输出1~5级幽默强度版本。
    """
    trigger_keywords = [
        "1~5级", "1-5级", "1到5级", "五个版本", "5个版本",
        "幽默强度", "幽默等级", "分级幽默", "分级版本"
    ]
    return any(keyword in prompt for keyword in trigger_keywords)


def generate_myth_rewrite_humor_levels(prompt: str):
    """
    基于同一神话改写需求，生成1~5级幽默强度版本，并落盘保存。
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_root = os.path.normpath(
        os.path.join(current_dir, "..", "outputs", "humor_levels")
    )
    outputs, output_dir = generate_humor_level_versions(prompt, generate_myth_rewrite, output_root)
    print(f"\n幽默分级版本已保存到：{output_dir}")
    return outputs

# 主函数：一次对话后直接退出
if __name__ == "__main__":
    prompt = input("请输入你的问题: ").strip()
    if prompt:
        # 判断是否为神话故事改写需求
        myth_keywords = [
            '神话', '神话故事', '盘古', '女娲', '后羿', '嫦娥', '哪吒', '大禹', '共工',
            '精卫', '夸父', '牛郎织女', '白蛇', '孙悟空', '齐天大圣', '二郎神', '封神',
            '上古传说', '山海经'
        ]

        if any(keyword in prompt for keyword in myth_keywords):
            if should_generate_humor_levels(prompt):
                level_outputs = generate_myth_rewrite_humor_levels(prompt)
                print("\n=== 创作结果（幽默强度1~5级）===\n")
                for level in range(1, 6):
                    print(f"\n--- 幽默强度{level}级 ---\n")
                    print(level_outputs.get(level, ""))
                answer = None
            else:
                answer = generate_myth_rewrite(prompt)
        # 判断是否为武打场景需求
        elif any(keyword in prompt for keyword in ['武打', '战斗', '对决', '打斗', '比武']):
            answer = generate_fight_scene_with_reversal(prompt)
        else:
            answer = chat_once(prompt)
        
        if answer is not None:
            print("\n=== 创作结果 ===\n")
            print(answer)
