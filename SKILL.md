---
name: pdflinker-anki-flashcards
description: |
  Generate Anki-ready cloze-deletion flashcards from PDF study materials.
  Reads uploaded PDF pages, extracts key concepts, and produces formatted
  cloze cards with source page references — replicating the AI generation
  workflow of the PDFLinker Anki add-on.
---

# PDFLinker Flashcard Generator

Provenance: [filcristallo/PDFLinker-Anki-Addon](https://github.com/filcristallo/PDFLinker-Anki-Addon)
Discovered via: [r/Anki post](https://www.reddit.com/r/Anki/comments/1r7myib/i_made_a_program_that_makes_flashcards_for_anki/)

## Job

Turn PDF study material into high-quality Anki cloze-deletion flashcards with
page-level source references. The user uploads a PDF (textbook chapter, lecture
slides, medical reference, legal statute) and receives importable flashcards
that link back to the exact source page.

## Inputs

- **File upload** (required): one or more PDF pages containing study material —
  textbook chapters, lecture notes, slides, reference documents.
- **Text prompt** (optional): focus area, chapter topic, or specific concepts
  the user wants cards for. If omitted, generate cards from all substantive
  content.

## Workflow

1. **Extract text** from the uploaded PDF pages. Preserve page numbers for
   source linking.

2. **Identify key concepts**: facts, definitions, processes, relationships,
   formulas, and clinical/legal/technical details worth memorizing.

3. **Generate cloze-deletion cards** following Anki best practices:
   - Use `{{c1::target}}` cloze syntax.
   - One atomic fact per card — avoid compound clozes that test multiple
     unrelated facts.
   - Include a `::hint` inside the cloze when the deletion would be ambiguous
     without context (e.g. `{{c1::mitochondria::organelle}}`).
   - Prefer active recall phrasing: state the context, then cloze the answer.
   - For multi-part facts, use `{{c1::...}}` and `{{c2::...}}` on the same
     note so Anki generates sibling cards.

4. **Format output** as a table with columns:
   - `Text` — the cloze-deletion note body
   - `Extra` — brief explanation or mnemonic (one sentence max)
   - `PDF_Page` — source page number from the uploaded PDF

5. **Quality checks** before returning:
   - Every cloze must be self-contained: a reader seeing only that card should
     understand what is being asked.
   - No trivial clozes (articles, prepositions, obvious fill-in-the-blank).
   - Hints are present when the cloze word could reasonably be confused with
     an alternative.
   - Page references are accurate.

## Output Contract

Return a Markdown table of cloze-deletion flashcards:

```
| Text | Extra | PDF_Page |
|------|-------|----------|
| The {{c1::mitochondria::organelle}} is the powerhouse of the cell. | Produces ATP via oxidative phosphorylation. | 12 |
```

If the PDF contains distinct sections or chapters, group cards under section
headings. Aim for 5–15 cards per page of dense material; fewer for sparse
content.
