import sys
import os

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import ctypes

_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\TurkceDictationMutex")
if ctypes.windll.kernel32.GetLastError() == 183:
    sys.exit(0)

if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(os.devnull, "w")

import threading
import time
import tkinter as tk
import numpy as np
import sounddevice as sd
import keyboard
from faster_whisper import WhisperModel

MODEL_SIZE = "small"
LANGUAGE = "tr"
SAMPLE_RATE = 16000
BEAM_SIZE = 5
VAD_FILTER = True
SILENCE_THRESHOLD = 0.01
INITIAL_PROMPT = "Merhaba, bugün toplantıda projeyi konuştuk. Sonuçlar gayet iyi, değil mi?"
CHUNK_SECONDS = 3
PANEL_WIDTH = 380
PANEL_HEIGHT = 300

TITLE = "Sesli Yazma"
BG = "#121212"
BG_LIGHT = "#2a1215"
FG = "#ffffff"
FG_DIM = "#b3a3a5"
ACCENT = "#e53935"
ACCENT_RED = "#ff5252"
SUCCESS = "#ffffff"
BORDER = "#7f1d1d"

recording = False
frames = []
frames_lock = threading.Lock()
app = None

model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

_current_rms = 0.0


def audio_callback(indata, blocksize, time_info, status):
    global _current_rms
    _current_rms = float(np.sqrt(np.mean(indata ** 2)))
    if recording:
        with frames_lock:
            frames.append(indata.copy())


stream = None


def open_stream():
    global stream
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1,
        dtype="float32", blocksize=1024,
        callback=audio_callback,
    )
    stream.start()


def close_stream():
    global stream, _current_rms
    if stream is not None:
        try:
            stream.stop()
            stream.close()
        except Exception:
            pass
        stream = None
    _current_rms = 0.0


def trim_silence(audio, threshold=SILENCE_THRESHOLD, chunk=1600):
    start = 0
    for i in range(0, len(audio), chunk):
        if np.sqrt(np.mean(audio[i:i + chunk] ** 2)) > threshold:
            start = i
            break
    end = len(audio)
    for i in range(len(audio), 0, -chunk):
        if np.sqrt(np.mean(audio[max(0, i - chunk):i] ** 2)) > threshold:
            end = i
            break
    return audio[start:end] if end > start else audio


def transcribe(audio):
    segments, _ = model.transcribe(
        audio, language=LANGUAGE,
        beam_size=BEAM_SIZE, vad_filter=VAD_FILTER,
        initial_prompt=INITIAL_PROMPT,
    )
    return " ".join(s.text for s in segments).strip()


class StreamWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.committed_text = []
        self.last_chunk_index = 0
        self.stop_event = threading.Event()
        self.finish_event = threading.Event()
        self.final_text = ""

    def run(self):
        while not self.stop_event.is_set():
            self.stop_event.wait(timeout=CHUNK_SECONDS)
            if self.stop_event.is_set():
                break
            self._transcribe_new_chunk()

        self._transcribe_final()
        self.finish_event.set()

    def _transcribe_new_chunk(self):
        with frames_lock:
            current_len = len(frames)
            if current_len <= self.last_chunk_index:
                return
            chunk_frames = frames[self.last_chunk_index:current_len]
        self.last_chunk_index = current_len

        audio = trim_silence(np.concatenate(chunk_frames, axis=0).flatten())
        if len(audio) < SAMPLE_RATE * 0.3:
            return

        try:
            text = transcribe(audio)
        except Exception:
            text = ""

        if text:
            self.committed_text.append(text)
            full = " ".join(self.committed_text)
            if app:
                app.root.after(0, app.on_live_text, full)

    def _transcribe_final(self):
        with frames_lock:
            if not frames:
                self.final_text = " ".join(self.committed_text)
                return
            all_audio = np.concatenate(frames, axis=0).flatten()

        all_audio = trim_silence(all_audio)
        if len(all_audio) < SAMPLE_RATE * 0.3:
            self.final_text = " ".join(self.committed_text)
            return

        if app:
            app.root.after(0, app.on_status, "⏳ Son düzeltme yapılıyor...", FG_DIM)

        try:
            text = transcribe(all_audio)
        except Exception:
            text = ""

        self.final_text = text if text else " ".join(self.committed_text)

    def request_stop(self):
        self.stop_event.set()


def paste_text(text, root):
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    time.sleep(0.05)
    keyboard.send("ctrl+v")


tray_icon = None


def setup_tray(root):
    global tray_icon
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        return

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, 56, 56], fill=ACCENT)
    d.rectangle([26, 16, 38, 40], fill="white")
    d.ellipse([22, 32, 42, 48], fill="white")

    def on_quit(icon, item):
        icon.stop()
        root.after(0, root.destroy)

    menu = pystray.Menu(pystray.MenuItem("Çıkış", on_quit))
    tray_icon = pystray.Icon("dictation", img, f"{TITLE} (Win+H)", menu)
    threading.Thread(target=tray_icon.run, daemon=True).start()


class WinHotkeyHook(threading.Thread):
    """Düşük seviye klavye kancası.

    Windows tuşunu asla bastırmaz; yalnızca Win basılıyken H'yi yutar
    (böylece Windows'un kendi Win+H sesli yazması açılmaz). Win+V, tek Win,
    diğer tüm Win kombinasyonları normal çalışmaya devam eder. Win+H'den
    sonra Başlat menüsünün açılmaması için Win tuşunu bir Ctrl dokunuşuyla
    maskeler.
    """

    def __init__(self, on_toggle, on_escape):
        super().__init__(daemon=True)
        self.on_toggle = on_toggle
        self.on_escape = on_escape
        self._win_down = False
        self._h_consumed = False
        self._proc = None

    def run(self):
        from ctypes import wintypes

        WH_KEYBOARD_LL = 13
        WM_KEYDOWN, WM_KEYUP = 0x0100, 0x0101
        WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0104, 0x0105
        VK_LWIN, VK_RWIN, VK_H, VK_ESCAPE, VK_CONTROL = 0x5B, 0x5C, 0x48, 0x1B, 0x11
        KEYEVENTF_KEYUP = 0x0002

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        HOOKPROC = ctypes.CFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                                    wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int,
                                          wintypes.WPARAM, wintypes.LPARAM]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                             wintypes.HINSTANCE, wintypes.DWORD]

        def ll(nCode, wParam, lParam):
            if nCode == 0:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk = kb.vkCode
                down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
                up = wParam in (WM_KEYUP, WM_SYSKEYUP)
                if vk in (VK_LWIN, VK_RWIN):
                    if down:
                        self._win_down = True
                    elif up:
                        self._win_down = False
                        self._h_consumed = False
                elif vk == VK_H and self._win_down:
                    if down:
                        if not self._h_consumed:
                            self._h_consumed = True
                            # Win tuşunu maskele ki Başlat menüsü açılmasın
                            user32.keybd_event(VK_CONTROL, 0, 0, 0)
                            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
                            self.on_toggle()
                        return 1
                    elif up:
                        self._h_consumed = False
                        return 1
                elif vk == VK_ESCAPE and down:
                    self.on_escape()
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        self._proc = HOOKPROC(ll)
        self._hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._proc, kernel32.GetModuleHandleW(None), 0)

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


class DictationPanel:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.95)
        self.root.configure(bg=BG)

        self.panel_visible = False
        self.is_recording = False
        self.is_finishing = False
        self.record_start = 0.0
        self._timer_id = None
        self._level_id = None
        self._finish_poll_id = None
        self._focus_target = None
        self.stream_worker = None

        self._build_panel()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        setup_tray(self.root)

        self._kbhook = WinHotkeyHook(self._on_hotkey, self._on_escape)
        self._kbhook.start()

    def _build_panel(self):
        f = tk.Frame(self.root, bg=BG, highlightbackground=BORDER,
                     highlightthickness=1, padx=16, pady=12)
        f.pack(fill="both", expand=True)

        top = tk.Frame(f, bg=BG)
        top.pack(fill="x")

        self.title_label = tk.Label(
            top, text=TITLE, font=("Segoe UI Semibold", 11),
            fg=FG, bg=BG, anchor="w",
        )
        self.title_label.pack(side="left")

        self.timer_label = tk.Label(
            top, text="0:00", font=("Segoe UI", 10),
            fg=FG_DIM, bg=BG, anchor="e",
        )
        self.timer_label.pack(side="right")

        self.level_canvas = tk.Canvas(
            f, height=6, bg=BG_LIGHT, highlightthickness=0, bd=0,
        )
        self.level_canvas.pack(fill="x", pady=(10, 6))

        self.status_label = tk.Label(
            f, text="Dinliyor...", font=("Segoe UI", 10),
            fg=ACCENT, bg=BG, anchor="w",
        )
        self.status_label.pack(fill="x")

        # Butonlar en alta sabitlenir. Metin alanindan ONCE "bottom"a
        # pack'lendigi icin metin ne kadar uzarsa uzasin her zaman gorunur.
        btn_frame = tk.Frame(f, bg=BG)
        btn_frame.pack(side="bottom", fill="x", pady=(10, 0))

        self.stop_btn = tk.Button(
            btn_frame, text="✓ Bitir", font=("Segoe UI", 9),
            fg=FG, bg=BG_LIGHT, activebackground=BORDER, activeforeground=FG,
            bd=0, padx=12, pady=4, cursor="hand2",
            command=self._on_stop_click,
        )
        self.stop_btn.pack(side="left")

        self.cancel_btn = tk.Button(
            btn_frame, text="✕ İptal", font=("Segoe UI", 9),
            fg=ACCENT_RED, bg=BG_LIGHT, activebackground=BORDER,
            activeforeground=ACCENT_RED, bd=0, padx=12, pady=4,
            cursor="hand2", command=self._on_cancel_click,
        )
        self.cancel_btn.pack(side="right")

        # Kaydirilabilir metin alani: status ile butonlar arasini doldurur.
        text_wrap = tk.Frame(f, bg=BG)
        text_wrap.pack(fill="both", expand=True, pady=(4, 0))

        scrollbar = tk.Scrollbar(
            text_wrap, orient="vertical", width=8, bd=0,
            bg=BG_LIGHT, troughcolor=BG, activebackground=BORDER,
            highlightthickness=0,
        )
        scrollbar.pack(side="right", fill="y")

        self.text_widget = tk.Text(
            text_wrap, font=("Segoe UI", 9), fg=FG, bg=BG,
            wrap="word", bd=0, highlightthickness=0, padx=0, pady=0,
            insertwidth=0, cursor="arrow", state="disabled",
            yscrollcommand=scrollbar.set,
        )
        self.text_widget.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.text_widget.yview)

        def _on_wheel(event):
            self.text_widget.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        self.text_widget.bind("<MouseWheel>", _on_wheel)

    def _set_text(self, text):
        self.text_widget.config(state="normal")
        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", text)
        self.text_widget.config(state="disabled")
        self.text_widget.see("end")

    def _position_panel(self):
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            cx, cy = pt.x, pt.y
        else:
            cx, cy = self.root.winfo_pointerx(), self.root.winfo_pointery()

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        x = cx + 20
        y = cy + 20
        if x + PANEL_WIDTH > sw:
            x = cx - PANEL_WIDTH - 20
        if y + PANEL_HEIGHT > sh:
            y = cy - PANEL_HEIGHT - 20

        self.root.geometry(f"{PANEL_WIDTH}x{PANEL_HEIGHT}+{x}+{y}")

    def show_panel(self):
        self._position_panel()
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.panel_visible = True
        self._restore_focus()

    def hide_panel(self):
        self.root.withdraw()
        self.panel_visible = False
        for attr in ("_timer_id", "_level_id", "_finish_poll_id"):
            after_id = getattr(self, attr)
            if after_id:
                self.root.after_cancel(after_id)
                setattr(self, attr, None)

    def _save_focus(self):
        self._focus_target = ctypes.windll.user32.GetForegroundWindow()

    def _restore_focus(self):
        if self._focus_target:
            ctypes.windll.user32.SetForegroundWindow(self._focus_target)

    def start_recording(self):
        global recording, frames
        self._save_focus()
        with frames_lock:
            frames = []
        try:
            open_stream()
        except Exception:
            self.status_label.config(text="Mikrofon açılamadı", fg=ACCENT_RED)
            self._set_text("")
            self.show_panel()
            self.root.after(1500, self.hide_panel)
            return
        recording = True
        self.is_recording = True
        self.is_finishing = False
        self.record_start = time.time()

        self.status_label.config(text="🎙 Dinliyor — konuştukça metin gelecek...", fg=ACCENT)
        self._set_text("")
        self.timer_label.config(text="0:00")
        self.stop_btn.config(state="normal", text="✓ Bitir")

        self.stream_worker = StreamWorker()
        self.stream_worker.start()

        self.show_panel()
        self._update_timer()
        self._update_level()

    def stop_recording(self):
        global recording
        if self.is_finishing:
            return
        recording = False
        close_stream()
        self.is_recording = False
        self.is_finishing = True

        self.status_label.config(text="⏳ Tamamlanıyor...", fg=FG_DIM)
        self.stop_btn.config(state="disabled")
        self.level_canvas.delete("all")

        if self.stream_worker:
            self.stream_worker.request_stop()
            self._poll_finish()

    def _poll_finish(self):
        if self.stream_worker and self.stream_worker.finish_event.is_set():
            text = self.stream_worker.final_text.strip()
            self.stream_worker = None
            self.is_finishing = False
            if text:
                self._set_text(text)
                self.status_label.config(text="✓ Yapıştırıldı", fg=SUCCESS)
                self._restore_focus()
                self.root.after(50, lambda: self._do_paste(text))
            else:
                self.status_label.config(text="Ses anlaşılamadı", fg=ACCENT_RED)
                self.root.after(1200, self.hide_panel)
        else:
            self._finish_poll_id = self.root.after(100, self._poll_finish)

    def cancel_recording(self):
        global recording
        recording = False
        close_stream()
        self.is_recording = False
        self.is_finishing = False
        if self.stream_worker:
            self.stream_worker.request_stop()
            self.stream_worker = None
        with frames_lock:
            frames.clear()
        self.hide_panel()

    def on_live_text(self, text):
        self._set_text(text)

    def on_status(self, text, color):
        self.status_label.config(text=text, fg=color)

    def _do_paste(self, text):
        paste_text(text, self.root)
        self.root.after(800, self.hide_panel)

    def _update_timer(self):
        if not self.is_recording:
            return
        elapsed = int(time.time() - self.record_start)
        m, s = divmod(elapsed, 60)
        self.timer_label.config(text=f"{m}:{s:02d}")
        self._timer_id = self.root.after(500, self._update_timer)

    def _update_level(self):
        if not self.is_recording:
            self.level_canvas.delete("all")
            return
        w = self.level_canvas.winfo_width()
        bar_w = int(w * min(_current_rms * 8, 1.0))
        self.level_canvas.delete("all")
        if bar_w > 0:
            self.level_canvas.create_rectangle(0, 0, bar_w, 6, fill=ACCENT, outline="")
        self._level_id = self.root.after(60, self._update_level)

    def _on_hotkey(self):
        self.root.after(0, self._toggle)

    def _on_escape(self):
        if self.is_recording or self.panel_visible:
            self.root.after(0, self.cancel_recording)

    def _toggle(self):
        if self.is_finishing:
            return
        if not self.is_recording:
            self.start_recording()
        else:
            self.stop_recording()

    def _on_stop_click(self):
        if self.is_recording:
            self.stop_recording()

    def _on_cancel_click(self):
        self.cancel_recording()

    def _on_close(self):
        self.cancel_recording()
        if tray_icon:
            tray_icon.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = DictationPanel()
    app.run()
