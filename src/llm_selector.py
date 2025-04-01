import os
import ollama
from anthropic import Anthropic
from dotenv import load_dotenv
import logging # Added logging

# Load .env specifically for potential Anthropic key
load_dotenv()

# Function to get available Ollama models
def get_ollama_models():
    """Lists available Ollama models."""
    try:
        ollama_list_response = ollama.list()
        logging.info(f"DEBUG: Ollama list() response structure: {ollama_list_response}")
        available_ollama_models_info = ollama_list_response.get('models', [])
        if not available_ollama_models_info:
            logging.warning("No Ollama models found or 'models' key missing.")
            return []
        else:
            # Correct key is 'model'
            available_ollama_models = [m['model'] for m in available_ollama_models_info]
            return available_ollama_models
    except Exception as e:
        logging.error(f"Error listing Ollama models: {e}.")
        return [] # Return empty list on error

# Function to initialize Anthropic client (takes key as argument)
def initialize_anthropic_client(api_key, default_model="claude-3-5-sonnet-20240620"):
    """Initializes the Anthropic client with a provided API key."""
    if not api_key:
        logging.error("Anthropic API Key was not provided.")
        return None, None
    try:
        client = Anthropic(api_key=api_key)
        logging.info(f"Anthropic client initialized. Using model: {default_model}")
        return client, default_model
    except Exception as e:
        logging.error(f"Failed to initialize Anthropic client: {e}")
        return None, None

# Function to check readiness (no changes needed)
def ensure_llm_provider_ready(provider, ollama_model, anthropic_client):
    """Checks if the selected LLM provider is ready to use."""
    if provider == 'ollama':
        try:
            ollama.list()
            logging.info("Ollama connection successful.")
            return True
        except Exception as e:
            logging.error(f"Error: Could not connect to Ollama. Please ensure it's running. Error: {e}")
            return False
    elif provider == 'anthropic':
        if not anthropic_client:
            logging.error("Error: Anthropic client not initialized.")
            return False
        return True
    return False
