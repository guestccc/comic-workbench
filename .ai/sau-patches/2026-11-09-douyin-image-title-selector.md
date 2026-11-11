# sau 本地补丁：抖音图文标题选择器（2026-11-09）

## 背景

`sau` 固定在 `E:\workbenchs\social-auto-upload`。抖音图文发布页在 2026-11 把标题输入框的占位符从「填写作品标题」改成了「添加作品标题」，导致 `upload-note` 在进入图文发布页后等待标题框 120 秒超时，任务失败。

该目录已于 2026-11-10 原地 `git init` 并关联 fork `guestccc/social-auto-upload`，本补丁现为本地 `main` 分支提交 `35332c0`（未 push）。

视频发布页仍使用「填写作品标题」，因此补丁同时匹配两种占位符。

## 改动位置

`uploader/douyin_uploader/main.py` → `DouYinBaseUploader.fill_title_and_description()`

```python
# 修改前
title_input = page.locator('input[placeholder*="填写作品标题"]').first

# 修改后
title_input = page.locator(
    'input[placeholder*="填写作品标题"], input[placeholder*="添加作品标题"]'
).first
```

## 验证

2026-11-09 用真实的 `cookies/douyin_default.json` 打开抖音图文发布页，确认：

- 图文页标题输入框占位符为「添加作品标题」；
- 新选择器能定位并填入标题；
- 描述、`#话题`、定时发布时间均可设置；
- 页面存在「发布」按钮（未点击，未产生真实作品）。

## 重新安装 sau 后

重新下载 / 更新 `sau` 会覆盖此补丁。先看本地分支是否还在：

```bash
git -C E:/workbenchs/social-auto-upload log --oneline --all
```

若再次出现「等待 `input[placeholder*="填写作品标题"]` 超时」，先确认抖音图文页当前的标题占位符，再按上面的方式同时匹配新旧占位符。

## 上游参考

- PR #225 `Fix/uploader dom 202606`：视频发布页 waited 120s 与占位符选择器修复
- 图文页 `添加作品标题` 占位符：2026-11-09 本地实测
