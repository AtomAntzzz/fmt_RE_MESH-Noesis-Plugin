# RE Engine Noesis / Maya Tool

[中文](./README.md) | [English](./README.en.md)

本仓库将 alphaZomega 的 Noesis RE Engine 资产插件与 AtomAntzzz 的 Maya 动画工作流合并到同一个维护入口。当前仓库不包含 3ds Max MaxScript。

## 文件

- `fmt_RE_MESH.py`：Noesis 插件，用于读取和导出 RE Engine 的 MESH、TEX、MDF/MDF2、MOTLIST 等资产。
- `REEM_Noesis_Maya.py`：Maya 工具，通过 Noesis 导入 MESH/MOTLIST、读取动画日志并批量切分动画片段。

## 上游 v3.28 列出的游戏

- Resident Evil 2 Remake
- Resident Evil 3 Remake
- Resident Evil 4 Remake
- Resident Evil 7（Ray Tracing）
- Resident Evil 8
- Devil May Cry 5
- Monster Hunter Rise
- Street Fighter 6
- Exoprimal
- Apollo Justice: Ace Attorney Trilogy
- Dragon's Dogma 2

该列表沿用 alphaZomega v3.28 的公开说明，不代表尚未完成样本回归的新游戏已经得到支持。Resident Evil 9 和 Monster Hunter Wilds 不在本仓库当前已验证支持声明中；PRAGMATA 只具有下述严格限定的单 profile 支持。

## PRAGMATA 限定支持

当前只支持一个已观察样本的 candidate 002 exact MESH profile：外部后缀 `.mesh.251121828`、内部版本 `250707828`、ordinary standalone、non-MPLY、skinned、单 LOD / 单 group / 单 submesh；冻结样本 SHA-256 为 `78001dd7dd85da34434e48ae4a9426ba71d023d54dab30f3c490f69471fa4068`。

- 该 exact profile 的只读导入为 `readable`，Noesis 中的纯几何预览为 `previewable`。
- GUI 验证计数为 `Models 1 / Meshes 1 / Textures 0 / Materials 0 / Bones 229`；零纹理/材质表示材质化预览尚未支持，骨骼/权重视觉正确性也未验证。
- candidate 001、其他 `.251121828` 结构、multi-LOD、multi-material、streaming、MPLY、TEX/MDF2/MOTLIST、导出、独立重新导入和游戏运行时均不在该声明中。
- 插件对不符合上述结构不变量的同后缀文件会关闭该能力，不能把这个单样本 profile 理解为整个 PRAGMATA 格式族已获支持。

仓库不包含 PRAGMATA 商业样本、文件名列表、提取清单或 GUI 证据文件。

## 安装 Noesis 插件

1. 从 [Noesis 官方页面](https://www.richwhitehouse.com/index.php?content=inc_projects.php&showproject=91)下载并安装 Noesis。
2. 将 `fmt_RE_MESH.py` 放入 `[Noesis 安装目录]/plugins/python/`。
3. 重启 Noesis。打开受支持的 `.mesh.*`、`.tex.*` 或 `.motlist.*` 文件时，插件会自动参与识别。

Noesis 的 MESH 选择窗口可以双击加入同目录相关 MESH，再通过 **Load** 一起载入模型、骨架、材质和纹理。MOTLIST 动画通常选择列表顶部的 `[ALL]` 集合，以便一次导出全部动画。

## 安装 Maya 工具

1. 在 Maya 打开 **窗口 → 常规编辑器 → 脚本编辑器**。
2. 在脚本编辑器使用 **文件 → 打开脚本**，选择 `REEM_Noesis_Maya.py`。
3. 使用 **文件 → 将脚本保存至工具架**。
4. 打开 REEM 工具，通过 **Browse** 选择 Noesis 可执行文件。

## Maya 动画工作流

1. 在 REEM 中选择 `.mesh.*` 或 `.motlist.*`。
2. 对 MOTLIST，在 Noesis 选择窗口双击 `[ALL]`，再点击 **Load**。
3. Maya 导入完成后，工具从 Noesis 日志填充 **Animation List**。
4. 使用 **Export Selected Animations** 或 **Export All Animations** 按片段导出。

Noesis 某些无法正确解析的动画可能只产生第一帧，却在日志中保留完整帧数。工具会剔除明确 Warning、把 0 帧和 `blend_pose` 修正为 1 帧；其余异常可通过 **Manually Paste Noesis List** 手工把对应 `frames` 改为 1。此类异常动画进入 Unreal Engine 前仍需单独检查。

## Windows UTF-8 兼容性

`REEM_Noesis_Maya.py` 会在隐藏的 CP936 控制台中启动 Noesis，以兼容 Noesis 4.474 的嵌入式 Python 插件加载器。即使 Windows 开启“Beta 版：使用 Unicode UTF-8 提供全球语言支持”，命令行导出也不应再因为插件未加载而显示 `Detected file type: Unknown`。

该处理只影响 REEM 创建的 Noesis 子进程，不会修改 Windows 系统区域设置；MESH 关联文件和 MOTLIST `[ALL]` 的交互式选择窗口保持可用。

## 来源与说明

- Noesis 插件来源：[alphazolam/fmt_RE_MESH-Noesis-Plugin](https://github.com/alphazolam/fmt_RE_MESH-Noesis-Plugin)
- Maya 工具原仓库：[AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool](https://github.com/AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool)
- Maya 工作流补充说明：[知乎文章](https://zhuanlan.zhihu.com/p/685480151)

来源、历史合并和权利状态见 [NOTICE.md](./NOTICE.md)。
