# Zread demo: repository discovery, then repo metadata with a staleness check.
#
# `zread ask` / `submit` require a ZREAD_TOKEN, so the demo sticks to the
# token-free commands (never show a token on screen).
#
# Render from the repository root:
#     vhs docs/demo/zread.tape
Output "docs/demo/zread.gif"

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

Hide
Type "PS1='$ '"
Enter
Type "clear"
Enter
Show
Sleep 400ms

Type "repowiki-cli zread find react"
Enter
Sleep 5s

Sleep 500ms
Type "repowiki-cli zread stat google-deepmind/alphafold3 --human --stale"
Enter
Sleep 8s
