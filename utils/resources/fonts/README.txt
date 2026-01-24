[Fonts Installation Guide]

This plugin relies on local fonts to ensure text is rendered correctly in Docker environments, especially for Chinese characters.

Status:
- "Noto Sans SC" (Simplified Chinese) has been AUTO-DOWNLOADED as .woff2 files. (Success!)
- Other fonts (Roboto, Open Sans, etc.) still need manual installation if you see issues, but they are less critical for Chinese support.

Files currently present (should represent Chinese font):
- NotoSansSC-Regular.woff2
- NotoSansSC-Bold.woff2

If you still see boxes (tofu) for Chinese characters:
1. Try downloading the FULL TTF versions manually (as the auto-downloaded woff2 is a subset).
2. Place them here as:
   - NotoSansSC-Regular.ttf
   - NotoSansSC-Bold.ttf
3. Update `../templates/_fonts.html` to point back to `.ttf` instead of `.woff2`.

Manual Download Links for TTF:
   https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC-Regular.ttf
   https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC-Bold.ttf

Restart the bot after any changes.
