# Speech Generation

Read this only when generating new narration, character dialogue, or voice-over. Reuse existing speech directly; use the transcription capability for transcription and subtitles, and the sound capability for BGM, ambience, or action effects

Inputs are approved lines, language, voice direction, delivery context, and timing requirements; the output is an accessible speech file. For a speech-only task, deliver the audio directly

## Delivery and Generation

If `tts-prompter` is available in the current environment, read it first to organize the prompt; otherwise continue with the available tools. Follow the current schema for voice, language, duration, and call fields

- Separate “how to say it” from “what to say.” Write the style instructions in English, specifying the target language, accent, speaking pace, and context; write the lines in the language that should actually be spoken
- Keep the lines consistent with the delivery direction, use natural punctuation to arrange pauses, and add necessary local delivery tags when the tool supports them
- Keep the same voice and delivery baseline for each character; identify the speaker of every line in a conversation
- For precise editing, generate by sentence or thought group and retain separate files; for ordinary full-passage reading, keep it complete, accurate, and natural

## Review and Next Steps

Audition and check the lines, pronunciation, language, phrasing, and file usability. When aligning with video, measure the actual duration before adjusting the copy or pacing

Deliver the speech file. When precise arrangement against picture is needed, record the actual duration and align it during local assembly; read the [transcription capability](transcription.md) when transcription or subtitles are needed
