# 媒体通知 Webhook 插件

一个用于 AstrBot 的媒体通知 Webhook 插件，支持接收来自各种媒体服务器的通知，并转发到指定的群组。

## 功能特性

- 🎬 **多平台支持**: Jellyfin、Emby、Plex、Sonarr、Radarr、Ani-RSS 等
- 📱 **智能消息**: 自动格式化，包含剧集信息、封面图片
- 🔄 **防重复**: 智能去重，避免重复通知
- 📊 **批量优化**: 支持合并转发，减少消息刷屏
- 🎯 **平台识别**: 自动识别通知来源，添加平台前缀
- 🔧 **容错处理**: 完善的错误处理和 JSON 修复

## 快速开始

### 1. 配置插件
```json
{
  "webhook_port": 60071,
  "webhook_path": "/media-webhook",
  "group_id": "your-group-id",
  "platform_name": "aiocqhttp"
}
```

### 2. 配置媒体服务器
在您的媒体服务器中设置 Webhook URL：
```
http://your-bot-server:60071/media-webhook
```

### 3. 测试功能
```
/webhook test        # 使用 BGM.TV 真实数据测试
/webhook test static # 使用静态数据测试
/webhook status      # 查看插件状态
```

## 支持的服务器

| 服务器 | 状态 | 特殊说明 |
|--------|------|----------|
| **Jellyfin** | ✅ 完全支持 | 自动识别，支持图片 |
| **Emby** | ✅ 完全支持 | 自动识别，支持图片 |
| **Plex** | ✅ 完全支持 | 自动识别，支持图片 |
| **Sonarr** | ✅ 完全支持 | 剧集下载通知 |
| **Radarr** | ✅ 完全支持 | 电影下载通知 |
| **Ani-RSS** | ✅ 完全支持 | 动画订阅，支持不完整 JSON 修复 |
| **Overseerr** | ✅ 完全支持 | 请求管理通知 |
| **Tautulli** | ✅ 完全支持 | Plex 统计通知 |

## 消息效果

```
🤖 📺 新单集上线 [Jellyfin]

剧集名称: 进击的巨人 最终季
集号: S04E28
集名称: 最终话

剧情简介:
艾伦·耶格尔的故事迎来最终章节...

时长: 24分钟
```

## 配置选项

| 选项 | 默认值 | 说明 |
|------|--------|------|
| `webhook_port` | 60071 | Webhook 服务端口 |
| `webhook_path` | /media-webhook | Webhook 路径 |
| `group_id` | - | 目标群组 ID（必填） |
| `platform_name` | aiocqhttp | 消息平台名称 |
| `batch_min_size` | 3 | 批量发送最小数量 |
| `batch_interval_seconds` | 300 | 批量发送间隔（秒） |
| `cache_ttl_seconds` | 300 | 缓存过期时间（秒） |
| `show_platform_prefix` | true | 显示平台前缀图标 |
| `show_source_info` | true | 显示通知来源信息 |
| `force_individual_send` | false | 强制单独发送 |

## 故障排除

### 常见问题

**Q: 收到 "JSON 解析失败" 错误**
A: 插件已支持自动修复不完整的 JSON，特别是 Ani-RSS 格式

**Q: 图片不显示**
A: 检查网络连接和图片 URL 有效性

**Q: 消息重复**
A: 插件有防重复机制，检查缓存设置

### 调试命令
```
/webhook status      # 查看运行状态
/webhook test        # 测试基本功能
```

## 更新记录

详细的修复和更新记录请参考 [FIX_NOTES.md](FIX_NOTES.md)

## Ani-RSS 支持

完整的 Ani-RSS 兼容性说明请参考 [ANI_RSS_COMPATIBILITY.md](ANI_RSS_COMPATIBILITY.md)

## 许可证

MIT License
