from openai import OpenAI

# api_key = config.get("llm", "api_key")  # LM Studio 本地不需要真实 key
api_key = "lm-studio"

client = OpenAI(
    api_key=api_key,
    base_url="http://localhost:1234/v1",
)

question = input("请输入问题: ")

try:
    stream = client.chat.completions.create(
        model="local-model",
        messages=[{"role": "user", "content": question}],
        stream=True,  # 开启流式输出
    )
except Exception as e:
    print("请求失败，请检查 LM Studio 是否已启动")
    print(f"错误信息: {e}")
else:
    printed = False
    try:
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                print(delta, end="", flush=True)
                printed = True
        if printed:
            print()
    except Exception as e:
        print()
        print("流式请求中断，请检查 LM Studio 是否已启动")
        print(f"错误信息: {e}")
