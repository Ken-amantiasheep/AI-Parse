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

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False
    print("Warning: tkinterdnd2 not available. Drag and drop will be disabled.")

from utils.json_generator import IntactJSONGenerator
from version import APP_VERSION
from app_update import run_startup_update_check


class DocumentDropFrame(tk.Frame):
    """Frame for document drop with visual feedback and drag & drop support"""
    
    def __init__(self, parent, label_text, row, col):
        super().__init__(parent, relief=tk.RAISED, borderwidth=2, bg="#F5F5F5")
        self.file_path = None
        self.label_text = label_text
        
        self.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
        
        # Configure for hover effect
        self.original_bg = "#F5F5F5"
        self.hover_bg = "#E3F2FD"
        self.active_bg = "#E8F5E9"
        self.drag_over_bg = "#FFF9C4"
        
        # Enable drag and drop if available
        if DND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self.on_drop)
            self.dnd_bind('<<DragEnter>>', self.on_drag_enter)
            self.dnd_bind('<<DragLeave>>', self.on_drag_leave)
        
        # Title label
        title_label = tk.Label(
            self,
            text=label_text,
            font=("Arial", 11, "bold"),
            bg=self.original_bg,
            fg="#333333",
            pady=15
        )
        title_label.pack()
        
        # Icon/placeholder
        icon_label = tk.Label(
            self,
            text="📄",
            font=("Arial", 32),
            bg=self.original_bg,
            fg="#999999"
        )
        icon_label.pack(pady=10)
        
        # File path label
        self.path_label = tk.Label(
            self,
            text="Click to select file",
            font=("Arial", 9),
            bg=self.original_bg,
            fg="#999999",
            wraplength=200,
            cursor="hand2"
        )
        self.path_label.pack(pady=5, padx=10)
        
        # Browse button
        self.browse_btn = tk.Button(
            self,
            text="Browse...",
            command=self.browse_file,
            bg="#2196F3",
            fg="white",
            font=("Arial", 9),
            relief=tk.FLAT,
            padx=20,
            pady=8,
            cursor="hand2",
            activebackground="#1976D2",
            activeforeground="white"
        )
        self.browse_btn.pack(pady=10)
        
        # Bind click events
        self.bind("<Button-1>", self.on_click)
        title_label.bind("<Button-1>", self.on_click)
        self.path_label.bind("<Button-1>", self.on_click)
        icon_label.bind("<Button-1>", self.on_click)
        
        # Bind hover events
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        title_label.bind("<Enter>", self.on_enter)
        title_label.bind("<Leave>", self.on_leave)
        icon_label.bind("<Enter>", self.on_enter)
        icon_label.bind("<Leave>", self.on_leave)
        self.path_label.bind("<Enter>", self.on_enter)
        self.path_label.bind("<Leave>", self.on_leave)
    
    def on_drop(self, event):
        """Handle file drop"""
        files = self.tk.splitlist(event.data)
        if files:
            file_path = files[0].strip('{}')  # Remove braces if present
            self.set_file(file_path)
    
    def on_drag_enter(self, event):
        """Handle drag enter - change background color"""
        self.config(bg=self.drag_over_bg)
        for widget in self.winfo_children():
            if isinstance(widget, tk.Label):
                widget.config(bg=self.drag_over_bg)
    
    def on_drag_leave(self, event):
        """Handle drag leave - restore background color"""
        if not self.file_path:
            self.config(bg=self.original_bg)
            for widget in self.winfo_children():
                if isinstance(widget, tk.Label):
                    widget.config(bg=self.original_bg)
    
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
    
    def set_file(self, file_path):
        """Set the file path and update display"""
        if os.path.exists(file_path):
            self.file_path = file_path
            filename = os.path.basename(file_path)
            self.path_label.config(
                text=filename,
                fg="#2E7D32"
            )
            self.config(bg=self.active_bg)
            for widget in self.winfo_children():
                if isinstance(widget, tk.Label):
                    widget.config(bg=self.active_bg)
        else:
            messagebox.showerror("Error", f"File not found: {file_path}")
    
    def on_enter(self, event):
        """Handle mouse enter"""
        if not self.file_path:
            self.config(bg=self.hover_bg)
            for widget in self.winfo_children():
                if isinstance(widget, tk.Label):
                    widget.config(bg=self.hover_bg)
    
    def on_leave(self, event):
        """Handle mouse leave"""
        if not self.file_path:
            self.config(bg=self.original_bg)
            for widget in self.winfo_children():
                if isinstance(widget, tk.Label):
                    widget.config(bg=self.original_bg)
    
    def get_file(self):
        """Get the selected file path"""
        return self.file_path
    
    def clear(self):
        """Clear the selected file"""
        self.file_path = None
        self.path_label.config(
            text="Click to select file",
            fg="#999999"
        )
        self.config(bg=self.original_bg)
        for widget in self.winfo_children():
            if isinstance(widget, tk.Label):
                widget.config(bg=self.original_bg)


class MultiFileDropFrame(tk.Frame):
    """Frame for multiple file drop with visual feedback and drag & drop support"""
    
    def __init__(self, parent, label_text, row, col):
        super().__init__(parent, relief=tk.RAISED, borderwidth=2, bg="#F5F5F5")
        self.file_paths = []
        self.label_text = label_text
        
        self.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
        
        # Configure for hover effect
        self.original_bg = "#F5F5F5"
        self.hover_bg = "#E3F2FD"
        self.active_bg = "#E8F5E9"
        self.drag_over_bg = "#FFF9C4"
        
        # Enable drag and drop if available
        if DND_AVAILABLE:
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self.on_drop)
            self.dnd_bind('<<DragEnter>>', self.on_drag_enter)
            self.dnd_bind('<<DragLeave>>', self.on_drag_leave)
        
        # Title label
        title_label = tk.Label(
            self,
            text=label_text,
            font=("Arial", 11, "bold"),
            bg=self.original_bg,
            fg="#333333",
            pady=15
        )
        title_label.pack()
        
        # Icon/placeholder
        icon_label = tk.Label(
            self,
            text="📄",
            font=("Arial", 32),
            bg=self.original_bg,
            fg="#999999"
        )
        icon_label.pack(pady=10)
        
        # File paths label (scrollable)
        list_frame = tk.Frame(self, bg=self.original_bg)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.path_listbox = tk.Listbox(
            list_frame,
            font=("Arial", 9),
            bg="#FFFFFF",
            fg="#333333",
            yscrollcommand=scrollbar.set,
            height=4
        )
        # 初始不显示列表，等有文件时再 pack
        scrollbar.config(command=self.path_listbox.yview)
        
        # Placeholder label
        self.placeholder_label = tk.Label(
            self,
            text="Click to select files\n(Can select multiple)",
            font=("Arial", 9),
            bg=self.original_bg,
            fg="#999999",
            wraplength=200
        )
        self.placeholder_label.pack(pady=5, padx=10)
        
        # Buttons frame
        buttons_frame = tk.Frame(self, bg=self.original_bg)
        buttons_frame.pack(pady=5)
        
        # Browse button
        self.browse_btn = tk.Button(
            buttons_frame,
            text="Browse...",
            command=self.browse_files,
            bg="#2196F3",
            fg="white",
            font=("Arial", 9),
            relief=tk.FLAT,
            padx=15,
            pady=6,
            cursor="hand2",
            activebackground="#1976D2",
            activeforeground="white"
        )
        self.browse_btn.pack(side=tk.LEFT, padx=2)
        
        # Remove button
        self.remove_btn = tk.Button(
            buttons_frame,
            text="Remove",
            command=self.remove_selected,
            bg="#F44336",
            fg="white",
            font=("Arial", 9),
            relief=tk.FLAT,
            padx=15,
            pady=6,
            cursor="hand2",
            activebackground="#D32F2F",
            activeforeground="white"
        )
        self.remove_btn.pack(side=tk.LEFT, padx=2)
        
        # Bind click events
        self.bind("<Button-1>", self.on_click)
        title_label.bind("<Button-1>", self.on_click)
        icon_label.bind("<Button-1>", self.on_click)
        self.placeholder_label.bind("<Button-1>", self.on_click)
        
        # Bind hover events
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        title_label.bind("<Enter>", self.on_enter)
        title_label.bind("<Leave>", self.on_leave)
        icon_label.bind("<Enter>", self.on_enter)
        icon_label.bind("<Leave>", self.on_leave)
        self.placeholder_label.bind("<Enter>", self.on_enter)
        self.placeholder_label.bind("<Leave>", self.on_leave)
    
    def on_drop(self, event):
        """Handle file drop"""
        files = self.tk.splitlist(event.data)
        for file_path in files:
            file_path = file_path.strip('{}')  # Remove braces if present
            if file_path and os.path.exists(file_path):
                self.add_file(file_path)
    
    def on_drag_enter(self, event):
        """Handle drag enter - change background color"""
        self.config(bg=self.drag_over_bg)
        for widget in self.winfo_children():
            if isinstance(widget, tk.Label) and widget != self.placeholder_label:
                widget.config(bg=self.drag_over_bg)
    
    def on_drag_leave(self, event):
        """Handle drag leave - restore background color"""
        if not self.file_paths:
            self.config(bg=self.original_bg)
            for widget in self.winfo_children():
                if isinstance(widget, tk.Label) and widget != self.placeholder_label:
                    widget.config(bg=self.original_bg)
    
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
    
    def add_file(self, file_path):
        """Add a file to the list"""
        if file_path not in self.file_paths:
            self.file_paths.append(file_path)
            filename = os.path.basename(file_path)
            self.path_listbox.insert(tk.END, filename)
            
            # Hide placeholder, show listbox
            if len(self.file_paths) == 1:
                self.placeholder_label.pack_forget()
                # 确保列表被显示（在自己的 list_frame 中 pack）
                self.path_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            # Update background
            self.config(bg=self.active_bg)
            for widget in self.winfo_children():
                if isinstance(widget, tk.Label) and widget != self.placeholder_label:
                    widget.config(bg=self.active_bg)
    
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
                self.config(bg=self.original_bg)
                for widget in self.winfo_children():
                    if isinstance(widget, tk.Label) and widget != self.placeholder_label:
                        widget.config(bg=self.original_bg)
    
    def on_enter(self, event):
        """Handle mouse enter"""
        if not self.file_paths:
            self.config(bg=self.hover_bg)
            for widget in self.winfo_children():
                if isinstance(widget, tk.Label) and widget != self.placeholder_label:
                    widget.config(bg=self.hover_bg)
    
    def on_leave(self, event):
        """Handle mouse leave"""
        if not self.file_paths:
            self.config(bg=self.original_bg)
            for widget in self.winfo_children():
                if isinstance(widget, tk.Label) and widget != self.placeholder_label:
                    widget.config(bg=self.original_bg)
    
    def get_files(self):
        """Get the selected file paths"""
        return self.file_paths.copy() if self.file_paths else None
    
    def clear(self):
        """Clear all selected files"""
        self.file_paths = []
        self.path_listbox.delete(0, tk.END)
        self.placeholder_label.pack(pady=5, padx=10)
        self.path_listbox.pack_forget()
        self.config(bg=self.original_bg)
        for widget in self.winfo_children():
            if isinstance(widget, tk.Label) and widget != self.placeholder_label:
                widget.config(bg=self.original_bg)


class IntactJSONGeneratorGUI:
    """Main GUI application"""
    
    def __init__(self, root):
        self.root = root
        self.root.title(f"Intact JSON Generator v{APP_VERSION}")
        self.root.geometry("900x750")
        self.root.resizable(True, True)
        self.root.configure(bg="#FFFFFF")
        
        # Create canvas with scrollbar
        canvas = tk.Canvas(root, bg="#FFFFFF", highlightthickness=0)
        scrollbar = ttk.Scrollbar(root, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#FFFFFF")
        
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
        main_container = tk.Frame(scrollable_frame, bg="#FFFFFF")
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Title
        title_frame = tk.Frame(main_container, bg="#FFFFFF")
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        title_label = tk.Label(
            title_frame,
            text="Intact JSON Generator",
            font=("Arial", 24, "bold"),
            fg="#1976D2",
            bg="#FFFFFF"
        )
        title_label.pack()
        
        subtitle_text = "Drag and drop files or click to select your documents"
        if not DND_AVAILABLE:
            subtitle_text = "Click on each box to select your documents (drag & drop not available)"
        
        subtitle_label = tk.Label(
            title_frame,
            text=subtitle_text,
            font=("Arial", 11),
            fg="#666666",
            bg="#FFFFFF"
        )
        subtitle_label.pack(pady=(5, 0))
        
        # Company selection frame
        company_frame = tk.Frame(main_container, bg="#FFFFFF")
        company_frame.pack(fill=tk.X, pady=(10, 20))
        
        company_label = tk.Label(
            company_frame,
            text="Company:",
            font=("Arial", 11, "bold"),
            fg="#333333",
            bg="#FFFFFF"
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
        output_dir_frame = tk.Frame(main_container, bg="#FFFFFF")
        output_dir_frame.pack(fill=tk.X, pady=(0, 15))

        output_dir_label = tk.Label(
            output_dir_frame,
            text="Output Folder:",
            font=("Arial", 11, "bold"),
            fg="#333333",
            bg="#FFFFFF"
        )
        output_dir_label.pack(side=tk.LEFT, padx=(0, 10))

        default_output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "output"))
        self.output_dir_var = tk.StringVar(value=default_output_dir)
        self.output_dir_entry = ttk.Entry(
            output_dir_frame,
            textvariable=self.output_dir_var,
            width=55
        )
        self.output_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        browse_output_btn = ttk.Button(
            output_dir_frame,
            text="Browse...",
            command=self.select_output_folder,
            width=12
        )
        browse_output_btn.pack(side=tk.LEFT)
        
        # Document frames container
        docs_container = tk.Frame(main_container, bg="#FFFFFF")
        docs_container.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Configure grid
        docs_container.grid_columnconfigure(0, weight=1)
        docs_container.grid_columnconfigure(1, weight=1)
        docs_container.grid_rowconfigure(0, weight=1)
        docs_container.grid_rowconfigure(1, weight=1)
        
        # Create 4 document frames
        self.autoplus_frame = MultiFileDropFrame(docs_container, "Autoplus Document(s)", 0, 0)
        self.quote_frame = DocumentDropFrame(docs_container, "Quote Document", 0, 1)
        self.mvr_frame = MultiFileDropFrame(docs_container, "MVR Document(s)", 1, 0)
        self.app_form_frame = DocumentDropFrame(docs_container, "Application Form", 1, 1)
        
        # Buttons frame
        buttons_frame = tk.Frame(main_container, bg="#FFFFFF")
        buttons_frame.pack(fill=tk.X, pady=20)
        
        # Generate button
        self.generate_btn = tk.Button(
            buttons_frame,
            text="Generate JSON",
            command=self.generate_json,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 12, "bold"),
            padx=30,
            pady=12,
            relief=tk.FLAT,
            cursor="hand2",
            activebackground="#45a049",
            activeforeground="white"
        )
        self.generate_btn.pack(side=tk.LEFT, padx=5)
        
        # Clear button
        clear_btn = tk.Button(
            buttons_frame,
            text="Clear All",
            command=self.clear_all,
            bg="#757575",
            fg="white",
            font=("Arial", 10),
            padx=20,
            pady=10,
            relief=tk.FLAT,
            cursor="hand2",
            activebackground="#616161",
            activeforeground="white"
        )
        clear_btn.pack(side=tk.LEFT, padx=5)
        
        # Progress bar
        self.progress = ttk.Progressbar(
            buttons_frame,
            mode='indeterminate',
            length=300
        )
        self.progress.pack(side=tk.LEFT, padx=20)
        
        # Status label
        self.status_label = tk.Label(
            buttons_frame,
            text="Ready",
            font=("Arial", 10),
            fg="#666666",
            bg="#FFFFFF"
        )
        self.status_label.pack(side=tk.LEFT, padx=10)
        
        # Output section
        output_frame = tk.Frame(main_container, bg="#FFFFFF")
        output_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        output_label = tk.Label(
            output_frame,
            text="Output Log:",
            font=("Arial", 11, "bold"),
            fg="#333333",
            bg="#FFFFFF"
        )
        output_label.pack(anchor=tk.W, pady=(0, 5))
        
        self.output_text = scrolledtext.ScrolledText(
            output_frame,
            height=8,
            font=("Consolas", 9),
            wrap=tk.WORD,
            bg="#FAFAFA",
            fg="#333333",
            relief=tk.FLAT,
            borderwidth=1
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)
        self.log(f"Version: {APP_VERSION}")
    
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
        self.status_label.config(text="Ready", fg="#666666")
        self.log("All files cleared")
    
    def generate_json(self):
        """Generate JSON from selected documents"""
        # Get selected company
        selected_company = self.company_var.get()
        
        # Check if company output type is configured (only for Aviva)
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
        self.status_label.config(text="Processing...", fg="#1976D2")
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
            self.root.after(0, self.log, "Initializing generator...")
            generator = IntactJSONGenerator(company=company)
            
            # Generate JSON
            self.root.after(0, self.log, f"Generating JSON for {company}...")
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
            import traceback
            tb = traceback.format_exc()
            self.root.after(0, self._generation_error, error_msg, tb)
    
    def _generation_success(self, output_path):
        """Handle successful generation"""
        self.progress.stop()
        self.generate_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Success!", fg="#2E7D32")
        self.log(f"\n[SUCCESS] JSON generated successfully!")
        self.log(f"Output saved to: {os.path.abspath(output_path)}")
        
        # Ask if user wants to open the file
        result = messagebox.askyesno(
            "Success",
            f"JSON generated successfully!\n\nSaved to:\n{os.path.abspath(output_path)}\n\nDo you want to open the file?"
        )
        
        if result:
            try:
                os.startfile(output_path)
            except:
                messagebox.showinfo("Info", f"File saved to:\n{os.path.abspath(output_path)}")
    
    def _generation_error(self, error_msg, traceback_str):
        """Handle generation error"""
        self.progress.stop()
        self.generate_btn.config(state=tk.NORMAL)
        self.status_label.config(text="Error", fg="#D32F2F")
        self.log(f"\n[ERROR] Generation failed: {error_msg}")
        self.log(f"\nTraceback:\n{traceback_str}")
        messagebox.showerror("Error", f"Failed to generate JSON:\n\n{error_msg}")


def main():
    """Main entry point"""
    # Startup update check runs before GUI initialization.
    if run_startup_update_check(messagebox):
        return

    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    
    app = IntactJSONGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
