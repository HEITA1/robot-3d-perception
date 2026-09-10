# P3.1-D: Canonical Frame Convention Audit

> 日期：2026-09-10
> 问题：synthetic renderer / training label 定义的 canonical coordinates，与 BOP YCB-V model coordinates
> 是否完全同一 canonical frame？（Case A = 存在固定 convention mismatch；Case B = 完全同一）
> 性质：只读审计 + 最小数学 sanity。不修改模型/checkpoint/loss/管线/Gate 3。
> 执行：`scripts/p3_1_d_canonical_frame_audit.py`；原始数据 `outputs/p3_1_d_canonical_frame_audit/p3_1_d_results.json`

## 结论

**Case B：synthetic canonical frame 与 BOP model frame 完全同一（对两个目标物体均成立）。**

直接后果：CoordNet 在 real domain 输出的 ~176.5° 系统性旋转**不是**数据 frame convention bug——
它产生于网络在真实输入分布上的 learned mapping 本身。训练数据与标签在这一假设空间内是清白的。

---

## Check 1 — Model source（两个读取器，同一个文件）

| 项 | obj 5 (mustard_bottle) | obj 13 (bowl) |
| --- | --- | --- |
| 文件 | `data/ycbv/models/obj_000005.ply` | `data/ycbv/models/obj_000013.ply` |
| sha256 | `c1d093e33fe9b447…` | `f4f23ae40cae3a205…`（前 16 位） |
| 读取器 A（渲染器/标签） | 手写 ASCII 解析（`TexturedModel.from_ply`） | 同左 |
| 读取器 B（评测） | Open3D `read_triangle_mesh` | 同左 |
| vertex 数 | 10,983 / 10,983 | 8,323 / 8,323 |
| **max \|manual − o3d\|** | **0.000e+00 m（逐位一致）** | **0.000e+00 m（逐位一致）** |
| bbox extent (m) | [0.097, 0.067, 0.191] | [0.161, 0.161, 0.055] |
| diameter (m) | 0.196463 | 0.161922 |
| PLY 顶点属性顺序 | x,y,z,nx,ny,nz,texture_u,texture_v（两文件相同，解析器硬编码列序与之一致） | 同左 |
| mm→m | 两侧同一转换（×1e-3） | 同左 |

**结论**：渲染器与评测从**同一个文件**读取，两个读取器产出**逐位相同**的顶点坐标。
不存在"渲染器读了另一个 mesh / 不同单位 / 不同解析"的空间。

## Check 2 — Canonical coordinate source（实际公式，已对 live code 断言）

```text
labels:  coords_i = eye + t_hit_i * dir_world_i      # raycast hit point, model/world frame
         （mesh 顶点 mm→m 后入 RaycastingScene；世界系 == 模型系，无其他变换）
inputs:  xyz_cam  = T_cam_model @ coords             # T_cam_model 由 _camera_pose 构造（world→cam）
BOP GT:  p_cam    = cam_R_m2c @ p_model + cam_t_m2c  # 行主序 9 → 3×3，t mm→m
评测:    model_points = Open3D(obj_*.ply) * 1e-3      # 与 Check 1 同文件
```

（脚本对 `synth_data.generate_samples` / `render_templates.render_view` / `TexturedModel.from_ply`
的源码行做了 assert，报告引用的是当前代码而非记忆。）

## Check 3 — Transform chain 方向

- synthetic：`T_cam_model`（world→cam），`xyz = T @ coords`，训练 loss 在 camera frame 计算——与
  Coordinate/Transform Audit（EXP-008 附带，合成闭环 4.05°/4.1mm/97.2% inliers）一致。
- real：`cam_R_m2c` 行主序 reshape(3,3)、`cam_t_m2c` mm→m，`p_cam = R @ p_model + t`——与 Phase 1
  GT 叠加像素级验证一致。
- 两侧均为 OpenCV 相机约定、model→camera 方向；`compute_all` 全程使用 `T_cam_model` 约定。
- 本审计**未发现**任何转置/行列/轴序/单位错位。

## Check 4 — Direct correspondence（决定性检查）

对 12 个真实使用的训练样本 / 物体（每个 2048 个 label 点）：

| 检查 | obj 5 | obj 13 |
| --- | --- | --- |
| NN(label → BOP vertex)，**恒等 frame** | mean **1.01mm** / max 3.11mm | mean **1.07mm** / max 2.33mm |
| NN(label → BOP vertex)，施加 P3.1-C 旋转 | mean **10.8mm（膨胀 10.7×）** | mean **16.7mm（膨胀 15.5×）** |
| Kabsch(label→BOP，NN 配对) 旋转 | **0.010–0.071°** | **0.019–0.096°** |
| Kabsch 平移范数 | ≤ 3.5e-05 m | ≤ 2.6e-04 m |
| det(R) | 1.000（无反射） | 1.000 |
| scale | 0.99995–1.00087 | 0.99715–1.00237 |
| **Kabsch R 与 P3.1-C 旋转的距离** | **176.5°** | **176.4–176.6°** |

判读：
- 恒等 frame 下 label 点到 BOP 顶点的 NN 距离 ~1mm——这是 2048 采样点 vs ~10k 顶点的**表面采样密度下限**，
  不是偏差；
- 把 label 点按 P3.1-C 的旋转旋转后，NN 距离膨胀 10.7×/15.5×（到物体半径量级）——**如果**两 frame 之间存在
  该旋转，这个旋转应当把距离缩小到亚毫米；实测相反；
- Kabsch 拟合出的 label→BOP 变换就是恒等（旋转 <0.1°、平移 <0.4mm、scale≈1、det=+1），
  且该拟合与 P3.1-C 旋转相距恰为 176.5°——即"能修复 Gate 3 的那个旋转"在数据层面**不存在**。

## Check 5 — 判定

**Case A（frame convention mismatch）：被数据否定。**
**Case B（frames identical）：成立。**

## Check 6 — 合规声明

P3.1-C 的 −176.5° 旋转在本审计中**仅用作判别器**（检验"施加它是否缩小距离"）；
未用它反推任何结论，未用它修正任何数据。GT pose 完全未使用（BOP model frame 由 mesh 文件定义）。

## 审计过程的诚实记录

本审计脚本自身出现过 3 处 verdict 实现 bug（NN 阈值以绝对值 0.1mm 判定采样密度下限、判别器
100× 膨胀阈值不可达、verdict 计算先于判别器计算），均已修正并以相对判据重写
（Kabsch 拟合 + 膨胀判别器为准）。**所有原始数值全程正确，仅 pass/fail 打包逻辑曾出错**；
最终判据：Kabsch rot<1°、|t|<1mm、|scale−1|<1%、det(R)>0.999、且 P3.1-C 旋转使 NN 膨胀 ≥5×。

---

## Confirmed facts

1. 渲染器与评测读取**同一个 PLY 文件**，两个读取器输出逐位一致（max diff = 0.0）。
2. 训练标签（coords）与 BOP model frame 的 Kabsch 变换 = 恒等（rot ≤0.096°，|t| ≤0.26mm，scale≈1，det=+1）。
3. 施加 P3.1-C 旋转使 label→BOP 距离**膨胀** 10.7×/15.5×（若存在 mismatch 则应缩小）。
4. P3.1-C 修正旋转与 label→BOP 实际拟合旋转相距 176.5°（即数据中不存在该旋转）。

## Strong evidence

5. **Case A（frame convention mismatch）被排除**：~176.5° 旋转不是数据层面的约定差异——
   两个 frame 在数学上同一。
6. 结合 P3.1-C（修正该旋转后 0/10→10/10，bottle ADD ~1mm）：**CoordNet 在 real domain 学到了一个
   系统性翻转 ~176.5° 的 canonical mapping，且除此之外其对应质量足以支撑 ~1mm 级位姿。**
   失败定位收窄到"网络在真实输入分布上的 frame 歧义选择"，而非数据、管线或约定。

## Hypotheses（未证明）

- H-a：真实深度覆盖模式（单视角 + 桌面遮挡 + 边缘噪声）与合成渲染（完整可见半球、无桌面）差异，
  使 CoordNet 的 max-pool 全局描述子落入"翻转"的对应模式。
- H-b：真实 RGB 光照/材质使网络依赖的外观线索（如标签位置/明暗）在两域间反转
  （mustard bottle 标签正面/背面恰差 ~180°）。
- H-c：训练视角采样（Fibonacci 全 SO(3) + up-vector 约定）与真实相机 roll 分布的差异，
  使网络在 real roll 区间外欠约束。

## Remaining uncertainty

- 176.5° 偏移的确切产生机制（H-a/H-b/H-c 或其组合）未被隔离——需要受控输入消融（纯几何 vs 含外观）
  才能定位，属后续实验。
- 本审计覆盖 obj 5/13 的两个 PLY 与两份训练数据；其余 19 个物体未检查（不在当前 scope）。
- float16 标签舍入（~0.01–0.04mm）为已知且无害，但不为 0；Kabsch 的 0.01–0.10° 残余主要是
  NN 配对的表面采样噪声，非系统性旋转。
