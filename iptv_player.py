#!/usr/bin/env python3
"""IPTV Desktop Player - uses pywebview + hls.js. No VLC needed."""

import json
import os
import re
import sys

try:
    import webview
except ImportError:
    print("ERROR: pywebview is required. Install with: pip install pywebview")
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
            group_match = re.search(r'group-title="([^"]*)"', line)
            group = group_match.group(1) if group_match else "Ungrouped"
            logo_match = re.search(r'tvg-logo="([^"]*)"', line)
            logo = logo_match.group(1) if logo_match else ""
            name_match = re.search(r",(.+)$", line)
            name = name_match.group(1).strip() if name_match else "Unknown"
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i].strip().startswith("#")):
                i += 1
            if i < len(lines):
                url = lines[i].strip()
                channels.append({"name": name, "url": url, "group": group, "logo": logo})
        i += 1
    return channels


def build_html(channels):
    """Build the full HTML player page with embedded channel data."""
    channels_json = json.dumps(channels)
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IPTV Player</title>
<script src="https://cdn.jsdelivr.net/npm/hls.js@1"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
html, body { height:100%%; overflow:hidden; font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif; background:#0f0f0f; color:#eaeaea; }

#app { display:flex; height:100%%; }

/* --- Sidebar --- */
#sidebar { width:300px; min-width:240px; max-width:400px; background:#16213e; display:flex; flex-direction:column; border-right:1px solid #0f3460; resize:horizontal; overflow:hidden; }
#sidebar.hidden { display:none; }
#sidebar-header { background:#0f3460; padding:14px 16px; text-align:center; }
#sidebar-header h1 { color:#e94560; font-size:18px; font-weight:700; letter-spacing:1px; }
#search-box { padding:8px 12px; background:#16213e; }
#search-box input { width:100%%; padding:8px 12px; background:#1a1a2e; border:1px solid #0f3460; border-radius:6px; color:#eaeaea; font-size:13px; outline:none; }
#search-box input:focus { border-color:#e94560; }
#search-box input::placeholder { color:#666; }
#channel-list { flex:1; overflow-y:auto; overflow-x:hidden; }
#channel-list::-webkit-scrollbar { width:6px; }
#channel-list::-webkit-scrollbar-track { background:#16213e; }
#channel-list::-webkit-scrollbar-thumb { background:#0f3460; border-radius:3px; }
#channel-list::-webkit-scrollbar-thumb:hover { background:#e94560; }

.group-header { background:#0f3460; padding:8px 14px; cursor:pointer; display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #16213e; user-select:none; }
.group-header:hover { background:#133a6e; }
.group-header .group-name { color:#e94560; font-weight:600; font-size:13px; }
.group-header .group-count { color:#888; font-size:11px; }
.group-header .arrow { color:#e94560; font-size:10px; transition:transform .2s; }
.group-header.collapsed .arrow { transform:rotate(-90deg); }
.group-channels { overflow:hidden; }
.group-channels.collapsed { display:none; }

.channel-item { padding:7px 14px 7px 24px; cursor:pointer; font-size:13px; color:#bbb; border-bottom:1px solid rgba(15,52,96,0.3); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; transition:background .15s, color .15s; }
.channel-item:hover { background:#1a2744; color:#fff; }
.channel-item.active { background:#e94560; color:#fff; font-weight:600; }

/* --- Player area --- */
#player-area { flex:1; display:flex; flex-direction:column; background:#000; min-width:0; }
#video-container { flex:1; position:relative; background:#000; display:flex; align-items:center; justify-content:center; }
#video-container video { width:100%%; height:100%%; object-fit:contain; background:#000; }
#placeholder { position:absolute; color:#333; font-size:18px; pointer-events:none; }
#placeholder.hidden { display:none; }
#error-msg { position:absolute; color:#e94560; font-size:14px; text-align:center; padding:20px; display:none; }

/* --- Controls --- */
#controls { background:#1a1a2e; padding:10px 16px; display:flex; align-items:center; gap:12px; border-top:1px solid #0f3460; }
#now-playing { flex:1; font-size:13px; color:#ccc; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ctrl-btn { background:#0f3460; color:#eaeaea; border:none; padding:6px 14px; border-radius:4px; font-size:12px; font-weight:600; cursor:pointer; transition:background .15s; white-space:nowrap; }
.ctrl-btn:hover { background:#1a4a8a; }
.ctrl-btn.stop-btn { background:#e94560; }
.ctrl-btn.stop-btn:hover { background:#c81e45; }
#volume-slider { width:90px; accent-color:#e94560; cursor:pointer; }

/* --- Status bar --- */
#status-bar { background:#111; padding:4px 16px; font-size:11px; color:#555; }
</style>
</head>
<body>
<div id="app">
  <div id="sidebar">
    <div id="sidebar-header"><h1>IPTV Player</h1></div>
    <div id="search-box"><input type="text" id="search" placeholder="Search channels..."></div>
    <div id="channel-list"></div>
  </div>
  <div id="player-area">
    <div id="video-container">
      <video id="video" autoplay></video>
      <div id="placeholder">Select a channel to start watching</div>
      <div id="error-msg"></div>
    </div>
    <div id="controls">
      <span id="now-playing">No channel selected</span>
      <input type="range" id="volume-slider" min="0" max="100" value="80" title="Volume">
      <button class="ctrl-btn stop-btn" id="stop-btn">Stop</button>
      <button class="ctrl-btn" id="mute-btn">Mute</button>
      <button class="ctrl-btn" id="fs-btn">Fullscreen</button>
    </div>
    <div id="status-bar">Ready</div>
  </div>
</div>

<script>
const CHANNELS = """ + channels_json + """;

let hls = null;
let currentChannel = null;
const video = document.getElementById('video');
const placeholder = document.getElementById('placeholder');
const errorMsg = document.getElementById('error-msg');
const nowPlaying = document.getElementById('now-playing');
const statusBar = document.getElementById('status-bar');
const searchInput = document.getElementById('search');
const channelList = document.getElementById('channel-list');
const volumeSlider = document.getElementById('volume-slider');
const sidebar = document.getElementById('sidebar');

// Group channels
function groupChannels(channels) {
  const groups = {};
  const order = [];
  channels.forEach(ch => {
    if (!groups[ch.group]) { groups[ch.group] = []; order.push(ch.group); }
    groups[ch.group].push(ch);
  });
  return { groups, order };
}

// Render channel list
function renderChannels(channels) {
  channelList.innerHTML = '';
  const { groups, order } = groupChannels(channels);
  order.forEach(groupName => {
    const chs = groups[groupName];
    const header = document.createElement('div');
    header.className = 'group-header';
    header.innerHTML = '<span class="group-name">' + escapeHtml(groupName) + '</span><span class="group-count">' + chs.length + '</span><span class="arrow">&#9660;</span>';
    channelList.appendChild(header);

    const container = document.createElement('div');
    container.className = 'group-channels';
    chs.forEach(ch => {
      const item = document.createElement('div');
      item.className = 'channel-item';
      if (currentChannel && currentChannel.url === ch.url) item.classList.add('active');
      item.textContent = ch.name;
      item.title = ch.name;
      item.addEventListener('click', () => playChannel(ch));
      container.appendChild(item);
    });
    channelList.appendChild(container);

    header.addEventListener('click', () => {
      header.classList.toggle('collapsed');
      container.classList.toggle('collapsed');
    });
  });
}

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

// Play a channel
function playChannel(ch) {
  errorMsg.style.display = 'none';
  placeholder.classList.add('hidden');

  // Destroy previous HLS instance
  if (hls) { hls.destroy(); hls = null; }

  currentChannel = ch;
  nowPlaying.textContent = 'Now Playing: ' + ch.name;
  statusBar.textContent = 'Connecting to ' + ch.name + '...';

  // Re-highlight active
  document.querySelectorAll('.channel-item').forEach(el => {
    el.classList.toggle('active', el.textContent === ch.name);
  });

  if (Hls.isSupported()) {
    hls = new Hls({
      maxBufferLength: 30,
      maxMaxBufferLength: 60,
      liveSyncDurationCount: 3,
    });
    hls.loadSource(ch.url);
    hls.attachMedia(video);
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      video.play();
      video.volume = volumeSlider.value / 100;
      statusBar.textContent = 'Playing: ' + ch.name;
    });
    hls.on(Hls.Events.ERROR, (event, data) => {
      if (data.fatal) {
        statusBar.textContent = 'Error: ' + data.type + ' - ' + data.details;
        errorMsg.textContent = 'Failed to load stream: ' + data.details;
        errorMsg.style.display = 'block';
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          setTimeout(() => { hls.startLoad(); statusBar.textContent = 'Retrying...'; }, 3000);
        }
      }
    });
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    // Native HLS (Safari)
    video.src = ch.url;
    video.addEventListener('loadedmetadata', () => { video.play(); });
    statusBar.textContent = 'Playing: ' + ch.name;
  } else {
    statusBar.textContent = 'Error: HLS not supported in this browser engine';
    errorMsg.textContent = 'HLS playback is not supported.';
    errorMsg.style.display = 'block';
  }
}

// Stop
document.getElementById('stop-btn').addEventListener('click', () => {
  if (hls) { hls.destroy(); hls = null; }
  video.src = '';
  currentChannel = null;
  nowPlaying.textContent = 'No channel selected';
  statusBar.textContent = 'Stopped';
  placeholder.classList.remove('hidden');
  errorMsg.style.display = 'none';
  document.querySelectorAll('.channel-item.active').forEach(el => el.classList.remove('active'));
});

// Mute
const muteBtn = document.getElementById('mute-btn');
muteBtn.addEventListener('click', () => {
  video.muted = !video.muted;
  muteBtn.textContent = video.muted ? 'Unmute' : 'Mute';
});

// Volume
volumeSlider.addEventListener('input', () => { video.volume = volumeSlider.value / 100; });

// Fullscreen
document.getElementById('fs-btn').addEventListener('click', () => {
  const el = document.getElementById('player-area');
  if (!document.fullscreenElement) {
    el.requestFullscreen().catch(() => {});
    sidebar.classList.add('hidden');
  } else {
    document.exitFullscreen();
    sidebar.classList.remove('hidden');
  }
});
document.addEventListener('fullscreenchange', () => {
  if (!document.fullscreenElement) sidebar.classList.remove('hidden');
});

// Search
searchInput.addEventListener('input', () => {
  const q = searchInput.value.trim().toLowerCase();
  if (!q) { renderChannels(CHANNELS); return; }
  renderChannels(CHANNELS.filter(ch => ch.name.toLowerCase().includes(q) || ch.group.toLowerCase().includes(q)));
});

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT') return;
  if (e.key === ' ' || e.key === 'k') { e.preventDefault(); video.paused ? video.play() : video.pause(); }
  if (e.key === 'm') { video.muted = !video.muted; muteBtn.textContent = video.muted ? 'Unmute' : 'Mute'; }
  if (e.key === 'f') { document.getElementById('fs-btn').click(); }
  if (e.key === 'ArrowUp') { e.preventDefault(); volumeSlider.value = Math.min(100, +volumeSlider.value + 5); video.volume = volumeSlider.value / 100; }
  if (e.key === 'ArrowDown') { e.preventDefault(); volumeSlider.value = Math.max(0, +volumeSlider.value - 5); video.volume = volumeSlider.value / 100; }
});

// Init
renderChannels(CHANNELS);
</script>
</body>
</html>"""


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

    html = build_html(channels)
    window = webview.create_window(
        "IPTV Player",
        html=html,
        width=1200,
        height=700,
        min_size=(900, 500),
    )
    webview.start()


if __name__ == "__main__":
    main()
