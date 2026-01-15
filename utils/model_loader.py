"""
LM Studio Model Loader - Automatically loads models on startup.
Uses LM Studio's REST API v0 for model management.
"""
import httpx
from config import config

LMS_BASE_URL = "http://localhost:1234"


async def ensure_models_loaded():
    """
    Ensure the required models are loaded in LM Studio.
    Uses the LM Studio REST API v0 endpoints.
    """
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Check what models are available
            models_resp = await client.get(f"{LMS_BASE_URL}/api/v0/models")
            if models_resp.status_code != 200:
                print(f"⚠ Could not fetch models list: {models_resp.status_code}")
                return False
            
            available = models_resp.json()
            print(f"Available models: {[m.get('id') or m.get('path') for m in available.get('data', [])]}")
            
            # Check loaded models
            loaded_resp = await client.get(f"{LMS_BASE_URL}/api/v0/models/loaded")
            if loaded_resp.status_code == 200:
                loaded = loaded_resp.json()
                loaded_ids = [m.get('id') for m in loaded.get('data', [])]
                print(f"Currently loaded: {loaded_ids}")
            else:
                loaded_ids = []
            
            # Load chat model
            chat_model = config.llm_model_name
            if chat_model not in loaded_ids:
                print(f"Loading chat model: {chat_model} (context: 30000)...")
                load_resp = await client.post(
                    f"{LMS_BASE_URL}/api/v0/models/load",
                    json={
                        "model": chat_model,
                        "context_length": 30000,
                    }
                )
                if load_resp.status_code == 200:
                    print(f"✓ Chat model loaded: {chat_model}")
                else:
                    print(f"⚠ Failed to load chat model: {load_resp.text}")
            else:
                print(f"✓ Chat model already loaded: {chat_model}")
            
            # Load embedding model
            embed_model = config.embedder_model_name
            if embed_model not in loaded_ids:
                print(f"Loading embedding model: {embed_model}...")
                load_resp = await client.post(
                    f"{LMS_BASE_URL}/api/v0/models/load",
                    json={"model": embed_model}
                )
                if load_resp.status_code == 200:
                    print(f"✓ Embedding model loaded: {embed_model}")
                else:
                    # Embeddings might auto-load on first use
                    print(f"⚠ Embedding model may auto-load on first use")
            else:
                print(f"✓ Embedding model already loaded: {embed_model}")
            
            return True
            
    except httpx.ConnectError:
        print("⚠ Cannot connect to LM Studio. Make sure it's running with the server enabled.")
        return False
    except Exception as e:
        print(f"⚠ Failed to load models: {e}")
        return False


def load_models_sync():
    """Synchronous wrapper for model loading."""
    import asyncio
    return asyncio.run(ensure_models_loaded())


if __name__ == "__main__":
    success = load_models_sync()
    if success:
        print("\n✓ All models ready!")
    else:
        print("\n✗ Model loading failed")
