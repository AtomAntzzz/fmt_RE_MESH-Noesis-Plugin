# RE Engine Noesis / Maya Tool

[中文](./README.md) | [English](./README.en.md)

本仓库把 alphaZomega 的 Noesis RE Engine 资产插件与 AtomAntzzz 的 Maya 动画工作流合并在一个维护入口中。当前发布树不包含 3ds Max MaxScript。

## 文件

- `fmt_RE_MESH.py`：Noesis 的 RE Engine MESH、TEX、MDF/MDF2、MOTLIST 等资产插件。
- `re_engine_*.py`：按职责拆分的内部模块；`re_engine_common.py` 保留原公共接口。必须与入口一起安装。
- `pragmata_gdeflate_x86.dll` / `pragmata_gdeflate_x64.dll`：PRAGMATA 与 Monster Hunter Wilds 压缩 TEX 使用的 GDeflate CPU 解码桥。
- `REEM_Noesis_Maya.py`：通过 Noesis 导入 MESH/MOTLIST、读取动画日志并批量切分片段的 Maya 工具。

## 支持的游戏

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
- PRAGMATA（模型、材质、纹理、独立骨骼动画及模型动画绑定；具体范围见下文）
- Monster Hunter Wilds（模型、基础材质、纹理和模型绑定动画；具体范围见下文）

前 11 款游戏沿用 alphaZomega v3.28 的公开支持列表，PRAGMATA 和 Monster Hunter Wilds 为本分支新增支持；各游戏的功能范围不同。Wilds 已在本地分支实现，尚未整合到公共发布。Resident Evil 9 不在支持列表中。

各游戏共用基础材质预览流程：查找模型对应的材质与贴图，按通用规则显示颜色、法线/粗糙度、透明及自发光等可用槽位。PRAGMATA 已在本地分支合入该流程，尚未公共发布。Noesis 以查看大概效果为目标，不复现完整游戏 shader；眼睛、皮肤和复杂混合可能失真。UE 专用材质及按槽位一键导入尚未实现。

## Monster Hunter Wilds：现在能做什么

已支持模型、基础材质、纹理的导入与预览，以及兼容动作的模型绑定和播放。验证版本为 Windows Steam build 24705561；其他版本和全游戏覆盖率尚未统计。

| 功能 | 当前可用内容 | 已知限制 |
| --- | --- | --- |
| 模型 | 几何、骨架、权重、LOD、配套 streaming 及已观察 MPLY 结构；玩家四部件静态组合、手持/穿戴装备、人形/非人形、建筑篷架、小道具、简化树和低矮植丛已有代表预览 | 固定 80 个模型中 75 个通过基础材质导入，5 个因位置编码或 streaming 索引布局被拒绝；另 5 个植物样本通过。组合动画、其他结构及全游戏覆盖未验证 |
| 材质 | 共用查找规则自动尝试同名、`_mat`、`_00`、`_v00`、`_a`，回退到本游戏解包目录，并可读取经模型/MDF 哈希核验的共享材质关联文件；加载基础颜色、法线/粗糙度和自发光 | 普通候选仍优先，其他变体可手动选择；共享关联文件需先核实场景上下文。玩家肤色可能不一致，部分地表默认光照很黑；专有 shader 和复杂混合效果未完整支持 |
| 纹理 | TEX 解码和基础显示，支持已观察的 raw/GDeflate 数据及配套 streaming 资源 | 体积贴图预览首个切片；未观察的布局或 codec 可能被拒绝 |
| 动画 | 在模型上选择、绑定和播放兼容的 MOTLIST 动作，支持多动作及跨文件队列；已补齐三种已观察的位移编码 | 两个自然动画文件的 155 个唯一动作（179 个条目）均通过解码和宿主绑定；其他动作/角色配对未全面验证，不支持独立打开 `.motlist.992` |

适用文件版本：`.mesh.241111606`、`.mdf2.45`、`.tex.241106027`、`.motlist.992`。保留解包后的 `natives/stm` 和 `streaming` 目录结构；模型、材质和贴图应来自同一版本，不能通过重命名旧版贴图后缀来替代。

角色材质查找已补充受限的男女共用 MDF 回退，并优先使用 MDF45 明确指定的主颜色和主法线槽，避免将细节或损伤贴图误作主贴图。角色路径中的顶点颜色按 shader 遮罩处理，不再直接叠加到预览颜色上；原始解析数据仍保留，但这些模型的 Noesis 模型及后续通用格式导出不包含该顶点颜色流。眼部偏黑、FakeAO 辅助面发白及部分肤色差异仍是基础预览的已知限制。

植物按材质中的透明裁剪标志与实际遮罩槽显示叶缘；简化树的实体树冠不代表细叶还原。需要新增 `.stmesh` / STM8 读取结构的植被不在本次范围，包括已确认的草/芦苇状样本；不能据此推定所有草都使用这种格式。

建议使用 64 位 Noesis。打开模型后沿用动画选择窗口加载动作；未支持的动作会明确拒绝。游戏内 shader、程序 IK、MTRE 语义、原生文件写回及游戏内验证不在当前支持范围。Noesis 通用格式转换与游戏原生写回是不同功能，Maya 动画导出尚未验证。

## PRAGMATA：现在能做什么

已实现模型、基础材质、纹理和骨骼动画的导入与预览。纹理有大规模结构验证；模型、材质和动画已通过代表样本验证，全游戏兼容覆盖率尚未统计，部分模型或动作仍可能无法读取。

| 功能 | 当前可用内容 | 验证范围与限制 |
| --- | --- | --- |
| 模型与骨架 | 导入几何、骨架和权重；支持已观察的多材质、多级细节（LOD）、单/双数据段 streaming 及部分 MPLY；玩家、手持/穿戴装备、人形/非人形、建筑场景、小道具、树与低矮植丛已有代表预览 | 固定 96 个模型中 83 个几何导入成功（82 个带基础贴图、1 个合法无贴图轮廓），13 个仍被拒绝。其余布局、全游戏覆盖及逐模型视觉未全面验证 |
| 基础材质 | 共用路径查找贴图并显示颜色、法线/粗糙度、透明裁剪、自发光；现有提取集 13,032 个 MDF 解析通过 | 解析成功不等于完整效果还原。眼睛发白、部分区域偏黑，非零发光部件可能显示纯白；大型场景的分层、贴花与玻璃可能黑白或斑点化，复杂混合效果不完整 |
| 纹理 | raw/GDeflate 解码，数组与立方体贴图按图层/面读取，可选加载 mip | 现有提取集 22,346 个文件通过结构解析，15 种像素格式及数组/立方体/体积代表通过 Noesis 转换；不是逐文件像素或视觉验证，体积贴图预览首个切片 |
| 骨骼动画 | 独立骨架预览、模型绑定、动作选择和跨文件队列 | 已验证一个单动作样本、主角目录中的 24 个含动作文件，以及主角模型的代表动作绑定；其他角色、动作布局和模型配对未全面验证 |
| 表情形变 | 部分模型可按数字帧预览 | 不提供按源名称选择形变；不是所有面部模型都已验证 |

适用文件版本：`.mesh.251121828`、`.mdf2.51`、`.tex.251111100`、`.motlist.1057`（MOT 993）。相同后缀并不保证所有文件兼容；不同游戏更新也可能改变布局。

需要新增 `.stmesh` / STM8 结构支持的植被不在本次范围，包括已识别的草叶、开花草本和蕨类样本。普通 MESH/MPLY 的树、低矮叶簇和落叶已有预览；未确认的其他活草不能记为已支持或不存在。固定批量的成功数只表示实际读取/加载结果，不表示每个文件都经过人工视觉验收。

### 打开模型和播放动画

- 保留解包后的目录结构和配套文件。需要 streaming 数据的模型，应打开主模型文件，并保留相应的 streaming 文件；不要单独打开无头部的 streaming 数据文件。
- 可以直接打开 MOTLIST 预览其自带骨架，也可以在模型上加载动作。
- 模型绑定：打开 MESH → `Select Animations` → 选择 MOTLIST（可以粘贴完整路径）→ 双击动作或 `[ALL]` 加入队列 → 点击 `Load` 返回 → 在模型窗口点击 `Load`。
- 动画使用与 DD2 相同的公共动画选择窗口，可跨文件排队；取消后重开保留目录与队列。
- 模型缺少的骨骼轨道会跳过并记录数量；没有匹配轨道或存在已知父空间冲突时拒绝绑定。任意模型和动作不能直接互换。
- PRAGMATA 的 `Force Center`、`Sync by Frame Count`、`Force Merge All` 暂不可用并置灰，DD2 原选项保持可用。

### 已知限制

- 基础材质显示已完成；不还原完整游戏 shader。材质参数能被读取，不等于每个效果都会显示。
- 通用映射可能改变主贴图选择，例如采用损伤贴图。脸部 EyeShell 的 OBJ/MTL 贴图路径与输出 PNG 名称可能不一致，需手动修正；不保证导出材质可直接用于 UE。
- 不支持 MTRE 动画数据；仅含 MTRE 的文件无法作为骨骼动作加载。
- 32 位 Noesis 反复重载较大的 MOTLIST 可能出现内存不足，旧版本也存在此问题，目前未修复。尚未验证同一大样本在 64 位下反复重载，不承诺换位数即可解决。
- 不提供 PRAGMATA 原生 MESH/TEX/MOTLIST 写回、独立重新导入或游戏内验证流程，不能据此制作已验证可回写游戏的文件。
- 上一项不限制 Noesis 将已读入内容转换为 FBX、OBJ、PNG、TGA 等通用格式。骨架、动画和形变能否保留取决于导出器与选项；并非所有转换组合都已验证。

## 安装 Noesis 插件

1. 从 [Noesis 官方页面](https://www.richwhitehouse.com/index.php?content=inc_projects&showproject=91)下载并安装 Noesis。
2. 将 `fmt_RE_MESH.py` 和根目录下全部 `re_engine_*.py` 复制到 `[Noesis 安装目录]/plugins/python/`，共 21 个 Python 运行时文件。更新时替换整套模块，避免混用版本。
3. 使用 32 位 `Noesis.exe` 时，把 `pragmata_gdeflate_x86.dll` 放到同一 `plugins/python/`；使用 64 位 `Noesis64.exe` 时使用 `pragmata_gdeflate_x64.dll`。
4. 两份 DLL 可以同时存在，插件按当前 Noesis 进程位数选择。重启 Noesis 后打开模型、纹理或动作文件。

两款游戏共用这套插件，无需分别安装。需要查看材质时，在模型加载窗口勾选 `Load Textures` 再点击 `Load`；关闭该选项会只加载模型。

查看透明叶片时，在 `Tools → Data Viewer → Persistent settings → View` 将 `Render opacity mask` 设为 `1`，并保持着色开启（`F5` 切换）。关闭着色可能使叶片消失。风动和完整游戏材质效果不提供。插件包不包含游戏资源；额外资源根也必须保留 `natives/stm` 与 `streaming` 的对应目录结构。

如果日志出现 `gdeflate-helper-missing`，请检查对应位数的 DLL 是否放在上述目录。未压缩纹理不需要该 helper；GDeflate 压缩纹理需要它。组件说明和许可证见 [GDeflate 说明](./tools/pragmata_gdeflate/README.md)。

## Maya 动画工作流

1. 在 Maya 打开 **窗口 → 常规编辑器 → 脚本编辑器**。
2. 通过 **文件 → 打开脚本** 选择 `REEM_Noesis_Maya.py`，再保存到工具架。
3. 在 REEM 中选择 Noesis 可执行文件及 `.mesh.*` 或 `.motlist.*`。
4. 对上游已支持的 MOTLIST，可在 Noesis 选择窗口双击 `[ALL]` 后载入，再按片段导出。

PRAGMATA 的 Maya 动画导出流程尚未验证。Noesis 内可以绑定和播放动画，不代表经 Maya 导出的结果已经验证。

## 来源与说明

- Noesis 插件来源：[alphazolam/fmt_RE_MESH-Noesis-Plugin](https://github.com/alphazolam/fmt_RE_MESH-Noesis-Plugin)
- Maya 工具原仓库：[AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool](https://github.com/AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool)

来源、合并历史、GDeflate 第三方组件和权利状态见 [NOTICE.md](./NOTICE.md)。仓库不包含商业样本、完整文件名列表、提取清单、日志或截图。
