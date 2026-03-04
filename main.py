import os
import json
import logging
from astrbot.api.event import filter
from astrbot.api.star import Context, Star, register
from astrbot.core.platform import AstrMessageEvent

logger = logging.getLogger("astrbot")

@register("astrbot_plugin_avatar_setter", "qingcai", "DNF角色图设置助手", "1.0.6")
class AvatarSetterPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        
        # === 关键改进：自动定位并创建数据目录 ===
        # 获取 plugin_data 根目录 (AstrBot 标准路径)
        base_data_dir = os.path.join(context.get_config().get("plugin_data_path", "data/plugin_data"), "astrbot_plugin_avatar_setter")
        
        # 如果配置里没写，尝试兼容旧路径或默认路径
        if not os.path.isabs(base_data_dir):
            # 相对路径则拼接当前工作目录下的 data/plugin_data
            base_data_dir = os.path.join("data", "plugin_data", "astrbot_plugin_avatar_setter")
            
        self.data_dir = base_data_dir
        self.db_path = os.path.join(self.data_dir, "config.json")
        self.avatar_dir = os.path.join(self.data_dir, "avatars")
        
        # 自动创建目录 (无需手动 mkdir)
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.avatar_dir, exist_ok=True)
        
        self.config = self._load_config()
        logger.info(f"===== [角色图设置] 已加载，数据路径: {self.data_dir} =====")

    def _load_config(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"读取配置失败: {e}")
        # 默认管理员QQ (首次运行生成)
        return {"admin_qq": ["1023902556"], "avatars": {}}

    def _save_config(self):
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    # === 设置操作：必须包含"全家福" + @目标 + 图片 ===
    @filter.command("setavatar")
    async def set_avatar(self, event: AstrMessageEvent):
        sender_id = str(event.get_sender_id())
        is_admin = sender_id in self.config.get("admin_qq", [])
        
        # 1. 必须包含"全家福" (防误触发)
        if "全家福" not in event.get_message_str():
            yield event.plain_result("⚠️ 请包含‘全家福’（例：@自己 全家福）")
            return
        
        # 2. 识别被@的ID
        target_id = ""
        for seg in event.get_messages():
            if (hasattr(seg, 'type') and seg.type == "at") or (hasattr(seg, 'qq') and seg.qq):
                target_id = str(getattr(seg, 'qq', seg.data.get("qq")))
                break
        
        if not target_id:
            yield event.plain_result("⚠️ 请@目标用户（例：@自己 全家福）")
            return
        
        # 3. 权限检查：普通用户只能@自己
        if not is_admin and target_id != sender_id:
            yield event.plain_result("❌ 普通用户只能@自己（请@自己）")
            return
        
        # 4. 识别图片
        image_url = ""
        for seg in event.get_messages():
            if hasattr(seg, 'type') and seg.type == "image":
                image_url = seg.data.get("url", "")
                break
            elif hasattr(seg, 'url'):
                image_url = seg.url
        
        if not image_url:
            yield event.plain_result("⚠️ 请附上图片（直接发图，不要文字）")
            return
        
        # 5. 保存图片到 plugin_data/astrbot_plugin_avatar_setter/avatars/
        avatar_filename = f"{target_id}.jpg"
        avatar_path = os.path.join(self.avatar_dir, avatar_filename)
        
        try:
            await self.context.download_image(image_url, avatar_path)
            # 配置里只存相对文件名，方便迁移
            self.config["avatars"][target_id] = avatar_filename
            self._save_config()
            yield event.plain_result(f"✅ 已保存 {target_id} 的角色图！\n📁 存储位置: {self.data_dir}")
        except Exception as e:
            logger.error(f"下载图片失败: {e}")
            yield event.plain_result(f"❌ 保存失败: {str(e)}")

    # === 触发操作：必须包含"全家福" ===
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_mention(self, event: AstrMessageEvent):
        # 1. 必须包含"全家福" (防误触发)
        if "全家福" not in event.get_message_str():
            return
        
        # 2. 识别被@的ID
        target_id = ""
        for seg in event.get_messages():
            if (hasattr(seg, 'type') and seg.type == "at") or (hasattr(seg, 'qq') and seg.qq):
                target_id = str(getattr(seg, 'qq', seg.data.get("qq")))
                break
        
        # 3. 检查是否有角色图
        if target_id and target_id in self.config.get("avatars", {}):
            avatar_filename = self.config["avatars"][target_id]
            avatar_path = os.path.join(self.avatar_dir, avatar_filename)
            
            if os.path.exists(avatar_path):
                yield event.image_result(avatar_path)
                event.stop_event() # 阻止其他插件处理
