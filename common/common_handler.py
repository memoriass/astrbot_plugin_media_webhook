
import json
from typing import Dict, Any, Optional
from astrbot.api import logger
from ..utils.i18n import t

class CommonHandler:
    """处理通用和扩展 Webhook (GitHub, DockerHub 等)"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    async def process_common_webhook(self, body: str, headers: Dict[str, str]) -> Optional[dict]:
        """处理通用 Webhook 数据"""
        try:
            # 1. 检测是否为 GitHub
            if "X-GitHub-Event" in headers:
                return self._handle_github(body, headers)

            # 2. 尝试解析为 JSON
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                # 纯文本处理
                return {
                    "message_text": f"{t('common_webhook')}:\n{body}",
                    "message_type": "common"
                }

            # 3. 检测是否为 DockerHub (简单检测机制)
            if "push_data" in data and "repository" in data:
                return self._handle_dockerhub(data)

            # 4. 兜底处理：检查是否有常见的 content/message 字段
            content = data.get("content") or data.get("message") or data.get("text")
            if content:
                return {
                    "message_text": str(content),
                    "message_type": "common"
                }

            # 5. 极端兜底：将整个 JSON 格式化输出
            return {
                "message_text": f"{t('common_webhook')}:\n{json.dumps(data, indent=2, ensure_ascii=False)}",
                "message_type": "common"
            }

        except Exception as e:
            logger.error(f"通用 Webhook 处理失败: {e}")
            return None

    def _handle_github(self, body: str, headers: Dict[str, str]) -> dict:
        event = headers.get("X-GitHub-Event", "unknown")
        try:
            data = json.loads(body)
            repo_name = data.get("repository", {}).get("full_name", "Unknown Repo")
            sender = data.get("sender", {}).get("login", "Unknown User")
            
            if event == "push":
                ref = data.get("ref", "").split("/")[-1]
                commits = data.get("commits", [])
                msg = f"{t('gh_push')} - {repo_name}\n"
                msg += f"{t('branch', '分支')}: {ref}\n"
                msg += f"{t('pusher', '推送者')}: {sender}\n"
                if commits:
                    msg += f"{t('summary', '摘要')}: {commits[0].get('message', '').splitlines()[0]}"
                return {"message_text": msg, "message_type": "common"}
            
            elif event == "release":
                action = data.get("action", "")
                tag = data.get("release", {}).get("tag_name", "")
                msg = f"{t('gh_release')} {action.capitalize()} - {repo_name}\n"
                msg += f"{t('version', '版本')}: {tag}\n"
                msg += f"{t('publisher', '发布者')}: {sender}"
                return {"message_text": msg, "message_type": "common"}

            # 其他事件显示类型
            return {
                "message_text": f"⚓ GitHub Event: {event}\n{t('repo', '仓库')}: {repo_name}\n{t('user', '用户')}: {sender}",
                "message_type": "common"
            }
        except:
            return {"message_text": f"GitHub: {event}", "message_type": "common"}

    def _handle_dockerhub(self, data: dict) -> dict:
        repo = data.get("repository", {}).get("repo_name", "Unknown")
        tag = data.get("push_data", {}).get("tag", "latest")
        pusher = data.get("push_data", {}).get("pusher", "Unknown")
        
        msg = f"{t('docker_update')}\n"
        msg += f"{t('repo', '仓库')}: {repo}\n"
        msg += f"{t('tag', '标签')}: {tag}\n"
        msg += f"{t('pusher', '推送者')}: {sender if 'sender' in locals() else pusher}"
        return {"message_text": msg, "message_type": "common"}
