# RE Engine Noesis / Maya Tool

[中文](./README.md) | [English](./README.en.md)

本仓库把 alphaZomega 的 Noesis RE Engine 资产插件与 AtomAntzzz 的 Maya 动画工作流合并在一个维护入口中。当前发布树不包含 3ds Max MaxScript。

## 文件

- `fmt_RE_MESH.py`：Noesis 的 RE Engine MESH、TEX、MDF/MDF2、MOTLIST 等资产插件。
- `re_engine_*.py`：按职责拆分的内部模块；`re_engine_common.py` 保留原公共接口。必须与入口一起安装。
- `pragmata_gdeflate_x86.dll` / `pragmata_gdeflate_x64.dll`：PRAGMATA TEX 所需的 GDeflate CPU 解码桥。
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
- PRAGMATA（模型、材质、纹理和独立骨骼动画；具体范围见下文）

前 11 款游戏沿用 alphaZomega v3.28 的公开支持列表，PRAGMATA 为本分支新增支持；各游戏的功能范围并不完全相同。Resident Evil 9 和 Monster Hunter Wilds 不在本仓库当前已验证声明中。PRAGMATA 仅限已观察 profile，不能理解为其全部 build、全部角色或所有同后缀文件都受支持。

## PRAGMATA 支持范围

这里把 `readable`（能够按已验证结构安全读取）和 `previewable`（另有 Noesis 预览证据）分开。能力选择使用 internal version 与结构不变量，不单靠游戏名或外部后缀。

| 资产 | 已观察身份 | 当前声明 |
| --- | --- | --- |
| MESH/MPLY | `.mesh.251121828`，internal `250707828`，魔数 `MESH` 或 `MPLY` | 冻结的 ordinary candidate 002、standalone multi-material、standalone multi-LOD、RE-067A reserved-ushort submission boundary、candidate 001 paired streaming、RE-067B compact one-entry paired streaming、RE-067C binary16 blend-shape、paired MPLY、playergame 和 face base-geometry profiles 为 scoped `readable`；只有已有独立 Noesis GUI 证据的子集为 `previewable`。 |
| TEX | `.tex.251111100`，internal `251111100` | observed structural matrix 为 bounds-safe `readable`；原 256×256 BC7 / 6-mip exact profile 有独立像素 oracle，并为 `previewable`。其他格式只按下述代表性证据声明。 |
| MDF2 | `.mdf2.51`，observed header version `1` | candidate 002 单材质 exact profile 及 playergame/face observed multi-material profiles 可读取和绑定；不保证 proprietary master shader 还原。 |
| MOTLIST | 冻结的 `.motlist.1057` / MOT `993` standalone profiles | RE-066 单动作、本地骨骼 exact profile，以及 RE-068 的 24 个 observed multi-action/shared-bones profiles 为 scoped `readable` / `previewable`；使用与 DD2 相同的公共动画选择窗口。 |

已冻结的 MESH 范围包括 ordinary、multi-material、multi-LOD、一个 companion 配对的 streaming profile 和一个 companion 配对的 MPLY profile。candidate 002 有 geometry/materialized GUI 证据；multi-LOD 有几何 GUI 证据。player/face 已有骨架 overlay 与确定性诊断姿态证据，但这只验证已观察 12-slot 权重影响，不等于完整角色着色、shape-key 可用性或自然动画 preview；没有独立 GUI 的 paired streaming/MPLY 也不会因为同一解析器能读就自动提升为 `previewable`。

TEX 的广度证据覆盖 22,346 个 observed `.tex.251111100` 文件的结构清点，并用真实 Noesis 验证 15 个 observed DXGI 格式及 array/cube/volume 代表。只有原 exact BC7 profile 做过独立逐像素 oracle；其余代表证明可操作的解码/导出路径，不表示所有 TEX 都有像素精确证明。

### 主角/脸部证据边界

- `playergame_mat.mdf2.51`：14 个材质、206 个贴图引用、1,380 个属性；headless Noesis 创建 14 个材质并解码 25 个物理 TEX。
- `ch0000_10_mat.mdf2.51`：6 个材质、51 个贴图引用、420 个属性；headless Noesis 创建 6 个材质并解码 8 个物理 TEX。
- 材质完成口径是对齐 alphazolam 原仓库的基础贴图映射，而不是复现 PRAGMATA proprietary shader：当前已覆盖 `BaseColor`、albedo→diffuse、normal/roughness→normal、emissive 基础映射，GUI 为 player `14/25`、face `6/8` Materials/Textures，因此该基础材质范围已完成。脸部虹膜、未验证 packed channels 和 master-shader fidelity 是额外 coverage debt，不影响这项基础支持声明。
- `ch0000_10` 的 91 个 observed shape 已有 finite delta、非零统计和 morph-frame 构造；真实 Noesis 已显示数值 frame 4/18，但尚未证明按源名称选择/切换 shape key，因此不声明形变整体 `previewable`。
- `ch0100_10` 的 observed encoding `2` 只按已冻结的 `padding1=1`、submesh reserved `0x100`、`4 × binary16`（XYZ + 零填充）exact profile 读取。独立 raw-byte oracle 与生产解析器均确认 107 × 10,982 条有限位移、payload SHA-256 `b9a53224...d5bb6`；真实 Noesis 导入并为目标子网格构造 107 个源命名 morph frame。该 CLI 证据把 exact profile 提升为 scoped `readable`，但没有 GUI 切换证据，故不声明为 `previewable`，也不外推其他 encoding/metadata。
- primary+extra 12-slot 权重结构和骨名映射已经独立核对；playergame 实际最大 8 个、face 最大 9 个非零影响。真实 Noesis 骨架 overlay 与独立姿态 OBJ 已验证 `L_UpperArm_Twist_2` 的 6,148 个变化顶点和 `C_Jaw` 的 1,871 个变化顶点，均为 0 escaped，未见错侧镜像、原点拉丝或爆点。该姿态只是冻结 source-X 平移的确定性 influence 诊断，不声明自然动画、MOTLIST、导出、独立 re-import 或游戏运行时。

## 安装 Noesis 插件

1. 从 [Noesis 官方页面](https://www.richwhitehouse.com/index.php?content=inc_projects.php&showproject=91)下载并安装 Noesis。
2. 把 `fmt_RE_MESH.py` 和仓库根目录下全部 `re_engine_*.py` 复制到 `[Noesis 安装目录]/plugins/python/`，共 20 个 Python 运行时文件，保持同一目录；更新时使用同一版本的整套模块。
3. 使用 32 位 `Noesis.exe` 时，把 `pragmata_gdeflate_x86.dll` 放到同一 `plugins/python/`；使用 64 位 `Noesis64.exe` 时放入 `pragmata_gdeflate_x64.dll`。
4. 两份 DLL 可以同时存在；插件按当前进程指针位数自动选择，不会把 x86 DLL 加载进 x64 进程或反过来。
5. 重启 Noesis，再打开已支持的 `.mesh.*`、`.tex.*` 或冻结 exact-profile `.motlist.1057` 文件。

没有匹配 DLL 时，未压缩 TEX 仍可按其 profile 处理，但需要 GDeflate 的 TEX 会以 `gdeflate-helper-missing:pragmata_gdeflate_x86.dll` 或 `gdeflate-helper-missing:pragmata_gdeflate_x64.dll` 明确失败；插件不会静默回退并显示错误像素。DLL 的固定 SHA-256、PE 架构、ABI、源码 provenance 和许可证见 [`tools/pragmata_gdeflate/README.md`](./tools/pragmata_gdeflate/README.md)。

### MOTLIST exact-profile 支持边界

RE-066 已完成已冻结的 PRAGMATA MOTLIST v1057 / MOT v993 单动作、本地骨骼 standalone exact profile：压缩轨道经独立 oracle 21/21 对齐，Noesis 通过 `NoeAnim` 系列中的 `NoeKeyFramedAnim` 导入并播放该 9 骨、7 animated bones、21 logical tracks、125 帧/60 FPS 动作。

RE-068 另外验证了 24 个 observed multi-action/shared-bones profiles，包括已观察的 dense/sparse/mixed 条目和共享骨骼布局。这些 standalone profiles 为 scoped `readable` / `previewable`，复用与 DD2 相同的公共动画选择窗口，支持切换文件、选择和排队加载动作。

PRAGMATA 动画目前应直接打开 MOTLIST，使用其自带骨架预览。Noesis 内从 MESH 的 `Select Animations` 入口直接绑定外部模型（external MESH binding）实测未通过，暂不支持；不要通过该入口强行输入 PRAGMATA MOTLIST 路径。无法匹配到骨架的轨道沿用既有策略跳过，并记录跳过数量。

该范围不覆盖 observed matrix 之外的其他 v1057 layouts、MTRE 语义、5 个 MTRE-only 文件、MOTLIST export、independent re-import 或 game runtime。不能把上述结果外推为所有 `.motlist.1057` 文件均受支持。

## 明确不支持的 PRAGMATA 范围

- 不支持一般 PRAGMATA MESH/TEX 写出，且不列为支持目标。这里指写回游戏原生 `.mesh.*` / `.tex.*` 文件；candidate 002 只有实验性、单样本、source-template exact writer implementation，不能代表通用 export，也不作为受支持的写回功能。
- 上述排除不指 Noesis 将已读入的模型或纹理转换为 FBX、OBJ、PNG、TGA 等通用格式；这些由 Noesis 对应导出器处理，是否保留骨骼、动画或形变取决于导出器和选项，不代表每种组合均已验证。
- 不提供独立 re-import；上游两个 MaxScript 只做 3ds Max FBX → Noesis FBX merge → FBX 回到 3ds Max，并不读取 PRAGMATA MESH writer 输出。
- 未做游戏运行时验证，不能声明 writer 输出会被游戏或官方工具接受。
- 不保证 proprietary master shader、未验证 packed channels、patch-only profiles、其他 build 或所有同后缀资产。

## Maya 动画工作流

1. 在 Maya 打开 **窗口 → 常规编辑器 → 脚本编辑器**。
2. 通过 **文件 → 打开脚本** 选择 `REEM_Noesis_Maya.py`，再保存到工具架。
3. 在 REEM 中选择 Noesis 可执行文件及 `.mesh.*` 或 `.motlist.*`。
4. 对上游已支持的 MOTLIST，可在 Noesis 选择窗口双击 `[ALL]` 后载入，再按片段导出。

此通用 Maya 流程不会扩大上述 RE-066/RE-068 standalone profiles 的声明。PRAGMATA 的 Maya 动画导出流程尚未验证；external MESH binding、范围外布局、export、independent re-import 与 runtime 仍不提供。

## 来源与说明

- Noesis 插件来源：[alphazolam/fmt_RE_MESH-Noesis-Plugin](https://github.com/alphazolam/fmt_RE_MESH-Noesis-Plugin)
- Maya 工具原仓库：[AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool](https://github.com/AtomAntzzz/RE-Engine-Mesh-Animtion-Noesis-Tool)

来源、合并历史、GDeflate 第三方组件和权利状态见 [NOTICE.md](./NOTICE.md)。仓库不包含 PRAGMATA 商业样本、文件名列表、提取清单、日志、截图或测试证据工件。
