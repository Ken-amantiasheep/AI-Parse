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


class IntactJSONGeneratorGUI:
    """Main GUI application"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("Intact JSON Generator")
        self.root.geometry("900x750")
        self.root.resizable(True, True)
        self.root.configure(bg="#FFFFFF")
        
        # Create main container
        main_container = tk.Frame(root, bg="#FFFFFF")
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
        
        # Document frames container
        docs_container = tk.Frame(main_container, bg="#FFFFFF")
        docs_container.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Configure grid
        docs_container.grid_columnconfigure(0, weight=1)
        docs_container.grid_columnconfigure(1, weight=1)
        docs_container.grid_rowconfigure(0, weight=1)
        docs_container.grid_rowconfigure(1, weight=1)
        
        # Create 4 document frames
        self.autoplus_frame = DocumentDropFrame(docs_container, "Autoplus Document", 0, 0)
        self.quote_frame = DocumentDropFrame(docs_container, "Quote Document", 0, 1)
        self.mvr_frame = DocumentDropFrame(docs_container, "MVR Document", 1, 0)
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
    
    def log(self, message):
        """Add message to output log"""
        self.output_text.insert(tk.END, f"{message}\n")
        self.output_text.see(tk.END)
        self.root.update_idletasks()
    
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
        # Get file paths
        autoplus_path = self.autoplus_frame.get_file()
        quote_path = self.quote_frame.get_file()
        mvr_path = self.mvr_frame.get_file()
        app_form_path = self.app_form_frame.get_file()
        
        # Check if at least one file is selected
        if not any([autoplus_path, quote_path, mvr_path, app_form_path]):
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
        self.log("Starting JSON generation...")
        
        # Run in separate thread to prevent GUI freezing
        thread = threading.Thread(
            target=self._generate_json_thread,
            args=(autoplus_path, quote_path, mvr_path, app_form_path)
        )
        thread.daemon = True
        thread.start()
    
    def _generate_json_thread(self, autoplus_path, quote_path, mvr_path, app_form_path):
        """Generate JSON in separate thread"""
        try:
            # Initialize generator
            self.root.after(0, self.log, "Initializing generator...")
            generator = IntactJSONGenerator()
            
            # Generate JSON
            self.root.after(0, self.log, "Generating JSON from documents...")
            json_data = generator.generate_json(
                autoplus_path=autoplus_path,
                quote_path=quote_path,
                mvr_path=mvr_path,
                application_form_path=app_form_path
            )
            
            # Save JSON
            output_path = os.path.join("output", "output.json")
            generator.save_json(json_data, output_path)
            
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
    if DND_AVAILABLE:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    
    app = IntactJSONGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
