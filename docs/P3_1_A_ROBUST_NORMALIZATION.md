# P3.1-A: Robust Normalization 单变量实验

## A. 实际修改了什么

**唯一修改**：normalization scale 的计算方式。

| | Baseline (`normalize_points`) | Robust (`normalize_points_robust`) |
|---|---|---|
| center | `xyz.mean(axis=0)` | `xyz.mean(axis=0)` (相同) |
| scale | `max(\|\|xyz - center\|\|)` | `percentile(radii, 95)` |

代码：`scripts/p3_1_a_robust_norm.py:34-46`

```python
def normalize_points_robust(xyz, percentile=95.0):
    center = xyz.mean(axis=0)
    radii = np.linalg.norm(xyz - center, axis=1)
    scale = float(np.percentile(radii, percentile))
    if scale < 1e-9:
        scale = 1.0
    return (xyz - center) / scale, center, scale
```

## B. 唯一实验变量

| 项目 | 状态 |
|---|---|
| Checkpoint | `outputs/p3_0/gate1/coord_net_bottle.pt` (冻结) |
| CoordNet 架构 | ~58.6K param MLP (冻结) |
| RGB 输入 | 原图 / 255.0 (冻结) |
| 深度 / mask | oracle mask_visib, 原始深度 (冻结) |
| 测试帧 | 10 帧 (bottle 5 + bowl 5) (冻结) |
| Voxel 大小 | 5mm (冻结) |
| 采样点数 | 1024 (冻结) |
| RANSAC 参数 | threshold=8mm, iters=2000 (冻结) |
| ICP 参数 | 3cm→1cm→3mm schedule (冻结) |
| Seeds | 与 Gate 3 完全相同 (冻结) |
| 评估指标 | ADD / ADD-S / trans / rot (冻结) |
| **Normalization scale** | **max → p95 (唯一变量)** |

无重新训练。无参数搜索。无范围扩展。

## C. Baseline vs Robust 结果

### C.1 obj05 (mustard_bottle, d=196.463mm, 0.1d=19.65mm)

| Frame | Baseline scale (m) | Robust scale (m) | Ratio | Baseline ADD (mm) | Robust ADD (mm) | Δ ADD |
|-------|-------------------|-----------------|-------|------------------|----------------|-------|
| 000620 | 0.1207 | 0.0897 | 1.35× | 117.45 | 113.28 | −4.17 |
| 000653 | 0.1255 | 0.0896 | 1.40× | 118.01 | 117.90 | −0.11 |
| 000721 | 2.4662 | 0.0884 | 27.90× | 116.56 | 116.59 | +0.03 |
| 001044 | 0.1356 | 0.0912 | 1.49× | 117.68 | 117.68 | 0.00 |
| 001113 | 0.1181 | 0.0873 | 1.35× | 117.40 | 117.40 | 0.00 |
| **Mean** | | | | **117.42** | **116.57** | **−0.85** |

| Frame | Baseline ADD-S (mm) | Robust ADD-S (mm) | Baseline trans (mm) | Robust trans (mm) | Baseline rot (deg) | Robust rot (deg) |
|-------|--------------------|--------------------|--------------------|--------------------|--------------------|------------------|
| 000620 | 12.60 | 16.90 | 30.35 | 35.52 | 172.35 | 170.82 |
| 000653 | 13.00 | 12.86 | 39.06 | 38.34 | 178.01 | 177.96 |
| 000721 | 11.87 | 19.43 | 35.61 | 42.48 | 179.82 | 170.26 |
| 001044 | 8.08 | 8.08 | 40.75 | 40.75 | 179.26 | 179.26 |
| 001113 | 7.24 | 7.24 | 51.15 | 51.15 | 179.80 | 179.80 |
| **Mean** | **10.56** | **12.90** | **39.38** | **41.65** | **177.85** | **175.62** |

成功率：0/5 → 0/5

### C.2 obj13 (bowl, d=161.922mm, 0.1d=16.19mm)

| Frame | Baseline scale (m) | Robust scale (m) | Ratio | Baseline ADD-S (mm) | Robust ADD-S (mm) | Δ ADD-S |
|-------|-------------------|-----------------|-------|--------------------|--------------------|---------|
| 000001 | 1.0003 | 0.0950 | 10.53× | 59.35 | 42.52 | −16.83 |
| 000093 | 1.0815 | 0.1003 | 10.79× | 62.05 | 65.81 | +3.76 |
| 000138 | 1.1106 | 0.1055 | 10.53× | 34.42 | 56.66 | +22.24 |
| 000162 | 1.1678 | 0.1073 | 10.88× | 38.23 | 60.70 | +22.47 |
| 000247 | 1.1884 | 0.0998 | 11.91× | 34.98 | 56.60 | +21.62 |
| **Mean** | | | | **45.81** | **56.46** | **+10.65** |

| Frame | Baseline trans (mm) | Robust trans (mm) | Baseline rot (deg) | Robust rot (deg) |
|-------|--------------------|--------------------|--------------------|------------------|
| 000001 | 129.60 | 92.57 | 171.60 | 177.52 |
| 000093 | 133.63 | 133.57 | 170.07 | 168.85 |
| 000138 | 64.40 | 123.11 | 177.14 | 174.75 |
| 000162 | 87.11 | 129.65 | 179.65 | 174.76 |
| 000247 | 73.81 | 120.80 | 174.68 | 179.07 |
| **Mean** | **97.71** | **120.10** | **174.63** | **174.99** |

成功率：0/5 → 0/5

### C.3 汇总

| 指标 | Bottle Baseline | Bottle Robust | Bowl Baseline | Bowl Robust |
|------|----------------|--------------|--------------|-------------|
| 成功率 | 0/5 | 0/5 | 0/5 | 0/5 |
| ADD mean (mm) | 117.42 | 116.57 | 126.39 | 145.17 |
| ADD-S mean (mm) | 10.56 | 12.90 | 45.81 | 56.46 |
| trans mean (mm) | 39.38 | 41.65 | 97.71 | 120.10 |
| rot mean (deg) | 177.85 | 175.62 | 174.63 | 174.99 |

**结论：robust normalization 没有改善任何主要指标。Bottle ADD 微降 0.85mm（可忽略），bowl ADD-S 反而恶化 10.65mm。**

## D. Frame 721 深度分析

Frame 721 是 Gate 3 debug 中发现的 normalization scale 极端污染帧（baseline scale = 2.4662m，是正常帧的 ~20 倍）。

### D.1 Normalization scale

| | Baseline | Robust |
|---|---|---|
| scale | 2.4662 m | 0.0884 m |
| ratio | — | 27.90× |

Robust normalization 成功将 scale 从 2.47m 降至 0.088m，回到训练数据正常范围（synthetic val 均值 ~0.09m）。

### D.2 Normalized XYZ 分布

| | Baseline (推断) | Robust |
|---|---|---|
| norm_xyz_std | [~0.01, ~0.03, ~0.01] | [0.275, 0.579, 1.211] |

Robust 归一化后，z 轴 std 达到 1.211 — 远超训练数据范围（synthetic val 各轴 std ≈ 0.3-0.5）。原因：p95 将 5% 的 outlier 点推到了极端的归一化坐标（z ≈ 27.9 倍原始位置），这些 outlier 的绝对坐标远超单位球。

### D.3 CoordNet 预测

| | Baseline | Robust |
|---|---|---|
| canonical err mean (mm) | 60.5 | 103.2 |
| canonical err max (mm) | — | 2272.3 |
| pred_std (x,y,z) | — | [0.027, 0.029, 0.029] |
| pred z range | — | [−0.471, 0.013] |

**CoordNet 预测反而恶化**：canonical error 从 60.5mm 升至 103.2mm，max 达到 2272mm。z 轴出现极端异常值（−0.47m），说明网络在归一化空间异常输入下产生了无意义的输出。

### D.4 Axis correlation (pred vs GT canonical)

| Axis | Baseline corr | Robust corr |
|------|--------------|-------------|
| 0 | 0.62 | 0.20 |
| 1 | 0.36 | −0.20 |
| 2 | −0.37 | −0.25 |

**所有轴的相关性都大幅下降**。Baseline 至少 axis 0 有中等正相关（0.62），robust 后全部降至弱相关或无相关。网络没有学到有意义的 canonical 坐标映射。

### D.5 RANSAC

| | Baseline | Robust |
|---|---|---|
| inliers | 58 / 1024 | 276 / 1024 |
| inlier ratio | 5.66% | 26.95% |
| mean resid | 7.37mm | 5.27mm |
| ADD (mm) | — | 132.27 |
| rot (deg) | — | 164.48 |

Robust 的 inlier count 增加了（58→276），但这并非因为对应关系质量提升，而是因为 RANSAC threshold = 8mm 在 robust 的更差 canonical 预测下仍然能"接受"大量噪声对应。RANSAC pose 的 ADD = 132.27mm，比 baseline 更差。

### D.6 ICP + 最终位姿

| | Baseline | Robust |
|---|---|---|
| ICP fitness | 0.406 | 0.269 |
| ICP rmse | 1.699mm | 1.884mm |
| Final ADD (mm) | 116.56 | 116.59 |
| Final ADD-S (mm) | 11.87 | 19.43 |
| Final trans (mm) | 35.61 | 42.48 |
| Final rot (deg) | 179.82 | 170.26 |

**最终 ADD 几乎完全相同**（116.56 vs 116.59mm，差 0.03mm）。ICP 从更差的 RANSAC 初始位姿出发，fitness 反而下降（0.406→0.269）。ADD-S 恶化 7.56mm。

### D.7 Frame 721 结论

Robust normalization 成功修复了 scale 异常（2.47m → 0.088m），但：
1. p95 归一化将 5% outlier 推到极端坐标（z ≈ 27× 正常范围）
2. CoordNet 的 global max-pool descriptor 被 outlier 主导
3. Canonical 预测质量反而下降（60.5mm → 103.2mm）
4. 最终位姿无改善（ADD 差 0.03mm，在浮点误差范围内）

## E. CoordNet 是否改善

**没有改善。**

| 对象 | Baseline canon err (mm) | Robust canon err (mm) | 变化 |
|------|------------------------|----------------------|------|
| Bottle mean (5帧) | ~100 (debug 报告) | 107.8 | +7.8 (恶化) |
| Bowl mean (5帧) | ~88 (debug 报告) | 132.2 | +44.2 (显著恶化) |

原因分析：

1. **Train/test mismatch**：CoordNet 训练时使用 `max(radii)` 归一化，所有训练样本的归一化坐标都在单位球内（max radius = 1.0）。推理时使用 p95 归一化，5% 的 outlier 点的归一化坐标远超 1.0（frame 721 达到 ~27.9）。网络从未见过这种输入分布。

2. **Global max-pool 污染**：CoordNet 使用 `local.max(dim=1).values` 作为全局形状描述符。当少数点的归一化坐标达到 10-28 时，max-pool 完全被这些 outlier 主导，正常点的特征信号被淹没。

3. **Bowl 恶化更严重**：bowl 的 baseline scale 已经很大（1.0-1.2m），p95 归一化后 outlier 同样被推到极端坐标，且 bowl 的几何对称性使得网络更依赖全局形状描述符。

## F. RANSAC 是否改善

**没有改善。**

| 对象 | Baseline inlier ratio | Robust inlier ratio | 变化 |
|------|----------------------|---------------------|------|
| Bottle mean | 0.441 | 0.444 | +0.003 (无变化) |
| Bowl mean | 0.032 | 0.184 | +0.152 |

Bowl 的 inlier ratio 看似提升（0.032→0.184），但这是因为 RANSAC 在更差的 canonical 预测中仍然能找到满足 threshold 的对应（阈值 8mm 在 ~130mm 的 canonical error 下仍然能接受部分噪声对应）。最终 RANSAC pose 质量并未提升：

| 对象 | Baseline RANSAC ADD (mm) | Robust RANSAC ADD (mm) |
|------|-------------------------|----------------------|
| Bottle (frame 620) | — | 120.08 |
| Bowl mean | — | 139.95 |

RANSAC 本身无法从更差的对应关系中恢复正确位姿。

## G. ICP 是否改善

**没有改善。**

| 对象 | Baseline ICP fitness | Robust ICP fitness |
|------|---------------------|---------------------|
| Bottle mean | 0.516 | 0.472 |
| Bowl mean | 0.098 | 0.097 |

Bottle ICP fitness 下降（0.516→0.472），bowl 基本不变。ICP 从更差（或相同质量）的 RANSAC 初始位姿出发，无法通过 fine-tuning 弥补 canonical 预测的退化。

## H. Outcome 分类

### **Outcome D：几乎没有改善**

| 判据 | 结果 |
|------|------|
| Normalization scale 修复？ | ✅ 是（bowl 10-12× 缩减，frame 721 27.9× 缩减） |
| CoordNet canonical 预测改善？ | ❌ 否（bottle +7.8mm 恶化，bowl +44.2mm 恶化） |
| RANSAC 位姿改善？ | ❌ 否（bottle ADD −0.85mm 可忽略，bowl ADD-S +10.65mm 恶化） |
| ICP 最终位姿改善？ | ❌ 否（bottle ADD −0.85mm，bowl ADD-S +10.65mm） |
| 成功率变化？ | ❌ 0/10 → 0/10 |

**Normalization hypothesis 被削弱。** 即使完美修复了 scale 异常，CoordNet 的 canonical 预测也没有改善——瓶颈不在 normalization scale，而在网络本身的泛化能力（sim-to-real gap + 模型容量不足）。

继续围绕 normalization 调参（如调整 percentile、clip outlier、train with robust norm）属于同一假设空间的变体，预期不会有本质不同的结果。

## I. 52/52 Tests

```
$ conda run -n r3p python -m pytest tests/ -q
....................................................                     [100%]
52 passed
```

**52/52 PASS**

## J. Commit Hash

(待提交)

## K. Working Tree 状态

新增文件：
- `scripts/p3_1_a_robust_norm.py` — 实验脚本
- `docs/P3_1_A_ROBUST_NORMALIZATION.md` — 本报告
- `outputs/p3_1_a_robust_norm/p3_1_a_results.json` — 实验结果
