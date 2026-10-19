"""Structured JSON logging, Correlation ID propagation, and runtime telemetry metrics."""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
import sys
try:
    import resource
except ImportError:
    resource = None
import threading
import time
from typing import Any, Dict, Optional
import uuid

# Context variable holding the correlation ID for the current async execution context
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Return the active correlation ID or generate a fallback ID."""
    cid = correlation_id_ctx.get()
    if not cid:
        cid = f"req_{uuid.uuid4().hex[:12]}"
        correlation_id_ctx.set(cid)
    return cid


def set_correlation_id(cid: Optional[str] = None) -> str:
    """Set and return a correlation ID for the current async context."""
    clean_cid = (cid or "").strip() or f"req_{uuid.uuid4().hex[:12]}"
    correlation_id_ctx.set(clean_cid)
    return clean_cid


class StructuredJsonFormatter(logging.Formatter):
    """Formats Python log records into single-line structured JSON with correlation IDs."""

    RESERVED_ATTRS = {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "thread", "threadName", "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "correlation_id": correlation_id_ctx.get() or "system",
            "message": record.getMessage(),
        }

        # Merge extra structured attributes attached via logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_structured_logging(level: int = logging.INFO, json_output: bool = True) -> None:
    """Configure root logger with structured JSON formatting cleanly without duplicate handlers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
        )

    root_logger.handlers = [handler]


def get_process_memory_mb() -> Dict[str, float]:
    """Read current process RSS memory usage in MB using Linux /proc, Windows psapi, or resource module."""
    rss_mb = 0.0
    try:
        statm_path = "/proc/self/statm"
        if os.path.exists(statm_path):
            with open(statm_path, "r", encoding="utf-8") as f:
                parts = f.read().split()
                if len(parts) >= 2:
                    page_size = os.sysconf("SC_PAGE_SIZE")
                    rss_bytes = int(parts[1]) * page_size
                    rss_mb = round(rss_bytes / (1024 * 1024), 2)
        elif sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            psapi = ctypes.windll.psapi
            kernel32 = ctypes.windll.kernel32
            psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
            psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            if psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb):
                rss_mb = round(pmc.WorkingSetSize / (1024 * 1024), 2)
        elif resource is not None:
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # On macOS ru_maxrss is bytes; on Linux it is kilobytes
            divisor = (1024 * 1024) if sys.platform == "darwin" else 1024
            rss_mb = round(usage / divisor, 2)
    except Exception:
        rss_mb = 0.0

    return {"rss_mb": rss_mb}


class TelemetryRegistry:
    """Thread-safe runtime metrics collector for HTTP requests and MCP tool executions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start_time = time.monotonic()
        self._started_at_iso = datetime.now(timezone.utc).isoformat()
        self._total_requests = 0
        self._active_requests = 0
        self._error_requests = 0
        self._timeout_requests = 0
        self._rate_limited_requests = 0

        self._tool_total = 0
        self._tool_success = 0
        self._tool_failure = 0
        self._tool_timeouts = 0
        self._tool_latency_sum_ms = 0.0
        self._per_tool: Dict[str, Dict[str, Any]] = {}

    def record_request_start(self) -> None:
        with self._lock:
            self._total_requests += 1
            self._active_requests += 1

    def record_request_end(
        self,
        status_code: int,
        timed_out: bool = False,
        rate_limited: bool = False,
    ) -> None:
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)
            if status_code >= 500 or timed_out:
                self._error_requests += 1
            if timed_out:
                self._timeout_requests += 1
            if rate_limited or status_code == 429:
                self._rate_limited_requests += 1

    def record_tool_execution(
        self,
        tool_name: str,
        success: bool,
        latency_ms: float,
        timed_out: bool = False,
    ) -> None:
        with self._lock:
            self._tool_total += 1
            self._tool_latency_sum_ms += latency_ms
            if success:
                self._tool_success += 1
            else:
                self._tool_failure += 1
            if timed_out:
                self._tool_timeouts += 1

            entry = self._per_tool.setdefault(
                tool_name,
                {"calls": 0, "success": 0, "failed": 0, "timeouts": 0, "total_latency_ms": 0.0},
            )
            entry["calls"] += 1
            entry["total_latency_ms"] += latency_ms
            if success:
                entry["success"] += 1
            else:
                entry["failed"] += 1
            if timed_out:
                entry["timeouts"] += 1

    def snapshot(self) -> Dict[str, Any]:
        """Return a consistent snapshot of server uptime, memory, HTTP, and MCP tool metrics."""
        with self._lock:
            uptime_seconds = round(time.monotonic() - self._start_time, 2)
            total_tools = self._tool_total
            success_rate = (
                round((self._tool_success / total_tools) * 100.0, 2)
                if total_tools > 0
                else 100.0
            )
            fail_rate = (
                round((self._tool_failure / total_tools) * 100.0, 2)
                if total_tools > 0
                else 0.0
            )
            avg_tool_latency = (
                round(self._tool_latency_sum_ms / total_tools, 2)
                if total_tools > 0
                else 0.0
            )

            by_tool: Dict[str, Dict[str, Any]] = {}
            for t_name, stats in self._per_tool.items():
                calls = stats["calls"]
                by_tool[t_name] = {
                    "calls": calls,
                    "success": stats["success"],
                    "failed": stats["failed"],
                    "timeouts": stats["timeouts"],
                    "success_rate_percent": round((stats["success"] / calls) * 100.0, 2) if calls else 100.0,
                    "avg_latency_ms": round(stats["total_latency_ms"] / calls, 2) if calls else 0.0,
                }

            http_stats = {
                "total_requests": self._total_requests,
                "active_requests": self._active_requests,
                "error_requests": self._error_requests,
                "timeout_requests": self._timeout_requests,
                "rate_limited_requests": self._rate_limited_requests,
            }

        memory_info = get_process_memory_mb()
        return {
            "started_at": self._started_at_iso,
            "uptime_seconds": uptime_seconds,
            "memory": memory_info,
            "http_requests": http_stats,
            "tool_executions": {
                "total": total_tools,
                "success": self._tool_success,
                "failed": self._tool_failure,
                "timeouts": self._tool_timeouts,
                "success_rate_percent": success_rate,
                "failure_rate_percent": fail_rate,
                "avg_latency_ms": avg_tool_latency,
                "by_tool": by_tool,
            },
        }


telemetry = TelemetryRegistry()
