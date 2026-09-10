# P3.1-B: Canonical Prediction Failure Analysis

## 实验设置

**严格冻结**：不训练、不 retrain、不修改 checkpoint / CoordNet / loss / optimizer / 网络结构 / RANSAC / ICP / normalization / mask / depth / 测试帧。

使用原 Gate 3 baseline pipeline（max-radius normalization）+ 原 Gate 1 frozen checkpoint（`outputs/p3_0/gate1/coord_net_bottle.pt`）。

P3.1-A robust normalization 不作为本轮正式实验变量。

**数据**：Gate 3 的 10 帧（bottle: 620, 653, 721, 1044, 1113; bowl: 1, 93, 138, 162, 247）+ 10 个 Gate 2 synthetic val samples 作为对照。

---

## 1. 核心结果：Raw → Translation → Rigid → Similarity

| Object | Domain | Raw (mm) | Trans-aligned (mm) | Rigid-aligned (mm) | Sim-aligned (mm) | Scale | Pattern |
|--------|--------|---------:|-------------------:|-------------------:|-----------------:|------:|---------|
| Bottle | Synthetic (n=10) | 5.51 | 3.73 | 3.00 | 2.78 | 1.010 | near-perfect |
| Bottle | Real clean (n=4) | 100.81 | 91.93 | 11.33 | 8.55 | 1.149 | ~176° rotation |
| Bottle | Real frame 721 | 60.50 | 57.45 | 53.66 | 58.72 | 18.030 | collapsed |
| Bowl | Real (n=5) | 88.53 | 65.17 | 57.79 | 47.88 | 10.232 | collapsed |

**关键发现**：clean bottle 的 raw error ~101mm 中，~90mm 可以被一个刚体变换解释（rigid-aligned residual ~11mm）。这个刚体变换的旋转角在所有 real frames 上一致为 ~176°。

---

## 2. 第一层：Raw Prediction Error

### 2.1 Synthetic 对照（bottle, 10 samples）

| 指标 | Mean | Min | Max |
|------|------|-----|-----|
| mean error (mm) | 5.51 | 4.25 | 8.74 |
| median error (mm) | — | 2.48 | 8.74 |
| p90 (mm) | — | 3.74 | 12.50 |
| RMSE (mm) | — | 2.70 | 9.94 |
| centroid shift (mm) | — | 2.2 | 7.5 |
| pred_radius / gt_radius | ~1.00 | 0.97 | 1.04 |

各轴 correlation：ax0 ≈ 0.998, ax1 ≈ 0.980, ax2 ≈ 0.999。网络在 synthetic 数据上表现接近完美。

### 2.2 Bottle Real（5 frames）

| Frame | visib | scale (m) | Raw mean (mm) | median | p90 | max | RMSE | centroid_shift (mm) | pred_r | gt_r |
|-------|-------|----------:|--------------:|-------:|----:|----:|-----:|--------------------:|-------:|-----:|
| 620 | 0.998 | 0.121 | 106.02 | 107.20 | 164.38 | 204.26 | 114.60 | 42.56 | 0.047 | 0.050 |
| 653 | 0.992 | 0.126 | 101.85 | 100.57 | 159.71 | 197.20 | 110.47 | 42.51 | 0.044 | 0.049 |
| 721 | 0.990 | 2.466 | 60.50 | 54.93 | 86.15 | 2411.43 | 121.09 | 13.37 | 0.004 | 0.055 |
| 1044 | 1.000 | 0.136 | 98.07 | 98.74 | 148.16 | 196.39 | 106.22 | 37.86 | 0.039 | 0.052 |
| 1113 | 1.000 | 0.118 | 97.30 | 98.96 | 150.46 | 211.73 | 106.03 | 34.45 | 0.041 | 0.051 |

各轴 correlation（clean 4 帧均值）：

| Axis | Correlation | 方向 |
|------|-----------:|------|
| X | −0.84 | 强负相关 |
| Y | +0.57 | 中等正相关 |
| Z | −0.997 | 近完美负相关 |

此 pattern 接近 180° Y 轴旋转 (x,y,z) → (−x,y,−z) 的预期 (−1, +1, −1)，但 Y 轴 correlation 偏弱。

### 2.3 Bowl Real（5 frames）

| Frame | visib | scale (m) | Raw mean (mm) | median | p90 | max | RMSE | centroid_shift (mm) | pred_r | gt_r |
|-------|-------|----------:|--------------:|-------:|----:|----:|-----:|--------------------:|-------:|-----:|
| 001 | 0.981 | 1.000 | 78.16 | 80.27 | 107.42 | 1031.92 | 87.37 | 55.56 | 0.006 | 0.054 |
| 093 | 0.984 | 1.082 | 86.87 | 83.14 | 110.00 | 1128.70 | 128.25 | 62.58 | 0.006 | 0.060 |
| 138 | 0.990 | 1.111 | 93.23 | 84.28 | 111.08 | 1160.80 | 150.86 | 65.83 | 0.006 | 0.067 |
| 162 | 0.997 | 1.168 | 97.80 | 88.17 | 113.59 | 1220.80 | 159.18 | 71.11 | 0.006 | 0.067 |
| 247 | 1.000 | 1.188 | 86.57 | 79.86 | 105.48 | 1235.88 | 117.64 | 59.41 | 0.006 | 0.063 |

**Bowl 的 pred_radius ≈ 0.006m，GT radius ≈ 0.06m** — prediction 坍缩到约 1/10 大小。

---

## 3. 第二层：Translation-Only Alignment

去除 centroid shift 后的 error：

| Object | Raw (mm) | Trans-aligned (mm) | Centroid 贡献 |
|--------|---------:|-------------------:|-------------|
| Synthetic | 5.51 | 3.73 | ~32% |
| Bottle clean | 100.81 | 91.93 | ~9% |
| Bottle 721 | 60.50 | 57.45 | ~5% |
| Bowl | 88.53 | 65.17 | ~26% |

Translation 只解释了 bottle clean 误差的 ~9%（~9mm），不是主要因素。Bowl 的 translation 贡献更大（~26%），因为坍缩导致 centroid 偏移更大。

---

## 4. 第三层：Rigid Alignment

这是本轮最关键的结果。

### 4.1 Rigid alignment 后的 error

| Frame | Raw (mm) | Rigid (mm) | 减少比例 | Rotation (deg) | Trans (mm) |
|-------|---------:|-----------:|--------:|---------------:|-----------:|
| **Synthetic mean** | **5.51** | **3.00** | **46%** | **3.6** | **—** |
| bottle 620 | 106.02 | 7.99 | 92% | 176.1 | — |
| bottle 653 | 101.85 | 8.57 | 92% | 175.1 | — |
| bottle 721 | 60.50 | 53.66 | 11% | 176.0 | — |
| bottle 1044 | 98.07 | 15.89 | 84% | 177.3 | — |
| bottle 1113 | 97.30 | 12.86 | 87% | 177.7 | — |
| **Bottle clean mean** | **100.81** | **11.33** | **89%** | **176.6** | **—** |
| bowl 001 | 78.16 | 48.45 | 38% | 175.6 | — |
| bowl 093 | 86.87 | 55.74 | 36% | 175.5 | — |
| bowl 138 | 93.23 | 62.84 | 33% | 179.0 | — |
| bowl 162 | 97.80 | 62.90 | 36% | 176.9 | — |
| bowl 247 | 86.57 | 59.02 | 32% | 175.3 | — |
| **Bowl mean** | **88.53** | **57.79** | **35%** | **176.5** | **—** |

### 4.2 关键观察

1. **Clean bottle：rigid alignment 将 error 从 ~101mm 降至 ~11mm（89% 减少）**。网络学到了正确结构，但 canonical frame 偏了 ~176°。

2. **Frame 721：rigid alignment 只从 60.5mm 降至 53.7mm（11%）**。预测已坍缩，刚体变换无法修复。

3. **Bowl：rigid alignment 从 ~89mm 降至 ~58mm（35%）**。改善有限，因为预测已坍缩。

4. **所有 real frames 的 rigid alignment 旋转角一致为 175.1°–179.0°**，均值 ~176.5°。这是一个系统性 pattern。

5. **所有帧（synthetic + real）的 det(R) = +1.0**，包括 unconstrained Kabsch。无 reflection。

---

## 5. 第四层：Similarity Alignment

| Frame | Rigid (mm) | Sim (mm) | Scale | Scale 含义 |
|-------|-----------:|---------:|------:|-----------|
| **Synthetic mean** | **3.00** | **2.78** | **1.010** | 几乎无 scale mismatch |
| bottle 620 | 7.99 | 7.68 | 1.037 | 预测小 3.7% |
| bottle 653 | 8.57 | 7.20 | 1.091 | 预测小 9.1% |
| bottle 721 | 53.66 | 58.72 | 18.030 | **预测坍缩 18×** |
| bottle 1044 | 15.89 | 10.37 | 1.269 | 预测小 27% |
| bottle 1113 | 12.86 | 8.96 | 1.201 | 预测小 20% |
| **Bottle clean mean** | **11.33** | **8.55** | **1.149** | 预测小 ~15% |
| bowl 001 | 48.45 | 22.45 | 7.719 | **坍缩 7.7×** |
| bowl 093 | 55.74 | 46.13 | 9.128 | **坍缩 9.1×** |
| bowl 138 | 62.84 | 61.89 | 11.828 | **坍缩 11.8×** |
| bowl 162 | 62.90 | 63.75 | 12.975 | **坍缩 13.0×** |
| bowl 247 | 59.02 | 45.18 | 9.509 | **坍缩 9.5×** |
| **Bowl mean** | **57.79** | **47.88** | **10.232** | **坍缩 ~10×** |

**Clean bottle**：similarity 比 rigid 只多降 ~3mm（11.3→8.6），scale ~1.15 — 存在 modest scale mismatch，但不是主要问题。

**Bowl**：similarity 比 rigid 降 ~10mm（57.8→47.9），scale ~10 — 预测严重坍缩，但即使 scale 纠正后仍有 ~48mm 残余误差，说明结构本身也有问题。

---

## 6. 第五层：Reflection / Axis Flip 检查

### 6.1 Unconstrained Kabsch determinant

| Group | det(R) unconstrained |
|-------|---------------------|
| Synthetic (10/10) | +1.0000 |
| Bottle (5/5) | +1.0000 |
| Bowl (5/5) | +1.0000 |

**所有 20 个样本的 unconstrained optimal transform 都是 proper rotation（det = +1）。无 reflection。**

### 6.2 Axis flip test

对每个 axis flip（diag(-1,1,1), diag(1,-1,1), diag(1,1,-1)），先做 flip 再做 rigid alignment：

| Group | Rigid baseline (mm) | Flip X (mm) | Flip Y (mm) | Flip Z (mm) |
|-------|--------------------:|------------:|------------:|------------:|
| Bottle 620 | 7.99 | 9.93 | 9.93 | 9.93 |
| Bottle 653 | 8.57 | 10.59 | 10.59 | 10.59 |
| Bowl 001 | 48.45 | 49.04 | 49.04 | 49.04 |

**所有 flip 的 aligned error 都 ≥ rigid baseline。无 axis flip 改善 prediction。**

### 6.3 180° rotation test

对 180° X/Y/Z rotation（proper rotations）：

所有 r180 的 aligned error = rigid baseline。这是数学必然：180° rotation 是 proper rotation（det=+1），optimal rigid alignment 会自动补偿。

### 6.4 结论

**不存在 systematic axis inversion 或 reflection pattern。** Prediction 与 GT 之间是 proper rotation 关系（~176°），非 mirror image。

---

## 7. 第六层：Non-rigid / Structural Error

### 7.1 Similarity-aligned residual 分析

| Group | Sim-aligned mean (mm) | resid_ax0 (mm) | resid_ax1 (mm) | resid_ax2 (mm) | resid_vs_radius corr |
|-------|----------------------:|---------------:|---------------:|---------------:|---------------------|
| Synthetic | 2.78 | ~1.1 | ~1.3 | ~0.9 | ~0.19 |
| Bottle clean | 8.55 | — | — | — | 0.16–0.42 |
| Bottle 721 | 58.72 | — | — | — | 0.92 |
| Bowl | 47.88 | — | — | — | 0.85–0.97 |

### 7.2 Covariance eigenvalue ratio（pred / GT，similarity-aligned 后）

| Group | 1st axis | 2nd axis | 3rd axis | 解释 |
|-------|---------:|---------:|---------:|------|
| Synthetic | 0.99 | 1.04 | 0.94 | 三轴等比 — 结构保持 |
| Bottle clean | 1.03 | 0.65 | 0.14 | 第2/3轴压缩 — 结构扁平化 |
| Bottle 721 | 0.35 | 0.57 | 4.08 | 完全失真 |
| Bowl | 0.23–0.74 | 0.70–2.14 | 0.28–1.42 | 高度不稳定 |

**Clean bottle**：第 1 主轴 variance 匹配 GT（ratio ~1.0），但第 2 轴压缩至 65%，第 3 轴压缩至 14%。这暗示 prediction 在垂直于主轴的平面上发生了部分坍缩。

**Bowl**：eigenvalue ratio 高度不稳定（0.22–2.14），各帧之间差异大。这不是简单的全局坍缩，而是 structure-dependent failure。

### 7.3 Visualization

生成的 4 组 diagnostic 图（`outputs/p3_1_b_canonical_analysis/viz_*.png`）：

- **Synthetic**：raw prediction 已与 GT 高度重叠，rigid/similarity alignment 几乎无改善
- **Bottle 620**：raw prediction 呈现 bottle 弧形结构但旋转了 ~180°；rigid-aligned 后 pred/GT 高度重叠
- **Bottle 721**：prediction 坍缩为一个小点簇 + 少量远距离 outlier，无法通过 alignment 修复
- **Bowl 001**：prediction 为 GT 内部的微小点簇（~1/8 大小），similarity-aligned 后形状近似但残余误差大

---

## 8. Bottle 专项分析

Bottle 是训练过的 object。

### 8.1 Clean frames（620, 653, 1044, 1113）

**Raw error ~101mm 的分解**：

| 误差来源 | 贡献 (mm) | 占总量 |
|---------|----------:|-------:|
| Centroid shift | ~9 | ~9% |
| Rotation (~176°) | ~80 | ~80% |
| Scale mismatch (~15%) | ~3 | ~3% |
| Structural residual | ~8.6 | ~9% |

**Rotation 是压倒性主要因素。** 纠正 ~176° rotation 后，残余 error 仅 ~8.6mm（bottle 直径 196mm 的 4.4%）。

### 8.2 Frame 721（outlier-contaminated）

Normalization scale = 2.4662m（正常帧 ~0.12m 的 20 倍）。这导致：
- 归一化坐标极端压缩（主体在 ±0.04 范围内）
- CoordNet global max-pool 被 outlier 主导
- Prediction 坍缩为 ~1/18 大小
- Rigid alignment 无法修复（53.7mm 残余）

### 8.3 与 viewpoint / visibility / depth scale 的相关性

| Frame | visib | norm_scale | rigid_aligned (mm) |
|-------|------:|-----------:|-------------------:|
| 620 | 0.998 | 0.121 | 7.99 |
| 653 | 0.992 | 0.126 | 8.57 |
| 721 | 0.990 | 2.466 | 53.66 |
| 1044 | 1.000 | 0.136 | 15.89 |
| 1113 | 1.000 | 0.118 | 12.86 |

Visibility 都很高（0.99–1.00），与 error 无明显相关。Norm scale 与 error 强相关：clean frames (scale ~0.12) → rigid error 8–16mm；contaminated frame (scale 2.47) → rigid error 54mm。

### 8.4 固定旋转

所有 clean bottle frames 的 rigid alignment 旋转角：175.1°, 176.1°, 177.3°, 177.7°。Range = 2.6°，高度一致。

**存在固定旋转偏移 ~176°，存在于所有 real frames（bottle + bowl 均为 ~176°）。**

---

## 9. Bowl 专项分析

Bowl 是未见 object（checkpoint 仅用 bottle 训练）。

### 9.1 与 Bottle 的比较

| 指标 | Bottle clean | Bowl | 比率 |
|------|------------:|-----:|-----:|
| Raw error (mm) | 100.81 | 88.53 | 0.88 |
| Trans-aligned (mm) | 91.93 | 65.17 | 0.71 |
| Rigid-aligned (mm) | 11.33 | 57.79 | 5.10 |
| Sim-aligned (mm) | 8.55 | 47.88 | 5.60 |
| Scale factor | 1.15 | 10.23 | 8.90 |
| pred_radius (m) | 0.043 | 0.006 | 0.14 |
| gt_radius (m) | 0.051 | 0.062 | 1.22 |

**Bowl 的 prediction 严重坍缩**：pred_radius 只有 0.006m，是 GT 的 ~1/10，是 bottle prediction 的 ~1/7。即使允许 scale 纠正（similarity alignment），残余 error 仍是 bottle 的 5.6 倍。

### 9.2 Structural failure evidence

Bowl 的 eigenvalue ratio 高度不稳定（0.22–2.14），且 resid_vs_radius correlation 很高（0.85–0.97）—— 误差随到中心的距离增大而增大，说明 prediction 不仅坍缩了，而且形状也不对。

### 9.3 Evidence for object-specific learning

Bowl（unseen object）的 prediction 坍缩且结构错误，而 bottle（trained object）在 clean 条件下保持了正确结构。这是 **evidence**（非证明）：

> 当前 CoordNet 可能学到了 object-specific geometry，而非 object-general canonical correspondence mapping。

---

## 10. Synthetic 对照

| 指标 | Synthetic | Bottle Real clean | Bowl Real |
|------|----------:|------------------:|----------:|
| Raw (mm) | 5.51 | 100.81 | 88.53 |
| Rigid-aligned (mm) | 3.00 | 11.33 | 57.79 |
| Sim-aligned (mm) | 2.78 | 8.55 | 47.88 |
| Rigid rot (deg) | 3.6 | 176.6 | 176.5 |
| Scale | 1.010 | 1.149 | 10.232 |
| det(R) | +1.0 | +1.0 | +1.0 |

**Synthetic → Real 的 error 增长不是 gradual degradation，而是质的飞跃**：
- Synthetic: rigid rot ~4°（噪声级别）
- Real: rigid rot ~176°（系统性偏移）

Real prediction 的额外误差主要表现为 **global transform mismatch**（~176° rotation），而非 structural/non-rigid mismatch（clean bottle 的 rigid-aligned residual 只有 ~11mm）。

---

## 11. 最终诊断矩阵

| Object | Domain | Raw | Trans | Rigid | Sim | Scale | Rot(°) | det(R) | Main pattern |
|--------|--------|----:|------:|------:|----:|------:|-------:|:------:|-------------|
| Bottle | Synth | 5.51 | 3.73 | 3.00 | 2.78 | 1.01 | 3.6 | +1 | Near-perfect |
| Bottle | Real clean | 100.81 | 91.93 | 11.33 | 8.55 | 1.15 | 176.6 | +1 | ~176° rotation |
| Bottle | Real 721 | 60.50 | 57.45 | 53.66 | 58.72 | 18.03 | 176.0 | +1 | Collapsed |
| Bowl | Real | 88.53 | 65.17 | 57.79 | 47.88 | 10.23 | 176.5 | +1 | Collapsed |

---

## 12. Hypothesis 分类

### Clean bottle (4/5 frames)：Hypothesis A 为主

`pred ≈ R · gt + t`，其中 R 是 ~176° 的 rotation。

网络学到了正确的物体几何结构（rigid-aligned residual ~11mm ≈ synthetic 的 3.8 倍），但 canonical frame 存在系统性 ~176° 旋转偏移。另存在 ~15% 的 scale mismatch 和轻微的 secondary axis 压缩。

### Frame 721：Hypothesis D

Prediction 坍缩（18× 过小），由 depth outlier 污染 normalization scale 导致。刚性/相似变换均无法修复。

### Bowl (5/5 frames)：Hypothesis C + D

Prediction 坍缩（~10× 过小）+ 结构错误。即使最佳 similarity alignment 后仍有 ~48mm 残余。网络未能恢复 unseen object 的 canonical correspondence。

---

## 13. Confirmed Facts / Strong Evidence / Hypotheses

### Confirmed facts

1. Synthetic control: raw error 5.51mm, rigid-aligned 3.00mm, rotation ~4°。网络在 synthetic 数据上工作正常。
2. 所有 20 个样本（synthetic + real）的 unconstrained Kabsch det(R) = +1。无 reflection。
3. 所有 10 个 real frames 的 rigid alignment 旋转角为 175.1°–179.0°，均值 ~176.5°。
4. Clean bottle rigid-aligned residual = 11.33mm；synthetic = 3.00mm。
5. Bowl pred_radius ≈ 0.006m，GT radius ≈ 0.06m — prediction 坍缩至 ~1/10。
6. Frame 721 pred_radius = 0.0035m，GT = 0.0553m — 坍缩至 ~1/16。
7. Bottle clean similarity scale ≈ 1.15；bowl ≈ 10.23；frame 721 ≈ 18.03。

### Strong evidence

1. **Real-domain canonical prediction failure 是当前最主要的 failure layer。** 对于 clean bottle，~90% 的 raw error 来自一个系统性 ~176° 旋转偏移。
2. **~176° 旋转是 systematic 的**，而非 per-frame random。所有 10 个 real frames（两种不同 object）均呈现相同范围的旋转角（175–179°）。
3. **Bowl 的 failure 比 bottle 更严重且更根本** — 不仅有 frame mismatch，还有结构坍缩。这支持 object-specific learning 的 hypothesis。
4. **Outlier-contaminated depth (frame 721) 导致 prediction 坍缩**，这与 normalization scale 污染一致（P3.1-A 已确认 scale 修复不改善 prediction）。

### Hypotheses

1. **~176° 旋转偏移可能源于 synthetic 训练数据与 real BOP 数据之间的 canonical frame 定义差异，或网络在 real domain 上学到了不同的 canonical frame mapping。** 需要检查 synthetic 数据生成 pipeline 的 canonical frame 约定。
2. **Clean bottle 的 ~11mm rigid-aligned residual（vs synthetic 3mm）可能来自 real depth noise、RGB 差异、或网络对 real feature distribution 的不完全泛化。**
3. **Bowl 坍缩可能是因为 global max-pool descriptor 在未见形状上无法提供有效的 shape context，导致 per-point MLP 退化到输出 conditional mean（接近原点的小值）。**

---

## 14. 不做的事

- 未将 rigid-aligned / similarity-aligned prediction 送入 RANSAC / ICP
- 未修改 Gate 3 结果
- 未训练 / retrain / 修改 checkpoint
- 未使用 P3.1-A robust normalization 作为正式变量
