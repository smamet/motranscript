# MoTranscript — Architecture Plan & Key Concepts

**Goal**: Build a speech-to-text system that transcribes conversations between Mauritians — in Mauritian Creole (Kreol Morisien), French, and English, with frequent code-switching — with a perfect handling of the Mauritian accent, correct official Creole orthography, and speaker attribution.

This document is the master plan. It is written so that coding agents (e.g. in Cursor) have all the context needed to derive detailed implementation plans from it.

---

## 1. System overview

Two applications around a single data cycle, plus two shared components (model registry, Lortograf normalizer).

```
[Part 1 — Annotation app (FastAPI backend + wavesurfer.js web editor)]
  YouTube URL / video file / audio file
    → yt-dlp / upload → ffmpeg (WAV 16 kHz mono)
    → speaker diarization (pyannote 3.x) + ASR (faster-whisper, current model) + alignment (WhisperX)
    → correction editor (interactive waveform timeline, per-speaker segments)
    → export of validated dataset (JSONL + segmented WAV files)

[Part 2 — Training & deployment (ephemeral cloud GPU)]
  validated dataset
    → rented GPU (RunPod / Lambda, A100): LoRA fine-tuning of Whisper large-v3 (HF transformers + PEFT)
    → evaluation on a FROZEN test set (WER/CER per language + code-switching set)
    → if better than current version: merge LoRA → convert to CTranslate2
    → push to private Hugging Face repo (creole-asr-vN)
    → annotation app downloads the new version → next pre-transcriptions get better
```

The system is a flywheel: the model pre-transcribes, humans correct, corrections retrain the model, the improved model makes the next corrections cheaper.

## 2. Part 1 — Annotation app

**Stack**: Python FastAPI backend (pipeline: yt-dlp, ffmpeg, pyannote, faster-whisper, WhisperX) + web frontend built on **wavesurfer.js** (interactive waveform, colored regions per speaker, click-to-seek, transcript panel synchronized with audio — reference UX: BBC's react-transcript-editor). Gradio was considered and rejected: its audio component cannot render a multi-speaker timeline.

**Ingestion**. Accept a YouTube URL (yt-dlp) or an uploaded video/audio file. ffmpeg extracts the audio track as WAV 16 kHz mono. Persist metadata: source, date, duration, license/rights (free text).

**Automatic pre-processing**.
- Diarization: pyannote.audio 3.x (requires a Hugging Face token).
- ASR: faster-whisper (CTranslate2 backend) using the **current model** from the registry — vanilla Whisper large-v3 at the start, then each fine-tuned version.
- Word-level alignment: WhisperX. Merge ASR output with diarization → 5–30 s segments, each attributed to a speaker.

**Correction editor (the main screen)**. Wavesurfer timeline with colored regions per speaker; clicking a region plays that segment; a synchronized transcript panel shows, per segment: speaker label (renamable, e.g. SPEAKER_00 → "Jean"), detected language (kreol/fr/en/mix, editable), editable text, a "Normalize (Lortograf)" button, and a status field `raw → corrected → validated`. Keyboard shortcuts for play/validate — annotation speed lives here.

**Storage**. SQLite for the single-user local v1; PostgreSQL for the server deployment (design the data model for Postgres from day one so migration is trivial). One WAV file per segment.

**Export**. Only `validated` segments → JSONL in Hugging Face datasets format: `{audio_path, text, lang, speaker, duration, source_id, model_version_used, annotator}`.

## 3. Multi-annotator server deployment (v2)

The app is a standard web app, so it deploys as-is to a VPS (Docker + HTTPS). Multi-user specifics:
- **Decouple inference from annotation.** The correction UI is lightweight; the heavy part is pre-processing (pyannote + large-v3). A CPU VPS is too slow for it → use a job queue: the server registers ingestion jobs, a worker pulls them — the Mac M2 as a worker initially (processes overnight, pushes results), or an on-demand cloud GPU at scale. Annotators never wait for inference; they only correct what is already pre-transcribed.
- **Accounts and roles**: annotator / reviewer; file- or segment-level locking to prevent collisions.
- **Multi-annotator quality**: double-annotate ~10% of segments to measure inter-annotator agreement; the transcription guide (verbatim, code-switching kept as spoken, Lortograf orthography) becomes the onboarding document.
- **Backups**: the database + segmented WAVs are the project's capital — daily off-server backup.
- Trajectory: v1 single-user local (SQLite) → v2 same code on VPS with Postgres + auth + job queue.

## 4. Part 2 — Training & deployment

**Frozen test set (build this first).** 30–60 minutes of representative audio (all 3 languages + code-switching, several speakers), corrected with maximum care, excluded from training forever. It is the benchmark for every model version.

**Training.** A standalone script run on an hourly-rented GPU (RunPod/Lambda/Vast, A100 ≈ $1.5–3/h; a full cycle ≈ $5–15):
- Base model: Whisper large-v3, fine-tuned with **LoRA** (PEFT) — preserves French/English quality, cheap to train.
- Starting hyperparameters: LoRA r=32 / alpha=64 on attention layers, effective batch ≈ 32, 3–5 epochs on a small corpus, SpecAugment.
- The Mac (M2 Pro/Max, 64 GB) is used to debug the training pipeline on a small model (turbo/medium) before paying for a GPU; never for the final run (PyTorch MPS is too slow/unstable for large-v3 training: 15–30 h vs 2–4 h on an A100).

**Quality gate.** Version vN+1 is published only if WER and CER improve on the frozen test set **per language**, not just on average. During bootstrap, also track a "phonetic CER" that treats phonetically-equivalent spellings as equal.

**Publication.** Merge LoRA weights → convert to CTranslate2 → push to a versioned private HF repo (`creole-asr-v1`, `v2`, …) with metrics in the README. The annotation app offers "Update model" when a newer version exists.

## 5. Shared component — Lortograf normalizer

A lexicon extracted from the Diksioner Morisien (reference dictionary by Arnaud Carpooran) + texts already in standard orthography; phonetic-key matching (Kreol grapheme→phoneme rules) maps any spontaneous spelling to the official form; an LLM pass constrained by the Lortograf rules (forbidden to change words, only spelling) handles out-of-lexicon cases. Used by the editor's "Normalize" button and as a QA check at export. Long-term option: a small seq2seq (ByT5) trained on synthetic corruptions of standard text.

## 6. Machine roles

| Task | Where | Why |
|---|---|---|
| Annotation editor (web) | Mac in v1, VPS in v2 | Lightweight UI, deploys as-is |
| Inference (diarization, ASR) | Mac M2 64 GB (worker) or on-demand GPU | Faster than real-time locally, zero cost; CPU VPS too slow |
| LoRA training of large-v3 | Ephemeral cloud GPU | 2–4 h on A100 vs 15–30 h on MPS; $5–15/iteration |
| Training-script debugging | Mac (small model) | Validate the pipeline before paying |
| Model hosting | Private HF repo | Versioning + simple download |

## 7. Build order

1. Interactive mockup of the editor (wavesurfer.js, fake data) → UX validation.
2. FastAPI backend: ingestion (yt-dlp/upload) → WAV 16 kHz → vanilla faster-whisper → segments.
3. Add pyannote diarization + speaker merge.
4. Full correction editor (statuses, shortcuts, SQLite, JSONL export).
5. Lortograf normalizer v1 (lexicon + phonetic key + LLM).
6. Frozen test set (30–60 min).
7. Cloud training script + quality gate + HF publication.
8. v2 server: Postgres + auth + job queue → open to other annotators.
9. Loop: iterate 4→7.

## 8. Suggested repository layout

```
creole-ai/
  apps/
    annotator/          # FastAPI app
      api/              # routes: sources, segments, speakers, export, model registry
      pipeline/         # yt-dlp, ffmpeg, pyannote, faster-whisper, whisperx, merge logic
      web/              # static frontend: wavesurfer.js editor
      db/               # SQLAlchemy models (Postgres-compatible), migrations
      worker/           # job queue consumer (ingestion/inference jobs)
  training/
    prepare_dataset.py  # JSONL + WAVs → HF dataset, train/dev split (test set excluded)
    train_lora.py       # transformers + PEFT, SpecAugment, checkpointing
    evaluate.py         # WER/CER per language + phonetic CER, quality gate
    publish.py          # merge LoRA, CTranslate2 conversion, HF push
  normalizer/
    lexicon/            # extracted Diksioner word list + build scripts
    phonetic.py         # grapheme→phoneme rules, phonetic-key matching
    llm_pass.py         # constrained LLM normalization
  docs/
    transcription-guide.md   # verbatim rules, code-switching, Lortograf
  data/                 # gitignored: audio, segments, sqlite db
```

---

## Appendix — Key concepts explained

**ASR (Automatic Speech Recognition)**: a model that maps audio to text. Modern ASR models (like Whisper) are sequence-to-sequence transformers trained on (audio, transcript) pairs. Crucial consequence: *the model learns spelling and grammar exclusively from the target transcripts*. There is no separate "grammar module" — the orthographic quality of the training transcripts IS the grammar training.

**Code-switching**: alternating languages within one conversation or sentence ("mo ti pe attend le bus, but it never came"). Mauritian speech is heavily code-switched. Rule: transcripts must keep each word in the language it was spoken — never translate. A dedicated code-switching test set is required because it is the hardest and most representative case.

**Speaker diarization vs. speaker identification**: diarization answers "who speaks when" — it splits audio into speaker-homogeneous turns and assigns anonymous labels (SPEAKER_00, SPEAKER_01). Identification answers "who is this" — matching a voice to a known person via speaker embeddings (e.g. ECAPA-TDNN) after enrollment. Part 1 needs diarization; identification is optional later.

**Forced alignment**: computing precise word-level timestamps by aligning the transcript to the audio (WhisperX does this on top of Whisper). Needed to cut clean 5–30 s training segments and to sync the editor's transcript with the waveform.

**Pseudo-labeling loop (the flywheel)**: instead of transcribing from scratch, the current model produces draft transcripts ("pseudo-labels") and humans only correct them. Correcting is 3–5× faster than transcribing. Each retraining improves the drafts, which lowers the cost of the next batch. This is the standard strategy for low-resource languages, where Kreol Morisien sits: almost no public audio corpus exists (existing datasets like KreolMorisienMT are text-only).

**Verbatim transcription**: the target text must be exactly what was said, including hesitations and false starts (per the transcription guide's conventions) — not a cleaned-up or translated version. ASR trained on paraphrases learns to paraphrase.

**Lortograf Kreol Morisien**: the official orthography of Mauritian Creole (2011, Akademi Kreol Morisien). It is **phonemic**: one sound ↔ one spelling, no silent letters. This makes automatic normalization tractable: any phonetically-correct spontaneous spelling can be mapped to the official form by phonetic-key lookup against a reference lexicon (Diksioner Morisien). Annotators therefore only need to be *phonetically* accurate; orthography is enforced by tooling ("correct content by humans, correct spelling by machines").

**WER / CER**: Word Error Rate and Character Error Rate — the standard ASR metrics (edit distance between hypothesis and reference, divided by reference length; lower is better). CER is more robust while Kreol orthography in the corpus is still stabilizing. "Phonetic CER" additionally treats phonetically-equivalent spellings as equal, to avoid penalizing pure spelling variance during bootstrap.

**Frozen test set & quality gate**: a held-out evaluation set created once, never trained on, and never modified. Every model version is measured against it; a new version is deployed only if it beats the previous one per language. Without this, you cannot know whether an iteration actually helped (and training on test data silently inflates scores).

**LoRA / PEFT**: Low-Rank Adaptation — instead of updating all 1.55B parameters of Whisper large-v3, small adapter matrices are trained (parameter-efficient fine-tuning). Benefits: fits on one GPU, cheap, and mitigates **catastrophic forgetting** — the tendency of full fine-tuning on Kreol data to degrade the model's existing French/English ability, which we must preserve.

**SpecAugment & data augmentation**: randomly masking parts of the audio spectrogram during training (SpecAugment), plus adding noise, speed perturbation, and room reverberation to artificially diversify a small corpus and improve robustness.

**faster-whisper / CTranslate2**: an optimized inference engine for Whisper (quantized, much faster than the reference implementation, runs well on Apple Silicon and CPU). Fine-tuned checkpoints must be converted to CTranslate2 format before the annotation app can use them — hence the convert step in the publication pipeline.

**Inter-annotator agreement**: when several people annotate, a sample (~10%) is annotated twice independently; the agreement rate measures whether the transcription guide is applied consistently. Low agreement = inconsistent corpus = noisy training signal.

**Model registry**: the versioned store of fine-tuned models (private Hugging Face repos `creole-asr-vN` with metrics). The annotation app always knows which version it used for each pre-transcription (`model_version_used` in the export), which allows measuring progress on real workloads.

**Volume targets (rules of thumb)**: ~10 h of corrected audio → first useful LoRA; 30–50 h → good model; 100 h+ → excellent. Diversity matters as much as volume: aim for 30–50+ different speakers, varied mics, registers, and noise conditions; ~60–70% of the corpus in Kreol/code-switching (French and English are already strong in the base model). Budget 4–8 h of human correction per hour of Kreol audio in the first iteration, dropping as the model improves.

**Rights**: YouTube content is copyrighted. Fine for private experimentation; a commercial product requires permission from creators or self-recorded data. Not legal advice — settle this before investing hundreds of correction hours.