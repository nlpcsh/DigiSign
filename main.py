import tkinter as tk

from classes.PdfSigner import PdfSigner

def main() -> None:
    root = tk.Tk()
    PdfSigner(root)
    icon = tk.PhotoImage(file="icon.png")
    root.iconphoto(True, icon)
    root.mainloop()

if __name__ == "__main__":
    main()
