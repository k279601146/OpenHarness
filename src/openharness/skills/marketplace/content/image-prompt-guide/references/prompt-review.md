# Prompt Review Before Generation

Use only when the user asks to inspect, debug or approve the prompt before generating, or explicitly requests prompt-only output. This is a diagnostic presentation mode, not a new Accio tool mode or a mandatory approval stage for ordinary work. Do not call an image generation/editing tool, submit a job or consume a generation retry during this mode. Reading source assets and available tool definitions is allowed; defer uploads or other mutations until execution unless separately authorized.

## Prepare from actual evidence

Read the task-relevant references and inspect the supplied source images. For ecommerce localization, show the source-to-target region map, protected product markings and allowed local reflow from [image-translation.md](image-translation.md). For other edits, use the selected operation in [edit-patterns.md](edit-patterns.md) to fill the four-item specification; show those resolved values rather than a generic task label. Apply the main Skill's pre-call check. For edits, resolve target, desired end state, protected properties and necessary consequences from the source and request. For new images, use the requested subject, purpose, content and layout constraints without inventing existing source structure.

If a source is inaccessible, say so. Do not claim a visual inspection from a filename, task summary or earlier generated result. Unknown dimensions prevent trustworthy pixel coordinates, not necessarily a semantic prompt. Distinguish observed facts, user requirements and unresolved assumptions briefly.

## Show a reviewable result

Explain the review in the user's conversation language; keep the actual model prompt in English while preserving literal artwork strings in their requested script. Present:

1. **Short task specification.** Target/source roles, desired result, protected properties and necessary consequences. Omit inapplicable items. List only unresolved assumptions that affect correctness.
2. **Exact proposed call.** If the current schema and bindings are known, show the actual tool name and proposed arguments in JSON. Include the full `prompt` string without abbreviations, with the same reference order and supported auxiliary fields planned for execution. If the schema or an asset binding is unavailable, show the exact prompt separately and list the unresolved fields outside the payload. Do not fabricate callable IDs, URLs, dimensions or parameters, or present a placeholder-filled payload as ready to execute.
3. **Brief coverage check.** Map each decisive requirement to the corresponding exact phrase in `prompt`. Include necessary structural consequences and critical protection constraints. Mark a missing or ambiguous clause as unresolved; repair it when evidence permits. This maps requirements to text, not a private reasoning transcript or a claim that generation will succeed.

Use the wording that will actually be submitted, not a polished summary of intended behavior. Check that optional auxiliary fields do not contradict or carry decisive information absent from `prompt`. Record the actual Skill/reference paths consulted when diagnosing loading issues, without claiming that a self-report proves runtime loading. Avoid lengthy execution summaries or claims of completed edits.

For multiple outputs, apply [parallel-generation.md](parallel-generation.md) to prepare the ready group's prompts together, but submit none in review mode. Show each output's own prompt, source/locale and dependency association; show shared decisions once. State the proposed submission mechanism only when exposed by the host, otherwise mark it unresolved. Reviewing one representative prompt does not make the other outputs ready. On authorized execution, retain each reviewed prompt and bind any resolved predecessor assets before dispatch.

## Continue after review

Stop at the requested review boundary. If the user then asks to generate using the reviewed prompt, retain that exact prompt and the agreed inputs. Do not silently summarize, retranslate or re-augment it. Resolve pending asset bindings using the existing host mechanism, and revalidate supported parameters. Surface any required change to the agreed prompt or source that materially affects the result. Follow Accio's existing execution and asynchronous handling; no new approval stage is needed after authorization.

When debugging a later run, distinguish the reviewed proposal, actual tool submission and any available downstream payload. They are separate evidence. Compare the prompt and input bindings across them before attributing a mismatch to model execution. This Skill cannot guarantee a wrapper's internal forwarding or merging behavior.
