import re
with open('__init__.py', 'r') as f:
    content = f.read()

custom_page = """
class LoggingWebPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        logger.info(f"JS Console: {message} (Line {lineNumber})")
"""

content = content.replace("class PDFReaderWindow", custom_page + "\nclass PDFReaderWindow")
content = content.replace("self.web_view = QWebEngineView(self)", "self.web_view = QWebEngineView(self)\n        self.web_view.setPage(LoggingWebPage(self.web_view))")

with open('__init__.py', 'w') as f:
    f.write(content)
