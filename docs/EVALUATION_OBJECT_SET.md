# EVALUATION OBJECT SET — W2-2 评测物体选择

> 日期：2026-09-13 ｜ 性质：**selection registry（选择与记录）**——不是实验记录，不含任何新实验结果。
> 机器可读配置：`configs/evaluation_objects.yaml`（`evaluated: true` 仅标记已有真实实验的物体）。
> 数据来源：本地 BOP 子集 metadata（`models/models_info.json`、`test/*/scene_gt.json`、
> `dataset_info.md`）只读扫描 + YCB/BOP 公开物体描述（定性）。**未下载任何新数据。**

---

## 1. Selection Goal

为后续实验（Classical 扩评测、FoundationPose 对照、Phase 5 robustness）建立一个
**覆盖几何 / 外观 / 对称性谱系** 的 5–8 物体评测集，同时保持当前资源约束
（本地 12 场景子集、CPU 侧可跑、不扩数据）。

## 2. Selection Criteria

维度（打分 1=low … 5=high；Compute cost / Data availability 为 5=最优）：
Geometry diversity（相对 obj5/obj13 的新几何）、Appearance diversity（纹理/材质对比）、
Symmetry challenge（姿态歧义谱系）、Pose relevance（6D 评测适配）、Robustness value
（Phase 5 变量价值）、Data availability（本地帧数/场景数）、Compute cost、Demo value。

**打分只作参考，不机械加权**——最终选择按可解释的覆盖逻辑人工裁定（§6）。

## 3. Candidate Pool（全部 21 个 YCB-V 物体，本地可用性实测）

diameter 取 `models_info.json`（最大点对距离语义，与项目评测口径一致）；
frames = 物体在本地 12 场景中的出现帧数（scene_gt.json 实测）。

| id | name | d(mm) | frames | scenes | geometry / appearance / symmetry（定性） |
| --- | --- | ---: | ---: | --- | --- |
| 1 | 002_master_chef_can | 172.1 | 300 | 48,51,55,56 | 圆柱罐；标签纹理；轴对称 |
| 2 | 003_cracker_box | 269.6 | 225 | 50,54,59 | 大扁盒；**强纹理**；非对称 |
| 3 | 004_sugar_box | 198.4 | 375 | 49,51,54,55,58 | 盒；中纹理；近盒对称 |
| 4 | 005_tomato_soup_can | 120.5 | 450 | 6 scenes | 圆柱罐；标签纹理；轴对称 |
| **5** | **006_mustard_bottle** | **196.5** | 150 | 50,52 | 弯曲瓶身；中弱纹理；**近轴 roll 歧义** |
| 6 | 007_tuna_fish_can | 89.8 | 300 | 48,49,52,59 | 扁圆盘罐；金属低纹理；**极端旋转对称** |
| 7 | 008_pudding_box | 142.5 | 75 | 58 | 小盒；低纹理；近对称 |
| 8 | 009_gelatin_box | 114.1 | 75 | 58 | 小盒；中纹理；近对称 |
| 9 | 010_potted_meat_can | 129.5 | 225 | 49,53,59 | 小方罐；标签；近对称 |
| **10** | **011_banana** | **197.8** | 150 | 50,56 | **细长弯曲**；黄色中纹理；**完全非对称** |
| 11 | 019_pitcher_base | 259.5 | 225 | 52,56,58 | 壶身；低纹理；近轴对称 |
| 12 | 021_bleach_cleanser | 259.6 | 300 | 51,54,55,57 | 高圆柱；环绕标签纹理；轴对称 |
| **13** | **024_bowl** | **161.9** | 150 | 49,53 | 开口曲面碗；低纹理；**旋转对称** |
| **14** | **025_mug** | **125.0** | 150 | 48,55 | 杯体近轴对称 + **手柄打破对称**；低纹理 |
| **15** | **035_power_drill** | **226.2** | 300 | 50,54,56,59 | **复杂机构**；强纹理；非对称 |
| 16 | 036_wood_block | 237.3 | 75 | 55 | 大木块；几乎无纹理；近对称 |
| 17 | 037_scissors | 204.0 | 75 | 51 | 薄金属片；低纹理；近对称 |
| 18 | 040_large_marker | 121.4 | 150 | 57,59 | 细圆柱；标签；轴对称 |
| 19 | 051_large_clamp | 174.7 | 150 | 48,54 | 金属夹具；低纹理；局部对称 |
| 20 | 052_extra_large_clamp | 217.1 | 150 | 48,57 | 金属夹具；低纹理；局部对称 |
| 21 | 061_strawberry | 102.9 | 75 | 57 | 小物体；强纹理；近对称 |

## 4. Final Object Set（7 个）

| Object | Name | Role | Primary reason |
| --- | --- | --- | --- |
| obj5 | 006_mustard_bottle | anchor（evaluated） | 既有基线锚点：roll 歧义 + 弱纹理瓶类 |
| obj13 | 024_bowl | anchor（evaluated） | 既有基线锚点：旋转对称 + 开曲面 |
| obj2 | 003_cracker_box | texture_diverse | 强纹理非对称盒——外观线索的富集端 |
| obj6 | 007_tuna_fish_can | symmetry_challenging | 极端对称 + 金属低纹理——歧义谱系最难端 |
| obj10 | 011_banana | geometry_diverse | 细长弯曲完全非对称——几何/点密度敏感端 |
| obj14 | 025_mug | symmetry_challenging | 近对称 + 手柄打破——对称谱系中间桥 |
| obj15 | 035_power_drill | robustness_oriented | 复杂机构 + 强纹理——几何复杂端 + demo 价值 |

## 5. Coverage Matrix

| Object | Geometry | Appearance | Symmetry | Robustness 轴 | Demo value |
| --- | --- | --- | --- | --- | --- |
| obj5 | compact curved bottle | weak/medium | near-axial roll | roll 歧义基线 | ★★★★★（已有） |
| obj13 | open curved surface | low | rotational | 遮挡敏感基线 | ★★★★（已有） |
| obj2 | large flat box (d=270mm) | **high texture** | asymmetric | 外观线索富集 / 尺度上限 | ★★★★ |
| obj6 | flat disc (d=90mm) | low + metallic | **extreme rotational** | 金属深度质量 / 完全歧义 | ★★ |
| obj10 | elongated curved thin | medium | **none** | 薄结构点密度 / 深度噪声 | ★★★★★ |
| obj14 | mug + handle | low | near + feature-broken | 手柄小特征遮挡 | ★★★★ |
| obj15 | complex mechanism | high | none | 复杂几何 / 自遮挡 | ★★★★★（已入 demo 场景） |

Rubric 明细（参考分，非决策依据）：

| obj | GeoD | AppD | SymC | PoseR | RobV | DataAv | CompC | DemoV | Σ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 3 | 3 | 4 | 5 | 4 | 5 | 5 | 5 | 34 |
| 13 | 4 | 2 | 5 | 5 | 4 | 5 | 5 | 4 | 34 |
| 2 | 4 | 5 | 2 | 5 | 3 | 5 | 4 | 5 | 33 |
| 6 | 3 | 2 | 5 | 4 | 5 | 5 | 4 | 2 | 30 |
| 10 | 5 | 4 | 1 | 4 | 5 | 5 | 4 | 5 | 33 |
| 14 | 4 | 3 | 4 | 5 | 4 | 5 | 4 | 4 | 33 |
| 15 | 5 | 4 | 1 | 5 | 5 | 5 | 3 | 5 | 33 |
| 12 | 3 | 3 | 4 | 4 | 4 | 5 | 4 | 3 | 30 |
| 1 | 2 | 3 | 4 | 4 | 3 | 5 | 4 | 2 | 27 |
| 21 | 4 | 4 | 3 | 3 | 4 | 3 | 2 | 4 | 27 |

## 6. Why Each Object

### obj5 006_mustard_bottle（anchor，evaluated）
- **Reason**：既有冻结基线（EXP-006：70/75=93.3%，roll 歧义 ×5）；弯曲瓶身 + 近轴 roll 歧义
  + 中弱纹理是全部后续对比的参照系。
- **Adds beyond**：本身即基线；提供「近对称但可解」的歧义档位。

### obj13 024_bowl（anchor，evaluated）
- **Reason**：旋转对称 + 开口曲面 + 低纹理（EXP-006：77.3%，重遮挡失败 16 帧）；
  对称物体必须用 ADD-S 的协议样本。
- **Adds beyond**：提供「完全旋转对称」档位与遮挡敏感案例。

### obj2 003_cracker_box
- **Reason**：全集中**最强的外观线索**（大面积高纹理）与最大直径（269.6mm），
  非对称盒几何与 obj5/obj13 的曲面/对称形成互补；与 obj5 同场景（50）可做同场景对照。
- **Adds beyond**：外观富集端——检验「纹理充分时方法表现」，与 obj6（无纹理金属）构成
  纹理谱系两端；平面盒几何为新类型。

### obj6 007_tuna_fish_can
- **Reason**：**对称谱系最难端**（扁圆盘：roll 完全退化 + 上下翻转歧义）+ 金属低纹理；
  d=89.8mm 提供小尺度档。
- **Adds beyond**：完全歧义下的 ADD-S 评测极值案例；金属表面深度质量是 Phase 5
  depth-noise/occlusion 轴的自然载体。demo 价值低是已知代价（位姿错误不直观），
  由其余物体补偿。

### obj10 011_banana
- **Reason**：**完全非对称**（谱系另一端）+ 细长弯曲薄结构——点密度与深度噪声敏感性
  远高于紧凑物体；黄色中纹理、轮廓独特。
- **Adds beyond**：无对称性的「位姿唯一可解」端；薄结构在扰动下的鲁棒性研究价值高；
  与 obj5 同场景（50）；demo 表现力强。

### obj14 025_mug
- **Reason**：杯体近轴对称但**手柄打破对称**——位于 bowl（全对称）与 box/banana（非对称）
  之间的中间档；低纹理；d=125mm。
- **Adds beyond**：对称谱系桥梁 + 「小特征决定位姿」现象（手柄遮挡/可见性直接改变可解性），
  是 controlled occlusion 实验的优质变量。

### obj15 035_power_drill
- **Reason**：**几何复杂度极值**（机构、凹腔、自遮挡）+ 强纹理 + 完全非对称；
  300 帧可用；已出现在 EXP-006/demo 场景（scene 50），观众天然熟悉。
- **Adds beyond**：复杂几何端——经典几何方法在自遮挡/非凸结构上的预期退化点，
  Phase 5 的核心压力测试对象；README/面试 demo 价值最高。

## 7. Rejected Candidates

| Object | 竞争力 | 不选原因 |
| --- | --- | --- |
| obj12 021_bleach_cleanser | 高（300 帧、环绕纹理、对称） | roll 歧义轴与 obj5 重叠；对称轴已由 obj6+obj13 覆盖；将成为第 4 个「容器」轮廓。**第一替补**：若需「对称几何 + 强纹理」轴再引入 |
| obj1 002_master_chef_can | 中 | 圆柱对称与 obj6 重叠、纹理中等，无新增覆盖轴 |
| obj4 005_tomato_soup_can | 中（450 帧） | 同上——圆柱冗余；帧数多不构成选择理由 |
| obj21 061_strawberry | 中高（尺度极小端） | 仅 1 场景/75 帧；小物体会改变点密度 regime，混入后破坏受控对比。列为未来 scale 扩展 |
| obj19/20 large/XL clamp | 中 | 金属薄结构有深度质量研究价值，但 demo 可读性差、全失败风险高；留作金属深度轴候选 |
| obj17 037_scissors | 中 | 1 场景；薄金属位姿视觉歧义大，解释成本高 |
| obj16 036_wood_block | 低 | 近无纹理大块——外观欠定；盒几何已由 obj2 覆盖 |
| obj3/8/9 小盒罐 | 低 | 与 obj2（盒）/obj6（罐）冗余；obj7/8 仅 1 场景 |
| obj11 019_pitcher_base | 低中 | 第 5 个近对称容器轮廓，冗余 |
| obj18 040_large_marker | 低 | 细圆柱，与已有对称物体冗余 |

## 8. Phase 5 Relevance

该 7 物体集为 controlled robustness matrix 提供的变量轴：

- **Symmetry spectrum**（核心轴）：bowl / tuna（完全对称）→ bottle（近轴 roll）→
  mug（特征打破）→ box / banana / drill（非对称）——同一扰动下可量化「对称度 × 扰动」交互。
- **Appearance spectrum**：cracker/drill（强纹理）→ bottle（中弱）→ bowl/mug/tuna（低纹理金属）——
  纹理线索依赖度可分离。
- **Geometry spectrum**：凸简单（盒/罐）→ 曲面（瓶/碗）→ 薄结构（banana）→ 复杂机构（drill）。
- **Scale**：89.8–269.6mm（2.9× 跨度），深度噪声敏感度天然分层。
- **Occlusion 行为先验已知**：bowl 重遮挡失败 16 帧、bottle roll 歧义 5 帧（EXP-006），
  Phase 5 可直接在同一协议下对照。

## 9. Current Data Availability

**全部 7 个物体本地完备，零下载**（models 21/21 在本地；场景实测见 §3）：
obj5=150 帧、obj13=150、obj2=225、obj6=300、obj10=150、obj14=150、obj15=300，
分布在 scenes 48–59。obj2/obj10/obj15 与 obj5 同在 scene 50（同场景多物体对照可行）。

## 10. Future Expansion Notes

- **scale 轴**：obj21 strawberry（1 场景，需先评估点密度 protocol）。
- **metallic depth 轴**：obj19/20 clamp、obj17 scissors。
- **对称+强纹理轴**：obj12 bleach_cleanser（第一替补）。
- 以上均记录为 future acquisition/extension，**本阶段未做任何下载**。
