import os
import json
import zipfile
import urllib.request
import urllib.parse
import urllib.error
import re
import logging
import webbrowser
from typing import Optional, Dict, Any, List, Callable

from aqt import mw
from aqt.qt import *
from aqt.editor import Editor
from aqt import gui_hooks
from aqt.utils import askUser, tooltip, showInfo
from aqt.addcards import AddCards
from anki.cards import Card
from anki.notes import Note

# Qt5 / Qt6 compatibility handling
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
except ImportError:
    from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings, QWebEnginePage

# ==========================================
# CONSTANTS & SETUP
# ==========================================
ADDON_DIR = os.path.dirname(__file__)
PDFJS_DIR = os.path.join(ADDON_DIR, "pdfjs")
VIEWER_HTML_PATH = os.path.join(PDFJS_DIR, "web", "viewer.html")

USER_FILES_DIR = os.path.join(ADDON_DIR, "user_files")
CACHE_FILE = os.path.join(USER_FILES_DIR, "pdf_cache.json")
CONFIG_PATH = os.path.join(ADDON_DIR, "config.json")

PDFJS_RELEASE_URL = "https://github.com/mozilla/pdf.js/releases/download/v3.11.174/pdfjs-3.11.174-dist.zip"
GITHUB_URL = "https://github.com/filcristallo/PDFLinker-Anki-Addon"
BUY_ME_COFFEE_URL = "https://www.buymeacoffee.com/filippocristallo"

def get_donators_list() -> List[str]:
    """Loads the list of donators from donators.json."""
    donators_path = os.path.join(ADDON_DIR, "donators.json")
    try:
        if os.path.exists(donators_path):
            with open(donators_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load donators.json: {e}")
    return []

# Setup basic logging for the add-on
logging.basicConfig(level=logging.INFO, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PDFLinker")


def setup_dependencies() -> None:
    """Downloads the PDF viewer in the background so it doesn't freeze Anki."""
    if os.path.exists(VIEWER_HTML_PATH):
        return

    os.makedirs(PDFJS_DIR, exist_ok=True)
    zip_path = os.path.join(PDFJS_DIR, "pdfjs.zip")
    
    def download_pdfjs() -> None:
        try:
            urllib.request.urlretrieve(PDFJS_RELEASE_URL, zip_path)
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(PDFJS_DIR)
        finally:
            if os.path.exists(zip_path):
                os.remove(zip_path)
        
    def on_download_done(future) -> None:
        try:
            future.result()
            tooltip("PDFLinker: Setup Complete!", period=3000)
            logger.info("PDF.js successfully downloaded and extracted.")
        except Exception as e:
            logger.error(f"Error downloading PDF.js: {e}")
            showInfo(f"PDFLinker failed to download PDF.js: {e}\nPlease check your internet connection.")
            
    tooltip("PDFLinker: Downloading PDF engine for the first time. Please wait...", period=4000)
    logger.info("Downloading PDF.js viewer...")
    mw.taskman.run_in_background(download_pdfjs, on_download_done)

# Initialize dependencies on startup
setup_dependencies()

# ==========================================
# CONFIGURATION MANAGEMENT
# ==========================================

def get_config() -> Dict[str, Any]:
    """Retrieves the add-on configuration dictionary from Anki."""
    return mw.addonManager.getConfig(__name__) or {}

def save_config(conf: Dict[str, Any]) -> None:
    """Saves the modified configuration dictionary back to Anki."""
    mw.addonManager.writeConfig(__name__, conf)

def is_first_run() -> bool:
    """Checks if this is the first time the add-on is being run by looking for a specific config flag."""
    conf = get_config()
    # If the key 'first_run_complete' is missing or False, it's the first run
    return not conf.get("first_run_complete", False)

def mark_first_run_complete() -> None:
    """Flags the add-on as having completed its first run to skip future welcome wizards."""
    conf = get_config()
    conf["first_run_complete"] = True
    save_config(conf)

# ==========================================
# CACHE SYSTEM & TEXT FORMATTING
# ==========================================

_local_cache = None

def get_cache_data() -> Dict[str, Any]:
    """Loads cached data (e.g., last viewed page for each PDF) from the local cache file."""
    global _local_cache
    if _local_cache is not None:
        return _local_cache
        
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                _local_cache = json.load(f)
                return _local_cache
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode cache file: {e}")
        except Exception as e:
            logger.error(f"Unexpected error reading cache: {e}")
    _local_cache = {}
    return _local_cache

def save_cache_data(data: Dict[str, Any]) -> None:
    """Saves data (e.g., last viewed page) to the local cache file."""
    global _local_cache
    _local_cache = data
    try:
        os.makedirs(USER_FILES_DIR, exist_ok=True)
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save cache data: {e}")

def get_last_page(pdf_path: str) -> str:
    """Returns the last viewed page number for a given PDF, defaulting to '1'."""
    return str(get_cache_data().get(pdf_path, "1"))

def set_last_page(pdf_path: str, page: str) -> None:
    """Updates the cache with the last viewed page number for a given PDF."""
    cache = get_cache_data()
    cache[pdf_path] = str(page)
    save_cache_data(cache)

def clean_ai_text(text: str) -> str:
    """
    Cleans and formats markdown-like text generated by AI into HTML suitable for Anki cards.
    Handles lists, bold, italics, tables, and headings.
    """
    if not text:
        return ""
    try:
        import markdown
        return markdown.markdown(text.strip(), extensions=['tables'])
    except Exception:
        pass

    text = text.strip()
    lines = text.split('\n')
    in_table = False
    html_lines = []
    
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith('|') and stripped_line.endswith('|'):
            if not in_table:
                html_lines.append('<table border="1" style="border-collapse: collapse; width: 100%; margin-bottom: 15px;">')
                in_table = True
            if re.match(r'^\|[\s\-\|:]+\|$', stripped_line):
                continue
            row_html = "<tr>"
            cells = [c.strip() for c in stripped_line.split('|')][1:-1]
            for cell in cells:
                row_html += f"<td style='padding: 8px;'>{cell}</td>"
            row_html += "</tr>"
            html_lines.append(row_html)
        else:
            if in_table:
                html_lines.append('</table>')
                in_table = False
            html_lines.append(line)
            
    if in_table: html_lines.append('</table>')
    text = '\n'.join(html_lines)
    
    text = re.sub(r'^(#{1,6})\s+(.*?)$', lambda m: f'<h{len(m.group(1))}>{m.group(2)}</h{len(m.group(1))}>', text, flags=re.MULTILINE)
    
    text = re.sub(r'^(\s*)[-*+]\s+(.*?)$', r'<ul><li>\2</li></ul>', text, flags=re.MULTILINE)
    text = re.sub(r'^(\s*)\d+\.\s+(.*?)$', r'<ol><li>\2</li></ol>', text, flags=re.MULTILINE)
    text = re.sub(r'</ul>\s*<ul>', '', text)
    text = re.sub(r'</ol>\s*<ol>', '', text)
    
    text = re.sub(r'(\*\*|__)(.*?)\1', r'<b>\2</b>', text, flags=re.DOTALL)
    text = re.sub(r'(?<!\w)(\*|_)(.*?)\1(?!\w)', r'<i>\2</i>', text)
    
    text = text.replace('\n\n', '<br><br>')
    text = text.replace('\n', '<br>')
    
    block_elements = ['ul', 'ol', 'table', 'tr']
    for el in block_elements:
        text = re.sub(fr'<br>\s*<{el}', f'<{el}', text)
        text = re.sub(fr'</{el}>\s*<br>', f'</{el}>', text)
    text = re.sub(r'<br>\s*<h(\d)>', r'<h\1>', text)
    text = re.sub(r'</h(\d)>\s*<br>', r'</h\1>', text)
    
    return text

# ==========================================
# AUTO-FILL ENGINE (REAL-TIME BRIDGE)
# ==========================================

def auto_fill_open_editors(path: str, page: str) -> None:
    """
    Iterates through all open Anki windows and auto-fills 'PDF_Path' and 'PDF_Page' fields 
    if they exist in the current note being edited. This creates a real-time bridge.
    """
    for widget in mw.app.topLevelWidgets():
        editor = getattr(widget, 'editor', None)
        if editor and getattr(editor, 'note', None):
            def update_note(ed=editor):
                note = ed.note
                changed = False
                
                if "PDF_Path" in note and note["PDF_Path"] != path:
                    note["PDF_Path"] = path
                    changed = True
                if "PDF_Page" in note and note["PDF_Page"] != str(page):
                    note["PDF_Page"] = str(page)
                    changed = True
                
                if changed:
                    ed.loadNote()
            
            # Use saveNow to ensure we don't wipe out un-saved fields the user might be typing
            editor.saveNow(update_note)

class CustomWebPage(QWebEnginePage):
    """
    Custom QWebEnginePage that listens for console messages sent from the JavaScript 
    in the PDF.js viewer. This is the bridge receiving PDF page changes and text selections.
    """
    def __init__(self, viewer, parent=None):
        super().__init__(parent)
        self.viewer = viewer 

    def javaScriptConsoleMessage(self, level, message: str, lineNumber: int, sourceID: str) -> None:
        if message.startswith("PDF_PAGE_CHANGED:"):
            page_num = message.split(":")[1]
            if self.viewer.mode == "create" and self.viewer.current_pdf_path:
                auto_fill_open_editors(self.viewer.current_pdf_path, page_num)
                set_last_page(self.viewer.current_pdf_path, page_num)
                
        elif message.startswith("PDF_EXTRACT_FLASHCARD:") or message.startswith("PDF_EXTRACT_CLOZE:"):
            text = message.split(":", 1)[1]
            self.viewer.process_extracted_text(text, task="cloze")

        elif message.startswith("PDF_EXTRACT_BASIC:"):
            text = message.split(":", 1)[1]
            self.viewer.process_extracted_text(text, task="basic")

        elif message.startswith("PDF_EXTRACT_EXPLAIN:"):
            text = message[len("PDF_EXTRACT_EXPLAIN:"):]
            self.viewer.process_extracted_text(text, task="explain")
                
        super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)

# ==========================================
# AI API MANAGER
# ==========================================

class ProfileSelectDialog(QDialog):
    def __init__(self, profiles, last_used, task, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Select AI Profile for {task.capitalize()}")
        self.resize(300, 100)
        self.layout = QVBoxLayout(self)
        
        self.layout.addWidget(QLabel("Select an AI Prompt Profile:"))
        
        self.combo = QComboBox()
        self.combo.addItems(profiles.keys())
        if last_used in profiles:
            self.combo.setCurrentText(last_used)
        self.layout.addWidget(self.combo)
        
        self.btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.layout.addWidget(self.btn_box)
        
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        
        self.manage_btn = QPushButton("Manage Profiles")
        self.manage_btn.clicked.connect(self.open_config)
        self.btn_box.addButton(self.manage_btn, QDialogButtonBox.ButtonRole.ActionRole)
        
        for btn in self.btn_box.buttons():
            btn.setAutoDefault(False)
            btn.setDefault(False)
            
        ok_btn = self.btn_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setDefault(True)
            ok_btn.setAutoDefault(True)
            ok_btn.setFocus()

    def open_config(self):
        dialog = ConfigDialog(self)
        if dialog.exec():
            # Refresh profiles after managing
            config = get_config()
            profiles = config.get("prompt_profiles", {})
            self.combo.clear()
            self.combo.addItems(profiles.keys())
            last_used = config.get("last_used_profile", "General")
            if last_used in profiles:
                self.combo.setCurrentText(last_used)

    def get_selected(self):
        return self.combo.currentText()

def call_gemini_api(extracted_text: str, task: str, parent_window: QWidget, on_success: Callable, on_error: Callable = None, enable_search: bool = False) -> None:
    """
    Standalone function to call the Google Gemini API.
    
    Args:
        extracted_text: The text to be processed by the AI.
        task: The type of task ('cloze', 'flashcard', 'basic', or 'explain').
        parent_window: The Qt window initiating the call (for context).
        on_success: Callback function executed with the result data on successful API call.
        on_error: Optional callback executed if the API call fails.
    """
    if not extracted_text or not str(extracted_text).strip():
        showInfo("No text provided for analysis.")
        return
        
    config = get_config()
    api_key = config.get("gemini_api_key", "")
    if not api_key:
        showInfo("Please set your 'gemini_api_key' in the PDFLinker config.")
        return

    model_name = config.get("gemini_model", "gemini-3-flash-preview")
    thinking_level = config.get("thinking_level", "")
    output_language = config.get("output_language", "English")
    
    # Profile Migration Logic for API Call
    profiles = config.get("prompt_profiles", {})
    if not profiles:
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                default_config = json.load(f)
                profiles = default_config.get("prompt_profiles", {})
        except Exception:
            pass

    last_used = config.get("last_used_profile", "General")
    prompt_template = ""
    
    if task in ("cloze", "flashcard", "basic", "explain"):
        dialog = ProfileSelectDialog(profiles, last_used, task, parent_window)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_profile = dialog.get_selected()
            config["last_used_profile"] = selected_profile
            save_config(config)
            profile_data = profiles.get(selected_profile, {})
            
            if task in ("cloze", "flashcard"):
                base_prompt = profile_data.get("cloze_prompt", profile_data.get("flashcard_prompt", ""))
                prompt_template = base_prompt
                if output_language != "English":
                    prompt_template += f"\n\nOUTPUT LANGUAGE:\nThe generated flashcards and explanations MUST be written in {output_language}."
                prompt_template += "\n\nOUTPUT FORMAT:\nReturn EXCLUSIVELY a JSON array of objects. Each object must have exactly these two keys:\n'text': The question text with optimized cloze syntax.\n'extra': Supporting information, explanations, and context notes."
                mime_type = "application/json"
            elif task == "basic":
                base_prompt = profile_data.get("basic_prompt", profile_data.get("flashcard_prompt", ""))
                prompt_template = base_prompt
                if output_language != "English":
                    prompt_template += f"\n\nOUTPUT LANGUAGE:\nThe generated flashcards and explanations MUST be written in {output_language}."
                prompt_template += "\n\nOUTPUT FORMAT:\nReturn EXCLUSIVELY a JSON array of objects. Each object must have exactly these two keys:\n'text': The question text (Front of the card).\n'extra': The answer text (Back of the card) and any supporting explanations."
                mime_type = "application/json"
            else:
                prompt_template = profile_data.get("explain_prompt", "Explain this text simply and clearly.")
                if output_language != "English":
                    prompt_template += f"\n\nOUTPUT LANGUAGE:\nThe explanation MUST be written in {output_language}."
                mime_type = "text/plain"
        else:
            return # User cancelled

    if not model_name or not prompt_template:
        showInfo("Please set 'gemini_model' and the respective prompt in your Anki add-on config.")
        return
        
    tooltip("Calling AI... Please wait.", period=4000)
    system_prompt = prompt_template.replace("{extracted_text}", "").strip()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    
    data = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": extracted_text}]}],
        "generationConfig": {"response_mime_type": mime_type}
    }
    
    if enable_search:
        data["tools"] = [{"googleSearch": {}}]
        
    if thinking_level:
        data["generationConfig"]["thinkingConfig"] = {"thinkingLevel": thinking_level}
    
    def fetch_from_api():
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), method='POST')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=45) as response:
            result = json.loads(response.read().decode('utf-8'))
            
            # Check for safety filter blocks or empty candidates
            if 'candidates' not in result or not result['candidates']:
                raise ValueError("No candidates returned. The AI might have blocked the content due to safety filters.")
                
            content = result['candidates'][0].get('content', {})
            parts = content.get('parts', [])
            if not parts:
                raise ValueError("The AI returned an empty response.")
                
            content_text = "".join(part.get("text", "") for part in parts if not part.get("thought", False))
                    
            if task in ("cloze", "flashcard", "basic"):
                # Clean up markdown formatting if the AI mistakenly outputs it instead of raw JSON
                cleaned_text = content_text.strip()
                
                # Robust extraction of JSON array in case the AI wraps it in conversational text
                match = re.search(r'\[.*\]', cleaned_text, re.DOTALL)
                if match:
                    cleaned_text = match.group(0)
                else:
                    if cleaned_text.startswith("```json"):
                        cleaned_text = cleaned_text[7:]
                    elif cleaned_text.startswith("```"):
                        cleaned_text = cleaned_text[3:]
                    if cleaned_text.endswith("```"):
                        cleaned_text = cleaned_text[:-3]
                    cleaned_text = cleaned_text.strip()

                cards_data = json.loads(cleaned_text)
                for card in cards_data:
                    if 'text' in card: card['text'] = clean_ai_text(card['text'])
                    if 'extra' in card: card['extra'] = clean_ai_text(card['extra'])
                return cards_data
            return content_text

    def on_api_done(future):
        try:
            result_data = future.result()
            on_success(result_data, extracted_text)
            track_action()
        except urllib.error.HTTPError as e:
            error_msg = f"HTTP Error calling AI API: {e.code} - {e.reason}"
            if e.code == 400:
                error_msg = f"Error 400 (Bad Request): The model '{model_name}' might not support the requested configuration."
            elif e.code in (401, 403):
                error_msg = "Error 401/403 (Unauthorized): Invalid Gemini API Key. Please check your configuration."
            elif e.code == 404:
                error_msg = f"Error 404: Model not found. Check if '{model_name}' is correct in config."
            elif e.code == 429:
                error_msg = "Error 429 (Too Many Requests): You have exceeded your API quota or rate limit."
            elif e.code >= 500:
                error_msg = "Error 500+ (Server Error): Google's Gemini API is currently experiencing issues."
            
            # Attempt to read the exact error message from Google's response body
            try:
                error_body = e.read().decode('utf-8')
                error_json = json.loads(error_body)
                if "error" in error_json and "message" in error_json["error"]:
                    error_msg += f"\n\nDetails: {error_json['error']['message']}"
            except Exception:
                pass
                
            logger.error(error_msg)
            showInfo(error_msg)
            if on_error: on_error(e)
        except urllib.error.URLError as e:
            error_msg = f"Network Error: Unable to connect to Google API. Check your internet connection.\nDetails: {e.reason}"
            logger.error(error_msg)
            showInfo(error_msg)
            if on_error: on_error(e)
        except json.JSONDecodeError as e:
            logger.exception("AI API JSON Parse Failed")
            msg = f"Error parsing AI response: The AI did not return a valid JSON format.\n\nDetails: {str(e)}"
            showInfo(msg)
            if on_error: on_error(e)
        except ValueError as e:
            logger.exception("AI API Value Error")
            showInfo(f"AI Generation Error:\n{str(e)}")
            if on_error: on_error(e)
        except Exception as e:
            logger.exception("AI API Call Failed")
            msg = f"Unexpected Error: {str(e)}"
            showInfo(msg)
            if on_error: on_error(e)

    mw.taskman.run_in_background(fetch_from_api, on_api_done)


# ==========================================
# ENGAGEMENT & SUPPORT PROMPTS
# ==========================================

class SupportDialog(QDialog):
    """A scrollable dialog for support prompts, ensuring large donator lists do not break the UI."""
    def __init__(self, title: str, html_text: str, accept_btn_text: str, reject_btn_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(500, 450)
        
        layout = QVBoxLayout(self)
        
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setHtml(html_text)
        layout.addWidget(self.text_browser)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.reject_btn = QPushButton(reject_btn_text)
        self.reject_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.reject_btn)
        
        self.accept_btn = QPushButton(accept_btn_text)
        self.accept_btn.setStyleSheet("background-color: #FFDD00; color: #000000; font-weight: bold;")
        self.accept_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.accept_btn)
        
        layout.addLayout(btn_layout)

def track_action() -> None:
    """Tracks user actions and triggers rate/donate prompts at specific milestones."""
    conf = get_config()
    actions = conf.get("action_count", 0) + 1
    conf["action_count"] = actions
    
    rate_target = conf.get("rate_target", 20)
    coffee_target = conf.get("coffee_target", 50)
    
    show_rate = (rate_target != -1 and actions >= rate_target)
    show_coffee = (coffee_target != -1 and actions >= coffee_target)
    
    if show_rate:
        msg = QMessageBox(mw)
        msg.setWindowTitle("Enjoying PDFLinker?")
        msg.setText("<h3>You're on a roll! 🚀</h3>"
                    "<p>You've used PDFLinker to generate or save items 25 times!</p>"
                    "<p>If this add-on is saving you time, leaving a quick review on AnkiWeb massively helps other students find it and keeps me motivated to build new features.</p>")
        
        rate_btn = QPushButton("⭐ Rate on AnkiWeb (Done)")
        later_btn = QPushButton("Maybe Later")
        
        msg.addButton(rate_btn, QMessageBox.ButtonRole.AcceptRole)
        msg.addButton(later_btn, QMessageBox.ButtonRole.RejectRole)
        
        msg.exec()
        
        if msg.clickedButton() == rate_btn:
            conf["rate_target"] = -1
            webbrowser.open("https://ankiweb.net/shared/info/962234340?cb=1775683908751")
        else:
            conf["rate_target"] = actions + 20
            
    elif show_coffee:
        donators = get_donators_list()
        donators_html = ""
        if donators:
            donators_html = "<hr><h4>💖 Huge thanks to our supporters:</h4><p><b>" + ", ".join(donators) + "</b></p>"
        
        pitch_text = ("<h3>You've saved hours of work! ⏳</h3>"
                      "<p>PDFLinker has now helped you process over 50 items. Think about how much manual flashcard creation time that has saved you!</p>"
                      "<p>I build and maintain this tool entirely in my free time, giving it away for free to help students like you study smarter.</p>"
                      "<p>If PDFLinker gives you an edge in your studies, <b>please consider buying me a coffee</b>. It directly fuels the late-night coding sessions required to keep this add-on alive, updated, and free. 🙏</p>"
                      + donators_html)
        
        dialog = SupportDialog(
            title="Support PDFLinker",
            html_text=pitch_text,
            accept_btn_text="☕ Buy me a coffee (Done)",
            reject_btn_text="Maybe Later",
            parent=mw
        )
        
        if dialog.exec():
            conf["coffee_target"] = -1
            webbrowser.open(BUY_ME_COFFEE_URL)
        else:
            conf["coffee_target"] = actions + 50
            
    save_config(conf)

def show_support_prompt(parent=None):
    """Shows the support message box and opens the link if accepted."""
    donators = get_donators_list()
    donators_html = ""
    if donators:
        donators_html = "<hr><h4>💖 Huge thanks to our supporters:</h4><p><b>" + ", ".join(donators) + "</b></p>"
    
    pitch_text = (
        "<h3>PDFLinker will always be 100% free and open source.</h3>"
        "<p>I built this tool to help us win back hundreds of hours of tedious flashcard creation.</p>"
        "<p>If PDFLinker has helped you save time, ace an exam, or just made your life a little easier, "
        "and <b>you are in a position to do so</b>—consider buying me a coffee!</p>"
        "<p>It directly fuels the late-night coding sessions required to keep this add-on updated and running smoothly.</p>"
        + donators_html
    )
    
    dialog = SupportDialog(
        title="Support PDFLinker",
        html_text=pitch_text,
        accept_btn_text="☕ Sure, I'll buy you a coffee!",
        reject_btn_text="Maybe later",
        parent=parent
    )
    
    if dialog.exec():
        import webbrowser
        webbrowser.open(BUY_ME_COFFEE_URL)

# ==========================================
# UI COMPONENTS
# ==========================================

class ClozeTextEdit(QTextEdit):
    """
    A custom QTextEdit that allows users to quickly modify cloze deletions.
    Double-clicking on cloze syntax (e.g., {{c1::text::hint}}) can quickly un-cloze 
    or remove the hint.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setStyleSheet("border: 1px solid rgba(128, 128, 128, 0.5); border-radius: 4px;")

    def mouseDoubleClickEvent(self, event) -> None:
        cursor = self.cursorForPosition(event.pos())
        pos = cursor.position()
        block = cursor.block()
        block_pos = block.position()
        relative_pos = pos - block_pos
        text = block.text()
        
        try:
            keep_anchor = QTextCursor.MoveMode.KeepAnchor
        except AttributeError:
            keep_anchor = QTextCursor.KeepAnchor
        
        for match in re.finditer(r'\{\{c\d+::.+?\}\}', text):
            cloze_text = match.group(0)
            start = match.start()
            end = match.end()
            
            first_colon_idx = cloze_text.find('::')
            last_colon_idx = cloze_text.rfind('::')
            has_hint = (last_colon_idx != -1 and last_colon_idx != first_colon_idx)
            
            c_prefix_end = start + first_colon_idx + 2
            if start <= relative_pos <= c_prefix_end:
                answer = cloze_text[first_colon_idx + 2 : last_colon_idx] if has_hint else cloze_text[first_colon_idx + 2 : -2]
                selection_cursor = self.textCursor()
                selection_cursor.setPosition(block_pos + start)
                selection_cursor.setPosition(block_pos + end, keep_anchor)
                selection_cursor.insertText(answer)
                return 
                
            if has_hint:
                hint_start = start + last_colon_idx
                hint_end = end - 2 
                if hint_start <= relative_pos <= end:
                    selection_cursor = self.textCursor()
                    selection_cursor.setPosition(block_pos + hint_start)
                    selection_cursor.setPosition(block_pos + hint_end, keep_anchor)
                    selection_cursor.removeSelectedText()
                    return 
        
        super().mouseDoubleClickEvent(event)


class GeneratedCardsWindow(QMainWindow):
    """
    Window that displays the AI-generated flashcards (Cloze or Basic). 
    Users can review, edit, and send these cards directly to the Anki 'Add' window.
    """
    def __init__(self, regenerate_callback: Callable, cards_data: List[Dict], extracted_text: str, task: str = "cloze", parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Generated Flashcards")
        self.resize(750, 600)
        
        self.regenerate_callback = regenerate_callback
        self.cards_data = cards_data
        self.extracted_text = extracted_text
        self.task = task
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        try:
            self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        except AttributeError:
            self.scroll_area.setFrameShape(QFrame.NoFrame)
        
        self.main_layout.addWidget(self.scroll_area)
        
        self.control_layout = QHBoxLayout()
        self.control_layout.addStretch()
        
        self.info_btn = QPushButton("ℹ️ Pro Tips")
        self.info_btn.clicked.connect(self.show_pro_tips)
        self.control_layout.addWidget(self.info_btn)
        
        self.regen_all_btn = QPushButton("Regenerate All")
        self.regen_all_btn.clicked.connect(self.on_regenerate_all)
        self.control_layout.addWidget(self.regen_all_btn)
        self.main_layout.addLayout(self.control_layout)
        
        self.populate_list()

    def show_pro_tips(self) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Pro Tips")
        msg.setText("<h3>💡 Pro-Tips for editing flashcards:</h3>"
                    "<ul>"
                    "<li><b>Un-cloze entirely:</b> Double-click on the <code>{{c1::</code> prefix.</li>"
                    "<li><b>Delete just the hint:</b> Double-click on the <code>::hint</code> portion.</li>"
                    "</ul>")
        msg.exec()

    def populate_list(self) -> None:
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(12)
        
        for card in self.cards_data:
            item_widget = QWidget()
            item_widget.setObjectName("cardContainer")
            item_widget.setStyleSheet("""
                #cardContainer {
                    background-color: rgba(128, 128, 128, 0.15);
                    border-radius: 8px;
                    border: 1px solid rgba(128, 128, 128, 0.3);
                }
            """)
            
            item_layout = QVBoxLayout(item_widget)
            item_layout.setSpacing(8)
            item_layout.setContentsMargins(14, 14, 14, 14)
            
            text_str = card.get('text', '')
            extra_str = card.get('extra', '')
            
            text_label = QLabel("<b>Text (Front):</b>") if self.task == "basic" else QLabel("<b>Text:</b>")
            text_edit = ClozeTextEdit()
            text_edit.setHtml(text_str)
            text_edit.setMinimumHeight(70)
            text_edit.setMaximumHeight(200)
            
            extra_label = QLabel("<b>Extra (Back):</b>") if self.task == "basic" else QLabel("<b>Extra:</b>")
            extra_edit = QTextEdit()
            extra_edit.setHtml(extra_str)
            extra_edit.setMinimumHeight(70)
            extra_edit.setMaximumHeight(200)
            extra_edit.setStyleSheet("border: 1px solid rgba(128, 128, 128, 0.5); border-radius: 4px;")
            
            btn_layout = QHBoxLayout()
            btn_layout.setContentsMargins(0, 4, 0, 0)
            
            import_extra_cb = QCheckBox("Include Extra/Back field when sending to Anki")
            import_extra_cb.setToolTip("Uncheck this if you only want to send the Front text and ignore the Back/Extra field.")
            import_extra_cb.setChecked(True)
            
            send_btn = QPushButton("Send to Add Window")
            send_btn.setToolTip("Click here to instantly copy these fields into your currently open Anki 'Add' window.")
            send_btn.clicked.connect(lambda _, te=text_edit, ee=extra_edit, cb=import_extra_cb, w=item_widget: 
                                     self.send_to_add_window(te, ee, cb, w))
            
            btn_layout.addWidget(import_extra_cb)
            btn_layout.addStretch()
            btn_layout.addWidget(send_btn)
            
            item_layout.addWidget(text_label)
            item_layout.addWidget(text_edit)
            item_layout.addWidget(extra_label)
            item_layout.addWidget(extra_edit)
            item_layout.addLayout(btn_layout)
            
            self.cards_layout.addWidget(item_widget)
        
        self.cards_layout.addStretch()
        self.scroll_area.setWidget(self.cards_container)

    def on_regenerate_all(self) -> None:
        self.regenerate_callback(self.extracted_text)

    def get_anki_html(self, text_edit: QTextEdit) -> str:
        html = text_edit.toHtml()
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if not body_match:
            return text_edit.toPlainText()
            
        content = body_match.group(1).strip()
        content = re.sub(r'</p>\s*<p[^>]*>', '<br>', content, flags=re.IGNORECASE)
        
        def replace_span(match):
            style = match.group(1).lower()
            res = match.group(2)
            if re.search(r'font-weight:\s*(600|700|800|900|bold)', style):
                res = f'<b>{res}</b>'
            if re.search(r'font-style:\s*italic', style):
                res = f'<i>{res}</i>'
            if re.search(r'text-decoration:\s*underline', style):
                res = f'<u>{res}</u>'
            return res

        old_content = ""
        while old_content != content:
            old_content = content
            content = re.sub(r'<span[^>]*style="([^"]*)"[^>]*>((?:(?!<span).)*?)</span>', replace_span, content, flags=re.IGNORECASE | re.DOTALL)
            
        content = re.sub(r'</?(?!(?:b|i|u|br)\b)[a-z0-9]+[^>]*>', '', content, flags=re.IGNORECASE)
        return content.strip()

    def send_to_add_window(self, text_edit: QTextEdit, extra_edit: QTextEdit, import_extra_cb: QCheckBox, widget_to_style: QWidget) -> None:
        add_window = None
        for widget in mw.app.topLevelWidgets():
            if isinstance(widget, AddCards):
                add_window = widget
                break
                
        if not add_window:
            tooltip("Please open the 'Add' window in Anki first.")
            return
            
        final_text = self.get_anki_html(text_edit)
        final_extra = self.get_anki_html(extra_edit) if import_extra_cb.isChecked() else ""
        
        config = get_config()
        text_fields = config.get("text_fields", ["Text", "Front", "Question", "Testo", "Fronte", "Domanda"])
        extra_fields = config.get("extra_fields", ["Extra", "Back", "Answer", "Retro", "Risposta"])
        
        def update_note():
            note = add_window.editor.note
            changed = False
            for field in note.keys():
                if field in text_fields or field.lower() in [f.lower() for f in text_fields]:
                    note[field] = final_text
                    changed = True
                elif field in extra_fields or field.lower() in [f.lower() for f in extra_fields]:
                    note[field] = final_extra if import_extra_cb.isChecked() else ""
                    changed = True
                    
            if changed:
                add_window.editor.loadNote()
                tooltip("Fields updated in Add Window!")
                widget_to_style.setStyleSheet("""
                    #cardContainer {
                        background-color: rgba(128, 128, 128, 0.15);
                        border-radius: 8px;
                        border: 1px solid #4CAF50;
                    }
                """)
                track_action()
            else:
                tooltip("Could not find suitable fields (e.g., 'Text', 'Extra') in the current Note Type.")
                
        # Use saveNow to avoid wiping out user changes in other fields
        add_window.editor.saveNow(update_note)


class ExplanationWindow(QMainWindow):
    """
    Window that displays the AI's explanation of a selected piece of text. 
    Users can choose to generate flashcards from this explanation.
    """
    def __init__(self, main_viewer_callback: Callable, explanation_text: str, extracted_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Explanation")
        self.resize(600, 500)
        
        self.main_viewer_callback = main_viewer_callback
        self.raw_explanation_text = explanation_text
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenExternalLinks(True)
        self.main_layout.addWidget(self.text_browser)
        
        self.control_layout = QHBoxLayout()
        self.control_layout.addStretch()
        self.gen_cloze_btn = QPushButton("Generate Cloze from this Explanation")
        self.gen_cloze_btn.clicked.connect(self.generate_cloze_from_explanation)
        self.control_layout.addWidget(self.gen_cloze_btn)
        
        self.gen_basic_btn = QPushButton("Generate Basic from this Explanation")
        self.gen_basic_btn.clicked.connect(self.generate_basic_from_explanation)
        self.control_layout.addWidget(self.gen_basic_btn)
        self.main_layout.addLayout(self.control_layout)
        
        self.update_explanation(explanation_text, extracted_text)

    def update_explanation(self, explanation_text: str, extracted_text: str) -> None:
        self.raw_explanation_text = explanation_text 
        formatted_text = clean_ai_text(explanation_text)
        self.text_browser.setHtml(formatted_text)

    def generate_cloze_from_explanation(self) -> None:
        if self.main_viewer_callback:
            self.main_viewer_callback(self.raw_explanation_text, task="cloze")

    def generate_basic_from_explanation(self) -> None:
        if self.main_viewer_callback:
            self.main_viewer_callback(self.raw_explanation_text, task="basic")


class TextToExplainWindow(QMainWindow):
    """Allows users to paste arbitrary text and generate an explanation."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDFLinker - Text to Explain")
        self.resize(600, 400)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        self.label = QLabel("<b>Paste text below to generate an explanation:</b>")
        self.layout.addWidget(self.label)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Paste a difficult paragraph or concept here.\n\nThe AI will break it down and explain it simply...")
        self.layout.addWidget(self.text_edit)
        
        self.btn_layout = QHBoxLayout()
        self.btn_layout.addStretch()
        
        self.generate_btn = QPushButton("🧠 Explain")
        self.generate_btn.clicked.connect(self.on_generate_clicked)
        self.btn_layout.addWidget(self.generate_btn)
        
        self.layout.addLayout(self.btn_layout)

    def on_generate_clicked(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            showInfo("Please paste some text first.")
            return
        call_gemini_api(text, "explain", self, self.on_explanation_generated)

    def process_callback(self, extracted_text: str, task: str = "cloze") -> None:
        if task in ("cloze", "flashcard", "basic"):
            call_gemini_api(extracted_text, task, self, self.on_cards_generated)
        elif task == "explain":
            call_gemini_api(extracted_text, task, self, self.on_explanation_generated)

    def on_explanation_generated(self, result_data, extracted_text):
        self.text_edit.clear()
        
        if hasattr(self, 'explanation_window') and self.explanation_window.isVisible():
            self.explanation_window.update_explanation(result_data, extracted_text)
            tooltip("Explanation Updated!", period=2000)
        else:
            self.explanation_window = ExplanationWindow(
                main_viewer_callback=self.process_callback,
                explanation_text=result_data,
                extracted_text=extracted_text,
                parent=self
            )
            self.explanation_window.show()

    def on_cards_generated(self, result_data, extracted_text):
        if hasattr(self, 'generated_cards_window') and self.generated_cards_window.isVisible():
            self.generated_cards_window.cards_data = result_data
            self.generated_cards_window.extracted_text = extracted_text
            self.generated_cards_window.populate_list()
            tooltip("Cards Updated!", period=2000)
        else:
            # We assume cloze as default if it's not clear which task was used here, 
            # though process_callback correctly routes to on_cards_generated. 
            self.generated_cards_window = GeneratedCardsWindow(
                regenerate_callback=lambda txt: call_gemini_api(txt, "cloze", self, self.on_cards_generated),
                cards_data=result_data,
                extracted_text=extracted_text,
                task="cloze",
                parent=self
            )
            self.generated_cards_window.show()

    def closeEvent(self, event):
        self.text_edit.clear()
        try:
            if hasattr(self, 'explanation_window') and self.explanation_window:
                self.explanation_window.close()
        except RuntimeError:
            pass  # Window already deleted by C++
        try:
            if hasattr(self, 'generated_cards_window') and self.generated_cards_window:
                self.generated_cards_window.close()
        except RuntimeError:
            pass
        event.accept()


class TextToCardsWindow(QMainWindow):
    """Allows users to paste arbitrary text and generate cards."""
    def __init__(self, task: str = "cloze", parent=None):
        super().__init__(parent)
        self.task = task
        title_type = "Cloze" if task == "cloze" else "Basic"
        self.setWindowTitle(f"PDFLinker - Text to {title_type}")
        self.resize(600, 400)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        self.label = QLabel(f"<b>Paste text below to generate {title_type.lower()} flashcards:</b>")
        self.label.setToolTip(f"Paste your notes or book text here.\n\nThe AI will automatically generate {title_type.lower()} flashcards from it...")
        self.layout.addWidget(self.label)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText(f"Paste your notes or book text here.\n\nThe AI will automatically generate {title_type.lower()} flashcards from it...")
        self.layout.addWidget(self.text_edit)
        
        self.btn_layout = QHBoxLayout()
        self.btn_layout.addStretch()
        
        self.generate_btn = QPushButton(f"⚡ Generate {title_type}")
        self.generate_btn.clicked.connect(self.on_generate_clicked)
        self.btn_layout.addWidget(self.generate_btn)
        
        self.layout.addLayout(self.btn_layout)

    def on_generate_clicked(self):
        text = self.text_edit.toPlainText().strip()
        if not text:
            showInfo("Please paste some text first.")
            return
        call_gemini_api(text, self.task, self, self.on_cards_generated)

    def on_cards_generated(self, result_data, extracted_text):
        # 1. Clear the text box once the generation is successful
        self.text_edit.clear()
        
        if hasattr(self, 'generated_cards_window') and self.generated_cards_window.isVisible():
            self.generated_cards_window.cards_data = result_data
            self.generated_cards_window.extracted_text = extracted_text
            self.generated_cards_window.task = self.task
            self.generated_cards_window.populate_list()
            tooltip("Flashcards Updated!", period=2000)
        else:
            self.generated_cards_window = GeneratedCardsWindow(
                regenerate_callback=lambda txt: call_gemini_api(txt, self.task, self, self.on_cards_generated),
                cards_data=result_data,
                extracted_text=extracted_text,
                task=self.task,
                parent=self
            )
            self.generated_cards_window.show()

    def closeEvent(self, event):
        # 2. Clear the text box if the user closes the window
        self.text_edit.clear()
        
        try:
            if hasattr(self, 'generated_cards_window') and self.generated_cards_window:
                self.generated_cards_window.close()
        except RuntimeError:
            pass  # Already deleted in C++
            
        event.accept()

# ==========================================
# CONFIG & FIRST-RUN GUIs
# ==========================================

class ConfigDialog(QDialog):
    """
    Dialog for configuring the add-on settings, such as the Gemini API key, 
    AI model selection, and custom prompts.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PDFLinker Configuration")
        self.resize(600, 700)
        self.config = get_config()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        self.api_key_input = QLineEdit(self.config.get("gemini_api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit if hasattr(QLineEdit, 'EchoMode') else QLineEdit.PasswordEchoOnEdit)
        self.api_key_input.setPlaceholderText("Paste your Gemini API Key here...")
        self.api_key_input.setToolTip("Required. Get this for free from Google AI Studio (aistudio.google.com).")
        form_layout.addRow("Gemini API Key:", self.api_key_input)
        
        self.model_input = QLineEdit(self.config.get("gemini_model", "gemini-3-flash-preview"))
        self.model_input.setPlaceholderText("e.g., gemini-2.5-flash")
        self.model_input.setToolTip("The AI model to use. 'flash' models are faster and cheaper. 'pro' models are smarter but slower.")
        form_layout.addRow("Gemini Model:", self.model_input)
        
        self.thinking_combo = QComboBox()
        self.thinking_combo.addItems(["none", "low", "high"])
        self.thinking_combo.setToolTip("Allows the AI to 'think' before answering. 'none' is fastest. 'high' is best for complex, difficult text.")
        current_thinking = self.config.get("thinking_level", "")
        if current_thinking == "":
            self.thinking_combo.setCurrentText("none")
        elif current_thinking in ["low", "high"]:
            self.thinking_combo.setCurrentText(current_thinking)
        form_layout.addRow("Thinking Level:", self.thinking_combo)
        
        self.language_combo = QComboBox()
        self.languages = [
            "English", "Spanish", "French", "German", "Italian", "Portuguese", 
            "Russian", "Japanese", "Korean", "Chinese (Simplified)", "Chinese (Traditional)",
            "Arabic", "Hindi", "Dutch", "Turkish", "Polish"
        ]
        self.language_combo.addItems(self.languages)
        self.language_combo.setToolTip("Select the language for the AI to use when generating output.")
        current_language = self.config.get("output_language", "English")
        if current_language in self.languages:
            self.language_combo.setCurrentText(current_language)
        else:
            self.language_combo.setCurrentText("English")
        form_layout.addRow("Output Language:", self.language_combo)
        
        layout.addLayout(form_layout)
        
        # Add a helper label for prompts
        prompt_help_label = QLabel("<i>Customize how the AI generates your flashcards and explanations below:</i>")
        prompt_help_label.setStyleSheet("color: gray; margin-top: 10px; margin-bottom: 5px;")
        layout.addWidget(prompt_help_label)
        
        # --- Profiles Management ---
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("<b>Prompt Profile:</b>"))
        
        self.profiles = self.config.get("prompt_profiles", {})
        if not self.profiles:
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    default_config = json.load(f)
                    self.profiles = default_config.get("prompt_profiles", {})
            except Exception:
                pass

        self.profile_combo = QComboBox()
        self.profile_combo.addItems(self.profiles.keys())
        last_used = self.config.get("last_used_profile", "General")
        if last_used in self.profiles:
            self.profile_combo.setCurrentText(last_used)
            
        self.new_profile_btn = QPushButton("New")
        self.delete_profile_btn = QPushButton("Delete")
        self.reset_profile_btn = QPushButton("Reset Profile")
        
        profile_layout.addWidget(self.profile_combo)
        profile_layout.addWidget(self.new_profile_btn)
        profile_layout.addWidget(self.delete_profile_btn)
        profile_layout.addWidget(self.reset_profile_btn)
        layout.addLayout(profile_layout)
        # -----------------------------
        
        def create_prompt_section(title, tooltip_text, is_profile_specific=True):
            header_layout = QHBoxLayout()
            header_layout.addWidget(QLabel(f"<b>{title}</b>"))
            header_layout.addStretch()
            layout.addLayout(header_layout)
            
            text_edit = QTextEdit()
            text_edit.setToolTip(tooltip_text)
            layout.addWidget(text_edit)
            return text_edit

        self.cloze_prompt_input = create_prompt_section("Cloze Prompt:", "Instructions for generating cloze flashcards.", True)
        self.basic_prompt_input = create_prompt_section("Basic Prompt:", "Instructions for generating basic flashcards.", True)
        self.explain_prompt_input = create_prompt_section("Explain Prompt:", "Instructions for explaining difficult concepts.", True)
        
        self.current_profile_name = self.profile_combo.currentText()
        if self.current_profile_name:
            self.load_profile_data(self.current_profile_name)

        self.profile_combo.currentTextChanged.connect(self.on_profile_changed)
        self.new_profile_btn.clicked.connect(self.create_new_profile)
        self.delete_profile_btn.clicked.connect(self.delete_profile)
        self.reset_profile_btn.clicked.connect(self.reset_profile)
        
        btn_layout = QHBoxLayout()
        
        github_btn = QPushButton("View on GitHub")
        github_btn.clicked.connect(lambda: webbrowser.open(GITHUB_URL))
        
        coffee_btn = QPushButton("☕ Buy me a coffee")
        coffee_btn.setStyleSheet("background-color: #FFDD00; color: #000000; font-weight: bold;")
        coffee_btn.clicked.connect(lambda: webbrowser.open(BUY_ME_COFFEE_URL))
        
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save_and_close)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(github_btn)
        btn_layout.addWidget(coffee_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)

    def load_profile_data(self, profile_name: str):
        data = self.profiles.get(profile_name, {})
        self.cloze_prompt_input.setPlainText(data.get("cloze_prompt", data.get("flashcard_prompt", "")))
        self.basic_prompt_input.setPlainText(data.get("basic_prompt", data.get("flashcard_prompt", "")))
        self.explain_prompt_input.setPlainText(data.get("explain_prompt", ""))

    def save_current_profile_data(self):
        if self.current_profile_name in self.profiles:
            self.profiles[self.current_profile_name]["cloze_prompt"] = self.cloze_prompt_input.toPlainText()
            self.profiles[self.current_profile_name]["basic_prompt"] = self.basic_prompt_input.toPlainText()
            self.profiles[self.current_profile_name]["explain_prompt"] = self.explain_prompt_input.toPlainText()
            if "flashcard_prompt" in self.profiles[self.current_profile_name]:
                del self.profiles[self.current_profile_name]["flashcard_prompt"]
    def on_profile_changed(self, profile_name):
        if not profile_name:
            return
        self.save_current_profile_data()
        self.current_profile_name = profile_name
        self.load_profile_data(profile_name)

    def create_new_profile(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Enter profile name:")
        if ok and name and name not in self.profiles:
            self.save_current_profile_data()
            self.profiles[name] = {
                "cloze_prompt": "You are an expert Anki flashcard creator...",
                "basic_prompt": "You are an expert Anki flashcard creator...",
                "explain_prompt": "Explain this text simply and clearly."
            }
            self.profile_combo.addItem(name)
            self.profile_combo.setCurrentText(name)

    def delete_profile(self):
        name = self.profile_combo.currentText()
        if name == "General":
            showInfo("Cannot delete the General profile.")
            return
        
        reply = QMessageBox.question(self, "Delete Profile", f"Are you sure you want to delete profile '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            del self.profiles[name]
            self.profile_combo.removeItem(self.profile_combo.currentIndex())

    def reset_profile(self):
        name = self.profile_combo.currentText()
        reply = QMessageBox.question(self, "Reset Profile", f"Are you sure you want to reset profile '{name}' to its defaults?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    default_config = json.load(f)
                    default_profiles = default_config.get("prompt_profiles", {})
                    if name in default_profiles:
                        self.profiles[name] = default_profiles[name].copy()
                        self.load_profile_data(name)
                        tooltip(f"Profile '{name}' has been reset.")
                    else:
                        showInfo(f"No default settings found for profile '{name}'.")
            except Exception as e:
                showInfo(f"Error reading defaults: {e}")

    def save_and_close(self):
        self.config["gemini_api_key"] = self.api_key_input.text().strip()
        self.config["gemini_model"] = self.model_input.text().strip()
        selected_thinking = self.thinking_combo.currentText()
        self.config["thinking_level"] = "" if selected_thinking == "none" else selected_thinking
        self.config["output_language"] = self.language_combo.currentText()
        
        self.save_current_profile_data()
        self.config["prompt_profiles"] = self.profiles
        self.config["last_used_profile"] = self.profile_combo.currentText()
        
        save_config(self.config)
        tooltip("Configuration saved successfully.")
        self.accept()


class FirstRunWizard(QDialog):
    """
    Wizard shown on the first run to guide the user through setting up 
    the API key and understanding the necessary Anki note fields.
    """
    def __init__(self, parent=mw):
        super().__init__(parent)
        self.setWindowTitle("Welcome to PDFLinker!")
        self.resize(650, 500)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        
        # Tab 1: Tutorial
        self.tutorial_tab = QWidget()
        tut_layout = QVBoxLayout(self.tutorial_tab)
        
        tutorial_text = """
        <h2>Welcome to PDFLinker! 🚀</h2>
        <p>PDFLinker is a powerful Anki add-on that bridges the gap between your study materials and your flashcards.</p>
        
        <h3>⚙️ Crucial Setup Step:</h3>
        <p>For the auto-sync to work properly, ensure your Anki Note Type has the following exactly named fields:</p>
        <ul>
            <li><b>PDF_Path</b></li>
            <li><b>PDF_Page</b></li>
        </ul>
        <p><i>When adding cards, click the <b>Pin (Lock) icon</b> next to both the PDF_Path and PDF_Page fields in your 'Add' window.</i></p>
        
        <h3>💡 Pro-Tips for Flashcard Previews:</h3>
        <ul>
            <li><b>Un-cloze entirely:</b> Double-click on the <code>{{c1::</code> prefix.</li>
            <li><b>Delete just the hint:</b> Double-click on the <code>::hint</code> portion.</li>
        </ul>
        <p>You can review this anytime in the <b>README</b> on our GitHub page.</p>
        """
        browser = QTextBrowser()
        browser.setHtml(tutorial_text)
        tut_layout.addWidget(browser)
        self.tabs.addTab(self.tutorial_tab, "📚 Tutorial")
        
        # Tab 2: API Key Setup
        self.api_tab = QWidget()
        api_layout = QVBoxLayout(self.api_tab)
        
        api_info = """
        <h3>🔑 Connect to Google Gemini AI</h3>
        <p>To use the AI generation features, you need a Google Gemini API key.</p>
        <ol>
            <li>Get an API key from <a href="https://aistudio.google.com/">Google AI Studio</a>.</li>
            <li>Paste it in the box below.</li>
        </ol>
        """
        api_browser = QTextBrowser()
        api_browser.setHtml(api_info)
        api_browser.setOpenExternalLinks(True)
        api_browser.setMaximumHeight(150)
        api_layout.addWidget(api_browser)
        
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText("Paste your Gemini API Key here...")
        self.api_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit if hasattr(QLineEdit, 'EchoMode') else QLineEdit.PasswordEchoOnEdit)
        api_layout.addWidget(self.api_input)
        api_layout.addStretch()
        
        self.tabs.addTab(self.api_tab, "⚙️ API Setup")
        
        layout.addWidget(self.tabs)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.finish_btn = QPushButton("Save and Finish")
        self.finish_btn.clicked.connect(self.finish_setup)
        btn_layout.addWidget(self.finish_btn)
        
        layout.addLayout(btn_layout)

    def finish_setup(self):
        api_key = self.api_input.text().strip()
        conf = get_config()
        if api_key:
            conf["gemini_api_key"] = api_key
            save_config(conf)
            tooltip("API Key saved!")
        mark_first_run_complete()
        self.accept()

def check_first_run():
    if is_first_run():
        wizard = FirstRunWizard(mw)
        wizard.exec()

# ==========================================
# MAIN VIEWER LOGIC
# ==========================================

review_viewer = None
creator_viewer = None

class PDFViewerWindow(QMainWindow):
    """
    The main PDF viewer window embedding PDF.js via QWebEngineView.
    Operates in two modes:
      - 'create': For reading PDFs and generating flashcards directly from text.
      - 'review': For viewing PDFs linked to the currently reviewed Anki card.
    """
    def __init__(self, mode: str = "review", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.current_pdf_path = None 
        self.web_view = QWebEngineView(self)
        
        self.web_page = CustomWebPage(self, self.web_view)
        self.web_view.setPage(self.web_page)
        
        # --- TOOLBAR SETUP ---
        toolbar = QToolBar("PDF Toolbar", self)
        toolbar.setMovable(False)
        toolbar.toggleViewAction().setEnabled(False)
        self.addToolBar(toolbar)

        if self.mode == "create":
            self.setWindowTitle("PDFLinker Reader (Creator Mode)")
            self.resize(1000, 1000)
            
            open_action = QAction("📂 Open PDF for Study...", self)
            open_action.triggered.connect(self.open_local_pdf)
            toolbar.addAction(open_action)

            refresh_action = QAction("🔄 Refresh Page", self)
            refresh_action.triggered.connect(self.refresh_pdf)
            toolbar.addAction(refresh_action)
        else:
            self.setWindowTitle("PDFLinker Reader (Review Mode)")
            self.resize(800, 1000)

        ai_tools_btn = QToolButton(self)
        ai_tools_btn.setText("🤖 AI Tools")
        ai_tools_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        ai_tools_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        ai_menu = QMenu(ai_tools_btn)
        
        flashcard_action = QAction("📝 Text ➔ Flashcard", self)
        flashcard_action.triggered.connect(self.generate_flashcard_current_page)
        ai_menu.addAction(flashcard_action)

        explain_action = QAction("🧠 Text ➔ Explain", self)
        explain_action.triggered.connect(self.explain_current_page)
        ai_menu.addAction(explain_action)
        
        ai_tools_btn.setMenu(ai_menu)
        toolbar.addWidget(ai_tools_btn)
        
        toolbar.addSeparator()
        
        support_action = QAction("☕ Buy me a coffee", self)
        support_action.triggered.connect(lambda: show_support_prompt(self))
        toolbar.addAction(support_action)
        
        self.setCentralWidget(self.web_view)
        self.web_view.loadFinished.connect(self.on_load_finished)
        
        settings = self.web_view.settings()
        try:
            settings.setAttribute(QWebEngineSettings.WebAttribute.ForceDarkMode, False)
        except AttributeError:
            pass  # ForceDarkMode may not be available in older Anki/Qt versions
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

        self._load_empty_viewer()

    def _load_empty_viewer(self) -> None:
        if os.path.exists(VIEWER_HTML_PATH):
            base_url = QUrl.fromLocalFile(VIEWER_HTML_PATH).toString()
            self.web_view.setUrl(QUrl(base_url))

    def on_load_finished(self, ok: bool) -> None:
        if not ok: return
        anti_scroll_js = """
        function disableSearchScroll() {
            if (typeof PDFViewerApplication !== 'undefined' && PDFViewerApplication.findController) {
                PDFViewerApplication.findController.scrollMatchIntoView = function() { return; };
            } else {
                setTimeout(disableSearchScroll, 100);
            }
        }
        disableSearchScroll();
        """
        
        if self.mode == "create":
            js_code = anti_scroll_js + """
            function initPdfListeners() {
                if (typeof PDFViewerApplication !== 'undefined' && PDFViewerApplication.eventBus) {
                    PDFViewerApplication.eventBus.on('pagechanging', function(e) {
                        console.log("PDF_PAGE_CHANGED:" + e.pageNumber);
                    });
                } else {
                    setTimeout(initPdfListeners, 500);
                }
            }
            initPdfListeners();
            """
            self.web_view.page().runJavaScript(js_code)
        elif self.mode == "review":
            self.web_view.page().runJavaScript(anti_scroll_js)

    def open_local_pdf(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if file_path:
            last_page = get_last_page(file_path)
            self.load_pdf(file_path, last_page)

    def refresh_pdf(self) -> None:
        if self.current_pdf_path:
            self.web_view.reload()

    def load_pdf(self, path: str, page: str, note: Optional[Note] = None) -> None:
        if not path or not os.path.exists(path):
            return
        self.current_pdf_path = path 
        
        pdf_name = os.path.basename(path)
        if self.mode == "create":
            self.setWindowTitle(f"PDFLinker Reader (Creator Mode) - {pdf_name}")
            auto_fill_open_editors(path, page)
        else:
            self.setWindowTitle(f"PDFLinker Reader (Review Mode) - {pdf_name}")
            
        base_viewer_url = QUrl.fromLocalFile(VIEWER_HTML_PATH).toString()
        file_url = QUrl.fromLocalFile(path).toString()
        encoded_file_url = urllib.parse.quote(file_url, safe="%/:=&?~#+!$,;'@()*[]")
        
        full_url = f"{base_viewer_url}?file={encoded_file_url}#page={page}"
        self.web_view.setUrl(QUrl(full_url))

    def generate_flashcard_current_page(self) -> None:
        task = ask_flashcard_type(self)
        if not task: return
        js_extract = f"(function() {{ console.log('PDF_EXTRACT_{task.upper()}:' + window.getSelection().toString().trim()); }})();"
        self.web_view.page().runJavaScript(js_extract)

    def explain_current_page(self) -> None:
        js_extract = "(function() { console.log('PDF_EXTRACT_EXPLAIN:' + window.getSelection().toString().trim()); })();"
        self.web_view.page().runJavaScript(js_extract)

    def process_extracted_text(self, extracted_text: str, task: str = "cloze") -> None:
        if task in ("cloze", "flashcard", "basic"):
            call_gemini_api(extracted_text, task, self, lambda res, ext: self.on_cards_generated(res, ext, task))
        elif task == "explain":
            call_gemini_api(extracted_text, task, self, self.on_explanation_generated)

    def on_cards_generated(self, result_data, extracted_text, task="cloze"):
        if hasattr(self, 'generated_cards_window') and self.generated_cards_window.isVisible():
            self.generated_cards_window.cards_data = result_data
            self.generated_cards_window.extracted_text = extracted_text
            self.generated_cards_window.task = task
            self.generated_cards_window.populate_list()
            tooltip("Flashcards Updated!", period=2000)
        else:
            self.generated_cards_window = GeneratedCardsWindow(
                regenerate_callback=lambda txt, t=task: call_gemini_api(txt, t, self, lambda res, ext: self.on_cards_generated(res, ext, t)),
                cards_data=result_data,
                extracted_text=extracted_text,
                task=task,
                parent=self
            )
            self.generated_cards_window.show()

    def on_explanation_generated(self, result_data, extracted_text):
        if hasattr(self, 'explanation_window') and self.explanation_window.isVisible():
            self.explanation_window.update_explanation(result_data, extracted_text)
            tooltip("Explanation Updated!", period=2000)
        else:
            self.explanation_window = ExplanationWindow(
                main_viewer_callback=self.process_extracted_text,
                explanation_text=result_data,
                extracted_text=extracted_text,
                parent=self
            )
            self.explanation_window.show()

    def closeEvent(self, event) -> None:
        global review_viewer, creator_viewer
        if self.mode == "review":
            review_viewer = None
        elif self.mode == "create":
            creator_viewer = None
            
        try:
            if hasattr(self, 'generated_cards_window') and self.generated_cards_window:
                self.generated_cards_window.close()
        except RuntimeError:
            pass
            
        try:
            if hasattr(self, 'explanation_window') and self.explanation_window:
                self.explanation_window.close()
        except RuntimeError:
            pass
            
        self.deleteLater()
        event.accept()

# ==========================================
# WINDOW LAUNCHERS & TOOLBAR REGISTRATION
# ==========================================

def launch_review_viewer() -> None:
    global review_viewer
    if not review_viewer:
        review_viewer = PDFViewerWindow(mode="review", parent=mw)
    review_viewer.show()
    review_viewer.raise_()
    review_viewer.activateWindow()
    if mw.state == "review" and getattr(mw.reviewer, 'state', None) == "answer":
        update_pdf_for_current_card(mw.reviewer.card)

def launch_creator_viewer() -> None:
    global creator_viewer
    if not creator_viewer:
        creator_viewer = PDFViewerWindow(mode="create", parent=mw)
    creator_viewer.show()
    creator_viewer.raise_()
    creator_viewer.activateWindow()

last_flashcard_type = "cloze"

def ask_flashcard_type(parent) -> str:
    global last_flashcard_type
    items = ["Cloze", "Basic"]
    current_index = items.index("Cloze" if last_flashcard_type == "cloze" else "Basic")
    item, ok = QInputDialog.getItem(parent, "Flashcard Type", "Select the type of flashcard to create:", items, current_index, False)
    if ok and item:
        last_flashcard_type = "cloze" if item == "Cloze" else "basic"
        return last_flashcard_type
    return None

text_to_cards_viewer = None
def launch_text_to_flashcard() -> None:
    task = ask_flashcard_type(mw)
    if not task: return
    global text_to_cards_viewer
    if not text_to_cards_viewer:
        text_to_cards_viewer = TextToCardsWindow(task=task, parent=mw)
    else:
        text_to_cards_viewer.task = task
        title_type = "Cloze" if task == "cloze" else "Basic"
        text_to_cards_viewer.setWindowTitle(f"PDFLinker - Text to {title_type}")
        text_to_cards_viewer.label.setText(f"<b>Paste text below to generate {title_type.lower()} flashcards:</b>")
        text_to_cards_viewer.text_edit.setPlaceholderText(f"Paste your notes or book text here.\n\nThe AI will automatically generate {title_type.lower()} flashcards from it...")
        text_to_cards_viewer.generate_btn.setText(f"⚡ Generate {title_type}")
    text_to_cards_viewer.show()
    text_to_cards_viewer.raise_()
    text_to_cards_viewer.activateWindow()

text_to_explain_viewer = None
def launch_text_to_explain() -> None:
    global text_to_explain_viewer
    if not text_to_explain_viewer:
        text_to_explain_viewer = TextToExplainWindow(parent=mw)
    text_to_explain_viewer.show()
    text_to_explain_viewer.raise_()
    text_to_explain_viewer.activateWindow()

class StandaloneAIHandler(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.windows = []
        
    def on_cards_generated(self, result_data, extracted_text, task):
        window = GeneratedCardsWindow(
            regenerate_callback=lambda txt: call_gemini_api(txt, task, mw, lambda res, ext: self.on_cards_generated(res, ext, task)),
            cards_data=result_data,
            extracted_text=extracted_text,
            task=task,
            parent=mw
        )
        self.windows.append(window)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.destroyed.connect(lambda obj, w=window: self.windows.remove(w) if w in self.windows else None)
        window.show()

    def on_explanation_generated(self, result_data, extracted_text):
        window = ExplanationWindow(
            main_viewer_callback=self.process_callback,
            explanation_text=result_data,
            extracted_text=extracted_text,
            parent=mw
        )
        self.windows.append(window)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.destroyed.connect(lambda obj, w=window: self.windows.remove(w) if w in self.windows else None)
        window.show()

    def process_callback(self, extracted_text: str, task: str = "cloze") -> None:
        if task in ("cloze", "flashcard", "basic"):
            call_gemini_api(extracted_text, task, mw, lambda res, ext: self.on_cards_generated(res, ext, task))
        elif task == "explain":
            call_gemini_api(extracted_text, task, mw, self.on_explanation_generated)

standalone_ai_handler = StandaloneAIHandler()

def open_config_dialog():
    dialog = ConfigDialog(mw)
    dialog.exec()

def update_pdf_for_current_card(card: Optional[Card]) -> None:
    """
    Called when the user is reviewing cards in Anki. Reads the 'PDF_Path' and 
    'PDF_Page' fields of the current card and updates the Review Mode viewer.
    """
    global review_viewer
    if not review_viewer or not review_viewer.isVisible() or not card: 
        return
        
    note = card.note()
    if "PDF_Path" in note and "PDF_Page" in note:
        path = note["PDF_Path"]
        page = note["PDF_Page"]
        if path and page and os.path.exists(path):
            review_viewer.load_pdf(path, page, note)

def setup_gui():
    """
    Initializes the GUI components for the add-on, such as injecting 
    the PDFLinker toolbar into the main Anki window.
    """
    # 1. Custom Configure Action override
    mw.addonManager.setConfigAction(__name__, open_config_dialog)
    
    # 2. Main Window Native Qt Toolbar Integration
    pdflinker_toolbar = QToolBar("PDFLinker", mw)
    pdflinker_toolbar.setObjectName("pdflinker_toolbar")
    
    # Lock the toolbar
    pdflinker_toolbar.setMovable(False)
    pdflinker_toolbar.setFloatable(False)
    pdflinker_toolbar.toggleViewAction().setEnabled(False)
    
    label = QLabel(" <b>PDFLinker</b> ")
    pdflinker_toolbar.addWidget(label)

    create_action = QAction("📝 Creator Mode", mw)
    create_action.setToolTip("Open PDF reader to create new flashcards from text")
    create_action.triggered.connect(launch_creator_viewer)
    pdflinker_toolbar.addAction(create_action)

    review_action = QAction("📖 Review Mode", mw)
    review_action.setToolTip("Open PDF reader that automatically syncs to the flashcard you are currently reviewing")
    review_action.triggered.connect(launch_review_viewer)
    pdflinker_toolbar.addAction(review_action)
    
    pdflinker_toolbar.addSeparator()
    
    ai_tools_btn = QToolButton(mw)
    ai_tools_btn.setText("🤖 AI Tools")
    ai_tools_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
    ai_tools_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    ai_menu = QMenu(ai_tools_btn)
    
    text_flashcard_action = QAction("📝 Text ➔ Flashcard", mw)
    text_flashcard_action.triggered.connect(launch_text_to_flashcard)
    ai_menu.addAction(text_flashcard_action)
    
    text_explain_action = QAction("🧠 Text ➔ Explain", mw)
    text_explain_action.triggered.connect(launch_text_to_explain)
    ai_menu.addAction(text_explain_action)
    
    ai_menu.addSeparator()
    
    ai_tools_btn.setMenu(ai_menu)
    pdflinker_toolbar.addWidget(ai_tools_btn)

    pdflinker_toolbar.addSeparator()

    config_action = QAction("⚙️ Config", mw)
    config_action.setToolTip("Open PDFLinker settings (API key, models, custom prompts)")
    config_action.triggered.connect(open_config_dialog)
    pdflinker_toolbar.addAction(config_action)

    pdflinker_toolbar.addSeparator()

    support_action = QAction("☕ Buy me a coffee", mw)
    support_action.setToolTip("Support the development of PDFLinker! ❤️")
    support_action.triggered.connect(lambda: show_support_prompt(mw))
    pdflinker_toolbar.addAction(support_action)

    mw.addToolBar(pdflinker_toolbar)
    
    # Allow hiding/showing toolbar from Anki Tools menu
    toggle_toolbar_action = QAction("Toggle PDFLinker Toolbar", mw)
    toggle_toolbar_action.setCheckable(True)
    
    config = get_config()
    show_toolbar = config.get("show_toolbar", True)
    pdflinker_toolbar.setVisible(show_toolbar)
    toggle_toolbar_action.setChecked(show_toolbar)
    
    def on_toggle_toolbar(checked):
        pdflinker_toolbar.setVisible(checked)
        conf = get_config()
        conf["show_toolbar"] = checked
        save_config(conf)
        
    toggle_toolbar_action.toggled.connect(on_toggle_toolbar)
    mw.form.menuTools.addAction(toggle_toolbar_action)

gui_hooks.reviewer_did_show_answer.append(update_pdf_for_current_card)
gui_hooks.profile_did_open.append(check_first_run)
gui_hooks.main_window_did_init.append(setup_gui)
