import os

MAX_CONCURRENT_RUNS = int(os.getenv("MAX_CONCURRENT_RUNS", "10"))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-6")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

AVAILABLE_MODELS = {
    "gpt-4o": {
        "id": "gpt-4o", "name": "GPT-4o",
        "provider": "openai", "max_tokens": 128000, "is_default": False,
    },
    "claude-sonnet-4-6": {
        "id": "claude-sonnet-4-6", "name": "Claude Sonnet 4.6",
        "provider": "anthropic", "max_tokens": 200000, "is_default": True,
    },
    "llama-3-70b": {
        "id": "llama-3-70b", "name": "Llama 3 70B",
        "provider": "bedrock", "max_tokens": 8192, "is_default": False,
    },
}
