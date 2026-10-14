"""在异步计算前从消息事件固定 QQ 群调用者；身份不接受模型参数。"""

from .ziwei_records import ZiweiCaller


def capture_qq_caller(event):
    platform_name = event.get_platform_name()
    if platform_name not in {"aiocqhttp", "qq_official"}:
        return None
    group_id = str(event.get_group_id() or "")
    user_id = str(event.get_sender_id() or "")
    platform_id = str(event.get_platform_id() or "")
    if not group_id or not user_id or not platform_id:
        return None
    if platform_name == "qq_official":
        # 官方频道也填 group_id；只有 GroupMessage 的 group_openid 才表示 QQ 群。
        raw = getattr(event.message_obj, "raw_message", None)
        if str(getattr(raw, "group_openid", "") or "") != group_id:
            return None
    return ZiweiCaller(
        platform_name=platform_name,
        platform_id=platform_id,
        group_id=group_id,
        user_id=user_id,
        message_id=str(getattr(event.message_obj, "message_id", "") or ""),
    )
