from comfyvn.lmstudio_client import healthcheck, sample_chat


def main() -> None:
    status = healthcheck()
    print(status)
    if status.get("ok") and status.get("models"):
        print(sample_chat())


if __name__ == "__main__":
    main()
