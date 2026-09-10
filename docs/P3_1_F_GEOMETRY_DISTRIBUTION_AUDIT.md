# P3.1-F: Synthetic vs Real Geometry Distribution Audit

> 日期：2026-09-10
> 问题：真实 YCB-V 输入给 CoordNet 的**几何分布**（网络真正收到的归一化 XYZ）与训练/验证 synthetic
> 几何输入差多少？这种差异能否为 real-domain 中稳定的 ~176° canonical orientation bias 提供**直接证据**？
> 性质：只读统计审计。零模型/checkpoint/管线修改，零重训。GT 仅评测端使用（canonical 反算）。
> 执行：`scripts/p3_1_f_geometry_distribution.py`；数据 `outputs/p3_1_f_geo_stats/`（JSON + 覆盖直方图 PNG）

## 测量对象（网络真正看到的输入）

- real：`mask → deproject → frame_seed 采样 1024 → max-radius normalize → XYZ`（与 Gate 3 逐位同构，
  frame_seed 公式一致；GT 仅用于把采样点反算到 canonical frame 做覆盖统计）
- synthetic：Gate 2 val 50 样本 + Gate 1 train 200 样本的存储 npz（2048 点，为 eval 子集的超集——已注明）
- bowl 参考池使用 `data_synth/bowl`（**非正式产物**，见 EXP-008 附记；同物体比较所需，已注明来源）

## 结果总表

### A. 网络 literally 看到的归一化 XYZ（逐轴 std）

| 组 | cam_norm 轴 std (x,y,z) | 对照：synthetic val [0.183, 0.398, 0.230] |
| --- | --- | --- |
| bottle clean（4 帧） | [0.122, 0.388, 0.181] | 同量级（x −33%、z −21%） |
| bottle 721 | [0.010, 0.021, 0.043] | **压缩 4–18×（严重 OOD）** |
| bowl（5 帧） | [0.035, 0.025, 0.086] | **压缩 4–16×（严重 OOD）** |

### B. 深度质量（real 独有；synthetic 无洞无噪）

| 组 | 有效深度占比 | 深度离群点（\|z−median\|>0.25m） |
| --- | ---: | ---: |
| bottle clean | 89–94% | **0** |
| bottle 721 | 94% | **66**（mask 边缘泄漏 → 3.2m 点，确认 P3.1-B 诊断） |
| bowl | 88–93% | **42–316/帧**（碗缘多次反射） |

### C. Canonical 覆盖域差（NN → 同物体合成池；合成基线 0.475mm）

| 组 | NN 域差倍数 | 覆盖直方图 L1（对同物体合成均值） |
| --- | ---: | ---: |
| bottle clean | **2.43–3.27×**（mean 2.75×） | 0.72–0.99 |
| bottle 721 | **12.68×** | 0.83 |
| bowl | **5.7–33.3×**（mean 23.0×） | 0.40–0.60 |

公平基线：**单个**合成 view 对 50-view 均值的 L1 自然波动 = 0.47–0.84（median 0.60，bottle）；
bowl 合成单 view 波动 0.20–0.88。real 值落在或略超该自然波动带。

### D. 判定（对核心问题的直接回答）

| 组 | 几何分布差距 | 能否直接解释该组的 ~176° 翻转？ |
| --- | --- | --- |
| **bottle clean** | **小**（NN 2.75× ≈ 1mm 深度噪声级；轴 std 同量级；scale 在训练范围内；0 离群点） | **不能。** 近 in-distribution 的输入上发生确定性 176.5° 翻转 → 属"零裕度朝向决策 / 朝向锚点缺失"，不是分布问题 |
| **bottle 721** | **大**（scale 20×、66 离群点、归一化坐标压缩 4–18×） | **能（针对其预测坍缩）**——与 P3.1-A"修复 scale 不改善预测"合并解读：坍缩破坏逐点预测，但 P3.1-C 证明其 pose 仍可被固定旋转+ICP 恢复 |
| **bowl** | **大**（NN 5.7–33×、离群点 42–316/帧、覆盖 L1 超出自然波动带上限） | **能（针对其预测坍缩与结构错误）**；叠加未训练物体因素 |

## 核心结论：两个截然不同的 failure regime

P3.1-F 最重要的产出是把 real-domain 失败切成两个机制不同的 regime（都经 P3.1-C 的同一 ~176.5° 偏移表现）：

1. **Regime 1 — clean bottle（4 帧）**：几何 near-in-distribution（~1mm 噪声级）+ 确定性翻转
   → **不是分布问题**，是网络朝向决策在 real domain 的**裕度崩塌/锚点缺失**。
2. **Regime 2 — frame 721 + bowl 全部**：严重几何 OOD（尺度污染 10–20×、大量离群点、NN 域差 12–87×）
   → 预测坍缩，分布差异**是**直接原因之一（叠加 bowl 的未训练物体因素）。

对"下一轮该做什么"的含义：若重启学习路线，Regime 1 的修复方向是**朝向锚点/等变性**
（而非单纯堆数据——近 in-distribution 输入也翻转）；Regime 2 的修复方向是**几何域对齐**
（深度噪声/遮挡/泄漏模拟，与 P3.1-E 的几何通路结论一致）。

## Confirmed facts

1. 两个读取器（手写解析/Open3D）逐位一致（P3.1-D），本审计的 synthetic 侧与训练数据同源。
2. real bottle clean 的归一化 XYZ 轴 std 与 synthetic 同量级（差 21–33%），NN 域差 2.75×（≈1mm 深度噪声级）。
3. frame 721：66 个深度离群点（mask 泄漏）、归一化尺度 2.466m（训练上界的 20×）。
4. bowl：每帧 42–316 个深度离群点、NN 域差 5.7–33.3×（对同物体非正式合成池）。
5. 全部 real 帧存在 6–11% 深度空洞（synthetic 为 0）。

## Strong evidence

6. real-domain 失败分属两个 regime：clean bottle = 近 in-distribution + 翻转（裕度问题）；
   721/bowl = 严重 OOD + 坍缩（分布问题）。两组的证据在 P3.1-A/E/C 的交叉验证下自洽。
7. 覆盖直方图差异（real clean L1 0.72–0.99）仅略超合成单 view 自然波动（0.47–0.84），
   且与 visibility 无相关（P3.1-B 已示 visib 0.99–1.00）——不支持"覆盖缺失导致翻转"。

## Hypotheses（未证明）

- H-f1：clean bottle 的翻转源于网络朝向决策对深度噪声级扰动的零裕度
  （可用"合成数据 + 1mm 深度噪声"重训/评测验证——留待批准）。
- H-f2：bowl 深度离群点来自碗缘多次反射（可用 mask 腐蚀或离群剔除验证）。
- H-f3：真实帧的桌面遮挡使 canonical z 分布偏斜（本轮直方图部分支持，未做定向检验）。

## 审计过程诚实记录

本脚本曾出现 3 处实现问题（字典字面量内引用未建键、canonical 数组被 stats dict 覆盖、
bowl 帧误用 bottle 参考池导致跨物体 NN 无意义），均在提交前发现并修正；
最终数值以修正后脚本为准。早期跨物体 bowl NN 数值（55–87×）作废。

## 边界

- synthetic 侧使用存储 npz 的 2048 点全量（训练/评测实际用 1024 子集）——分布等价，已注明。
- bowl 参考池来自非正式数据（EXP-008 附记），仅用于同物体覆盖比较。
- 覆盖直方图为 6×12 球面分箱的粗粒度度量；不排除更细粒度的分布差异。
