import os
import re
import json
from dotenv import load_dotenv
from google import genai


# =========================
# 1. 环境变量读取
# =========================

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("请在 .env 文件中配置 GOOGLE_API_KEY")


# =========================
# 2. 定义工具 Tools
# =========================

def add(a: float, b: float) -> float:
    """
    加法工具
    """
    print(f"\n[Action 执行] add_numbers(a={a}, b={b})")
    result = a + b
    print(f"[Observation 返回] {result}")
    return result


def multiply(a: float, b: float) -> float:
    """
    乘法工具
    """
    print(f"\n[Action 执行] multiply_numbers(a={a}, b={b})")
    result = a * b
    print(f"[Observation 返回] {result}")
    return result


def search_wikipedia(query: str) -> str:
    """
    模拟 Wikipedia 搜索工具
    """
    print(f"\n[Action 执行] wikipedia_search(query={query})")

    query_lower = query.lower()

    if "alan turing" in query_lower:
        result = (
            "Alan Turing was a British mathematician, computer scientist, "
            "logician, cryptanalyst, philosopher, and theoretical biologist. "
            "He was highly influential in the development of theoretical computer science."
        )
    elif "llama" in query_lower:
        result = (
            "A llama is a domesticated South American camelid, widely used as "
            "a meat and pack animal by Andean cultures."
        )
    elif "react agent" in query_lower:
        result = (
            "A ReAct Agent combines reasoning and acting. "
            "It reasons about the task, chooses actions, observes results, "
            "and then continues reasoning."
        )
    else:
        result = f"Fake Wikipedia 中没有找到关于 {query} 的信息。"

    print(f"[Observation 返回] {result}")
    return result


# 工具注册表
TOOLS = {
    "add_numbers": add,
    "multiply_numbers": multiply,
    "wikipedia_search": search_wikipedia,
}


# =========================
# 3. 构造 ReAct Prompt
# =========================

SYSTEM_PROMPT = """
你是一个 ReAct Agent。

你不能直接回答问题，必须按照 ReAct 流程完成任务。

你可以使用以下工具：

1. wikipedia_search
   用途：搜索人物、概念、事实信息
   输入格式：
   {"query": "Alan Turing"}

2. add_numbers
   用途：计算两个数字相加
   输入格式：
   {"a": 5, "b": 12.5}

3. multiply_numbers
   用途：计算两个数字相乘
   输入格式：
   {"a": 3, "b": 4}

你的输出必须严格使用以下两种格式之一。

如果还需要调用工具，输出：

Thought: 这里写你的思考
Action: 工具名称
Action Input: JSON格式参数

如果已经可以给出最终答案，输出：

Thought: 这里写你的思考
Final Answer: 最终答案

注意：
- Action 必须是 wikipedia_search、add_numbers、multiply_numbers 之一。
- Action Input 必须是合法 JSON。
- 最终答案以及执行过程必须用韩语。
- 不要输出 Markdown 表格。
- 不要编造 Observation，Observation 只能由程序工具返回。
"""


# =========================
# 4. 调用 Gemini
# =========================

client = genai.Client(api_key=GOOGLE_API_KEY)


def call_llm(prompt: str) -> str:
    """
    调用大模型。
    这里只使用 Google GenAI SDK，不使用任何 Agent 框架。
    """
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    return response.text.strip()


# =========================
# 5. 解析模型输出
# =========================

def parse_action(llm_output: str):
    """
    从模型输出中解析 Action 和 Action Input。
    """
    action_match = re.search(r"Action:\s*(.+)", llm_output)
    input_match = re.search(r"Action Input:\s*(\{.*\})", llm_output, re.DOTALL)

    if not action_match or not input_match:
        return None, None

    action_name = action_match.group(1).strip()
    action_input_text = input_match.group(1).strip()

    try:
        action_input = json.loads(action_input_text)
    except json.JSONDecodeError:
        return action_name, None

    return action_name, action_input


def parse_final_answer(llm_output: str):
    """
    判断模型是否已经输出 Final Answer。
    """
    final_match = re.search(r"Final Answer:\s*(.*)", llm_output, re.DOTALL)

    if final_match:
        return final_match.group(1).strip()

    return None


# =========================
# 6. 执行工具
# =========================

def execute_tool(action_name: str, action_input: dict):
    """
    根据模型选择的 Action 调用对应 Python 函数。
    """
    if action_name not in TOOLS:
        return f"错误：不存在名为 {action_name} 的工具。"

    tool_func = TOOLS[action_name]

    try:
        result = tool_func(**action_input)
        return result
    except Exception as e:
        return f"工具执行失败：{e}"


# =========================
# 7. 手写 ReAct 主循环
# =========================

def run_react_agent(user_question: str, max_steps: int = 6):
    """
    手写 ReAct Agent。

    核心流程：
    1. 把问题交给模型
    2. 模型输出 Thought + Action
    3. Python 解析 Action
    4. Python 调用工具
    5. 把 Observation 追加回 prompt
    6. 循环直到 Final Answer
    """

    scratchpad = ""

    for step in range(1, max_steps + 1):
        print("\n" + "=" * 60)
        print(f"ReAct Step {step}")
        print("=" * 60)

        prompt = f"""
{SYSTEM_PROMPT}

用户问题：
{user_question}

下面是之前的推理过程：
{scratchpad}

请继续 ReAct 推理。
"""

        llm_output = call_llm(prompt)

        print("\n[LLM 输出]")
        print(llm_output)

        final_answer = parse_final_answer(llm_output)

        if final_answer:
            print("\n" + "=" * 60)
            print("Final Answer")
            print("=" * 60)
            print(final_answer)
            return final_answer

        action_name, action_input = parse_action(llm_output)

        if not action_name:
            observation = "错误：模型没有按照格式输出 Action。"
        elif action_input is None:
            observation = "错误：Action Input 不是合法 JSON。"
        else:
            observation = execute_tool(action_name, action_input)

        scratchpad += f"""
{llm_output}
Observation: {observation}
"""

    return "达到最大推理步数，仍未得到最终答案。"


# =========================
# 8. 运行案例
# =========================

if __name__ == "__main__":
    question = "Who was Alan Turing and what is 5 added to 12.5? "
    run_react_agent(question)