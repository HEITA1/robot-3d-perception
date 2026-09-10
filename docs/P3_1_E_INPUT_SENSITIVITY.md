# P3.1-E: Input Sensitivity Diagnostic

> 日期：2026-09-10
> 问题：CoordNet 的 ~176.5° real-domain orientation bias，主要由 RGB、XYZ，还是二者的逐点关联驱动？
> 性质：**Input Sensitivity Diagnostic**——对 frozen checkpoint 的输入通道敏感性探针。
> **不是** "RGB-only vs XYZ-only 模型" ablation（checkpoint 从未在单模态输入上训练，零重训）。
> 执行：`scripts/p3_1_e_input_sensitivity.py`；数据 `outputs/p3_1_e_input_sensitivity/p3_1_e_results.json`

## 条件（预注册；审批消息在 Condition A 后截断，B/C/D 为标准敏感性集合，如与原稿不符可廉价重跑）

| 条件 | 定义 | 破坏的信息 | 保留的信息 |
| --- | --- | --- | --- |
| A `full` | XYZ + RGB | —（Gate 3 基线） | 全部 |
| B `rgb_mean` | XYZ + 逐帧通道均值 RGB 广播 | 逐点外观-几何关联 | 几何 + RGB 边际分布 |
| C `xyz_zero` | 归一化 XYZ 置零（质心）+ RGB | 逐点几何 | 外观 |
| D `rgb_shuffle` | XYZ + 按行随机重排的 RGB（固定种子） | 逐点外观-几何关联（保留边际分布的另一方式） | 几何 + RGB 边际分布 |

其余全部冻结：Gate 1 checkpoint、架构、权重、max-radius 归一化、voxel、采样种子、oracle mask、
10 帧（bottle 620/653/721/1044/1113，bowl 1/93/138/162/247）、RANSAC、ICP、metrics。
GT 仅评测端使用（canonical 误差 / 刚体对齐旋转偏置 / pose 误差）。
**合成对照**：Gate 2 val 的 10 个合成样本，同四条件——区分"real 触发"与"消融输入伪影"。

## 结果

### Real bottle（scene 50，5 帧；healthy = 预测半径 ~34mm，GT ~43mm）

| 条件 | median 偏置 (°) | canonical 误差 (mm) | pred 半径 (mm) | pose success |
| --- | ---: | ---: | ---: | ---: |
| full | **176.1** | 92.8 | 34.9 | 0/5 |
| rgb_mean | **173.4** | 96.4 | 33.5 | 0/5 |
| xyz_zero | 165.4（**坍缩**，r=2.2mm，证据弱） | 59.7 | 2.2 | 0/5 |
| rgb_shuffle | **175.8** | 92.4 | 34.9 | 0/5 |

### Real bowl（scene 53，5 帧；预测全程坍缩 r≈5–6mm，GT ~62mm）

| 条件 | median 偏置 (°) | canonical 误差 (mm) | pred 半径 (mm) | pose success |
| --- | ---: | ---: | ---: | ---: |
| full | 175.6 | 88.5 | 6.0 | 0/5 |
| rgb_mean | 175.2 | 82.1 | 5.0 | 0/5 |
| xyz_zero | 82.9（坍缩，证据弱） | 86.3 | 2.4 | 0/5 |
| rgb_shuffle | 176.8 | 88.1 | 5.9 | 0/5 |

### 合成对照（bottle，10 个 Gate 2 val 样本）——关键的判别行

| 条件 | median 偏置 (°) | pred 半径 (mm) |
| --- | ---: | ---: |
| full | **3.2** | 51.2 |
| rgb_mean | **49.7** | 45.5 |
| xyz_zero | 105.8（坍缩 r=1.3mm） | 1.3 |
| rgb_shuffle | **13.4** | 49.4 |

## 分析

### 发现 1：偏置与逐点 RGB 内容无关——"外观线索反转"假设被否定
rgb_mean 与 rgb_shuffle 以两种不同方式破坏逐点外观-几何关联，real bottle 的偏置几乎不变
（176.1° → 173.4° / 175.8°）。若 ~176.5° 翻转由标签正面/背面等外观线索在两域间反转驱动
（P3.1-D 的 H-b），破坏外观关联后偏置应消失或显著改变——实测没有。
**P3.1-D 的 H-b（强形式）被否定。**

### 发现 2：偏置在"纯几何输入"下依然存在——几何通路驱动
rgb_mean 条件下（仅几何有信息、预测未坍缩 r=33.5mm），偏置仍为 173.4°。
即：**真实几何本身就能触发 ~173° 翻转**。

### 发现 3：翻转是 real-domain 触发，不是消融伪影
合成对照显示：full 条件下合成域偏置仅 3.2°，而 real full 为 176.1°——同一条件定义、同一网络。
翻转由真实输入分布触发，而非消融输入的分布效应。
（消融输入在合成域确实引入退化：rgb_mean 49.7°、rgb_shuffle 13.4°、xyz_zero 105.8°+坍缩——
见下"发现 5"的叠加效应讨论。）

### 发现 4：逐点 RGB 在合成域是"承重"的——这使悖论更尖锐
合成域 rgb_mean 使偏置从 3.2° 恶化到 49.7°：网络确实**依赖逐点外观做朝向判定**。
但在 real domain，无论外观如何处理（保留/均值/打乱），偏置都是 ~173–177°。
最一致的解读：real domain 下几何通路的翻转已"饱和"，外观通路的贡献被淹没；
或外观通路在 real domain 同样失效但被几何翻转掩盖。

### 发现 5：xyz_zero 两域都坍缩（1.3/2.2mm），其偏置数（105.8°/165.4°）为坍缩伪影，
**不能作为"RGB 单独触发/不触发翻转"的证据**。RGB-only 的干净检验需要 rgb_mean 条件的
镜像操作（XYZ 保持、RGB 保留、几何置零做不到非退化），本轮无法给出。

## Confirmed facts

1. real full = 176.1°（复现 Gate 3/P3.1-B）；synthetic full = 3.2°——同一条件定义下 real/synthetic 断裂确认。
2. rgb_mean / rgb_shuffle 不改变 real 偏置（173.4° / 175.8° vs 176.1°）。
3. rgb_mean（非坍缩）下偏置仍 173.4°——纯几何输入足以触发。
4. rgb_shuffle 与 rgb_mean 结果一致——排除特定打乱方式的伪影。
5. xyz_zero 在两域均坍缩（半径 1.3–2.4mm），该条件下的偏置数不具解释力。

## Strong evidence

6. **偏置由几何通路驱动、与逐点外观无关**：发现 1+2+3 组合。
7. **"外观线索反转"假设（P3.1-D H-b）被否定**。
8. **域差定位收窄到"真实几何→canonical 朝向"这一条通路**：后续任何迭代
   （若路线重启）应针对几何域对齐（深度噪声模型/覆盖模式/遮挡结构），
   而非外观域随机化——RGB 侧 DR 对该失败无效。

## Hypotheses（未证明）

- H-e1：真实单视角几何的**覆盖模式**（桌面遮挡底部、深度空洞、边缘飞点）使网络的全局
  描述子落入翻转模式——可通过"合成渲染 + 桌面/遮挡模拟"验证（留待批准，非本轮）。
- H-e2：真实深度的噪声/量化改变逐点局部特征的分布，使 per-point 特征在朝向维度上退化。
- H-e3：网络容量（58.6k）不足以在几何单通道上保持朝向分辨率——与 Gate 1 的欠拟合签名一致。

## 边界

- 单模态条件对 frozen checkpoint 是 off-distribution 输入；xyz_zero 条件坍缩，其数值不具解释力。
- 本诊断不改变 Gate 3 NO-GO、不改变 P3.1-C 的诊断结论、不构成任何可部署改进。
- 10 帧 × 4 条件 × 2 物体 + 10 合成对照——smoke 规模，非统计性结论。
