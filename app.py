import os
import threading
import time
import oci
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# 全局状态变量
sniper_thread = None
is_running = False
logs = []

def log_message(msg):
    timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
    full_msg = f"{timestamp} {msg}"
    print(full_msg)
    logs.append(full_msg)
    if len(logs) > 100:  # 只保留最近100条日志
        logs.pop(0)

def sniper_loop():
    global is_running
    log_message("🚀 抢机后台线程已启动...")
    
    # 从环境变量读取配置
    config = {
        "tenancy": os.getenv("OCI_TENANCY"),
        "user": os.getenv("OCI_USER"),
        "fingerprint": os.getenv("OCI_FINGERPRINT"),
        "region": os.getenv("OCI_REGION", "ap-singapore-1"),
        "key_content": os.getenv("OCI_PRIVATE_KEY")
    }
    
    compartment_id = os.getenv("OCI_COMPARTMENT_ID")
    subnet_id = os.getenv("OCI_SUBNET_ID")
    image_id = os.getenv("OCI_IMAGE_ID")
    availability_domain = os.getenv("OCI_AD")
    
    try:
        compute_client = oci.core.ComputeClient(config)
    except Exception as e:
        log_message(f"❌ 初始化 OCI 客户端失败: {e}")
        is_running = False
        return

    while is_running:
        log_message("⏳ 正在尝试创建 ARM VPS (4核 24G)...")
        
        shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=2,
            memory_in_gbs=12
        )

        launch_details = oci.core.models.LaunchInstanceDetails(
            compartment_id=compartment_id,
            availability_domain=availability_domain,
            display_name="oci-free-vps",
            shape="VM.Standard.A1.Flex",
            shape_config=shape_config,
            image_id=image_id,
            create_vnic_details=oci.core.models.CreateVnicDetails(
                subnet_id=subnet_id,
                assign_public_ip=True
            )
        )

        try:
            response = compute_client.launch_instance(launch_details)
            log_message("🎉🎉🎉 恭喜！VPS 创建请求成功！详情已发送。")
            log_message(str(response.data))
            is_running = False # 抢到后自动停止
            break
        except oci.exceptions.ServiceError as e:
            if "Out of host capacity" in e.message:
                log_message("❌ 库存不足 (Out of host capacity)，30秒后重试...")
            else:
                log_message(f"❌ 发生错误: {e.message}")
        except Exception as ex:
            log_message(f"❌ 未知异常: {ex}")
            
        # 等待 30 秒（期间每秒检查一次是否被手动停止）
        for _ in range(30):
            if not is_running:
                break
            time.sleep(1)

    log_message("🛑 抢机后台线程已停止。")

@app.route("/")
def index():
    return render_template("index.html", is_running=is_running)

@app.route("/status")
def status():
    return jsonify({"is_running": is_running, "logs": logs})

@app.route("/start", methods=["POST"])
def start_sniper():
    global sniper_thread, is_running
    if not is_running:
        is_running = True
        sniper_thread = threading.Thread(target=sniper_loop, daemon=True)
        sniper_thread.start()
        return jsonify({"status": "started", "message": "抢机任务已启动"})
    return jsonify({"status": "already_running", "message": "已经在运行中"})

@app.route("/stop", methods=["POST"])
def stop_sniper():
    global is_running
    if is_running:
        is_running = False
        return jsonify({"status": "stopped", "message": "正在停止任务..."})
    return jsonify({"status": "not_running", "message": "任务未在运行"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
