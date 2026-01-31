#!/usr/bin/env python3
"""IPTV Desktop Player - A Python desktop application for playing IPTV channels."""

import os
import re
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from collections import OrderedDict

try:
    import vlc
except ImportError:
    print("ERROR: python-vlc is required. Install it with: pip install python-vlc")
    print("You also need VLC media player installed on your system.")
    sys.exit(1)


def parse_m3u(filepath):
    """Parse an M3U playlist file and return a list of channel dicts."""
    channels = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().strip().splitlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            info_line = line
            # Extract group-title
            group_match = re.search(r'group-title="([^"]*)"', info_line)
            group = group_match.group(1) if group_match else "Ungrouped"

            # Extract tvg-logo
            logo_match = re.search(r'tvg-logo="([^"]*)"', info_line)
            logo = logo_match.group(1) if logo_match else ""

            # Extract channel name (after the last comma)
            name_match = re.search(r",(.+)$", info_line)
            name = name_match.group(1).strip() if name_match else "Unknown"

            # Next non-empty, non-comment line is the URL
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith("#")):
                i += 1
            if i < len(lines):
                url = lines[i].strip()
                channels.append({
                    "name": name,
                    "url": url,
                    "group": group,
                    "logo": logo,
                })
        i += 1
    return channels


class IPTVPlayer:
    """Main IPTV Player application window."""

    def __init__(self, root, channels):
        self.root = root
        self.channels = channels
        self.current_channel = None
        self.is_fullscreen = False
        self.vlc_instance = vlc.Instance("--no-xlib")
        self.media_player = self.vlc_instance.media_player_new()

        self._setup_window()
        self._build_ui()
        self._build_groups(channels)
        self._bind_events()

        # Periodically update the UI state
        self._update_ui()

    def _setup_window(self):
        self.root.title("IPTV Player")
        self.root.geometry("1200x700")
        self.root.minsize(900, 500)
        self.root.configure(bg="#1a1a2e")

        # Style configuration
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Sidebar.TFrame", background="#16213e")
        style.configure("Player.TFrame", background="#0f0f0f")
        style.configure("Controls.TFrame", background="#1a1a2e")
        style.configure(
            "Group.TLabel",
            background="#16213e",
            foreground="#e94560",
            font=("Helvetica", 11, "bold"),
            padding=(10, 6),
        )
        style.configure(
            "Channel.TLabel",
            background="#16213e",
            foreground="#eaeaea",
            font=("Helvetica", 10),
            padding=(20, 4),
        )
        style.configure(
            "ChannelActive.TLabel",
            background="#e94560",
            foreground="#ffffff",
            font=("Helvetica", 10, "bold"),
            padding=(20, 4),
        )
        style.configure(
            "Title.TLabel",
            background="#1a1a2e",
            foreground="#e94560",
            font=("Helvetica", 14, "bold"),
        )
        style.configure(
            "NowPlaying.TLabel",
            background="#1a1a2e",
            foreground="#eaeaea",
            font=("Helvetica", 10),
        )
        style.configure(
            "Status.TLabel",
            background="#1a1a2e",
            foreground="#888888",
            font=("Helvetica", 9),
        )
        style.configure(
            "TButton",
            background="#e94560",
            foreground="#ffffff",
            font=("Helvetica", 10, "bold"),
            padding=6,
        )
        style.map(
            "TButton",
            background=[("active", "#c81e45"), ("pressed", "#a01535")],
        )

    def _build_ui(self):
        # Main horizontal pane
        self.main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        # --- Sidebar ---
        self.sidebar_frame = tk.Frame(self.main_pane, bg="#16213e", width=300)
        self.main_pane.add(self.sidebar_frame, weight=0)

        # App title
        title_frame = tk.Frame(self.sidebar_frame, bg="#0f3460", pady=10)
        title_frame.pack(fill=tk.X)
        tk.Label(
            title_frame,
            text="IPTV Player",
            bg="#0f3460",
            fg="#e94560",
            font=("Helvetica", 16, "bold"),
        ).pack()

        # Search box
        search_frame = tk.Frame(self.sidebar_frame, bg="#16213e", pady=5, padx=10)
        search_frame.pack(fill=tk.X)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search)
        self.search_entry = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            bg="#1a1a2e",
            fg="#eaeaea",
            insertbackground="#e94560",
            font=("Helvetica", 10),
            relief=tk.FLAT,
            bd=5,
        )
        self.search_entry.pack(fill=tk.X)
        self.search_entry.insert(0, "Search channels...")
        self.search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self._on_search_focus_out)

        # Channel list with scrollbar
        list_frame = tk.Frame(self.sidebar_frame, bg="#16213e")
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.channel_canvas = tk.Canvas(list_frame, bg="#16213e", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.channel_canvas.yview)
        self.scrollable_frame = tk.Frame(self.channel_canvas, bg="#16213e")

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.channel_canvas.configure(scrollregion=self.channel_canvas.bbox("all")),
        )
        self.canvas_window = self.channel_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.channel_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.channel_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Make scrollable frame fill canvas width
        self.channel_canvas.bind("<Configure>", self._on_canvas_configure)

        # Bind mousewheel
        self.channel_canvas.bind_all("<Button-4>", self._on_mousewheel_up)
        self.channel_canvas.bind_all("<Button-5>", self._on_mousewheel_down)

        # --- Right side (player + controls) ---
        self.right_frame = tk.Frame(self.main_pane, bg="#0f0f0f")
        self.main_pane.add(self.right_frame, weight=1)

        # Video frame
        self.video_frame = tk.Frame(self.right_frame, bg="#000000")
        self.video_frame.pack(fill=tk.BOTH, expand=True)

        # Placeholder label when nothing is playing
        self.placeholder_label = tk.Label(
            self.video_frame,
            text="Select a channel to start watching",
            bg="#000000",
            fg="#444444",
            font=("Helvetica", 16),
        )
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # Controls bar
        controls_frame = tk.Frame(self.right_frame, bg="#1a1a2e", pady=8, padx=10)
        controls_frame.pack(fill=tk.X)

        # Now playing label
        self.now_playing_var = tk.StringVar(value="No channel selected")
        tk.Label(
            controls_frame,
            textvariable=self.now_playing_var,
            bg="#1a1a2e",
            fg="#eaeaea",
            font=("Helvetica", 11),
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Control buttons
        btn_frame = tk.Frame(controls_frame, bg="#1a1a2e")
        btn_frame.pack(side=tk.RIGHT)

        self.stop_btn = tk.Button(
            btn_frame,
            text="Stop",
            command=self._stop,
            bg="#e94560",
            fg="white",
            font=("Helvetica", 10, "bold"),
            relief=tk.FLAT,
            padx=12,
            pady=4,
            activebackground="#c81e45",
            activeforeground="white",
        )
        self.stop_btn.pack(side=tk.LEFT, padx=3)

        self.mute_btn = tk.Button(
            btn_frame,
            text="Mute",
            command=self._toggle_mute,
            bg="#0f3460",
            fg="white",
            font=("Helvetica", 10, "bold"),
            relief=tk.FLAT,
            padx=12,
            pady=4,
            activebackground="#16213e",
            activeforeground="white",
        )
        self.mute_btn.pack(side=tk.LEFT, padx=3)

        self.fullscreen_btn = tk.Button(
            btn_frame,
            text="Fullscreen",
            command=self._toggle_fullscreen,
            bg="#0f3460",
            fg="white",
            font=("Helvetica", 10, "bold"),
            relief=tk.FLAT,
            padx=12,
            pady=4,
            activebackground="#16213e",
            activeforeground="white",
        )
        self.fullscreen_btn.pack(side=tk.LEFT, padx=3)

        # Volume slider
        vol_frame = tk.Frame(controls_frame, bg="#1a1a2e")
        vol_frame.pack(side=tk.RIGHT, padx=(0, 10))
        tk.Label(vol_frame, text="Vol:", bg="#1a1a2e", fg="#888888", font=("Helvetica", 9)).pack(side=tk.LEFT)
        self.volume_var = tk.IntVar(value=80)
        self.volume_slider = tk.Scale(
            vol_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.volume_var,
            command=self._on_volume_change,
            bg="#1a1a2e",
            fg="#eaeaea",
            troughcolor="#0f3460",
            highlightthickness=0,
            sliderrelief=tk.FLAT,
            length=100,
            showvalue=False,
        )
        self.volume_slider.pack(side=tk.LEFT)

        # Status bar
        status_frame = tk.Frame(self.right_frame, bg="#111111", pady=3, padx=10)
        status_frame.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(
            status_frame,
            textvariable=self.status_var,
            bg="#111111",
            fg="#666666",
            font=("Helvetica", 9),
            anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X)

    def _on_canvas_configure(self, event):
        self.channel_canvas.itemconfig(self.canvas_window, width=event.width)

    def _build_groups(self, channels):
        """Build the grouped channel list in the sidebar."""
        # Clear existing widgets
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        # Group channels
        groups = OrderedDict()
        for ch in channels:
            g = ch["group"]
            if g not in groups:
                groups[g] = []
            groups[g].append(ch)

        self.channel_labels = {}
        self.group_frames = {}

        for group_name, group_channels in groups.items():
            # Group header
            group_header = tk.Frame(self.scrollable_frame, bg="#0f3460", cursor="hand2")
            group_header.pack(fill=tk.X, pady=(1, 0))

            header_label = tk.Label(
                group_header,
                text=f"  {group_name} ({len(group_channels)})",
                bg="#0f3460",
                fg="#e94560",
                font=("Helvetica", 11, "bold"),
                anchor="w",
                pady=6,
                padx=5,
            )
            header_label.pack(fill=tk.X)

            # Channel container (collapsible)
            channel_container = tk.Frame(self.scrollable_frame, bg="#16213e")
            channel_container.pack(fill=tk.X)
            self.group_frames[group_name] = (channel_container, header_label, True)

            # Toggle collapse on header click
            header_label.bind("<Button-1>", lambda e, g=group_name: self._toggle_group(g))
            group_header.bind("<Button-1>", lambda e, g=group_name: self._toggle_group(g))

            for ch in group_channels:
                ch_frame = tk.Frame(channel_container, bg="#16213e", cursor="hand2")
                ch_frame.pack(fill=tk.X)

                ch_label = tk.Label(
                    ch_frame,
                    text=f"    {ch['name']}",
                    bg="#16213e",
                    fg="#cccccc",
                    font=("Helvetica", 10),
                    anchor="w",
                    pady=3,
                    padx=5,
                )
                ch_label.pack(fill=tk.X)

                # Store reference
                self.channel_labels[ch["url"]] = ch_label

                # Bind click to play
                ch_label.bind("<Button-1>", lambda e, c=ch: self._play_channel(c))
                ch_frame.bind("<Button-1>", lambda e, c=ch: self._play_channel(c))

                # Hover effects
                ch_label.bind("<Enter>", lambda e, lbl=ch_label: self._on_channel_hover(lbl, True))
                ch_label.bind("<Leave>", lambda e, lbl=ch_label: self._on_channel_hover(lbl, False))

    def _toggle_group(self, group_name):
        container, header_label, visible = self.group_frames[group_name]
        if visible:
            container.pack_forget()
            self.group_frames[group_name] = (container, header_label, False)
        else:
            # Re-pack after the header
            container.pack(fill=tk.X)
            self.group_frames[group_name] = (container, header_label, True)

    def _on_channel_hover(self, label, entering):
        if self.current_channel and self.channel_labels.get(self.current_channel["url"]) == label:
            return
        if entering:
            label.configure(bg="#1a2744", fg="#ffffff")
        else:
            label.configure(bg="#16213e", fg="#cccccc")

    def _play_channel(self, channel):
        """Play the selected channel."""
        # Reset previous active label
        if self.current_channel and self.current_channel["url"] in self.channel_labels:
            prev_label = self.channel_labels[self.current_channel["url"]]
            prev_label.configure(bg="#16213e", fg="#cccccc")

        self.current_channel = channel

        # Highlight current
        if channel["url"] in self.channel_labels:
            self.channel_labels[channel["url"]].configure(bg="#e94560", fg="#ffffff")

        # Hide placeholder
        self.placeholder_label.place_forget()

        # Play media
        media = self.vlc_instance.media_new(channel["url"])
        media.add_option(":network-caching=3000")
        self.media_player.set_media(media)

        # Embed video in the frame
        self.root.update_idletasks()
        handle = self.video_frame.winfo_id()
        if sys.platform.startswith("linux"):
            self.media_player.set_xwindow(handle)
        elif sys.platform == "win32":
            self.media_player.set_hwnd(handle)
        elif sys.platform == "darwin":
            self.media_player.set_nsobject(handle)

        self.media_player.play()
        self.media_player.audio_set_volume(self.volume_var.get())

        self.now_playing_var.set(f"Now Playing: {channel['name']}")
        self.status_var.set(f"Connecting to {channel['name']}...")

    def _stop(self):
        self.media_player.stop()
        self.now_playing_var.set("No channel selected")
        self.status_var.set("Stopped")
        self.placeholder_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        if self.current_channel and self.current_channel["url"] in self.channel_labels:
            self.channel_labels[self.current_channel["url"]].configure(bg="#16213e", fg="#cccccc")
        self.current_channel = None

    def _toggle_mute(self):
        is_muted = self.media_player.audio_get_mute()
        self.media_player.audio_set_mute(not is_muted)
        self.mute_btn.configure(text="Unmute" if not is_muted else "Mute")

    def _toggle_fullscreen(self):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)

        if self.is_fullscreen:
            self.sidebar_frame.pack_forget()
            self.fullscreen_btn.configure(text="Exit FS")
        else:
            self.main_pane.forget(self.right_frame)
            self.main_pane.add(self.sidebar_frame, weight=0)
            self.main_pane.add(self.right_frame, weight=1)
            self.fullscreen_btn.configure(text="Fullscreen")

    def _on_volume_change(self, val):
        self.media_player.audio_set_volume(int(val))

    def _on_search(self, *args):
        query = self.search_var.get().strip().lower()
        if query == "" or query == "search channels...":
            self._build_groups(self.channels)
        else:
            filtered = [ch for ch in self.channels if query in ch["name"].lower() or query in ch["group"].lower()]
            self._build_groups(filtered)

    def _on_search_focus_in(self, event):
        if self.search_entry.get() == "Search channels...":
            self.search_entry.delete(0, tk.END)
            self.search_entry.configure(fg="#eaeaea")

    def _on_search_focus_out(self, event):
        if not self.search_entry.get():
            self.search_entry.insert(0, "Search channels...")
            self.search_entry.configure(fg="#666666")

    def _on_mousewheel_up(self, event):
        self.channel_canvas.yview_scroll(-3, "units")

    def _on_mousewheel_down(self, event):
        self.channel_canvas.yview_scroll(3, "units")

    def _bind_events(self):
        self.root.bind("<Escape>", lambda e: self._exit_fullscreen())
        self.root.bind("<F11>", lambda e: self._toggle_fullscreen())
        self.root.bind("<space>", lambda e: self._toggle_pause())
        self.root.bind("<m>", lambda e: self._toggle_mute())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _exit_fullscreen(self):
        if self.is_fullscreen:
            self._toggle_fullscreen()

    def _toggle_pause(self):
        if self.media_player.is_playing():
            self.media_player.pause()
            self.status_var.set("Paused")
        else:
            self.media_player.play()
            if self.current_channel:
                self.status_var.set(f"Playing: {self.current_channel['name']}")

    def _update_ui(self):
        """Periodic UI update."""
        if self.media_player.is_playing() and self.current_channel:
            self.status_var.set(f"Playing: {self.current_channel['name']}")
        self.root.after(2000, self._update_ui)

    def _on_close(self):
        self.media_player.stop()
        self.vlc_instance.release()
        self.root.destroy()


def main():
    playlist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "playlist.m3u")
    if not os.path.exists(playlist_path):
        print(f"Playlist not found: {playlist_path}")
        sys.exit(1)

    channels = parse_m3u(playlist_path)
    if not channels:
        print("No channels found in playlist.")
        sys.exit(1)

    print(f"Loaded {len(channels)} channels.")

    root = tk.Tk()
    IPTVPlayer(root, channels)
    root.mainloop()


if __name__ == "__main__":
    main()
