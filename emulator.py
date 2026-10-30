"""Java Game Emulator - a Tkinter launcher for J2ME (.jar) games (Windows and Linux).

This application manages a personal library of J2ME games and launches them
through FreeJ2ME, an open-source J2ME emulator (GPL-3.0). The launcher itself
does not render games; FreeJ2ME opens its own window and handles graphics,
audio, keyboard input, and save data.

project layout:

    JavaEmulator/
    |-- emulator.py            This launcher
    |-- games_library.json     Persistent game list (created automatically)
    |-- freej2me/freej2me.jar  FreeJ2ME emulator
    |-- jre-windows/           Optional portable JRE for Windows
    |-- jre-linux/ (or jre/)   Optional portable JRE for Linux
    `-- logs/                  Emulator output from the most recent run

If no portable JRE is found, the launcher falls back to the Java installation
available on the system PATH.
"""

import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# All paths are resolved relative to this file, so the application works
# regardless of the current working directory it was started from.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "games_library.json")
FREEJ2ME_DIR = os.path.join(BASE_DIR, "freej2me")
FREEJ2ME_JAR = os.path.join(FREEJ2ME_DIR, "freej2me.jar")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# ---------------------------------------------------------------------------
# Emulator settings
# ---------------------------------------------------------------------------
# Screen resolution and scale factor passed to FreeJ2ME as command-line
# arguments. Increase LCD_SCALE (e.g. 2) to enlarge the game window.
LCD_WIDTH, LCD_HEIGHT, LCD_SCALE = 240, 320, 1

# Seconds to wait after launch before checking whether the emulator crashed.
LAUNCH_CHECK_DELAY_MS = 3000

# Number of game cards displayed per row in the library grid.
GRID_COLUMNS = 3


class JavaEmulatorApp:
  """Main application window: game library grid and game launcher."""

  def __init__(self, root):
    self.root = root
    self.root.title("Java Game Emulator (Offline Portable)")
    self.root.geometry("850x600")
    self.root.minsize(700, 500)

    self.games = self.load_games()
    self.create_widgets()

  # -------------------------------------------------------------------------
  # Library persistence
  # -------------------------------------------------------------------------
  def load_games(self):
    """Load the saved game list from disk.

    Returns:
      A list of {"name": str, "path": str} dictionaries. An empty list is
      returned if the file is missing or cannot be parsed.
    """
    if os.path.exists(CONFIG_FILE):
      try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
          return json.load(f)
      except Exception as e:
        print(f"Error loading games: {e}")
        return []
    return []

  def save_games(self):
    """Write the current game list to disk as formatted JSON."""
    try:
      with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(self.games, f, ensure_ascii=False, indent=4)
    except Exception as e:
      print(f"Error saving games: {e}")

  # -------------------------------------------------------------------------
  # Java runtime lookup
  # -------------------------------------------------------------------------
  def get_local_java_path(self):
    """Locate a Java executable for the current operating system.

    Search order:
      1. A portable JRE bundled in the project folder (OS-specific directory).
      2. The `java` executable found on the system PATH.

    Returns:
      The path to the Java executable, or None if none was found.
    """
    if sys.platform.startswith("win"):
      folders, exe = ["jre-windows"], "java.exe"
    else:
      # "jre" is kept as a legacy folder name for existing Linux setups.
      folders, exe = ["jre-linux", "jre"], "java"

    for folder in folders:
      local = os.path.join(BASE_DIR, folder, "bin", exe)
      if os.path.isfile(local):
        return local
    return shutil.which("java")

  # -------------------------------------------------------------------------
  # User interface
  # -------------------------------------------------------------------------
  def create_widgets(self):
    """Build the top bar, notice banner, and scrollable library area."""
    # --- Top control panel ---
    top_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
    top_frame.pack(fill=tk.X, side=tk.TOP)

    title_label = tk.Label(
        top_frame,
        text="🎮 Java Game Emulator",
        bg="#2c3e50",
        fg="white",
        font=("Arial", 14, "bold"),
    )
    title_label.pack(side=tk.LEFT, padx=20, pady=15)

    btn_import = tk.Button(
        top_frame,
        text="+ Import .jar Game",
        command=self.import_game,
        bg="#27ae60",
        fg="white",
        font=("Arial", 10, "bold"),
        padx=10,
        pady=5,
        relief=tk.FLAT,
    )
    btn_import.pack(side=tk.RIGHT, padx=15, pady=12)

    btn_settings = tk.Button(
        top_frame,
        text="⚙ Key Mapping",
        command=self.open_settings,
        bg="#2980b9",
        fg="white",
        font=("Arial", 10),
        padx=10,
        pady=5,
        relief=tk.FLAT,
    )
    btn_settings.pack(side=tk.RIGHT, padx=5, pady=12)

    # --- Notice banner ---
    notice_frame = tk.Frame(self.root, bg="#f39c12", height=30)
    notice_frame.pack(fill=tk.X, side=tk.TOP)

    notice_label = tk.Label(
        notice_frame,
        text=(
            "💡 Note: For the best experience, please import J2ME games with a"
            " 240x320 screen resolution."
        ),
        bg="#f39c12",
        fg="#ffffff",
        font=("Arial", 9, "bold"),
    )
    notice_label.pack(pady=5)

    # --- Scrollable library area ---
    # A Canvas hosts an inner Frame so the card grid can scroll vertically.
    self.canvas = tk.Canvas(self.root, bg="#ecf0f1", highlightthickness=0)
    self.scrollbar = ttk.Scrollbar(
        self.root, orient="vertical", command=self.canvas.yview
    )
    self.game_frame = tk.Frame(self.canvas, bg="#ecf0f1")

    # Keep the scrollable region in sync with the size of the card grid.
    self.game_frame.bind(
        "<Configure>",
        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
    )

    self.canvas.create_window((0, 0), window=self.game_frame, anchor="nw")
    self.canvas.configure(yscrollcommand=self.scrollbar.set)

    self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    self.update_game_display()

  def update_game_display(self):
    """Rebuild the game card grid from the current library."""
    for widget in self.game_frame.winfo_children():
      widget.destroy()

    if not self.games:
      lbl = tk.Label(
          self.game_frame,
          text=(
              "No games imported yet.\nClick '+ Import .jar Game' to add your"
              " J2ME games!"
          ),
          bg="#ecf0f1",
          fg="#7f8c8d",
          font=("Arial", 12),
          pady=100,
      )
      lbl.pack(fill=tk.BOTH, expand=True)
      return

    for index, game in enumerate(self.games):
      row = index // GRID_COLUMNS
      col = index % GRID_COLUMNS

      card = tk.Frame(
          self.game_frame,
          bg="white",
          bd=1,
          relief=tk.SOLID,
          width=180,
          height=180,
      )
      card.grid(row=row, column=col, padx=20, pady=20)
      card.pack_propagate(False)  # Keep the card at its fixed size.

      lbl_name = tk.Label(
          card,
          text=game["name"],
          bg="white",
          fg="#2c3e50",
          font=("Arial", 10, "bold"),
          wraplength=160,
      )
      lbl_name.pack(pady=10)

      # Default arguments bind the current game to each button's callback.
      btn_play = tk.Button(
          card,
          text="▶ Play",
          command=lambda p=game["path"], n=game["name"]: self.play_game(p, n),
          bg="#e67e22",
          fg="white",
          font=("Arial", 9, "bold"),
          relief=tk.FLAT,
          width=12,
      )
      btn_play.pack(side=tk.TOP, pady=2)

      btn_remove = tk.Button(
          card,
          text="🗑 Remove",
          command=lambda p=game["path"]: self.remove_game(p),
          bg="#c0392b",
          fg="white",
          font=("Arial", 8),
          relief=tk.FLAT,
          width=12,
      )
      btn_remove.pack(side=tk.TOP, pady=5)

  def open_settings(self):
    """Show a read-only reference of the FreeJ2ME keyboard mapping.

    The mapping is defined inside FreeJ2ME itself (see freej2me/KEYMAP.md);
    this window only displays it and cannot change it.
    """
    settings_win = tk.Toplevel(self.root)
    settings_win.title("Key Mapping Settings")
    settings_win.geometry("520x330")
    settings_win.config(bg="#f8f9fa")
    settings_win.grab_set()  # Make the dialog modal.

    tk.Label(
        settings_win,
        text="🎮 Key Mapping Configuration",
        font=("Arial", 12, "bold"),
        bg="#f8f9fa",
        fg="#2c3e50",
    ).pack(pady=15)

    mappings = [
        ("Keypad 1-0", "Number Row"),
        ("Left Softkey", "Q"),
        ("Right Softkey", "W"),
        ("Star (*)", "E"),
        ("Hash (#)", "R"),
        ("D-Pad", "Arrow Keys"),
        ("OK / Fire", "Enter"),
        ("freej2me Menu", "Esc"),
    ]

    frame_map = tk.Frame(settings_win, bg="#f8f9fa")
    frame_map.pack(pady=5)

    # Lay the mappings out in two columns of (label, key) pairs.
    for i, (j_btn, p_key) in enumerate(mappings):
      r = i // 2
      c = (i % 2) * 2
      tk.Label(
          frame_map, text=f"{j_btn}:", bg="#f8f9fa", font=("Arial", 9, "bold")
      ).grid(row=r, column=c, sticky="w", padx=15, pady=4)

      tk.Label(
          frame_map,
          text=f"[{p_key}]",
          bg="#ffffff",
          fg="#c0392b",
          font=("Arial", 9, "bold"),
          relief="solid",
          width=12,
      ).grid(row=r, column=c + 1, padx=10, pady=4)

    tk.Button(
        settings_win,
        text="Close",
        command=settings_win.destroy,
        bg="#7f8c8d",
        fg="white",
        font=("Arial", 9),
        padx=15,
    ).pack(pady=20)

  # -------------------------------------------------------------------------
  # Library actions
  # -------------------------------------------------------------------------
  def import_game(self):
    """Prompt for a .jar file and add it to the library.

    Rejects non-.jar files and games that are already in the library
    (compared by normalized absolute path).
    """
    file_path = filedialog.askopenfilename(
        title="Select Java Game (.jar)",
        filetypes=[("Java Archive Files", "*.jar")],
    )
    if not file_path:
      return  # The user cancelled the dialog.

    file_path = os.path.abspath(file_path)
    if not file_path.lower().endswith(".jar"):
      messagebox.showerror("Error", "Only .jar files are supported.")
      return

    game_name = os.path.basename(file_path)
    if any(
        os.path.normcase(g["path"]) == os.path.normcase(file_path)
        for g in self.games
    ):
      messagebox.showwarning("Warning", "This game is already in your library!")
      return

    self.games.append({"name": game_name, "path": file_path})
    self.save_games()

    messagebox.showinfo("Success", f"Successfully imported:\n{game_name}")
    self.update_game_display()

  def remove_game(self, path):
    """Remove a game from the library after user confirmation.

    Only the library entry is removed; the .jar file itself is not deleted.
    """
    if messagebox.askyesno(
        "Remove Game", "Do you want to remove this game from your library?"
    ):
      self.games = [g for g in self.games if g["path"] != path]
      self.save_games()
      self.update_game_display()

  # -------------------------------------------------------------------------
  # Game launching
  # -------------------------------------------------------------------------
  def play_game(self, path, name):
    """Launch a game in FreeJ2ME as a separate process.

    Args:
      path: Absolute path to the game's .jar file.
      name: Display name of the game (currently unused; kept for callers).
    """
    # Verify that all required components exist before launching.
    if not os.path.exists(FREEJ2ME_JAR):
      messagebox.showerror(
          "Error",
          f"Missing '{FREEJ2ME_JAR}' file!\nPlease ensure the freej2me.jar"
          " exists inside the 'freej2me/' folder.",
      )
      return

    java_executable = self.get_local_java_path()
    if not java_executable:
      messagebox.showerror(
          "Error",
          "Java not found!\nPut a portable JRE in 'jre-windows/' (Windows)"
          " or 'jre-linux/' (Linux), or install Java.",
      )
      return

    if not os.path.isfile(path):
      messagebox.showerror("Error", f"Game file not found:\n{path}")
      return

    # FreeJ2ME opens its own window for the game. It is started with its
    # working directory set to the freej2me/ folder so that its generated
    # config/ and rms/ (save data) directories stay inside the project.
    # All emulator output, including errors, is redirected to a log file.
    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, "freej2me_last_run.txt")
    try:
      cmd = [
          java_executable,
          # Disable Direct3D/OpenGL pipelines and HiDPI scaling, which are
          # common causes of blank (white) AWT windows on some systems.
          "-Dsun.java2d.d3d=false",
          "-Dsun.java2d.opengl=false",
          "-Dsun.java2d.uiScale=1",
          "-jar",
          FREEJ2ME_JAR,
          # FreeJ2ME requires the game location as a file:// URL, not a
          # plain filesystem path.
          Path(path).resolve().as_uri(),
          str(LCD_WIDTH),
          str(LCD_HEIGHT),
          str(LCD_SCALE),
      ]
      with open(log_path, "w", encoding="utf-8", errors="replace") as log_file:
        log_file.write("COMMAND: " + " ".join(cmd) + "\n\n")
        log_file.flush()
        # The child process inherits its own copy of the file handle, so it is
        # safe to close ours as soon as the process has started.
        proc = subprocess.Popen(
            cmd, cwd=FREEJ2ME_DIR, stdout=log_file, stderr=subprocess.STDOUT
        )
    except Exception as e:
      messagebox.showerror("Execution Error", f"Failed to launch game: {e}")
      return

    # After a short delay, check whether the emulator exited immediately.
    self.root.after(
        LAUNCH_CHECK_DELAY_MS, lambda: self.check_launch(proc, log_path)
    )

  def check_launch(self, proc, log_path):
    """Report an error dialog if the emulator exited with a non-zero code.

    Args:
      proc: The subprocess.Popen object for the emulator process.
      log_path: Path to the log file capturing the emulator's output.
    """
    if proc.poll() is not None and proc.returncode != 0:
      try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
          tail = f.read()[-1500:]  # Show only the end of the log.
      except Exception:
        tail = "(log unreadable)"
      messagebox.showerror(
          "Game exited with an error",
          f"Exit code: {proc.returncode}\n\nLog: {log_path}\n\n{tail}",
      )


if __name__ == "__main__":
  root = tk.Tk()
  app = JavaEmulatorApp(root)
  root.mainloop()
