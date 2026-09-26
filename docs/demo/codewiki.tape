# CodeWiki demo: the documentation table of contents, then a question.
#
# Render from the repository root:
#     vhs docs/demo/codewiki.tape
Output "docs/demo/codewiki.gif"

Set Shell "bash"
Set FontFamily "DejaVu Sans Mono"
Set FontSize 16
Set Width 1040
Set Height 560
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

Type "repowiki-cli codewiki structure pallets/flask"
Enter
Sleep 6s

Sleep 500ms
Type "repowiki-cli codewiki ask pallets/flask 'In one sentence, what is this project?'"
Enter
Sleep 14s
