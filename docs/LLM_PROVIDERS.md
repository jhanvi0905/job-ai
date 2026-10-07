# LLM provider evaluation (resumes + JDs = personal data)

All facts read **2026-10-07** from the source pages listed as [S#] at the bottom. Anything not confirmed there is marked *unverified*. Prices are USD per 1M tokens, standard/on-demand tier, no batch discount.

## 1. Recommendation

| Workload | Primary | Why | Fallback (outage) |
|---|---|---|---|
| Triage (1.5k in / 350 out) | OpenAI `gpt-6-luna`, `reasoning_effort: none`, strict `json_schema` | $0.10/$0.50, supports Chat Completions + Structured Outputs [S1][S2]; cheaper than today's gpt-4o-mini ($0.15/$0.60) [S1] | Azure OpenAI `gpt-6-luna` Global Standard, resource in `canadaeast` [S9] |
| Deep match (2.5k / 700) | OpenAI `gpt-6-luna`, `reasoning_effort: low` | Same model, more thinking; reasoning tokens bill as output (~700 extra assumed) | Azure `gpt-6-luna` |
| Resume parse (3k / 1.5k) | OpenAI `gpt-6-luna`, `none` | Extraction, rare | Azure `gpt-6-luna` |
| Tailoring (3k / 1k) | Anthropic `claude-sonnet-5-5`, `inference_geo: "us"`, native Structured Outputs | Writing quality; $2/$10 (x1.1 for US-only) [S4]; Active until at least 2027-09-28 [S5] | OpenAI/Azure `gpt-6.1-sol` ($2/$10) [S1] |

Fallback rationale: Azure OpenAI hosts the same model family (gpt-6-luna and gpt-6.1-sol are listed for `canadaeast` Global Standard [S9]), speaks the OpenAI v1 API at `https://RESOURCE.openai.azure.com/openai/v1/` with the plain OpenAI client [S11], so prompts and schemas carry over unchanged. Data at rest, including the abuse-monitoring store, stays in the resource's geography (Canada); **processing on Global deployments can happen in any region** [S10].

**No Canada-only processing at a sane price today.** Azure Standard/Regional in `canadaeast` offers only gpt-4.1-mini and gpt-4o 2024-11-20 [S9]; both are Deprecated/Legacy and retire 2027-04-14 [S12]. Vertex AI Montréal (`northamerica-northeast1`) offers Gemini 3.5 Flash ($1.65/$9.90 non-global) [S15][S16]; Gemini 2.5 Flash is also listed there but retires **2026-10-20** [S17]. Bedrock `ca-central-1` reaches current Claude/OpenAI/Nova models only through Geo or Global cross-region profiles, not In-Region [S13]; the US geo profile can route Canadian requests to us-east-1/us-east-2/us-west-2 [S14]. OpenAI's Canada residency covers **storage only, not processing**; it needs sales approval and adds +10% on newer models [S3]. PIPEDA does not prohibit processing outside Canada. It requires contractual comparable protection plus clear notice [S27]. Québec (Law 25 s.17) requires a privacy impact assessment and a written agreement before data leaves Québec [S28]. So: process in the US, disclose it, and keep the Canada-only route as a later enterprise option (Vertex Montréal Gemini 3.5 Flash, about 7.6x the cost; see below).

**Dropped:** DeepSeek. Its policy says data is collected, processed and stored in the PRC and can be used for training (opt-out) [S23]. Do not send resumes there. AI/ML API (current) is a UAE company. Its privacy policy says nothing about API prompt retention, upstream sharing or a DPA [S24] (*unverified* beyond that), so it is unfit for a multi-tenant product handling PII.

### Estimated monthly LLM cost
Assumptions: per weekly-active user per week, after our existing per-user verdict cache (`evaluation.py` reuses a row while `(jd_hash, rules_sig)` match; tailor results are cached per resume/JD/bank/prompt/model), the billable calls are 40 triage, 5 deep matches, 0.2 parses and 1 tailor. Months are 4.33 weeks. +15% for schema-repair retries. Deep match adds 700 reasoning tokens. Claude token counts are x1.3 because Claude 4.7+ uses a new tokenizer producing ~30% more tokens [S4]. Tailoring uses US-only inference (x1.1). No credit taken for OpenAI cached input (10% of the input rate [S2]), which is upside.

| Scenario | per WAU / month | 100 WAU | 1,000 WAU | 10,000 WAU |
|---|---|---|---|---|
| **Recommended** (Luna + Sonnet 5.5 tailor) | $0.20 | **$20** | **$204** | **$2,035** |
| All-OpenAI (Luna + gpt-6.1-sol tailor) | $0.17 | $17 | $169 | $1,692 |
| Today's routing priced at OpenAI list for gpt-4o-mini | $0.11 | $11 | $113 | $1,131 |
| Canada-processing only (Vertex Montréal Gemini 3.5 Flash for everything) | $1.55 | $155 | $1,553 | $15,532 |

Tailoring is ~55% of the recommended bill. Triage on Luna costs $0.013/user/week.

## 2. Comparison (models we would actually use)

| Provider | Cheap / mid model: in/out $ | Structured output | Retention / training | ZDR | DPA | Residency | OpenAI-compatible? | Notes |
|---|---|---|---|---|---|---|---|---|
| OpenAI direct | gpt-6-luna 0.10/0.50; gpt-6.1-sol 2/10; gpt-5.4-nano 0.20/1.25 [S1] | json_schema strict [S2] | No training by default; abuse logs up to 30 d [S3] | Approval-only programme; chat/completions eligible [S3] | Yes, DPA form [S25] | US default; CA/EU/UK etc. storage. Canada = storage only, no processing [S3] | Yes, drop-in | Luna Build tier 2M TPM / 5K RPM [S2] |
| Azure OpenAI | Same models; Azure prices *unverified* | json_schema [S11] | Not used to train; not shared with OpenAI [S10] | "Modified abuse monitoring" for managed customers on application [S10] | Microsoft DPA [S10] | Global: any region; DataZone: US or EU; Standard: in-region. canadaeast Standard = gpt-4.1-mini, gpt-4o only [S9][S10] | Yes (v1 API) [S11] | Auto-upgrade on retirement [S12] |
| Anthropic API | haiku-4-5 1/5 (retire ≥2026-10-15); sonnet-5-5 2/10 [S4][S5] | Native only. OpenAI layer ignores `response_format`/`strict` [S6] | Deleted within 30 d; flagged up to 2 y [S7] | By agreement [S7] | In Commercial Terms [S26] | `inference_geo` us/global only; storage US only [S8] | Compat layer is "not production-ready"; needs adapter [S6] | temperature≠default returns 400 on 4.7+ [S5] |
| Bedrock | Claude at list; Nova 2 Lite / gpt-6-luna prices *unverified* (page is JS-rendered) | Model-dependent | AWS-controlled `data_retention_mode`; `none` = ZDR for most models [S19] | Yes (`none`), per region [S19] | AWS DPA (*unverified* link) | ca-central-1: Claude 4.5–5.5, GPT-5.6/6, Nova 2 Lite via Geo/Global only [S13] | Yes: `bedrock-runtime.{region}.amazonaws.com/openai/v1` [S20] | Regional/geo endpoints +10% for Claude [S4] |
| Gemini API (paid) / Vertex | 3.1-flash-lite 0.25/1.50; 3.5-flash 1.50/9.00 [S15] | json_schema via OpenAI layer (beta) [S18] | Free tier is used to improve products; paid is not [S15][S21] | Vertex: no training; disable 24h in-memory cache; request abuse-logging exception [S22] | Google CDPA [S22] | Vertex Montréal: 3.5 Flash, 2.5 Flash, 2.5 Pro [S16]; 3.5-flash-lite only us/eu multi-region [S17] | Gemini API: yes (`…/v1beta/openai/`) [S18]; Vertex: *unverified* | Only paid services may be offered to EEA/UK/CH users [S21] |
| Mistral | small-4 0.15/0.60; medium-3.5 1.50/7.50 [S29] | json_schema *unverified* | 30-day abuse retention [S30] | Pay-as-you-go, stateless, on request [S31] | Yes [S30] | EU by default; US endpoint optional [S30] | Yes (`/v1/chat/completions`) | Good EU option later |
| Groq | gpt-oss-20b 0.075/0.30; gpt-oss-120b 0.15/0.60 [S32] | strict on gpt-oss + qwen3.8-27b [S33] | Not retained by default; up to 30 d for reliability/abuse [S34] | Self-serve toggle [S34] | Yes [S35] | US (GCP) [S34] | Yes | Fast; gpt-oss quality for tailoring *unverified* |
| Cerebras | gpt-oss-120b, qwen-3.8-27b listed [S36]; prices *unverified* | *unverified* | *unverified* | *unverified* | *unverified* | *unverified* | Yes | Free tier context 65k |
| Together | gpt-oss-120b 0.15/0.60 [S37] | *unverified* | History stored unless deleted; no training without opt-in [S38] | Account toggle [S38] | Not mentioned [S38] | Unspecified [S38] | Yes | |
| Fireworks | gpt-oss-120b 0.15/0.60 [S39] | *unverified* | No prompt logging for open models without opt-in [S40] | Default [S40] | *unverified* | *unverified* | Yes | |
| OpenRouter | Provider list price + 5.5% credit fee (8% Business) [S41] | Passthrough | OpenRouter does not keep prompts unless you opt in [S42] | Account-wide or per-request `provider.zdr` [S42] | In ToS; signed copy on request [S43] | EU/US in-region routing on Business+ [S44] | Yes | ZDR eligibility of specific OpenAI/Anthropic endpoints *unverified* |
| DeepSeek | deepseek-flash 0.15/0.60 off-peak, 0.30/1.20 peak [S45] | JSON mode [S45] | Stored in PRC; training with opt-out [S23] | No | Not offered [S23] | China | Yes | **Do not use** |
| AI/ML API (current) | gpt-4o-mini via router (price *unverified*) | Passthrough | Not stated [S24] | Not stated | Not stated | UAE company | Yes | Replace |

## 3. Privacy checklist
1. **Privacy policy:** name the purpose (matching, tailoring). State that resumes and JDs are processed by OpenAI (US) and Anthropic (US), plus Microsoft Azure as fallback, and "may be processed in the United States and accessible to its authorities" [S27]. Say provider data is not used to train models. Give retention: provider abuse logs up to 30 d unless ZDR [S3][S7].
2. **Subprocessor list:** OpenAI, Anthropic, Microsoft (Azure OpenAI), and any host or DB vendors. Remove AI/ML API and never list DeepSeek. Version the list and notify users of changes.
3. **Contracts:** sign the OpenAI DPA [S25] and the Anthropic DPA (in Commercial Terms) [S26]. Azure is covered by the Microsoft DPA [S10]. File a Law 25 s.17 PIA for Québec users [S28]. Before EU/UK launch, confirm SCCs/UK addendum in each DPA (*unverified* per provider).
4. **Retention settings to request:** OpenAI ZDR or Modified Abuse Monitoring (application) [S3], and send `store: false`. Anthropic ZDR agreement [S7]. Azure modified abuse monitoring (check that `ContentLogging=false`) [S10]. If Bedrock is used, set `data_retention_mode: none` per region [S19].
5. **Regions to pin:** Anthropic workspace `allowed_inference_geos: ["us"]`, `default_inference_geo: "us"` [S8]. Azure resource in `canadaeast` (data at rest in Canada) [S10]. EU users later: Azure DataZone EU or OpenAI EU project, plus Mistral EU [S10][S3][S30].
6. **Minimise:** strip contact details (email, phone, address) from resumes before any LLM call. Do not log prompt bodies in our ledger. Keep `user_id` out of provider `user`/metadata fields.

## 4. Config and gateway changes
Today `LLMProvider` reads one `provider` block (`base_url`, `api_key_env`), sends `Authorization: Bearer` with `response_format: json_object` to `/chat/completions`, and takes cost from AI/ML API's `meta.usage.usd_spent`. Otherwise it falls back to the optional `pricing:` map, and **with no map it records $0**, which silently disables the USD budgets (`src/jobai/engine/ai/provider.py` `_cost`). Proposed `config/models.yaml`:

```yaml
providers:
  openai:    {base_url: "https://api.openai.com/v1", api_key_env: "OPENAI_API_KEY", api: openai}
  azure:     {base_url: "https://<resource>.openai.azure.com/openai/v1", api_key_env: "AZURE_OPENAI_API_KEY", api: openai}  # model = deployment name
  anthropic: {base_url: "https://api.anthropic.com/v1", api_key_env: "ANTHROPIC_API_KEY", api: anthropic}
routing:
  classify_job:  {provider: openai, fallback: azure, model: "gpt-6-luna", reasoning_effort: none, max_output_tokens: 350}
  analyse_match: {provider: openai, fallback: azure, model: "gpt-6-luna", reasoning_effort: low,  max_output_tokens: 1500}
  classify_email:{provider: openai, fallback: azure, model: "gpt-6-luna", reasoning_effort: none, max_output_tokens: 80}
  parse_resume:  {provider: openai, fallback: azure, model: "gpt-6-luna", reasoning_effort: none, max_output_tokens: 3000}
  tailor_resume: {provider: anthropic, fallback: openai, model: "claude-sonnet-5-5", fallback_model: "gpt-6.1-sol", inference_geo: us, max_output_tokens: 1500}  # drop temperature
pricing:  # required: OpenAI/Azure/Anthropic do not return usd_spent
  gpt-6-luna: {in_per_mtok: 0.10, out_per_mtok: 0.50}
  gpt-6.1-sol: {in_per_mtok: 2.00, out_per_mtok: 10.00}
  claude-sonnet-5-5: {in_per_mtok: 2.20, out_per_mtok: 11.00}  # x1.1 US-only
```

Code changes needed (small, all in `src/jobai/engine/ai/provider.py`):
- **Per-route provider and fallback.** Resolve provider per call. On `circuit_open`, 5xx or timeout after retries, retry once on `fallback`. Today there is one provider per instance.
- **Pass-through params.** Send `reasoning_effort` (Luna/Sol default to `medium` [S2], which would burn the 350-token budget on reasoning). Send `response_format: {type: json_schema, strict: true}` with the route's schema. Keep `json_object` plus the repair retry as the fallback. Reasoning models may need `max_completion_tokens` instead of `max_tokens` [S11] (*verify* via `scripts/dev/verify_models.py`).
- **Anthropic adapter** (about 80 lines). Do not use the OpenAI compat layer: it ignores `response_format`/`strict` and `inference_geo` and is not production-grade [S6]. The adapter uses `POST /v1/messages` with `x-api-key` + `anthropic-version`, a top-level `system`, structured-output schema, and `inference_geo`. It maps `usage.input_tokens/output_tokens` and treats `stop_reason: max_tokens` as `truncated`. Omit `temperature`: non-default values return 400 on Claude 4.7+ [S5].
- **Model-retirement guard.** Haiku 4.5 (≥2026-10-15), Gemini 2.5 Flash (2026-10-20) and Azure gpt-4.1-nano (2026-10-14) all retire within weeks [S5][S17][S12]. Do not route to them.

## Sources (all read 2026-10-07)
S1 https://developers.openai.com/api/docs/pricing · S2 https://developers.openai.com/api/docs/models/gpt-6-luna (and /gpt-6-sol) · S3 https://developers.openai.com/api/docs/guides/your-data · S4 https://platform.claude.com/docs/en/about-claude/pricing · S5 https://platform.claude.com/docs/en/about-claude/model-deprecations · S6 https://platform.claude.com/docs/en/api/openai-sdk · S7 https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data · S8 https://platform.claude.com/docs/en/manage-claude/data-residency · S9 https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability · S10 https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy · S11 https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle · S12 https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirement-schedule · S13 https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html · S14 https://aws.amazon.com/blogs/machine-learning/accelerate-generative-ai-innovation-in-canada-with-amazon-bedrock-cross-region-inference/ · S15 https://ai.google.dev/gemini-api/docs/pricing · S16 https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations · S17 https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash (and /3-5-flash, /3-5-flash-lite, /3-1-flash-lite) · S18 https://ai.google.dev/gemini-api/docs/openai · S19 https://docs.aws.amazon.com/bedrock/latest/userguide/data-retention.html · S20 https://docs.aws.amazon.com/bedrock/latest/userguide/inference-chat-completions.html · S21 https://ai.google.dev/gemini-api/terms · S22 https://docs.cloud.google.com/vertex-ai/generative-ai/docs/vertex-ai-zero-data-retention · S23 https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html · S24 https://aimlapi.com/privacy-policy · S25 https://openai.com/policies/feb-2024-data-processing-addendum/ · S26 https://privacy.claude.com/en/articles/7996862-how-do-i-view-and-sign-your-data-processing-addendum-dpa · S27 https://www.priv.gc.ca/en/privacy-topics/airports-and-borders/gl_dab_090127/ · S28 https://www.legisquebec.gouv.qc.ca/en/document/cs/p-39.1 · S29 https://docs.mistral.ai/inference/pricing · S30 https://legal.mistral.ai/terms/data-processing-addendum/ and https://help.mistral.ai/en/articles/347629-where-do-you-store-my-data-or-my-organization-s-data · S31 https://help.mistral.ai/en/articles/347612-can-i-activate-zero-data-retention-zdr · S32 https://console.groq.com/docs/models · S33 https://console.groq.com/docs/structured-outputs · S34 https://console.groq.com/docs/your-data · S35 https://console.groq.com/docs/legal/customer-data-processing-addendum · S36 https://inference-docs.cerebras.ai/models/overview · S37 https://www.together.ai/pricing · S38 https://www.together.ai/privacy · S39 https://docs.fireworks.ai/serverless/pricing · S40 https://docs.fireworks.ai/guides/security_compliance/data_handling · S41 https://openrouter.ai/pricing · S42 https://openrouter.ai/docs/guides/features/zdr · S43 https://openrouter.ai/terms · S44 https://openrouter.ai/docs/guides/privacy/provider-logging · S45 https://api-docs.deepseek.com/quick_start/pricing
