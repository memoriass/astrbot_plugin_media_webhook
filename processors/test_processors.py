"""
处理器测试脚本
用于验证各个处理器的功能
"""

from processor_manager import ProcessorManager
from ani_rss_handler import AniRSSHandler


def test_processor_manager():
    """测试处理器管理器"""
    print("=== 测试处理器管理器 ===")
    
    manager = ProcessorManager()
    
    # 获取处理器信息
    info = manager.get_processor_info()
    print(f"总处理器数: {info['total_processors']}")
    print("已注册的处理器:")
    for processor in info['processors']:
        print(f"  - {processor['name']}: {processor['source_name']}")
    
    print()


def test_emby_detection():
    """测试Emby数据检测"""
    print("=== 测试Emby数据检测 ===")
    
    manager = ProcessorManager()
    
    # 模拟Emby数据
    emby_data = {
        "Item": {
            "Type": "Episode",
            "Name": "测试集",
            "SeriesName": "测试剧集",
            "ParentIndexNumber": 1,
            "IndexNumber": 1
        },
        "Server": {
            "Url": "http://localhost:8096"
        }
    }
    
    # 检测数据源
    source = manager.detect_source(emby_data)
    print(f"检测到的数据源: {source}")
    
    # 转换数据
    result = manager.convert_to_standard(emby_data, source)
    if result:
        print("转换成功:")
        print(f"  类型: {result.get('item_type')}")
        print(f"  剧集名: {result.get('series_name')}")
        print(f"  集名: {result.get('item_name')}")
        print(f"  季数: {result.get('season_number')}")
        print(f"  集数: {result.get('episode_number')}")
    else:
        print("转换失败")
    
    print()


def test_ani_rss_detection():
    """测试Ani-RSS数据检测"""
    print("=== 测试Ani-RSS数据检测 ===")
    
    ani_handler = AniRSSHandler()
    
    # 模拟Ani-RSS JSON数据
    ani_rss_json = '''
    {
        "meassage": [
            {
                "type": "text",
                "data": {
                    "text": "动漫下载完成: 测试动漫 第01集"
                }
            },
            {
                "type": "image",
                "data": {
                    "url": "http://example.com/image.jpg"
                }
            }
        ]
    }
    '''
    
    # 检测格式
    is_ani_rss, data, format_type = ani_handler.detect_ani_rss_format(ani_rss_json)
    print(f"是否为Ani-RSS: {is_ani_rss}")
    print(f"格式类型: {format_type}")
    
    if is_ani_rss:
        # 处理数据
        message_payload = ani_handler.process_ani_rss_data(data, format_type)
        print("处理结果:")
        print(f"  消息文本: {message_payload.get('message_text')[:50]}...")
        print(f"  图片URL: {message_payload.get('image_url')}")
        print(f"  来源: {message_payload.get('source')}")
    
    print()


def test_ani_rss_template():
    """测试Ani-RSS模板检测"""
    print("=== 测试Ani-RSS模板检测 ===")
    
    ani_handler = AniRSSHandler()
    
    # 模拟Ani-RSS模板数据
    template_text = "${emoji} ${action}: ${title} ${season} 第${episode}集 已下载完成"
    
    # 检测格式
    is_ani_rss, data, format_type = ani_handler.detect_ani_rss_format(template_text)
    print(f"是否为Ani-RSS模板: {is_ani_rss}")
    print(f"格式类型: {format_type}")
    
    if is_ani_rss:
        # 处理数据
        message_payload = ani_handler.process_ani_rss_data(data, format_type)
        print("处理结果:")
        print(f"  消息文本: {message_payload.get('message_text')}")
        print(f"  来源: {message_payload.get('source')}")
    
    print()


def test_generic_processor():
    """测试通用处理器"""
    print("=== 测试通用处理器 ===")
    
    manager = ProcessorManager()
    
    # 模拟通用数据
    generic_data = {
        "type": "episode",
        "name": "测试集名",
        "series_name": "测试剧集名",
        "season_number": 1,
        "episode_number": 1,
        "year": 2024
    }
    
    # 检测数据源
    source = manager.detect_source(generic_data)
    print(f"检测到的数据源: {source}")
    
    # 转换数据
    result = manager.convert_to_standard(generic_data, source)
    if result:
        print("转换成功:")
        print(f"  类型: {result.get('item_type')}")
        print(f"  剧集名: {result.get('series_name')}")
        print(f"  集名: {result.get('item_name')}")
        print(f"  年份: {result.get('year')}")
    else:
        print("转换失败")
    
    print()


if __name__ == "__main__":
    print("开始处理器测试...\n")
    
    test_processor_manager()
    test_emby_detection()
    test_ani_rss_detection()
    test_ani_rss_template()
    test_generic_processor()
    
    print("测试完成!")
