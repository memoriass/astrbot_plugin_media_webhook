# 媒体通知 Webhook 插件

用于 AstrBot 的媒体通知 Webhook 插件，支持接收来自各种媒体服务器的通知。

## 主要功能

- 🎬 **多平台支持**: Jellyfin、Emby、Plex、Ani-RSS 等
- 📱 **智能消息**: 自动格式化，包含剧集信息、封面图片
- 🔄 **智能去重**: 哈希校验，排除图片等不稳定字段，提高准确率
- 🎯 **数据丰富**: TMDB → BGM.TV → 原始数据的降级机制
- 🔧 **消息修复**: 针对 aiocqhttp 的多行消息显示优化

## 支持的服务器

- **Jellyfin** - 完全支持，TMDB/BGM.TV 数据丰富
- **Emby** - 完全支持，TMDB/BGM.TV 数据丰富
- **Plex** - 完全支持，TMDB/BGM.TV 数据丰富
- **Ani-RSS** - 完全支持，JSON 修复
- **Sonarr/Radarr** - 完全支持

## 快速配置

### 1. 插件配置
```json
{
  "webhook_port": 60071,
  "group_id": "your-group-id",
  "tmdb_api_key": "your-tmdb-key"
}
```

### 2. 媒体服务器配置
设置 Webhook URL：
```
http://your-bot-server:60071/media-webhook
```

### 3. 测试命令
```
/webhook test        # 测试功能
/webhook status      # 查看状态
```


## 消息效果

```
🤖 📺 新剧集更新 [Jellyfin]

剧集名称: 进击的巨人 (2023)
集号: S04E28
集名称: 最终话

剧情简介:
艾伦·耶格尔的故事迎来最终章节...

时长: 24分钟
✨ 数据来源: TMDB
```

## 主要配置

| 选项 | 说明 |
|------|------|
| `webhook_port` | Webhook 服务端口（默认：60071） |
| `group_id` | 目标群组 ID（必填） |
| `tmdb_api_key` | TMDB API 密钥（可选，用于数据丰富） |
| `batch_min_size` | 批量发送阈值（默认：3） |
| `platform_name` | 消息平台名称（默认：aiocqhttp） |
| `force_individual_send` | 强制单独发送（默认：false） |
| `cache_ttl_seconds` | 重复检测缓存时间（默认：300秒） |


插件支持为 **Jellyfin、Emby、Plex** 通过外部 API 获取更准确的剧集信息：

1. **TMDB 优先** - 有季数信息时使用 TMDB API
2. **BGM.TV 降级** - TMDB 失败时尝试 BGM.TV
3. **原始数据保底** - 两者都失败时使用原始数据

配置 `tmdb_api_key` 可获得更准确的剧情简介和剧集名称。

**支持平台**：Jellyfin、Emby、Plex 的剧集通知都会自动进行数据丰富处理。

## 消息修复

针对 aiocqhttp 平台的多行消息显示问题进行了专门优化：

- **智能压缩**: 针对 Emby/Plex/Jellyfin 消息移除空行，创建紧凑格式
- **格式保持**: 保持所有重要信息的完整性和可读性
- **平台兼容**: 不影响 Ani-RSS 等其他平台的消息格式
- **显著效果**: 消息行数减少 33-40%，大幅提高显示兼容性
- **智能批量**: 根据 aiocqhttp 文档优化批量发送逻辑
- **精准去重**: 哈希校验排除图片URL等不稳定字段
- **性能优化**: 减少重复逻辑，提升代码执行效率

**修复效果对比**：
```
修复前（只显示第一行）:
🤖 📺 新剧集更新 [Emby]
（后续内容被截断...）

修复后（完整显示）:
🤖 📺 新剧集更新 [Emby]
剧集名称: 进击的巨人 (2023)
集号: S04E28
集名称: 最终话
剧情简介: 艾伦·耶格尔的故事迎来最终章节...
时长: 24分钟
✨ 数据来源: TMDB
```

**批量发送优化**：
- 低于 `batch_min_size` (默认3): 单独发送，避免合并转发开销
- 达到或超过 `batch_min_size`: 合并转发，减少刷屏
- 根据平台能力智能选择发送方式

**重复检测优化**：
- 使用 SHA-256 哈希算法提高安全性
- 排除图片URL、时间戳等不稳定字段
- 针对不同数据源采用不同哈希策略
- 自动清理过期缓存，避免内存泄漏

**性能优化**：
- 预缓存常用配置值，减少重复的 config.get() 调用
- 预计算字符串比较，避免重复的 lower() 操作
- 规则驱动的验证逻辑，减少重复代码
- 优化错误处理，使用条件表达式替代多个 if-else

## Ani-RSS 支持

完整支持 Ani-RSS 项目，**采用原始数据格式直接发送**：

- **原始格式**: 保持 Ani-RSS 的完整信息和原始格式
- **无数据转换**: 不进行标准化处理，避免信息丢失
- **无数据丰富**: 不使用 TMDB/BGM.TV 等外部 API
- **用户体验**: 保持用户熟悉的 Ani-RSS 消息风格

详见 [ANI_RSS_COMPATIBILITY.md](ANI_RSS_COMPATIBILITY.md)

## 许可证

MIT License
