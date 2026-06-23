"""Shared utilities for robot control loops."""

import datetime
import time
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from gello.agents.agent import Agent
from gello.env import RobotEnv

DEFAULT_MAX_JOINT_DELTA = 1.0


def move_to_start_position(
    env: RobotEnv, agent: Agent, max_delta: float = 1.0, steps: int = 25
) -> bool:
    """Move robot to start position gradually.

    Args:
        env: Robot environment
        agent: Agent that provides target position
        max_delta: Maximum joint delta per step
        steps: Number of steps for gradual movement

    Returns:
        bool: True if successful, False if position too far
    """
    print("Going to start position")
    start_pos = agent.act(env.get_obs())
    obs = env.get_obs()
    joints = obs["joint_positions"]

    abs_deltas = np.abs(start_pos - joints)
    id_max_joint_delta = np.argmax(abs_deltas)

    max_joint_delta = DEFAULT_MAX_JOINT_DELTA
    if abs_deltas[id_max_joint_delta] > max_joint_delta:
        id_mask = abs_deltas > max_joint_delta
        print()
        ids = np.arange(len(id_mask))[id_mask]
        for i, delta, joint, current_j in zip(
            ids,
            abs_deltas[id_mask],
            start_pos[id_mask],
            joints[id_mask],
        ):
            print(
                f"joint[{i}]: \t delta: {delta:4.3f} , leader: \t{joint:4.3f} , follower: \t{current_j:4.3f}"
            )
        return False

    print(f"Start pos: {len(start_pos)}", f"Joints: {len(joints)}")
    assert len(start_pos) == len(
        joints
    ), f"agent output dim = {len(start_pos)}, but env dim = {len(joints)}"

    for _ in range(steps):
        obs = env.get_obs()
        command_joints = agent.act(obs)
        current_joints = obs["joint_positions"]
        delta = command_joints - current_joints
        max_joint_delta = np.abs(delta).max()
        if max_joint_delta > max_delta:
            delta = delta / max_joint_delta * max_delta
        env.step(current_joints + delta)

    return True


class SaveInterface:
    """Handles keyboard-based data saving interface."""

    def __init__(
        self,
        data_dir: str = "data",
        agent_name: str = "Agent",
        expand_user: bool = False,
    ):
        """Initialize save interface.

        Args:
            data_dir: Base directory for saving data
            agent_name: Name of agent (used for subdirectory)
            expand_user: Whether to expand ~ in data_dir path
        """
        from gello.data_utils.keyboard_interface import KBReset

        self.kb_interface = KBReset()
        self.data_dir = Path(data_dir).expanduser() if expand_user else Path(data_dir)
        self.agent_name = agent_name
        self.save_path: Optional[Path] = None

        print("Save interface enabled. Use keyboard controls:")
        print("  S: Start recording")
        print("  Q: Stop recording")

    def update(self, obs: Dict[str, Any], action: np.ndarray) -> Optional[str]:
        """Update save interface and handle saving.

        Args:
            obs: Current observations
            action: Current action

        Returns:
            Optional[str]: "quit" if user wants to exit, None otherwise
        """
        from gello.data_utils.format_obs import save_frame

        dt = datetime.datetime.now()
        state = self.kb_interface.update()

        if state == "start":
            dt_time = datetime.datetime.now()
            self.save_path = (
                self.data_dir / self.agent_name / dt_time.strftime("%m%d_%H%M%S")
            )
            self.save_path.mkdir(parents=True, exist_ok=True)
            print(f"Saving to {self.save_path}")
        elif state == "save":
            if self.save_path is not None:
                save_frame(self.save_path, dt, obs, action)
        elif state == "normal":
            self.save_path = None
        elif state == "quit":
            print("\nExiting.")
            return "quit"
        else:
            raise ValueError(f"Invalid state {state}")

        return None

import torch
import numpy as np
from typing import Dict, Any, Optional

class LeRobotSaveInterface:
    def __init__(self, repo_id: str = "local/ur5_lerobot_dataset", fps: int = 30, task_name: str = "UR5 Teleoperation Task"):
        from gello.data_utils.keyboard_interface import KBReset
        from lerobot.datasets.lerobot_dataset import LeRobotDataset
        import os  # 新增导入 os

        self.kb_interface = KBReset()
        self.is_recording = False
        self.task_name = task_name  # <--- 新增这行，把任务名记在心里
        
        joint_names = ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3", "gripper_width"]
        image_dim_names = ["height", "width", "channel"]

        # 只定义业务字段。timestamp / frame_index / episode_index / task_index
        # 属于 LeRobot 的 DEFAULT_FEATURES，由框架自动管理，不需要也不能在此覆盖
        # （LeRobotDatasetMetadata.create 内部用 {**features, **DEFAULT_FEATURES} 合并，
        #  DEFAULT_FEATURES 优先级更高，写在这里的同名字段会被静默覆盖）。
        features = {
            "observation.state": {"dtype": "float32", "shape": (7,), "names": joint_names},
            "action":            {"dtype": "float32", "shape": (7,), "names": joint_names},
            "observation.images.base":  {"dtype": "video", "shape": (480, 640, 3), "names": image_dim_names},  # D435
            "observation.images.wrist": {"dtype": "video", "shape": (480, 640, 3), "names": image_dim_names},  # D415
        }
        
        # 2. 判断数据集文件夹是否已经存在
        dataset_path = os.path.expanduser(f"~/.cache/huggingface/lerobot/{repo_id}")
        if os.path.exists(dataset_path):
            print(f"\n[LeRobot] 📂 发现已有数据集，开启【追加模式】 ({repo_id})")
            self.dataset = LeRobotDataset(repo_id)
        else:
            print(f"\n[LeRobot] ✨ 创建【全新】数据集 ({repo_id})")
            # 只有第一次不存在时，才调用 create()。并在这里加上 robot_type="ur5"
            self.dataset = LeRobotDataset.create(
                repo_id=repo_id, 
                fps=fps, 
                features=features, 
                robot_type="ur5"   # <--- 这里加上机器人型号！
            )
            
        print("操作指南: \n  按 [S] 键开始录制一个 Episode \n  按 [Q] 键停止录制（回到待机）\n  按 [Esc] 键退出程序（若正在录制则先自动保存）")

    def _process_image(self, img_array: np.ndarray) -> torch.Tensor:
        # 视频编码器只接受 uint8 HWC 格式
        if img_array.dtype != np.uint8:
            if img_array.dtype in [np.float32, np.float64] and img_array.max() <= 1.0:
                # clip 防止浮点精度导致的轻微越界（如 1.0001）在 astype 时溢出回绕
                img_array = np.clip(img_array * 255.0, 0, 255)
            img_array = img_array.astype(np.uint8)

        # FFmpeg 要求内存连续，np.ascontiguousarray 保证这一点
        return torch.from_numpy(np.ascontiguousarray(img_array))

    def update(self, obs: Dict[str, Any], action: np.ndarray) -> Optional[str]:
        # 每帧调用一次，轮询键盘状态，驱动录制状态机。
        # 状态机流转：
        #   待机(normal) --[S键]--> 录制中(start→save) --[Q键]--> 待机(normal)
        #                                                --[Esc键]--> 退出(quit)
        state = self.kb_interface.update()

        if state == "start":
            # S 键按下时触发一次。立即写入第一帧，再设置录制标志。
            # 注意：KBReset 只在按键帧返回 "start"，下一帧起持续返回 "save"，
            # 若不在此写帧，每个 Episode 的第一帧会永远丢失。
            if not self.is_recording:
                # 获取当前已存好的数量，加 1 就是正在录制的这一条
                current_count = self.dataset.num_episodes + 1 
                print(f"\n[LeRobot] 🎥 开始录制第 【{current_count}】 条 Episode...")
                self.is_recording = True
                self.dataset.add_frame({
                    "observation.state": torch.tensor(obs["joint_positions"], dtype=torch.float32),
                    "action": torch.tensor(action, dtype=torch.float32),
                    "observation.images.wrist": self._process_image(obs["wrist_rgb"]),
                    "observation.images.base": self._process_image(obs["base_rgb"]),
                    "task": self.task_name,
                })

        elif state == "save":
            # 录制进行中，每帧持续写入。add_frame 仅缓存到内存，不落盘，
            # 视频帧写入临时目录，需等 save_episode() 才完成编码。
            if self.is_recording:
                self.dataset.add_frame({
                    "observation.state": torch.tensor(obs["joint_positions"], dtype=torch.float32),
                    "action": torch.tensor(action, dtype=torch.float32),
                    "observation.images.wrist": self._process_image(obs["wrist_rgb"]),
                    "observation.images.base": self._process_image(obs["base_rgb"]),
                    "task": self.task_name,
                })

        elif state == "normal" and self.is_recording:
            # Q 键按下时触发。将本 Episode 的缓存数据编码落盘（视频编码在此阶段完成，
            # 可能耗时数秒），然后重置录制标志回到待机。
            print("[LeRobot] ⏹️ 保存当前 Episode (编码视频中)...")
            self.dataset.save_episode()
            self.is_recording = False
            # 视频保存完后，再报一次平安
            print(f"[LeRobot] ✅ 保存成功！当前数据集总共包含 【{self.dataset.num_episodes}】 条轨迹。")

        elif state == "quit":
            # Esc 键按下时触发。若正在录制则先保存当前 Episode，再通知控制循环退出。
            if self.is_recording:
                print("[LeRobot] ⏹️ 保存当前 Episode (编码视频中)...")
                self.dataset.save_episode()
            print("[LeRobot] ✅ 退出程序。")
            return "quit"

        return None

def run_control_loop(
    env: RobotEnv,
    agent: Agent,
    save_interface: Optional[SaveInterface] = None,
    print_timing: bool = True,
    use_colors: bool = False,
) -> None:
    """Run the main control loop.

    Args:
        env: Robot environment
        agent: Agent for control
        save_interface: Optional save interface for data collection
        print_timing: Whether to print timing information
        use_colors: Whether to use colored terminal output
    """
    # Check if we can use colors
    colors_available = False
    if use_colors:
        try:
            from termcolor import colored

            colors_available = True
            start_msg = colored("\nStart 🚀🚀🚀", color="green", attrs=["bold"])
        except ImportError:
            start_msg = "\nStart 🚀🚀🚀"
    else:
        start_msg = "\nStart 🚀🚀🚀"

    print(start_msg)

    start_time = time.time()
    obs = env.get_obs()

    while True:
        if print_timing:
            num = time.time() - start_time
            message = f"\rTime passed: {round(num, 2)}          "

            if colors_available:
                print(
                    colored(message, color="white", attrs=["bold"]), end="", flush=True
                )
            else:
                print(message, end="", flush=True)

        action = agent.act(obs)

        # Handle save interface
        if save_interface is not None:
            result = save_interface.update(obs, action)
            if result == "quit":
                break

        obs = env.step(action)
