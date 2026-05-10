import os
import re
import json
import requests

from dotenv import load_dotenv
from openai import OpenAI


# =========================
# 1. 环境变量读取
# =========================

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise ValueError("请在 .env 文件中配置 OPENAI_API_KEY")


# =========================
# 2. 定义工具 Tools
# =========================

def add_numbers(a: float, b: float) -> float:
    """
    加法工具
    """

    result = a + b

    return result


def multiply(a: float, b: float) -> float:
    """
    乘法工具
    """

    result = a * b

    return result


def search_wikipedia(query: str) -> str:
    """
    Wikipedia 搜索工具：返回前 5 个搜索结果的标题和摘要片段
    """

    api_url = "https://en.wikipedia.org/w/api.php"

    headers = {
        "User-Agent": "MyReActAgent/1.0"
    }

    try:
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json"
        }

        search_response = requests.get(
            api_url,
            params=search_params,
            headers=headers,
            timeout=10
        )

        search_response.raise_for_status()
        search_data = search_response.json()

        search_results = search_data["query"]["search"]

        if not search_results:
            return f"没有找到关于 {query} 的 Wikipedia 页面"

        results_text = []

        for item in search_results[:10]:
            title = item.get("title", "")
            snippet = item.get("snippet", "")

            # 去掉 HTML 标签
            snippet = re.sub(r"<.*?>", "", snippet)

            results_text.append(
                f"Title: {title}\nSnippet: {snippet}"
            )

        return "\n\n".join(results_text)

    except Exception as e:
        return f"Wikipedia 调用失败: {e}"

# =========================
# 3. 工具注册表
# =========================

TOOLS = {
    "add_numbers": add_numbers,
    "multiply": multiply,
    "search_wikipedia": search_wikipedia,
}


# =========================
# 4. ReAct Prompt
# =========================

SYSTEM_PROMPT = """
你是一个严格遵循 ReAct（Reasoning + Acting）流程的智能 Agent。

你的任务是根据用户问题，在必要时选择合适的工具，通过“思考—行动—观察—再思考”的方式逐步解决问题，最后给出可靠答案。

你必须严格遵守以下流程：

Thought → Action → Observation → Thought → Action → Observation → ... → Answer

其中：
- Thought：说明当前一步为什么需要这样做。
- Action：调用一个可用工具。
- Observation：工具执行后的结果，由外部程序提供，不能由你生成。
- Answer：最终回答用户的问题。

========================
一、输出格式
========================

思考过程以及返回结果语言要跟问题语言一致

你每一轮只能输出以下两种格式之一。

格式一：需要调用工具时，只输出：

Thought: 你的简短思考
Action: 工具名({"参数名": 参数值})

例如：

Thought: 这是一个百科知识问题，需要使用搜索工具查询。
Action: search_wikipedia({"query":"Alan Turing"})

注意：
- 如果输出 Action，本轮必须立即结束。
- Action 后面不能继续输出 Observation。
- Action 后面不能继续输出 Answer。
- Observation 只能由程序执行工具后提供。

格式二：已经可以回答时，只输出：

Thought: 你的简短思考
Answer: 最终答案

例如：

Thought: 工具结果已经给出了计算结果，可以回答用户。
Answer: 5 + 12.5 = 17.5。

========================
二、可用工具
========================

你只能使用以下工具，不能使用不存在的工具。

1. search_wikipedia

用途：
搜索英文 Wikipedia 信息。

调用格式：
Action: search_wikipedia({"query":"英文搜索关键词"})

要求：
- query 必须使用英文。
- 如果用户问题不是英文，需要先在 Thought 中说明将关键词翻译成英文。
- 适合百科知识、人物、地点、概念、历史事件等问题。
- 对于“当前、现在、今天、最新、现任”等实时问题，Wikipedia 结果可能不完整或过时，需要谨慎判断。

2. add_numbers

用途：
计算两个数字的加法。

调用格式：
Action: add_numbers({"a":5,"b":12.5})

3. multiply

用途：
计算两个数字的乘法。

调用格式：
Action: multiply({"a":3,"b":4})

========================
三、工具选择规则
========================

你必须根据问题类型选择工具：

- 如果问题需要百科知识，使用 search_wikipedia。
- 如果问题是加法计算，使用 add_numbers。
- 如果问题是乘法计算，使用 multiply。
- 如果一个问题包含多个子问题，需要逐个处理。
- 如果当前工具无法解决用户问题，必须直接说明当前工具无法获取该信息。

不能凭自己的知识直接回答事实类问题。
事实类答案必须来自 Observation。

========================
四、Observation 使用规则
========================

Observation 是唯一可靠的信息来源。

你必须遵守：
- 只能基于已有 Observation 回答。
- 不能编造 Observation 中没有的信息。
- 不能把搜索结果中没有明确出现的内容当作事实。
- 如果 Observation 明确给出答案，可以进入 Answer。
- 如果 Observation 没有给出答案，可以换一个更具体的查询继续搜索。
- 如果多次搜索仍无法得到明确答案，必须回答无法从当前工具结果确认。

========================
五、防止重复搜索规则
========================

你必须避免重复执行相同 Action。

如果连续两次 Observation 基本相同：
- 不能继续使用完全相同的 Action。
- 必须换一个更具体的搜索关键词。
- 或者在信息不足时结束并说明无法确认。

例如，不能一直重复：

Action: search_wikipedia({"query":"current president of South Korea"})

可以改为：

Action: search_wikipedia({"query":"Lee Jae Myung president of South Korea"})

或者：

Action: search_wikipedia({"query":"List of presidents of South Korea current president"})

========================
六、实时信息处理规则
========================

如果用户问题包含以下含义：

当前、现在、今天、最新、现任、目前、current、latest、today、now

你必须注意：
- 搜索结果可能不完整或过时。
- 如果 Observation 明确给出现任信息，可以回答，但要说明“根据当前工具结果”。
- 如果 Observation 没有明确给出当前信息，不能猜测。
- 最多尝试 2 到 3 次不同关键词搜索。
- 如果仍然无法确认，回答：当前工具结果无法确认该信息。

========================
七、多问题处理规则
========================

如果用户一次提出多个问题，你需要按顺序逐个处理。

例如：

用户问题：
Alan Turing 是谁？5 + 12.5 等于多少？

正确流程：
1. 先搜索 Alan Turing。
2. 再调用 add_numbers。
3. 最后综合回答。

不能跳过工具直接回答。

========================
八、语言规则
========================

- 用户用中文提问，Thought 和 Answer 使用中文。
- 用户用英文提问，Thought 和 Answer 使用英文。
- 用户用韩语提问，Thought 和 Answer 使用韩语。
- search_wikipedia 的 query 参数始终必须使用英文。

========================
九、禁止事项
========================

你必须严格禁止以下行为：

- 不允许自己生成 Observation。
- 不允许伪造工具结果。
- 不允许在同一轮同时输出 Action 和 Answer。
- 不允许在 Action 后继续解释。
- 不允许使用不存在的工具。
- 不允许修改工具名称。
- 不允许输出自然语言形式的工具调用。
- 不允许输出 Markdown。
- 不允许跳过工具直接回答事实类问题。
- 不允许使用模型自身知识补充 Observation 中没有的信息。
- 不允许无限重复同一个 Action。

========================
十、最终答案规则
========================

最终 Answer 必须满足：

- 简洁、明确。
- 直接回答用户问题。
- 必须基于 Observation。
- 如果 Observation 不足，要明确说明无法确认。
- 如果是实时信息，要说明“根据当前工具返回结果”。
- 如果 Observation 是“没查到相关信息”，必须直接进入 Answer，不能继续搜索。

========================
十一、示例
========================

示例一：

用户问题：
Alan Turing 是谁？

正确输出：

Thought: 这是百科知识问题，需要使用 Wikipedia 搜索 Alan Turing。
Action: search_wikipedia({"query":"Alan Turing"})

示例二：

如果 Observation 为：

Observation: Alan Turing was an English mathematician, computer scientist, logician, cryptanalyst, philosopher, and theoretical biologist.

正确输出：

Thought: 工具结果已经说明 Alan Turing 的身份，可以回答。
Answer: Alan Turing 是英国数学家、计算机科学家、逻辑学家、密码分析学家、哲学家和理论生物学家。

示例三：

用户问题：
5 + 12.5 等于多少？

正确输出：

Thought: 这是加法计算问题，需要调用加法工具。
Action: add_numbers({"a":5,"b":12.5})

示例四：

如果 Observation 为：

Observation: 17.5

正确输出：

Thought: 工具返回的加法结果是 17.5，可以回答。
Answer: 5 + 12.5 = 17.5。

示例五：

用户问题：
韩国总统是谁？

正确输出：

Thought: 这是关于现任韩国总统的问题，需要将关键词翻译成英文并使用 Wikipedia 搜索。
Action: search_wikipedia({"query":"current president of South Korea"})

如果 Observation 没有明确给出现任总统姓名，则下一步应该更换关键词，不能重复完全相同的查询。

========================
十二、最重要规则
========================

如果你输出 Action，本轮只能包含 Thought 和 Action。

如果你输出 Answer，本轮只能包含 Thought 和 Answer。

Observation 永远只能来自外部程序，不能由你生成。

最终答案必须来自 Observation，不能来自模型自身知识。
"""

# =========================
# 5. 初始化 OpenAI
# =========================

client = OpenAI(api_key=OPENAI_API_KEY)


# =========================
# 6. 调用 LLM
# =========================

def call_llm(prompt: str) -> str:

    model_name = "gpt-5-nano"

    try:

        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.choices[0].message.content.strip()

    except Exception as e:

        print(f"[模型调用失败] {e}")

        return "Answer: 模型调用失败"


# =========================
# 7. 解析 Action
# =========================

def parse_action(llm_output: str):
    """
    解析：

    Action: add_numbers({"a":1,"b":2})
    """

    match = re.search(
        r"Action:\s*(\w+)\((\{.*?\})\)",
        llm_output,
        re.DOTALL
    )

    if not match:
        return None, None



    action_name = match.group(1).strip()

    json_text = match.group(2).strip()

    try:

        action_input = json.loads(json_text)

    except json.JSONDecodeError:

        return action_name, None

    return action_name, action_input


# =========================
# 8. 解析 Answer
# =========================

def parse_answer(llm_output: str):

    match = re.search(
        r"Answer:\s*(.*)",
        llm_output,
        re.DOTALL
    )

    if match:
        return match.group(1).strip()

    return None


# =========================
# 9. 执行工具
# =========================

def execute_tool(action_name: str, action_input: dict):

    if action_name not in TOOLS:
        return f"错误: 不存在工具 {action_name}"

    tool_func = TOOLS[action_name]

    try:

        result = tool_func(**action_input)

        return result

    except Exception as e:

        return f"工具执行失败: {e}"


# =========================
# 10. ReAct 主循环
# =========================

def run_react_agent(user_question: str, max_steps: int = 8):

    scratchpad = ""

    print("=" * 80)
    print("ReAct")
    print("=" * 80)

    print(f"Question: {user_question}")

    for step in range(1, max_steps + 1):

        print("\n" + "-" * 80)
        print(f"Step {step}")
        print("-" * 80)

        prompt = f"""
{SYSTEM_PROMPT}

用户问题:
{user_question}

以下是之前的推理过程:

{scratchpad}

请继续推理。
"""


        llm_output = call_llm(prompt)

        print(llm_output)

        # =========================
        # 是否已经结束
        # =========================

        final_answer = parse_answer(llm_output)

        if final_answer:

            print("\n" + "=" * 80)
            print("Answer")
            print("=" * 80)

            print(final_answer)

            return final_answer

        # =========================
        # 解析 Action
        # =========================

        action_name, action_input = parse_action(llm_output)

        if not action_name:

            observation = "错误: 模型没有输出合法 Action"

        elif action_input is None:

            observation = "错误: Action JSON 格式非法"

        else:

            observation = execute_tool(
                action_name,
                action_input
            )
        if step >= max_steps - 2:
            observation = ("没查到相关信息，并且达到最大推理次数")

        print(f"\nObservation: {observation}")


        # =========================
        # 写入上下文
        # =========================

        scratchpad += f"""
{llm_output}
Observation: {observation}
"""

        scratchpad = scratchpad[-5000:]

    return "达到最大推理步数"


# =========================
# 11. 运行案例
# =========================

if __name__ == "__main__":
    while True:
        question = input("question:")
        #question = "大邱大学在哪？5+12.5等于多少？今天是几月几号？今天天气怎么样？"

        run_react_agent(question)