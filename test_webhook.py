#!/usr/bin/env python3
"""
媒体 Webhook 插件测试脚本
测试各个模块与智能发送逻辑
"""

import json
import requests
import time
from typing import Dict, Any

# Webhook 服务器地址
WEBHOOK_URL = "http://localhost:60071/media-webhook"

def send_webhook(data: Dict[str, Any], description: str = ""):
    """发送 Webhook 请求"""
    print(f"\n🚀 发送测试: {description}")
    print(f"📤 数据: {json.dumps(data, ensure_ascii=False, indent=2)}")
    
    try:
        response = requests.post(
            WEBHOOK_URL,
            json=data,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        
        print(f"✅ 响应状态: {response.status_code}")
        print(f"📥 响应内容: {response.text}")
        
    except Exception as e:
        print(f"❌ 请求失败: {e}")
    
    print("-" * 50)

def test_emby_webhook():
    """测试 Emby Webhook"""
    emby_data = {
        "Event": "library.new",
        "Item": {
            "Name": "不时用俄语小声说真心话的邻桌艾莉同学",
            "Id": "12345",
            "Type": "Episode",
            "SeriesName": "不时用俄语小声说真心话的邻桌艾莉同学",
            "SeasonNumber": 1,
            "EpisodeNumber": 1,
            "Year": 2024,
            "Overview": "艾莉是一个可爱的俄罗斯女孩，她总是用俄语小声说出自己的真心话。",
            "RunTimeTicks": 14400000000,  # 24分钟
            "ImageTags": {
                "Primary": "abc123"
            }
        },
        "Server": {
            "Name": "Emby Server",
            "Id": "server123",
            "Url": "http://localhost:8096"
        }
    }
    
    send_webhook(emby_data, "Emby 剧集通知 (标准媒体消息)")

def test_jellyfin_webhook():
    """测试 Jellyfin Webhook"""
    jellyfin_data = {
        "NotificationType": "ItemAdded",
        "Name": "间谍过家家",
        "ItemId": "67890",
        "ItemType": "Episode",
        "SeriesName": "间谍过家家",
        "SeasonNumber": 2,
        "EpisodeNumber": 5,
        "Year": 2024,
        "Overview": "黄昏、约儿和阿尼亚的温馨家庭生活继续。",
        "RunTimeTicks": 15000000000,  # 25分钟
        "ServerId": "jellyfin123",
        "ServerUrl": "http://localhost:8096"
    }
    
    send_webhook(jellyfin_data, "Jellyfin 剧集通知 (标准媒体消息)")

def test_plex_webhook():
    """测试 Plex Webhook"""
    plex_data = {
        "event": "library.new",
        "Metadata": {
            "title": "葬送的芙莉莲",
            "type": "episode",
            "grandparentTitle": "葬送的芙莉莲",
            "parentIndex": 1,
            "index": 10,
            "year": 2024,
            "summary": "在勇者死后的世界，精灵法师芙莉莲踏上了新的旅程。",
            "duration": 1440000,  # 24分钟 (毫秒)
            "thumb": "/library/metadata/12345/thumb/1234567890"
        },
        "Server": {
            "title": "Plex Server",
            "uuid": "plex123"
        }
    }
    
    send_webhook(plex_data, "Plex 剧集通知 (标准媒体消息)")

def test_ani_rss_webhook():
    """测试 Ani-RSS Webhook"""
    ani_rss_data = {
        "text_template": "${emoji} ${action}: ${title}\n季度: ${season}\n集数: ${episode}\n大小: ${size}\n发布组: ${group}",
        "emoji": "📺",
        "action": "新番上线",
        "title": "魔法少女小圆",
        "season": "第1季",
        "episode": "第12集",
        "size": "1.2GB",
        "group": "Sakurato",
        "image_url": "https://example.com/madoka.jpg"
    }
    
    send_webhook(ani_rss_data, "Ani-RSS 模板通知 (独立发送)")

def test_ani_rss_message_format():
    """测试 Ani-RSS 消息格式"""
    ani_rss_message = {
        "meassage": [
            {
                "type": "text",
                "data": {
                    "text": "📺 新番上线: 进击的巨人 最终季\n季度: 第4季\n集数: 第28集\n大小: 1.5GB\n发布组: SubsPlease"
                }
            },
            {
                "type": "image",
                "data": {
                    "url": "https://example.com/aot.jpg"
                }
            }
        ]
    }
    
    send_webhook(ani_rss_message, "Ani-RSS 消息格式 (独立发送)")

def test_batch_media_messages():
    """测试批量媒体消息"""
    print("\n🎯 测试批量媒体消息发送逻辑")
    print("发送多条标准媒体消息，测试批量处理器...")
    
    # 发送多条 Emby 消息
    for i in range(3):
        emby_data = {
            "Event": "library.new",
            "Item": {
                "Name": f"测试剧集 {i+1}",
                "Id": f"test{i+1}",
                "Type": "Episode",
                "SeriesName": "测试系列",
                "SeasonNumber": 1,
                "EpisodeNumber": i+1,
                "Year": 2024,
                "Overview": f"这是第{i+1}集的测试内容。",
                "RunTimeTicks": 14400000000
            },
            "Server": {
                "Name": "Test Emby Server",
                "Id": f"server{i+1}"
            }
        }
        
        send_webhook(emby_data, f"批量测试 - Emby 消息 {i+1}/3")
        time.sleep(1)  # 短暂延迟

def test_mixed_messages():
    """测试混合消息类型"""
    print("\n🎯 测试混合消息类型")
    print("发送 Ani-RSS 和标准媒体消息的混合，测试智能分发逻辑...")
    
    # 先发送一条 Ani-RSS
    test_ani_rss_webhook()
    time.sleep(1)
    
    # 再发送一条标准媒体
    test_emby_webhook()
    time.sleep(1)
    
    # 再发送一条 Ani-RSS
    test_ani_rss_message_format()

def main():
    """主测试函数"""
    print("🧪 媒体 Webhook 插件测试开始")
    print("=" * 60)
    
    # 等待服务器启动
    print("⏳ 等待 Webhook 服务器启动...")
    time.sleep(2)
    
    # 测试各个模块
    print("\n📋 测试计划:")
    print("1. 测试 Emby 标准媒体消息")
    print("2. 测试 Jellyfin 标准媒体消息") 
    print("3. 测试 Plex 标准媒体消息")
    print("4. 测试 Ani-RSS 模板格式")
    print("5. 测试 Ani-RSS 消息格式")
    print("6. 测试批量媒体消息")
    print("7. 测试混合消息类型")
    
    input("\n按 Enter 键开始测试...")
    
    # 1. 测试标准媒体消息
    test_emby_webhook()
    time.sleep(2)
    
    test_jellyfin_webhook()
    time.sleep(2)
    
    test_plex_webhook()
    time.sleep(2)
    
    # 2. 测试 Ani-RSS 消息
    test_ani_rss_webhook()
    time.sleep(2)
    
    test_ani_rss_message_format()
    time.sleep(2)
    
    # 3. 测试批量处理
    test_batch_media_messages()
    time.sleep(5)  # 等待批量处理器处理
    
    # 4. 测试混合消息
    test_mixed_messages()
    
    print("\n✅ 所有测试完成!")
    print("请检查 AstrBot 日志以确认:")
    print("- 标准媒体消息使用批量发送逻辑")
    print("- Ani-RSS 消息使用独立发送逻辑")
    print("- TMDB 图片正确嵌入到消息中")
    print("- 批量处理器正确分离不同类型的消息")

if __name__ == "__main__":
    main()
