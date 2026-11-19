"""
E.D.I.T.H.  -  Even Dead, I'm The Hero
Hand-gesture + voice + typed-command control for your computer.

INSTALL (Python 3.9-3.12):
    pip install opencv-python mediapipe pyautogui numpy psutil SpeechRecognition pyttsx3 pyaudio

RUN:
    python edith.py

GESTURES (use your right or left hand, palm facing the camera)
    Move hand ........ moves the mouse
    Fist ............. press & hold left mouse button (release = open hand) -> click / drag
    Pinch (thumb+index) right click
    Peace sign (V) ... scroll: move hand up / down

KEYS in the EDITH window:  M = mouse on/off   V = voice on/off   Q / ESC = quit
You can also TYPE commands in the terminal or SAY them (say "EDITH" first if you like).
"""
import collections, datetime, math, os, platform, queue, random, re, subprocess, sys, threading, time, webbrowser
import urllib.request
import cv2, numpy as np, mediapipe as mp, pyautogui

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
CONNECTIONS = [(0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9), (9, 10), (10, 11), (11, 12),
               (9, 13), (13, 14), (14, 15), (15, 16), (13, 17), (17, 18), (18, 19), (19, 20), (0, 17)]

try: import speech_recognition as sr
except ImportError: sr = None
try: import psutil
except ImportError: psutil = None
try: import pyttsx3
except ImportError: pyttsx3 = None

OS = platform.system()
W, H = 1100, 620
LOG = collections.deque(maxlen=6)
CMDS = queue.Queue()
FLAGS = {"run": True, "voice": True, "mouse": True}

# ---------------------------------------------------------------- apps & sites
APPS = {  # name: (Windows, macOS, Linux)
    "chrome": ("chrome", "Google Chrome", "google-chrome"),
    "edge": ("msedge", "Microsoft Edge", "microsoft-edge"),
    "firefox": ("firefox", "Firefox", "firefox"),
    "notepad": ("notepad", "TextEdit", "gedit"),
    "calculator": ("calc", "Calculator", "gnome-calculator"),
    "explorer": ("explorer", "Finder", "nautilus"),
    "files": ("explorer", "Finder", "nautilus"),
    "terminal": ("cmd", "Terminal", "gnome-terminal"),
    "code": ("code", "Visual Studio Code", "code"),
    "vscode": ("code", "Visual Studio Code", "code"),
    "spotify": ("spotify", "Spotify", "spotify"),
    "word": ("winword", "Microsoft Word", "libreoffice --writer"),
    "excel": ("excel", "Microsoft Excel", "libreoffice --calc"),
    "powerpoint": ("powerpnt", "Microsoft PowerPoint", "libreoffice --impress"),
    "paint": ("mspaint", "Preview", "gimp"),
    "settings": ("ms-settings:", "System Preferences", "gnome-control-center"),
    "task manager": ("taskmgr", "Activity Monitor", "gnome-system-monitor"),
    "discord": ("discord", "Discord", "discord"),
    "whatsapp": ("whatsapp:", "WhatsApp", "whatsapp-for-linux"),
}
SITES = {
    "google": "https://www.google.com/search?q={}", "youtube": "https://www.youtube.com/results?search_query={}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={}", "github": "https://github.com/search?q={}",
    "amazon": "https://www.amazon.in/s?k={}", "flipkart": "https://www.flipkart.com/search?q={}",
    "maps": "https://www.google.com/maps/search/{}", "reddit": "https://www.reddit.com/search/?q={}",
    "stackoverflow": "https://stackoverflow.com/search?q={}", "images": "https://www.google.com/search?tbm=isch&q={}",
    "news": "https://news.google.com/search?q={}", "chatgpt": "https://chatgpt.com/", "claude": "https://claude.ai/",
    "gmail": "https://mail.google.com/", "netflix": "https://www.netflix.com/",
}
HOME = {"youtube": "https://www.youtube.com", "github": "https://github.com", "gmail": "https://mail.google.com",
        "google": "https://www.google.com", "netflix": "https://www.netflix.com", "claude": "https://claude.ai",
        "chatgpt": "https://chatgpt.com", "reddit": "https://www.reddit.com", "amazon": "https://www.amazon.in",
        "wikipedia": "https://www.wikipedia.org", "flipkart": "https://www.flipkart.com", "maps": "https://maps.google.com"}


def say(msg, speak=True):
    LOG.append(msg); print("EDITH>", msg)
    if speak and pyttsx3:
        def _t():
            try: e = pyttsx3.init(); e.say(msg); e.runAndWait()
            except Exception: pass
        threading.Thread(target=_t, daemon=True).start()


def open_app(name):
    idx = {"Windows": 0, "Darwin": 1, "Linux": 2}[OS]
    cmd = APPS[name][idx]
    try:
        if OS == "Windows": subprocess.Popen(f'start "" {cmd}', shell=True)
        elif OS == "Darwin": subprocess.Popen(["open", "-a", cmd])
        else: subprocess.Popen(cmd.split())
        say(f"Opening {name}")
    except Exception as e:
        say(f"Couldn't open {name}")


def search(q, site="google"):
    site = site if site in SITES else "google"
    webbrowser.open(SITES[site].format(re.sub(r"\s+", "+", q.strip())))
    say(f"Searching {site} for {q}")


def hk(*k): pyautogui.hotkey(*k)
MOD = "command" if OS == "Darwin" else "ctrl"


def handle(raw):
    c = raw.lower().strip()
    c = re.sub(r"^(hey |ok |okay )?edith[, ]*", "", c).strip()
    if not c: return
    LOG.append("> " + c)
    # --- search / websites
    m = re.match(r"(?:search|find|look up|google)\s+(.+?)(?:\s+(?:on|in)\s+(\w+))?$", c)
    if m: return search(m.group(1), (m.group(2) or "google"))
    m = re.match(r"(?:play|youtube)\s+(.+)", c)
    if m: return search(m.group(1), "youtube")
    m = re.match(r"(wikipedia|github|amazon|flipkart|maps|reddit|stackoverflow|images|news)\s+(.+)", c)
    if m: return search(m.group(2), m.group(1))
    m = re.match(r"weather(?: in| for)?\s*(.*)", c)
    if m: return search("weather " + m.group(1), "google")
    # --- open apps / sites
    m = re.match(r"(?:open|launch|start)\s+(.+)", c)
    if m:
        t = m.group(1).strip()
        if t in APPS: return open_app(t)
        if t in HOME: webbrowser.open(HOME[t]); return say(f"Opening {t}")
        if "." in t: webbrowser.open("https://" + t.replace(" ", "")); return say(f"Opening {t}")
        return search(t)
    # --- keyboard / window control
    m = re.match(r"(?:type|write)\s+(.+)", c)
    if m: pyautogui.write(m.group(1), interval=0.02); return
    table = {
        "close window": lambda: hk("command", "w") if OS == "Darwin" else hk("alt", "f4"),
        "close tab": lambda: hk(MOD, "w"), "new tab": lambda: hk(MOD, "t"),
        "switch window": lambda: hk("command", "tab") if OS == "Darwin" else hk("alt", "tab"),
        "minimize": lambda: hk("command", "m") if OS == "Darwin" else hk("win", "down"),
        "maximize": lambda: hk("win", "up") if OS == "Windows" else None,
        "copy": lambda: hk(MOD, "c"), "paste": lambda: hk(MOD, "v"), "cut": lambda: hk(MOD, "x"),
        "undo": lambda: hk(MOD, "z"), "select all": lambda: hk(MOD, "a"), "save": lambda: hk(MOD, "s"),
        "refresh": lambda: hk(MOD, "r"), "go back": lambda: hk("alt", "left"),
        "press enter": lambda: pyautogui.press("enter"), "enter": lambda: pyautogui.press("enter"),
        "scroll down": lambda: pyautogui.scroll(-600), "scroll up": lambda: pyautogui.scroll(600),
        "volume up": lambda: [pyautogui.press("volumeup") for _ in range(5)],
        "volume down": lambda: [pyautogui.press("volumedown") for _ in range(5)],
        "mute": lambda: pyautogui.press("volumemute"),
        "pause": lambda: pyautogui.press("playpause"), "play music": lambda: pyautogui.press("playpause"),
        "next song": lambda: pyautogui.press("nexttrack"), "previous song": lambda: pyautogui.press("prevtrack"),
        "show desktop": lambda: hk("win", "d") if OS == "Windows" else hk("fn", "f11"),
    }
    for k, f in table.items():
        if c == k or c.startswith(k + " "):
            f(); return say(k.capitalize(), speak=False)
    if "screenshot" in c:
        p = os.path.join(os.path.expanduser("~"), f"edith_{int(time.time())}.png")
        pyautogui.screenshot(p); return say(f"Screenshot saved to {p}")
    if c in ("lock", "lock screen", "lock computer"):
        if OS == "Windows": subprocess.Popen("rundll32.exe user32.dll,LockWorkStation")
        elif OS == "Darwin": hk("ctrl", "command", "q")
        else: subprocess.Popen(["loginctl", "lock-session"])
        return
    if "time" in c: return say(datetime.datetime.now().strftime("It is %I:%M %p"))
    if "date" in c or "today" in c: return say(datetime.datetime.now().strftime("Today is %A, %d %B %Y"))
    if any(w in c for w in ("status", "battery", "cpu", "system")):
        if not psutil: return say("Install psutil for system status")
        b = psutil.sensors_battery()
        return say(f"CPU {psutil.cpu_percent()}%, RAM {psutil.virtual_memory().percent}%" + (f", battery {int(b.percent)}%" if b else ""))
    if "mouse off" in c or "stop mouse" in c: FLAGS["mouse"] = False; return say("Mouse control off")
    if "mouse on" in c or "start mouse" in c: FLAGS["mouse"] = True; return say("Mouse control on")
    if c in ("quit", "exit", "goodbye", "shut down edith"): FLAGS["run"] = False; return say("Goodbye")
    if c == "help":
        return say("Try: open chrome, search cats on youtube, weather bengaluru, type hello, screenshot, volume up")
    search(c)  # fallback: anything else becomes a web search


# ---------------------------------------------------------------- input threads
def voice_loop():
    if not sr: return LOG.append("Voice off (pip install SpeechRecognition pyaudio)")
    r = sr.Recognizer()
    try: mic = sr.Microphone()
    except Exception: return LOG.append("No microphone found")
    with mic as s: r.adjust_for_ambient_noise(s, 1)
    while FLAGS["run"]:
        if not FLAGS["voice"]: time.sleep(0.3); continue
        try:
            with mic as s: audio = r.listen(s, timeout=3, phrase_time_limit=6)
            CMDS.put(r.recognize_google(audio))
        except Exception: pass


def typed_loop():
    while FLAGS["run"]:
        try: CMDS.put(input())
        except EOFError: break


# ---------------------------------------------------------------- visuals
def jag(x0, y0, x1, y1, n=16, amp=26):
    pts = [(x0, y0)]
    for i in range(1, n):
        t = i / n
        pts.append((int(x0 + (x1 - x0) * t + random.randint(-amp, amp)), int(y0 + (y1 - y0) * t + random.randint(-6, 6))))
    return pts + [(x1, y1)]


def lightning(t, cx, cy):
    rays = np.zeros((H, W, 3), np.uint8)
    for i in range(22):  # rotating light rays from the centre
        a = t * 0.25 + i * math.pi / 11
        cv2.line(rays, (cx, cy), (int(cx + 900 * math.cos(a)), int(cy + 900 * math.sin(a))), (90, 55, 8), 2 + (i % 3) * 3, cv2.LINE_AA)
    rays = cv2.GaussianBlur(rays, (0, 0), 7)
    bolts = np.zeros((H, W, 3), np.uint8)
    random.seed(int(t * 9))
    for _ in range(5):
        end = (cx + random.randint(-170, 170), cy + random.randint(-90, 90))
        start = (random.randint(0, W), 0) if random.random() < .7 else (random.choice([0, W]), random.randint(0, H // 2))
        pts = np.array(jag(*start, *end), np.int32)
        cv2.polylines(bolts, [pts], False, (255, 190, 40), 5, cv2.LINE_AA)
        cv2.polylines(bolts, [pts], False, (255, 255, 255), 1, cv2.LINE_AA)
        k = random.randint(4, 10)  # side branch
        bx, by = pts[k]
        cv2.polylines(bolts, [np.array(jag(bx, by, bx + random.randint(-120, 120), by + random.randint(60, 160), 7, 14), np.int32)],
                      False, (255, 160, 30), 2, cv2.LINE_AA)
    random.seed()
    glow = cv2.GaussianBlur(bolts, (0, 0), 11)
    return cv2.add(cv2.add(rays, glow), bolts)


def make_title(cx, cy):
    t = np.zeros((H, W, 3), np.uint8)
    f = cv2.FONT_HERSHEY_DUPLEX

    def put(img, s, y, sc, col, th):
        (tw, _), _ = cv2.getTextSize(s, f, sc, th)
        cv2.putText(img, s, ((W - tw) // 2, y), f, sc, col, th, cv2.LINE_AA)
    put(t, "E.D.I.T.H.", cy + 25, 2.6, (255, 200, 60), 12)
    put(t, "EVEN DEAD, I'M THE HERO", cy + 85, 0.95, (255, 200, 60), 6)
    glow = cv2.GaussianBlur(t, (0, 0), 10)
    put(t, "E.D.I.T.H.", cy + 25, 2.6, (255, 255, 255), 4)
    put(t, "EVEN DEAD, I'M THE HERO", cy + 85, 0.95, (255, 255, 255), 2)
    return cv2.add(glow, t)


def rings(img, cx, cy, t):
    for r, sp, col in ((150, 40, (255, 200, 60)), (185, -25, (255, 150, 30)), (225, 15, (200, 120, 20))):
        for k in range(4):
            a = t * sp + k * 90
            cv2.ellipse(img, (cx, cy), (r + 70, int((r + 70) * .45)), 0, a, a + 55, col, 2, cv2.LINE_AA)


def panel(img, lines, x, y):
    ov = img.copy()
    cv2.rectangle(ov, (x - 8, y - 22), (x + 420, y + 18 * len(lines) + 2), (30, 15, 5), -1)
    cv2.addWeighted(ov, .55, img, .45, 0, img)
    for i, s in enumerate(lines):
        cv2.putText(img, s[:60], (x, y + i * 18), cv2.FONT_HERSHEY_SIMPLEX, .46, (255, 220, 120), 1, cv2.LINE_AA)


# ---------------------------------------------------------------- gestures
def fingers_up(lm):
    return [lm[t].y < lm[p].y for t, p in ((8, 6), (12, 10), (16, 14), (20, 18))]


def main():
    pyautogui.FAILSAFE = False; pyautogui.PAUSE = 0
    sw, sh = pyautogui.size()
    cap = cv2.VideoCapture(0)
    cap.set(3, 960); cap.set(4, 540)
    model = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hand_landmarker.task")
    if not os.path.exists(model):
        print("Downloading hand model (one time only)...")
        urllib.request.urlretrieve(MODEL_URL, model)
    vis = mp.tasks.vision
    hands = vis.HandLandmarker.create_from_options(vis.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=model),
        running_mode=vis.RunningMode.VIDEO, num_hands=1,
        min_hand_detection_confidence=.6, min_hand_presence_confidence=.6, min_tracking_confidence=.6))
    cx, cy = W // 2, H // 2 - 40
    title = make_title(cx, cy)
    threading.Thread(target=voice_loop, daemon=True).start()
    threading.Thread(target=typed_loop, daemon=True).start()
    orb = None
    orb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edith_orb.py")
    if os.path.exists(orb_path):
        orb = subprocess.Popen([sys.executable, orb_path])
    say("EDITH online. Say help for commands.")

    sx = sy = None; down = False; fist_n = open_n = 0
    last_rc = 0; prev_y = None; gesture = "NO HAND"; t0 = time.time(); M = .18; SMOOTH = 4
    cv2.namedWindow("E.D.I.T.H.", cv2.WINDOW_NORMAL); cv2.resizeWindow("E.D.I.T.H.", W, H)

    while FLAGS["run"]:
        ok, cam = cap.read()
        if not ok: break
        cam = cv2.flip(cam, 1)
        rgb = np.ascontiguousarray(cv2.cvtColor(cam, cv2.COLOR_BGR2RGB))
        res = hands.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int((time.time() - t0) * 1000))
        t = time.time() - t0
        navy = np.full((H, W, 3), (40, 18, 6), np.uint8)
        frame = cv2.addWeighted(cv2.resize(cam, (W, H)), .25, navy, .75, 0)
        frame = cv2.add(frame, lightning(t, cx, cy))
        rings(frame, cx, cy, t)
        frame = cv2.add(frame, title)

        gesture = "NO HAND"
        if res.hand_landmarks:
            lm = res.hand_landmarks[0]
            pts = [(int(p.x * W), int(p.y * H)) for p in lm]
            for a, b in CONNECTIONS: cv2.line(frame, pts[a], pts[b], (255, 220, 120), 2, cv2.LINE_AA)
            for p in pts: cv2.circle(frame, p, 4, (255, 255, 255), -1, cv2.LINE_AA)
            up = fingers_up(lm)
            size = math.hypot(lm[0].x - lm[9].x, lm[0].y - lm[9].y) + 1e-6
            pinch = math.hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y) / size < .28
            fist = not any(up) and not pinch
            peace = up[0] and up[1] and not up[2] and not up[3]
            px, py = lm[9].x, lm[9].y
            tx = np.interp(px, [M, 1 - M], [0, sw]); ty = np.interp(py, [M, 1 - M], [0, sh])
            tx = min(max(tx, 0), sw - 1); ty = min(max(ty, 0), sh - 1)

            if FLAGS["mouse"]:
                if peace:
                    gesture = "SCROLL"
                    if prev_y is not None: pyautogui.scroll(int((prev_y - py) * 2500))
                    prev_y = py
                else:
                    prev_y = None
                    if pinch:
                        gesture = "RIGHT CLICK"
                        if time.time() - last_rc > 1: pyautogui.rightClick(); last_rc = time.time()
                    else:
                        sx, sy = (tx, ty) if sx is None else (sx + (tx - sx) / SMOOTH, sy + (ty - sy) / SMOOTH)
                        pyautogui.moveTo(int(sx), int(sy))
                        gesture = "FIST = PRESS" if fist else "MOVE"
                if fist: fist_n += 1; open_n = 0
                else: open_n += 1; fist_n = 0
                if fist_n >= 3 and not down: pyautogui.mouseDown(); down = True
                if open_n >= 2 and down: pyautogui.mouseUp(); down = False
            cv2.circle(frame, (int(px * W), int(py * H)), 16, (0, 255, 255) if down else (255, 255, 120), 3 if not down else -1, cv2.LINE_AA)

        while not CMDS.empty():
            try: handle(CMDS.get())
            except Exception as e: say(f"Error: {e}", speak=False)

        stat = f"CPU {psutil.cpu_percent():.0f}%  RAM {psutil.virtual_memory().percent:.0f}%" if psutil else ""
        panel(frame, [f"GESTURE: {gesture}", f"MOUSE: {'ON' if FLAGS['mouse'] else 'OFF'}   VOICE: {'ON' if FLAGS['voice'] else 'OFF'}   {stat}"], 20, 36)
        panel(frame, list(LOG), 20, H - 125)
        cv2.putText(frame, "M mouse | V voice | Q quit | type or say: open chrome, search X on youtube", (20, H - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, .42, (200, 180, 120), 1, cv2.LINE_AA)
        cv2.imshow("E.D.I.T.H.", frame)
        k = cv2.waitKey(1) & 0xFF
        if k in (27, ord("q")): break
        if k == ord("m"): FLAGS["mouse"] = not FLAGS["mouse"]
        if k == ord("v"): FLAGS["voice"] = not FLAGS["voice"]

    if down: pyautogui.mouseUp()
    FLAGS["run"] = False; cap.release(); cv2.destroyAllWindows()
    if orb: orb.terminate()
    os._exit(0)


if __name__ == "__main__":
    main()

