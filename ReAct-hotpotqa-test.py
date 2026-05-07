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

def add(a: float, b: float) -> float:
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
    Wikipedia 搜索工具
    """

    api_url = "https://en.wikipedia.org/w/api.php"

    headers = {
        "User-Agent": "MyReActAgent/1.0"
    }

    try:

        # =========================
        # Step 1 搜索页面
        # =========================

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

        title = search_results[0]["title"]

        # =========================
        # Step 2 获取摘要
        # =========================

        extract_params = {
            "action": "query",
            "prop": "extracts",
            "explaintext": True,
            "exintro": True,
            "titles": title,
            "format": "json"
        }

        extract_response = requests.get(
            api_url,
            params=extract_params,
            headers=headers,
            timeout=10
        )

        extract_response.raise_for_status()

        extract_data = extract_response.json()

        pages = extract_data["query"]["pages"]

        page = next(iter(pages.values()))

        extract = page.get("extract", "")

        if not extract:
            return f"找到了页面 {title}，但没有摘要"

        extract = extract[:1000]

        result = f"{title}: {extract}"

        return result

    except Exception as e:

        return f"Wikipedia 调用失败: {e}"


# =========================
# 3. 工具注册表
# =========================

TOOLS = {
    "add_numbers": add,
    "multiply_numbers": multiply,
    "wikipedia_search": search_wikipedia,
}


# =========================
# 4. ReAct Prompt
# =========================

SYSTEM_PROMPT = """
你是一个 ReAct Agent。

你必须严格按照以下格式输出。

Thought: 你的思考

如果需要调用工具：

Action: 工具名(JSON参数)

例如：

Action: add_numbers({"a":1,"b":2})

工具返回结果后，你会继续推理。

如果已经得到最终答案：

Answer: 最终答案

你可以使用以下工具：

1. wikipedia_search
用途：搜索 Wikipedia 信息
格式：
Action: wikipedia_search({"query":"Alan Turing"})
注意：调用的英文接口，在使用这个工具前先把问题翻译为英文

2. add_numbers
用途：计算加法
格式：
Action: add_numbers({"a":5,"b":10})

3. multiply_numbers
用途：计算乘法
格式：
Action: multiply_numbers({"a":3,"b":4})

注意：

- 问题用什么语言，思考过程与返回结果必须用与问题一样的语言
- 必须严格使用 Thought / Action / Observation / Answer
- 不允许输出 Markdown
- 不允许编造 Observation
- Observation 只能来自工具执行结果
- 最终答案必须基于 Observation
- 不允许使用模型自身知识补充答案
- 所有答案必须直接来自 Observation
- 如果 Observation 中不存在对应信息，必须明确说明无法获取
- 即使你知道答案，也不能直接回答
- wikipedia_search 必须使用英文搜索
- 如果问题没有对应工具，回答：
Answer: 当前没有可用工具获取该信息
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

            #print("\n" + "=" * 80)
            #print("Answer")
            #print("=" * 80)

            #print(final_answer)

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