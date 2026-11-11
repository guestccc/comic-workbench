# sau 本地补丁：抖音发布页禁用 stealth 初始化脚本（2026-11-09）

## 背景

`sau` 固定在 `E:\workbenchs\social-auto-upload`。2026-11 抖音新版图文发布页在开启
`utils/stealth.min.js`（`set_init_script`）时，图片上传会一直停在 0%，约 60 秒后整批标记「上传失败，
重新上传」；此时点「发布」只会反复提示「没有选择封面」，`upload-note` 因此陷入无限重试。

该目录已于 2026-11-10 原地 `git init` 并关联 fork `guestccc/social-auto-upload`，本补丁现为本地 `main` 分支提交 `ddca79e`（未 push）。

实测同一个文件：

| 条件 | 结果 |
|---|---|
| 有 stealth（headless / headed、内置 Chromium / 本机 Chrome） | 全部图片 0% → 上传失败 |
| 无 stealth（headless） | 15 张图约 15 秒上传完成，可正常预览、定时、发布 |

服务端并不拒绝：上传期间的 `ApplyImageUpload`、TOS `POST /upload/v1/...`、`CommitImageUpload`
均返回 200（`code: 2000 Success`），失败发生在前端处理阶段。控制台同时出现
`Creating a worker from 'blob:...' violates ... script-src ...` 的 CSP 报错，疑似 stealth 与新版上传器冲突。

`patchright` 自身已在浏览器层做了指纹伪装，额外的 stealth 脚本不是必需项；仓库内
`uploader/alipay_uploader/main.py` 也有同样结论的注释先例。

## 改动位置

`uploader/douyin_uploader/main.py`：

- `DouYinBaseUploader.upload()`（视频发布）
- `DouYinNoteUploader.upload()`（图文发布）

两处都注释掉 `context = await set_init_script(context)`，保留说明注释。

登录（`douyin_login`）、Cookie 检测（`cookie_auth`）仍保留 stealth，此次未改动。

## 验证

2026-11-09 用真实 `cookies/douyin_default.json` 验证：

- 无 stealth：单图 / 3 图 / 15 图均上传成功，页面进入「预览图文」状态；
- 上传完成后封面自动取第一张图，点「发布」不再提示「没有选择封面」；
- 有 stealth 时单图也必然失败，排除图片数量、体积、headless 等因素。

## 重新安装 sau 后

重新下载 / 更新 `sau` 会覆盖此补丁。先确认本地提交是否还在：

```bash
git -C E:/workbenchs/social-auto-upload log --oneline --all
```

若再次出现「图片一直 0% → 上传失败」或 `upload-note` 反复打印「小人正在冲刺发布图文」，
先检查 `DouYinBaseUploader.upload()` / `DouYinNoteUploader.upload()` 里是否又加回了
`set_init_script(context)`，注释掉即可。
