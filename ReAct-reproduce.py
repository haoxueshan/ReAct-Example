"""
react_chinese_case.py

中文教学版 ReAct 论文案例复现代码。

复现四种方法：
1. Standard Prompting：直接回答
2. CoT：只进行推理
3. Act-only：只执行动作
4. ReAct：推理 + 行动

说明：
- 不需要 OpenAI API Key。
- 不需要联网。
- 使用一个“迷你 Wikipedia 环境”模拟论文中的 Search / Lookup / Finish。
- 重点是理解四种方法的区别。
"""

import re
from typing import Dict, List, Optional


# =========================================================
# 1. 构造一个迷你 Wikipedia 环境
# =========================================================

class MiniWikipedia:
    """
    这是一个简化版 Wikipedia 环境。

    支持三种动作：
    1. Search[实体名]：搜索某个页面
    2. Lookup[关键词]：在当前页面中查找关键词
    3. Finish[答案]：输出最终答案

    这对应 ReAct 论文中用于 HotpotQA / FEVER 的动作空间。
    """

    def __init__(self):
        # 模拟 Wikipedia 页面内容
        self.pages: Dict[str, str] = {
            "Apple Remote": (
                "Apple Remote 是苹果公司在 2005 年 10 月推出的一款遥控器。"
                "它最初被设计用来控制 Front Row 媒体中心程序。"
            ),
            "Front Row (software)": (
                "Front Row 是苹果 Macintosh 电脑上的一款已停止维护的媒体中心软件。"
                "它可以由 Apple Remote 或键盘功能键控制。"
            )
        }

        # 模拟搜索不到时给出的相似结果
        self.suggestions: Dict[str, List[str]] = {
            "Front Row": [
                "Front Row Seat to Earth",
                "Front Row Motorsports",
                "Front Row (software)"
            ]
        }

        self.current_page: Optional[str] = None
        self.finished: bool = False
        self.answer: Optional[str] = None

    def search(self, entity: str) -> str:
        """模拟 Search[entity]。"""
        entity = entity.strip()

        if entity in self.pages:
            self.current_page = entity
            return self.pages[entity]

        if entity in self.suggestions:
            return f"没有找到 [{entity}]。相似结果：{self.suggestions[entity]}"

        return f"没有找到 [{entity}]。"

    def lookup(self, keyword: str) -> str:
        """模拟 Lookup[string]，在当前页面里查找关键词。"""
        if self.current_page is None:
            return "当前没有打开任何页面。"

        text = self.pages.get(self.current_page, "")
        keyword = keyword.strip().lower()

        sentences = re.split(r"(?<=[。！？.!?])", text)

        for sentence in sentences:
            if keyword in sentence.lower():
                return sentence.strip()

        return "没有找到更多结果。"

    def finish(self, answer: str) -> str:
        """模拟 Finish[answer]。"""
        self.finished = True
        self.answer = answer.strip()
        return f"任务结束。最终答案：{self.answer}"

    def step(self, action: str) -> str:
        """
        执行动作字符串。

        支持：
        Search[xxx]
        Lookup[xxx]
        Finish[xxx]
        """
        action = action.strip()

        if action.startswith("Search[") and action.endswith("]"):
            entity = action[len("Search["):-1]
            return self.search(entity)

        if action.startswith("Lookup[") and action.endswith("]"):
            keyword = action[len("Lookup["):-1]
            return self.lookup(keyword)

        if action.startswith("Finish[") and action.endswith("]"):
            answer = action[len("Finish["):-1]
            return self.finish(answer)

        return f"无效动作：{action}"


# =========================================================
# 2. Standard Prompting：直接回答
# =========================================================

def standard_prompting(question: str) -> str:
    """
    Standard Prompting：直接回答。

    特点：
    - 不推理
    - 不搜索外部信息
    - 直接给答案

    问题：
    - 很容易猜错
    - 没有解释过程
    """

    print("\n" + "=" * 80)
    print("方法一：Standard Prompting（直接回答）")
    print("=" * 80)

    print("\n【问题】")
    print(question)

    print("\n【模型行为】")
    print("模型不进行推理，也不搜索外部信息，直接回答。")

    # 模拟 Figure 1 中 Standard 的错误答案
    answer = "iPod"

    print("\n【输出】")
    print(f"答案：{answer}")

    return answer


# =========================================================
# 3. CoT：只进行推理
# =========================================================

def cot_prompting(question: str) -> str:
    """
    CoT：Chain-of-Thought，链式思维。

    特点：
    - 模型会一步一步推理
    - 但不能搜索外部信息

    问题：
    - 如果模型内部知识错误，就会产生幻觉
    - 推理过程看起来合理，但事实可能是错的
    """

    print("\n" + "=" * 80)
    print("方法二：CoT（只进行推理）")
    print("=" * 80)

    print("\n【问题】")
    print(question)

    print("\n【模型行为】")
    print("模型会一步一步推理，但不允许使用 Search / Lookup 获取外部信息。")

    # 模拟论文 Figure 1 中 CoT 的错误推理
    thought = (
        "让我们一步一步思考。"
        "Apple Remote 最初是为了和 Apple TV 交互而设计的。"
        "Apple TV 可以由 iPhone、iPad 和 iPod Touch 控制。"
        "所以答案是 iPhone、iPad 和 iPod Touch。"
    )

    answer = "iPhone、iPad、iPod Touch"

    print("\n【推理过程】")
    print(thought)

    print("\n【输出】")
    print(f"答案：{answer}")

    return answer


# =========================================================
# 4. Act-only：只执行动作
# =========================================================

def act_only(question: str) -> str:
    """
    Act-only：只执行动作。

    特点：
    - 可以搜索外部信息
    - 但是没有 Thought，不会明确说明为什么这样做

    问题：
    - 缺少规划能力
    - 搜索之后不会很好地综合信息
    - 容易盲目行动
    """

    print("\n" + "=" * 80)
    print("方法三：Act-only（只执行动作）")
    print("=" * 80)

    env = MiniWikipedia()

    print("\n【问题】")
    print(question)

    print("\n【模型行为】")
    print("模型只能执行动作，不能写出 Thought 推理过程。")

    actions = [
        "Search[Apple Remote]",
        "Search[Front Row]",
        "Search[Front Row (software)]",
        "Finish[yes]"
    ]

    final_answer = None

    for i, action in enumerate(actions, start=1):
        print(f"\n动作 {i}：{action}")
        observation = env.step(action)
        print(f"观察 {i}：{observation}")

        if env.finished:
            final_answer = env.answer
            break

    print("\n【输出】")
    print(f"答案：{final_answer}")

    return final_answer


# =========================================================
# 5. ReAct：推理 + 行动
# =========================================================

def react_prompting(question: str) -> str:
    """
    ReAct：Reasoning + Acting。

    特点：
    - Thought 用来思考和规划
    - Action 用来搜索或执行动作
    - Observation 用来接收环境反馈
    - 模型可以根据观察结果动态调整下一步行动

    核心循环：
    Thought → Action → Observation → Thought → Action
    """

    print("\n" + "=" * 80)
    print("方法四：ReAct（推理 + 行动）")
    print("=" * 80)

    env = MiniWikipedia()

    print("\n【问题】")
    print(question)

    print("\n【模型行为】")
    print("模型一边思考，一边搜索，并根据搜索结果调整下一步。")

    trajectory = [
        {
            "thought": (
                "我需要先搜索 Apple Remote，找出它最初被设计用来交互的程序是什么。"
            ),
            "action": "Search[Apple Remote]"
        },
        {
            "thought": (
                "搜索结果显示，Apple Remote 最初被设计用来控制 Front Row 媒体中心程序。"
                "现在我需要搜索 Front Row，找出除了 Apple Remote 之外，还有什么设备可以控制它。"
            ),
            "action": "Search[Front Row]"
        },
        {
            "thought": (
                "直接搜索 Front Row 没有找到准确页面。"
                "相似结果中有 Front Row (software)，所以我应该搜索这个页面。"
            ),
            "action": "Search[Front Row (software)]"
        },
        {
            "thought": (
                "搜索结果显示，Front Row 可以由 Apple Remote 或键盘功能键控制。"
                "题目问的是除了 Apple Remote 之外的其他设备，所以答案是键盘功能键。"
            ),
            "action": "Finish[keyboard function keys]"
        }
    ]

    final_answer = None

    for i, step in enumerate(trajectory, start=1):
        thought = step["thought"]
        action = step["action"]

        print(f"\n思考 {i}：{thought}")
        print(f"动作 {i}：{action}")

        observation = env.step(action)
        print(f"观察 {i}：{observation}")

        if env.finished:
            final_answer = env.answer
            break

    print("\n【输出】")
    print(f"答案：{final_answer}")

    return final_answer


# =========================================================
# 6. 主程序：对比四种方法
# =========================================================

def main():
    question = (
        "除了 Apple Remote 之外，还有什么设备可以控制 "
        "Apple Remote 最初设计用来交互的那个程序？"
    )

    print("\nReAct 论文案例中文复现")
    print("=" * 80)
    print("本程序对比四种方法：")
    print("1. Standard Prompting：直接回答")
    print("2. CoT：只进行推理")
    print("3. Act-only：只执行动作")
    print("4. ReAct：推理 + 行动")

    standard_answer = standard_prompting(question)
    cot_answer = cot_prompting(question)
    act_answer = act_only(question)
    react_answer = react_prompting(question)

    print("\n" + "=" * 80)
    print("最终结果对比")
    print("=" * 80)

    results = [
        ("Standard Prompting", "直接回答", "缺少推理和外部信息", standard_answer),
        ("CoT", "只进行推理", "容易产生幻觉，无法更新知识", cot_answer),
        ("Act-only", "只执行动作", "缺少规划能力，容易盲目操作", act_answer),
        ("ReAct", "推理 + 行动", "能边想边做，动态调整", react_answer),
    ]

    for method, feature, weakness, answer in results:
        print(f"{method:20s} | {feature:10s} | {weakness:20s} | 答案：{answer}")

    print("\n正确答案：keyboard function keys")
    print("中文意思：键盘功能键")

    print("\n结论：")
    print(
        "Standard 直接猜答案；CoT 虽然有推理，但没有外部信息，容易幻觉；"
        "Act-only 虽然能搜索，但缺少规划；ReAct 结合推理和行动，"
        "能够根据搜索结果动态调整，因此得到正确答案。"
    )


if __name__ == "__main__":
    main()