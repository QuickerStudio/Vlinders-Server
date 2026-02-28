"""
Vlinders-Server 使用示例

演示如何使用 Python 客户端调用 Vlinders-Server API
"""
import requests
import json
from typing import Iterator


class VlindersClient:
    """Vlinders-Server 客户端"""

    def __init__(self, base_url: str = "http://localhost:8000", api_key: str = ""):
        self.base_url = base_url
        self.api_key = api_key
        self.headers = {
            "Content-Type": "application/json",
            "X-Internal-Auth": api_key
        }

    def health_check(self) -> dict:
        """健康检查"""
        response = requests.get(f"{self.base_url}/health")
        response.raise_for_status()
        return response.json()

    def list_models(self) -> list:
        """列出可用模型"""
        response = requests.get(
            f"{self.base_url}/internal/models",
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()["data"]

    def chat(
        self,
        messages: list,
        model: str = "minimax-m2.5",
        max_tokens: int = 2048,
        temperature: float = 0.7,
        stream: bool = False
    ) -> dict | Iterator[dict]:
        """
        聊天接口

        Args:
            messages: 消息列表 [{"role": "user", "content": "..."}]
            model: 模型名称
            max_tokens: 最大生成 token 数
            temperature: 温度参数
            stream: 是否流式返回

        Returns:
            非流式: 完整响应字典
            流式: 响应块迭代器
        """
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream
        }

        if stream:
            return self._chat_stream(payload)
        else:
            return self._chat_complete(payload)

    def _chat_complete(self, payload: dict) -> dict:
        """非流式聊天"""
        response = requests.post(
            f"{self.base_url}/internal/chat",
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        return response.json()

    def _chat_stream(self, payload: dict) -> Iterator[dict]:
        """流式聊天"""
        response = requests.post(
            f"{self.base_url}/internal/chat/stream",
            headers=self.headers,
            json=payload,
            stream=True
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]  # 去掉 'data: ' 前缀
                    if data == '[DONE]':
                        break
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue


# ==================== 使用示例 ====================

def example_health_check():
    """示例: 健康检查"""
    print("=" * 50)
    print("示例 1: 健康检查")
    print("=" * 50)

    client = VlindersClient()
    health = client.health_check()

    print(f"状态: {health['status']}")
    print(f"已加载模型: {health['models_loaded']}")
    print(f"GPU 可用: {health['gpu_available']}")
    print(f"GPU 数量: {health['gpu_count']}")
    print()


def example_list_models():
    """示例: 列出模型"""
    print("=" * 50)
    print("示例 2: 列出模型")
    print("=" * 50)

    client = VlindersClient(api_key="your-secret-key")
    models = client.list_models()

    print("可用模型:")
    for model in models:
        print(f"  - {model['id']}")
    print()


def example_simple_chat():
    """示例: 简单对话"""
    print("=" * 50)
    print("示例 3: 简单对话")
    print("=" * 50)

    client = VlindersClient(api_key="your-secret-key")

    messages = [
        {"role": "user", "content": "你好,请用一句话介绍你自己"}
    ]

    response = client.chat(messages=messages, max_tokens=100)

    print(f"用户: {messages[0]['content']}")
    print(f"助手: {response['choices'][0]['message']['content']}")
    print(f"Token 使用: {response['usage']['total_tokens']}")
    print()


def example_multi_turn_chat():
    """示例: 多轮对话"""
    print("=" * 50)
    print("示例 4: 多轮对话")
    print("=" * 50)

    client = VlindersClient(api_key="your-secret-key")

    messages = [
        {"role": "user", "content": "请写一个 Python 函数计算斐波那契数列"},
        {"role": "assistant", "content": "好的,这是一个计算斐波那契数列的函数:\n\n```python\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)\n```"},
        {"role": "user", "content": "能否优化一下性能?"}
    ]

    response = client.chat(messages=messages, max_tokens=500)

    print("对话历史:")
    for msg in messages:
        print(f"{msg['role']}: {msg['content'][:50]}...")

    print(f"\n最新回复:")
    print(response['choices'][0]['message']['content'])
    print()


def example_streaming_chat():
    """示例: 流式对话"""
    print("=" * 50)
    print("示例 5: 流式对话")
    print("=" * 50)

    client = VlindersClient(api_key="your-secret-key")

    messages = [
        {"role": "user", "content": "请写一个关于 AI 的短故事"}
    ]

    print("用户: 请写一个关于 AI 的短故事")
    print("助手: ", end="", flush=True)

    for chunk in client.chat(messages=messages, stream=True, max_tokens=500):
        if 'choices' in chunk:
            delta = chunk['choices'][0].get('delta', {})
            content = delta.get('content', '')
            if content:
                print(content, end="", flush=True)

    print("\n")


def example_with_parameters():
    """示例: 自定义参数"""
    print("=" * 50)
    print("示例 6: 自定义参数")
    print("=" * 50)

    client = VlindersClient(api_key="your-secret-key")

    messages = [
        {"role": "user", "content": "生成 3 个创意的产品名称"}
    ]

    # 高温度 = 更有创意
    response = client.chat(
        messages=messages,
        max_tokens=200,
        temperature=1.2  # 更高的温度
    )

    print("高温度 (temperature=1.2) - 更有创意:")
    print(response['choices'][0]['message']['content'])
    print()

    # 低温度 = 更确定性
    response = client.chat(
        messages=messages,
        max_tokens=200,
        temperature=0.2  # 更低的温度
    )

    print("低温度 (temperature=0.2) - 更确定:")
    print(response['choices'][0]['message']['content'])
    print()


def example_error_handling():
    """示例: 错误处理"""
    print("=" * 50)
    print("示例 7: 错误处理")
    print("=" * 50)

    client = VlindersClient(api_key="wrong-key")

    try:
        messages = [{"role": "user", "content": "Hello"}]
        response = client.chat(messages=messages)
    except requests.exceptions.HTTPError as e:
        print(f"❌ 请求失败: {e}")
        print(f"   状态码: {e.response.status_code}")
        print(f"   错误信息: {e.response.text}")
    print()


if __name__ == "__main__":
    print("\n🚀 Vlinders-Server 使用示例\n")

    # 运行所有示例
    try:
        example_health_check()
        example_list_models()
        example_simple_chat()
        example_multi_turn_chat()
        example_streaming_chat()
        example_with_parameters()
        example_error_handling()
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        print("\n提示:")
        print("1. 确保 Vlinders-Server 正在运行: python -m vlinders_server.main")
        print("2. 确保 API 密钥正确: 检查 .env 文件中的 INTERNAL_SECRET")
        print("3. 确保模型已加载: 检查 configs/models.yaml")

    print("\n✅ 示例运行完成!")
