# Batch Prompts and Concurrent Image Tasks

Use before the first image call for multiple requested outputs. The execution unit is one deliverable with its own complete prompt and source binding. Prepare a ready group together, submit through the existing host, then collect its results. These are Agent instructions, not a new Accio API or scheduler.

## 1. Plan one group, write multiple prompts

Reuse the caller's IDs, order and dependencies. Resolve shared product facts, reference roles, style, glossary and output constraints once. For each item retain:

`output ID | purpose/locale | source bindings | dependencies | exact prompt | supported call arguments | task/result handle | status`

Use the caller's task records if available; otherwise keep a compact internal list. These bookkeeping fields must not be added to image tool arguments. Do not produce a user-facing planning report unless requested.

Draft all prompts in the current independent group in one planning pass. Each uses the shared context plus only its own subject, composition, copy and locale. Include necessary context in each actual prompt: "same as image 1" is insufficient. Run the main Skill's pre-call check for each item before submission. Distinct roles/locales require distinct prompts; multiple candidates of one prompt do not fulfill different tasks.

For a large set, use manageable groups compatible with the host's context and queue limits; do not require every future prompt to be ready before any work starts. A missing input blocks only its affected items and descendants. Keep other ready items moving.

Drafting multiple prompts in one Agent response is **batch preparation**, not simultaneous LLM inference. Separate prompt workers are optional only when the caller already exposes and permits them. This Skill does not require extra agents or a new model endpoint.

## 2. Distinguish shared context from asset dependencies

| Situation | Scheduling decision |
|---|---|
| Listing images share supplied product photos, copy or a textual style brief | Independent: prepare together and submit together |
| Several locales of several existing images | One item per requested source/locale pair, all using their original source; no locale-to-locale chain |
| Applications require a newly generated logo or character reference | Resolve that specific reference first; then release dependent applications |
| A caller requires review of the first visual before the rest | Keep this dependency; do not invent such a gate for every set |
| Independent detail-page sections plus a final long image | Submit sections together; assemble only after required sections are usable |
| A later edit uses an earlier result, or a frame needs predecessor continuity | Keep the actual edge; independent branches may still run |

Sharing a visual system does not require generating an extra anchor. An actual predecessor must return a usable inspected asset before it can bind dependent prompts. Prepare dependency-independent copy early, but finalize its asset bindings before dispatch.

## 3. Select the supported submission mechanism

Inspect the current host/tool definitions once; reuse the conclusion for the run. Use the first applicable mechanism that preserves per-item prompts, inputs and result associations. Keep [generation-runtime.md](generation-runtime.md) single-call fields unless a live batch schema explicitly replaces them.

| Exposed capability | What the Agent does |
|---|---|
| Native batch accepting distinct per-item prompts and references | Submit the ready items in that documented schema. Retain its index/ID mapping and partial results. A candidate-count field is not this capability. |
| Host supports concurrent tool calls or an existing parallel executor | Emit the ready image calls in the same dispatch turn/group, or use that exposed executor. Do not await one image before issuing its independent sibling. |
| Submission returns a pending task handle and completion is separate | Submit ready items and record their acknowledgements first. Only then enter status/result collection through existing host facilities. Briefly awaiting an acknowledgement is different from waiting for the image to finish. |
| Only a blocking single-call interface is exposed | Execute sequentially. Keep the batch prompts and result mapping; report the execution limitation when relevant. Do not claim concurrent generation. |

Respect caller concurrency, queue, rate and budget limits. If the host manages limits for confirmed concurrent calls, submit through that scheduler even when its numeric limit is hidden; an unknown numeric limit alone is not a reason to serialize. If concurrency capability itself is unknown, use the available documented mechanism and mark concurrency unverified. Do not invent `prompts`, `parallel`, `concurrency`, `batch_generate`, status endpoints, threads or a replacement CLI.

When an explicit in-flight limit applies, fill the available slots from ready items and refill as results free slots; no need to wait for the slowest sibling. If the host accepts a queued batch, let it manage that queue. Submit each item once. Do not reorder an explicitly sequential caller workflow or silently exceed requested variants to manufacture concurrency.

## 4. Collect by identity, then release dependent work

Keep `planned`, `submitted`, `available`, `checked`, `delivered`, `failed`, `blocked`, and `unverified` distinct. A submission acknowledgement is not an image. Associate responses by the original call/task mapping, never arrival order. Inspect available outputs against their own requirements and shared identity/style; inspection of one completed image should not delay submission of an already ready independent item.

Use only host-provided waiting/status handling. A timeout with an existing or uncertain task is unresolved, not permission to submit a duplicate. Resolve status first; retry only when failure or non-acceptance is established. A confirmed rate-limit rejection defers only that item. Repairs affect only failed outputs within the existing repair budget. If a predecessor fails, keep descendants blocked and continue unrelated branches.

Assemble only usable required modules in their original order; never close a gap silently. Deliver successful standalone outputs when useful, labeling a partial set and retaining pending/failed associations. A contact sheet is optional and does not replace the requested individual files.

## 5. Execution examples

**Three listing images from an existing product reference:** prepare hero, feature, and contents with their own complete prompts. With concurrent calls, dispatch all three before waiting. With async handles, submit hero -> receive handle, feature -> receive handle, contents -> receive handle, then collect. If completion is contents -> hero -> feature, delivery remains hero -> feature -> contents. Do not use hero as the source of its siblings unless the caller actually requires it.

**Two sources into two locales:** prepare four independent items after resolving the glossary and each source's text regions. Every item points to its own original source. If one region is unreadable, block that affected work or explicitly agree on a partial translation; the other source's items can proceed.

**Logo and two packaging mockups:** create/resolve the logo, inspect and settle any required identity choice, then dispatch both applications with that actual logo asset. A text description of the intended logo cannot substitute for the dependency.

## 6. Verify execution claims

When diagnosing latency, capture exact per-item prompts/arguments, submission and completion times, returned handles, outcomes and delivery IDs from real host records. Distinguish Agent dispatch overlap from backend generation overlap: submit-all-before-wait can expose concurrency, but the service may still queue work. Claim measured speedup only from comparable runs with the same outputs, settings and retry policy. A list of prompts, tool acknowledgements or simulated schedule is not evidence of Accio throughput.
