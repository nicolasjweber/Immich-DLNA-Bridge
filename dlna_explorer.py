#!/usr/bin/env python3
"""
Immich DLNA Graphical Web Explorer
A zero-dependency local web app to browse and preview your Immich DLNA media server
with high-resolution photos, face avatars, album covers, and video playback.
"""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
from socketserver import ThreadingMixIn
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET

DEFAULT_SERVER = "http://localhost:8200"
DEFAULT_PORT = 8201

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Immich DLNA Explorer</title>
  <style>
    :root {
      --bg: #0f141c;
      --card-bg: #182232;
      --card-hover: #223046;
      --border: #28374d;
      --text: #e6edf3;
      --text-muted: #8b9bb4;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --accent: #10b981;
      --danger: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: #131b26;
      border-bottom: 1px solid var(--border);
      padding: 1rem 1.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 1rem;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }
    .logo-badge {
      background: linear-gradient(135deg, #3b82f6, #8b5cf6);
      color: white;
      font-weight: 700;
      font-size: 1.1rem;
      padding: 0.35rem 0.75rem;
      border-radius: 8px;
      letter-spacing: 0.5px;
    }
    .brand h1 {
      font-size: 1.15rem;
      font-weight: 600;
    }
    .server-status {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.85rem;
      color: var(--text-muted);
      background: rgba(255,255,255,0.05);
      padding: 0.4rem 0.8rem;
      border-radius: 20px;
      border: 1px solid var(--border);
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 8px var(--accent);
    }
    .controls {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .btn {
      background: var(--card-bg);
      color: var(--text);
      border: 1px solid var(--border);
      padding: 0.45rem 0.9rem;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 500;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.15s ease;
      text-decoration: none;
    }
    .btn:hover {
      background: var(--card-hover);
      border-color: #3e5270;
    }
    .btn-primary {
      background: var(--primary);
      border-color: var(--primary);
      color: white;
    }
    .btn-primary:hover {
      background: var(--primary-hover);
    }
    .nav-bar {
      padding: 0.85rem 1.5rem;
      background: rgba(19, 27, 38, 0.6);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .breadcrumbs {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.95rem;
      flex-wrap: wrap;
    }
    .crumb {
      color: var(--primary);
      cursor: pointer;
      padding: 0.2rem 0.4rem;
      border-radius: 4px;
      transition: background 0.15s;
    }
    .crumb:hover {
      background: rgba(59, 130, 246, 0.15);
      text-decoration: underline;
    }
    .crumb.current {
      color: var(--text);
      font-weight: 600;
      cursor: default;
      text-decoration: none;
    }
    .crumb.current:hover { background: transparent; }
    .sep { color: var(--text-muted); font-size: 0.8rem; }

    main {
      padding: 1.5rem;
      flex: 1;
      max-width: 1600px;
      width: 100%;
      margin: 0 auto;
    }
    .section-title {
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: var(--text-muted);
      margin-bottom: 1rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .section-title span {
      background: var(--card-bg);
      padding: 0.15rem 0.5rem;
      border-radius: 12px;
      font-size: 0.75rem;
      border: 1px solid var(--border);
    }

    /* Container Grid */
    .container-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 1.25rem;
      margin-bottom: 2rem;
    }
    .container-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.25rem 1rem;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      cursor: pointer;
      transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
      position: relative;
    }
    .container-card:hover {
      background: var(--card-hover);
      border-color: #3b82f6;
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(0,0,0,0.3);
    }
    .folder-art {
      width: 90px;
      height: 90px;
      border-radius: 50%;
      object-fit: cover;
      margin-bottom: 0.85rem;
      border: 2px solid var(--border);
      background: #111827;
      box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    }
    .folder-art.square {
      border-radius: 10px;
      width: 100px;
      height: 100px;
    }
    .folder-icon {
      width: 80px;
      height: 80px;
      border-radius: 16px;
      background: rgba(59, 130, 246, 0.12);
      color: var(--primary);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 2.2rem;
      margin-bottom: 0.85rem;
      border: 1px solid rgba(59, 130, 246, 0.3);
    }
    .container-title {
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--text);
      word-break: break-word;
      line-height: 1.3;
    }
    .container-sub {
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-top: 0.25rem;
    }

    /* Media Items Grid */
    .media-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 1rem;
    }
    .media-card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      cursor: pointer;
      transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
      position: relative;
      aspect-ratio: 1 / 1;
      display: flex;
      flex-direction: column;
    }
    .media-card:hover {
      border-color: #3b82f6;
      transform: translateY(-2px);
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
    }
    .media-thumb {
      width: 100%;
      height: 100%;
      object-fit: cover;
      background: #111827;
      display: block;
      transition: transform 0.2s ease;
    }
    .media-card:hover .media-thumb {
      transform: scale(1.03);
    }
    .media-overlay {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      background: linear-gradient(transparent, rgba(0,0,0,0.85) 60%);
      padding: 1.5rem 0.6rem 0.6rem;
      color: white;
      font-size: 0.78rem;
      display: flex;
      flex-direction: column;
      gap: 0.2rem;
      pointer-events: none;
    }
    .media-title {
      font-weight: 500;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .video-badge {
      position: absolute;
      top: 0.5rem;
      right: 0.5rem;
      background: rgba(0,0,0,0.7);
      backdrop-filter: blur(4px);
      color: white;
      font-size: 0.7rem;
      font-weight: 600;
      padding: 0.2rem 0.5rem;
      border-radius: 6px;
      display: flex;
      align-items: center;
      gap: 0.3rem;
      border: 1px solid rgba(255,255,255,0.2);
    }

    /* Lightbox Modal */
    .modal {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.92);
      backdrop-filter: blur(8px);
      z-index: 1000;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    .modal.active { display: flex; }
    .modal-content {
      max-width: 90vw;
      max-height: 80vh;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }
    .modal-img {
      max-width: 90vw;
      max-height: 80vh;
      object-fit: contain;
      border-radius: 8px;
      box-shadow: 0 16px 48px rgba(0,0,0,0.8);
    }
    .modal-video {
      max-width: 90vw;
      max-height: 80vh;
      border-radius: 8px;
      box-shadow: 0 16px 48px rgba(0,0,0,0.8);
      outline: none;
    }
    .modal-bar {
      margin-top: 1rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
      max-width: 900px;
      color: var(--text-muted);
      font-size: 0.85rem;
    }
    .modal-close {
      position: absolute;
      top: 1.5rem;
      right: 1.5rem;
      background: rgba(255,255,255,0.1);
      border: 1px solid rgba(255,255,255,0.2);
      color: white;
      width: 40px;
      height: 40px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.25rem;
      cursor: pointer;
      transition: background 0.15s;
    }
    .modal-close:hover { background: rgba(255,255,255,0.25); }
    .modal-nav {
      position: absolute;
      top: 50%;
      transform: translateY(-50%);
      background: rgba(255,255,255,0.1);
      border: 1px solid rgba(255,255,255,0.2);
      color: white;
      width: 48px;
      height: 48px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.5rem;
      cursor: pointer;
      transition: background 0.15s;
    }
    .modal-nav:hover { background: rgba(255,255,255,0.25); }
    .modal-nav.prev { left: 1.5rem; }
    .modal-nav.next { right: 1.5rem; }

    /* Loading Spinner */
    .spinner {
      border: 3px solid rgba(255,255,255,0.1);
      border-top-color: var(--primary);
      border-radius: 50%;
      width: 36px;
      height: 36px;
      animation: spin 0.8s linear infinite;
      margin: 3rem auto;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    .empty-state {
      text-align: center;
      padding: 4rem 1rem;
      color: var(--text-muted);
    }
    .empty-icon { font-size: 3rem; margin-bottom: 0.75rem; opacity: 0.7; }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="logo-badge">DLNA</div>
      <div>
        <h1>Immich Media Explorer</h1>
      </div>
    </div>
    <div class="server-status">
      <div class="status-dot"></div>
      <span id="server-url-label">Connected</span>
    </div>
    <div class="controls">
      <button class="btn" id="btn-refresh" title="Reload current folder">🔄 Refresh</button>
      <button class="btn" id="btn-back" title="Go back">⬅ Back</button>
    </div>
  </header>

  <div class="nav-bar">
    <div class="breadcrumbs" id="breadcrumbs">
      <span class="crumb current">Home</span>
    </div>
    <div style="font-size: 0.82rem; color: var(--text-muted);" id="item-count-label"></div>
  </div>

  <main>
    <div id="loading" class="spinner" style="display: none;"></div>

    <div id="container-section" style="display: none;">
      <div class="section-title">Folders & Categories <span id="container-count">0</span></div>
      <div class="container-grid" id="containers-view"></div>
    </div>

    <div id="media-section" style="display: none;">
      <div class="section-title">Photos & Videos <span id="media-count">0</span></div>
      <div class="media-grid" id="media-view"></div>
    </div>

    <div style="text-align: center; margin-top: 1.5rem; display: none;" id="load-more-container">
      <button class="btn btn-primary" id="btn-load-more" style="display: none;">Load More</button>
    </div>

    <div id="empty-state" class="empty-state" style="display: none;">
      <div class="empty-icon">📁</div>
      <h3>This folder is empty</h3>
      <p style="margin-top: 0.35rem; font-size: 0.9rem;">No subfolders or media items found.</p>
    </div>
  </main>

  <!-- Lightbox Modal -->
  <div class="modal" id="lightbox">
    <button class="modal-close" id="modal-close" title="Close (Esc)">✕</button>
    <button class="modal-nav prev" id="modal-prev" title="Previous (Left arrow)">‹</button>
    <button class="modal-nav next" id="modal-next" title="Next (Right arrow)">›</button>
    <div class="modal-content" id="modal-content"></div>
    <div class="modal-bar">
      <span id="modal-title"></span>
      <a class="btn" id="modal-dl-btn" href="#" target="_blank" download>Open Full Res ↗</a>
    </div>
  </div>

  <script>
    const state = {
      history: [{ id: "0", title: "Home" }],
      currentContainers: [],
      currentMediaItems: [],
      lightboxIndex: -1,
      pageStart: 0,
      pageSize: 100,
      totalMatches: 0
    };

    const breadcrumbsEl = document.getElementById("breadcrumbs");
    const containersViewEl = document.getElementById("containers-view");
    const mediaViewEl = document.getElementById("media-view");
    const containerSectionEl = document.getElementById("container-section");
    const mediaSectionEl = document.getElementById("media-section");
    const loadMoreContainerEl = document.getElementById("load-more-container");
    const emptyStateEl = document.getElementById("empty-state");
    const loadingEl = document.getElementById("loading");
    const containerCountEl = document.getElementById("container-count");
    const mediaCountEl = document.getElementById("media-count");
    const itemCountLabelEl = document.getElementById("item-count-label");
    const btnLoadMore = document.getElementById("btn-load-more");
    const lightboxEl = document.getElementById("lightbox");
    const modalContentEl = document.getElementById("modal-content");
    const modalTitleEl = document.getElementById("modal-title");
    const modalDlBtnEl = document.getElementById("modal-dl-btn");

    function renderBreadcrumbs() {
      breadcrumbsEl.innerHTML = "";
      state.history.forEach((step, idx) => {
        const isCurrent = idx === state.history.length - 1;
        const crumb = document.createElement("span");
        crumb.className = `crumb ${isCurrent ? "current" : ""}`;
        crumb.textContent = step.title;
        if (!isCurrent) {
          crumb.onclick = () => {
            state.history = state.history.slice(0, idx + 1);
            navigateToCurrent();
          };
        }
        breadcrumbsEl.appendChild(crumb);
        if (!isCurrent) {
          const sep = document.createElement("span");
          sep.className = "sep";
          sep.textContent = "›";
          breadcrumbsEl.appendChild(sep);
        }
      });
    }

    async function loadFolder(objectId, start = 0, append = false) {
      if (!append) {
        loadingEl.style.display = "block";
        containerSectionEl.style.display = "none";
        mediaSectionEl.style.display = "none";
        loadMoreContainerEl.style.display = "none";
        emptyStateEl.style.display = "none";
        state.currentContainers = [];
        state.currentMediaItems = [];
        mediaViewEl.innerHTML = "";
        containersViewEl.innerHTML = "";
      }

      try {
        const resp = await fetch(`/api/browse?id=${encodeURIComponent(objectId)}&start=${start}&count=${state.pageSize}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        state.pageStart = start;
        state.totalMatches = data.total || 0;

        // Render Containers
        const containers = data.containers || [];
        if (containers.length > 0) {
          containerSectionEl.style.display = "block";
          containers.forEach(c => {
            state.currentContainers.push(c);
            const card = document.createElement("div");
            card.className = "container-card";
            card.onclick = () => {
              state.history.push({ id: c.id, title: c.title });
              navigateToCurrent();
            };

            // Determine icon or cover
            if (c.art) {
              const isPerson = c.id.startsWith("person:") || c.id.includes(":person:");
              const img = document.createElement("img");
              img.className = isPerson ? "folder-art" : "folder-art square";
              img.src = (c.art.startsWith(window.location.origin) || c.art.startsWith("/"))
                ? c.art
                : `/api/proxy?url=${encodeURIComponent(c.art)}`;
              img.loading = "lazy";
              img.onerror = () => {
                img.replaceWith(createFallbackIcon(c.id));
              };
              card.appendChild(img);
            } else {
              card.appendChild(createFallbackIcon(c.id));
            }

            const titleEl = document.createElement("div");
            titleEl.className = "container-title";
            titleEl.textContent = c.title;
            card.appendChild(titleEl);

            if (c.childCount) {
              const subEl = document.createElement("div");
              subEl.className = "container-sub";
              subEl.textContent = `${c.childCount} items`;
              card.appendChild(subEl);
            }

            containersViewEl.appendChild(card);
          });
        }
        containerCountEl.textContent = state.currentContainers.length;

        // Render Media Items
        const items = data.items || [];
        if (items.length > 0) {
          mediaSectionEl.style.display = "block";
          items.forEach(item => {
            const index = state.currentMediaItems.length;
            state.currentMediaItems.push(item);

            const card = document.createElement("div");
            card.className = "media-card";
            card.onclick = () => openLightbox(index);

            const img = document.createElement("img");
            img.className = "media-thumb";
            const thumbUrl = item.thumb || item.res;
            img.src = (thumbUrl.startsWith(window.location.origin) || thumbUrl.startsWith("/"))
              ? thumbUrl
              : `/api/proxy?url=${encodeURIComponent(thumbUrl)}`;
            img.loading = "lazy";
            img.alt = item.title;
            card.appendChild(img);

            if (item.isVideo) {
              const badge = document.createElement("div");
              badge.className = "video-badge";
              badge.innerHTML = "▶ Video";
              card.appendChild(badge);
            }

            const overlay = document.createElement("div");
            overlay.className = "media-overlay";
            const nameEl = document.createElement("div");
            nameEl.className = "media-title";
            nameEl.textContent = item.title;
            overlay.appendChild(nameEl);
            card.appendChild(overlay);

            mediaViewEl.appendChild(card);
          });
        }

        mediaCountEl.textContent = state.currentMediaItems.length;
        const totalLoaded = state.currentContainers.length + state.currentMediaItems.length;
        if (state.totalMatches > 0) {
          if (state.currentContainers.length > 0 && state.currentMediaItems.length === 0) {
            itemCountLabelEl.textContent = `Showing ${state.currentContainers.length} of ${state.totalMatches} folders`;
          } else if (state.currentContainers.length === 0 && state.currentMediaItems.length > 0) {
            itemCountLabelEl.textContent = `Showing ${state.currentMediaItems.length} of ${state.totalMatches} items`;
          } else {
            itemCountLabelEl.textContent = `Showing ${totalLoaded} of ${state.totalMatches} items`;
          }
        } else {
          itemCountLabelEl.textContent = "";
        }

        // Load More button
        if (totalLoaded < state.totalMatches) {
          loadMoreContainerEl.style.display = "block";
          btnLoadMore.style.display = "inline-block";
        } else {
          loadMoreContainerEl.style.display = "none";
          btnLoadMore.style.display = "none";
        }

        if (state.currentContainers.length === 0 && state.currentMediaItems.length === 0) {
          emptyStateEl.style.display = "block";
        }

      } catch (err) {
        alert("Failed to load folder: " + err.message);
      } finally {
        loadingEl.style.display = "none";
      }
    }

    function createFallbackIcon(id) {
      const el = document.createElement("div");
      el.className = "folder-icon";
      if (id === "people" || id.startsWith("people:")) el.textContent = "👥";
      else if (id.startsWith("person:")) el.textContent = "👤";
      else if (id === "favorites") el.textContent = "⭐";
      else if (id === "albums" || id.startsWith("album:")) el.textContent = "🖼️";
      else if (id === "tags" || id.startsWith("tag:") || id.startsWith("tag_group:") || id === "tags:all") el.textContent = "🏷️";
      else if (id === "years" || id.startsWith("year:") || id.startsWith("month:")) el.textContent = "📅";
      else el.textContent = "📁";
      return el;
    }

    function navigateToCurrent() {
      renderBreadcrumbs();
      const current = state.history[state.history.length - 1];
      loadFolder(current.id, 0, false);
    }

    function openLightbox(index) {
      if (index < 0 || index >= state.currentMediaItems.length) return;
      state.lightboxIndex = index;
      const item = state.currentMediaItems[index];

      modalTitleEl.textContent = `${item.title} (${index + 1} / ${state.currentMediaItems.length})`;
      const proxyUrl = (item.res.startsWith(window.location.origin) || item.res.startsWith("/"))
        ? item.res
        : `/api/proxy?url=${encodeURIComponent(item.res)}`;
      modalDlBtnEl.href = proxyUrl;

      modalContentEl.innerHTML = "";
      if (item.isVideo) {
        const video = document.createElement("video");
        video.className = "modal-video";
        video.src = proxyUrl;
        video.controls = true;
        video.autoplay = true;
        modalContentEl.appendChild(video);
      } else {
        const img = document.createElement("img");
        img.className = "modal-img";
        img.src = proxyUrl;
        modalContentEl.appendChild(img);
      }

      lightboxEl.classList.add("active");
    }

    function closeLightbox() {
      lightboxEl.classList.remove("active");
      modalContentEl.innerHTML = "";
      state.lightboxIndex = -1;
    }

    // Keyboard controls
    document.addEventListener("keydown", (e) => {
      if (!lightboxEl.classList.contains("active")) return;
      if (e.key === "Escape") closeLightbox();
      if (e.key === "ArrowLeft") openLightbox(state.lightboxIndex - 1);
      if (e.key === "ArrowRight") openLightbox(state.lightboxIndex + 1);
    });

    document.getElementById("modal-close").onclick = closeLightbox;
    document.getElementById("modal-prev").onclick = () => openLightbox(state.lightboxIndex - 1);
    document.getElementById("modal-next").onclick = () => openLightbox(state.lightboxIndex + 1);
    lightboxEl.onclick = (e) => {
      if (e.target === lightboxEl) closeLightbox();
    };

    document.getElementById("btn-back").onclick = () => {
      if (state.history.length > 1) {
        state.history.pop();
        navigateToCurrent();
      }
    };
    document.getElementById("btn-refresh").onclick = () => navigateToCurrent();
    btnLoadMore.onclick = () => {
      const current = state.history[state.history.length - 1];
      const totalLoaded = state.currentContainers.length + state.currentMediaItems.length;
      loadFolder(current.id, totalLoaded, true);
    };

    // Initial load
    navigateToCurrent();
  </script>
</body>
</html>
"""


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def create_handler(target_server: str):
    class DLNAExplorerHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Suppress noisy standard logs unless error
            if args and str(args[1]).startswith(("4", "5")):
                sys.stderr.write(f"[HTTP] {fmt % args}\n")

        def _send_cors_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")

        def do_OPTIONS(self):
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_cors_headers()
            self.end_headers()

        def do_GET(self):
            parsed_path = urlparse(self.path)

            if parsed_path.path in {"/", "/index.html"}:
                body = HTML_PAGE.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(body)
                return

            if parsed_path.path == "/api/browse":
                qs = parse_qs(parsed_path.query)
                object_id = qs.get("id", ["0"])[0]
                start = int(qs.get("start", ["0"])[0])
                count = int(qs.get("count", ["50"])[0])

                try:
                    data = self._browse_dlna(object_id, start, count)
                    body = json.dumps(data).encode("utf-8")
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(body)
                except Exception as exc:
                    err = json.dumps({"error": str(exc)}).encode("utf-8")
                    self.send_response(HTTPStatus.BAD_GATEWAY)
                    self.send_header("Content-Type", "application/json")
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(err)
                return

            if parsed_path.path == "/api/proxy":
                qs = parse_qs(parsed_path.query)
                media_url = qs.get("url", [""])[0]
                if not media_url:
                    self.send_error(HTTPStatus.BAD_REQUEST, "Missing 'url' parameter")
                    return

                try:
                    req_headers = {}
                    range_hdr = self.headers.get("Range")
                    if range_hdr:
                        req_headers["Range"] = range_hdr

                    req = urllib.request.Request(media_url, headers=req_headers)
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        self.send_response(resp.status)
                        for k, v in resp.headers.items():
                            if k.lower() in {"content-type", "content-length", "content-range", "accept-ranges", "cache-control"}:
                                self.send_header(k, v)
                        self._send_cors_headers()
                        self.end_headers()

                        # Stream body
                        while chunk := resp.read(64 * 1024):
                            self.wfile.write(chunk)
                except Exception as exc:
                    self.send_error(HTTPStatus.BAD_GATEWAY, f"Proxy failed: {exc}")
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

        def _browse_dlna(self, object_id: str, start: int, count: int) -> dict:
            soap_body = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
  <s:Body>
    <u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1">
      <ObjectID>{object_id}</ObjectID>
      <BrowseFlag>BrowseDirectChildren</BrowseFlag>
      <Filter>*</Filter>
      <StartingIndex>{start}</StartingIndex>
      <RequestedCount>{count}</RequestedCount>
      <SortCriteria></SortCriteria>
    </u:Browse>
  </s:Body>
</s:Envelope>"""

            req = urllib.request.Request(
                f"{target_server.rstrip('/')}/ContentDirectory/control",
                data=soap_body.encode("utf-8"),
                headers={
                    "SOAPAction": '"urn:schemas-upnp-org:service:ContentDirectory:1#Browse"',
                    "Content-Type": 'text/xml; charset="utf-8"',
                },
            )

            with urllib.request.urlopen(req, timeout=15) as resp:
                xml_raw = resp.read()

            root = ET.fromstring(xml_raw)
            result_node = root.find(".//{urn:schemas-upnp-org:service:ContentDirectory:1}BrowseResponse/Result")
            total_node = root.find(".//{urn:schemas-upnp-org:service:ContentDirectory:1}BrowseResponse/TotalMatches")
            total = int(total_node.text) if total_node is not None and total_node.text else 0

            containers = []
            items = []

            if result_node is not None and result_node.text:
                didl = ET.fromstring(result_node.text)
                for elem in didl:
                    tag = elem.tag.split("}")[-1]
                    elem_id = elem.attrib.get("id", "")
                    title_node = elem.find("{http://purl.org/dc/elements/1.1/}title")
                    title = title_node.text if title_node is not None and title_node.text else elem_id
                    art_node = elem.find("{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI")
                    art = art_node.text if art_node is not None and art_node.text else ""

                    if tag == "container":
                        child_count_attr = elem.attrib.get("childCount")
                        containers.append({
                            "id": elem_id,
                            "title": title,
                            "art": art,
                            "childCount": int(child_count_attr) if child_count_attr else None,
                        })
                    elif tag == "item":
                        class_node = elem.find("{urn:schemas-upnp-org:metadata-1-0/upnp/}class")
                        is_video = "video" in (class_node.text if class_node is not None and class_node.text else "").lower()
                        res_node = elem.find("{urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/}res")
                        res_url = res_node.text if res_node is not None else ""
                        items.append({
                            "id": elem_id,
                            "title": title,
                            "thumb": art,
                            "res": res_url,
                            "isVideo": is_video,
                        })

            return {
                "id": object_id,
                "total": total,
                "containers": containers,
                "items": items,
            }

    return DLNAExplorerHandler


def main():
    parser = argparse.ArgumentParser(description="Immich DLNA Graphical Web Explorer")
    parser.add_argument("--server", default=DEFAULT_SERVER, help=f"Immich DLNA Server URL (default: {DEFAULT_SERVER})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Local web port (default: {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="Do not open web browser automatically")
    args = parser.parse_args()

    server_url = args.server.rstrip("/")
    local_url = f"http://localhost:{args.port}"

    print("=" * 65)
    print(" Immich DLNA Graphical Web Explorer")
    print(f" Target DLNA Server: {server_url}")
    print(f" Web Explorer URL:   {local_url}")
    print("=" * 65)

    handler_class = create_handler(server_url)
    try:
        httpd = ThreadedHTTPServer(("127.0.0.1", args.port), handler_class)
    except OSError as e:
        print(f"[!] Port {args.port} is already in use. Trying port {args.port + 1}...")
        httpd = ThreadedHTTPServer(("127.0.0.1", args.port + 1), handler_class)
        local_url = f"http://localhost:{args.port + 1}"

    print(f"[+] Server started successfully on {local_url}")
    if not args.no_browser:
        print(f"[+] Opening {local_url} in your default web browser...")
        webbrowser.open(local_url)

    print("[*] Press Ctrl+C in this terminal to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Stopping DLNA Web Explorer. Goodbye!")
        httpd.server_close()


if __name__ == "__main__":
    main()
