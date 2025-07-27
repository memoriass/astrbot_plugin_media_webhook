# 媒体处理器模块

这个模块提供了模块化的媒体数据处理功能，支持多种媒体服务器的数据转换和标准化。

## 架构概述

### 处理器层次结构

```
BaseMediaProcessor (抽象基类)
├── EmbyProcessor (Emby 专用处理器)
├── JellyfinProcessor (Jellyfin 专用处理器)
├── PlexProcessor (Plex 专用处理器)
└── GenericProcessor (通用处理器)
```

### 处理器管理器

`ProcessorManager` 负责：
- 管理所有处理器实例
- 自动检测数据源类型
- 调度合适的处理器
- 提供统一的处理接口

## 处理器功能

### 1. EmbyProcessor
- **检测特征**: `Item` 和 `Server` 字段，User-Agent 包含 "emby"
- **专门处理**: Emby 媒体服务器的 webhook 数据
- **图片处理**: 构建 Emby 图片 URL
- **元数据提取**: 演员、导演、制片公司、评分等

### 2. JellyfinProcessor  
- **检测特征**: `ItemType` 或 `SeriesName` 字段，User-Agent 包含 "jellyfin"
- **专门处理**: Jellyfin 媒体服务器的 webhook 数据
- **图片处理**: 构建 Jellyfin 图片 URL
- **流媒体信息**: 视频编解码器、分辨率、音频信息等

### 3. PlexProcessor
- **检测特征**: `Metadata` 或 `Player` 字段，User-Agent 包含 "plex"
- **专门处理**: Plex 媒体服务器的 webhook 数据
- **播放器信息**: 播放器标题、UUID、用户信息等
- **时长处理**: Plex 毫秒格式转换

### 4. GenericProcessor
- **检测特征**: 可以处理任何数据（降级处理器）
- **通用处理**: 未知来源或标准格式的媒体数据
- **字段映射**: 智能匹配多种可能的字段名
- **类型标准化**: 统一媒体类型命名

### 5. AniRSSHandler (独立处理器)
- **检测特征**: `meassage` 字段或 Ani-RSS 模板变量
- **专门处理**: Ani-RSS 动漫下载通知数据
- **独立逻辑**: 不走标准处理器流程，使用独立的消息格式
- **模板支持**: 支持 Ani-RSS 文本模板和 JSON 消息格式
- **图片提取**: 自动提取通知中的图片内容
- **Emoji支持**: 保留 `${emoji}` 模板变量支持

## 标准数据格式

所有处理器都将输入数据转换为统一的标准格式：

```python
{
    "item_type": "Episode",           # 媒体类型
    "series_name": "剧集名称",         # 剧集名称
    "item_name": "集名称",            # 单集名称
    "season_number": "1",             # 季数
    "episode_number": "1",            # 集数
    "year": "2024",                   # 年份
    "overview": "剧情简介",           # 简介
    "runtime": "45分钟",              # 时长
    "image_url": "https://...",       # 图片URL
    "source_data": "emby"            # 数据源
}
```

## 使用示例

### 基本使用

```python
from processors import ProcessorManager, AniRSSHandler

# 初始化管理器
manager = ProcessorManager()

# 自动检测并处理数据
result = manager.convert_to_standard(webhook_data, headers=request_headers)

# 手动指定处理器
result = manager.convert_to_standard(webhook_data, source="emby")
```

### Ani-RSS 独立处理

```python
from processors import AniRSSHandler

# 初始化 Ani-RSS 处理器
ani_handler = AniRSSHandler()

# 检测 Ani-RSS 格式
is_ani_rss, data, format_type = ani_handler.detect_ani_rss_format(body_text)

if is_ani_rss:
    # 处理 Ani-RSS 数据（独立逻辑）
    message_payload = ani_handler.process_ani_rss_data(data, format_type)
    # 注意：Ani-RSS 不使用标准处理器流程
```

### 添加自定义处理器

```python
from processors import BaseMediaProcessor, ProcessorManager

class CustomProcessor(BaseMediaProcessor):
    def can_handle(self, data: dict, headers: dict = None) -> bool:
        return "custom_field" in data
    
    def convert_to_standard(self, data: dict, headers: dict = None) -> dict:
        return self.create_standard_data(
            item_type=data.get("type", "Episode"),
            series_name=data.get("show_name", ""),
            # ... 其他字段映射
        )

# 添加到管理器
manager = ProcessorManager()
manager.add_processor(CustomProcessor(), priority=0)
```

## 扩展功能

### 元数据提取
每个处理器都提供专门的元数据提取方法：
- `extract_emby_metadata()` - Emby 特有元数据
- `extract_jellyfin_metadata()` - Jellyfin 特有元数据  
- `extract_plex_metadata()` - Plex 特有元数据
- `extract_generic_metadata()` - 通用元数据

### 处理器测试
```python
# 测试特定处理器
test_result = manager.test_processor("emby", test_data, headers)
print(test_result["conversion_success"])
```

### 处理器信息
```python
# 获取所有处理器信息
info = manager.get_processor_info()
print(f"总处理器数: {info['total_processors']}")
```

## 特殊说明

### Ani-RSS 处理器的独立性

**重要**: `AniRSSHandler` 虽然位于 processors 文件夹中，但它**不是标准处理器系统的一部分**：

1. **独立检测**: 使用自己的 `detect_ani_rss_format()` 方法
2. **独立处理**: 使用自己的 `process_ani_rss_data()` 方法
3. **独立消息格式**: 不转换为标准媒体数据格式
4. **独立验证**: 使用自己的 `validate_ani_rss_message()` 方法

这种设计是因为 Ani-RSS 的数据结构和处理需求与传统媒体服务器完全不同。

### Emoji 处理策略

**重要变更**: 从 v1.0.15 开始，标准媒体处理器**不再使用 emoji**：

1. **标准处理器**: 移除了所有 emoji 相关逻辑，消息标题使用纯文本
2. **Ani-RSS 处理器**: **保留** `${emoji}` 模板变量支持，因为这是 Ani-RSS 的核心功能
3. **设计理念**: 标准媒体通知使用简洁的文本格式，Ani-RSS 保持其特有的表现力

**示例对比**:
- 标准处理器: "新剧集上线" (无emoji)
- Ani-RSS: "${emoji} ${action}: ${title}" (保留emoji模板)

## 配置选项

处理器支持以下配置：
- **优先级排序**: 控制处理器检测顺序
- **动态添加/移除**: 运行时管理处理器
- **降级处理**: 自动使用通用处理器作为后备

## 最佳实践

1. **优先使用自动检测**: 让 ProcessorManager 自动选择合适的处理器
2. **验证输出数据**: 使用 `validate_standard_data()` 验证转换结果
3. **错误处理**: 所有处理器都有完整的异常处理
4. **日志记录**: 详细的调试和错误日志便于问题排查
5. **扩展性**: 通过继承 BaseMediaProcessor 轻松添加新的处理器

## 性能优化

- **缓存机制**: 处理器结果可以被缓存
- **懒加载**: 处理器按需实例化
- **批量处理**: 支持批量数据转换
- **内存优化**: 避免大对象的重复创建
