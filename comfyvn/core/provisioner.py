from __future__ import annotations

import logging
import subprocess

import paramiko

from comfyvn.core.compute_registry import get_provider_registry

LOGGER = logging.getLogger(__name__)


class Provisioner:
    def __init__(self, provider: str, creds: dict):
        self.provider = provider
        self.creds = creds
        self.registry = get_provider_registry()

    def deploy(self):
        raise NotImplementedError

    def _save_endpoint(self, name: str, endpoint: str) -> None:
        """Persist the provisioned endpoint into the shared provider registry."""
        payload = {
            "name": name or self.provider,
            "service": self.provider.lower().replace(" ", "_"),
            "kind": "remote",
            "base_url": endpoint,
            "active": True,
        }
        entry = self.registry.register(payload)
        LOGGER.info("[%s] endpoint registered -> %s", self.provider, entry.get("id"))


class RunPodProvisioner(Provisioner):
    def deploy(self) -> str:
        key = self.creds.get("api_key")
        if not key:
            raise RuntimeError("RunPod API key missing.")
        LOGGER.info("[RunPod] requesting pod …")
        # Placeholder example (real API call omitted for brevity)
        endpoint = "https://runpod.example/8001"
        self._save_endpoint("RunPod", endpoint)
        return endpoint


class VastAIProvisioner(Provisioner):
    def deploy(self) -> str:
        LOGGER.info("[Vast.ai] provisioning instance …")
        endpoint = "http://vast.example:8001"
        self._save_endpoint("Vast.ai", endpoint)
        return endpoint


class LambdaProvisioner(Provisioner):
    def deploy(self) -> str:
        LOGGER.info("[Lambda] assuming SSH access …")
        host = self.creds.get("host")
        user = self.creds.get("user", "ubuntu")
        if not host:
            raise RuntimeError("Lambda provision requires host.")
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=host, username=user, key_filename=self.creds.get("key"))
        cmds = [
            "sudo apt update -y",
            "sudo apt install -y docker.io git python3-venv",
            "git clone https://github.com/Megamjm/Comfyvn-ToolProject.git",
            "cd Comfyvn-ToolProject && ./run_server.sh &",
        ]
        for cmd in cmds:
            ssh.exec_command(cmd)
        ssh.close()
        endpoint = f"http://{host}:8001"
        self._save_endpoint("Lambda Labs", endpoint)
        return endpoint


class AWSProvisioner(Provisioner):
    def deploy(self) -> str:
        LOGGER.info("[AWS] launching EC2 …")
        endpoint = "http://aws.example:8001"
        self._save_endpoint("AWS EC2", endpoint)
        return endpoint


class UnraidProvisioner(Provisioner):
    def deploy(self) -> str:
        LOGGER.info("[Unraid] using local docker runner …")
        subprocess.Popen(["docker", "run", "-d", "-p", "8001:8001", "comfyvn/server:latest"])
        endpoint = "http://127.0.0.1:8001"
        self._save_endpoint("Unraid / LAN", endpoint)
        return endpoint


def provision_factory(provider: str, creds: dict) -> Provisioner:
    mapping = {
        "RunPod": RunPodProvisioner,
        "Vast.ai": VastAIProvisioner,
        "Lambda Labs": LambdaProvisioner,
        "AWS EC2": AWSProvisioner,
        "Unraid / LAN": UnraidProvisioner,
    }
    cls = mapping.get(provider)
    if not cls:
        raise RuntimeError(f"No provisioner for {provider}")
    return cls(provider, creds)
