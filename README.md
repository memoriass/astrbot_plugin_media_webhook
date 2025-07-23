# Media Webhook 插件

基于原始 `webhook.js` 开发的 AstrBot Python 插件，用于接收媒体服务器的通知并发送到群聊。

## 功能特性

- 🌐 **HTTP Webhook 服务器** - 接收媒体通知请求
- 🔄 **重复请求检测** - 使用MD5哈希防止重复处理
- 📦 **批量消息处理** - 支持单独发送和合并转发
- ⚙️ **灵活配置** - 可配置端口、群组、处理间隔等
- 📊 **状态监控** - 提供状态查询和测试命令
- 🎬 **多媒体类型支持** - 支持电影、剧集、专辑等多种媒体类型

## 安装配置

### 1. 插件安装

将插件文件夹放置到 AstrBot 的 `data/plugins/` 目录下：

```
AstrBot/
└── data/
    └── plugins/
        └── astrbot_plugin_media_webhook/
            ├── main.py
            ├── metadata.yaml
            ├── requirements.txt
            ├── _conf_schema.json
            └── README.md
```

### 2. 配置插件

在 AstrBot 管理面板中找到 "Media Webhook" 插件，配置以下参数：

- **group_id**: 目标群组ID（必填）
- **webhook_port**: Webhook监听端口（默认: 60071）
- **webhook_path**: Webhook路径（默认: /media-webhook）
- **cache_ttl_seconds**: 重复请求缓存时间（默认: 300秒）
- **batch_interval_seconds**: 批量处理间隔（默认: 300秒）
- **batch_min_size**: 触发合并转发的最小消息数（默认: 3条）

### 3. 启动插件

在插件管理页面启用插件，插件将自动启动HTTP服务器。

## 使用方法

### Webhook 接口

**接口地址**: `http://localhost:{port}{path}`
**请求方法**: POST
**Content-Type**: application/json

### 请求格式

```json
{
  "item_type": "Episode",
  "series_name": "示例剧集",
  "year": "2024",
  "item_name": "第一集",
  "season_number": 1,
  "episode_number": 1,
  "overview": "剧情简介",
  "runtime": "45分钟",
  "image_url": "https://example.com/poster.jpg"
}
```

### 支持的媒体类型

- **Movie**: 电影
- **Series**: 剧集
- **Season**: 剧季
- **Episode**: 单集
- **Album**: 专辑
- **Song**: 歌曲
- **Video**: 视频

## 插件命令

### `/webhook_status`
查看Webhook服务状态，包括：
- 服务地址
- 队列消息数
- 缓存请求数
- 配置参数

### `/webhook_test`
发送测试消息，验证插件功能是否正常。

## 测试工具

插件提供了测试脚本 `test_webhook.py`，可以用来测试各种功能：

```bash
# 运行所有测试
python test_webhook.py

# 指定webhook地址
python test_webhook.py --url http://localhost:60071/media-webhook

# 运行特定测试
python test_webhook.py --test single
python test_webhook.py --test duplicate
python test_webhook.py --test batch
python test_webhook.py --test invalid
```

## 工作原理

1. **接收请求**: HTTP服务器接收媒体通知请求
2. **重复检测**: 计算请求哈希值，检查是否为重复请求
3. **消息格式化**: 将媒体数据转换为友好的消息格式
4. **队列缓存**: 将消息添加到内存队列
5. **批量处理**: 定时处理队列中的消息
6. **智能发送**: 根据消息数量选择单独发送或合并转发

## 消息格式示例

```
🎬 新单集上线

剧集名称: 示例剧集 (2024)
集号: S01E01
集名称: 第一集

剧情简介:
这是一个示例剧情简介...

时长: 45分钟
```

## 注意事项

1. 确保配置的群组ID正确且机器人在该群组中
2. 防火墙需要开放配置的端口
3. 建议在生产环境中使用反向代理
4. 定期检查日志以监控插件运行状态

## 故障排除

### 常见问题

1. **插件无法启动**
   - 检查端口是否被占用
   - 确认依赖包已正确安装

2. **消息发送失败**
   - 验证群组ID配置
   - 检查机器人权限

3. **重复请求检测失效**
   - 检查缓存TTL配置
   - 确认请求数据格式一致

### 日志查看

插件运行日志可在 AstrBot 日志中查看，关键词：`Media Webhook`

## 开发说明

本插件基于原始 `webhook.js` 功能开发，主要改进：

- 使用 Python 异步编程提高性能
- 集成 AstrBot 插件系统
- 提供可视化配置界面
- 增加测试工具和错误处理
- 支持更多消息类型和格式

## 许可证

本插件遵循 MIT 许可证。
