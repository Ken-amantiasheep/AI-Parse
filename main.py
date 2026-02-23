"""
Main program - Generate Intact upload JSON from documents
"""
import os
import sys
import argparse
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.json_generator import IntactJSONGenerator

def main():
    parser = argparse.ArgumentParser(
        description="Generate Intact upload JSON from documents"
    )
    
    parser.add_argument(
        "--autoplus",
        type=str,
        action="append",
        help="Path to Autoplus document (can be specified multiple times for multiple documents)"
    )
    parser.add_argument(
        "--quote",
        type=str,
        help="Path to Quote document"
    )
    parser.add_argument(
        "--mvr",
        type=str,
        action="append",
        help="Path to MVR document (can be specified multiple times for multiple drivers)"
    )
    parser.add_argument(
        "--application-form",
        type=str,
        dest="application_form",
        help="Path to Application Form document"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default="output/output.json",
        help="Output JSON file path (default: output/output.json)"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        help="Path to config file (default: config/config.json)"
    )
    
    args = parser.parse_args()
    
    # Check at least one document is provided
    autoplus_list = args.autoplus if args.autoplus else []
    mvr_list = args.mvr if args.mvr else []
    if not any([autoplus_list, args.quote, mvr_list, args.application_form]):
        print("[ERROR] At least one document path must be provided")
        print("\nUsage example:")
        print("  python main.py --autoplus path/to/autoplus.pdf --quote path/to/quote.pdf")
        print("  python main.py --mvr path/to/mvr1.pdf --mvr path/to/mvr2.pdf")
        parser.print_help()
        return
    
    try:
        # Initialize generator
        print("=" * 60)
        print("Intact JSON Generator")
        print("=" * 60)
        
        generator = IntactJSONGenerator(config_path=args.config)
        
        # Generate JSON
        json_data = generator.generate_json(
            autoplus_paths=autoplus_list if autoplus_list else None,
            quote_path=args.quote,
            mvr_paths=mvr_list if mvr_list else None,
            application_form_path=args.application_form
        )
        
        # Save JSON
        output_path = args.output
        generator.save_json(json_data, output_path)
        
        print("\n" + "=" * 60)
        print("[SUCCESS] Process completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Process failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
