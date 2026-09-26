# Combined header demo: all three services in one recording.
#
# Render from the repository root:
#
#     ZREAD_TOKEN="$(cat ~/.zread_token)" vhs docs/demo/header.tape
#
# The Zread `ask` turns are token-gated. The token is read from the environment,
# never typed, so it stays out of this file, the transcript, and the recording.
# Zread's talk endpoint is also flaky — if a turn errors, re-run the render.
Output "docs/demo/header.gif"

Set Shell "bash"
Set FontFamily "DejaVu Sans Mono"
Set FontSize 15
Set Width 1040
Set Height 700
Set Padding 16
Set Framerate 15
Set TypingSpeed 45ms
Set PlaybackSpeed 5.0
Set Theme "Dracula"
Set CursorBlink false

# Plain prompt, hidden setup, clean screen.
Hide
Type "PS1='$ '"
Enter
Type "clear"
Enter
Show
Sleep 400ms

# ---- DeepWiki ----------------------------------------------------------
Type "repowiki-cli deepwiki structure google-deepmind/alphafold3"
Enter
Sleep 7s

Sleep 400ms
Type "repowiki-cli deepwiki ask google-deepmind/alphafold3 'In one sentence, what is the main entry point?'"
Enter
Sleep 9s

Sleep 400ms
Type "repowiki-cli deepwiki ask google-deepmind/alphafold3 --mode fast --stream"
Enter
Sleep 4s
Type "In one sentence, what is the main entry point?"
Enter
Sleep 45s
Type "/exit"
Enter
Sleep 1s
Type "clear"
Enter
Sleep 400ms

# ---- CodeWiki ----------------------------------------------------------
Type "repowiki-cli codewiki structure google-deepmind/alphafold3"
Enter
Sleep 7s

Sleep 400ms
Type "repowiki-cli codewiki ask google-deepmind/alphafold3 'In one sentence, what is the main entry point?'"
Enter
Sleep 15s
Type "clear"
Enter
Sleep 400ms

# ---- Zread -------------------------------------------------------------
Type "repowiki-cli zread find alphafold"
Enter
Sleep 4s

Sleep 400ms
Type "repowiki-cli zread stat google-deepmind/alphafold3 --human --stale"
Enter
Sleep 7s

Sleep 400ms
Type "repowiki-cli zread ask google-deepmind/alphafold3 'In one sentence, what is the main entry point?'"
Enter
Sleep 55s

Sleep 400ms
Type "repowiki-cli zread ask google-deepmind/alphafold3 --stream"
Enter
Sleep 4s
Type "In one sentence, what is the main entry point?"
Enter
Sleep 55s
Type "/exit"
Enter
Sleep 1s
