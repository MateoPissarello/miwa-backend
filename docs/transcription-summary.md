# Transcription summary contract

The transcription pipeline produces two artefacts for every processed recording:

1. A **raw transcript JSON** stored under the prefix configured in `TRANSCRIPTS_PREFIX`
   (e.g. `transcripts/raw/<job-name>/<job-name>.json`). This is the direct output
   from Amazon Transcribe and contains the full transcript payload.
2. A **structured summary JSON** stored under `SUMMARIES_PREFIX`
   (e.g. `summaries/<job-name>.json`). The file uses the following schema:

```json
{
  "summary": "Natural language overview of the conversation.",
  "highlights": ["List of key highlights"],
  "action_items": ["Action items extracted from the transcript"],
  "sentiment": "Optional high level sentiment indicator"
}
```

The prompt template defined by `SUMMARY_PROMPT_TEMPLATE` MUST contain the `{transcript}`
placeholder so the Lambda can inject the transcript text. A reference template:

```
Genera un resumen en formato JSON con las claves summary, highlights,
action_items y sentiment para la siguiente transcripción:
{transcript}
```

Any additional keys returned by the selected LLM will be stored alongside the
required ones so consumers can extend the summary contract without code changes.

