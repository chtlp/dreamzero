"""
Example script for running 10 rollouts of a DROID policy on the example environment.

Usage:

First, make sure you download the simulation assets and unpack them into the root directory of this package.

Then, in a separate terminal, launch the policy server on localhost:8000 
-- make sure to set XLA_PYTHON_CLIENT_MEM_FRACTION to avoid JAX hogging all the GPU memory.

For example, to launch a pi0-FAST-DROID policy (with joint position control), 
run the command below in a separate terminal from the openpi "karl/droid_policies" branch:

XLA_PYTHON_CLIENT_MEM_FRACTION=0.5 uv run scripts/serve_policy.py policy:checkpoint --policy.config=pi0_fast_droid_jointpos --policy.dir=s3://openpi-assets-simeval/pi0_fast_droid_jointpos

Finally, run the evaluation script:

python run_eval.py --episodes 10 --headless
"""

import uuid
import json

import tyro
import argparse
import gymnasium as gym
import torch
import cv2
import mediapy
import numpy as np
from datetime import datetime
from pathlib import Path
import os
import random
import sys
from dataclasses import replace
from typing import Literal, Optional
from PIL import Image
from tqdm import tqdm

from openpi_client import image_tools
from sim_evals.inference.abstract_client import InferenceClient
from sim_evals.evaluation import (
    SceneSuccessConfig,
    SCENE_CONFIGS,
    STAGE_NAMES,
    get_source_initial_height,
    evaluate_progress,
    compute_success_hold_steps,
)
from policy_client import WebsocketClientPolicy


TASK_SUITES = ("default", "pnp-hard")

WARN_COLOR = "\033[1;35m"
RESET_COLOR = "\033[0m"

def format_warning(message: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return message
    return f"{WARN_COLOR}{message}{RESET_COLOR}"

def _scaled_uniform(rng: random.Random, low: float, high: float, scale: float):
    return rng.uniform(low, high) * scale

def select_instruction(
    scene_cfg: SceneSuccessConfig,
    eval_split: Literal["default", "held-out-scene", "held-out-instruction"],
    instruction_override: Optional[str],
    instruction_variant: int,
):
    """Select the language prompt for the requested split."""
    if instruction_override:
        return instruction_override, "override"
    if eval_split == "held-out-instruction":
        if not scene_cfg.heldout_instructions:
            raise ValueError(f"Scene {scene_cfg.scene_id} has no held-out instructions.")
        index = instruction_variant % len(scene_cfg.heldout_instructions)
        return scene_cfg.heldout_instructions[index], f"held-out-instruction:{index}"
    return scene_cfg.instruction, "default"

def apply_task_suite(
    scene_cfg: SceneSuccessConfig,
    task_suite: Literal["default", "pnp-hard"],
    eval_split: Literal["default", "held-out-scene", "held-out-instruction"],
    object_pose: bool,
    container_pose: bool,
    distractor: bool,
    lighting_camera: bool,
):
    if task_suite == "default":
        return scene_cfg, eval_split, object_pose, container_pose, distractor, lighting_camera
    if task_suite != "pnp-hard":
        raise ValueError(f"Task suite {task_suite!r} not supported. Available: {TASK_SUITES}")

    hard_scene_cfg = replace(
        scene_cfg,
        horizontal_thresh=max(0.03, scene_cfg.horizontal_thresh * 0.7),
        transport_thresh=max(0.06, scene_cfg.transport_thresh * 0.75),
    )
    hard_eval_split = "held-out-scene" if eval_split == "default" else eval_split
    return hard_scene_cfg, hard_eval_split, True, True, True, True

def build_scene_variation(
    scene_cfg: SceneSuccessConfig,
    eval_split: Literal["default", "held-out-scene", "held-out-instruction"],
    task_suite: Literal["default", "pnp-hard"],
    object_pose: bool,
    container_pose: bool,
    distractor: bool,
    lighting_camera: bool,
    variation_seed: int,
    variation_level: float,
):
    """Build a deterministic scene perturbation payload for EnvCfg.set_scene()."""
    held_out_scene = eval_split == "held-out-scene"
    use_object_pose = held_out_scene or object_pose
    container_pose_requested = held_out_scene or container_pose
    use_container_pose = container_pose_requested and scene_cfg.target_is_rigid
    use_distractor = held_out_scene or distractor
    use_lighting_camera = held_out_scene or lighting_camera

    if not any([use_object_pose, use_container_pose, use_distractor, use_lighting_camera]):
        if not container_pose_requested:
            return None

    scale = max(0.0, variation_level)
    rng = random.Random(f"scene={scene_cfg.scene_id}:seed={variation_seed}:level={scale}")

    variation = {
        "source_obj": scene_cfg.source_obj,
        "target_obj": scene_cfg.target_obj,
        "target_is_rigid": scene_cfg.target_is_rigid,
        "object_pose": use_object_pose,
        "container_pose": use_container_pose,
        "container_pose_requested": container_pose_requested,
        "distractor": use_distractor,
        "lighting_camera": use_lighting_camera,
        "task_suite": task_suite,
        "variation_seed": variation_seed,
        "variation_level": scale,
    }

    if use_object_pose:
        variation.update({
            "object_offset": (
                _scaled_uniform(rng, -0.06, 0.06, scale),
                _scaled_uniform(rng, -0.05, 0.05, scale),
                0.0,
            ),
            "object_yaw": _scaled_uniform(rng, -0.8, 0.8, scale),
        })
    if use_container_pose:
        variation.update({
            "container_offset": (
                _scaled_uniform(rng, -0.07, 0.07, scale),
                _scaled_uniform(rng, -0.06, 0.06, scale),
                0.0,
            ),
            "container_yaw": _scaled_uniform(rng, -0.55, 0.55, scale),
        })
    if use_distractor:
        if task_suite == "pnp-hard":
            variation.update({
                "distractor_offset": (
                    _scaled_uniform(rng, 0.035, 0.075, scale),
                    _scaled_uniform(rng, -0.025, 0.025, scale),
                    0.02,
                ),
                "distractor_size": (0.085, 0.035, 0.04),
                "distractor_color": (0.95, 0.18, 0.05),
                "distractor_yaw": _scaled_uniform(rng, -1.4, 1.4, scale),
                "distractor_description": "nearby red rectangular block",
            })
        else:
            variation.update({
                "distractor_offset": (
                    _scaled_uniform(rng, 0.055, 0.095, scale),
                    _scaled_uniform(rng, -0.035, 0.035, scale),
                    0.018,
                ),
                "distractor_size": (0.075, 0.03, 0.035),
                "distractor_color": (0.95, 0.18, 0.05),
                "distractor_yaw": _scaled_uniform(rng, -1.2, 1.2, scale),
                "distractor_description": "red rectangular block",
            })
    if use_lighting_camera:
        variation.update({
            "light_intensity": rng.uniform(2300, 7800),
            "light_offset": (
                _scaled_uniform(rng, -0.25, 0.25, scale),
                _scaled_uniform(rng, -0.20, 0.20, scale),
                _scaled_uniform(rng, -0.10, 0.12, scale),
            ),
            "camera_offsets": {
                "external_cam": (
                    _scaled_uniform(rng, -0.035, 0.035, scale),
                    _scaled_uniform(rng, -0.035, 0.035, scale),
                    _scaled_uniform(rng, -0.025, 0.025, scale),
                ),
                "external_cam_2": (
                    _scaled_uniform(rng, -0.035, 0.035, scale),
                    _scaled_uniform(rng, -0.035, 0.035, scale),
                    _scaled_uniform(rng, -0.025, 0.025, scale),
                ),
            },
        })

    return variation


class DreamZeroJointPosClient(InferenceClient):
    def __init__(self, 
                remote_host:str = "localhost", 
                remote_port:int = 6000,
                open_loop_horizon:int = 8,
    ) -> None:
        self.client = WebsocketClientPolicy(remote_host, remote_port)
        self.open_loop_horizon = open_loop_horizon
        self.actions_from_chunk_completed = 0
        self.pred_action_chunk = None
        self.session_id = str(uuid.uuid4())

    def visualize(self, request: dict):
        """
        Return the camera views how the model sees it
        """
        curr_obs = self._extract_observation(request)
        right_img = image_tools.resize_with_pad(curr_obs["right_image"], 224, 224)
        wrist_img = image_tools.resize_with_pad(curr_obs["wrist_image"], 224, 224)
        left_img = image_tools.resize_with_pad(curr_obs["left_image"], 224, 224)
        combined = np.concatenate([right_img, wrist_img, left_img], axis=1)
        return combined

    def reset(self):
        self.actions_from_chunk_completed = 0
        self.pred_action_chunk = None
        self.session_id = str(uuid.uuid4())

    def infer(self, obs: dict, instruction: str) -> dict:
        """
        Infer the next action from the policy in a server-client setup
        """
        curr_obs = self._extract_observation(obs)
        if (
            self.actions_from_chunk_completed == 0
            or self.actions_from_chunk_completed >= self.open_loop_horizon
        ):
            self.actions_from_chunk_completed = 0
            request_data = {
                "observation/exterior_image_0_left": image_tools.resize_with_pad(curr_obs["right_image"], 180, 320),
                "observation/exterior_image_1_left": image_tools.resize_with_pad(curr_obs["left_image"], 180, 320),
                "observation/wrist_image_left": image_tools.resize_with_pad(curr_obs["wrist_image"], 180, 320),
                "observation/joint_position": curr_obs["joint_position"].astype(np.float64),
                "observation/cartesian_position": np.zeros((6,), dtype=np.float64),  # dummy cartesian position
                "observation/gripper_position": curr_obs["gripper_position"].astype(np.float64),
                "prompt": instruction,
                "session_id": self.session_id,
            }
            for k, v in request_data.items():
                print(f"{k}: {v.shape if not isinstance(v, str) else v}")
            
            result = self.client.infer(request_data)
            actions = result["actions"] if isinstance(result, dict) else result
            assert len(actions.shape) == 2, f"Expected 2D array, got shape {actions.shape}"
            assert actions.shape[-1] == 8, f"Expected 8 action dimensions (7 joints + 1 gripper), got {actions.shape[-1]}"
            self.pred_action_chunk = actions


        action = self.pred_action_chunk[self.actions_from_chunk_completed]
        self.actions_from_chunk_completed += 1

        # binarize gripper action
        if action[-1].item() > 0.5:
            action = np.concatenate([action[:-1], np.ones((1,))])
        else:
            action = np.concatenate([action[:-1], np.zeros((1,))])

        img1 = image_tools.resize_with_pad(curr_obs["right_image"], 224, 224)
        img2 = image_tools.resize_with_pad(curr_obs["wrist_image"], 224, 224)
        img3 = image_tools.resize_with_pad(curr_obs["left_image"], 224, 224)
        both = np.concatenate([img1, img2, img3], axis=1)

        return {"action": action, "viz": both}

    def _extract_observation(self, obs_dict, *, save_to_disk=False):
        # Assign images
        right_image = obs_dict["policy"]["external_cam"][0].clone().detach().cpu().numpy()
        left_image = obs_dict["policy"]["external_cam_2"][0].clone().detach().cpu().numpy()
        wrist_image = obs_dict["policy"]["wrist_cam"][0].clone().detach().cpu().numpy()

        # Capture proprioceptive state
        robot_state = obs_dict["policy"]
        joint_position = robot_state["arm_joint_pos"].clone().detach().cpu().numpy()
        gripper_position = robot_state["gripper_pos"].clone().detach().cpu().numpy()

        if save_to_disk:
            combined_image = np.concatenate([right_image, wrist_image], axis=1)
            combined_image = Image.fromarray(combined_image)
            combined_image.save("robot_camera_views.png")

        return {
            "right_image": right_image,
            "left_image": left_image,
            "wrist_image": wrist_image,
            "joint_position": joint_position,
            "gripper_position": gripper_position,
        }




def main(
        episodes: int = 10,
        scene: int = 1,
        headless: bool = True,
        host: str = "localhost",
        port: int = 6000,
        task_suite: Literal["default", "pnp-hard"] = "default",
        instruction_override: Optional[str] = None,
        eval_split: Literal["default", "held-out-scene", "held-out-instruction"] = "default",
        instruction_variant: int = 0,
        object_pose: bool = False,
        container_pose: bool = False,
        distractor: bool = False,
        lighting_camera: bool = False,
        variation_seed: int = 0,
        variation_level: float = 1.0,
        early_stop_on_success: bool = True,
        early_stop_success_delay_s: float = 2.0,
        ):
    if task_suite not in TASK_SUITES:
        raise ValueError(f"Task suite {task_suite!r} not supported. Available: {TASK_SUITES}")

    # ---- Validate scene config ----
    if scene not in SCENE_CONFIGS:
        raise ValueError(
            f"Scene {scene} not supported. Available: {list(SCENE_CONFIGS.keys())}"
        )
    scene_cfg = SCENE_CONFIGS[scene]
    requested_eval_split = eval_split
    requested_perturbations = {
        "object_pose": object_pose,
        "container_pose": container_pose,
        "distractor": distractor,
        "lighting_camera": lighting_camera,
    }
    scene_cfg, eval_split, object_pose, container_pose, distractor, lighting_camera = apply_task_suite(
        scene_cfg=scene_cfg,
        task_suite=task_suite,
        eval_split=eval_split,
        object_pose=object_pose,
        container_pose=container_pose,
        distractor=distractor,
        lighting_camera=lighting_camera,
    )
    default_instruction = scene_cfg.instruction
    instruction, instruction_source = select_instruction(
        scene_cfg, eval_split, instruction_override, instruction_variant
    )
    scene_variation = build_scene_variation(
        scene_cfg=scene_cfg,
        eval_split=eval_split,
        task_suite=task_suite,
        object_pose=object_pose,
        container_pose=container_pose,
        distractor=distractor,
        lighting_camera=lighting_camera,
        variation_seed=variation_seed,
        variation_level=variation_level,
    )

    # launch omniverse app with arguments (inside function to prevent overriding tyro)
    from isaaclab.app import AppLauncher
    parser = argparse.ArgumentParser(description="Tutorial on creating an empty stage.")
    AppLauncher.add_app_launcher_args(parser)
    args_cli, _ = parser.parse_known_args()
    args_cli.enable_cameras = True
    args_cli.headless = headless
    app_launcher = AppLauncher(args_cli)
    simulation_app = app_launcher.app

    # All IsaacLab dependent modules should be imported after the app is launched
    import sim_evals.environments # noqa: F401
    from isaaclab_tasks.utils import parse_env_cfg


    # Initialize the env
    env_cfg = parse_env_cfg(
        "DROID",
        device=args_cli.device,
        num_envs=1,
        use_fabric=True,
    )
    env_cfg.set_scene(scene, variation=scene_variation)
    env = gym.make("DROID", cfg=env_cfg)

    obs, _ = env.reset()
    obs, _ = env.reset() # need second render cycle to get correctly loaded materials
    client = DreamZeroJointPosClient(remote_host=host, remote_port=port)

    max_steps = env.env.max_episode_length
    control_hz = 15
    success_hold_steps = compute_success_hold_steps(early_stop_success_delay_s, control_hz)

    # ---- Output directory ----
    video_dir = Path("runs") / datetime.now().strftime("%Y-%m-%d") / datetime.now().strftime("%H-%M-%S")
    video_dir.mkdir(parents=True, exist_ok=True)

    # ---- Save run metadata immediately for debugging / reproducibility ----
    run_metadata = {
        "created_at": datetime.now().isoformat(),
        "scene": scene,
        "task_suite": task_suite,
        "source_obj": scene_cfg.source_obj,
        "target_obj": scene_cfg.target_obj,
        "target_is_rigid": scene_cfg.target_is_rigid,
        "instruction": instruction,
        "default_instruction": default_instruction,
        "instruction_override": instruction_override,
        "instruction_source": instruction_source,
        "instruction_variant": instruction_variant,
        "heldout_instructions": scene_cfg.heldout_instructions,
        "eval_split": eval_split,
        "requested_eval_split": requested_eval_split,
        "requested_perturbations": requested_perturbations,
        "scene_variation": scene_variation,
        "success_config": {
            "horizontal_thresh": scene_cfg.horizontal_thresh,
            "height_lo": scene_cfg.height_lo,
            "height_hi": scene_cfg.height_hi,
            "reach_thresh": scene_cfg.reach_thresh,
            "lift_height": scene_cfg.lift_height,
            "transport_thresh": scene_cfg.transport_thresh,
        },
        "episodes": episodes,
        "max_steps": max_steps,
        "control_hz": control_hz,
        "success_hold_steps": success_hold_steps,
        "host": host,
        "port": port,
        "headless": headless,
        "early_stop_on_success": early_stop_on_success,
        "early_stop_success_delay_s": early_stop_success_delay_s,
    }
    metadata_path = video_dir / "run_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(run_metadata, f, indent=2, default=str)

    # ---- Get initial source object height (table surface proxy) ----
    try:
        initial_source_z = get_source_initial_height(env.unwrapped, scene_cfg)
    except Exception as e:
        print(f"[WARN] Could not get initial source height: {e}. Defaulting to 0.0")
        initial_source_z = 0.0

    # ---- Evaluation loop ----
    video = []
    results = []  # per-episode results

    print(f"\n{'='*60}")
    print(f"  DROID Sim Eval — Scene {scene}: \"{instruction}\"")
    print(f"  Task suite: {task_suite}")
    if instruction_override or instruction_source != "default":
        print(f"  Default instruction: \"{default_instruction}\"")
        print(f"  Instruction source: {instruction_source}")
    print(f"  Split: {eval_split}  |  Variation seed: {variation_seed}  |  Level: {variation_level}")
    if scene_variation:
        print(f"  Scene variation: {scene_variation}")
        if scene_variation.get("container_pose_requested") and not scene_variation.get("container_pose"):
            print(format_warning("  [WARN] Container pose skipped because the target is not a rigid scene entity."))
    print(f"  Episodes: {episodes}  |  Max steps: {max_steps}")
    print(f"  Early stop: {early_stop_on_success}  |  Hold delay: {early_stop_success_delay_s}s ({success_hold_steps} steps)")
    print(f"  Output: {video_dir}")
    print(f"{'='*60}\n")

    with torch.no_grad():
        for ep in range(episodes):
            max_stage = 0
            has_succeeded = False
            final_details = {}
            steps_taken = 0
            success_step = None
            consecutive_success = 0  # count of consecutive steps where success holds

            for step in tqdm(range(max_steps), desc=f"Episode {ep+1}/{episodes}"):
                steps_taken = step + 1
                ret = client.infer(obs, instruction)
                if not headless:
                    cv2.imshow("Right Camera", cv2.cvtColor(ret["viz"], cv2.COLOR_RGB2BGR))
                    cv2.waitKey(1)
                video.append(ret["viz"])
                action = torch.tensor(ret["action"])[None]
                obs, _, term, trunc, _ = env.step(action)

                # ---- Evaluate success at each step ----
                try:
                    stage, success, details = evaluate_progress(
                        env.unwrapped, scene_cfg, initial_source_z
                    )
                    max_stage = max(max_stage, stage)
                    final_details = details

                    if success:
                        consecutive_success += 1
                        if consecutive_success == 1:
                            # Record the step where the current success streak began
                            success_step = step
                        # Require the success condition to hold for the full hold period
                        if consecutive_success >= success_hold_steps:
                            has_succeeded = True
                    else:
                        # Success condition lost — reset the streak
                        consecutive_success = 0
                        success_step = None
                except Exception as e:
                    # If evaluation fails, break the success streak as well
                    consecutive_success = 0
                    success_step = None

                if has_succeeded and early_stop_on_success:
                    break
                if term or trunc:
                    break

            if not final_details:
                final_details = {"error": "Evaluation failed or episode empty"}

            ep_result = {
                "episode": ep,
                "scene": scene,
                "task_suite": task_suite,
                "instruction": instruction,
                "default_instruction": default_instruction,
                "instruction_override": instruction_override,
                "instruction_source": instruction_source,
                "instruction_variant": instruction_variant,
                "eval_split": eval_split,
                "scene_variation": scene_variation,
                "success": has_succeeded,
                "stage": max_stage,
                "stage_name": STAGE_NAMES.get(max_stage, "unknown"),
                "steps": steps_taken,
                "success_step": success_step,
                "success_hold_steps": success_hold_steps,
                "early_stop_success_delay_s": early_stop_success_delay_s,
                "details": final_details,
            }
            results.append(ep_result)

            # Print per-episode result
            status = "✅ SUCCESS" if has_succeeded else f"❌ FAIL (stage={max_stage}: {STAGE_NAMES.get(max_stage, '?')})"
            print(f"  Episode {ep+1}/{episodes}: {status}  |  h_dist={final_details.get('horizontal_dist', '?')}  v_diff={final_details.get('vertical_diff', '?')}")

            # ---- Save video ----
            try:
                client.reset()
                mediapy.write_video(
                    video_dir / f"episode_{ep}.mp4",
                    video,
                    fps=15,
                )
            except Exception as e:
                print(f"  [WARN] Failed to save video for episode {ep+1}: {e}")
            video = []

            # ---- Reset for next episode ----
            try:
                obs, _ = env.reset()
                # Re-acquire initial_source_z after reset (position may vary)
                initial_source_z = get_source_initial_height(env.unwrapped, scene_cfg)
            except Exception as e:
                print(f"  [WARN] Failed to reset env after episode {ep+1}: {e}")

    # ---- Print summary ----
    num_success = sum(r["success"] for r in results)
    success_rate = num_success / episodes * 100 if episodes > 0 else 0
    progress_rate = (sum(r["stage"] for r in results) / (episodes * 4) * 100) if episodes > 0 else 0
    stage_counts = {}
    for r in results:
        sn = r["stage_name"]
        stage_counts[sn] = stage_counts.get(sn, 0) + 1

    print(f"\n{'='*60}")
    print(f"  RESULTS — Scene {scene}: \"{instruction}\"")
    print(f"{'='*60}")
    print(f"  Success rate: {num_success}/{episodes} ({success_rate:.1f}%)")
    print(f"  Progress rate: {progress_rate:.1f}%")
    print(f"  Stage distribution:")
    for sname, cnt in sorted(stage_counts.items()):
        print(f"    {sname}: {cnt}")
    print(f"  Videos saved to: {video_dir}")
    print(f"{'='*60}\n")

    # ---- Save results JSON ----
    results_summary = {
        "scene": scene,
        "task_suite": task_suite,
        "instruction": instruction,
        "default_instruction": default_instruction,
        "instruction_override": instruction_override,
        "instruction_source": instruction_source,
        "eval_split": eval_split,
        "requested_eval_split": requested_eval_split,
        "requested_perturbations": requested_perturbations,
        "scene_variation": scene_variation,
        "success_config": {
            "horizontal_thresh": scene_cfg.horizontal_thresh,
            "height_lo": scene_cfg.height_lo,
            "height_hi": scene_cfg.height_hi,
            "reach_thresh": scene_cfg.reach_thresh,
            "lift_height": scene_cfg.lift_height,
            "transport_thresh": scene_cfg.transport_thresh,
        },
        "episodes": episodes,
        "success_count": num_success,
        "success_rate": success_rate,
        "progress_rate": progress_rate,
        "early_stop_on_success": early_stop_on_success,
        "early_stop_success_delay_s": early_stop_success_delay_s,
        "success_hold_steps": success_hold_steps,
        "stage_distribution": stage_counts,
        "per_episode": results,
    }
    results_path = video_dir / "results.json"
    with open(results_path, "w") as f:
        json.dump(results_summary, f, indent=2, default=str)
    print(f"  Results JSON saved to: {results_path}")

    env.close()
    simulation_app.close()

if __name__ == "__main__":
    args = tyro.cli(main)
