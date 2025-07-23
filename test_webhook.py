#!/usr/bin/env python3
"""
Media Webhook 插件测试脚本
用于测试 webhook 接收和消息处理功能
"""

import asyncio
import json
import aiohttp
import time
from typing import Dict, Any


class WebhookTester:
    def __init__(self, webhook_url: str = "http://localhost:60071/media-webhook"):
        self.webhook_url = webhook_url
        
    async def send_test_request(self, data: Dict[str, Any]) -> bool:
        """发送测试请求到webhook"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=data,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    response_text = await response.text()
                    print(f"状态码: {response.status}")
                    print(f"响应: {response_text}")
                    return response.status == 200
        except Exception as e:
            print(f"请求失败: {e}")
            return False

    def create_test_data(self, item_type: str = "Episode") -> Dict[str, Any]:
        """创建测试数据"""
        base_data = {
            "series_name": "测试剧集",
            "year": "2024",
            "item_name": "测试内容",
            "overview": "这是一个测试剧情简介，用于验证webhook功能是否正常工作。",
            "runtime": "45分钟",
            "image_url": "https://via.placeholder.com/300x450/0066cc/ffffff?text=Test+Media"
        }
        
        if item_type == "Episode":
            base_data.update({
                "item_type": "Episode",
                "season_number": 1,
                "episode_number": 1,
                "item_name": "第一集"
            })
        elif item_type == "Season":
            base_data.update({
                "item_type": "Season",
                "season_number": 1,
                "item_name": "第一季"
            })
        elif item_type == "Movie":
            base_data.update({
                "item_type": "Movie",
                "item_name": "测试电影"
            })
        
        return base_data

    async def test_single_request(self):
        """测试单个请求"""
        print("=== 测试单个请求 ===")
        data = self.create_test_data("Episode")
        success = await self.send_test_request(data)
        print(f"单个请求测试: {'成功' if success else '失败'}\n")
        return success

    async def test_duplicate_requests(self):
        """测试重复请求检测"""
        print("=== 测试重复请求检测 ===")
        data = self.create_test_data("Movie")
        
        # 发送第一个请求
        print("发送第一个请求...")
        success1 = await self.send_test_request(data)
        
        # 立即发送相同请求
        print("发送重复请求...")
        success2 = await self.send_test_request(data)
        
        print(f"重复请求测试: {'成功' if success1 and success2 else '失败'}\n")
        return success1 and success2

    async def test_batch_requests(self):
        """测试批量请求"""
        print("=== 测试批量请求 ===")
        
        # 发送多个不同的请求
        for i in range(5):
            data = self.create_test_data("Episode")
            data["episode_number"] = i + 1
            data["item_name"] = f"第{i+1}集"
            
            print(f"发送第 {i+1} 个请求...")
            success = await self.send_test_request(data)
            if not success:
                print(f"第 {i+1} 个请求失败")
                return False
            
            # 短暂延迟避免被当作重复请求
            await asyncio.sleep(0.1)
        
        print("批量请求测试: 成功\n")
        return True

    async def test_invalid_requests(self):
        """测试无效请求"""
        print("=== 测试无效请求 ===")
        
        # 测试空请求体
        print("测试空请求体...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, data="") as response:
                    print(f"空请求体状态码: {response.status}")
        except Exception as e:
            print(f"空请求体测试出错: {e}")
        
        # 测试无效JSON
        print("测试无效JSON...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    data="invalid json",
                    headers={"Content-Type": "application/json"}
                ) as response:
                    print(f"无效JSON状态码: {response.status}")
        except Exception as e:
            print(f"无效JSON测试出错: {e}")
        
        print("无效请求测试: 完成\n")
        return True

    async def run_all_tests(self):
        """运行所有测试"""
        print("开始 Media Webhook 插件测试...\n")
        
        tests = [
            self.test_single_request,
            self.test_duplicate_requests,
            self.test_batch_requests,
            self.test_invalid_requests
        ]
        
        results = []
        for test in tests:
            try:
                result = await test()
                results.append(result)
            except Exception as e:
                print(f"测试出错: {e}")
                results.append(False)
        
        print("=== 测试总结 ===")
        print(f"总测试数: {len(tests)}")
        print(f"成功数: {sum(results)}")
        print(f"失败数: {len(tests) - sum(results)}")
        
        if all(results):
            print("🎉 所有测试通过！")
        else:
            print("❌ 部分测试失败，请检查插件配置和运行状态")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Media Webhook 插件测试工具")
    parser.add_argument(
        "--url", 
        default="http://localhost:60071/media-webhook",
        help="Webhook URL (默认: http://localhost:60071/media-webhook)"
    )
    parser.add_argument(
        "--test",
        choices=["single", "duplicate", "batch", "invalid", "all"],
        default="all",
        help="要运行的测试类型"
    )
    
    args = parser.parse_args()
    
    tester = WebhookTester(args.url)
    
    if args.test == "single":
        await tester.test_single_request()
    elif args.test == "duplicate":
        await tester.test_duplicate_requests()
    elif args.test == "batch":
        await tester.test_batch_requests()
    elif args.test == "invalid":
        await tester.test_invalid_requests()
    else:
        await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
