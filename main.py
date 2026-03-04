import json
import os
import logging
import httpx
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.platform import AstrMessageEvent

logger = logging.getLogger("astrbot")

@register("astrbot_plugin_avatar_setter", "qingcai", "DNF角色图展示助手", "1.1.2")
class AvatarSetterPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.data_dir = os.path.join("data", "plugin_data", "astrbot_plugin_avatar_setter")
        self.db_path = os.path.join(self.data_dir, "config.json")
        self.avatar_dir = os.path.join(self.data_dir, "avatars")
        os.makedirs(self.avatar_dir, exist_ok=True)
        self.config = self._load_config()
        logger.info(f"===== [全家福] 插件初始化成功，数据目录: {self.data_dir} =====")

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
        logger.info(f"=====[全家福] 触发关键词。发送者: {sender_id}, 消息内容: {msg_str} =====")

        # 2. 识别被 @ 的人
        target_id = ""
        for seg in event.get_messages():
            if hasattr(seg, 'type') and seg.type == "at":
                target_id = str(seg.data.get("qq") or seg.data.get("user_id", ""))
            elif hasattr(seg, 'qq') and seg.qq:
                target_id = str(seg.qq)
        
        if not target_id:
            logger.info("=====[全家福] 未识别到 @ 目标，跳过 =====")
            return
        
        logger.info(f"=====[全家福] 识别到目标 QQ: {target_id} =====")

        # 3. 识别图片 (兼容多种获取方式)
        image_url = ""
        for seg in event.get_messages():
            if hasattr(seg, 'type') and seg.type == "image":
                # 尝试多种可能的 URL 字段
                image_url = seg.data.get("url") or seg.data.get("file") or ""
                if image_url and not image_url.startswith("http"): # 如果是本地缓存文件名则清空
                    image_url = ""
                break
        
        is_admin = sender_id in self.config.get("admin_qq", [])

        # --- 情况 A: 包含图片 (设置模式) ---
        if image_url:
            logger.info(f"=====[全家福] 检测到图片 URL: {image_url[:50]}... =====")
            
            if not is_admin and target_id != sender_id:
                logger.warn(f"=====[全家福] 权限拒绝: {sender_id} 试图给 {target_id} 设图 =====")
                yield event.plain_result("❌ 权限不足：你只能设置自己的全家福。")
                return
            
            try:
                async with httpx.AsyncClient() as client:
                    logger.info(f"=====[全家福] 正在从网络下载图片... =====")
                    resp = await client.get(image_url, timeout=15)
                    if resp.status_code == 200:
                        save_path = os.path.join(self.avatar_dir, f"{target_id}.jpg")
                        with open(save_path, "wb") as f:
                            f.write(resp.content)
                        
                        self.config["avatars"][target_id] = f"{target_id}.jpg"
                        self._save_config()
                        logger.info(f"=====[全家福] 保存成功: {save_path} =====")
                        yield event.plain_result(f"✅ 设置成功！已更新 {target_id} 的全家福。")
                        event.stop_event()
                    else:
                        logger.error(f"=====[全家福] 下载失败，状态码: {resp.status_code} =====")
                        yield event.plain_result("❌ 图片下载失败 (服务器响应异常)")
            except Exception as e:
                logger.error(f"=====[全家福] 处理图片时发生崩溃: {e}", exc_info=True)
                yield event.plain_result(f"❌ 发生错误: {str(e)}")
            return

        # --- 情况 B: 不包含图片 (查看模式) ---
        else:
            logger.info(f"=====[全家福] 未检测到图片，进入查询模式 =====")
            if target_id in self.config.get("avatars", {}):
                img_path = os.path.join(self.avatar_dir, self.config["avatars"][target_id])
                if os.path.exists(img_path):
                    logger.info(f"=====[全家福] 发送图片文件: {img_path} =====")
                    yield event.image_result(img_path)
                    event.stop_event()
                else:
                    logger.error(f"=====[全家福] 数据库有记录但文件不存在: {img_path} =====")
                    yield event.plain_result(f"⚠️ 图片文件丢失，请重新上传。")
            else:
                logger.info(f"=====[全家福] 数据库中没有 {target_id} 的记录 =====")
                # 只有在明确是“查看”且没找到时才提示
                if "全家福" in msg_str:
                     yield event.plain_result(f"🔎 尚未设置 {target_id} 的全家福。发送“图片+@他+全家福”即可设置。")

    @filter.command("add_avatar_admin")
    async def add_admin(self, event: AstrMessageEvent, qq: str):
        if str(event.get_sender_id()) not in self.config["admin_qq"]: return
        if qq not in self.config["admin_qq"]:
            self.config["admin_qq"].append(qq)
            self._save_config()
            yield event.plain_result(f"✅ 已添加管理员: {qq}")
