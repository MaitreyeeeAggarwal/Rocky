import asyncio
import logging
from datetime import datetime
from rocky.config import get_config

logger = logging.getLogger("rocky.thermal_monitor")

class ThermalMonitor:
    """
    Background daemon polling GPU temperature.
    §R.13: Never calls subprocess.run() — all nvidia-smi/rocm-smi calls use
    asyncio.create_subprocess_exec() to avoid blocking the event loop.
    Uses a cached-value pattern: the background poller writes to _last_temp,
    and check_and_pace() reads from cache (zero blocking, zero I/O).
    """
    def __init__(self):
        self.config = get_config()
        self._last_temp: float | None = None
        self._last_poll: datetime | None = None
        self._threshold = self.config.engine.thermal_threshold_c
        self._pause_s = self.config.engine.thermal_pause_seconds
        self._poll_task: asyncio.Task | None = None
        self._active = False

    async def start(self):
        """Launches the background polling task."""
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Thermal monitor started.")

    async def _poll_loop(self):
        """
        Background loop — runs for the lifetime of the session.
        Uses adaptive intervals: 30s when idle, 10s when active.
        """
        while True:
            try:
                interval = 10 if self._active else 30
                
                # Check for NVIDIA GPU temperature
                proc = await asyncio.create_subprocess_exec(
                    'nvidia-smi', '--query-gpu=temperature.gpu', '--format=csv,noheader,nounits',
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
                if proc.returncode == 0:
                    self._last_temp = float(stdout.decode().strip().split('\n')[0])
                    self._last_poll = datetime.now()
                else:
                    self._last_temp = None
            except asyncio.CancelledError:
                break
            except Exception:
                # AMD fallback or no-smi
                self._last_temp = None
            
            await asyncio.sleep(interval)

    async def check_and_pace(self):
        """
        Called before each worker invocation. Reads from cache only — NEVER
        spawns a subprocess. Zero latency on the worker path.
        """
        self._active = True
        
        if self._last_temp is None:
            return
            
        if self._last_temp > self._threshold:
            print(f"[*] GPU cooling needed — current temperature is {self._last_temp}°C (Threshold: {self._threshold}°C).")
            print(f"[*] Pausing worker dispatch for {self._pause_s} seconds...")
            await asyncio.sleep(self._pause_s)
            
            # Re-check temperature
            if self._last_temp and self._last_temp > self._threshold:
                logger.warning(f"GPU still hot after pause: {self._last_temp}°C. Proceeding cautiously.")

    def mark_idle(self):
        """Called after worker completes. Reduces poll frequency."""
        self._active = False

    async def stop(self):
        """Cancels background polling task on session end."""
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            logger.info("Thermal monitor stopped.")
