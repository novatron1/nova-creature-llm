"""Conservative local media admission; observations are not model-fit promises."""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess

from .media_store import MediaStore


@dataclass(frozen=True)
class ResourceSnapshot:
    available_ram_bytes: int | None
    free_disk_bytes: int | None
    gpu_free_bytes: int | None
    measured_at: str


@dataclass(frozen=True)
class ReleaseResult:
    safe: bool
    unload_requested: bool
    stopped: bool
    before: ResourceSnapshot
    after: ResourceSnapshot
    reason: str


class ResourceGate:
    def __init__(self, root: Path, store: MediaStore):
        self.root = Path(root)
        self.store = store

    def snapshot(self) -> ResourceSnapshot:
        ram = disk = gpu = None
        try:
            import psutil
            ram = psutil.virtual_memory().available
            disk = shutil.disk_usage(self.root).free
        except (ImportError, OSError):
            pass
        try:
            result = subprocess.run(['nvidia-smi', '--query-gpu=memory.free', '--format=csv,noheader,nounits', '-i', '0'],
                                    capture_output=True, text=True, timeout=5,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            if result.returncode == 0:
                gpu = int(result.stdout.strip()) * 1024**2
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
        return ResourceSnapshot(ram, disk, gpu, datetime.now(timezone.utc).isoformat())

    def admit(self, estimated_temp_bytes: int, required_ram_bytes: int) -> tuple[bool, str]:
        quarantine = self.store.get_quarantine()
        if quarantine:
            return False, 'Resource cleanup requires reconciliation: ' + quarantine
        if type(required_ram_bytes) is not int or required_ram_bytes <= 0:
            return False, 'A measured memory profile is required before generation.'
        if type(estimated_temp_bytes) is not int or estimated_temp_bytes < 0:
            return False, 'Invalid temporary storage estimate.'
        observed = self.snapshot()
        if any(value is None for value in (observed.available_ram_bytes, observed.free_disk_bytes, observed.gpu_free_bytes)):
            return False, 'Resource availability could not be measured.'
        if observed.free_disk_bytes < estimated_temp_bytes + 10*1024**3:
            return False, 'Insufficient disk space: preserve 10 GiB free headroom.'
        if observed.available_ram_bytes < required_ram_bytes or observed.gpu_free_bytes <= 0:
            return False, 'Waiting for memory to meet the measured profile.'
        return True, 'Measured admission passed; model fit is not guaranteed.'

    def acquire(self, job_id: str) -> bool:
        return bool(job_id) and self.store.acquire_lease(job_id)

    def release(self, job_id: str) -> None:
        self.store.release_lease(job_id)
