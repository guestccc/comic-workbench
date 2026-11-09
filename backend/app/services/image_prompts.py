"""生图提示词组装：角色三视角设定图、参考图映射。"""

from __future__ import annotations

import re

REFERENCE_PATTERN = re.compile(r"\{\{([^{}]+)\}\}")


def extract_character_names(prompt: str) -> list[str]:
    """按首次出现顺序提取提示词里的 {{角色名}}，去重。"""
    names: list[str] = []
    for match in REFERENCE_PATTERN.findall(prompt or ""):
        name = match.strip()
        if name and name not in names:
            names.append(name)
    return names


def build_character_sheet_prompt(
    *,
    style_name: str,
    style_content: str,
    name: str,
    appearance: str,
) -> str:
    """角色资产图提示词：一张图内包含全身、七分身、半身三个视角。"""
    return f"""【画风】{style_name}，{style_content}
【画面】3:4竖版角色设定图，一整幅完整单画面，浅灰色纯净背景。画面分成左右两列，画同一个角色「{name}」的三个视角，三个人物的发型、五官、服装、配饰、身高比例完全一致：
左列：全身正面站立，从头顶到鞋底完整入画；
右列上方：七分身（膝盖以上）正面站立；
右列下方：半身（腰部以上）正面站立。
角色设定：{appearance}
每个视角都是中性表情、双手自然下垂、正面看向镜头，不摆剧情动作；三个视角之间用极浅的灰色细线分隔，不遮挡人物。
【文字标注】左列人物旁写小号黑色中文「全身」，右列上方人物旁写「七分身」，右列下方人物旁写「半身」；标注清晰、不遮挡人物；除这三个标注外不出现任何文字、页码、水印、logo。
【画面形式】3:4竖版，一整幅完整单画面，无外框、无标题框，可以有极浅的灰色分隔线。
【负面提示词】纯黑背景，大面积死黑，场景，道具，分格，漫画框，边框，标题框，水印，logo，文字乱码，错字，多余文字，重复文字，页码，对话气泡，角色换装，脸型漂移，五官变形，比例失调，裸露，走光，情趣服饰，挑逗姿势，过度夸张身材，色情，低俗，过度暴露，Q版，3D渲染，塑料质感，平涂，贴纸，全图粗黑描边，多出来的手脚，畸形肢体。"""


def build_provider_prompt(
    prompt: str,
    *,
    start_prompt: str,
    story_name: str,
    story_content: str,
    style_name: str,
    style_content: str,
) -> str:
    """把启动提示词解析后拼在发给上游的 prompt 最前面。

    工作台调用生图 API 时每次都是独立请求，不能依赖外部会话上下文，
    所以启动提示词必须在每次请求里自带。占位符与 DeepSeek 文案生成一致：
    {story_name} / {story_content} / {art_style} / {art_style_name}。
    """
    prefix = (start_prompt or "").strip()
    if not prefix:
        return prompt
    prefix = prefix.replace("{story_name}", story_name or "")
    prefix = prefix.replace("{story_content}", story_content or "")
    prefix = prefix.replace("{art_style_name}", style_name or "")
    prefix = prefix.replace("{art_style}", style_content or "")
    prefix = prefix.strip()
    return f"{prefix}\n\n{prompt}" if prefix else prompt


def build_reference_prompt(prompt: str, names: list[str]) -> str:
    """把 {{角色名}} 映射成参考图编号，并追加不可照搬排版的前缀。"""
    if not names:
        return prompt
    lines = ["【参考图】"]
    for index, name in enumerate(names, start=1):
        lines.append(f"参考图{index}：「{name}」的角色设定图；")
    lines.append(
        "只取角色的五官、发型、服装、配饰和体态，不要照搬参考图的排版、背景、标注文字和分隔线。"
    )
    lines.append("")
    mapped = prompt
    for index, name in enumerate(names, start=1):
        mapped = mapped.replace("{{" + name + "}}", f"参考图{index}中的角色（{name}）")
    return "\n".join(lines) + mapped
