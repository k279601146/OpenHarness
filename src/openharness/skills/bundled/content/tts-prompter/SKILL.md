---
name: tts-prompter
description: MUST read this skill BEFORE entering generate mode for text-to-speech (TTS) tasks. Covers prompt crafting framework, separating spoken text from style instructions, and using markup tags vs natural language for emotions and non-speech sounds.
---

# TTS Prompter

This skill provides the definitive framework for crafting high-quality Text-to-Speech (TTS) prompts. You MUST follow these guidelines when generating speech to ensure natural, expressive, and predictable audio output.

## 1. The Ultimate TTS Formula

To generate perfect audio, always construct your single input string using this formula:

**`{Language, Accent, and Situational Style Instructions}: {Emotionally Aligned Text (with local action tags only if needed)}`**

The most critical rule in TTS prompting is physically separating **"Director Instructions"** (how to speak) from the **"Script"** (what to say) using a colon (`:`).

**Core Alignment Rule:** The style instructions, the text content, and any tags should all point in the same direction. A scared-sounding instruction works best with text that actually sounds alarming.

### Multi-speaker Conversations

For dialogues, use the colon to separate the global instructions from the script, and also to separate speaker names from their lines:

```text
TTS the following conversation between Joe and Jane:
Joe: How's it going today Jane?
Jane: Not too bad, how about you?
```

## 2. Part 1: Style Instructions (Before the Colon)

The Style Instructions section is your primary tool for controlling the overall performance. **This part is NEVER spoken.**

**Mandatory Rule:** You MUST write the Style Instructions entirely in English, regardless of the target language being spoken. The model follows English instructions most reliably.

**Tip 1: Don't overspecify.** The model fills in gaps naturally. Leaving some room often produces more natural results than controlling every detail.

**Tip 2: Avoid naming real brands or real-person identities.** Phrasing like "Chanel-style" or "like a TikTok creator promoting her favorite brand" is the most common trigger of policy blocks. Describe the desired *style* in generic terms instead.

**Tip 3: Steer clear of sensitive content cues.** Prompts that touch on violence, sexual content, hate, self-harm, or illegal activities (per [Google's policy](https://policies.google.com/terms/generative-ai/use-policy)) can be silently blocked. Soften descriptors and remove explicit cues.

### 2.1 Controlling Language, Emotion, Tone & Accent

Provide a specific, situational description. Because the Style Instructions carry the highest weight in the model's generation logic, you MUST explicitly state the target language and accent here to ensure correct output.

If the Spoken Text contains a mix of languages (e.g., Japanese with English words), you MUST explicitly state this mixed-language requirement in the Style Instructions so the model knows to switch pronunciation rules dynamically.

*   ❌ **Weak:** `Speak in a scared way: I think someone is in the house.`
*   ✅ **Strong:** `You are hiding in a dark closet. Speak in English with a terrified, trembling whisper as if you are afraid of being caught: I think someone is in the house.`
*   **Language & Accent Example:** `Speak in Brazilian Portuguese with a standard São Paulo accent: Bem-vindo ao nosso programa de hoje.`
*   **Mixed Language Example:** `Speak in a mix of Japanese and English, with a professional and confident tone: 私たちの新しい製品は強力な AI capabilities を備えており、既存の workflow にシームレスに統合できます。`

*(Note: If you mention a conflicting language here, e.g., "Read as a Japanese boy" but the text is Portuguese, the model will output Japanese.)*

### 2.2 Emotion & Tone

To coax the model into making natural sounds without relying on tags, set up the prompt and provide "breath markers" in the text.
*   **Laughing:** `React to the text with an amused, genuine laugh before speaking: Hahaha, I did NOT expect that. Can you believe it!`
*   **Sighing:** `You are exhausted and frustrated. Start the sentence with a heavy, tired sigh: Oh man... I can't do this anymore.`

### 2.3 Pacing & Volume

Use the Style Instructions to force physical delivery changes:
*   **Pacing:** `Read this disclaimer extremely fast, like a radio commercial voiceover rushing through the terms and conditions: Availability and terms may vary. Check our website for details.`
*   **Volume:** `You are trying not to wake a sleeping baby. Whisper this entire sentence as quietly as possible: I think he finally fell asleep.`

## 3. Part 2: Spoken Text (After the Colon)

The Spoken Text contains the actual words to be synthesized. **This part IS spoken.**

**Mandatory Rule: Match the target language.** The Spoken Text MUST be written in the exact language(s) you want the model to speak. If you want Japanese, write in Japanese characters; if you want a mix of Japanese and English, write the text exactly as a mix of Japanese and English. Do not rely on the model to translate on the fly.

**Tip: Punctuation matters.** Commas, periods, and semicolons create natural pauses. Use them to help the model breathe.

### 3.1 Using Markup Tags

You may use **Markup Tags** (words enclosed in brackets like `[sigh]`) inside the Spoken Text to inject specific, localized actions or style modifications.

**Golden Rule: Tags for precision, instructions for tone.** Use tags inside the Spoken Text when you need a specific moment (a laugh, a pause, a whisper). Use the Style Instructions before the colon to set the overall feel.

*(Note: There is no exhaustive, hardcoded list of tags. The model interprets any descriptive word in brackets. However, you MUST follow the rules below.)*

#### DO Use Tags For:

Place these tags **inside the Spoken Text** (after the colon). They will not be read as words.

1.  **Non-speech sounds:** `[sigh]`, `[laughing]`, `[uhm]`, `[cough]`, `[gasp]`, `[snorts]`
    *   *Example:* `Say the following casually: Well, [uhm], let me think about it. [sigh] I guess we have no choice.`
2.  **Local style shifts:** `[shouting]`, `[whispering]`, `[extremely fast]`, `[sarcasm]`, `[asmr]`
    *   *Example:* `Narrate the following: He looked at me and said, [shouting] 'Get out!'`
3.  **Pacing and pauses:** `[short pause]` (~250ms), `[medium pause]` (~500ms), `[long pause]` (~1000ms+)
    *   *Example:* `Read this like a game show host: The winner is... [long pause] ...John!`

#### DO NOT Use Tags For:

**NEVER use emotional adjective tags** (e.g., `[scared]`, `[curious]`, `[bored]`, `[excitedly]`) inside the Spoken Text. 
*   *Why?* The TTS engine will literally read the word aloud (e.g., it will say the word "scared" before the sentence), ruining the audio.
*   *Solution:* Move emotional descriptions to the Style Instructions (before the colon).

## 4. Duration vs Faithfulness

TTS output duration is **not deterministic**: the model speaks at a rate it chooses, and you cannot tightly control physical seconds via prompt wording or rate tags.

- **Standalone TTS tasks with no explicit time limit** (the user just wants audio of a text): ignore duration concerns. Optimize for **reading the text fully and accurately** in the requested style.
- **Time-constrained tasks** (e.g., narration in `video-generator`, dubbing to a fixed clip, ad spots): consult the `Unit` and `Rate` columns in the Language Catalog (§5.2 below), and follow the calling skill's rules for sizing text against the budget.

## 5. References: Model Priority & Voice Catalog

The `language_code` parameter acts only as an auxiliary hint to select the correct regional voice model (e.g., `en-US` vs `en-GB`). It does NOT force the output language.

### 5.0 Default Model & Priority Strategy (默认模型与优先级策略)

> [!IMPORTANT]
> **Default Free Tier Priority**: By default, always prioritize using **Fish Audio** under the **`fish-audio-s2.1-pro-free`** model (Fish Audio S2.1-Pro Free) because it is a **free tier** with high-fidelity speech synthesis. Unless the user explicitly requests another paid model or specifies a MiniMax-exclusive voice, use `fish-audio-s2.1-pro-free` as the default.

- **When generating with Fish Audio voices**: Use `model_id: "fish-audio-s2.1-pro-free"` (default) or fallback models `fish-audio-drama-3-preview` / `fish-audio-s2.1-pro`.
- **When generating with MiniMax voices**: When using MiniMax character/drama/broadcast voices listed below, specify `model_id: "minimax-speech-2.8-hd"`.

---

### 5.1 Voice Catalog

The system integrates two authoritative voice providers: **Fish Audio** (44 curated voices) and **MiniMax** (303 official system voices).

#### 5.1.1 Fish Audio Voices (默认优先 / 免费档位优先)

Default model: `fish-audio-s2.1-pro-free`. Pass the `Voice ID` (32-char Hex or `default`) to `generate_audio`.

##### Official & Licensed Voices (官方商业认证与默认音色)

| Voice Name | Voice ID | Lang | Gender | Category | Character / Timbre & Recommended Use |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Fish 官方默认音色** | `default` | zh | Neutral | narration | Fish Audio 官方默认高保真自然音色（无需指定参考音色模型，通用稳定） |
| **さとる (和風平稳男声)** | `297a6fd278df47c3b9da9bfdf55ac89a` | ja | Male | narration | Fish Audio 官方商业认证日系男声，温和从容、吐字清晰，适合朗读教学与影视旁白 |
| **きょうこ (知性播音女声)** | `b2d9d8db057042688a5e318b8f405bc2` | ja | Female | business | Fish Audio 官方商业认证日系女声，知性优雅、专业清晰，适合客服语音与信息播报 |
| **じん (电台主持亲切男声)** | `d738c70d206149e69f8e3b6fc8af9d96` | ja | Male | casual | Fish Audio 官方商业认证电台主持男声，磁性平稳、亲切随和，适合播客与访谈 |

##### Chinese Voices (中文精选通用音色)

| Voice Name | Voice ID | Lang | Gender | Category | Character / Timbre & Recommended Use |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **大气播音国配男声** | `59cb5986671546eaa6ca8ae6f29f6d22` | zh | Male | narration | 央视大片级配音质感，底蕴深厚、字正腔圆，适合大型纪录片、政企宣传与文史演播 |
| **影视解说男声** | `b4bdf5dc66004241a21ff2df165bf442` | zh | Male | narration | 极具感染力的影视与剧情解说男声，抑扬顿挫抓人耳球，适合短视频解说与故事精讲 |
| **宣传片浑厚男声** | `dd43b30d04d9446a94ebe41f301229b5` | zh | Male | business | 大气磅礴、悠扬浑厚的高级品牌宣传片配音男声，穿透力强，极具商务号召力 |
| **活力元气女声** | `5c353fdb312f4888836a9a5680099ef0` | zh | Female | casual | 青春活泼、明快自然的年轻女声，如同大学校园邻家女孩，适合生活日常Vlog与对话 |
| **电商带货女主播** | `57eab548c7ed4ddc974c4c153cb015b2` | zh | Female | business | 热情充沛、语速轻快、号召力强的带货女主播声线，适合电商促销与爆款短视频 |
| **温柔动听女声** | `faccba1a8ac54016bcfc02761285e67f` | zh | Female | narration | 温润柔和、如沐春风的抒情演播女声，声线轻柔治愈，适合有声读物、睡前故事与情感散文 |
| **游戏解说男声** | `959b9a533d984b9a92af0c101a92118f` | zh | Male | entertainment | 激情澎湃、节奏明快的游戏高光与实况解说男声，充满竞技张力与临场感 |
| **历史故事讲述男声** | `6fc59d2b56cf402eb572934114c8d8aa` | zh | Male | narration | 情绪沉稳克制、深邃有内涵的叙事男声，适合历史风云、传记故事与严肃纪录开篇 |
| **温情校园女声** | `a1417155aa234890aab4a18686d12849` | zh | Female | casual | 纯真真挚、柔和清澈的校园女声，富有青春怀旧气息，适合毕业季寄语与情感独白 |
| **新闻资讯播报男声** | `2926cb350f1a426d800bf8c360c3cb94` | zh | Male | business | 严肃权威、吐字清晰规范的新闻播音员声线，适合早晚报速览、金融快讯与权威通报 |
| **知性教学科普女声** | `cf71d823861b4e0eadff1672d646da36` | zh | Female | educational | 条理分明、知性温和的教师科普女声，适合在线微课、知识解说与逻辑教程讲解 |
| **史诗评书低沉男声** | `4f328dc477ab4e36a36f0b761e69c410` | zh | Male | drama | 苍劲低沉、带有传统评书韵味的戏剧演播男声，适合三国演义、英雄史诗与战役风云 |
| **台湾甜美女生** | `e855dc04a51f48549b484e41c4d4d4cc` | zh | Female | casual | 软萌甜美、语调亲切自然的台湾腔调女声，适合轻松甜宠短剧、萌系配音与日常闲聊 |
| **纪实厚重男声** | `2cb86560d1a541fa842a8571a5ffa70b` | zh | Male | narration | 沧桑沉郁、声如洪钟的硬核纪实解说男声，适合军工重器、自然地理与厚重史册 |
| **武侠江湖叙事男声** | `bbfff76fd7c74f35a04a33366574f2d6` | zh | Male | drama | 快意恩仇、沉稳自如的国风武侠讲书男声，适合仙侠修真、江湖传奇与有声剧对白 |
| **商务文旅专业女声** | `a616236f5e874bcd84fceae68410680f` | zh | Female | business | 亲切得体、落落大方的展馆导览与文旅推荐女声，适合城市宣传片与商业汇报 |
| **自然清爽对话男声** | `29a7eea9ed484ef6b175da9bcfb49979` | zh | Male | casual | 不紧不慢、毫无雕琢感的原生生活系男声，适合播客闲聊、随笔漫谈与口语化内容 |

##### English Voices (英语精选通用音色)

| Voice Name | Voice ID | Lang | Gender | Category | Character / Timbre & Recommended Use |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Energetic Commercial Male** | `802e3bc2b27e49c2995d23ef70e6ac89` | en | Male | business | Dynamic, vibrant English male voice with high commercial punch for promos and ads |
| **Sarah - Gentle Narrative Female** | `933563129e564b19a115bedd57b7406a` | en | Female | narration | Soft, warm, articulate English female voice ideal for audiobooks and gentle storytelling |
| **E-Girl Gaming Voice** | `ca3007f96ae7499ab87d27ea3599956a` | en | Female | drama | Bright, playful, upbeat anime & gaming English female voice for characters and dialogue |
| **Hannah - Professional Corporate Female** | `9a9cf47702da476aa4629e2506d4a857` | en | Female | business | Confident, polished corporate English female voice suitable for presentations and training |
| **Adrian - Deep Narrative Male** | `bf322df2096a46f18c579d0baa36f41d` | en | Male | narration | Resonant, measured, cinematic English narrator voice perfect for history and documentaries |
| **Ethan - Educational Narrator** | `536d3a5e000945adb7038665781a4aca` | en | Male | educational | Clear, informative, articulate English male voice for online courses and explainer videos |
| **Friendly Conversational Female** | `b545c585f631496c914815291da4e893` | en | Female | casual | Natural, pleasant, approachable English conversational female voice for lifestyle and social media |
| **Calm Gentle Conversational Male** | `0b74ead073f2474a904f69033535b98e` | en | Male | casual | Relaxed, genuine, unhurried English male voice for podcasts, chats, and mindful narrations |
| **Professional News Anchor Male** | `05aff7ff557d45d2ace9a639452451ea` | en | Male | business | Crisp, authoritative, television-grade English broadcast voice for daily news digests |
| **Brian - British Gentleman Narrator** | `65c0b8155c464a648161af8877404f11` | en | Male | narration | Distinguished, classic British English gentleman voice for literature readings and period drama |
| **Documentary Storyteller Male** | `0327fdb5da9e4fd782899a8058c8ae2b` | en | Male | narration | Evocative, clear documentary narrator voice with rich cadence for science and nature content |
| **Selene - Soft Storytelling Female** | `b347db033a6549378b48d00acb0d06cd` | en | Female | narration | Velvety, intimate, calming English female narrator voice for meditation and sleep tales |

##### Japanese Voices (日语精选通用音色)

| Voice Name | Voice ID | Lang | Gender | Category | Character / Timbre & Recommended Use |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **元気な女性 (元气日常女声)** | `5161d41404314212af1254556477c17d` | ja | Female | casual | 明るく親しみやすい日本語日常会話ボイス。柔らかく優しい語り口でVlogや対話に最適 |
| **落ち着いた男性 (沉稳青年男声)** | `45c5d3723c9c42f598e4776dcfd5f02d` | ja | Male | narration | 穏やかで知的なトーンを持つ日本語青年ボイス。解説動画や落ち着いた日常トークに適合 |
| **女性ナレーション (商业广告女声)** | `825c9e9870494118ad93b6853a22d5e7` | ja | Female | business | 透明感と説得力を兼ね備えた日本語CM・プロモーション向け女性ナレーション |
| **男性ナレーター (深沉解说男声)** | `bb3bf6a073cb48c1a5b6c436053ce243` | ja | Male | narration | 重厚感のある低音と落ち着いた間を持つ日本語ナレーションボイス。ドキュメンタリーや朗読に |
| **女性アナウンサー (资深新闻女主播)** | `f1d92c18f84e47c6b5bc0cebb80ddaf5` | ja | Female | business | 正確無比な発音と品格のあるトーンを持つ日本語ベテランアナウンサーボイス |

##### Multilingual Voices (西语/法语/韩语/葡语/俄语精选音色)

| Voice Name | Voice ID | Lang | Gender | Category | Character / Timbre & Recommended Use |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Voz Femenina Suave (西语柔和女声)** | `bfed5c0810a347dbb62e8ccce7f59c48` | es | Female | narration | Voz femenina en español, suave y fluida con matices cálidos para narraciones y relatos |
| **Narrador Dinámico (西语解说男声)** | `35199d5438854f5d9157c500479ab684` | es | Male | narration | Locutor masculino en español dinámico y persuasivo para publicidad, documentales y YouTube |
| **Voix Féminine Douce (法语优雅女声)** | `5567200c7d8341738f0892bbacd3be3c` | fr | Female | casual | Voix féminine française posée, élégante et chaleureuse pour podcasts, narration et dialogue |
| **20대 여성 (韩语清亮女声)** | `4e118bfbb83e401c84699c09b5f08257` | ko | Female | casual | 자연스럽고 상큼한 20대 한국어 여성 목소리, 쇼츠와 일상 대화에 최적화 |
| **Locutor Comercial (葡语专业男声)** | `572760b7d9ec4a369ca387dad720a828` | pt | Male | business | Locução comercial em português com dicção clara, entonação firme e apelo publicitário |
| **Спокойный женский голос (俄语平静女声)** | `2a1036d645634680b3cc69aeeb60375b` | ru | Female | narration | Спокойный, мягкий и выразительный русский женский голос для аудиокниг и озвучки |

---

#### 5.1.2 MiniMax Voices (MiniMax 官方系统音色库)

Corresponding model: `minimax-speech-2.8-hd`. Source: [MiniMax Audio Voices](https://www.bahew.com/api/v1/audio/voices?provider=minimax_tts&model_id=minimax-speech-2.8-hd). MiniMax excels in emotional nuance, dramatic dialogue, radio broadcasts, and regional accents.

##### Classic Chinese Personas (经典青年与精品人设)

| Voice Name | Voice ID | Gender | Category | Timbre & Scenario |
| :--- | :--- | :--- | :--- | :--- |
| **青涩青年音色** | `male-qn-qingse` | Male | casual | MiniMax 官方系统音色：青涩青年音色，青年男声。 |
| **精英青年音色** | `male-qn-jingying` | Male | casual | MiniMax 官方系统音色：精英青年音色，青年男声。 |
| **霸道青年音色** | `male-qn-badao` | Male | drama | MiniMax 官方系统音色：霸道青年音色，青年男声。 |
| **青年大学生音色** | `male-qn-daxuesheng` | Male | casual | MiniMax 官方系统音色：青年大学生音色，青年男声。 |
| **少女音色** | `female-shaonv` | Female | casual | MiniMax 官方系统音色：少女音色，青年女声。 |
| **御姐音色** | `female-yujie` | Female | drama | MiniMax 官方系统音色：御姐音色，青年女声。 |
| **成熟女性音色** | `female-chengshu` | Female | casual | MiniMax 官方系统音色：成熟女性音色，成熟女声。 |
| **甜美女性音色** | `female-tianmei` | Female | casual | MiniMax 官方系统音色：甜美女性音色，青年女声。 |
| **青涩青年音色-beta** | `male-qn-qingse-jingpin` | Male | casual | MiniMax 官方系统音色：青涩青年音色-beta，青年男声。 |
| **精英青年音色-beta** | `male-qn-jingying-jingpin` | Male | casual | MiniMax 官方系统音色：精英青年音色-beta，青年男声。 |
| **霸道青年音色-beta** | `male-qn-badao-jingpin` | Male | drama | MiniMax 官方系统音色：霸道青年音色-beta，青年男声。 |
| **青年大学生音色-beta** | `male-qn-daxuesheng-jingpin` | Male | casual | MiniMax 官方系统音色：青年大学生音色-beta，青年男声。 |
| **少女音色-beta** | `female-shaonv-jingpin` | Female | casual | MiniMax 官方系统音色：少女音色-beta，青年女声。 |
| **御姐音色-beta** | `female-yujie-jingpin` | Female | drama | MiniMax 官方系统音色：御姐音色-beta，青年女声。 |
| **成熟女性音色-beta** | `female-chengshu-jingpin` | Female | casual | MiniMax 官方系统音色：成熟女性音色-beta，成熟女声。 |
| **甜美女性音色-beta** | `female-tianmei-jingpin` | Female | casual | MiniMax 官方系统音色：甜美女性音色-beta，青年女声。 |

##### Drama & Character Voices (短剧与角色定制)

| Voice Name | Voice ID | Gender | Category | Timbre & Scenario |
| :--- | :--- | :--- | :--- | :--- |
| **聪明男童** | `clever_boy` | Male | casual | MiniMax 官方系统音色：聪明男童，少年男声。 |
| **可爱男童** | `cute_boy` | Male | casual | MiniMax 官方系统音色：可爱男童，少年男声。 |
| **萌萌女童** | `lovely_girl` | Female | casual | MiniMax 官方系统音色：萌萌女童，少年女声。 |
| **卡通猪小琪** | `cartoon_pig` | Male | casual | MiniMax 官方系统音色：卡通猪小琪，青年男声。 |
| **病娇弟弟** | `bingjiao_didi` | Male | casual | MiniMax 官方系统音色：病娇弟弟，青年男声。 |
| **俊朗男友** | `junlang_nanyou` | Male | drama | MiniMax 官方系统音色：俊朗男友，青年男声。 |
| **纯真学弟** | `chunzhen_xuedi` | Male | casual | MiniMax 官方系统音色：纯真学弟，青年男声。 |
| **冷淡学长** | `lengdan_xiongzhang` | Male | casual | MiniMax 官方系统音色：冷淡学长，青年男声。 |
| **霸道少爷** | `badao_shaoye` | Male | drama | MiniMax 官方系统音色：霸道少爷，青年男声。 |
| **俏皮萌妹** | `qiaopi_mengmei` | Female | casual | MiniMax 官方系统音色：俏皮萌妹，青年女声。 |
| **妩媚御姐** | `wumei_yujie` | Female | drama | MiniMax 官方系统音色：妩媚御姐，青年女声。 |
| **嗲嗲学妹** | `diadia_xuemei` | Female | casual | MiniMax 官方系统音色：嗲嗲学妹，青年女声。 |
| **淡雅学姐** | `danya_xuejie` | Female | casual | MiniMax 官方系统音色：淡雅学姐，青年女声。 |
| **傲娇御姐** | `Chinese (Mandarin)_Mature_Woman` | Female | drama | 一位妩媚成熟的青年御姐声音，标准普 通话。 |
| **不羁青年** | `Chinese (Mandarin)_Unrestrained_Young_Man` | Male | casual | 一位潇洒不羁的青年男性声音，标准普通话。 |
| **嚣张小姐** | `Arrogant_Miss` | Female | drama | 一位嚣张自信的青年女性声音，标准普通话，展现出优越感。 |
| **机械战甲** | `Robot_Armor` | Male | drama | 一位电子化、机器人般的青年男性声音，适合科幻或未来主义内容的标准普通话。 |

##### Broadcast, News & Life Tones (新闻播音、电台与特色生活)

| Voice Name | Voice ID | Gender | Category | Timbre & Scenario |
| :--- | :--- | :--- | :--- | :--- |
| **沉稳高管** | `Chinese (Mandarin)_Reliable_Executive` | Male | business | 一位沉稳可靠的中年男性高 管声音，标准普通话，传递出值得信赖的感觉。 |
| **新闻女声** | `Chinese (Mandarin)_News_Anchor` | Female | news | 一位专业、播音腔的中年女性新闻主播，标准普通话。 |
| **港普空姐** | `Chinese (Mandarin)_HK_Flight_Attendant` | Female | casual | 一位礼貌的中年女性空乘员声音，带有港式普 通话口音，清晰而有礼。 |
| **搞笑大爷** | `Chinese (Mandarin)_Humorous_Elder` | Male | casual | 一位爽朗幽默的老年男性大爷声音，带有北方口音的中文，充满个性。 |
| **温润男声** | `Chinese (Mandarin)_Gentleman` | Male | casual | 一位温润磁性的青年男性声音，标准普通话。 |
| **温暖闺蜜** | `Chinese (Mandarin)_Warm_Bestie` | Female | casual | 一位温暖清脆的青年女性闺蜜声音，标准普通话，友好而清晰。 |
| **播报男声** | `Chinese (Mandarin)_Male_Announcer` | Male | news | 一位富有磁性的中年男性播报员声音，标准普通话，清晰而权威。 |
| **南方小哥** | `Chinese (Mandarin)_Southern_Young_Man` | Male | casual | 一位质朴的青年男性声音，带有南方口音的中文。 |
| **阅历姐姐** | `Chinese (Mandarin)_Wise_Women` | Female | casual | 一位富有阅历、声音抒情的中年姐姐声音，标准普通话。 |
| **花甲奶奶** | `Chinese (Mandarin)_Kind-hearted_Elder` | Female | casual | 一位慈祥和蔼的老年女性奶奶声音，标准普通话。 |
| **电台男 主播** | `Chinese (Mandarin)_Radio_Host` | Male | news | 一位富有诗意的青年男性电台主播声音，标准普通话，声音流畅引人入胜。 |
| **抒情男声** | `Chinese (Mandarin)_Lyrical_Voice` | Male | casual | 一位磁性抒情的青年男性声音，标准普通话，流畅而富有表现力。 |

##### Cantonese Voices (粤语主持与日常对白)

| Voice Name | Voice ID | Gender | Category | Timbre & Scenario |
| :--- | :--- | :--- | :--- | :--- |
| **专业女主持** | `Cantonese_ProfessionalHost（F)` | Female | news | 一位中性、专业的青年女性粤语主持人声音。 |
| **温柔女声** | `Cantonese_GentleLady` | Female | casual | 一位平静温柔的青年女性粤语声音。 |
| **专业男主持** | `Cantonese_ProfessionalHost（M)` | Male | news | 一位中性、专业的青年男性粤语主持人声音。 |
| **活泼男声** | `Cantonese_PlayfulMan` | Male | casual | 一位活泼深情的青年男性粤语声音。 |
| **可爱女孩** | `Cantonese_CuteGirl` | Female | casual | 一位柔和可爱的青年女性粤语声音。 |
| **善良女声** | `Cantonese_KindWoman` | Female | casual | 一位亲切善良的青年女性粤语声音。 |

##### English & International Featured Voices (英语与国际精选)

| Voice Name | Voice ID | Gender | Category | Timbre & Scenario |
| :--- | :--- | :--- | :--- | :--- |
| **Santa Claus** | `Santa_Claus` | Male | casual | MiniMax 官方系统音色：Santa Claus，老年男声。 |
| **Grinch** | `Grinch` | Male | casual | MiniMax 官方系统音色：Grinch，青年男声。 |
| **Charming Lady** | `Charming_Lady` | Female | casual | MiniMax 官方系统音色：Charming Lady，青年女声。 |
| **Sweet Girl** | `Sweet_Girl` | Female | casual | MiniMax 官方系统音色：Sweet Girl，青年女声。 |
| **Trustworthy Man** | `English_Trustworthy_Man` | Male | casual | 一位值得信赖、富有磁性的青年男性声音，带通用美式口音。 |
| **Graceful Lady** | `English_Graceful_Lady` | Female | casual | 一位优雅的中年女士，带有经典的英式口音，散发着成熟的魅力。 |
| **Aussie Bloke** | `English_Aussie_Bloke` | Male | casual | 一位阳光开朗的青年男 性，带有独特的澳大利亚口音。 |
| **Whispering girl** | `English_Whispering_girl` | Female | casual | 一位青年女性的轻柔耳语声，带通用美式口音，非常适合ASMR内容。 |
| **Gentle-voiced man** | `English_Gentle-voiced_man` | Male | casual | 一位声音温柔、富有磁性的青年男性，带通用美式口音。 |

### 5.2 Supported Languages

The TTS models detect the input language automatically, but setting the `language_code` explicitly is recommended for best results.

The `Unit` and `Rate` columns are empirically measured speech rates for **video off-screen narration** (documentary-style, steady pace). `Unit` is `chars` for unspaced scripts (CJK, Thai, Lao, Burmese) and `words` for the rest. `Rate` is the average number of units spoken per second of audio.

Under other delivery styles (excited announcer, ASMR whisper, news anchor, etc.), actual rate can deviate by approximately ±25%. **Voice choice has only a minor effect (~±5%) on rate; pick the voice that best matches the role and do not anchor on the calibration setup below.** See §4 for when to use these rates and when to ignore them.

*Calibration method (for reproducibility only, not a recommendation): TTS engine default, voice `Charon`, prompt prefix `Read this as a documentary narrator at a natural, steady conversational pace:`, N=2 samples per language.*

| Language | BCP-47 Code | Unit | Rate |
| :--- | :--- | :--- | :--- |
| Arabic (Egypt) | ar-EG | words | 1.3 |
| Bangla (Bangladesh) | bn-BD | words | 1.8 |
| Dutch (Netherlands) | nl-NL | words | 2.1 |
| English (India) | en-IN | words | 2.2 |
| English (United States) | en-US | words | 2.1 |
| French (France) | fr-FR | words | 2.2 |
| German (Germany) | de-DE | words | 2.1 |
| Hindi (India) | hi-IN | words | 2.1 |
| Indonesian (Indonesia) | id-ID | words | 1.6 |
| Italian (Italy) | it-IT | words | 1.9 |
| Japanese (Japan) | ja-JP | chars | 4.2 |
| Korean (South Korea) | ko-KR | chars | 3.8 |
| Marathi (India) | mr-IN | words | 1.6 |
| Polish (Poland) | pl-PL | words | 1.7 |
| Portuguese (Brazil) | pt-BR | words | 1.7 |
| Romanian (Romania) | ro-RO | words | 1.6 |
| Russian (Russia) | ru-RU | words | 1.5 |
| Spanish (Spain) | es-ES | words | 1.8 |
| Tamil (India) | ta-IN | words | 1.3 |
| Telugu (India) | te-IN | words | 1.3 |
| Thai (Thailand) | th-TH | chars | 7.2 |
| Turkish (Turkey) | tr-TR | words | 1.6 |
| Ukrainian (Ukraine) | uk-UA | words | 1.5 |
| Vietnamese (Vietnam) | vi-VN | words | 2.7 |
| Afrikaans (South Africa) | af-ZA | words | 2.0 |
| Albanian (Albania) | sq-AL | words | 2.1 |
| Amharic (Ethiopia) | am-ET | words | 1.2 |
| Arabic (World) | ar-001 | words | 1.3 |
| Armenian (Armenia) | hy-AM | words | 1.5 |
| Azerbaijani (Azerbaijan) | az-AZ | words | 1.6 |
| Basque (Spain) | eu-ES | words | 1.7 |
| Belarusian (Belarus) | be-BY | words | 1.5 |
| Bulgarian (Bulgaria) | bg-BG | words | 1.8 |
| Burmese (Myanmar) | my-MM | chars | 11.2 |
| Catalan (Spain) | ca-ES | words | 2.2 |
| Cebuano (Philippines) | ceb-PH | words | 1.9 |
| Chinese, Mandarin (China) | cmn-CN | chars | 2.8 |
| Chinese, Mandarin (Taiwan) | cmn-tw | chars | 2.7 |
| Croatian (Croatia) | hr-HR | words | 1.7 |
| Czech (Czech Republic) | cs-CZ | words | 1.8 |
| Danish (Denmark) | da-DK | words | 2.1 |
| English (Australia) | en-AU | words | 2.2 |
| English (United Kingdom) | en-GB | words | 2.1 |
| Estonian (Estonia) | et-EE | words | 1.6 |
| Filipino (Philippines) | fil-PH | words | 1.7 |
| Finnish (Finland) | fi-FI | words | 1.2 |
| French (Canada) | fr-CA | words | 2.2 |
| Galician (Spain) | gl-ES | words | 1.9 |
| Georgian (Georgia) | ka-GE | words | 1.4 |
| Greek (Greece) | el-GR | words | 1.6 |
| Gujarati (India) | gu-IN | words | 1.8 |
| Haitian Creole (Haiti) | ht-HT | words | 2.6 |
| Hebrew (Israel) | he-IL | words | 1.5 |
| Hungarian (Hungary) | hu-HU | words | 1.8 |
| Icelandic (Iceland) | is-IS | words | 1.4 |
| Javanese (Java) | jv-JV | words | 1.7 |
| Kannada (India) | kn-IN | words | 1.2 |
| Konkani (India) | kok-IN | words | 1.6 |
| Lao (Laos) | lo-LA | chars | 8.2 |
| Latin (Vatican City) | la-VA | words | 1.3 |
| Latvian (Latvia) | lv-LV | words | 1.4 |
| Lithuanian (Lithuania) | lt-LT | words | 1.4 |
| Luxembourgish (Luxembourg) | lb-LU | words | 2.0 |
| Macedonian (North Macedonia) | mk-MK | words | 1.7 |
| Maithili (India) | mai-IN | words | 2.1 |
| Malagasy (Madagascar) | mg-MG | words | 1.8 |
| Malay (Malaysia) | ms-MY | words | 1.6 |
| Malayalam (India) | ml-IN | words | 1.2 |
| Mongolian (Mongolia) | mn-MN | words | 1.6 |
| Nepali (Nepal) | ne-NP | words | 1.4 |
| Norwegian, Bokmål (Norway) | nb-NO | words | 1.7 |
| Norwegian, Nynorsk (Norway) | nn-NO | words | 1.6 |
| Odia (India) | or-IN | words | 1.5 |
| Pashto (Afghanistan) | ps-AF | words | 2.1 |
| Persian (Iran) | fa-IR | words | 1.5 |
| Portuguese (Portugal) | pt-PT | words | 1.6 |
| Punjabi (India) | pa-IN | words | 2.3 |
| Serbian (Serbia) | sr-RS | words | 1.7 |
| Sindhi (India) | sd-IN | words | 2.1 |
| Sinhala (Sri Lanka) | si-LK | words | 1.6 |
| Slovak (Slovakia) | sk-SK | words | 1.7 |
| Slovenian (Slovenia) | sl-SI | words | 1.6 |
| Spanish (Latin America) | es-419 | words | 1.7 |
| Spanish (Mexico) | es-MX | words | 1.8 |
| Swahili (Kenya) | sw-KE | words | 1.8 |
| Swedish (Sweden) | sv-SE | words | 1.8 |
| Urdu (Pakistan) | ur-PK | words | 2.2 |

