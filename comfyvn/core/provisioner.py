from PySide6.QtGui import QAction

# comfyvn/core/provisioner.py
# [Phase 0.98] Unified Remote GPU Provisioner Framework
import json, os, subprocess, paramiko, httpx, logging
log = logging.getLogger(__name__)

class Provisioner:
    def __init__(self, provider:str, creds:dict):
        self.provider = provider; self.creds = creds
    def deploy(self): raise NotImplementedError
    def _save_endpoint(self, name, endpoint):
        os.makedirs("config", exist_ok=True)
        path = "config/remote_gpus.json"
        data = {"endpoints":[]}
        if os.path.exists(path):
            try: data=json.load(open(path))
            except Exception: pass
        data["endpoints"].append({"name":name,"endpoint":endpoint})
        json.dump(data, open(path,"w"), indent=2)
        log.info(f"[{self.provider}] endpoint registered: {endpoint}")

class RunPodProvisioner(Provisioner):
    def deploy(self):
        key=self.creds.get("api_key"); 
        if not key: raise RuntimeError("RunPod API key missing.")
        log.info("[RunPod] requesting pod ...")
        # Placeholder example (real API call omitted for brevity)
        return "https://runpod.example/8001"

class VastAIProvisioner(Provisioner):
    def deploy(self):
        log.info("[Vast.ai] provisioning instance ...")
        # Simplified sample logic
        return "http://vast.example:8001"

class LambdaProvisioner(Provisioner):
    def deploy(self):
        log.info("[Lambda] assuming SSH access ...")
        host=self.creds.get("host"); user=self.creds.get("user","ubuntu")
        ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=user, key_filename=self.creds.get("key"))
        cmds=[
            "sudo apt update -y",
            "sudo apt install -y docker.io git python3-venv",
            "git clone https://github.com/Megamjm/Comfyvn-ToolProject.git",
            "cd Comfyvn-ToolProject && ./run_server.sh &"
        ]
        for c in cmds:
            ssh.exec_command(c)
        ssh.close()
        return f"http://{host}:8001"

class AWSProvisioner(Provisioner):
    def deploy(self):
        log.info("[AWS] launching EC2 ...")
        return "http://aws.example:8001"

class UnraidProvisioner(Provisioner):
    def deploy(self):
        log.info("[Unraid] using local docker runner ...")
        subprocess.Popen(["docker","run","-d","-p","8001:8001","comfyvn/server:latest"])
        return "http://127.0.0.1:8001"

def provision_factory(provider, creds):
    mapping={
        "RunPod":RunPodProvisioner,
        "Vast.ai":VastAIProvisioner,
        "Lambda Labs":LambdaProvisioner,
        "AWS EC2":AWSProvisioner,
        "Unraid / LAN":UnraidProvisioner
    }
    cls=mapping.get(provider)
    if not cls: raise RuntimeError(f"No provisioner for {provider}")
    return cls(provider, creds)