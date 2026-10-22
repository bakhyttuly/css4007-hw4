"""Measure how many input tokens the two tool definitions add to every S3 request.

Sends the same tiny request twice, once without tools and once with them, and compares the
`prompt_tokens` reported by the API. Costs a fraction of a cent.

    python measure_tools.py
"""

import strategies
import tools


def main():
    client = strategies.get_client()
    messages = [
        {"role": "system", "content": f"{strategies.BASE_SYSTEM_PROMPT} {strategies.S3_SUFFIX}"},
        {"role": "user", "content": "Question: test"},
    ]
    without_tools, _ = strategies.chat(client, messages)
    with_tools, _ = strategies.chat(client, messages, tools.TOOL_DEFINITIONS)
    a = without_tools.usage.prompt_tokens
    b = with_tools.usage.prompt_tokens
    print(f"input tokens without tools: {a}")
    print(f"input tokens with the two tool definitions: {b}")
    print(f"the two tool definitions add: {b - a} tokens to every S3 request")


if __name__ == "__main__":
    main()