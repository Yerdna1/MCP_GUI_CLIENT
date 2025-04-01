import os
import ollama
from anthropic import Anthropic
from dotenv import load_dotenv

# Load .env specifically for potential Anthropic key
load_dotenv()

def select_llm_provider():
    """Prompts the user to select an LLM provider (Ollama or Anthropic)."""
    print("\nSelect LLM Provider:")
    print("1. Ollama (Local)")
    print("2. Anthropic (Claude API)")
    while True:
        choice = input("Select provider (1-2): ")
        if choice == '1':
            return 'ollama'
        elif choice == '2':
            return 'anthropic'
        else:
            print("Invalid choice.")

def select_ollama_model(default_model='mistral:latest'):
    """Lists available Ollama models and prompts the user to select one."""
    selected_model = default_model
    try:
        ollama_list_response = ollama.list()
        print(f"DEBUG: Ollama list() response structure: {ollama_list_response}")
        available_ollama_models_info = ollama_list_response.get('models', [])

        if not available_ollama_models_info:
            print(f"Warning: No Ollama models found or 'models' key missing. Using default '{default_model}'. Ensure Ollama is running and models are pulled.")
            return selected_model # Return default if none found
        else:
            available_ollama_models = [m['model'] for m in available_ollama_models_info]
            print("\nAvailable Ollama Models:")
            for i, model_name in enumerate(available_ollama_models):
                print(f"{i + 1}. {model_name}")

            while True:
                try:
                    model_choice = input(f"Select an Ollama model (1-{len(available_ollama_models)}, press Enter for default '{default_model}'): ")
                    if not model_choice:
                        break # User pressed Enter, keep default
                    index = int(model_choice) - 1
                    if 0 <= index < len(available_ollama_models):
                        selected_model = available_ollama_models[index]
                        break # Valid choice made
                    else:
                        print("Invalid choice.")
                except ValueError:
                    print("Invalid input. Please enter a number or press Enter.")
            print(f"Using Ollama model: {selected_model}")
            return selected_model

    except Exception as e:
        print(f"Error listing Ollama models: {e}. Using default '{default_model}'.")
        return selected_model # Return default on error

def initialize_anthropic_client(default_model="claude-3-5-sonnet-20240620"):
    """Initializes the Anthropic client, prompting for API key if needed."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        load_dotenv(override=True) # Ensure .env is loaded
        api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        api_key = input("Enter your Anthropic API Key: ").strip()
        if not api_key:
            print("Anthropic API Key is required.")
            return None, None # Return None if key is missing

    try:
        client = Anthropic(api_key=api_key)
        print(f"Anthropic client initialized. Using model: {default_model}")
        return client, default_model
    except Exception as e:
        print(f"Failed to initialize Anthropic client: {e}")
        return None, None

def ensure_llm_provider_ready(provider, ollama_model, anthropic_client):
    """Checks if the selected LLM provider is ready to use."""
    if provider == 'ollama':
        try:
            ollama.list()
            print("Ollama connection successful.")
            return True
        except Exception as e:
            print(f"Error: Could not connect to Ollama. Please ensure it's running. Error: {e}")
            return False
    elif provider == 'anthropic':
        if not anthropic_client:
            print("Error: Anthropic client not initialized.")
            return False
        # Add a simple API ping here if desired, e.g., list models (might incur cost)
        return True
    return False
