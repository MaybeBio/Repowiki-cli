# DeepWiki demo: the documentation table of contents, then a question.
#
# Render from the repository root (needs vhs + ttyd + a browser):
#     vhs docs/demo/deepwiki.tape
# `repowiki-cli` must be on PATH inside the recorded shell; the tape inherits
# the environment vhs was started with. Output paths are relative to the
# directory vhs is run from, hence the docs/demo/ prefix.
Output "docs/demo/deepwiki.gif"

Set Shell "bash"
Set FontFamily "DejaVu Sans Mono"
Set FontSize 15
Set Width 1040
Set Height 700
Set Padding 16
Set Framerate 15
Set TypingSpeed 45ms
Set PlaybackSpeed 2.0
Set Theme "Dracula"
Set CursorBlink false

# Give the demo a plain `$ ` prompt and a clear screen. `Hide` only suppresses
# frame capture, so a separate `clear` is what removes the setup from the
# scrollback (typing both on one line leaves a repaint artifact).
Hide
Type "PS1='$ '"
Enter
Type "clear"
Enter
Show
Sleep 400ms

Type "repowiki-cli deepwiki structure encode/starlette"
Enter
Sleep 9s

Sleep 500ms
Type "repowiki-cli deepwiki ask encode/starlette 'In one sentence, what is this project?'"
Enter
Sleep 18s
