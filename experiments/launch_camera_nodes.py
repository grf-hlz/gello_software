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
        "204222068556": 5000,  # 强制绑定给腕部 (wrist)
        "239122070951": 5001   # 强制绑定给全局 (base)
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