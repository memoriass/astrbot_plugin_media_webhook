"""
适配器测试脚本
用于测试不同协议适配器的功能
"""

import asyncio
from typing import Any, Dict
from processors.adapter_type import AdapterFactory, AdapterType


class MockBotClient:
    """模拟的机器人客户端"""
    
    def __init__(self, platform_name: str):
        self.platform_name = platform_name
        self.call_history = []
    
    async def call_action(self, action: str, **kwargs) -> Dict[str, Any]:
        """模拟API调用"""
        call_info = {
            "action": action,
            "kwargs": kwargs,
            "platform": self.platform_name
        }
        self.call_history.append(call_info)
        
        print(f"[{self.platform_name}] 调用API: {action}")
        print(f"参数: {kwargs}")
        
        # 模拟返回结果
        return {
            "message_id": 12345,
            "status": "ok"
        }
    
    def get_call_history(self):
        """获取调用历史"""
        return self.call_history


async def test_adapter(adapter_type: str, platform_name: str):
    """测试指定适配器"""
    print(f"\n{'='*50}")
    print(f"测试适配器: {adapter_type} (平台: {platform_name})")
    print(f"{'='*50}")
    
    try:
        # 创建适配器
        adapter = AdapterFactory.create_adapter(platform_name, adapter_type)
        print(f"✅ 适配器创建成功: {adapter.__class__.__name__}")
        
        # 获取适配器信息
        info = adapter.get_adapter_info()
        print(f"📋 适配器信息:")
        print(f"  名称: {info.get('name')}")
        print(f"  版本: {info.get('version')}")
        print(f"  描述: {info.get('description')}")
        print(f"  支持API: {', '.join(info.get('supported_apis', []))}")
        print(f"  功能特性: {', '.join(info.get('features', []))}")
        
        # 创建模拟客户端
        mock_client = MockBotClient(platform_name)
        
        # 准备测试消息
        test_messages = [
            {
                "message_text": "🎬 新电影通知：《测试电影》已添加到媒体库",
                "image_url": "https://example.com/poster1.jpg"
            },
            {
                "message_text": "📺 新剧集通知：《测试剧集》S01E01 已添加",
                "image_url": None
            },
            {
                "message_text": "🎵 新音乐通知：《测试专辑》已添加到音乐库"
            }
        ]
        
        # 测试发送消息
        print(f"\n🧪 测试发送 {len(test_messages)} 条消息...")
        result = await adapter.send_forward_messages(
            bot_client=mock_client,
            group_id="123456789",
            messages=test_messages,
            sender_id="2659908767",
            sender_name="媒体通知测试"
        )
        
        # 检查结果
        if result.get("success"):
            print(f"✅ 发送成功!")
            print(f"  消息ID: {result.get('message_id')}")
        else:
            print(f"❌ 发送失败: {result.get('error')}")
        
        # 显示API调用历史
        print(f"\n📞 API调用历史:")
        for i, call in enumerate(mock_client.get_call_history(), 1):
            print(f"  {i}. {call['action']}")
            print(f"     参数: {call['kwargs']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        return False


async def test_all_adapters():
    """测试所有适配器"""
    print("🚀 开始测试所有适配器...")
    
    test_cases = [
        (AdapterType.NAPCAT, "napcat"),
        (AdapterType.NAPCAT, "aiocqhttp"),
        (AdapterType.LLONEBOT, "llonebot"),
        (AdapterType.GENERIC, "generic"),
        (None, "unknown_platform")  # 测试自动推断
    ]
    
    results = []
    for adapter_type, platform_name in test_cases:
        success = await test_adapter(adapter_type, platform_name)
        results.append((adapter_type or "auto", platform_name, success))
    
    # 显示测试总结
    print(f"\n{'='*50}")
    print("📊 测试总结")
    print(f"{'='*50}")
    
    success_count = sum(1 for _, _, success in results if success)
    total_count = len(results)
    
    for adapter_type, platform_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"  {adapter_type:10} | {platform_name:15} | {status}")
    
    print(f"\n总计: {success_count}/{total_count} 个测试通过")
    
    if success_count == total_count:
        print("🎉 所有测试都通过了!")
    else:
        print("⚠️ 部分测试失败，请检查错误信息")


async def test_factory_methods():
    """测试工厂方法"""
    print(f"\n{'='*50}")
    print("测试工厂方法")
    print(f"{'='*50}")
    
    # 测试获取支持的类型
    supported_types = AdapterFactory.get_supported_types()
    print(f"📋 支持的适配器类型: {', '.join(supported_types)}")
    
    # 测试获取适配器信息
    for adapter_type in supported_types:
        info = AdapterFactory.get_adapter_info(adapter_type)
        print(f"\n🔧 {adapter_type} 适配器信息:")
        print(f"  名称: {info.get('name')}")
        print(f"  描述: {info.get('description')}")
        print(f"  功能: {', '.join(info.get('features', []))}")


if __name__ == "__main__":
    async def main():
        print("🧪 适配器测试工具")
        print("=" * 50)
        
        # 测试工厂方法
        await test_factory_methods()
        
        # 测试所有适配器
        await test_all_adapters()
        
        print("\n✨ 测试完成!")
    
    asyncio.run(main())
