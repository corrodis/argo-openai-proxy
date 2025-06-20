import openai

MODEL = "argo:gpt-4o"

client = openai.OpenAI(
    api_key="whatever+random",
    base_url="http://localhost:44498/v1",
)


def stream_chat_test():
    print("Running Chat Test with Streaming")

    prompt = ["Tell me something interesting about quantum mechanics."]
    # max_tokens = 5

    try:
        response = client.completions.create(
            model=MODEL,
            prompt=prompt,
            # max_tokens=max_tokens,
            stream=True,
        )
        print("Streaming Response:")
        for chunk in response:
            # Stream each chunk as it arrives
            print(chunk.choices[0].text, end="", flush=True)
    except Exception as e:
        print("\nError:", e)


if __name__ == "__main__":
    stream_chat_test()
