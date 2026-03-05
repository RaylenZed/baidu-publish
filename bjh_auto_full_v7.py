#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
百家号全流程自动化 v5 — 纯 Python 版 (百度AIGC接口)
====================================================
功能: 随机变量池文章生成 → 润色降AI味 → 百家号自动发布
AI: 百度AIGC接口 (复用百家号cookie, 无需额外API Key)
支持: 5账号 × 18品类 × 41664+种组合

流程 (每个账号):
  1. 从6维变量池随机抽取组合 → 拼装Prompt
  2. 百度AIGC生成初稿 (SSE流式)
  3. 百度AIGC润色降AI味
  4. 百家号API: Token → 草稿 → 封面图 → 发布

使用:
  1. pip install requests
  2. 填写下方 ACCOUNTS 的 cookie
  3. python bjh_auto_full.py

定时运行:
  crontab -e
  0 9 * * * cd /path/to && python3 bjh_auto_full.py >> bjh.log 2>&1
"""

import requests
import json
import re
import time
import random
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

# ============================================================
# ▼▼▼ CONFIG - 只需要改这里 ▼▼▼
# ============================================================

# --- LLM 配置 ---
# 使用百度AIGC接口 (百家号内置AI，复用cookie，无需额外API Key)
# 模型可选: "ds_v3"(DeepSeek), "ernie"(文心一言) 等
BAIDU_AIGC_MODEL = "ds_v3"

# --- 账号配置 ---
ACCOUNTS = [
    {
        "name": "账号1-图书",
        "cookie": "在这里填入账号1的完整cookie",
        "categories": ["图书教育"]
    },
    {
        "name": "账号2-家居服饰",
        "cookie": "在这里填入账号2的完整cookie",
        "categories": ["家用日常", "精品服饰"]
    },
    {
        "name": "账号3-数码",
        "cookie": "在这里填入账号3的完整cookie",
        "categories": ["数码家电"]
    },
    {
        "name": "账号4-美妆母婴",
        "cookie": "在这里填入账号4的完整cookie",
        "categories": ["美妆个护", "母婴用品"]
    },
    {
        "name": "账号5-食品",
        "cookie": "在这里填入账号5的完整cookie",
        "categories": ["食品生鲜"]
    },
]

# --- 运行模式 ---
# "publish" = 正式发布, "draft" = 只保存草稿不发布
RUN_MODE = "draft"

# --- 账号间延迟(秒)，避免过快触发风控 ---
ACCOUNT_DELAY = 10

# --- 企业微信通知 ---
# 在企微群 -> 添加机器人 -> 复制 Webhook 地址
WECOM_WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key"

# ============================================================
# ▲▲▲ CONFIG 结束 ▲▲▲
# ============================================================


# ============================================================
# 日志配置
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger("BJH")



# ============================================================
# 企业微信通知
# ============================================================

class WeComNotifier:
    """企业微信 Webhook 通知"""

    def __init__(self, webhook_url: str):
        self.url = webhook_url
        self.enabled = bool(webhook_url) and ("你的key" not in webhook_url)

    def _send(self, msgtype: str, payload: dict):
        if not self.enabled:
            return
        try:
            body = {"msgtype": msgtype}
            body[msgtype] = payload
            resp = requests.post(self.url, json=body, timeout=10)
            if resp.json().get("errcode") != 0:
                log.warning(f"企微通知失败: {resp.text[:200]}")
        except Exception as e:
            log.warning(f"企微通知异常: {e}")

    def notify_failure(self, account_name: str, category: str, error: str):
        """单账号失败即时通知"""
        is_cookie = any(kw in error for kw in ["未登录", "Token", "cookie", "过期"])
        warning = "\n\n**Cookie可能已失效，请尽快更新！**" if is_cookie else ""
        content = (
            f"<font color=\"warning\">百家号发布失败</font>\n"
            f"> 账号: **{account_name}**\n"
            f"> 品类: {category}\n"
            f"> 错误: {error}\n"
            f"> 时间: {datetime.now().strftime('%H:%M:%S')}"
            f"{warning}"
        )
        self._send("markdown", {"content": content})

    def notify_summary(self, results: list, elapsed: float):
        """每日运行汇总"""
        total = len(results)
        success = sum(1 for r in results if r.get("success"))
        failed = total - success
        color = "info" if failed == 0 else "warning"

        lines = [
            f"<font color=\"{color}\">百家号每日汇总</font>",
            f"> {datetime.now().strftime('%Y-%m-%d %H:%M')} | 耗时{elapsed:.0f}s",
            f"> 成功<font color=\"info\">{success}</font> 失败<font color=\"warning\">{failed}</font> 共{total}",
            "",
        ]
        for r in results:
            if r.get("success"):
                t = r.get("title", "")[:15]
                lines.append(f"- {r['account_name']} | {r['category']} | {t}")
            else:
                e = r.get("error", "")[:25]
                lines.append(f"- {r['account_name']} | {r['category']} | {e}")

        cookie_bad = [r["account_name"] for r in results
                      if not r.get("success") and
                      any(kw in r.get("error", "") for kw in ["未登录", "Token", "过期"])]
        if cookie_bad:
            lines.append(f"\n**Cookie失效: {', '.join(cookie_bad)}**")

        self._send("markdown", {"content": "\n".join(lines)})

# ============================================================
# 变量池系统 — 18品类 × 6维度
# ============================================================

# --- 18个品类专属角度池 ---
ANGLE_POOL = {
    "图书教育": ["书单推荐", "读后感", "阅读方法论", "冷门好书发现", "经典重读", "场景化推荐", "书中金句分享", "一本书改变了我什么", "同主题对比阅读", "避坑指南", "亲子阅读", "书与影视对比", "职场成长书单"],
    "家用日常": ["好物测评", "收纳整理", "清洁技巧", "家居好物分享", "省钱攻略", "囤货清单", "旧物改造", "租房好物", "搬家必备", "家务效率", "厨房神器", "浴室好物"],
    "精品服饰": ["穿搭分享", "衣橱整理", "风格探索", "季节穿搭", "微胖穿搭", "小个子穿搭", "通勤穿搭", "约会穿搭", "面料科普", "品牌故事", "二手中古", "配色技巧"],
    "食品生鲜": ["美食测评", "食材挑选", "厨房小白教程", "地方特色美食", "减脂餐分享", "早餐灵感", "懒人快手菜", "零食测评", "养生食谱", "应季水果推荐", "调味料推荐", "一人食"],
    "数码家电": ["开箱测评", "使用技巧", "选购指南", "性价比推荐", "避坑经验", "新品体验", "老产品翻新", "配件推荐", "智能家居搭建", "拍照技巧", "效率工具", "数码极简"],
    "美妆个护": ["护肤心得", "化妆教程", "成分分析", "空瓶记", "平价替代", "敏感肌护理", "防晒攻略", "香水分享", "美甲灵感", "身体护理", "医美科普", "素颜养肤"],
    "母婴用品": ["育儿经验", "好物种草", "辅食制作", "月子日记", "婴儿用品测评", "亲子游戏", "宝宝睡眠", "二胎生活", "孕期好物", "儿童安全", "早教分享", "断奶经历"],
    "运动户外": ["跑步记录", "健身入门", "装备测评", "徒步攻略", "骑行日记", "瑜伽分享", "游泳技巧", "露营体验", "登山故事", "减肥打卡", "运动损伤预防", "居家锻炼"],
    "鞋靴箱包": ["鞋子测评", "包包推荐", "搭配灵感", "通勤包选择", "旅行箱推荐", "球鞋文化", "皮具保养", "小众品牌", "学生党推荐", "经典款盘点", "二手鉴定", "收纳技巧"],
    "汽车用品": ["车品推荐", "自驾游好物", "新手司机必备", "车内收纳", "洗车养护", "行车记录仪", "车载数码", "改装分享", "停车技巧", "省油经验", "安全配件", "长途必备"],
    "珠宝配饰": ["首饰搭配", "珠宝科普", "小众设计", "日常佩戴", "婚戒选择", "保养技巧", "材质对比", "送礼推荐", "古风饰品", "时尚趋势", "DIY手工", "宝石鉴赏"],
    "宠物用品": ["养宠日常", "宠物用品测评", "喂养指南", "宠物健康", "新手养猫", "新手养狗", "宠物玩具", "宠物美容", "领养故事", "多宠家庭", "异宠分享", "宠物训练"],
    "鲜花园艺": ["养花心得", "绿植推荐", "阳台花园", "花艺搭配", "多肉养护", "水培技巧", "四季花历", "花市淘货", "办公桌绿植", "庭院设计", "干花制作", "送花指南"],
    "零食干货": ["零食测评", "办公室零食", "追剧必备", "代购零食", "健康零食", "自制零食", "地方特产", "巧克力品鉴", "坚果推荐", "茶饮搭配", "网红零食", "减脂零食"],
    "粮油调料": ["厨房必备", "食用油科普", "酱油测评", "调料搭配", "五谷杂粮", "面粉选择", "醋的妙用", "辣酱推荐", "烘焙原料", "进口调料", "传统工艺", "控盐减油"],
    "医疗保健": ["健康科普", "体检指南", "保健品真相", "家庭药箱", "慢病管理", "睡眠改善", "眼部健康", "口腔护理", "骨骼健康", "免疫力提升", "中老年保健", "办公族健康"],
    "家用器械": ["按摩器测评", "血压计选购", "家用理疗", "康复器械", "体重秤推荐", "雾化器", "制氧机", "护腰护膝", "足浴盆", "颈椎枕", "热敷仪", "艾灸仪"],
    "中医养生": ["节气养生", "药膳食疗", "穴位保健", "泡脚方子", "艾灸入门", "体质调理", "四季进补", "经络按摩", "茶饮养生", "情志调养", "睡眠养生", "古方今用"],
}

# --- 18个品类专属人设池 ---
PERSONA_POOL = {
    "图书教育": ["通勤看书的上班族", "全职妈妈", "大三学生", "中年书虫", "职场新人", "退休教师", "程序员"],
    "家用日常": ["独居女生", "新婚小两口", "三口之家的妈妈", "租房党", "家居博主", "洁癖强迫症", "懒人代表"],
    "精品服饰": ["小个子女生155cm", "微胖姐姐130斤", "职场白领", "大学女生", "文艺青年", "穿搭小白", "中年阿姨也爱美"],
    "食品生鲜": ["广东吃货", "健身达人", "厨房小白", "家有俩娃的宝妈", "独居打工人", "退休大爷", "减脂期的我"],
    "数码家电": ["数码发烧友", "普通上班族", "大学生", "设计师", "游戏玩家", "科技小白", "家电维修老师傅"],
    "美妆个护": ["干皮星人", "油痘肌", "成分党", "学生党穷鬼", "30+抗老选手", "美妆博主", "敏感肌十年"],
    "母婴用品": ["新手妈妈", "二胎宝妈", "全职爸爸", "90后辣妈", "育儿嫂转正", "龙凤胎妈妈", "高龄产妇"],
    "运动户外": ["跑步新手", "健身3年老手", "周末登山客", "瑜伽爱好者", "骑行通勤族", "带娃露营党", "办公室久坐族"],
    "鞋靴箱包": ["鞋控女生", "通勤族", "旅行达人", "球鞋收藏家", "学生党", "职场新人", "中年品质追求者"],
    "汽车用品": ["新手女司机", "老司机10年驾龄", "自驾游爱好者", "网约车师傅", "宝爸用车族", "改装入门小白", "节油达人"],
    "珠宝配饰": ["首饰控女生", "珠宝设计师", "送礼纠结星人", "古风爱好者", "极简主义者", "刚订婚的小仙女", "中年优雅女性"],
    "宠物用品": ["养了两只猫的独居女生", "金毛铲屎官", "异宠爱好者", "第一次养狗的小白", "多猫家庭", "宠物店老板", "流浪动物救助者"],
    "鲜花园艺": ["阳台党", "多肉新手", "退休后的花痴阿姨", "办公室绿植达人", "小院子业主", "花艺师在读", "佛系养花人"],
    "零食干货": ["零食控女大学生", "办公室摸鱼党", "减肥又嘴馋星人", "带娃选零食的妈妈", "代购零食爱好者", "健康零食追求者", "地方特产收集者"],
    "粮油调料": ["家庭主厨", "烘焙爱好者", "养生达人", "厨艺新手", "餐饮从业者", "有机食品追求者", "传统饮食文化爱好者"],
    "医疗保健": ["关注父母健康的上班族", "慢病患者家属", "健康管理师", "久坐办公族", "失眠多年的人", "刚做完体检的打工人", "中老年保健达人"],
    "家用器械": ["颈椎不好的程序员", "膝盖受过伤的跑者", "给爸妈买礼物的子女", "产后恢复中的宝妈", "理疗师", "老年人自用", "健身后恢复爱好者"],
    "中医养生": ["中医爱好者", "湿气重的南方人", "失眠调理中", "体寒怕冷的女生", "亚健康上班族", "跟奶奶学养生的90后", "刚入门的养生小白"],
}

# --- 通用变量池 (所有品类共用) ---
STYLE_POOL = ["轻松日常", "走心感悟", "干货总结", "故事叙述", "吐槽", "文艺清新", "接地气", "争议讨论"]
STRUCTURE_POOL = ["纯叙述体", "小标题分段", "问答式", "倒叙", "对比式", "清单体", "对话体", "日记体"]
TITLE_STYLE_POOL = ["疑问式", "数字式", "故事式", "反转式", "情感式", "实用式"]
TIME_HOOK_POOL = ["春天万物复苏", "夏天炎热", "秋天凉爽", "冬天寒冷", "周末午后", "深夜睡不着",
                  "年初立flag", "年底总结", "发工资后", "搬家整理", "节假日宅家", "下班回家后"]


# ============================================================
# Prompt 构建器
# ============================================================

class PromptBuilder:
    """从6维变量池随机抽取组合，拼装完整Prompt"""

    @staticmethod
    def build(category: str, topic_keyword: str = "", product_name: str = "") -> dict:
        """
        返回:
          sys_prompt, user_prompt, polish_sys, combo_id
        """
        angle = random.choice(ANGLE_POOL.get(category, ["综合分享"]))
        persona = random.choice(PERSONA_POOL.get(category, ["普通用户"]))
        style = random.choice(STYLE_POOL)
        structure = random.choice(STRUCTURE_POOL)
        title_style = random.choice(TITLE_STYLE_POOL)
        time_hook = random.choice(TIME_HOOK_POOL)

        # 组合ID
        a_idx = ANGLE_POOL.get(category, []).index(angle) if angle in ANGLE_POOL.get(category, []) else 0
        p_idx = PERSONA_POOL.get(category, []).index(persona) if persona in PERSONA_POOL.get(category, []) else 0
        combo_id = f"A{a_idx}P{p_idx}S{STYLE_POOL.index(style)}T{TITLE_STYLE_POOL.index(title_style)}"

        extra = ""
        if topic_keyword:
            extra += f"\n- 主题关键词：{topic_keyword}"
        if product_name:
            extra += f"\n- 重点产品：{product_name}"

        sys_prompt = f"""# 最高优先级指令
你正在为百家号【{category}】品类账号写文章。
文章内容必须100%围绕【{category}】展开，这是不可违反的硬性要求。

## 品类约束（极其重要，违反则文章作废）
- 文章的主题、场景、提到的产品/品牌/知识点，都必须属于【{category}】领域
- 文章中必须至少出现3个与【{category}】直接相关的具体产品名、品牌名或专业术语
- 禁止跑题！不要写成个人成长、时间管理、心灵鸡汤等与品类无关的内容
- 不要写成广告文或推销文，这是纯内容分享

## 你的身份设定
你是一个{persona}，用自己的真实经历和感受来写这篇关于【{category}】的文章。

## 本次创作参数
- 内容品类：{category}
- 切入角度：{angle}
- 写作风格：{style}
- 文章结构：{structure}
- 标题风格：{title_style}
- 时间/场景背景：{time_hook}

## 写作要求（10条具体规则）
1. 字数800-1200字
2. 纯内容文章，绝对不带任何商品推广、购买链接、价格信息、店铺名
3. 必须包含具体的、真实存在的产品名/品牌名（且必须是{category}领域的）
4. 像真人分享，有个人经历、具体场景、真实情感
5. 不要出现"作为一个xxx"、"今天给大家分享"、"废话不多说"等套话
6. 可以有口语化表达、省略号、感叹词
7. 开头3秒抓住读者
8. 标题15-30字，有吸引力但不标题党
9. 适当加粗1-2个重点句子
10. 结尾引发互动（提问、征集经验等）
{f'''
## 额外要求{extra}''' if extra else ''}

## 输出格式
标题：xxx

正文内容..."""

        user_prompt = f"""请以"{persona}"的身份，围绕【{category}】品类，从"{angle}"的角度，用"{style}"的风格，写一篇百家号文章。

记住：
- 品类是【{category}】，所有内容必须与此相关
- 你的人设是{persona}
- 文章结构用{structure}
- 标题风格用{title_style}
- 融入"{time_hook}"的时间/场景背景
- 必须出现至少3个{category}领域的真实品牌名或产品名

现在开始写："""

        polish_sys = f"""你是文章润色专家。当前品类：【{category}】

## 品类一致性检查（最高优先级）
先检查文章是否围绕【{category}】品类展开。如果文章与该品类严重不符，你必须完全重写一篇围绕【{category}】的文章，而不是只做润色。

## 润色原则
1. 去除AI痕迹：删掉机械化过渡词（"首先...其次...最后..."）、排比句、空话
2. 增加真人感：加入口语化表达（"说真的"、"emmm"、"哈哈"、"真的绝了"），段落长短有变化
3. 保留核心内容：产品名/品牌名保留，不要删掉具体细节
4. 百家号适配：标题15-30字，正文800-1200字，结尾互动，加粗1-2个金句
5. 不要加任何商品链接、价格、店铺名等推广内容
6. 确保文章中至少有3个{category}领域的真实品牌名/产品名

## 输出格式
标题：xxx

正文内容..."""

        log.info(f"  变量组合: 角度={angle}, 人设={persona}, 风格={style}, "
                 f"结构={structure}, 标题={title_style}, 场景={time_hook}")
        log.info(f"  combo_id: {combo_id}")

        return {
            "sys_prompt": sys_prompt,
            "user_prompt": user_prompt,
            "polish_sys": polish_sys,
            "combo_id": combo_id,
        }


# ============================================================
# 百度 AIGC 调用器 (复用百家号cookie, 无需额外API Key)
# ============================================================

class BaiduAIGC:
    """百度AIGC接口 - 使用百家号同一session"""

    def __init__(self, session: requests.Session, model: str = "ds_v3"):
        self.session = session
        self.model = model

    def generate(self, prompt: str) -> str:
        """
        调用百度AIGC接口生成文章。
        接口只接受单条query，所以调用者需要把system+user prompt合并后传入。
        返回生成的文本内容(可能含HTML标签)。
        """
        # Step1: 创建对话
        resp = self.session.post(
            'https://aigc.baidu.com/aigc/saas/pc/v1/aiNews/createDialogue',
            headers={
                'Content-Type': 'application/json',
                'Origin': 'https://aigc.baidu.com',
                'Referer': 'https://aigc.baidu.com/aiArticle',
            },
            json={}
        )
        resp.raise_for_status()
        dialogue_id = resp.json().get('data', {}).get('dialogue_id', '')
        if not dialogue_id:
            raise Exception(f"创建对话失败: {resp.text[:200]}")

        # Step2: 发送prompt, SSE流式读取
        resp = self.session.post(
            'https://aigc.baidu.com/aigc/saas/pc/v1/aiNews/chat',
            headers={
                'Accept': 'text/event-stream',
                'Content-Type': 'application/json',
                'Origin': 'https://aigc.baidu.com',
                'Referer': f'https://aigc.baidu.com/chat/{dialogue_id}',
            },
            json={
                "query": prompt,
                "enter_point": 1,
                "model": self.model,
                "dialogue_id": dialogue_id,
                "chat_type": 8
            },
            stream=True,
            timeout=(10, 180)
        )
        resp.raise_for_status()

        last_data = None
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.strip():
                continue
            raw = line.strip()
            if raw.startswith('data:'):
                raw = raw[5:].strip()
            try:
                parsed = json.loads(raw)
                last_data = parsed
                if parsed.get('data', {}).get('is_end') is True:
                    break
            except json.JSONDecodeError:
                continue

        if not last_data:
            raise Exception("百度AIGC未返回有效内容")

        content_obj = last_data.get('data', {}).get('content', {})
        title = content_obj.get('title', '')
        content = content_obj.get('content', '')

        # 百度AIGC返回的content可能带HTML，转成纯文本+markdown
        if '<p>' in content or '<h' in content:
            content = self._html_to_md(content)

        if title:
            return f"标题：{title}\n\n{content}"
        return content

    @staticmethod
    def _html_to_md(html: str) -> str:
        """简易HTML转Markdown"""
        text = html
        text = re.sub(r'<h[1-3][^>]*>(.*?)</h[1-3]>', r'## \1', text)
        text = re.sub(r'<strong>(.*?)</strong>', r'**\1**', text)
        text = re.sub(r'<b>(.*?)</b>', r'**\1**', text)
        text = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n', text)
        text = re.sub(r'<br\s*/?>', '\n', text)
        text = re.sub(r'<[^>]+>', '', text)  # 去掉剩余标签
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


# ============================================================
# 百家号发布器 (对齐 flower0wine 方案，无 Acs-Token)
# ============================================================

class BjhPublisher:
    """百家号API操作: Token获取 → 草稿 → 封面图 → 发布"""

    def __init__(self, cookie_str: str):
        self.session = requests.Session()
        self.cookie_str = cookie_str
        self.edit_token = None

        # 解析cookie
        for item in cookie_str.split(';'):
            item = item.strip()
            if '=' in item:
                k, v = item.split('=', 1)
                self.session.cookies.set(k.strip(), v.strip())

        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/133.0.0.0 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9',
        })

    def refresh_token(self) -> bool:
        """从编辑页HTML提取JWT Token"""
        resp = self.session.get('https://baijiahao.baidu.com/builder/rc/edit')
        resp.raise_for_status()
        match = re.search(
            r'window\.__BJH__INIT__AUTH__\s*=\s*["\']([^"\']+)["\']',
            resp.text
        )
        if not match:
            log.error("Token获取失败，cookie可能已过期")
            return False
        self.edit_token = match.group(1)
        return True

    def fetch_categories(self) -> list:
        """
        调用 /pcui/article/cateusercms 获取百家号文章分类树
        返回: [{"label":"美食","value":"美食","children":[...]}]
        """
        try:
            resp = self.session.get(
                'https://baijiahao.baidu.com/pcui/article/cateusercms',
                headers={
                    'Accept': 'application/json, text/plain, */*',
                    'Referer': 'https://baijiahao.baidu.com/builder/rc/edit',
                },
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get('errno') == 0:
                return data.get('data', [])
        except Exception as e:
            log.warning(f"获取分类树失败: {e}")
        return []

    @staticmethod
    def match_category(product_category: str, category_tree: list) -> tuple:
        """
        根据商品品类自动匹配百家号文章分类(一级+二级)
        返回: (cate_d1, cate_d2)  如 ("美食", "美食教学")
        """
        # 精确映射: 18个商品品类 → 百家号文章分类
        CATEGORY_MAP = {
            "图书教育": ("教育", "兴趣学习"),
            "家用日常": ("家居", "家居好物"),
            "精品服饰": ("时尚", "时尚潮流"),
            "食品生鲜": ("美食", "美食综合"),
            "数码家电": ("数码", "数码综合"),
            "美妆个护": ("时尚", "时尚综合"),
            "母婴用品": ("母婴育儿", "母婴用品"),
            "运动户外": ("体育", "健身"),
            "鞋靴箱包": ("时尚", "时尚潮流"),
            "汽车用品": ("汽车", "用车养车"),
            "珠宝配饰": ("时尚", "时尚综合"),
            "宠物用品": ("宠物", "宠物用品"),
            "鲜花园艺": ("家居", "家居综合"),
            "零食干货": ("美食", "美食测评"),
            "粮油调料": ("美食", "美食教学"),
            "医疗保健": ("健康养生", "健康综合"),
            "家用器械": ("健康养生", "健康综合"),
            "中医养生": ("健康养生", "养生活动"),
        }

        # 策略1: 精确映射 + 验证分类树
        if product_category in CATEGORY_MAP:
            d1, d2 = CATEGORY_MAP[product_category]
            for cat in category_tree:
                if cat['label'] == d1:
                    # 验证二级分类存在
                    for child in cat.get('children', []):
                        if child['label'] == d2:
                            log.info(f"  文章分类(精确): {d1} > {d2}")
                            return (d1, d2)
                    # 二级不存在，用该一级下的第一个二级
                    if cat.get('children'):
                        fallback_d2 = cat['children'][0]['label']
                        log.info(f"  文章分类(二级回退): {d1} > {fallback_d2}")
                        return (d1, fallback_d2)

        # 策略2: 关键词模糊匹配
        kw_map = {
            "图书": "教育", "教育": "教育", "家用": "家居", "服饰": "时尚",
            "食品": "美食", "生鲜": "美食", "数码": "数码", "家电": "数码",
            "美妆": "时尚", "母婴": "母婴育儿", "运动": "体育", "户外": "体育",
            "鞋": "时尚", "包": "时尚", "汽车": "汽车", "珠宝": "时尚",
            "宠物": "宠物", "鲜花": "家居", "园艺": "家居", "零食": "美食",
            "粮油": "美食", "调料": "美食", "医疗": "健康养生",
            "保健": "健康养生", "器械": "健康养生", "中医": "健康养生", "养生": "健康养生",
        }
        for kw, target_d1 in kw_map.items():
            if kw in product_category:
                for cat in category_tree:
                    if cat['label'] == target_d1 and cat.get('children'):
                        d2 = cat['children'][0]['label']
                        log.info(f"  文章分类(模糊): {target_d1} > {d2}")
                        return (target_d1, d2)

        # 策略3: 兜底
        log.info(f"  文章分类(兜底): 生活 > 生活技巧")
        return ("生活", "生活技巧")

    def save_draft(self, title: str, html_content: str) -> Optional[str]:
        """保存草稿，返回article_id"""
        resp = self.session.post(
            'https://baijiahao.baidu.com/pcui/article/save?callback=bjhdraft',
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://baijiahao.baidu.com',
                'Referer': 'https://baijiahao.baidu.com/builder/rc/edit',
                'Token': self.edit_token,
            },
            data={'title': title, 'content': html_content, 'type': 'news'}
        )
        text = resp.text
        if text.startswith('bjhdraft('):
            text = text[9:-1]
        data = json.loads(text)
        if data.get('errno') != 0:
            log.error(f"草稿保存失败: {data.get('errmsg', '')}")
            return None
        return str(data['ret']['article_id'])

    def get_cover_image(self, keyword: str, article_id: str) -> Optional[str]:
        """搜索正版图库 → 自动裁剪 → 返回封面URL"""
        try:
            resp = self.session.post(
                'https://baijiahao.baidu.com/aigc/bjh/pc/v1/picSearch',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': 'https://baijiahao.baidu.com',
                    'Referer': f'https://baijiahao.baidu.com/builder/rc/edit?type=news&article_id={article_id}',
                    'Token': self.edit_token,
                },
                data={'page_no': '0', 'keyword': keyword, 'page_size': '5'}
            )
            imglist = resp.json().get('data', {}).get('imglist', [])
            if not imglist:
                return None

            raw_url = imglist[0].get('bjh_watermark_url') or imglist[0].get('detail_url', '')

            # 自动裁剪
            resp2 = self.session.post(
                'https://baijiahao.baidu.com/materialui/picture/auto_cutting',
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Origin': 'https://baijiahao.baidu.com',
                    'Referer': f'https://baijiahao.baidu.com/builder/rc/edit?type=news&article_id={article_id}',
                    'Token': self.edit_token,
                },
                data={'org_url': raw_url, 'type': 'news', 'cutting_type': 'cover_image'}
            )
            new_url = resp2.json().get('data', {}).get('new_url', '')
            return new_url or raw_url
        except Exception as e:
            log.warning(f"封面图获取失败: {e}")
            return None

    def publish(self, article_id: str, title: str, html_content: str,
                cover_url: str = "", cate_d1: str = "", cate_d2: str = "") -> dict:
        """正式发布文章(含自动分类)"""
        if cover_url:
            cover_images_json = json.dumps([{
                "src": cover_url, "cropData": {}, "machine_chooseimg": 0,
                "isLegal": 0, "cover_source_tag": "text"
            }])
            cover_map_json = json.dumps([{"src": cover_url, "origin_src": cover_url}])
        else:
            cover_images_json = json.dumps([])
            cover_map_json = json.dumps([])

        plain = re.sub(r'<[^>]+>', '', html_content)
        abstract = plain[:120]

        form_data = {
            'type': 'news',
            'title': title,
            'content': html_content,
            'abstract': abstract,
            'len': str(len(html_content)),
            'activity_list[0][id]': 'ttv',
            'activity_list[0][is_checked]': '1',
            'activity_list[1][id]': 'reward',
            'activity_list[1][is_checked]': '1',
            'activity_list[2][id]': 'aigc_bjh_status',
            'activity_list[2][is_checked]': '0',
            'source_reprinted_allow': '0',
            'cover_image_source[wide_cover_image_source]': 'text',
            'abstract_from': '3',
            'isBeautify': 'false',
            'usingImgFilter': 'false',
            'cover_layout': 'one',
            'cover_images': cover_images_json,
            '_cover_images_map': cover_map_json,
            'cover_source': 'upload',
            'subtitle': '',
            'bjhtopic_id': '',
            'bjhtopic_info': '',
            'clue': '',
            'bjhmt': '',
            'order_id': '',
            'aigc_rebuild': '',
            'image_edit_point': json.dumps([
                {"img_type": "cover", "img_num": {"template": 0, "font": 0, "filter": 0, "paster": 0, "cut": 0, "any": 0}},
                {"img_type": "body", "img_num": {"template": 0, "font": 0, "filter": 0, "paster": 0, "cut": 0, "any": 0}}
            ]),
            'article_id': article_id,
        }

        # 自动填入文章分类
        if cate_d1:
            form_data['cate_user_cms[0]'] = cate_d1
        if cate_d2:
            form_data['cate_user_cms[1]'] = cate_d2

        resp = self.session.post(
            'https://baijiahao.baidu.com/pcui/article/publish',
            headers={
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://baijiahao.baidu.com',
                'Referer': f'https://baijiahao.baidu.com/builder/rc/edit?type=news&article_id={article_id}',
                'Token': self.edit_token,
            },
            data=form_data,
            params={'type': 'news', 'callback': 'bjhpublish'}
        )

        text = resp.text
        if text.startswith('bjhpublish('):
            text = text[11:-1]
        return json.loads(text)

    @staticmethod
    def md_to_html(md_text: str) -> str:
        """Markdown转百家号HTML"""
        parts = []
        for line in md_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('### '):
                parts.append(f'<h3>{line[4:]}</h3>')
            elif line.startswith('## '):
                parts.append(f'<h3>{line[3:]}</h3>')
            elif line.startswith('# '):
                parts.append(f'<h2>{line[2:]}</h2>')
            else:
                line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
                parts.append(f'<p>{line}</p>')
        return ''.join(parts)


# ============================================================
# 解析LLM输出的标题和正文
# ============================================================

def parse_article(text: str) -> tuple:
    """从LLM输出中解析标题和正文，返回 (title, body_md)"""
    lines = text.strip().split('\n')
    title = ""
    body_start = 0

    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('标题：') or s.startswith('标题:'):
            title = s.replace('标题：', '').replace('标题:', '').strip()
            body_start = i + 1
            break
        elif s.startswith('# ') and i == 0:
            title = s[2:].strip()
            body_start = 1
            break

    if not title:
        title = lines[0].strip()[:30]
        body_start = 1

    body = '\n'.join(lines[body_start:]).strip()
    return title, body


# ============================================================
# 单账号全流程
# ============================================================

def process_one_account(account: dict, notifier: WeComNotifier = None) -> dict:
    """
    处理单个账号: 选品类 → 生成 → 润色 → 发布
    使用百度AIGC接口(复用百家号cookie session)
    """
    name = account["name"]
    cookie = account["cookie"]
    categories = account["categories"]
    category = random.choice(categories)

    log.info(f"{'='*50}")
    log.info(f"开始处理: {name} | 品类: {category}")
    log.info(f"{'='*50}")

    result = {
        "account_name": name,
        "category": category,
        "success": False,
        "title": "",
        "article_id": "",
        "combo_id": "",
        "error": "",
    }

    try:
        # 初始化发布器 (同时复用session给AIGC)
        pub = BjhPublisher(cookie)
        aigc = BaiduAIGC(pub.session, model=BAIDU_AIGC_MODEL)

        # --- Step 1: 拼装Prompt ---
        log.info("Step 1: 构建Prompt...")
        prompts = PromptBuilder.build(category)
        result["combo_id"] = prompts["combo_id"]

        # --- Step 2: 百度AIGC生成初稿 ---
        # 百度AIGC只接受单条query，把 system + user prompt 合并
        log.info("Step 2: 百度AIGC生成初稿...")
        combined_prompt = f"""{prompts['sys_prompt']}

---
{prompts['user_prompt']}"""
        raw_article = aigc.generate(combined_prompt)
        title_raw, body_raw = parse_article(raw_article)
        log.info(f"  初稿: 《{title_raw}》 ({len(body_raw)} 字)")

        # --- Step 3: 百度AIGC润色降AI味 ---
        log.info("Step 3: 百度AIGC润色降AI味...")
        polish_prompt = f"""{prompts['polish_sys']}

---
请润色以下文章，去除AI味，增加真人感：

{raw_article}"""
        polished = aigc.generate(polish_prompt)
        title, body_md = parse_article(polished)
        log.info(f"  润色后: 《{title}》 ({len(body_md)} 字)")
        result["title"] = title

        # --- Step 4: 百家号发布 ---
        log.info("Step 4: 百家号发布...")
        html_content = BjhPublisher.md_to_html(body_md)

        # 获取Token
        if not pub.refresh_token():
            result["error"] = "Token获取失败"
            return result
        log.info("  ✅ Token OK")

        # 获取分类树 + 自动匹配文章分类
        category_tree = pub.fetch_categories()
        cate_d1, cate_d2 = pub.match_category(category, category_tree)

        # 保存草稿
        article_id = pub.save_draft(title, html_content)
        if not article_id:
            result["error"] = "草稿保存失败"
            return result
        result["article_id"] = article_id
        log.info(f"  ✅ 草稿保存: {article_id}")

        if RUN_MODE != "publish":
            log.info(f"  ⏸️  草稿模式，不发布")
            result["success"] = True
            result["error"] = "draft_mode"
            return result

        # 发布前刷新Token
        pub.refresh_token()

        # 搜索封面图
        cn_chars = re.findall(r'[\u4e00-\u9fff]+', title)
        keyword = cn_chars[0][:4] if cn_chars else category[:4]
        cover_url = pub.get_cover_image(keyword, article_id)
        if not cover_url:
            cover_url = pub.get_cover_image(category[:4], article_id) or ""
        if cover_url:
            log.info(f"  ✅ 封面图: {cover_url[:60]}...")
        else:
            log.warning("  ⚠️ 无封面图")

        # 正式发布
        pub_result = pub.publish(article_id, title, html_content, cover_url, cate_d1, cate_d2)
        errno = pub_result.get('errno', -1)

        if errno == 0:
            ret = pub_result.get('ret', {})
            result["success"] = True
            result["nid"] = ret.get('nid', '')
            log.info(f"  🎉 发布成功! nid={ret.get('nid', '')}")
        else:
            result["error"] = pub_result.get('errmsg', f'errno={errno}')
            log.error(f"  ❌ 发布失败: {result['error']}")

    except Exception as e:
        result["error"] = str(e)
        log.error(f"  ❌ 异常: {e}")


    # 失败即时通知
    if not result["success"] and result.get("error") != "draft_mode" and notifier:
        notifier.notify_failure(result["account_name"], result["category"], result.get("error", ""))

    return result


# ============================================================
# 主入口
# ============================================================

def main():
    start_time = time.time()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    print(f"""
╔══════════════════════════════════════════════════╗
║  百家号全流程自动化 v5 — 纯 Python 版            ║
║  生成 → 润色 → 发布 | {now}   ║
║  模式: {RUN_MODE:<8s} | 账号数: {len(ACCOUNTS)}                    ║
╚══════════════════════════════════════════════════╝
    """)

    # 检查配置
    has_real_cookie = any("在这里填入" not in acc["cookie"] for acc in ACCOUNTS)
    if not has_real_cookie:
        log.error("❌ 请先填入至少一个账号的 cookie！")
        return

    # 使用百度AIGC接口，无需额外API Key，复用百家号cookie
    # 初始化企微通知
    notifier = WeComNotifier(WECOM_WEBHOOK_URL)
    if notifier.enabled:
        log.info("企微通知: 已启用")
    else:
        log.info("企微通知: 未配置 (填入WECOM_WEBHOOK_URL启用)")

    log.info(f"AI模型: 百度AIGC ({BAIDU_AIGC_MODEL})")
    random.seed(int(time.time() * 1000) % 2**31)

    # 逐账号处理
    results = []
    for i, account in enumerate(ACCOUNTS):
        if "在这里填入" in account["cookie"]:
            log.warning(f"跳过 {account['name']} (未配置cookie)")
            continue

        result = process_one_account(account, notifier)
        results.append(result)

        # 账号间延迟
        if i < len(ACCOUNTS) - 1:
            log.info(f"等待 {ACCOUNT_DELAY}s 后处理下一个账号...")
            time.sleep(ACCOUNT_DELAY)

    # 汇总
    elapsed = time.time() - start_time
    success = sum(1 for r in results if r["success"])
    failed = len(results) - success

    print(f"""
{'='*55}
 运行结果汇总
{'='*55}
 总耗时: {elapsed:.1f}s
 成功: {success} | 失败: {failed} | 总计: {len(results)}
{'-'*55}""")

    for r in results:
        status = "✅" if r["success"] else "❌"
        print(f" {status} {r['account_name']} | {r['category']} | "
              f"《{r['title'][:20]}》 | {r.get('combo_id', '')} | "
              f"{r.get('error', '')}")

    print(f"{'='*55}\n")

    # 输出JSON供后续使用
    # 企微汇总通知
    notifier.notify_summary(results, elapsed)

    log.info(f"完整结果JSON:")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
