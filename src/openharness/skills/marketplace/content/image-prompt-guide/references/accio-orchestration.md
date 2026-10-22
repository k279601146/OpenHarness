# Accio Workflow Integration

Use for delegated image steps, dependent sets, pending results or resumption. These are working-context conventions, not new API fields or a replacement scheduler.

## Entry and ownership

Accio activates `image-prompt-guide` through its existing Skill mechanism. Resolve resources from this Skill directory. Reuse current tool definitions, task context and asset handles. Do not introduce Codex-specific metadata, a new agent, mandatory CLI gateway or environment installation.

The caller owns the overall marketing plan, product-development proposals, video script or publishing workflow. This Skill owns the requested static images. Do not restart upstream research, replan a storyboard or ask again for accepted inputs.

Carry relevant context forward: purpose and count/order; source images and roles; product facts and evidence; literal copy and its language; conversation language; size/format; chosen style; accepted decisions; and required predecessor outputs. Distinguish proposed concept features from verified existing-product facts. Surface only genuinely missing facts that block the image task.

If Accio exposes `ask_user`, use its structured interaction for a blocking question, batching unresolved fields once. Follow its actual schema. Do not add a second generation-approval stage after the caller already obtained approval.

## Output planning

Proceed directly for one image. For a set, retain a compact association between each requested output, its sources, dependencies, generated result and delivery state. Reuse caller IDs and order. These internal associations are not extra parameters for the image tools.

- For multiple outputs, read [parallel-generation.md](parallel-generation.md) before the first call. Draft the ready group's distinct complete prompts together, then submit through native batch, concurrent tool calls, or async acknowledgements as actually supported. Submit independent ready work before waiting for its images. Do not serialize merely because outputs share product identity or a textual style. Preserve limits and original delivery order.
- Outputs depending on an accepted logo, previous frame or generated reference wait for that usable asset. Preserve an upstream sequential plan; do not parallelize it away.
- A user-designated first frame or completed merchant graphic may pass through unchanged. Do not regenerate it merely to count a tool call.
- In a video workflow, produce the specified static frames, preserve shot order/reference roles, and hand them back. Do not alter durations, combine shots or run video generation from this Skill.
- Reuse task records if the caller maintains them, through its exposed mechanism. Do not mandate `task_create`/`task_update` for every image or create a competing task graph.

## Pending, completion and resumption

Retain actual responses and errors. Distinguish planned, submitted, available, checked and delivered outputs. Count assets per requested output, not API calls: one call may return several candidates and several calls may repair one output.

For a returned image, associate and inspect it. For a task ID/status only, preserve that structure and follow Accio's documented asynchronous handling. Poll only if an available tool and the host assign polling to the agent. Do not fabricate a result URL or mark the set complete at submission.

Separate submission from collection: with asynchronous acknowledgements, submit the other ready siblings before polling the first. A blocking single-call host remains sequential; do not report parallel execution from prompt batching alone.

Resume using existing task/result handles. Repair only affected outputs; keep completed siblings. Avoid blind duplicate submissions on ambiguous timeout. If a required predecessor fails, report dependent outputs as blocked rather than substituting an unrelated image.

## Handoff and presentation

Use Accio's existing response/artifact mechanism. Provide actual available assets in the requested order with their proposal, listing-slot or storyboard association. Preserve task/status information for pending items and concise failure reasons for missing items. Follow a caller-provided output schema; otherwise do not impose a new JSON envelope.

A prompt, contact sheet, inaccessible local file, HTML draft or pending task ID does not silently replace the requested image. Register/upload locally assembled outputs through the existing asset/file mechanism where needed. Tool response keys, asset registration and canvas insertion come from Accio's current exposed contract, not a designer Skill's example.

Use the conversation language for user-facing messages. Keep internal prompts/records internal unless requested or included in the agreed deliverables. Publishing and live-listing changes remain the responsibility of the owning workflow and its authorization.
