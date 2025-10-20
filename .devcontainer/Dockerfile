// .devcontainer/devcontainer.json
// [ComfyVN_Architect | Devcontainer sanity check — 2025-10-20]
{
  "name": "ComfyVN Studio Suite",
  "build": { "dockerfile": "Dockerfile" }, // <- use the one in .devcontainer/
  "features": {
    "ghcr.io/devcontainers/features/node:1": { "version": "20" }
  },
  "postCreateCommand": "pip install -U pip && pip install -r requirements.txt",
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-toolsai.jupyter",
        "ms-python.vscode-pylance",
        "ms-azuretools.vscode-docker",
        "GitHub.copilot",
        "GitHub.copilot-chat",
        "openai.chatgpt"
      ],
      "settings": { "python.defaultInterpreterPath": "/usr/local/bin/python" }
    }
  },
  "forwardPorts": [8000, 8001, 8188, 1234],
  "portsAttributes": {
    "8000": { "label": "ComfyVN API" },
    "8001": { "label": "ComfyVN v1 API" },
    "8188": { "label": "ComfyUI" },
    "1234": { "label": "LM Studio" }
  },
  "remoteEnv": {
    "COMFYVN_ENV": "dev",
    "LMSTUDIO_BASE_URL": "http://host.docker.internal:1234"
  },
  // bind to the actual workspace folder, whatever VS Code names it
  "mounts": [
    "source=${localWorkspaceFolder}/data,target=${containerWorkspaceFolder}/data,type=bind"
  ],
  "overrideCommand": false,
  "runArgs": [] // enable GPU later: ["--gpus=all"]
}
