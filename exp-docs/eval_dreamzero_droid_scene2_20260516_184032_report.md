# DreamZero DROID Scene 2 Default 实验日志分析报告（第二次复现）

## 1. 实验概览

- **日志文件**：`logs/droid_roboarena_efficiency/eval_dreamzero_droid_scene2_20260516_184032.log`
- **运行目录**：`runs/2026-05-16/18-40-55`
- **任务**：DROID Sim Eval — Scene 2，指令为 `put the can in the mug`
- **任务套件 / split**：`default` / `default`
- **Variation seed**：0 | **Level**：1.0（默认值，扰动全关闭，实际无扰动生效）
- **扰动配置**：object_pose=off, container_pose=off, distractor=off, lighting_camera=off（**全部关闭**）
- **目标物体**：source 为 `_10_potted_meat_can`，target 为 `_25_mug`
- **策略**：DreamZero（通过 WebSocket 连接 localhost:6000 提供推理服务）
- **推理模式**：open-loop horizon = 8，每 8 步调用一次模型推理
- **计划集数**：10 episodes；每集上限 450 steps，控制频率 15 Hz，即每集最长 30s
- **成功判定**：水平距离 `< 0.06m`，高度差在 `(-0.02m, 0.15m)`，并需连续保持 30 steps（约 2s）
- **Early-stop**：开启，成功保持后提前结束

本次运行已完整结束，10 个 episode 全部完成，`results.json` 已正常生成。**注意：日志文件在 Episode 10 (ep9) 的 step 202/450 处截断，但 `results.json` 已正确记录全部 10 个 episode 的完整结果，确认 ep9 成功完成。**

## 2. 运行完成度与指标

| 项目 | 结果 |
| --- | --- |
| 计划 episodes | 10 |
| 完整完成 episodes | 10 |
| 保存视频 | `episode_0.mp4` ~ `episode_9.mp4` |
| `results.json` | ✅ 已生成 |
| 成功率 | **8/10 = 80.0%** |
| 平均进度 | **80.0%** |
| stage 分布 | place (success): 8, idle: 2 |
| 是否通过 strict_success_threshold (80%) | ✅ 是（刚好达标） |

逐 episode 摘要：

| Episode | 结果 | 总 steps | 成功 step | 成功耗时 | `h_dist` | `v_diff` | 解释 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 (ep0) | ✅ SUCCESS | 348 | 318 | 21.20s | 0.0289 | 0.1084 | **最慢成功之一**，可能经历修正过程 |
| 2 (ep1) | ✅ SUCCESS | 237 | 207 | 13.80s | 0.0185 | 0.1168 | 中速成功，精度较高 |
| 3 (ep2) | ✅ SUCCESS | 363 | 333 | 22.20s | 0.0269 | 0.1159 | **最慢成功**，运输/对准阶段耗时较长 |
| 4 (ep3) | ✅ SUCCESS | 357 | 327 | 21.80s | 0.0119 | 0.1098 | **放置精度最高** (h_dist=11.9mm)，但耗时较长 |
| 5 (ep4) | ✅ SUCCESS | 353 | 323 | 21.53s | 0.0241 | 0.1131 | 稳定成功，耗时偏长 |
| 6 (ep5) | ❌ FAILURE | 450 | - | - | 0.1410 | 0.0030 | idle 阶段直至超时，策略未启动抓取 |
| 7 (ep6) | ❌ FAILURE | 450 | - | - | 0.1410 | 0.0030 | 与 ep5 完全相同的失败模式，idle 超时 |
| 8 (ep7) | ✅ SUCCESS | 222 | 192 | 12.80s | 0.0250 | 0.1145 | 快速成功 |
| 9 (ep8) | ✅ SUCCESS | 214 | 184 | 12.27s | 0.0246 | 0.1329 | 快速成功，**v_diff 最高** (罐头悬于杯口上方较高) |
| 10 (ep9) | ✅ SUCCESS | 203 | 173 | 11.53s | 0.0392 | 0.0915 | **最快成功**，但 h_dist 接近阈值 (39.2mm vs 60mm) |

> 成功的 8 个 episode 均因 `early_stop_on_success=True` 在成功连续保持 30 steps（约 2s）后提前结束。成功步数范围为 173–333，对应成功耗时 11.53s–22.20s。2 次失败的 episode (ep5, ep6) 均达到 450 steps 上限后超时退出，全程处于 idle 阶段，`source_lifted=False`。

## 3. 关键统计

| 指标 | 值 |
| --- | --- |
| 成功率 | **80.0% (8/10)** |
| 平均进度 | 80.0% |
| 平均成功 step | 257.1 (17.14s) |
| 最快成功 | Episode 10 (ep9): step 173 (11.53s) |
| 最慢成功 | Episode 3 (ep2): step 333 (22.20s) |
| 平均总 steps | 319.7 |
| 成功 ep 平均 `h_dist` | 0.0249m |
| 成功 ep 平均 `v_diff` | 0.1129m |
| `h_dist` 范围 | 0.0119m – 0.0392m (阈值 0.06m) |
| `v_diff` 范围 | 0.0915m – 0.1329m (阈值 -0.02m ~ 0.15m) |
| 所有成功 ep `source_lifted` | 均为 True |
| 失败 ep `source_lifted` | 均为 False |

## 4. 失败模式分析

### 4.1 失败 Episode 特征

两个失败 episode (ep5, ep6) 呈现完全一致的失败模式：

| 特征 | EP6 (ep5) | EP7 (ep6) |
| --- | --- | --- |
| stage | 0 (idle) | 0 (idle) |
| 总 steps | 450（超时） | 450（超时） |
| h_dist | 0.141m | 0.141m |
| v_diff | 0.003m | 0.003m |
| source_lifted | False | False |
| source_pos | (0.454, 0.062, 0.099) | (0.454, 0.062, 0.099) |
| target_pos | (0.439, -0.078, 0.096) | (0.439, -0.078, 0.096) |

> **关键发现**：ep5 和 ep6 的最终 source_pos 和 target_pos **完全一致**，且与前次实验 (0516_160732) 中失败的 ep1/ep4/ep9 也相同。这进一步印证了 **特定初始构型导致策略进入"死锁"状态** 的假设。在 default 配置（seed=0、扰动全关）下，环境的随机性有限，某些 episode 会重复生成相同的"困难"初始排布，导致策略无法启动抓取动作。

### 4.2 与前次 Default 实验失败对比

| | 前次 Default (0516_160732) | 本次 Default (0516_184032) |
| --- | --- | --- |
| idle 失败数 | 3 (ep1, ep4, ep9) | 2 (ep5, ep6) |
| 失败 source_pos | (0.454, 0.062, 0.099) | (0.454, 0.062, 0.099) |
| 失败模式 | idle | idle |

> 两次实验的失败 episode 的最终物体位置完全一致，说明这些失败由环境中特定的初始构型决定。本次实验减少了一次 idle 失败，可能是因为某些随机因素（如推理采样噪声）在本次执行中恰好使策略突破了"死锁"状态。

## 5. 行为模式分析

### 5.1 成功 Episode 的速度分布

8 次成功 episode 的成功耗时分布：

- **快速 (11–13s)**（3 个）：ep9 (11.53s)、ep8 (12.27s)、ep7 (12.80s) — 策略快速执行完整的抓取-运输-放置流程，无明显修正步骤
- **中速 (13–14s)**（1 个）：ep1 (13.80s) — 中等速度完成
- **慢速 (21–23s)**（4 个）：ep0 (21.20s)、ep4 (21.53s)、ep3 (21.80s)、ep2 (22.20s) — 经历额外的探索或运输修正步骤

成功耗时呈明显的**双峰分布**：一组集中在 ~12s，另一组集中在 ~22s，中间几乎没有过渡。这可能表明策略存在两种不同的执行路径——快速直接路径和需要修正的缓慢路径。

### 5.2 放置精度与深度分析

所有成功 episode 的最终水平距离均远低于 0.06m 阈值：
- **最佳**：ep3 的 `h_dist=0.0119m`（距杯口中心仅 11.9mm）
- **最差**：ep9 的 `h_dist=0.0392m`（仍有 20.8mm 的阈值余量）
- **平均**：0.0249m（低于 0.06m 阈值约 58%）

垂直高度差分布：
- **最低（最接近杯口高度）**：ep9 的 `v_diff=0.0915m`
- **最高（罐头在杯口上方最高位置）**：ep8 的 `v_diff=0.1329m`
- **平均**：0.1129m

> **h_dist vs 速度权衡**：最快成功的 ep9 (11.53s) 的 h_dist=0.0392m 是所有成功 episode 中最大的，而最慢成功之一的 ep3 (21.80s) 反而有最高精度 (h_dist=0.0119m)。这表明更长的执行时间可能用于更精细的对准修正，带来了更高的放置精度。

### 5.3 推理效率

从日志中的 tqdm 进度条可以观察到 DreamZero 的推理模式：

- 每 8 步（open-loop horizon）触发一次远程推理调用
- 推理调用耗时约 **5–6 秒**（从进度条的时间跳跃可以看出）
- 中间的 7 步执行非常快（< 0.5s/step）
- 单 episode wall-clock 时间约 3–7 分钟
- GPU：NVIDIA RTX PRO 6000 Blackwell (98GB)，CPU：Intel Xeon Platinum 8470Q

## 6. 与前次实验对比

### 6.1 与前次 DreamZero Default 实验对比

| 指标 | DreamZero Default #1 (0516 160732) | DreamZero Default #2 (0516 本次) |
| --- | --- | --- |
| Task suite / split | default / default | default / default |
| 扰动 | 全部关闭 | 全部关闭 |
| horizontal_thresh | 0.06m | 0.06m |
| 计划 episodes | 10 | 10 |
| 成功率 | 7/10 = 70.0% | **8/10 = 80.0%** |
| 平均进度 | 70.0% | **80.0%** |
| 失败模式 | idle: 3 | idle: 2 |
| 平均成功耗时 | 14.44s | 17.14s |
| 最快成功 | 10.60s | 11.53s |
| 最慢成功 | 24.40s | 22.20s |
| 平均成功 h_dist | 0.0206m | 0.0249m |
| 平均成功 v_diff | 0.1046m | 0.1129m |

> **关键发现**：
> 1. 本次实验成功率提升至 80%（vs 70%），idle 失败从 3 次减少到 2 次。
> 2. 平均成功耗时从 14.44s 增加到 17.14s，主要因为本次有更多"慢速成功"episode（4个在 21–22s 范围），这些 episode 在前次实验中可能以不同的方式执行（更快但精度不同）。
> 3. 两次实验的失败 episode 的物体终态位置完全一致，证实了 idle 失败的构型特异性。
> 4. 本次成功率刚好达到 strict_success_threshold (80%)，而前次未通过。

### 6.2 与 DreamZero PnP-Hard 实验对比

| 指标 | DreamZero Default #2 (本次) | DreamZero PnP-Hard (0516 171000) |
| --- | --- | --- |
| Task suite / split | default / default | **pnp-hard / held-out-scene** |
| 扰动 | 全部关闭 | **全部开启** |
| horizontal_thresh | 0.06m | **0.042m（更严格）** |
| 计划 episodes | 10 | 10 |
| 成功率 | 8/10 = 80.0% | **10/10 = 100.0%** |
| 平均进度 | 80.0% | **100.0%** |
| 失败模式 | idle: 2 | **无失败** |
| 平均成功耗时 | 17.14s | 14.92s |
| 平均成功 h_dist | 0.0249m | 0.0266m |
| 平均成功 v_diff | 0.1129m | 0.1010m |

> **反直觉的结果仍然成立**：pnp-hard 配置（全部扰动开启、更严格阈值）下的 100% 成功率继续优于 default 配置的 80%。结合两次 default 实验（70% 和 80%），default 配置下的 idle 失败是一个持续存在的问题，源于特定初始构型。pnp-hard 的 `variation_seed=3` 恰好规避了这些"死锁"构型。

### 6.3 与 Polaris 实验对比

| 指标 | Polaris Default (0514) | DreamZero Default #2 (本次) |
| --- | --- | --- |
| 策略 | Polaris (pi0_fast_droid_jointpos) | DreamZero |
| Task suite / split | default / default | default / default |
| 成功率 | 10/10 = 100.0% | 8/10 = 80.0% |
| 失败模式 | 无 | idle: 2 |

> 在 default 配置下，Polaris 以 100% 成功率优于 DreamZero 的 80%。但在 pnp-hard 配置下，DreamZero 的 100% 显著优于 Polaris 的 50%。这表明 DreamZero 在面对扰动时的鲁棒性更强，但在标准无扰动环境下的可靠性略低于 Polaris。

## 7. 运行环境警告

日志中出现的环境警告与前次实验一致：

- `Warp CUDA error ... cuDeviceGetUuid`：CUDA/Warp 驱动入口不匹配，仿真仍正常运行。
- `CPU performance profile is set to powersave`：CPU 处于省电模式，可能影响仿真吞吐但不影响策略行为。
- `Not all actuators are configured! ... 8 != 13`：动作维度 8 与 articulation 关节数 13 不一致，与前次相同。
- `Seed not set`（环境级别）：评测脚本使用默认 seed=0，但 IsaacLab 环境级别的 seed 固定为 42。
- `libgomp: Invalid value for environment variable OMP_NUM_THREADS`：OpenMP 配置异常，但未影响运行。
- NGX / USD material / GLFW 等渲染相关警告：在 headless 模式下常见，未影响 rollout。
- 日志截断：Episode 10 (ep9) 的日志在 step 202/450 处截断，但从 `results.json` 确认该 episode 在 step 203 正常完成（step 173 成功 + 30 steps hold）。截断原因可能是日志缓冲区刷新延迟或文件写入被提前关闭。

## 8. 结论

本次 DreamZero DROID Scene 2 **default** 评测（第二次复现）达到 **8/10 = 80% 成功率**，平均进度 **80%**，**刚好通过** strict_success_threshold (80%)。相比第一次 default 实验 (70%)，成功率有所提升。

### 核心发现：

1. **80% 成功率**：在 default 配置（无扰动、horizontal_thresh=0.06m）下，DreamZero 实现了 8/10 成功，较首次实验 (7/10) 提升一个 episode。
2. **idle 失败减少**：从 3 次减少到 2 次，但 idle 失败的根本原因（特定初始构型导致策略"死锁"）仍然存在。两次实验中失败 episode 的物体终态位置完全一致，证实了构型特异性。
3. **成功耗时的双峰分布**：成功 episode 分为快速组 (~12s) 和慢速组 (~22s)，中间几乎没有过渡，暗示策略存在两种不同的执行路径。
4. **最后一个 episode (ep9) 成功**：尽管日志在 step 202 处截断，`results.json` 确认 ep9 以 step 173 成功（11.53s），是本次实验中最快完成的 episode。h_dist=0.0392m 虽然是成功 ep 中最大的，但仍远低于 0.06m 阈值。
5. **放置精度充足**：平均 h_dist=0.0249m，全部低于 0.06m 阈值，最差案例 (ep9) 仍有 ~21mm 余量。
6. **与 pnp-hard 的对比反差**：DreamZero 在 pnp-hard（全扰动、更严格阈值）下取得 100%，而 default 下仅 80%。idle 失败与扰动/阈值无关，纯粹由初始构型驱动。

### 需要注意的局限性：

1. **idle 失败的确定性**：ep5 和 ep6 的失败是确定性的（相同构型、相同结果），策略需要修改以应对这类初始排布。
2. **样本量有限**：仅 10 个 episode，80% 成功率的 95% 置信区间下界约为 44%（Clopper-Pearson）。
3. **成功耗时偏长**：本次平均成功耗时 17.14s 高于前次的 14.44s，慢速组 (~22s) 的占比增加。
4. **日志截断**：最后一个 episode 的日志不完整，但 results.json 确认已成功完成。

## 9. 建议后续实验

- **诊断 idle 失败**：深入分析 ep5/ep6 的初始构型，检查罐头和杯子的相对位置/朝向是否超出策略训练分布。
- **增加 episode 数量**：运行 20–50 个 episode 以提高统计置信度，确认真实成功率区间。
- **对比不同 seed**：使用不同的 `--variation-seed` 运行 default 配置，检验 idle 失败是否仅在特定 seed 下出现。
- **策略改进**：针对 idle 失败模式，考虑增加初始动作的扰动或预热步骤，打破策略的"死锁"状态。
- **分析成功耗时双峰**：检查快速成功组和慢速成功组的初始构型差异，理解策略在不同排布下的行为差异。
