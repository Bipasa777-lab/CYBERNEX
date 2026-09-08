import subprocess
import psutil
from app.schemas.security import SystemMetricsSchema
from app.core.logging import logger


class SystemMonitorService:
    def _get_gpu_usage(self) -> float:
        try:
            res = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=2.0
            )
            if res.returncode == 0 and res.stdout.strip():
                return float(res.stdout.strip().split("\n")[0])
        except Exception:
            pass
        return 0.0

    def get_status(self) -> SystemMetricsSchema:
        """
        Returns real-time system hardware metrics (CPU, Memory, Disk, GPU).
        """
        raw_cpu = psutil.cpu_percent(interval=None)
        cpu_val = float(raw_cpu[0]) if isinstance(raw_cpu, list) else float(raw_cpu)
        memory_info = psutil.virtual_memory()
        disk_info = psutil.disk_usage("/")
        gpu_usage = self._get_gpu_usage()

        return SystemMetricsSchema(
            cpuUsage=round(cpu_val, 1),
            memoryUsage=round(memory_info.percent, 1),
            storageUsage=round(disk_info.percent, 1),
            gpuUsage=gpu_usage,
            ragIndexingRate="Local Dynamic",
            activeAgents=0,
            totalDocuments=0,
            totalChunks=0
        )


system_monitor = SystemMonitorService()

