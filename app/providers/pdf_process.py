"""Run untrusted PDF parsing in a process that can be killed on timeout."""
import asyncio
import multiprocessing
import sys

from app.providers.documents import PDFExtractionError, extract_pdf, validate_pdf_bytes


def _windows_memory_limit(memory_mb):
    """Apply a per-process committed-memory ceiling using a Windows Job."""
    import ctypes
    from ctypes import wintypes

    class BasicLimits(ctypes.Structure):
        _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                    ("max_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [("basic", BasicLimits), ("io", IoCounters),
                    ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                    ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    job = kernel.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    limits.process_memory = memory_mb * 1024 * 1024
    if not job or not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
        raise OSError("Cannot set PDF parser memory limit.")
    if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
        raise OSError("Cannot isolate PDF parser memory.")
    # The child owns the handle until process exit.


def _parse_child(sender, data, memory_mb, timeout_seconds):
    try:
        if sys.platform != "win32":
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (int(timeout_seconds) + 1,) * 2)
        else:
            _windows_memory_limit(memory_mb)
        sender.send((True, extract_pdf(data)))
    except BaseException:
        # Never transfer exception objects or private parser diagnostics.
        sender.send((False, None))
    finally:
        sender.close()


async def extract_pdf_isolated(data, *, timeout_seconds=30, memory_mb=512):
    validate_pdf_bytes(data)
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_parse_child, args=(sender, data, memory_mb, timeout_seconds), daemon=True)
    try:
        process.start()
        sender.close()
        async with asyncio.timeout(timeout_seconds):
            while not receiver.poll():
                if not process.is_alive():
                    raise PDFExtractionError("PDF parser stopped before completing extraction.")
                await asyncio.sleep(0.02)
            ok, document = await asyncio.to_thread(receiver.recv)
        if not ok:
            raise PDFExtractionError("The PDF is unsupported or exceeds parsing resource limits.")
        return document
    except (TimeoutError, EOFError) as exc:
        raise PDFExtractionError("PDF extraction exceeded its resource limits.") from exc
    finally:
        sender.close()
        receiver.close()
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            await asyncio.to_thread(process.join, 5)
            if process.is_alive():
                process.kill()
                await asyncio.to_thread(process.join, 5)
            process.close()
