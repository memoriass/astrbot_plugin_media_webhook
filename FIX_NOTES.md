# 媒体通知 Webhook 插件修复说明

## 修复的问题

修复了 "发送消息时出错: 不合法的 session 字符串: not enough values to unpack (expected 3, got 1)" 的错误。

## 问题原因

原代码使用了错误的 `unified_msg_origin` 格式：
```python
unified_msg_origin = f"group_{group_id}"  # 错误格式
```

AstrBot 的 `MessageSesion.from_str()` 方法期望的格式是：`platform_name:message_type:session_id`

## 修复内容

### 1. 添加了必要的导入
```python
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.message_type import MessageType
```

### 2. 修复了 MessageChain 构造方式
```python
# 修复前
message_chain = MessageChain(forward_nodes)

# 修复后
message_chain = MessageChain(chain=forward_nodes)
```

### 3. 修复了 Node 组件构造方式
```python
# 修复前
node = Comp.Node(uin="2659908767", name="媒体通知", content=content)

# 修复后
node = Comp.Node(content=content, uin="2659908767", name="媒体通知")
```

### 4. 修复了消息发送方式
```python
# 修复前
unified_msg_origin = f"group_{group_id}"
await self.context.send_message(unified_msg_origin, message_chain)

# 修复后
platform_name = self.config.get("platform_name", "aiocqhttp")
# 清理 group_id，移除可能的冒号
group_id = str(group_id).replace(":", "_")
unified_msg_origin = f"{platform_name}:GroupMessage:{group_id}"
await self.context.send_message(unified_msg_origin, message_chain)
```

### 5. 添加了平台名称配置
在 `_conf_schema.json` 中添加了 `platform_name` 配置项：
```json
{
  "platform_name": {
    "description": "消息平台名称",
    "type": "string",
    "hint": "发送消息的平台名称，如 aiocqhttp、telegram 等",
    "default": "aiocqhttp"
  },
  "force_individual_send": {
    "description": "强制单独发送",
    "type": "bool",
    "hint": "是否强制使用单独发送模式，即使达到批量发送条件",
    "default": false
  }
}
```

## 使用说明

1. 在插件配置中设置正确的 `platform_name`，常见值：
   - `aiocqhttp` - QQ 个人号（使用 NapCat、Lagrange 等）
   - `telegram` - Telegram
   - `qqofficial` - QQ 官方接口
   - `discord` - Discord
   - `lark` - 飞书

2. 设置正确的 `group_id`（群组ID）

3. 插件现在应该能够正常发送消息到指定的群组

### 6. 添加了调试日志和群组ID清理
- 添加了调试日志来跟踪消息发送过程
- 清理群组ID中的冒号字符，避免解析错误

### 7. 修复了测试命令的网络问题
- 修复了 `/webhook_test` 命令中图片URL无法访问的问题
- 将测试图片源从 `via.placeholder.com` 改为 `picsum.photos`
- 添加了图片加载失败的错误处理

### 8. 新增 BGM.TV 数据源功能
- 集成了 BGM.TV API，可以获取真实的动画剧集数据
- 添加了 `fetch_bgm_data()` 方法从 BGM.TV 随机获取剧集信息
- 添加了 `convert_bgm_to_test_data()` 方法转换数据格式
- 支持获取剧集名称、年份、简介、图片等完整信息
- 增强了 `/webhook_test` 命令，支持多种数据源和参数

### 9. 优化发送逻辑，支持平台兼容性
- 添加了 `supports_forward_messages()` 方法检查平台合并转发支持
- 实现智能发送策略：
  - 消息数量 < `batch_min_size`：直接单独发送
  - 消息数量 ≥ `batch_min_size` 且平台支持合并转发：使用合并转发
  - 消息数量 ≥ `batch_min_size` 但平台不支持合并转发：回退到单独发送
- 添加了 `force_individual_send` 配置项，可强制使用单独发送
- 更新了状态命令，显示当前发送策略和平台兼容性

### 10. 优化测试命令用户体验
- 修改 `/webhook test` 命令默认使用 BGM.TV 真实数据
- 默认包含图片，提供更真实的测试体验
- 将所有命令中的下划线改为空格，提升用户体验：
  - `/webhook_test` → `/webhook test`
  - `/webhook_status` → `/webhook status`
  - `/webhook_test_simple` → `/webhook test simple`

### 11. 新增通知来源识别和平台前缀功能
- 添加了 `detect_notification_source()` 方法智能识别通知来源
- 支持检测 Jellyfin、Emby、Plex、Sonarr、Radarr、Overseerr、Tautulli 等
- 添加了 `get_platform_prefix()` 方法为不同平台添加前缀图标
- 新增配置选项：
  - `show_platform_prefix`：控制是否显示平台前缀
  - `show_source_info`：控制是否显示通知来源信息
- 消息格式优化：`🤖 📺 新单集上线 [Jellyfin]`

## 测试

修复后的代码已通过基本测试：
1. 能够正确构造 `unified_msg_origin` 字符串格式
2. 字符串格式符合 `platform_name:message_type:session_id` 的要求
3. 能够被 `MessageSesion.from_str()` 正确解析

## 常见问题

### Q: 仍然出现 "not enough values to unpack" 错误怎么办？
A: 请检查以下配置：
1. 确保 `group_id` 配置正确，不包含冒号等特殊字符
2. 确保 `platform_name` 配置正确，与实际使用的平台匹配
3. 检查 AstrBot 日志中的调试信息，确认 `unified_msg_origin` 格式正确

### Q: 支持哪些平台？
A: 常见的平台名称包括：
- `aiocqhttp` - QQ 个人号
- `telegram` - Telegram
- `qqofficial` - QQ 官方接口
- `discord` - Discord
- `lark` - 飞书
- `dingtalk` - 钉钉

### Q: 测试命令使用方法？
A: 插件提供了多个测试命令：

**基础测试命令：**
- `/webhook test simple` - 纯文本测试，不包含图片，快速验证

**增强测试命令：**
- `/webhook test` - 使用 BGM.TV 真实数据，包含图片（默认，推荐）
- `/webhook test static` - 使用静态测试数据，包含默认图片
- `/webhook test bgm` - 明确使用 BGM.TV 真实数据，包含图片
- `/webhook test bgm no` - 使用 BGM.TV 数据但不包含图片
- `/webhook test static no` - 使用静态数据但不包含图片

### Q: 为什么图片测试失败？
A: 可能的原因：
1. 网络连接问题，无法访问图片URL
2. 防火墙或代理设置阻止了图片下载
3. 建议使用 `/webhook_test_simple` 进行纯文本测试

### Q: BGM.TV 数据源有什么特点？
A: BGM.TV 数据源的特点：
1. **真实数据** - 从 BGM.TV 获取真实的动画剧集信息
2. **随机性** - 每次调用都会随机选择不同的作品
3. **完整信息** - 包含剧集名称、年份、简介、图片等
4. **自动图片** - 如果作品有封面图，会自动包含
5. **网络依赖** - 需要能够访问 BGM.TV API

### Q: 如何选择合适的测试命令？
A: 建议选择：
- **快速测试** - 使用 `/webhook test simple`
- **日常测试** - 使用 `/webhook test`（默认 BGM.TV 真实数据）
- **静态数据测试** - 使用 `/webhook test static`
- **无图片测试** - 使用 `/webhook test bgm no`
