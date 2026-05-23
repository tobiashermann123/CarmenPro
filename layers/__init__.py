"""
Public interface for all CarmenPro layers.
Downstream code imports only from here — never from sub-modules directly.
"""
# Layer 1 requires llama_index + vllm (GPU/MPS). Guard so other layers
# remain importable when those heavy deps are not installed.
try:
    from layers.layer1_foresight import run_for_pdf, run_for_sec_filing
    _layer1_available = True
except ImportError:
    _layer1_available = False

from layers.layer3_storage import get_client

__all__ = [
    "run_for_pdf",
    "run_for_sec_filing",
    "get_client",
]
