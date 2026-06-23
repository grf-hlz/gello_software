# GELLO + UR5 + LeRobot V3.0 遥操作与数据采集全指南

github：https://github.com/wuphilipp/gello_software
http://www.rosrobot.cn/?tags=123

## 阶段一：基础环境与依赖配置 (Conda版)

官方推荐使用 uv，但我们可以完全使用更熟悉的 conda 来搭建隔离环境。

### 1. 克隆代码库
```bash
git clone https://github.com/wuphilipp/gello_software.git
cd gello_software
git submodule init
git submodule update
```

### 2. 创建 Conda 虚拟环境
（GELLO 官方要求 Python 3.11）
```bash
conda create -n gello_env python=3.11 -y
conda activate gello_env
```

### 3. 安装基础与核心依赖
```bash
pip install -r requirements.txt
# 安装 gello 本身
pip install -e .
# 安装 Dynamixel 电机 SDK
pip install -e third_party/DynamixelSDK/python
```

### 4. 安装 UR5 与 LeRobot 专属依赖
```bash
pip install ur_rtde    # UR机械臂通信库
pip install lerobot    # VLA数据格式与处理库
```

## 阶段二：GELLO 主端与 UR5 硬件对齐校准

你不需要管说明书里的 YAM 或 CAN 总线内容，UR5 走的是网线 TCP/IP。第一步是让系统知道你的 GELLO 控制器的“物理零位”偏差，也就是获取关节偏移量 (Offsets)

### 1. 摆放姿态
将你的 GELLO 主端和真实的 UR5 手动摆成互相匹配的基准姿态（0 -90 90 -90 -90 0度，参考官方文档配图）。
- **软件上**：不需要开 UR5 的控制节点。
- **硬件上**：打开你真实 UR5 的示教器（控制器屏幕）。

用示教器手动把真实的 UR5 移动到这组关节角度：0, -90度, 90度, -90度, -90度, 0 （这对应弧度就是 0, -1.57, 1.57, -1.57, -1.57, 0）。
UR5 停在这个完美标准姿态后，把它当成一个参照物（模特）。
把你手里的 GELLO 主端，照着旁边真实的 UR5，一点点掰，掰得跟它一模一样。
在电脑上运行校准脚本获取 Offset。

**注意！！！**：因为 Linux 系统默认不允许普通用户（xiaohei）直接读取 USB 串口设备。由于拿不到权限，GELLO 程序不仅没有报错退出，反而自动切换成了“虚拟假手（fake Dynamixel driver）”模式。所以不管你现实中怎么掰动把手，程序发给 UR5 的都是一堆虚拟的死数据，UR5 自然一动不动。

**解决方法**
你有两种方法解决这个权限问题，推荐先用方法一快速测试，之后再用方法二一劳永逸。

**方法一：临时解决（立即生效，重启电脑后失效）**
在你的终端里（不管哪个终端），输入以下命令，强行给这个 USB 端口赋予读写权限：先找到连接你 GELLO 的 USB 端口号（终端输入 `ls /dev/serial/by-id`）
```bash
sudo chmod 666 /dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_FTBTJFYI-if00-port0
```
*如果用这个方法，那就得再每次重启（包括电脑或者主臂）的时候都要输入这个命令*

**方法二：永久解决（官方推荐方法）**
为了避免以后每次插拔 USB 或重启电脑都要输密码，你可以把你的当前用户加入到串口通信的 `dialout` 组中。
运行以下命令：
```bash
sudo usermod -aG dialout $USER
```
*注意：这个命令执行后不会立刻生效。你必须注销（Log out）当前电脑账号并重新登录，或者直接重启一下电脑！*
重启之后，以后你运行 GELLO 就再也不会遇到权限拒绝的问题了。

### 2. 运行校准脚本获取 Offsets
运行校准脚本：找到连接你 GELLO 的 USB 端口号（终端输入 `ls /dev/serial/by-id`），然后运行以下命令。请注意，UR 机械臂的初始关节角度设定为 `0 -1.57 1.57 -1.57 -1.57 0`，关节符号（Joint Signs）需设置为 `1 1 -1 1 1 1`；运行：
```bash
python scripts/gello_get_offset.py \
    --start-joints 0 -1.57 1.57 -1.57 -1.57 0 \
    --joint-signs 1 1 -1 1 1 1 \
    --port /dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_FTBTJFYI-if00-port0#你的USB端口标识
```

### 3. 填入配置文件
终端会输出一组关节偏移量和夹爪最大开合数值（Joint Offsets）。获取到偏移量后，你需要让系统记录这些数据：打开代码文件 `gello/agents/gello_agent.py`，找到 `PORT_CONFIG_MAP` 字典的 `Left UR`，将你的USB 端口号、`joint_signs` (1 1 -1 1 1 1) 以及刚刚生成的偏移量和夹爪最大开合填进去。

### **启动之前：**
Robotiq 夹爪有一个硬件特性：每次断电重启后，必须先发送一次“激活（Activate）”指令。在激活过程中，它会自动缓慢闭合到底，再完全张开，以此来校准行程。如果没有激活，你给它发任何位置指令，它都会装死不动。
在 GELLO 的源码里，原作者可能为了自己平时重启程序时不用每次都等夹爪缓慢校准，把激活夹爪的那行代码给注释掉了！

**修复步骤**
**第一步：修改 ur.py 开启激活机制**
打开文件 `gello/robots/ur.py`。
找到第 28 行到 30 行左右，在 `__init__` 函数里，原始代码是这样的：
```python
            self.gripper.connect(hostname=robot_ip, port=63352)
            print("gripper connected")
            # gripper.activate() 
```
把最后一行注释取消掉，并加上 `self.` 前缀（因为它是类属性），改成这样：
```python
            self.gripper.connect(hostname=robot_ip, port=63352)
            print("gripper connected")
            self.gripper.activate()  # 取消注释，并加上 self.
```

### 4. 启动遥操作
在正式遥操作时，你需要开启两个独立的终端窗口，并确保两个终端都激活了之前创建的虚拟环境（`conda activate gello_env`）。

**终端 1：启动 UR5 机器人节点**
这个节点负责与真实的 UR5 机械臂建立网络通信。请将下方的 IP 地址替换为你 UR5 的实际 IP：
```bash
python experiments/launch_nodes.py --robot ur --robot_ip 192.168.12.4
```
*(注：`--robot ur` 指定了真实硬件，`--robot_ip` 用于传入你 UR5 的真实局域网 IP 地址。)*

**终端 2：启动 GELLO 控制器**
当机器人节点成功启动并连接后，在第二个终端启动你的 GELLO 主端控制器：
```bash
python experiments/run_env.py --agent=gello
```
*(若有需要，你可以附加 `--start-joints` 参数来指定 GELLO 的启动配置，以便系统在复位时自动对齐。)*

执行完上述操作后，你就可以通过转动 GELLO 主端来实时遥操作真实的 UR5 机械臂了。如果在操作中发现某个关节的转动方向是反的，可以在配置文件或 `gello_agent.py` 中将对应关节的符号（Joint Sign）反转（即 1 改为 -1，或反之）即可解决。

## 阶段三：双相机 (D435 + D415) 硬核防错绑定

官方原始代码存在“瞎分配端口”的缺陷，每次插拔 USB 都可能导致“全局”和“腕部”画面错乱。我们需要做物理序列号硬绑定。

### 1. 获取相机序列号 (Serial Number)
分别插上 D415 和 D435，运行：
```bash
python gello/cameras/realsense_camera.py
```
终端会打印出类似 `['239122070951', '204222068556']` 的设备号。弄清楚哪个是 D415，哪个是 D435。如果不确定，可以拔掉一个再运行一次看看剩哪个。

### 2. 修改 launch_camera_nodes.py 代码
打开 `experiments/launch_camera_nodes.py`，将内容完全替换为以下防错代码：

```python
#我们直接去掉了原始代码里那种不可靠的“自动按顺序分配”逻辑，改成了一个硬编码的字典 CAMERA_MAP。这样无论你插入 USB 的顺序是什么，D415 的画面永远只会推送到 5000 端口，D435 的画面永远只会推送到 5001 端口。你的数据采集也就绝对不会乱了。
from dataclasses import dataclass
from multiprocessing import Process
import tyro
from gello.cameras.realsense_camera import RealSenseCamera
from gello.zmq_core.camera_node import ZMQServerCamera

@dataclass
class Args:
    # ⚠️ 强烈注意：原文件里写的是 128.32.175.167。
    # 除非这是你这台电脑的真实局域网IP，否则如果你是在本机运行，一定要改成 127.0.0.1 或者 0.0.0.0！
    hostname: str = "127.0.0.1"  # 强制绑定本地

def launch_server(port: int, camera_id: str, args: Args):
    # 这里传入具体的 Serial Number (camera_id) 让相机开启
    camera = RealSenseCamera(device_id=camera_id)
    server = ZMQServerCamera(camera, port=port, host=args.hostname)
    print(f"Starting camera server on port {port} for device {camera_id}")
    server.serve()

def main(args):
    # ==========================================
    # 在此硬编码你的设备号，彻底杜绝端口乱序！
    # ==========================================
    CAMERA_MAP = {
        "你的D415序列号": 5000,  # 强制绑定给腕部 (wrist)
        "你的D435序列号": 5001   # 强制绑定给全局 (base)
    }
    
    camera_servers = []
    for camera_id, camera_port in CAMERA_MAP.items():
        camera_servers.append(Process(target=launch_server, args=(camera_port, camera_id, args)))

    for server in camera_servers:
        server.start()
    for server in camera_servers:
        server.join()

if __name__ == "__main__":
    main(tyro.cli(Args))
```
    
## 阶段四：无缝接入 LeRobot V3.0 (核心代码改造)

这是整套系统最精华的部分：抛弃极耗内存的 .pkl 裸存方案，让采集到的画面直接被 LeRobot 压缩成 MP4 视频，动作压成 Parquet。

### 1. 修改启动入口，开启相机与替换保存类
打开 `experiments/run_env.py`：

**开启相机节点**： 在第 51 行左右，取消两行 `ZMQClientCamera` 的注释：
```python
camera_clients = {
    "wrist": ZMQClientCamera(port=args.wrist_camera_port, host=args.hostname),
    "base": ZMQClientCamera(port=args.base_camera_port, host=args.hostname),
}
```
并且在`experiments/run_env.py`文件开头输入
```python
from gello.zmq_core.camera_node import ZMQClientCamera
```
我们需要让启动脚本支持 --task-name 参数。打开 experiments/run_env.py。滚动到文件顶部的 class Args:
```python
@dataclass
class Args:
    # ... （上面是原有的其他参数）

    # 新增下面这一行
    task_name: str = "UR5 Teleoperation Task"
```

**替换录制逻辑**： 在文件末尾的 `if args.use_save_interface:` 处：
```python
# 2. 找到文件末尾关于 use_save_interface 的部分，修改如下：
# 原始代码是：
# if args.use_save_interface:
#     save_interface = SaveInterface(...)

# 改为引入我们自定义的 LeRobot 接口：
save_interface = None
if args.use_save_interface:
    from gello.utils.control_utils import LeRobotSaveInterface 
    save_interface = LeRobotSaveInterface(
        repo_id="local/ur5_lerobot_dataset", 
        fps=30,
        task_name=args.task_name  # <--- 新增这行，把参数传给保存接口
    )
run_control_loop(env, agent, save_interface, use_colors=True)
```
### 1.1 修改gello/data_utils/keyboard_interface.py文件
找到`class KBReset:`在这基础上替换为以下内容
```python
KEY_QUIT_PROGRAM = pygame.K_ESCAPE

class KBReset:
    def __init__(self):
        pygame.init()
        self._screen = pygame.display.set_mode((800, 800))
        self._set_color(NORMAL)
        self._saved = False

    def update(self) -> str:
        pressed_last = self._get_pressed()

        # Esc：退出整个程序（优先级最高）
        if KEY_QUIT_PROGRAM in pressed_last:
            self._saved = False
            return "quit"

        # Q：停止当前录制，回到待机状态
        if KEY_QUIT_RECORDING in pressed_last:
            self._set_color(RED)
            self._saved = False
            return "normal"

        if self._saved:
            return "save"

        # S：开始录制一个新 Episode
        if KEY_START in pressed_last:
            self._set_color(GREEN)
            self._saved = True
            return "start"

        self._set_color(NORMAL)
        return "normal"

    def _get_pressed(self):
        pressed = []
        pygame.event.pump()
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                pressed.append(event.key)
        return pressed

    def _set_color(self, color):
        self._screen.fill(color)
        pygame.display.flip()
```

### 2. 编写 LeRobotSaveInterface 采集类
打开 `gello/utils/control_utils.py`，在任意位置（如 `SaveInterface` 下方）新增此类：

```python
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
        
        ## 1. 定义特征空间严格定义，LeRobot 的特征空间 (终极完美版)
        joint_names = ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2", "wrist_3", "gripper_width"]
        # 图像的 names 恢复为正常的高、宽、通道
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
                print("\n[LeRobot] 🎥 开始录制新的 Episode...")
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

        elif state == "quit":
            # Esc 键按下时触发。若正在录制则先保存当前 Episode，再通知控制循环退出。
            if self.is_recording:
                print("[LeRobot] ⏹️ 保存当前 Episode (编码视频中)...")
                self.dataset.save_episode()
            print("[LeRobot] ✅ 退出程序。")
            return "quit"

        return None
```
        
## 阶段五：终极启动流程与操作实战

一切配置就绪！每次你准备开始遥操作采集数据时，请打开三个不同的终端（并分别运行 `conda activate gello_env`）：

**终端 1 (启动相机节点):**
```bash
python experiments/launch_camera_nodes.py
```

**终端 2 (连接真实 UR5 控制箱):**
```bash
python experiments/launch_nodes.py --robot ur --robot_ip 192.168.12.4
```

**终端 3 (启动 GELLO 主端与录制程序):**

先做这个步骤，解决 USB 串口权限问题：
```bash
sudo chmod 666 /dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_FTBTJFYI-if00-port0
```
检查下输出的参数与你gello_agent.py的Left UR里的参数是否一致
```bash
python scripts/gello_get_offset.py \
    --start-joints 0 -1.57 1.57 -1.57 -1.57 0 \
    --joint-signs 1 1 -1 1 1 1 \
    --port /dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_FTBTJFYI-if00-port0
```
执行遥操作主臂
```bash
python experiments/run_env.py --agent=gello --use-save-interface
```
**如果有多任务采集，那就在终端 3执行终极多任务流水线工作流：**

录制第一个任务（比如抓苹果）：
在终端输入：
```bash
python experiments/run_env.py --agent=gello --use-save-interface --task-name "pick up the apple"
```
开始疯狂按 S 和 Q 录制。录完 20 条后，直接按 Ctrl+C 强行退出程序。

秒切第二个任务（比如推盒子）：
不用换终端，不用清空数据，按一下键盘的 ↑ 键调出上一条命令，把后面改掉：

```bash
python experiments/run_env.py --agent=gello --use-save-interface --task-name "push the box"
```
程序瞬间启动，打印出 📂 发现已有数据集，开启【追加模式】。你继续按 S 和 Q 录制。

**遥操作采数动作规范：**
1. 采集流程如下：
2. 准备：将机械臂手动摆放到任务的初始位置。
3. 录制第一条：用鼠标点击一下 Pygame 灰色窗口（确保它在最前面），敲击一下 S 键并松开。看到窗口变绿，说明开始录制（Episode 1）。
4. 操作：双手握住 GELLO，控制 UR5 完成抓取任务。
5. 结束第一条：任务完成后，敲击一下 Q 键。看到窗口闪红变灰，说明 Episode 1 已经安全保存。
6. 复位：把机械臂重新摆回初始位置，准备下一次抓取。
7. 录制第二条：再次敲击一下 S 键，窗口变绿，现在正在录制 Episode 2。
8. 结束第二条：完成动作后，再次敲击 Q 键结束并保存。
9. 循环：重复上述过程，直到你录够了需要的数据（比如 50 条）。
10. 如要采集多个不同任务，那就跑多任务流水线工作流

## 阶段六：核心知识点与避坑解惑 (FAQ)

**Q1：为什么 5000 端口一定对应 Wrist (腕部) 相机？**
因为 GELLO 的主循环代码 `run_env.py` 开头硬编码了：`wrist_camera_port: int = 5000` 以及 `base_camera_port: int = 5001`。这决定了接收端去哪个端口拉数据，所以我们在 `launch_camera_nodes.py` 里必须让 D415 推流到 5000 端口。

**Q2：如何确认相机的帧率 (FPS) 和分辨率？**
在 GELLO 的 `gello/cameras/realsense_camera.py` 代码中，初始化配置已被写死：
`config.enable_stream(..., 640, 480, ..., 30)`。
因此，硬件实际输出的分辨率就是 640x480，帧率是 30。

**Q3：既然已经写死了，为什么还要在 LeRobot 接口里强调“严格匹配”？**
这是一种防御性编程的忠告。LeRobot 的 Shape 检查极其严苛。如果你未来嫌 640x480 不够清晰，跑去 `realsense_camera.py` 里改成了 1280x720，但忘记在 `LeRobotSaveInterface` 中同步把 shape 结构改为 `(3, 720, 1280)`，LeRobot 接收到图像时会立刻报错闪退，导致你采数的心血白费。

**Q4：在训练 VLA 前，需要给 D415 和 D435 做手眼标定吗？**
完全不需要，但有一个死规则！
现在的端到端 VLA（如 Pi0, OpenVLA, ACT）做的是“图像到动作的隐式映射（模仿学习）”，不需要明确的外参矩阵。
死规则是：相机的物理位置绝对、绝对不能动！
腕部相机必须用强力支架死死锁在机械臂末端；全局相机必须稳稳固定在桌子上。如果在采数期间或者测试期间相机被碰歪了哪怕一两厘米，模型学到的视觉映射就会彻底失效。(注：除非你未来玩 3D 点云驱动的模型，才需要用标定板做严格的手眼标定。)

