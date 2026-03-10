"""
GUI Application for Intact JSON Generator
Supports drag and drop documents
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import threading
from pathlib import Path

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.json_generator import IntactJSONGenerator


class DragDropFrame(ttk.Frame):
    """Frame with drag and drop functionality"""
    
    def __init__(self, parent, label_text, file_type="*"):
        super().__init__(parent, relief=tk.RAISED, borderwidth=2)
        self.file_path = None
        self.file_type = file_type
        self.label_text = label_text
        
        # Configure style
        self.configure(style="DropFrame.TFrame")
        
        # Label
        self.label = ttk.Label(
            self,
            text=label_text,
            font=("Arial", 10, "bold"),
            foreground="#666666"
        )
        self.label.pack(pady=10)
        
        # File path label
        self.path_label = ttk.Label(
            self,
            text="No file selected",
            font=("Arial", 9),
            foreground="#999999",
            wraplength=250
        )
        self.path_label.pack(pady=5, padx=10)
        
        # Browse button
        self.browse_btn = ttk.Button(
            self,
            text="Browse...",
            command=self.browse_file,
            width=15
        )
        self.browse_btn.pack(pady=5)
        
        # Bind drag and drop events
        self.bind("<Button-1>", self.on_click)
        self.label.bind("<Button-1>", self.on_click)
        self.path_label.bind("<Button-1>", self.on_click)
        self.browse_btn.bind("<Button-1>", lambda e: None)  # Prevent event propagation
        
        # Enable drag and drop
        self.drop_target_register("DND_Files")
        self.dnd_bind("<<Drop>>", self.on_drop)
        
        # Configure for drag and drop
        self.configure(cursor="hand2")
    
    def on_click(self, event):
        """Handle click to browse file"""
        self.browse_file()
    
    def browse_file(self):
        """Open file browser"""
        filetypes = [
            ("All supported", "*.pdf;*.doc;*.docx;*.txt"),
            ("PDF files", "*.pdf"),
            ("Word documents", "*.doc;*.docx"),
            ("Text files", "*.txt"),
            ("All files", "*.*")
        ]
        
        filename = filedialog.askopenfilename(
            title=f"Select {self.label_text}",
            filetypes=filetypes
        )
        
        if filename:
            self.set_file(filename)
    
    def on_drop(self, event):
        """Handle file drop"""
        files = self.tk.splitlist(event.data)
        if files:
            self.set_file(files[0])
    
    def set_file(self, file_path):
        """Set the file path and update display"""
        if os.path.exists(file_path):
            self.file_path = file_path
            filename = os.path.basename(file_path)
            self.path_label.config(
                text=filename,
                foreground="#2E7D32"
            )
            self.configure(style="DropFrameActive.TFrame")
        else:
            messagebox.showerror("Error", f"File not found: {file_path}")
    
    def get_file(self):
        """Get the selected file path"""
        return self.file_path
    
    def clear(self):
        """Clear the selected file"""
        self.file_path = None
        self.path_label.config(
            text="No file selected",
            foreground="#999999"
        )
        self.configure(style="DropFrame.TFrame")


class MultiFileDragDropFrame(ttk.Frame):
    """Frame with drag and drop functionality for multiple files"""
    
    def __init__(self, parent, label_text, file_type="*"):
        super().__init__(parent, relief=tk.RAISED, borderwidth=2)
        self.file_paths = []
        self.file_type = file_type
        self.label_text = label_text
        
        # Configure style
        self.configure(style="DropFrame.TFrame")
        
        # Label
        self.label = ttk.Label(
            self,
            text=label_text,
            font=("Arial", 10, "bold"),
            foreground="#666666"
        )
        self.label.pack(pady=10)
        
        # File listbox with scrollbar
        list_frame = ttk.Frame(self)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.path_listbox = tk.Listbox(
            list_frame,
            font=("Arial", 9),
            yscrollcommand=scrollbar.set,
            height=4
        )
        self.path_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.path_listbox.yview)
        
        # Placeholder label
        self.placeholder_label = ttk.Label(
            self,
            text="No files selected\n(Can select multiple)",
            font=("Arial", 9),
            foreground="#999999",
            wraplength=250
        )
        self.placeholder_label.pack(pady=5, padx=10)
        
        # Buttons frame
        buttons_frame = ttk.Frame(self)
        buttons_frame.pack(pady=5)
        
        # Browse button
        self.browse_btn = ttk.Button(
            buttons_frame,
            text="Browse...",
            command=self.browse_files,
            width=12
        )
        self.browse_btn.pack(side=tk.LEFT, padx=2)
        
        # Remove button
        self.remove_btn = ttk.Button(
            buttons_frame,
            text="Remove",
            command=self.remove_selected,
            width=12
        )
        self.remove_btn.pack(side=tk.LEFT, padx=2)
        
        # Bind drag and drop events
        self.bind("<Button-1>", self.on_click)
        self.label.bind("<Button-1>", self.on_click)
        self.placeholder_label.bind("<Button-1>", self.on_click)
        
        # Enable drag and drop
        self.drop_target_register("DND_Files")
        self.dnd_bind("<<Drop>>", self.on_drop)
        
        # Configure for drag and drop
        self.configure(cursor="hand2")
    
    def on_click(self, event):
        """Handle click to browse files"""
        self.browse_files()
    
    def browse_files(self):
        """Open file browser for multiple files"""
        filetypes = [
            ("All supported", "*.pdf;*.doc;*.docx;*.txt"),
            ("PDF files", "*.pdf"),
            ("Word documents", "*.doc;*.docx"),
            ("Text files", "*.txt"),
            ("All files", "*.*")
        ]
        
        filenames = filedialog.askopenfilenames(
            title=f"Select {self.label_text}",
            filetypes=filetypes
        )
        
        for filename in filenames:
            if filename and os.path.exists(filename):
                self.add_file(filename)
    
    def on_drop(self, event):
        """Handle file drop"""
        files = self.tk.splitlist(event.data)
        for file_path in files:
            if file_path and os.path.exists(file_path):
                self.add_file(file_path)
    
    def add_file(self, file_path):
        """Add a file to the list"""
        if file_path not in self.file_paths:
            self.file_paths.append(file_path)
            filename = os.path.basename(file_path)
            self.path_listbox.insert(tk.END, filename)
            
            # Hide placeholder, show listbox
            if len(self.file_paths) == 1:
                self.placeholder_label.pack_forget()
                self.path_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, before=self.placeholder_label)
            
            # Update style
            self.configure(style="DropFrameActive.TFrame")
    
    def remove_selected(self):
        """Remove selected file from list"""
        selection = self.path_listbox.curselection()
        if selection:
            index = selection[0]
            self.path_listbox.delete(index)
            self.file_paths.pop(index)
            
            # Show placeholder if no files
            if not self.file_paths:
                self.path_listbox.pack_forget()
                self.placeholder_label.pack(pady=5, padx=10)
                self.configure(style="DropFrame.TFrame")
    
    def get_files(self):
        """Get the selected file paths"""
        return self.file_paths.copy() if self.file_paths else None
    
    def clear(self):
        """Clear all selected files"""
        self.file_paths = []
        self.path_listbox.delete(0, tk.END)
        self.placeholder_label.pack(pady=5, padx=10)
        self.path_listbox.pack_forget()
        self.configure(style="DropFrame.TFrame")


class IntactJSONGeneratorGUI:
    """Main GUI application"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Intact JSON Generator")
        self.root.geometry("800x700")
        self.root.resizable(True, True)
        
        # Configure styles
        self.setup_styles()
        
        # Create canvas with scrollbar
        canvas = tk.Canvas(root, highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        def update_scrollregion(event=None):
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        scrollable_frame.bind("<Configure>", update_scrollregion)
        
        canvas_window = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        def configure_canvas_width(event):
            canvas_width = event.width
            canvas.itemconfig(canvas_window, width=canvas_width)
        
        canvas.bind("<Configure>", configure_canvas_width)
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel to canvas
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        
        # Create main container inside scrollable frame
        main_container = ttk.Frame(scrollable_frame, padding="20")
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            main_container,
            text="Intact JSON Generator",
            font=("Arial", 18, "bold"),
            foreground="#1976D2"
        )
        title_label.pack(pady=(0, 10))
        
        # Company selection frame
        company_frame = ttk.Frame(main_container)
        company_frame.pack(fill=tk.X, pady=(0, 10))
        
        company_label = ttk.Label(
            company_frame,
            text="Company:",
            font=("Arial", 11, "bold")
        )
        company_label.pack(side=tk.LEFT, padx=(0, 10))
        
        # Company dropdown
        self.company_var = tk.StringVar(value="CAA_Auto")
        company_options = ["Intact_Auto", "CAA_Auto", "CAA_property", "Aviva"]
        self.company_combo = ttk.Combobox(
            company_frame,
            textvariable=self.company_var,
            values=company_options,
            state="readonly",
            width=15,
            font=("Arial", 11)
        )
        self.company_combo.pack(side=tk.LEFT)
        self.company_combo.bind("<<ComboboxSelected>>", self.on_company_change)

        # Output directory selection
        output_dir_frame = ttk.Frame(main_container)
        output_dir_frame.pack(fill=tk.X, pady=(0, 10))

        output_dir_label = ttk.Label(
            output_dir_frame,
            text="Output Folder:",
            font=("Arial", 11, "bold")
        )
        output_dir_label.pack(side=tk.LEFT, padx=(0, 10))

        default_output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "output"))
        self.output_dir_var = tk.StringVar(value=default_output_dir)
        self.output_dir_entry = ttk.Entry(
            output_dir_frame,
            textvariable=self.output_dir_var,
            width=60
        )
        self.output_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        browse_output_btn = ttk.Button(
            output_dir_frame,
            text="Browse...",
            command=self.select_output_folder,
            width=12
        )
        browse_output_btn.pack(side=tk.LEFT)
        
        # Subtitle
        subtitle_label = ttk.Label(
            main_container,
            text="Drag and drop your documents or click to browse",
            font=("Arial", 10),
            foreground="#666666"
        )
        subtitle_label.pack(pady=(0, 20))
        
        # Document frames container
        docs_frame = ttk.Frame(main_container)
        docs_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Create 4 drag-drop frames in 2x2 grid
        self.autoplus_frame = MultiFileDragDropFrame(docs_frame, "Autoplus Document(s)")
        self.autoplus_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        
        self.quote_frame = DragDropFrame(docs_frame, "Quote Document")
        self.quote_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        
        self.mvr_frame = MultiFileDragDropFrame(docs_frame, "MVR Document(s)")
        self.mvr_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        
        self.app_form_frame = DragDropFrame(docs_frame, "Application Form")
        self.app_form_frame.grid(row=1, column=1, padx=10, pady=10, sticky="nsew")
        
        # Configure grid weights
        docs_frame.grid_columnconfigure(0, weight=1)
        docs_frame.grid_columnconfigure(1, weight=1)
        docs_frame.grid_rowconfigure(0, weight=1)
        docs_frame.grid_rowconfigure(1, weight=1)
        
        # Buttons frame
        buttons_frame = ttk.Frame(main_container)
        buttons_frame.pack(fill=tk.X, pady=20)
        
        # Generate button
        self.generate_btn = ttk.Button(
            buttons_frame,
            text="Generate JSON",
            command=self.generate_json,
            style="Action.TButton"
        )
        self.generate_btn.pack(side=tk.LEFT, padx=5)
        
        # Clear button
        clear_btn = ttk.Button(
            buttons_frame,
            text="Clear All",
            command=self.clear_all
        )
        clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(
            main_container,
            mode='indeterminate',
            length=400
        )
        self.progress.pack(pady=10)
        
        # Status label
        self.status_label = ttk.Label(
            main_container,
            text="Ready",
            font=("Arial", 9),
            foreground="#666666"
        )
        self.status_label.pack(pady=5)
        
        # Output text area
        output_label = ttk.Label(
            main_container,
            text="Output Log:",
            font=("Arial", 10, "bold")
        )
        output_label.pack(anchor=tk.W, pady=(10, 5))
        
        self.output_text = scrolledtext.ScrolledText(
            main_container,
            height=8,
            font=("Consolas", 9),
            wrap=tk.WORD
        )
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Initialize document frame visibility based on default company
        # Must be called after output_text is created
        self.on_company_change()
        
        # Configure root window for drag and drop
        try:
            import tkinterdnd2 as tkdnd
            root.drop_target_register(tkdnd.DND_FILES)
            root.dnd_bind('<<Drop>>', self.on_root_drop)
        except ImportError:
            self.log("Note: tkinterdnd2 not installed. Drag and drop from outside may not work.")
            self.log("You can still use the Browse buttons or drag files onto the frames.")
    
    def setup_styles(self):
        """Configure ttk styles"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Drop frame style
        style.configure("DropFrame.TFrame", background="#F5F5F5")
        style.map("DropFrame.TFrame",
                 background=[("active", "#E3F2FD")])
        
        # Active drop frame style
        style.configure("DropFrameActive.TFrame", background="#E8F5E9")
        
        # Action button style
        style.configure("Action.TButton",
                        font=("Arial", 11, "bold"),
                        padding=10)
    
    def on_root_drop(self, event):
        """Handle file drop on root window"""
        # This would need tkinterdnd2 for full functionality
        pass
    
    def log(self, message):
        """Add message to output log"""
        self.output_text.insert(tk.END, f"{message}\n")
        self.output_text.see(tk.END)
        self.root.update_idletasks()
    
    def on_company_change(self, event=None):
        """Handle company selection change"""
        selected_company = self.company_var.get()
        
        # Only log if output_text exists (avoid error during initialization)
        if hasattr(self, 'output_text'):
            self.log(f"Company changed to: {selected_company}")
        
        # Show/hide document frames based on company type
        is_property = selected_company.endswith("_property")
        
        if is_property:
            # Property type: only show quote and application
            self.autoplus_frame.grid_remove()
            self.mvr_frame.grid_remove()
            self.quote_frame.grid()
            self.app_form_frame.grid()
        else:
            # Auto type: show all 4 frames
            self.autoplus_frame.grid()
            self.quote_frame.grid()
            self.mvr_frame.grid()
            self.app_form_frame.grid()

    def select_output_folder(self):
        """Select output folder for generated JSON"""
        current_dir = self.output_dir_var.get().strip() or os.getcwd()
        selected_dir = filedialog.askdirectory(
            title="Select output folder for JSON",
            initialdir=current_dir if os.path.isdir(current_dir) else os.getcwd()
        )
        if selected_dir:
            self.output_dir_var.set(selected_dir)
            self.log(f"Output folder set to: {selected_dir}")
    
    def clear_all(self):
        """Clear all selected files"""
        self.autoplus_frame.clear()
        self.quote_frame.clear()
        self.mvr_frame.clear()
        self.app_form_frame.clear()
        self.output_text.delete(1.0, tk.END)
        self.status_label.config(text="Ready", foreground="#666666")
        self.log("All files cleared")
    
    def generate_json(self):
        """Generate JSON from selected documents"""
        # Get selected company
        selected_company = self.company_var.get()
        
        # Check if company output type is configured
        if selected_company == "Aviva":
            messagebox.showinfo(
                "Output Type Not Configured",
                "Output type not yet configured"
            )
            return
        
        # Check if property type
        is_property = selected_company.endswith("_property")
        
        if is_property:
            # Property type: only quote and application
            quote_path = self.quote_frame.get_file()
            app_form_path = self.app_form_frame.get_file()
            
            # Check if required files are selected
            if not quote_path or not app_form_path:
                messagebox.showwarning(
                    "Missing Documents",
                    "Please select both Quote Document and Application Form for property insurance."
                )
                return
            
            autoplus_paths = None
            mvr_paths = None
        else:
            # Auto type: all documents
            autoplus_paths = self.autoplus_frame.get_files()
            quote_path = self.quote_frame.get_file()
            mvr_paths = self.mvr_frame.get_files()
            app_form_path = self.app_form_frame.get_file()
            
            # Check if at least one file is selected
            if not any([autoplus_paths, quote_path, mvr_paths, app_form_path]):
                messagebox.showwarning(
                    "No Documents",
                    "Please select at least one document to generate JSON."
                )
                return
        
        # Disable button and start progress
        self.generate_btn.config(state=tk.DISABLED)
        self.progress.start()
        self.status_label.config(text="Processing...", foreground="#1976D2")
        self.output_text.delete(1.0, tk.END)
        self.log(f"Starting JSON generation for {selected_company}...")
        
        # Run in separate thread to prevent GUI freezing
        thread = threading.Thread(
            target=self._generate_json_thread,
            args=(autoplus_paths, quote_path, mvr_paths, app_form_path, selected_company)
        )
        thread.daemon = True
        thread.start()
    
    def _generate_json_thread(self, autoplus_paths, quote_path, mvr_paths, app_form_path, company):
        """Generate JSON in separate thread"""
        try:
            # Initialize generator
            self.log("Initializing generator...")
            generator = IntactJSONGenerator(company=company)
            
            # Generate JSON
            self.log(f"Generating JSON for {company}...")
            json_data = generator.generate_json(
                autoplus_paths=autoplus_paths,
                quote_path=quote_path,
                mvr_paths=mvr_paths,
                application_form_path=app_form_path,
                company=company
            )
            
            # Save JSON
            output_dir = self.output_dir_var.get().strip()
            if not output_dir:
                output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "output"))
            applicant_filename = generator.get_applicant_filename(json_data)
            output_path = os.path.join(output_dir, f"{applicant_filename}.json")
            output_path = generator.save_json(json_data, output_path)
            
            # Update UI in main thread
            self.root.after(0, self._generation_success, output_path)
            
        except Exception as e:
            error_msg = str(e)
            self.root.after(0, self._generation_error, error_msg)
    
    def _generation_success(self, output_path):
        """Handle successful generation"""
        self.progress.stop()
        self.generate_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Success!", foreground="#2E7D32")
        self.log(f"\n[SUCCESS] JSON generated successfully!")
        self.log(f"Output saved to: {os.path.abspath(output_path)}")
        
        # Ask if user wants to open the file
        result = messagebox.askyesno(
            "Success",
            f"JSON generated successfully!\n\nSaved to:\n{os.path.abspath(output_path)}\n\nDo you want to open the file?"
        )
        
        if result:
            os.startfile(output_path)
    
    def _generation_error(self, error_msg):
        """Handle generation error"""
        self.progress.stop()
        self.generate_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Error", foreground="#D32F2F")
        self.log(f"\n[ERROR] Generation failed: {error_msg}")
        messagebox.showerror("Error", f"Failed to generate JSON:\n\n{error_msg}")


def main():
    """Main entry point"""
    root = tk.Tk()
    app = IntactJSONGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
