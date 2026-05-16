# DreamZero DROID Scene 2 实验日志分析报告

## 1. 实验概览

- **日志文件**：`logs/droid_roboarena_efficiency/eval_dreamzero_droid_scene2_20260516_160732.log`
- **运行目录**：`runs/2026-05-16/16-07-56`
- **任务**：DROID Sim Eval — Scene 2，指令为 `put the can in the mug`
- **目标物体**：source 为 `_10_potted_meat_can`，target 为 `_25_mug`
- **计划集数**：10 episodes；每集上限 450 steps，控制频率 15 Hz，即每集最长 30s
- **成功判定**：水平距离 `< 0.06m`，高度差在 `(-0.02m, 0.15m)`，并需连续保持 30 steps（约 2s）
- **Early-stop**：开启，成功保持后提前结束

本次运行已完整结束，10 个 episode 全部完成，`results.json` 已正常生成。

## 2. 运行完成度与指标

| 项目 | 结果 |
| --- | --- |
| 计划 episodes | 10 |
| 完整完成 episodes | 10 |
| 保存视频 | `episode_0.mp4` ~ `episode_9.mp4` |
| `results.json` | ✅ 已生成 |
| 成功率 | **7/10 = 70.0%** |
| 平均进度 | **70.0%** |
| stage 分布 | place (success): 7, idle: 3 |
| 是否通过 strict_success_threshold (80%) | ❌ 否 |

逐 episode 摘要：

| Episode | 结果 | 总 steps | 成功 step | 成功耗时 | `h_dist` | `v_diff` | 解释 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | ✅ SUCCESS | 189 | 159 | 10.60s | 0.0064 | 0.1016 | 最快成功，罐头高精度放置入杯 |
| 1 | ❌ FAILURE | 450 | - | - | 0.1410 | 0.0030 | 一直停留在 idle 阶段，未能成功抓取 |
| 2 | ✅ SUCCESS | 203 | 173 | 11.53s | 0.0418 | 0.1037 | 快速成功 |
| 3 | ✅ SUCCESS | 194 | 164 | 10.93s | 0.0152 | 0.1038 | 快速成功 |
| 4 | ❌ FAILURE | 450 | - | - | 0.1410 | 0.0030 | 与 Ep 1 初始状态一致，未能成功抓取 |
| 5 | ✅ SUCCESS | 265 | 235 | 15.67s | 0.0144 | 0.1107 | 成功 |
| 6 | ✅ SUCCESS | 396 | 366 | 24.40s | 0.0264 | 0.1059 | 最慢成功，可能经历了较长时间探索或调整 |
| 7 | ✅ SUCCESS | 255 | 225 | 15.00s | 0.0154 | 0.0992 | 成功 |
| 8 | ✅ SUCCESS | 224 | 194 | 12.93s | 0.0245 | 0.1074 | 成功 |
| 9 | ❌ FAILURE | 450 | - | - | 0.1410 | 0.0030 | 与 Ep 1 初始状态一致，未能成功抓取 |

> 成功的 episode 均因 `early_stop_on_success=True` 在成功连续保持 30 steps（约 2s）后提前结束。成功步数范围为 159–366，对应成功耗时 10.60s–24.40s。3 次失败的 episode 均达到 450 steps 上限。

## 3. 截图证据

完整关键帧拼图（每 episode 6 帧均匀采样）：

![Episode 0 contact sheet (Fastest)](assets/dreamzero_droid_scene2_20260516_160732/episode_0_contact_sheet.jpg)

![Episode 1 contact sheet (Failure)](assets/dreamzero_droid_scene2_20260516_160732/episode_1_contact_sheet.jpg)

![Episode 2 contact sheet](assets/dreamzero_droid_scene2_20260516_160732/episode_2_contact_sheet.jpg)

![Episode 3 contact sheet](assets/dreamzero_droid_scene2_20260516_160732/episode_3_contact_sheet.jpg)

![Episode 4 contact sheet (Failure)](assets/dreamzero_droid_scene2_20260516_160732/episode_4_contact_sheet.jpg)

![Episode 5 contact sheet](assets/dreamzero_droid_scene2_20260516_160732/episode_5_contact_sheet.jpg)

![Episode 6 contact sheet (Slowest success)](assets/dreamzero_droid_scene2_20260516_160732/episode_6_contact_sheet.jpg)

![Episode 7 contact sheet](assets/dreamzero_droid_scene2_20260516_160732/episode_7_contact_sheet.jpg)

![Episode 8 contact sheet](assets/dreamzero_droid_scene2_20260516_160732/episode_8_contact_sheet.jpg)

![Episode 9 contact sheet (Failure)](assets/dreamzero_droid_scene2_20260516_160732/episode_9_contact_sheet.jpg)

典型成功样例（Episode 0，最快）：

![Episode 0 initial state](assets/dreamzero_droid_scene2_20260516_160732/ep0_initial.jpg)

![Episode 0 success state](assets/dreamzero_droid_scene2_20260516_160732/ep0_success.jpg)

典型失败样例（Episode 1）：

![Episode 1 initial state](assets/dreamzero_droid_scene2_20260516_160732/ep1_initial.jpg)

![Episode 1 failure state](assets/dreamzero_droid_scene2_20260516_160732/ep1_failure.jpg)

## 4. 关键统计

| 指标 | 值 |
| --- | --- |
| 成功率 | 70% (7/10) |
| 平均成功 step | 216.6 (14.44s) |
| 最快成功 | Episode 0: step 159 (10.60s) |
| 最慢成功 | Episode 6: step 366 (24.40s) |
| 成功 episode 平均 `h_dist` | 0.0206m |
| 成功 episode 平均 `v_diff` | 0.1046m |

## 5. 行为模式分析

### 5.1 成功的 Episode

7次成功的 Episode 表明 DreamZero 策略在此场景下具备执行完整的 Pick-and-Place (grasp, lift, transport, place) 流水线的能力。其中，大部分成功发生在 10-16s 之间，放置精度较高（平均水平误差 ~2cm）。

### 5.2 失败的 Episode (Ep 1, 4, 9)

3 次失败的 Episode 均停留在 `idle` 阶段，直到超时 (450 steps)。根据 `results.json` 中的 `source_pos` 和 `target_pos` 数据，Ep 1, 4, 9 共享完全相同的初始物体排布配置。这表明模型对该特定的物体构型存在明显的脆弱性，无法在该特定状态下启动有效的抓取动作，从而一直处于闲置 (idle) 状态，导致任务失败。

## 6. 结论与后续建议

本次 DreamZero DROID Scene 2 评测的成功率为 70%，稍低于预期的 80% 阈值。虽然策略在 70% 的配置下能稳定地完成罐头放置任务（平均耗时 ~14.4s），但在某些特定初始排布（如 Ep 1/4/9）下表现出一致的失败行为。

**后续建议**：
1. **排查特定失败配置**：针对 Ep 1、4、9 的初始排布进行专项 debug，查看是相机视角遮挡、空间可达性不足还是策略在该状态下的动作预测发散导致了“idle”行为。
2. **优化 Inference 速度与动作输出**：如果确认策略在某些配置下犹豫不决，可以考虑优化推理延迟或注入适量探索噪声帮助其脱离困境。
3. **增加评测多样性**：开启环境变量随机种子，并确保每次评测的 10/20 episodes 均匀覆盖不同的初始构型，避免策略因在某一特定分布下连续失败而导致整体成功率显著下滑。
