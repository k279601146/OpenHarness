# Edit Prompt Patterns

Read only the selected section. Questions are slots to resolve from actual images and user intent, not questions to ask the user automatically. Patterns produce sentences for the existing prompt string, not additional tool fields. Use English instructions with exact display strings preserved. Omit irrelevant slots, remove all placeholders, and retain the four-item specification for inspection. Examples assume the stated observations; do not copy their product facts into other tasks.

## Attribute

**Resolve:** Which image and region are edited? Which attribute changes, and to what value or donor? Which shape, marks and adjacent regions must stay? Does the new finish require different reflections?

**Pattern:** "In Image [base], change only [region]'s [attribute] to [value]. [Image donor] supplies only [attribute]. Preserve [identity/shape/marks] and [vulnerable neighbors]. Allow [necessary surface response] while retaining [lighting or scene constraints]."

**Example:** Request: use the swatch's blue on the bag fabric. Observed: Image 1 is a fabric bag with tan leather handles and a printed label; Image 2 is a blue swatch. Specification: bag fabric / swatch blue / tan handles, label and shape / shading consistent with the fabric folds.

Usable prompt: "Input images: Image 1 is the edit target; Image 2 supplies fabric color only. Primary request: Recolor only the bag's fabric panels to match Image 2's blue. Product invariants: Preserve the tan leather handles, printed label, bag shape and background. Allowed changes: Fabric color and its shaded appearance across the existing folds."

Weak: "Make the bag match Image 2." This can transfer the wrong identity or recolor every material. Check: target attribute correct; boundaries, neighboring materials and identity intact.

## Text

For ecommerce image translation with product/layout preservation, use [image-translation.md](image-translation.md) instead of this literal-edit pattern.

**Resolve:** Literal replacement, translation, removal or new copy? Which strings map to which destinations? Which region and occurrences? Which text, branding and layout remain? Is layout adjustment necessary for the destination script or length?

**Pattern:** "Replace [source string] with exactly [destination string] in [region/occurrences]. Preserve [protected copy, graphics and surface]. Match [typography/perspective]. Allow only [needed fit adjustment]. Render the destination verbatim without correction or extra text."

**Example:** Request: replace only the top heading with "reeemix". Observed: a flat poster has one top heading and a separate brand mark. Specification: top heading / literal reeemix / brand and lower copy / fit within the heading area.

Usable prompt: "Primary request: Replace only the top heading with exactly \"reeemix\". Typography: Keep the existing heading style and fit the literal replacement inside its existing area; do not autocorrect the spelling. Product invariants: Preserve the separate brand mark, lower copy, images and background. Allowed changes: Top-heading text and spacing needed to fit it."

Weak: "Correct and refresh the poster text." This authorizes a different operation. Check: character-by-character match, correct scope, protected copy and surface perspective. Translation permits changes to selected strings, not unrelated brand names.

## Structure and placement

**Resolve:** Which object/part changes? Which part determines placement or alignment? What visible landmark or region defines the target? What support, orientation, scale, clearance or interaction is needed there? What source area needs repair? Which reference features and framing remain fixed?

**Pattern:** "Move/change [object or part] so that [placement part] is [specific relationship] to [visible reference] on/in [surface or region]. Set [required orientation/interaction]. Preserve [identity and fixed references]. Allow [necessary dependent changes]. Remove/repair [vacated content] when applicable."

Do not fill every spatial slot when irrelevant. Use the arrowhead or designated region as evidence, not a default destination. Resolve the target before removing annotation. A coordinate supplements a visible relation; it does not replace the relation or require a new tool parameter.

**Example:** Request: place the desk lamp at the marked spot and light the notebook. Observed: an arrow ends on the left tabletop beside a notebook; the current shade points away. Specification: lamp base / marked tabletop spot and shade toward notebook / lamp design, notebook and camera / lamp pose, contact shadow and old-site repair.

Usable prompt: "Primary request: Move the entire desk lamp so its base rests at the arrowhead on the left tabletop beside the notebook. Turn its shade toward the notebook pages. Product invariants: Preserve the lamp design, notebook position, desk and camera framing. Allowed changes: Lamp location and pose needed to aim at the notebook, contact shadow and the affected light; repair the old lamp location and remove the arrow. Avoid: A second lamp or moving the notebook to meet the target."

Weak: "Move the lamp to the marker; preserve its silhouette and all shadows." This leaves placement vague and can forbid necessary pose changes. Check: the designated part meets the target relation, supports/contacts are coherent, fixed references stay fixed and no unwanted duplicate remains. For shape redesign, protect only the features outside the authorized redesign.

## Viewpoint

**Resolve:** Does the camera move or the product rotate? Which face should become frontal or newly visible, and at what elevation? What stays fixed? Which identity details are supported by the references? Does a newly visible critical part lack evidence?

**Pattern:** "Change [camera view/object orientation] to show [faces/elevation]. Preserve [physical identity and fixed scene properties]. Allow perspective-dependent outline, occlusion and reflections to update. Use [reference] for [newly visible features]."

**Example:** Request: show the box straight from the front. Observed: a three-quarter packshot with a readable front label. Specification: camera view / front panel square to camera / package proportions and label / projected outline and visible side area.

Usable prompt: "Primary request: Change the view to a straight-on, eye-level packshot with the box's front panel facing the camera squarely. Product invariants: Preserve the package's physical proportions, front label text, material and background color. Allowed changes: Perspective, projected outline, side visibility and reflections needed for the front view."

Weak: "Make it front-facing while keeping exactly the same outline." Check: requested view visibly achieved without redesigning the product. Ask for another view only when unknown identity-critical details materially affect the requested result; do not invent hidden components as fact.

## Environment and style

**Resolve:** Which background, lighting or style changes? Is subject restyling authorized, or only environmental adaptation? Which identity attributes stay? What contact, illumination, edge treatment or reflection must adapt?

**Pattern:** "Replace/change [environment or style] to [target]. Preserve [subject identity, marks, composition as applicable]. Update [environment-dependent effects] to integrate the subject. Change [subject styling] only if requested."

**Example:** Request: put a supplied white shoe on a dark studio background. Specification: background / dark studio / white shoe, sole geometry and logo / edge separation and contact shadow.

Usable prompt: "Primary request: Replace the background with a dark studio setting. Product invariants: Preserve the shoe's white material identity, sole geometry, logo and pose. Allowed changes: Background, appropriate illumination and a coherent contact shadow; keep the white shoe edges distinguishable from the background."

Weak: "Make everything dark and dramatic." Check: new environment/style achieved without unintended material or identity change. A transparent cutout requires actual alpha, not a painted checkerboard; verify through existing runtime facilities.

## Removal and compositing

**Resolve:** Remove, extract or insert? Which source contributes which object? Which base and region receive it? What disappears, remains or needs reconstruction? What scale, contact, occlusion and lighting connect the subjects?

**Pattern:** "In Image [base], remove [target] and reconstruct [exposed region], preserving [neighbors]." Or: "Insert [subject] from Image [donor] into Image [base] at [target relation]. Match [scale, perspective/contact]. Preserve [identity and base content]."

**Example:** Request: place the product from Image 2 on the shelf in Image 1. Observed: a bottle cutout and an empty shelf. Specification: bottle / base resting on shelf surface / bottle label and shelf scene / scale, edge integration and contact shadow.

Usable prompt: "Input images: Image 1 is the base scene; Image 2 supplies the bottle and its label. Primary request: Place one bottle from Image 2 on the empty shelf in Image 1, with its base resting on the shelf surface. Product invariants: Preserve the bottle shape and label and the surrounding shelf contents. Allowed changes: Bottle placement and scale consistent with the shelf perspective, edge integration and contact shadow."

Weak: "Combine both images." Check: correct donor identity, intended placement, coherent occlusion/contact and protected neighbors. For removal, check the exposed region and absence of the requested object rather than accepting a blurred remnant. For SKU extraction, native isolation can suffice; do not invent new inventory.
