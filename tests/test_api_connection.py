"""
Test Anthropic API connection
"""
from anthropic import Anthropic
import json
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def load_config():
    """Load configuration file"""
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.json")
    if not os.path.exists(config_path):
        print("[ERROR] Config file not found!")
        print("Please copy config/config.example.json to config/config.json and fill in your API Key")
        return None
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def test_api_connection():
    """Test if API connection is working"""
    config = load_config()
    if not config:
        return False
    
    api_key = config.get("api_key")
    if not api_key or api_key == "your-api-key-here":
        print("[ERROR] Please fill in your API Key in config/config.json")
        return False
    
    try:
        client = Anthropic(api_key=api_key)
        
        # Try using common model names
        model = config.get("model", "claude-3-5-sonnet-20240620")
        
        # Send a simple test request
        response = client.messages.create(
            model=model,
            max_tokens=100,
            messages=[
                {
                    "role": "user",
                    "content": "Please reply 'API connection successful' and tell me today's date."
                }
            ]
        )
        
        print("[SUCCESS] API connection successful!")
        print(f"Model used: {model}")
        # Safely print response to avoid Windows encoding issues
        try:
            response_text = response.content[0].text
            print(f"Response: {response_text}")
        except UnicodeEncodeError:
            # If encoding fails, use ASCII-safe method
            response_text = response.content[0].text.encode('ascii', 'ignore').decode('ascii')
            print(f"Response: {response_text}")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"[ERROR] API connection failed: {error_msg}")
        # If model name is wrong, provide suggestions
        if "not_found" in error_msg or "404" in error_msg:
            print("\nHint: Model name might be incorrect.")
            print("Common model names:")
            print("  - claude-3-5-sonnet-20240620")
            print("  - claude-3-opus-20240229")
            print("  - claude-3-sonnet-20240229")
            print("  - claude-3-haiku-20240307")
            print("\nPlease set the correct 'model' field in config/config.json")
        return False

if __name__ == "__main__":
    test_api_connection()
