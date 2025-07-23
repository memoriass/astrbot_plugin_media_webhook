# 通知来源识别和平台前缀功能指南

## 概述

媒体通知 Webhook 插件现在支持智能识别通知来源，并为不同发送平台添加前缀图标，让用户能够清楚地知道消息来自哪个媒体服务器以及通过哪个平台发送。

## 功能特性

### 🔍 智能来源识别

插件能够自动识别以下媒体服务器和工具：

| 来源 | 识别方式 | 显示名称 |
|------|----------|----------|
| **Jellyfin** | User-Agent、server_name、数据内容 | Jellyfin |
| **Emby** | User-Agent、application字段、数据内容 | Emby |
| **Plex** | User-Agent、product字段、数据内容 | Plex |
| **Sonarr** | 数据内容特征 | Sonarr |
| **Radarr** | 数据内容特征 | Radarr |
| **Overseerr** | 数据内容特征 | Overseerr |
| **Tautulli** | 数据内容特征 | Tautulli |
| **Ani-RSS** | 配置字段特征、数据内容 | Ani-RSS |

### 🎯 平台前缀图标

不同发送平台使用不同的前缀图标：

| 平台 | 前缀图标 | 说明 |
|------|----------|------|
| **aiocqhttp** | 🤖 | QQ 机器人 |
| **telegram** | ✈️ | Telegram |
| **gewechat** | 💬 | 微信个人号 |
| **qqofficial** | 🤖 | QQ 官方接口 |
| **lark** | 🚀 | 飞书 |
| **dingtalk** | 📱 | 钉钉 |
| **discord** | 🎮 | Discord |
| **wecom** | 💼 | 企业微信 |
| **其他** | 📢 | 默认图标 |

## 消息格式示例

### 完整格式
```
🤖 📺 新单集上线 [Jellyfin]

剧集名称: 进击的巨人 (2023)
集号: S04E28
集名称: 最终话

剧情简介:
故事的最终章节，艾伦的真正目的即将揭晓...

时长: 24分钟
```

### 不同配置下的格式

**仅显示平台前缀**：
```
🤖 📺 新单集上线

剧集名称: 进击的巨人 (2023)
...
```

**仅显示来源信息**：
```
📺 新单集上线 [Jellyfin]

剧集名称: 进击的巨人 (2023)
...
```

**最简格式**：
```
📺 新单集上线

剧集名称: 进击的巨人 (2023)
...
```

## 配置选项

### show_platform_prefix
- **类型**: 布尔值
- **默认值**: true
- **说明**: 是否在消息中显示发送平台的前缀图标

### show_source_info
- **类型**: 布尔值
- **默认值**: true
- **说明**: 是否在消息中显示通知来源信息

### 配置示例
```json
{
  "platform_name": "aiocqhttp",
  "show_platform_prefix": true,
  "show_source_info": true
}
```

## 来源检测机制

### 1. User-Agent 检测
插件首先检查 HTTP 请求的 User-Agent 头：
```
User-Agent: Jellyfin/10.8.0
User-Agent: Emby Server/4.7.0
User-Agent: Plex/1.28.0
```

### 2. 数据字段检测
检查请求数据中的特定字段：
```json
{
  "server_name": "MyJellyfin",
  "application": "Emby",
  "product": "Plex"
}
```

### 3. 内容特征检测
分析请求数据中的关键词：
```json
{
  "notification_type": "sonarr.episode.downloaded",
  "data": "radarr movie added"
}
```

## 使用场景

### 🏠 家庭媒体中心
```
🤖 📺 新单集上线 [Jellyfin]
🤖 🎬 新电影上线 [Radarr]
🤖 📺 新剧集下载完成 [Sonarr]
🤖 📺 新单集上线 [Ani-RSS]
```

### 📱 多平台通知
```
✈️ 📺 新单集上线 [Emby]     # Telegram
💬 🎬 新电影上线 [Plex]      # 微信
🎮 📺 新单集上线 [Jellyfin]  # Discord
```

### 🔧 调试和监控
通过前缀和来源信息，可以快速识别：
- 消息来自哪个媒体服务器
- 通过哪个平台发送
- 便于问题排查和系统监控

## 自定义扩展

### 添加新的来源检测
如需支持新的媒体服务器，可以修改 `detect_notification_source()` 方法：

```python
def detect_notification_source(self, data, headers):
    # 添加新的检测逻辑
    if "new_media_server" in str(data).lower():
        return "new_server"
    
    # 现有逻辑...
```

### 添加新的平台前缀
在 `platform_prefix_map` 中添加新平台：

```python
self.platform_prefix_map = {
    "new_platform": "🆕",
    # 现有映射...
}
```

## 最佳实践

### 🎯 推荐配置

**生产环境**：
```json
{
  "show_platform_prefix": true,
  "show_source_info": true
}
```
- 完整的信息显示，便于识别和管理

**简洁模式**：
```json
{
  "show_platform_prefix": false,
  "show_source_info": false
}
```
- 最简洁的消息格式，减少视觉干扰

**调试模式**：
```json
{
  "show_platform_prefix": true,
  "show_source_info": true
}
```
- 显示完整信息，便于问题排查

### 🔧 故障排除

**来源识别不准确**：
1. 检查 webhook 请求的 User-Agent
2. 查看请求数据中的特征字段
3. 根据需要调整检测逻辑

**平台前缀不显示**：
1. 确认 `show_platform_prefix` 配置为 true
2. 检查 `platform_name` 配置是否正确
3. 验证平台名称在映射表中存在

## 兼容性说明

### 向后兼容
- 所有现有配置继续有效
- 默认启用新功能，不影响现有用户
- 可以通过配置关闭新功能

### 平台支持
- 所有 AstrBot 支持的平台都可以使用前缀功能
- 来源检测适用于所有 webhook 通知
- 不依赖特定的消息平台特性

## 示例配置文件

```json
{
  "webhook_port": 60071,
  "webhook_path": "/media-webhook",
  "group_id": "123456789",
  "platform_name": "aiocqhttp",
  "batch_min_size": 3,
  "show_platform_prefix": true,
  "show_source_info": true,
  "cache_ttl_seconds": 300,
  "batch_interval_seconds": 300
}
```

这个配置将产生如下格式的消息：
```
🤖 📺 新单集上线 [Jellyfin]
```
