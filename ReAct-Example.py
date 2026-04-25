import asyncio
import gc
import os
import sys

from dotenv import load_dotenv


# Windows + aiohttp 在默认 Proactor 事件循环上，退出时偶发出现
# “Fatal error on SSL transport / Event loop is closed” 的清理噪音。
# 切换到 Selector 事件循环通常可以避免该问题。
if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 重要：`google.genai` 在 import 阶段就可能触发 SSL 初始化并尝试写入 SSLKEYLOGFILE。
# 你的环境里该路径（Postman 抓包 keylog）不可写，会导致 PermissionError，所以必须在 import 之前清理。
os.environ.pop("SSLKEYLOGFILE", None)

# 一些环境会注入无效本地代理（例如 127.0.0.1:9），会导致请求连接被拒绝；这里统一清理，避免网络异常。
for proxy_var in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(proxy_var, None)

from llama_index.core.agent import ReActAgent
from llama_index.core.tools import FunctionTool
from llama_index.llms.google_genai import GoogleGenAI


load_dotenv()
google_api_key = os.getenv("GOOGLE_API_KEY")

if not google_api_key:
    raise ValueError(
        "GOOGLE_API_KEY not found in environment variables. Please set it in your .env file."
    )


def multiply(a: float, b: float) -> float:
    """Multiplies two numbers, a and b. Use this for multiplication tasks."""
    print(f"--- Calling Multiply Tool with: a={a}, b={b} ---")
    return a * b


def add(a: float, b: float) -> float:
    """Adds two numbers, a and b. Use this for addition tasks."""
    print(f"--- Calling Add Tool with: a={a}, b={b} ---")
    return a + b


def search_wikipedia(query: str) -> str:
    """Looks up a query on a FAKE Wikipedia."""
    print(f"--- Calling Wikipedia Tool with query: {query} ---")
    query = query.lower()
    if "alan turing" in query:
        return (
            "Alan Turing was a British mathematician, computer scientist, "
            "logician, cryptanalyst, philosopher, and theoretical biologist. "
            "He was highly influential in the development of theoretical "
            "computer science."
        )
    if "llama" in query:
        return (
            "A llama is a domesticated South American camelid, widely used as "
            "a meat and pack animal by Andean cultures since the Pre-Columbian era."
        )
    if "react agent" in query:
        return (
            "A ReAct Agent combines Reasoning and Acting within large language "
            "models. It generates verbal reasoning traces and actions "
            "pertaining to a task, allowing for dynamic reasoning, tool use, "
            "and information gathering."
        )
    return f"Couldn't find information about '{query}' on Fake Wikipedia."


multiply_tool = FunctionTool.from_defaults(fn=multiply, name="multiply_numbers")
add_tool = FunctionTool.from_defaults(fn=add, name="add_numbers")
wikipedia_tool = FunctionTool.from_defaults(
    fn=search_wikipedia, name="wikipedia_search"
)
tools = [multiply_tool, add_tool, wikipedia_tool]


def _iter_exception_messages(exc: BaseException) -> list[str]:
    """遍历异常链（__cause__/__context__），收集所有 message，便于判断具体失败原因。"""
    seen: set[int] = set()
    msgs: list[str] = []
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        msgs.append(str(cur))
        cur = cur.__cause__ or cur.__context__
    return msgs


def _looks_like_recitation(exc: BaseException) -> bool:
    """Gemini 可能会以 finish_reason=RECITATION 提前终止输出，LlamaIndex 会抛 RuntimeError。"""
    text = "\n".join(_iter_exception_messages(exc)).upper()
    return "RECITATION" in text


def _looks_like_quota(exc: BaseException) -> bool:
    """配额不足/限流通常表现为 429 RESOURCE_EXHAUSTED 等关键词。"""
    text = "\n".join(_iter_exception_messages(exc)).upper()
    return ("RESOURCE_EXHAUSTED" in text) or ("HTTP" in text and "429" in text)


def _looks_like_key_error(exc: BaseException) -> bool:
    """API Key 失效/过期/无效时，通常会返回 400/401 且包含明确错误信息。"""
    text = "\n".join(_iter_exception_messages(exc)).upper()
    return (
        "API KEY EXPIRED" in text
        or "API_KEY_INVALID" in text
        or ("INVALID API KEY" in text)
        or ("UNAUTHORIZED" in text)
    )


async def main() -> None:
    # system_prompt 约束输出：尽量避免“引用/逐字复述”触发 RECITATION 终止。
    llm_system_prompt = (
        "You are a helpful assistant.\n"
        "Answer in your own words. Do not provide verbatim quotes, song lyrics, or long excerpts.\n"
        "If asked about a person, give a short factual summary and avoid copying from any source.\n"
    )

    try:
        llm = GoogleGenAI(
            model="gemini-flash-latest",
            api_key=google_api_key,
            temperature=0,
            system_prompt=llm_system_prompt,
        )
    except Exception as exc:
        # 这里是初始化失败（网络/Key/环境）层面的问题，直接提示并退出即可，避免堆栈噪音。
        print("GoogleGenAI initialization failed. Check your API key and network settings.")
        print("Details:", exc)
        return

    agent = ReActAgent(tools=tools, llm=llm, verbose=True, streaming=False)

    print("--- Starting Agent ---")
    question = "Who was Alan Turing and what is 5 added to 12.5?"

    # 第一次尝试：正常跑 ReAct
    try:
        result = await agent.run(user_msg=question)
    except Exception as exc:
        # API key 过期/无效：提示更新 key（这是配置问题，不是代码问题）。
        if _looks_like_key_error(exc):
            print("Gemini API key error: expired/invalid. Please renew/update GOOGLE_API_KEY.")
            print("Details:", exc)
            return

        # 429/RESOURCE_EXHAUSTED：配额不足，直接提示用户处理额度问题。
        if _looks_like_quota(exc):
            print("Gemini API quota/rate limit error (429/RESOURCE_EXHAUSTED).")
            print("Details:", exc)
            return

        # RECITATION：Gemini 以“引用风险”提前终止输出（不是代码错），我们自动重试一次更严格的提示。
        if _looks_like_recitation(exc):
            print("Gemini terminated the response early with finish_reason=RECITATION. Retrying once...")
            safer_question = (
                "In your own words, give a brief (2-3 sentences) summary of who Alan Turing was, "
                "then compute 5 + 12.5. Do not quote any source."
            )
            try:
                result = await agent.run(user_msg=safer_question)
            except Exception as exc2:
                # 如果仍然 RECITATION，为了让示例“可跑通”，降级走工具直接计算/查询（不依赖 LLM 输出）。
                if _looks_like_recitation(exc2):
                    print("Still RECITATION after retry. Falling back to direct tool calls (no LLM).")
                    turing = search_wikipedia("Alan Turing")
                    total = add(5, 12.5)
                    print("\n--- Final Answer (Fallback) ---")
                    print(f"{turing}\n\n5 + 12.5 = {total}")
                    print("\n--- Agent Finished ---")
                    return

                print("ReAct retry failed.")
                print("Details:", exc2)
                return

        # 其他未知异常：打印简要信息并退出（不再抛出大堆栈）。
        print("ReAct Agent call failed for an unexpected reason.")
        print("Details:", exc)
        return

    print("\n--- Final Answer ---")
    print(result.response.content)

    print("\n--- Agent Finished ---")
    # 如需查看 ReAct 的 system prompt，可取消注释：
    # print("\n--- System Prompt ---")
    # print(agent.formatter.system_header)
    # print("---------------------\n")


if __name__ == "__main__":
    # 不使用 asyncio.run：google.genai/aiohttp 在 Windows 上偶发在退出阶段触发
    # “Fatal error on SSL transport / Event loop is closed” 的清理噪音。
    # 手动管理事件循环，确保异步生成器/残留任务在 loop 关闭前被处理。
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
        # 给底层连接一个短暂的收尾时间，减少退出噪音
        loop.run_until_complete(asyncio.sleep(0.05))
        loop.run_until_complete(loop.shutdown_asyncgens())
        gc.collect()
    finally:
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()
