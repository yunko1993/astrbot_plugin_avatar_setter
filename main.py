import json
import os
import logging
import httpx
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.platform import AstrMessageEvent
# 导入消息组件类型用于精准识别
from astrbot.api.message_components import Image, At, Plain

logger = logging.getLogger("astrbot")

@register("astrbot_plugin_avatar_setter", "qingcai", "DNF角色图展示助手", "1.1.5")
class AvatarSetterPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = os.path.join("data", "plugin_data", "astrbot_plugin_avatar_setter")
        self.db_path = os.path.join(self.data_dir, "config.json")
        self.avatar_dir = os.path.join(self.data_dir, "avatars")
        os.makedirs(self.avatar_dir, exist_ok=True)
        self.config = self._load_config()
        logger.info(f"===== [全家福] 1.1.5 加载成功 =====")

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

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def handle_avatar_logic(self, event: AstrMessageEvent):
        msg_str = event.get_message_str()
        
        # 1. 关键词拦截
        if "全家福" not in msg_str:
            return

        sender_id = str(event.get_sender_id())
        message_chain = event.get_messages()
        
        # --- [调试日志] 打印接收到的所有消息段结构 ---
        logger.info(f"=====[全家福] 收到指令。发送者: {sender_id} =====")
        for i, seg in enumerate(message_chain):
            logger.info(f"DEBUG: 段[{i}] 类型: {type(seg).__name__} | 内容: {seg}")

        # 2. 识别目标和图片
        target_id = ""
        image_url = ""

        for seg in message_chain:
            # 识别 At 对象
            if isinstance(seg, At):
                target_id = str(seg.qq)
            # 识别 Image 对象
            elif isinstance(seg, Image):
                # 尝试获取 URL
                image_url = getattr(seg, 'url', '') or getattr(seg, 'file', '') or ""
            # 兜底：如果不是标准对象，尝试按旧格式识别
            elif not target_id and hasattr(seg, 'type') and seg.type == "at":
                target_id = str(seg.data.get("qq") or seg.data.get("user_id", ""))
            elif not image_url and hasattr(seg, 'type') and seg.type == "image":
                image_url = seg.data.get("url") or seg.data.get("file") or ""

        # 3. 逻辑判断
        if not target_id:
            logger.info("=====[全家福] 未识别到 At 目标 =====")
            return

        is_admin = sender_id in self.config.get("admin_qq", [])

        # --- 情况 A: 设置模式 (有图片) ---
        if image_url and image_url.startswith("http"):
            logger.info(f"=====[全家福] 进入设置模式。目标: {target_id}, URL: {image_url[:50]}...")
            
            if not is_admin and target_id != sender_id:
                yield event.plain_result("❌ 权限不足：你只能设置自己的全家福。")
                return
            
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(image_url, timeout=15)
                    if resp.status_code == 200:
                        save_path = os.path.join(self.avatar_dir, f"{target_id}.jpg")
                        with open(save_path, "wb") as f:
                            f.write(resp.content)
                        
                        self.config["avatars"][target_id] = f"{target_id}.jpg"
                        self._save_config()
                        logger.info(f"=====[全家福] 存储成功: {save_path}")
                        yield event.plain_result(f"✅ 设置成功！已更新 {target_id} 的全家福。")
                        event.stop_event()
                    else:
                        yield event.plain_result(f"❌ 下载失败，错误码: {resp.status_code}")
            except Exception as e:
                logger.error(f"=====[全家福] 下载崩溃: {e}", exc_info=True)
                yield event.plain_result(f"❌ 处理异常: {str(e)}")
            return

        # --- 情况 B: 查询模式 (无图片) ---
        else:
            logger.info(f"=====[全家福] 进入查询模式。目标: {target_id}")
            if target_id in self.config.get("avatars", {}):
                img_path = os.path.join(self.avatar_dir, self.config["avatars"][target_id])
                if os.path.exists(img_path):
                    yield event.image_result(img_path)
                    event.stop_event()
                else:
                    yield event.plain_result(f"⚠️ 图片文件已丢失，请重新上传。")
            else:
                yield event.plain_result(f"🔎 尚未设置 {target_id} 的全家福。发送“图片+@他+全家福”即可设置。")

    @filter.command("add_avatar_admin")
    async def add_admin(self, event: AstrMessageEvent, qq: str):
        if str(event.get_sender_id()) not in self.config["admin_qq"]: return
        if qq not in self.config["admin_qq"]:
            self.config["admin_qq"].append(qq)
            self._save_config()
            yield event.plain_result(f"✅ 已添加管理员: {qq}")
