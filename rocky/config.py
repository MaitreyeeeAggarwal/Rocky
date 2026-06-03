import os
import sys
import yaml
import asyncio
from enum import Enum
from pathlib import Path
from pydantic import BaseModel

class HardwareProfile(str, Enum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    FULL = "full"
    CPU_ONLY = "cpu_only"
    API_HOSTED = "api_hosted"

class EngineSettings(BaseModel):
    provider: str
    mode: str
    kv_cache_type: str
    default_num_ctx: int
    ram_disk_path: str
    thermal_threshold_c: int
    thermal_pause_seconds: int
    circuit_breaker_recovery_s: int

class GroqSettings(BaseModel):
    host: str
    timeout: int
    models: dict[str, str]

class OllamaSettings(BaseModel):
    host: str
    timeout: int
    models: dict[str, str]
    hardware_profiles: dict[str, dict]

class MemorySettings(BaseModel):
    root: str
    session_ttl_hours: int
    warm_ttl_days: int
    max_lines_per_file: int
    max_memory_file_size_kb: int

class SkillsSettings(BaseModel):
    root: str
    staging_dir: str
    archive_dir: str
    max_active_skills: int
    max_dispatch_rules: int
    dispatch_version_file: str

class HermesSettings(BaseModel):
    enabled: bool
    reflection_model: str
    auto_commit: bool
    commit_prefix: str
    max_retries: int

class SafetySettings(BaseModel):
    max_tool_calls_per_turn: int
    risk_levels: dict[str, list[str]]
    blocked_paths: list[str]

class CapabilityCeilingSettings(BaseModel):
    optimized_for: list[str]
    not_optimized_for: list[str]

class RockyConfig(BaseModel):
    version: str = "0.1.0"
    engine: EngineSettings
    groq: GroqSettings
    ollama: OllamaSettings
    memory: MemorySettings
    skills: SkillsSettings
    hermes: HermesSettings
    safety: SafetySettings
    capability_ceiling: CapabilityCeilingSettings

_config: RockyConfig | None = None

def is_wsl_environment() -> bool:
    """Detect if running under Windows Subsystem for Linux."""
    try:
        if os.path.exists("/proc/version"):
            with open("/proc/version", "r", encoding="utf-8") as f:
                content = f.read().lower()
                return "microsoft" in content or "wsl" in content
    except Exception:
        pass
    return False

def load_config(config_path: Path | str = "config.yaml") -> RockyConfig:
    global _config
    if _config is not None:
        return _config
    
    resolved_path = Path(config_path)
    if not resolved_path.exists():
        possible_roots = [
            Path(__file__).parent.parent / "config.yaml",
            Path.cwd() / "config.yaml",
            Path.cwd() / "rocky" / "config.yaml"
        ]
        for p in possible_roots:
            if p.exists():
                resolved_path = p
                break
                
    if not resolved_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
        
    with open(resolved_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    rocky_data = data.get("rocky", data)
    _config = RockyConfig(**rocky_data)
    
    if _config.engine.ram_disk_path and not is_wsl_environment():
        _config.engine.ram_disk_path = "" 
        
    return _config

def get_config() -> RockyConfig:
    if _config is None:
        return load_config()
    return _config

async def detect_hardware_profile() -> HardwareProfile:
    """
    §R.10 + §R.16: Multi-vendor fallback hardware detection chain.
    Never blocks the event loop (§R.13).
    """
    config = get_config()
    
    if config.engine.provider == "groq" and os.getenv("GROQ_API_KEY"):
        return HardwareProfile.API_HOSTED
        
    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0:
            total_vram = int(stdout.decode().strip().split('\n')[0])
            if total_vram >= 24000:
                return HardwareProfile.FULL
            elif total_vram >= 12000:
                return HardwareProfile.STANDARD
            else:
                return HardwareProfile.MINIMAL
    except Exception:
        pass

    try:
        proc = await asyncio.create_subprocess_exec(
            "rocm-smi", "--showmeminfo", "vram",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0:
            return HardwareProfile.STANDARD
    except Exception:
        pass

    return HardwareProfile.CPU_ONLY
