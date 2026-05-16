import os
import cv2
import json

log_dir = "/root/workspace/dreamzero/runs/2026-05-16/16-07-56"
out_dir = "/root/workspace/dreamzero/exp-docs/assets/dreamzero_droid_scene2_20260516_160732"
os.makedirs(out_dir, exist_ok=True)

with open(os.path.join(log_dir, "results.json")) as f:
    results = json.load(f)

for ep_data in results["per_episode"]:
    ep_id = ep_data["episode"]
    video_path = os.path.join(log_dir, f"episode_{ep_id}.mp4")
    if not os.path.exists(video_path):
        continue
    
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames == 0:
        continue
    
    # Extract 6 evenly spaced frames
    indices = [int(i * (total_frames - 1) / 5) for i in range(6)]
    frames = []
    
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    
    if len(frames) == 6:
        contact_sheet = cv2.hconcat(frames)
        out_path = os.path.join(out_dir, f"episode_{ep_id}_contact_sheet.jpg")
        cv2.imwrite(out_path, contact_sheet)
    
    # Save initial state and final state
    if ep_data["success"]:
        if len(frames) > 0:
            cv2.imwrite(os.path.join(out_dir, f"ep{ep_id}_initial.jpg"), frames[0])
            cv2.imwrite(os.path.join(out_dir, f"ep{ep_id}_success.jpg"), frames[-1])
    else:
        if len(frames) > 0:
            cv2.imwrite(os.path.join(out_dir, f"ep{ep_id}_initial.jpg"), frames[0])
            cv2.imwrite(os.path.join(out_dir, f"ep{ep_id}_failure.jpg"), frames[-1])
            
    cap.release()

print("Images extracted successfully.")
