====================================
Intact JSON Generator - Usage Guide
====================================

## How to Run

### Method 1: Double-click to run (Recommended)
-------------------
1. Double-click "start.bat" file
2. Follow the prompts to enter document paths
3. Wait for the program to complete

### Method 2: Command line
-------------------
Open command line (PowerShell or CMD), navigate to AI_parse folder, then run:

```
python main.py --autoplus "document_path" --quote "document_path" --mvr "document_path" --application-form "document_path"
```

Example:
```
python main.py --autoplus "documents\autoplus\file.pdf" --quote "documents\quote\file.pdf"
```


## Steps to Use

1. Prepare documents
   - Have your documents ready (PDF, Word, or text files)
   - Remember the full path to each document

2. Run the program
   - Double-click "start.bat"
   - Enter document paths (you can drag and drop files into the command window)

3. View results
   - Generated JSON file will be saved in output\output.json
   - Open to view the generated content


## Supported Document Formats

- PDF files (.pdf)
- Word documents (.doc, .docx)
- Text files (.txt)


## Notes

1. Ensure API Key is configured
   - File: config\config.json
   - Replace "your-api-key-here" with your actual API Key

2. Ensure dependencies are installed
   - Run: pip install -r requirements.txt

3. At least one document path is required

4. Document paths can contain spaces, it's recommended to use quotes


## Common Issues

Q: "Python not found" error
A: Please install Python first and ensure Python is in system PATH

Q: "Config file not found" error
A: Copy config\config.example.json to config\config.json and fill in API Key

Q: "ModuleNotFoundError" error
A: Run pip install -r requirements.txt to install dependencies

Q: API call failed
A: Check if API Key is correct and network is working


## Output File

Generated JSON file is saved by default in: output\output.json

You can specify a different path using --output parameter:
```
python main.py --autoplus "file.pdf" --output "my_output.json"
```
