#!/usr/bin/env python3
"""
API 测试脚本

测试 Vlinders-Server 的各个 API 端点
"""
import requests
import json
import sys


BASE_URL = "http://localhost:8000"
INTERNAL_SECRET = "your-secret-key"  # 从 .env 读取


def test_health():
    """测试健康检查"""
    print("🔍 Testing /health endpoint...")

    response = requests.get(f"{BASE_URL}/health")

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Health check passed")
        print(f"   Status: {data['status']}")
        print(f"   Models: {data['models_loaded']}")
        print(f"   GPU: {data['gpu_count']} available")
        return True
    else:
        print(f"❌ Health check failed: {response.status_code}")
        return False


def test_chat():
    """测试聊天接口"""
    print("\n🔍 Testing /internal/chat endpoint...")

    headers = {
        "Content-Type": "application/json",
        "X-Internal-Auth": INTERNAL_SECRET
    }

    payload = {
        "model": "minimax-m2.5",
        "messages": [
            {"role": "user", "content": "Hello! Please respond with 'Hi there!'"}
        ],
        "max_tokens": 50,
        "temperature": 0.7
    }

    response = requests.post(
        f"{BASE_URL}/internal/chat",
        headers=headers,
        json=payload
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Chat request successful")
        print(f"   Response: {data['choices'][0]['message']['content'][:100]}")
        print(f"   Tokens: {data['usage']['total_tokens']}")
        return True
    else:
        print(f"❌ Chat request failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_models():
    """测试模型列表"""
    print("\n🔍 Testing /internal/models endpoint...")

    headers = {
        "X-Internal-Auth": INTERNAL_SECRET
    }

    response = requests.get(
        f"{BASE_URL}/internal/models",
        headers=headers
    )

    if response.status_code == 200:
        data = response.json()
        print(f"✅ Models list retrieved")
        print(f"   Models: {[m['id'] for m in data['data']]}")
        return True
    else:
        print(f"❌ Models list failed: {response.status_code}")
        return False


def main():
    """运行所有测试"""
    print("🚀 Starting API tests...\n")

    results = []

    # 测试健康检查
    results.append(("Health Check", test_health()))

    # 测试模型列表
    results.append(("Models List", test_models()))

    # 测试聊天接口
    results.append(("Chat API", test_chat()))

    # 打印总结
    print("\n" + "="*50)
    print("📊 Test Summary:")
    print("="*50)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")

    # 返回退出码
    all_passed = all(result[1] for result in results)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
