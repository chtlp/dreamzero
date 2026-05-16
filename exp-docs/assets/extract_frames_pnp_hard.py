"""Extract keyframes from DreamZero pnp-hard episode videos for the experiment report.

This script extracts frames at specific time points to illustrate:
1. Contact sheets (6 frames per episode)
2. Success pattern analysis (fast, medium, slow)
3. Key moments: initial state, grasp, transport, alignment, success
"""
import os
import cv2
import json
import numpy as np

log_dir = "/root/workspace/dreamzero/runs/2026-05-16/17-10-25"
out_dir = "/root/workspace/dreamzero/exp-docs/assets/dreamzero_droid_scene2_pnp_hard_20260516_171000"
os.makedirs(out_dir, exist_ok=True)

with open(os.path.join(log_dir, "results.json")) as f:
    results = json.load(f)

CONTROL_HZ = 15  # 15 Hz control frequency


def extract_frame_at_time(cap, time_s, total_frames, fps):
    """Extract a single frame at a given time in seconds."""
    frame_idx = min(int(time_s * fps), total_frames - 1)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    return frame if ret else None


def extract_frame_at_step(cap, step, total_frames, fps):
    """Extract a single frame at a given simulation step."""
    time_s = step / CONTROL_HZ
    return extract_frame_at_time(cap, time_s, total_frames, fps)


def create_contact_sheet(frames, cols=6):
    """Create a horizontal contact sheet from a list of frames."""
    if not frames:
        return None
    # Ensure all frames have the same height
    h = frames[0].shape[0]
    resized = []
    for f in frames:
        if f.shape[0] != h:
            scale = h / f.shape[0]
            f = cv2.resize(f, (int(f.shape[1] * scale), h))
        resized.append(f)
    return cv2.hconcat(resized)


for ep_data in results["per_episode"]:
    ep_id = ep_data["episode"]
    video_path = os.path.join(log_dir, f"episode_{ep_id}.mp4")
    if not os.path.exists(video_path):
        print(f"Video not found: {video_path}")
        continue

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    if total_frames == 0 or fps == 0:
        print(f"Invalid video: {video_path}")
        cap.release()
        continue

    total_steps = ep_data["steps"]
    success_step = ep_data.get("success_step")
    success_time = success_step / CONTROL_HZ if success_step else None
    total_time = total_steps / CONTROL_HZ

    print(f"\nEP{ep_id}: {total_frames} frames, {fps:.1f} fps, {total_steps} steps, "
          f"success_step={success_step}, success_time={success_time:.1f}s, total_time={total_time:.1f}s")

    # === 1. Contact sheet: 6 evenly spaced frames ===
    indices = [int(i * (total_frames - 1) / 5) for i in range(6)]
    contact_frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            contact_frames.append(frame)

    if len(contact_frames) == 6:
        contact_sheet = create_contact_sheet(contact_frames)
        cv2.imwrite(os.path.join(out_dir, f"episode_{ep_id}_contact_sheet.jpg"), contact_sheet)
        print(f"  Contact sheet saved")

    # === 2. Key moment frames ===
    # Initial state (t=0)
    frame_init = extract_frame_at_time(cap, 0, total_frames, fps)
    if frame_init is not None:
        cv2.imwrite(os.path.join(out_dir, f"ep{ep_id}_initial.jpg"), frame_init)

    # Success state (last frame before early-stop)
    if ep_data["success"] and success_step:
        frame_success = extract_frame_at_step(cap, success_step, total_frames, fps)
        if frame_success is not None:
            cv2.imwrite(os.path.join(out_dir, f"ep{ep_id}_success.jpg"), frame_success)

    # === 3. Success pattern keyframes ===
    # Extract frames at key phases: approach (~3-5s), grasp (~5-8s), transport (~8-12s), align (success_time-2s), success
    if ep_data["success"] and success_time:
        key_times = {}

        if success_time <= 13:
            # Fast success pattern
            key_times = {
                "start": 0,
                "approach": min(3.0, success_time * 0.2),
                "grasp": min(5.0, success_time * 0.35),
                "transport": min(8.0, success_time * 0.55),
                "align": max(success_time - 2.0, success_time * 0.8),
                "success": success_time,
            }
        elif success_time <= 18:
            # Medium success pattern
            key_times = {
                "start": 0,
                "approach": min(4.0, success_time * 0.15),
                "grasp": min(7.0, success_time * 0.3),
                "transport": min(10.0, success_time * 0.5),
                "align": max(success_time - 3.0, success_time * 0.75),
                "success": success_time,
            }
        else:
            # Slow success pattern
            key_times = {
                "start": 0,
                "approach": min(5.0, success_time * 0.1),
                "grasp": min(8.0, success_time * 0.25),
                "transport": min(14.0, success_time * 0.45),
                "align": max(success_time - 4.0, success_time * 0.7),
                "success": success_time,
            }

        for label, t in key_times.items():
            frame = extract_frame_at_time(cap, t, total_frames, fps)
            if frame is not None:
                cv2.imwrite(os.path.join(out_dir, f"ep{ep_id}_{label}.jpg"), frame)
                print(f"  {label} @ {t:.1f}s saved")

    cap.release()

print(f"\n=== Done! All frames saved to {out_dir} ===")
print(f"Total files: {len(os.listdir(out_dir))}")
