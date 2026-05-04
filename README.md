# PDFLinker: The Ultimate PDF Workflow for Anki

> **PDFLinker will always be 100% free and open source.**
> 
> I built this tool to help us win back hundreds of hours of tedious flashcard creation. If PDFLinker has helped you save time, ace an exam, or just made your life a little easier, and you are in a position to do so—consider buying me a coffee! It directly fuels the late-night coding sessions required to keep this add-on updated and running smoothly.
> 
> <a href="https://www.buymeacoffee.com/filippocristallo" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="40"></a>

<img width="1532" alt="PDFLinker Screenshot" src="https://github.com/user-attachments/assets/ce8b9b00-2d14-4923-a187-b869829753cb" />

PDFLinker is a powerful Anki add-on that bridges the gap between your study materials and your flashcards. Read PDFs directly within Anki, automatically generate high-quality cloze-deletion flashcards using the Gemini API, and instantly tie those flashcards back to the exact page they came from.

## ✨ Features

* **Manual Card Creation (No AI Required):** You don't have to use the AI! You can simply open a PDF, open your Anki 'Add' window, and type your flashcards manually. PDFLinker will still track your position and link the exact PDF page to your card.
* **Creator Mode (AI Generation):** Open a PDF, highlight complex text, and click a button to generate perfectly formatted Anki flashcards using Google's Gemini models.
* **Auto-Fill Engine:** Whether you send AI-generated cards to the 'Add' window or type them manually, PDFLinker automatically fills in custom `PDF_Path` and `PDF_Page` fields in real-time so you never lose your source.
* **Review Mode:** When reviewing flashcards, the add-on reads the `PDF_Path` and `PDF_Page` fields and automatically pulls up the exact PDF page alongside your review window for instant context.
* **AI Explanations:** Highlight confusing academic or medical text and ask the AI to break it down into plain language.
* **Smart UI:** Double-click generated cloze deletions in the preview window to easily adjust or remove hints before sending them to Anki.

## 🚀 Installation

**Method 1: Install via AnkiWeb (Recommended)**
The absolute easiest way to install PDFLinker and get automatic updates is through AnkiWeb.
1. Open Anki and go to **Tools -> Add-ons**.
2. Click **Get Add-ons...**
3. Paste the code **`962234340`** and click OK.
4. Restart Anki.
*(You can view the official AnkiWeb page [here](https://ankiweb.net/shared/info/962234340)).*

**Method 2: Manual Installation (For Developers)**
1. Clone this repository or download the source code `.zip`.
2. Place the extracted folder into your Anki `addons21` directory. **Important:** Make sure the folder is named exactly `pdflinker` (no spaces, hyphens, or periods).
    * *Windows:* `%APPDATA%\Anki2\addons21`
    * *Mac:* `~/Library/Application Support/Anki2/addons21`
    * *Linux:* `~/.local/share/Anki2/addons21`
3. Restart Anki.

*(Note: On its first run, PDFLinker will automatically download the required Mozilla PDF.js engine in the background).*

## ⚙️ Configuration

To use the AI generation features, you need a free Google Gemini API key.

1. Get an API key from [Google AI Studio](https://aistudio.google.com/).
2. In Anki, go to **Tools -> Add-ons -> PDFLinker -> Config**.
3. Paste your key into the `gemini_api_key` field.
4. (Optional) Select, edit, or create AI **Prompt Profiles** to fit your specific study needs.

### Field Setup (Important)
For the auto-sync to work, ensure your Anki Note Type has the following fields:
* `PDF_Path`
* `PDF_Page`

**📌 Crucial Step for the 'Add' Window:** When adding cards, open your Anki "Add" window and click the **Pin (Lock) icon** next to both the `PDF_Path` and `PDF_Page` fields. This tells Anki to "remember" the current PDF and page number so you don't lose your linked status when making multiple flashcards in a row!

<img width="719" height="145" alt="image" src="https://github.com/user-attachments/assets/fef6635f-1fc9-4e6b-9605-cf0ce5d4df32" />


The add-on will look for fields named `Text` or `Front` to drop the question in, and `Extra` or `Back` for the explanation.

## 💡 Pro-Tips

When reviewing AI-generated cloze cards in the preview window, you can use these **double-click shortcuts** to edit cards at lightning speed:
* **Un-cloze entirely:** Double-click on the `{{c1::` prefix of any cloze. The add-on will instantly delete the cloze brackets and the hint, leaving only the pure text behind!
* **Delete just the hint:** Double-click on the `::hint` portion of the cloze. The add-on will instantly strip the hint away, leaving the cloze active but hint-free.

## ❓ FAQ

**Q: Why can't I highlight text or make annotations directly in Creator Mode?**
A: PDFLinker is designed to act as a bridge for linking flashcards to specific pages and generating flashcards using AI, rather than replacing your dedicated PDF editor. Because of limitations in saving annotations directly to local files from within Anki, we recommend using your native PDF viewer (like Preview, Adobe Acrobat, or Drawboard) to highlight text or take notes. Once you save your highlights in your native viewer, simply click the "Refresh Page" button in Creator Mode to instantly sync and view your new highlights. You can then use the AI tools to generate flashcards from those sections!

**Q: If a deck is shared with someone else, how do they keep the same linked PDF pages?**
A: Because PDFLinker links to local files on your computer, anyone you share the deck with must have the exact same PDF saved in the **exact same file path**. 
* *Pro-tip for sharing:* If you are studying with friends, keep your PDFs in a shared folder (like a root `C:\Study_PDFs` or a synced Dropbox folder) so the path is identical on everyone's computer. Otherwise, the person receiving the deck can use Anki's "Find and Replace" tool in the Browser to update the `PDF_Path` field to match where they saved the PDF on their own machine.

## 🤝 Contributing

Contributions are welcome! If you want to improve the markdown parser, add new AI models, or refine the UI, please check out our [CONTRIBUTING.md](CONTRIBUTING.md).

## 📄 License

This project is open-source and licensed under the MIT License. 

You are absolutely free to share, edit, modify, and distribute this code. The only requirement is that you must provide clear attribution by citing **Fil Cristallo** as the original author of the project and include the original license file in any forks or distributions. 

See the [LICENSE](LICENSE) file for more details.

<a href="https://www.buymeacoffee.com/filippocristallo" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" height="40"></a>
