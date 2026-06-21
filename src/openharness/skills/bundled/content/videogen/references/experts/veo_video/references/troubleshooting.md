# Veo Troubleshooting

| Failure | Likely cause | Repair move |
|---|---|---|
| Generic realism | Prompt used quality adjectives instead of production facts | Add camera, lens/optics, physical light, material behavior, and one grounded action. |
| Weak action | Too much story for clip length | Reduce to one visible action with a final state. |
| Wrong framing | Aspect ratio chosen after prompt | Rewrite shot around 16:9 or 9:16 before generation. |
| Audio missing or vague | Audio not explicitly directed | Add a separate audio sentence with dialogue, ambience, SFX, or silence. |
| Dialogue confusion | Speaker not assigned or line too long | Name the speaker and shorten the line. |
| I2V identity drift | Reference role not explicit | State what the image locks and what may change. |
| Endpoint mismatch | First/last frames described loosely | Name start state, transition mechanism, and end state in order. |
| Extension drift | Planned state used instead of observed footage | Start from the accepted final frame and keep camera/light continuity. |
| Safety block | Prompt has protected identity, unsafe content, or evasive wording | Rewrite to authorized, generic, or fictionalized subject and remove evasion terms. |
| Negative prompt ineffective | Instructional negatives in prose | Use separate unwanted-element phrases when supported by the active surface. |

## Retry Rule

Change one major variable per retry: camera, action, reference role, audio, aspect ratio, or negative prompt. If three attempts fail the same way, change the scene design instead of adding more adjectives.
