# Changelog

All notable changes to this project will be documented in this file. This project adheres to Semantic Versioning.

---

## [v1.2.0] - 2026-06-21

This release delivers major UX and stability improvements, centering around data backup orchestration, custom dialog controls, safety prompts for unsaved changes, and aesthetic enhancements in the brain panel.

### Added
- **AI Settings Modal & Custom Dropdowns**:
  - Migrated the AI Provider and Model selector from a settings accordion to a dedicated modal dialog (`#ai-modal`).
  - Added a custom-styled dropdown wrapper matching the write/rewrite options to replace system native options.
- **Topmost Confirmation Modal**:
  - Replaced browser-native `confirm()` dialogues with the app's integrated custom warning confirmation modal.
  - Positioned the confirmation modal at `z-index: 1050` to overlay other modals and adjusted its width/padding to fit short confirmation text neatly.

### Changed
- **Dialog Backdrop Dismissals**:
  - Implemented safe click-outside-to-close behavior across all dialog overlays (`#data-modal`, `#ai-modal`, `#prompt-modal`, `#confirm-modal`).
  - Implemented capturing-phase event listener on the sidebar. Clicking on the sidebar or any button inside it now intercepts actions, validates unsaved edits/active processes, and dismisses active popups/sheets.
- **Prompt Edits check**:
  - Added validation checks on prompt cancellations (button click, backdrop click, or sidebar clicks). If the input text has unsaved changes, users are prompted via the confirmation modal.
- **Colorized Brain Actions**:
  - Highlighted Edit (blue accent) and Delete (red danger) buttons in the Brain lists and memories cards for better visual distinction from rule content.
- **Translation improvements**:
  - Updated offline backup indicators and status texts to read `"Restored from device"`.

---

## [v1.1.0] - 2026-06-18

This release focuses on a complete visual redesign, user experience (UX) enhancements to match premium AI platforms (ChatGPT, Gemini, Claude), a robust test suite, and clean attachment workflows.

### Added
- **Dynamic Attachment Options Popover Menu**:
  - Replaced immediate file selection with a sleek option popover right next to the attachment button.
  - Users can now select specifically between **Gambar** (Images, filtering `image/*`) and **Dokumen** (Documents, filtering text, PDFs, JSON, and office documents).
  - Designed the menu to auto-dismiss on outside clicks or pressing the `Escape` key.
- **Auto/System Theme Split Icon**:
  - Replaced the previous moon/sun-rays icon with a mathematically precise, mathematically symmetric split Sun-Moon SVG icon for the "Auto" system theme.
- **TDD Test Suite**:
  - Added full backend and storage unit test coverage in `tests/test_api.py` and `tests/test_storage.py` (127 unit tests total).
  - Integrated `conftest.py` setup for automated testing fixtures.
- **Git Assistant Script (`gitman.sh`)**:
  - Added helper script for managing and automating git workflows.
- **Language Translation Utility (`translate.py`)**:
  - Added utility script for localizations.

### Changed
- **Visual Design & Polish (Premium Chat Experience)**:
  - Redesigned the main dashboard with a unified color palette (`--bg-surface`, `--bg-base`, `--border`) for light and dark modes.
  - Implemented cohesive typography using Inter (UI labels) and Georgia (branding).
  - Redesigned the chat message bubbles with clear user/assistant separation, soft hover states, and smooth markdown rendering using `marked.js` and code highlighting using `highlight.js`.
- **Sidebar Transitions & Minimized State**:
  - Reordered the sidebar layout (toggle on left, branding on right).
  - Redesigned minimized transitions to hide text labels and branding smoothly via opacity/width without causing layout jumps or visual stutters.
  - Added overlay backdrop support for mobile sidebar dismissals.
- **Conversation Title Behavior**:
  - Defaulted the active conversation title to hidden/collapsed in the top header.
  - Added a dropdown toggle button to expand/collapse the active conversation title on demand.
- **Active Chat Highlight**:
  - The current active chat session in the sidebar history list is now visually highlighted.
- **Theme Cycling**:
  - Polished dark/light modes and cycling behavior (Light -> System/Auto -> Dark).
- **Custom Scrollbar Styling**:
  - Custom Webkit and Firefox scrollbars styled to follow dark/light theme variables and blend natively with the app layout.
- **Rich Attachment Support in APIs**:
  - Expanded `ChatRequest` in the FastAPI backend to accept base64-encoded file attachments (images, PDFs, documents) alongside metadata (name, size, type).
- **README Updates**:
  - Updated configuration, environment setup instructions, and architecture details.

### Removed
- Obsolete Hugging Face synchronization GitHub actions workflow (`sync_from_hf.yml`).
- Obsolete `.env.example` file (unified configurations).

---

## [v1.0.0] - Initial Release

Initial release of the AI assistant chat workspace.

### Added
- Core backend FastAPI services with chat history storage.
- Basic theme toggling between Light and Dark modes.
- Text chat interface with basic formatting and session creation.
- Sidebar conversation history list.
