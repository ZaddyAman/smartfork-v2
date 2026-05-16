"""Ollama helper utilities for SmartFork v2."""

import shutil
import subprocess

from loguru import logger

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    ollama = None  # type: ignore[assignment]


def _start_ollama_server() -> bool:
    """Try to start the Ollama server in the background.

    Returns:
        True if server was started successfully, False otherwise.
    """
    if not shutil.which("ollama"):
        return False
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        logger.info("Started Ollama server in background")
        return True
    except Exception as e:
        logger.error(f"Failed to start Ollama server: {e}")
        return False


def check_ollama_available(model: str) -> bool:
    """Check if Ollama is installed, running, and has the model pulled.

    Args:
        model: The model name to check for.

    Returns:
        True if Ollama is running and model is available, False otherwise.
    """
    if not OLLAMA_AVAILABLE:
        logger.error("Ollama Python package is not installed. Install it with: pip install ollama")
        return False

    if not shutil.which("ollama"):
        logger.error(
            "Ollama binary not found. Install Ollama from https://ollama.com/download"
        )
        return False

    # Check if Ollama server is running
    try:
        assert ollama is not None
        response = ollama.list()
        model_list = response.models if hasattr(response, "models") else response.get("models", [])
        model_names = [m.model if hasattr(m, "model") else m.get("name", "") for m in model_list]
        # Strip tags for comparison (model can be "qwen2.5-coder:7b" or just "qwen2.5-coder")
        model_base = model.split(":")[0]
        for name in model_names:
            if not name:
                continue
            if name == model or name.startswith(model_base):
                return True
        logger.warning(f"Model '{model}' is not pulled. Pull it with: ollama pull {model}")
        return False
    except Exception:
        # Server not running — try auto-start
        logger.info("Ollama server not running, attempting to start...")
        if _start_ollama_server():
            import time
            time.sleep(2)  # Wait for server to boot
            try:
                assert ollama is not None
                response = ollama.list()
                model_list = response.models if hasattr(response, "models") else response.get("models", [])
                model_names = [m.model if hasattr(m, "model") else m.get("name", "") for m in model_list]
                model_base = model.split(":")[0]
                for name in model_names:
                    if not name:
                        continue
                    if name == model or name.startswith(model_base):
                        return True
                logger.warning(f"Model '{model}' is not pulled. Pull it with: ollama pull {model}")
                return False
            except Exception as e:
                logger.error(f"Ollama server started but still unreachable: {e}")
                return False
        else:
            logger.error(
                "Cannot connect to Ollama and failed to start it. Start it manually with: ollama serve"
            )
            return False


def ensure_ollama_model(model: str) -> None:
    """Ensure the Ollama model is available, pulling it if necessary.

    Args:
        model: The model name to ensure is available.

    Raises:
        RuntimeError: If Ollama is not available or model pull fails.
    """
    if not OLLAMA_AVAILABLE:
        raise RuntimeError(
            "Ollama Python package is not installed. "
            "Install it with: pip install ollama"
        )

    if not shutil.which("ollama"):
        raise RuntimeError(
            "Ollama binary not found. Install from: https://ollama.com/download"
        )

    try:
        assert ollama is not None
        # Check if model is already pulled
        response = ollama.list()
        model_list = response.models if hasattr(response, "models") else response.get("models", [])
        model_names = [m.model if hasattr(m, "model") else m.get("name", "") for m in model_list]
        if model in model_names:
            logger.info(f"Model '{model}' is already available.")
            return

        logger.info(f"Pulling model '{model}'... This may take a few minutes.")
        ollama.pull(model)
        logger.info(f"Model '{model}' pulled successfully.")
    except Exception as e:
        raise RuntimeError(
            f"Failed to pull model '{model}'. Is Ollama running? Start it with: ollama serve\n"
            f"Error: {e}"
        ) from e


def list_available_ollama_models() -> list[str]:
    """Return list of locally available Ollama model names.

    Returns:
        List of model name strings. Empty list if Ollama is unavailable.
    """
    if not OLLAMA_AVAILABLE or not shutil.which("ollama"):
        return []

    try:
        assert ollama is not None
        response = ollama.list()
        model_list = response.models if hasattr(response, "models") else response.get("models", [])
        return [m.model if hasattr(m, "model") else m.get("name", "") for m in model_list]
    except Exception:
        return []


def recommend_model() -> str:
    """Recommend the best available local model based on hardware.

    Returns:
        Recommended model name string.
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "qwen2.5-coder:7b"
        return "qwen3:0.6b"
    except ImportError:
        pass

    # Check for CUDA via nvidia-smi
    if shutil.which("nvidia-smi"):
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, check=True)
            return "qwen2.5-coder:7b"
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass

    # Check system RAM (rough heuristic)
    try:
        import psutil  # type: ignore[import-untyped]
        mem = psutil.virtual_memory()
        if mem.total < 8 * 1024**3:  # Less than 8 GB
            return "qwen3:0.6b"
    except ImportError:
        pass

    return "qwen2.5-coder:7b"  # Default for modern hardware
