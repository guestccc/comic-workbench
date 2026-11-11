# sau 本地补丁：小红书内容声明与合集（2026-11-10）

## 背景

小红书图文发布页把「虚构演绎，仅供娱乐」「笔记含AI合成内容」「内容包含营销广告」
「内容来源声明」放在同一个选择器里（入口文案「添加内容类型声明」），合集入口是「选择合集」。
`sau` 的 `xiaohongshu upload-note` 此前两者都不支持：

- 唯一相关代码是 `check_original_declaration()`，它**无条件**选择「来源转载」且来源为空，
  日志会打印 `来源转载已声明（来源：）`；
- 没有任何合集参数。

结果：小红书图文既不能声明「笔记含AI合成内容」，也不能归入已有合集。

## 拆成两个 PR

声明与合集是两个独立能力，提上游时不能放进同一个 PR：

| PR | 内容 | 当前存放位置 |
|---|---|---|
| PR1 | 内容声明：`--declaration` / `--repost-source`，并移除无条件的「来源转载」 | `E:\workbenchs\social-auto-upload` 未提交工作区 |
| PR2 | 合集：`--collection`，只选择**已存在**的合集 | `.ai/sau-patches/patches/0002-xiaohongshu-collection.patch`（叠在 PR1 之上） |

`0001-xiaohongshu-content-declaration.patch` 是 PR1 的完整补丁，仅用于对照，内容等于当前工作区改动。

工作区当前状态 = `ddca79e` + PR1；PR2 未应用。应用 / 撤销：

```bash
cd E:/workbenchs/social-auto-upload
git apply  E:/workbenchs/comic-workbench/.ai/sau-patches/patches/0002-xiaohongshu-collection.patch
git apply -R E:/workbenchs/comic-workbench/.ai/sau-patches/patches/0002-xiaohongshu-collection.patch
```

两个补丁已校验：PR1 补丁单独应用后得到当前工作区；再叠 PR2 后六个文件与拆分前的合并状态逐字节一致，撤销后回到 PR1 状态。相关测试在两种状态下均为 35 / 40 项，只余上游既有的 `test_video_fill_meta_uses_desc_then_first_tag` 失败。

## 改动位置

| 文件 | PR1 | PR2 |
|---|---|---|
| `sau_commands/xiaohongshu.py` | 新增 `--declaration`、`--repost-source`；请求 dataclass 与 `run()` 透传 | 追加 `--collection` 与透传 |
| `uploader/xiaohongshu_uploader/main.py` | 新增 `apply_content_declaration()`；`XiaoHongShuNote` 接收并归一化两个字段；用条件调用替代无条件 `check_original_declaration()` | 新增 `apply_collection()`；接收 `collection` 归一化为 `collection_name`；发布流程追加一次调用 |
| `tests/test_sau_browser_cli.py` | 声明参数、默认 None、dispatch 透传 | 合集参数、默认 None、dispatch 透传 |
| `tests/test_xiaohongshu_uploader.py` | 声明归一化、互斥校验、未传声明不触碰页面、拒绝把「内容来源声明」当普通声明 | 合集归一化与默认值 |
| `README.md`、`docs/CLI.md` | 声明参数示例与说明 | 追加合集示例与说明 |

## 行为约定

| 参数 | 语义 | 失败时 |
|---|---|---|
| `--declaration "笔记含AI合成内容"` | 按**精确选项文案**在 `.d-popover.declaration-drop-down` 的 `.d-grid-item` 中点击 | 抛错，拒绝发布（声明属合规项，不允许静默漏选） |
| `--repost-source "媒体名"` | 选择「内容来源声明」并填来源 | 沿用原 `check_original_declaration()` 逻辑 |
| `--collection "合集名"` | 按名称精确匹配已有合集 | 告警并跳过，保持未选状态（合集属可选增强项） |

发布页「添加内容类型声明」实测结构（2026-11-10），同一时间只能选一个：

| 选项 | 交互 | 传参方式 |
|---|---|---|
| 虚构演绎，仅供娱乐 | 点击即选中 | `--declaration "虚构演绎，仅供娱乐"` |
| 笔记含AI合成内容 | 点击即选中 | `--declaration "笔记含AI合成内容"` |
| 内容包含营销广告 | 点击即选中 | `--declaration "内容包含营销广告"` |
| 内容来源声明 | **悬停**展开二级菜单 | 不能直接传 |
| ├ 来源转载 | 弹窗填「请输入媒体名称」→ 确认；选中后入口文案变成「来源转载 / 信息转载于某媒体」 | `--repost-source "<媒体名>"` |
| └ 自主拍摄 | 弹窗填「拍摄地点」（下拉选地点）+「拍摄日期」→ 确认 | 不支持，本补丁未实现 |

「原创声明」是发布页上独立的开关，不属于内容类型声明，本补丁不处理。

二级菜单只有悬停才显示，但条目始终在 DOM 里，用 `has_text` 定位后直接点击即可触发；
现有 `check_original_declaration()`（`--repost-source` 走它）在新 UI 下仍能完整走完
「展开 → 点来源转载 → 填媒体名称 → 确认」，2026-11-10 实测入口变成「来源转载」。

- 不传 `--declaration` 时完全不修改发布页声明；`--declaration` 与 `--repost-source` 互斥，
  同时传由 `validate_upload_args()` 抛 `ValueError`。
- 显式传「内容来源声明」/「来源转载」给 `--declaration` 会被拒绝，要求改用 `--repost-source`。
- 未传 `--repost-source` 时不再执行 `check_original_declaration()`，修掉了「每条图文都被标记来源转载且来源为空」。

与抖音既有约定一致：声明 fail-closed，合集 warn-and-skip。

## 验证

### 声明（当前工作区状态，2026-11-10 实测）

真实账号 `cookies/xiaohongshu_default.json`、真实图文发布页，全程不点击「发布」或「定时发布」：

| 场景 | 结果 |
|---|---|
| 传 `笔记含AI合成内容` | 选中成功，入口文案变为该声明，「添加内容类型声明」消失 |
| 不传声明 | 页面完全不动，「添加内容类型声明」保持原样 |
| 传不存在的声明文案 | 报「声明选项「…」不存在」，抛错并拒绝继续发布（fail-closed 生效） |

复现：用 `sau` 的 venv 运行 `E:\workbenchs\.tmp_xhs_decl_test\run_declaration_check.py pass|none|invalid`，脚本只填内容和声明，不点击发布。

另两项 2026-11-10 实测：

- `--repost-source "某媒体"`（走原 `check_original_declaration()`）在新级联菜单下仍能完成：展开 → 点来源转载 → 填媒体名称 → 确认，入口变为「来源转载 / 信息转载于某媒体」；
- `--repost-source ""`（旧代码的无条件调用就是这种情况）：平台照样接受，「请输入媒体名称」留空点确认即可，入口只显示「来源转载」、没有来源说明。这解释了历史小红书图文为什么都带一条空来源的「来源转载」声明。

单测：`tests.test_sau_browser_cli` + `tests.test_xiaohongshu_uploader` 共 35 项，仅上游既有 `test_video_fill_meta_uses_desc_then_first_tag` 失败。`sau xiaohongshu upload-note --help` 只出现 `--declaration` / `--repost-source`，已无 `--collection`。

### 合集（PR2 合并态，2026-11-10 历史记录）

- `--collection 西天路上的谜团` 选中后入口文案变为合集名，「选择合集」消失；
- 传入不存在的合集名时打印告警并保持未选状态，不中断流程。

已知遗留（均为上游既有问题，与本次改动无关）：

- `test_video_fill_meta_uses_desc_then_first_tag` 期望 wait 超时 2000ms，源码为 4000ms；
- 全套 `unittest discover` 中 article_render / dayu / instagram / xueqiu 等区域的失败与错误。

## 重新安装 sau 后

`sau` 已于 2026-11-10 在 `E:\workbenchs\social-auto-upload` 原地 `git init` 并关联 fork
`guestccc/social-auto-upload`，尚未 push。抖音两个补丁已提交在本地 `main`；声明改动留在工作区（**没有 commit**）；
合集改动只存在于本仓库的补丁文件。重新下载 / 覆盖安装会丢失，恢复方式：

```bash
git -C E:/workbenchs/social-auto-upload log --oneline --all   # 已提交的抖音补丁
git -C E:/workbenchs/social-auto-upload status --short        # 声明改动的未提交文件
```

- `main`：`35332c0` 抖音标题占位符、`ddca79e` 抖音 stealth
- 工作区未提交：声明改动 6 个文件（`sau_commands/xiaohongshu.py`、`uploader/xiaohongshu_uploader/main.py`、`tests/test_sau_browser_cli.py`、`tests/test_xiaohongshu_uploader.py`、`README.md`、`docs/CLI.md`）
- 合集改动：`.ai/sau-patches/patches/0002-xiaohongshu-collection.patch`，按上文命令应用

若小红书图文又出现「来源转载已声明（来源：）」，说明又走回了无条件 `check_original_declaration()`；
若无法设置 AI 声明，先确认发布页入口文案是否已改（当前为「添加内容类型声明」）。

## 上游参考

- Issue #185（小红书能力清单，原创申明 / 加入合集 标为待开发）
- Issue #291 / PR #295（小红书空来源转载声明，同一处代码）
- 发布页 DOM：2026-11-10 本地实测

## 已确认与遗留

已确认（2026-11-10，用户）：

1. 小红书默认声明「笔记含AI合成内容」，可在故事级关闭；
2. 合集归属故事级，一个故事一个合集；
3. 历史小红书图文先确认平台实际状态，再决定是否修正；
4. 暂不 commit、暂不 push，保持可本地检查的状态。
5. 声明与合集**不能混在一个 PR 里**，上游按 PR1（声明）/ PR2（合集）分别提交。

遗留：

- 小红书合集只能在**发布页**创建（用户 2026-11-10 确认），`sau` 目前只选择已存在的合集；
  新账号第一次发布时没有可选的合集，只能留空，等建好合集后再给后续章节设置。
- 若发布页合集弹窗内存在「新建合集」入口，可考虑让 `sau` 在发布时先建再选；
  需先在真实发布页确认弹窗结构，未验证前不做假设。
