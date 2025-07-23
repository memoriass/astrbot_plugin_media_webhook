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
