import time
from typing import Dict, Any
from app.core.config import get_settings
from app.core.logging import logger

try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None  # type: ignore

settings = get_settings()


class SandboxExecutor:
    def run_code(self, code: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Executes Python code inside an isolated Docker container with network disabled.
        If Docker is unavailable, returns SANDBOX_UNAVAILABLE without host execution fallback.
        """
        start_time = time.time()
        timeout = min(timeout, settings.SANDBOX_TIMEOUT_SECONDS)

        if not DOCKER_AVAILABLE or docker is None:
            return {
                "stdout": "",
                "stderr": "SANDBOX_UNAVAILABLE: Docker SDK is not installed or available.",
                "exit_code": -1,
                "duration": "0.0s",
                "status": "SANDBOX_UNAVAILABLE"
            }

        try:
            client = docker.from_env()
            client.ping()
        except Exception as e:
            logger.warning(f"Docker daemon ping failed: {e}")
            return {
                "stdout": "",
                "stderr": f"SANDBOX_UNAVAILABLE: Docker daemon is unreachable ({e}). Host execution fallback is strictly disabled.",
                "exit_code": -1,
                "duration": "0.0s",
                "status": "SANDBOX_UNAVAILABLE"
            }

        try:
            container = client.containers.run(
                image="python:3.11-slim",
                command=["python", "-c", code],
                detach=False,
                mem_limit="256m",
                nano_cpus=1000000000,  # 1 CPU
                network_disabled=True,
                timeout=timeout,
                remove=True
            )
            duration = f"{round(time.time() - start_time, 2)}s"
            stdout_str = container.decode("utf-8") if isinstance(container, bytes) else str(container)
            return {
                "stdout": stdout_str,
                "stderr": "",
                "exit_code": 0,
                "duration": duration,
                "status": "SUCCESS"
            }
        except Exception as e:
            errors_mod = getattr(docker, "errors", None)
            container_err = getattr(errors_mod, "ContainerError", None) if errors_mod else None
            if container_err and isinstance(e, container_err):
                duration = f"{round(time.time() - start_time, 2)}s"
                ce_err = getattr(e, "stderr", "")
                stderr_str = ce_err.decode("utf-8") if isinstance(ce_err, bytes) else str(ce_err)
                return {
                    "stdout": stderr_str,
                    "stderr": str(e),
                    "exit_code": getattr(e, "exit_status", -1),
                    "duration": duration,
                    "status": "ERROR"
                }
            logger.error(f"Docker execution error: {e}")
            duration = f"{round(time.time() - start_time, 2)}s"
            return {
                "stdout": "",
                "stderr": f"SANDBOX_UNAVAILABLE: Execution error - {e}",
                "exit_code": -1,
                "duration": duration,
                "status": "SANDBOX_UNAVAILABLE"
            }


sandbox_executor = SandboxExecutor()

