"""
Usage example - Demonstrate how to use JSON generator
"""
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.json_generator import IntactJSONGenerator

def example_usage():
    """Example: How to use JSON generator"""
    
    # Initialize generator
    generator = IntactJSONGenerator()
    
    # Specify document paths (modify according to actual situation)
    autoplus_path = "documents/autoplus/your_autoplus_file.pdf"
    quote_path = "documents/quote/your_quote_file.pdf"
    mvr_path = "documents/mvr/your_mvr_file.pdf"
    application_form_path = "documents/application_form/your_form_file.pdf"
    
    # Generate JSON
    try:
        json_data = generator.generate_json(
            autoplus_path=autoplus_path if os.path.exists(autoplus_path) else None,
            quote_path=quote_path if os.path.exists(quote_path) else None,
            mvr_path=mvr_path if os.path.exists(mvr_path) else None,
            application_form_path=application_form_path if os.path.exists(application_form_path) else None
        )
        
        # Save JSON
        output_path = "output/generated_output.json"
        generator.save_json(json_data, output_path)
        
        print(f"\nExample completed! Check {output_path}")
        
    except Exception as e:
        print(f"Error: {e}")
        print("\nPlease make sure:")
        print("1. Documents exist at the specified paths")
        print("2. API key is configured in config/config.json")
        print("3. All required dependencies are installed")

if __name__ == "__main__":
    example_usage()
