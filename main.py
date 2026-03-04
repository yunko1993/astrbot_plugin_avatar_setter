import json
import os
import logging
import httpx # 需要在 requirements.txt 加入 httpx
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.platform import AstrMessageEvent

logger = logging.getLogger("astrbot")

@register("astrbot_plugin_avatar_setter", "qingcai", "DNF角色图展示助手", "1.1.0")
class AvatarSetterPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        # 1. 路径设置 (标准 plugin_data 路径)
        self.data_dir = os.path.join("data", "plugin_data", "astrbot_plugin_avatar_setter")
        self.db_path = os.path.join(self.data_dir, "config.json")
        self.avatar_dir = os.path.join(self.data_dir, "avatars")
        
        os.makedirs(self.avatar_dir, exist_ok=True)
        self.config = self._load_config()

    def _load_config(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except: pass
        return {"admin_qq": ["1023902556"], "avatars": {}}

    def _save_config(self):
        with open(self.db_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=4)

    # === 核心逻辑：监听所有消息 ===
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_avatar_logic(self, event: AstrMessageEvent):
        msg_str = event.get_message_str()
        
        # 1. 关键词拦截
        if "全家福" not in msg_str:
            return

        # 2. 识别被 @ 的人 (兼容多版本)
        target_id = ""
        for seg in event.get_messages():
            if hasattr(seg, 'type') and seg.type == "at":
                target_id = str(seg.data.get("qq") or seg.data.get("user_id", ""))
            elif hasattr(seg, 'qq') and seg.qq:
                target_id = str(seg.qq)
        
        if not target_id: return

        # 3. 检查是否有图片 (判断是 "设置" 还是 "查看")
        image_url = ""
        for seg in event.get_messages():
            if hasattr(seg, 'type') and seg.type == "image":
                image_url = seg.data.get("url") or seg.data.get("file", "")
                break
        
        sender_id = str(event.get_sender_id())
        is_admin = sender_id in self.config.get("admin_qq", [])

        # --- 情况 A: 设置图片 ---
        if image_url:
            # 权限检查：非管理不能帮别人设图
            if not is_admin and target_id != sender_id:
                yield event.plain_result("❌ 权限不足：你只能设置自己的全家福。")
                return
            
            # 下载图片
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(image_url, timeout=10)
                    if resp.status_code == 200:
                        save_path = os.path.join(self.avatar_dir, f"{target_id}.jpg")
                        with open(save_path, "wb") as f:
                            f.write(resp.content)
                        
                        self.config["avatars"][target_id] = f"{target_id}.jpg"
                        self._save_config()
                        yield event.plain_result(f"✅ 成功！已更新 {target_id} 的全家福。")
                        event.stop_event() # 拦截，不让 AI 说话
                    else:
                        yield event.plain_result("❌ 图片下载失败，请重试。")
            except Exception as e:
                logger.error(f"下载错误: {e}")
                yield event.plain_result(f"❌ 发生错误: {str(e)}")
            return

        # --- 情况 B: 查看图片 ---
        else:
            if target_id in self.config.get("avatars", {}):
                img_path = os.path.join(self.avatar_dir, self.config["avatars"][target_id])
                if os.path.exists(img_path):
                    yield event.image_result(img_path)
                    event.stop_event()
                else:
                    yield event.plain_result(f"⚠️ 记录存在但文件丢失，请重新上传。")
            else:
                # 如果没设置过，不理会，交给 AI 或者是其他逻辑
                pass

    # 管理员指令：添加管理员
    @filter.command("add_avatar_admin")
    async def add_admin(self, event: AstrMessageEvent, qq: str):
        if str(event.get_sender_id()) not in self.config["admin_qq"]: return
        if qq not in self.config["admin_qq"]:
            self.config["admin_qq"].append(qq)
            self._save_config()
            yield event.plain_result(f"✅ 已添加管理员: {qq}")
