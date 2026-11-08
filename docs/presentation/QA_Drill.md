# Q&A drill

One question per block. Read the question aloud, answer in 20 to 30 seconds, then check yourself against the model answer. Then try the follow-up.

Tags: AI engineer, Product designer, Petroleum engineer. A line starting with **Honest gap** means the true answer is "we have not done that yet".

## Q1. How does the system find the right report for a question?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> Code does it, not the model. The router reads the wells and dates in the question, in many spellings, and picks the report dated exactly that day. It filters by well first, because two wells can share a date. If no well or date is named, it uses the whole archive. If the well or date does not exist, it abstains with no model call.

**If they push:** What if the date is wrong by a day? The router tries D plus one only as a recorded fallback, and the context says so.

---

## Q2. What exactly does the model see?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> A handful of evidence lines. Each line is one record with its ID, type, fields, report date and time stamp. A single-report question is about 180 to 1,800 tokens. Multi-report contexts are capped near 12,000 tokens. The model never sees the PDF or searches the archive.

**If they push:** Who decides which lines? The context builder, from the question's topic words and a recall step that forces in records matching the question's distinctive words.

---

## Q3. How do you stop the model inventing citations?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> Three layers. The model may only cite IDs it was shown. The verifier rejects any other ID. And the evidence column is built by code from the store, so an unknown ID is dropped, never printed. In our benchmark of 405 calls there were zero invented IDs.

**If they push:** Could it cite a real ID that does not support the answer? Yes. That is what the number, unit and date checks are for.

---

## Q4. What does the verifier actually check?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> Thirteen things, all in code. The reply is valid JSON, the IDs were shown, an answer cites something, every number, unit, date and time appears in a cited record, no 'nothing found' claim for a well that has a match, every part of a multi-part question is answered, and an abstention is not contradicted by a matching line.

**If they push:** Does it check meaning? No. It checks that facts are supported. A right number from the wrong field can still pass.

---

## Q5. Why run the small model twice?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> The second run is a cheap disagreement detector. If the two runs differ on status or key numbers, we call Sonnet once to arbitrate. The second run never replaces the first answer by itself. On the 32 questions ten were arbitrated. It also keeps the escalation honest: Sonnet is only called when the two runs actually disagree.

**If they push:** Does it double the cost? The Haiku calls total 8 cents for all 32 questions. The cost is in Sonnet, not in the repeat.

---

## Q6. When does the bigger model get called, and what does it cost?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> Only when the code objects: the verifier fails, the model abstains although a matching line exists, or two runs disagree. For all 32 questions that was 26 Sonnet calls, 20 percent of calls but 87 percent of the 65 cents total. We do not escalate a plain 'no such field' abstention.

**If they push:** Could you drop Sonnet? Probably for most questions, but multi-report ones like T2-017 needed it to fix a number the verifier rejected.

---

## Q7. How do you handle the one-day offset in the reports?

**Best presenter:** Petroleum engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> A report dated D covers the day before D up to D. A sample stamped 9 pm on the 25th is in the report dated the 26th. Every record carries its window, and when a question names a clock time and a date, a note in the context says the earlier time stamp belongs to that report. The verifier accepts dates found in the cited record's window.

**If they push:** Why not just shift the dates? Because the question uses report dates, and the record keeps its true time stamp. We cite both.

---

## Q8. What do you do when the XML and the PDF disagree?

**Best presenter:** Petroleum engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> The XML wins. For example the PDF prints Y for tight well and HPHT in all 32 reports, while the XML says 0. We keep a derived note record for each disagreement and show it only when the question mentions that field. The locator never assigns a PDF page to those fields.

**If they push:** How many disagreements did you find? 64 flag fields, 11 days-behind values and one bit end depth, 2574 in the PDF against 2577 in the XML.

---

## Q9. How do you answer counts and maximums across the archive?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> Code computes them. For questions that ask for a count, an extreme or a comparison, the context builder finds fields whose names match the question, then adds an aggregate line with count, minimum, maximum and the source records. The model reads the result and the verifier checks the numbers against it.

**If they push:** Why not let the model count? On our 40 unseen questions the comparison and archive-wide ones scored 1 of 9 before aggregates and 9 of 9 after.

---

## Q10. What is the second pass?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> A single retry for multi-report or archive-wide questions when the first pass abstains, is partial, or trips the abstain flag. It gets an enriched context: the aggregates, a catalogue of field names that exist, and full records of the named wells. In the final 40-question run it never fired. In a test with aggregates switched off it fired on 5 of 8 and rescued all 5.

**If they push:** Is that test in the repo? Not yet committed. I would call it a session test, not a result to quote as a score.

**Honest gap.** Best way to say it: We have only tested the second pass in a one-off run with aggregates switched off. It rescued 5 of 5 cases where it fired. We have not added that as a committed test or scored it on a blind set.

---

## Q11. How can a reviewer rerun this with no API key?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> Every model answer is cached with a key made from the prompt, context, question and settings. The cache file is committed. With no key, the notebook replays the cache, takes about 10 seconds, and writes a byte-identical predictions file. A question that is not cached gets a NOT EVALUATED row, never a guess.

**If they push:** What if the cache is stale? A changed question changes the key, so it misses instead of returning an old answer.

---

## Q12. What does the evidence column contain?

**Best presenter:** Product designer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> A PDF file, page and section, then the XML file and record ID. For example the PDF page 1 Drilling Fluid and the XML ID F1C-20140326-FLUID-01. If the PDF never prints the value, we cite the XML only and say so. For an abstention it names the files searched.

**If they push:** Can a reviewer verify it in under a minute? Yes: open the page, find the table, open the XML at the same ID. The dashboard shows the page with the evidence highlighted.

---

## Q13. How does the dashboard show the evidence on the PDF page?

**Best presenter:** Product designer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> The locator finds where each record's text sits on its page and stores highlight rectangles. The API serves the page image with those boxes drawn on. Records the PDF does not print have no page, and the interface says so instead of showing a wrong one.

**If they push:** How accurate is the location? 99.2 percent of table and narrative records are located exactly. 78.8 percent of all records, because the rest are not printed.

---

## Q14. Does the API change the pipeline?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> No. The trace builder watches the pipeline from outside with pass-through wrappers. Tests prove predictions and caches are byte-identical after live asks, and that the contexts equal the original builder's. The API only reads, records and serves. The same trace powers the dashboard replay, so what you see on screen is what the pipeline did.

**If they push:** How do you know? A test regenerates predictions through the traced path and compares them to the committed file.

---

## Q15. How does abstention work technically?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> If the question names a topic the archive has no field for, such as cost or weather, the context holds an ABSENT record that says what was searched. The model abstains, and code sets the citation to that ABSENT record. If the question names a missing well or date, the router abstains with no model call at all.

**If they push:** Can the model abstain by habit? The verifier flags an abstention when a matching line is in the context, and the model is asked again.

---

## Q16. Why pin the provider, and what are the model settings?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> Haiku 5.5 and Sonnet 5.5 at temperature zero with a strict JSON shape. Requests are pinned to the Anthropic provider, because turning on require_parameters made every request return 404. If the pin is not available on someone's key, the run falls back to default routing for the same model and logs a warning.

**If they push:** Does it change results? The answers are checked by the same verifier either way.

---

## Q17. Will this scale to thousands of reports?

**Best presenter:** AI engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> Not tested. We have 32 reports. The design helps: the router filters by well and date before any model call, and contexts have a token cap. But archive-wide questions would need an index and better recall than we have now. For now the honest scale claim is the design, not a measurement.

**If they push:** What would you build first? A report index by well, date and field, so the context builder selects before it reads.

**Honest gap.** Best way to say it: We have not tested beyond 32 reports. The router and the token cap are built to keep the cost flat per question, but scale is the first thing the pilot would measure.

---

## Q18. How accurate is the page locator?

**Best presenter:** Petroleum engineer  |  **Group:** Technical

**Say it aloud first. Then check yourself:**

> 99.2 percent of table and narrative records are located to the exact row. 94.5 percent of the records the PDF prints. 78.8 percent of all records. The rest are XML only, such as wellhead elevation and the rig code, and are cited as XML only.

**If they push:** What are the unlocated ones? 31 rig aliases, 32 NPD aliases, 11 days-behind values blank in the PDF and 5 empty texts.

---

## Q19. What is the value for Heirs?

**Best presenter:** Petroleum engineer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> Well history is spread across daily reports, PDFs and exports. Engineers search by hand and cannot easily show where a number came from. This gives the figure with its page in seconds, and says plainly when the archive has no answer. That helps offset-well review, handover, abandonment work and data-integrity attestation.

**If they push:** Have you measured it at Heirs? No. The dashboard's calculator is illustrative and says so.

**Honest gap.** Best way to say it: Nobody has measured the time saved at Heirs yet. The calculator in the dashboard uses placeholder inputs. A pilot on a small set of real Heirs reports is how we would measure it.

---

## Q20. Who would use it, and how would they adopt it?

**Best presenter:** Product designer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> Drilling and well-integrity engineers first. They already ask these questions of old reports. The interface answers in plain language, shows the evidence page, and shows its confidence rule. The simplest adoption path is a pilot on one asset's reports. We would start with the people who feel the pain most, the engineers who handle well history every week.

**If they push:** What would make them trust it? Seeing the highlighted page, and seeing it say 'not in the archive' when that is true.

---

## Q21. What is the ROI?

**Best presenter:** Petroleum engineer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> We do not have a measured figure. Our costs are measured: about 2 cents a question, and 65 cents for all 32 questions. The benefit depends on how many engineer hours a week go to searching. The dashboard lets you enter your own numbers.

**If they push:** So what is the payback? We would only quote one after a pilot with Heirs' own hours and questions.

**Honest gap.** Best way to say it: We have no measured ROI. We have measured cost per question. We would estimate payback with Heirs' own search hours after a pilot.

---

## Q22. What are the main risks?

**Best presenter:** AI engineer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> A confident wrong answer that passes every check, for example a right number from the wrong field. Scanned documents we have not tested. Model or provider changes. And data leaving the building. We reduce the first with citations a human can open, and we log every stage.

**If they push:** What is the worst case? A wrong answer that looks verified. That is why every answer carries its evidence and a confidence rule.

---

## Q23. Who owns the data, and where does it go?

**Best presenter:** AI engineer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> The data stays the owner's. In our setup the evidence lines and the question go to the model provider through OpenRouter, and the API key lives only on the API host. For confidential Heirs data we would need a private or in-region deployment, which we have not built.

**If they push:** Can it run fully inside Heirs? The pipeline and the dashboard can run locally. The model call is the part that needs a decision.

**Honest gap.** Best way to say it: Right now the model call leaves the machine. Running fully inside Heirs needs a private model endpoint. We have not built or tested that, and we would settle it with Heirs' security team first.

---

## Q24. How would you deploy this inside Heirs?

**Best presenter:** AI engineer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> Three pieces: the pipeline and API, the data pack built from Heirs reports, and the dashboard. Today the API runs on Render and the site on Vercel for the demo, with an offline fallback that runs everything on a laptop. Inside Heirs it would run on their infrastructure behind their access control.

**If they push:** Is that done? No. We have the design and deployment files, not an Heirs install.

**Honest gap.** Best way to say it: We have not deployed inside Heirs. We have deployment files for Render and a local run for offline use. An Heirs install is the pilot's first task.

---

## Q25. What would it cost to run?

**Best presenter:** Product designer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> Measured: about 2 cents per question for the first 32, mostly escalation, and under a cent for a typical new question. A hard archive-wide question can reach about 5 cents. Hosting is separate. Cached answers cost nothing. For the cached 32 questions, 87 percent of the cost was escalation, so keeping the context clean is how we keep cost down.

**If they push:** Is there a price for Heirs? We have not set a price or a commercial model.

**Honest gap.** Best way to say it: We have measured running cost but have not set a price. A commercial model would come after the pilot shows value.

---

## Q26. Can it work with Heirs' own report formats?

**Best presenter:** Petroleum engineer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> The pipeline assumes WITSML XML plus PDF, as in Volve. Heirs reports may differ. The parser and the locator would need adapting, but the router, verifier, trace and dashboard do not depend on the format. The first pilot task would be to run the parser on a few real Heirs reports and see what breaks.

**If they push:** How long would adapting take? We have not estimated it. It depends on how structured Heirs' reports are.

**Honest gap.** Best way to say it: We have only built for the Volve format. Adapting the parser to Heirs reports is the main work of a pilot, and we have not estimated it yet.

---

## Q27. What about vendor lock-in?

**Best presenter:** AI engineer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> The model call goes through OpenRouter, so changing model is a setting. We benchmarked eight models and chose Haiku because it scored best on our cases at low cost. The cache key includes the model, so switching just misses the cache and re-asks.

**If they push:** Is the benchmark solid? It is small: 16 cases, one call each. Good for failure patterns and cost, not for fine ranking.

---

## Q28. How does this relate to regulatory data submissions?

**Best presenter:** Petroleum engineer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> Operators attest to the integrity of data they submit to the national data repository. Tracing each figure to a source page supports that. We have not tested any regulatory workflow, so this is a use case, not a claim. It is a use case we think fits, so please treat it as a direction rather than a tested workflow.

**If they push:** Which regulator? The dashboard names the NUPRC National Data Repository. Please confirm the wording with Heirs before quoting it.

**Honest gap.** Best way to say it: This is a use case we think fits, not something we have tested. The regulatory wording needs checking [VERIFY] before we rely on it in public.

---

## Q29. What do you need from Heirs to start?

**Best presenter:** Product designer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> A small set of real daily reports, a few engineers who will ask their own questions, and an answer on where the model call may run. We would measure accuracy on their questions, not ours. We would also want a named contact in Heirs who can say whether the answers are right.

**If they push:** How big a pilot? We suggest a small set of reports from one asset. We have not set a number.

---

## Q30. Why not just use a general chat assistant with the files uploaded?

**Best presenter:** Product designer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> Because it cannot prove its numbers and tends to answer when it should not. Here the evidence is chosen by code, the answer is checked by code, and a missing field gets an honest abstention. That difference is what scored in this contest.

**If they push:** Did you compare? Not head to head on these questions. Our benchmark compared models, not products.

**Honest gap.** Best way to say it: We did not run a head-to-head against a general chat assistant. We compared eight models inside our own pipeline.

---

## Q31. What would change in the interface for different roles?

**Best presenter:** Petroleum engineer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> Today there is one dashboard: answer, evidence page, trace, replay and a 3D view. A manager might want only the answer and the confidence rule. A data-integrity reviewer might want the trace and the evidence. We have not built role views. Today every viewer sees the same dashboard, including the trace and the cost view.

**If they push:** Is there access control? Not yet.

**Honest gap.** Best way to say it: We have not built role-based views or access control yet. It is on the roadmap after the pilot.

---

## Q32. What happens when a judge types a question live?

**Best presenter:** AI engineer  |  **Group:** Business

**Say it aloud first. Then check yourself:**

> The API checks length and rate limits, then answers from cache if the question is known. A vague question gets a clarification with examples and costs nothing. A new, specific question goes to the model, costs a few cents, and is bounded by a server budget and a limit on the key itself. If a limit is hit the interface says so.

**If they push:** What if the model is down? Cached questions still work. Others show a designed error state, never a guess.

---

## Q33. This is just prompt engineering.

**Best presenter:** AI engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> The prompt is 250 tokens and has no per-question rules. Most of the system is code: a parser, an evidence store with stable IDs, a router, a context builder, 13 verifier checks, a cache and a trace. The model only phrases what the code found. If you removed the model the code would still choose the evidence.

**If they push:** Show me. The verifier test rejects a right-looking number that is not in a cited record. That is not a prompt.

---

## Q34. You tuned it on the test.

**Best presenter:** AI engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> For the 40 unseen questions, yes, partly. We fixed failures after seeing them, going from 31 to 40, so 40 of 40 is not a clean estimate. The 32 official answers are unchanged by those fixes, and tests prove it. The independent test and the engineer's check are still pending.

**If they push:** Is there a clean number? A second set from a different seed scored 40 of 40 but used the same templates, and it is not saved in the repo. We would want a blind set.

**Honest gap.** Best way to say it: The 40 of 40 is tuned. We have not yet had an independent or blind test. We will say that on the slide and not claim more.

---

## Q35. What if the model is wrong?

**Best presenter:** AI engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> Then the verifier usually catches it. A number, unit, date or ID that is not in the cited records is rejected and sent back, first to the same model and then to a bigger one. If it still fails, the answer is kept but flagged, with confidence 0.2. A human can open the cited page in a minute.

**If they push:** And if it passes every check but is still wrong? That can happen, for example a right number from the wrong field. That is the limit.

---

## Q36. Why trust a small model?

**Best presenter:** AI engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> We do not trust it. We check it. On our cases it was also the most accurate, 16 of 16, and the most stable across repeats. It reads a few lines and writes a short answer. When the code objects, a bigger model is called.

**If they push:** Was 16 cases enough? No, it is small. It shows failure patterns and cost. The verifier is what carries the trust.

---

## Q37. What about scanned documents?

**Best presenter:** AI engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> Not in this archive. All 54 PDF pages have a text layer, so we did not need OCR. Real archives often have scans. That needs OCR and a way to locate text on the image, which we have not built. If a pilot archive is mostly scans, OCR quality becomes the main limit on accuracy, so we would test that first.

**If they push:** Would the verifier still work? Yes, if the OCR text becomes records with IDs. The quality of OCR would limit accuracy.

**Honest gap.** Best way to say it: We have not built OCR. This archive has a text layer on every page. Scanned reports are a known next step and the main risk for a pilot.

---

## Q38. How do I know your numbers are real?

**Best presenter:** AI engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> Each number on our slides names its source file. Costs come from the cache's recorded usage. The test counts come from a fresh run. Where something is not in the repository we mark it as to verify. You can rerun the notebook yourself in about a minute.

**If they push:** Can I see the cost record? Yes: submission/indexes/cost_summary.csv and the cost view in the dashboard.

---

## Q39. Only 32 reports. Is that enough to prove anything?

**Best presenter:** Petroleum engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> It proves the method on one real field with real traps, such as the day offset and XML-PDF conflicts. It does not prove performance on a whole company's archive. That is why we propose a pilot on Heirs' own reports. So we describe the result as a method that works on real data, and we ask for a pilot to measure scale.

**If they push:** What would you test first? Scale, other formats and scanned pages.

---

## Q40. Abstaining is easy. It just refuses.

**Best presenter:** AI engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> It abstained on 8 of 32 questions, and 2 of those are because the report does not exist. The other 6 ask for fields the archive does not have, like cost or weather. On the 40 unseen questions the system answered 33 and abstained on 7 expected absences. The verifier also flags an abstention when a matching line is in the context.

**If they push:** How do you know it did not refuse something answerable? The 'no missed evidence' check, and the unseen set had 33 answerable questions answered.

---

## Q41. Your verifier can be fooled.

**Best presenter:** AI engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> Yes, in one way: it checks that facts are supported, not that they are the right facts. A right number from a wrong field can pass. Our prompt says never to substitute a field, and the human can open the cited line, but we do not claim zero wrong answers.

**If they push:** What would reduce it? A larger blind test and a field-match check. Not built yet.

**Honest gap.** Best way to say it: The verifier checks support, not field choice. We have no blind measure of how often a right number from the wrong field gets through.

---

## Q42. Is the cost figure only a cache replay?

**Best presenter:** Petroleum engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> The cost is real usage recorded when the answers were generated: 130 calls, 65 cents. A rerun replays the cache and costs nothing. For new questions the cost is incurred live, and the API trace reports both numbers separately. Judges who type a new question see the incurred cost for that question in the trace.

**If they push:** Where is that shown? The cost view and the trace totals: generation cost and incurred cost.

---

## Q43. The benchmark is tiny.

**Best presenter:** AI engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> Agreed. It is 16 cases and one call per model. We use it for failure patterns and for cost, not to rank close models. The result that matters is that every model failed the date-window case, and that Haiku answered it. We also tested four cases three times each for stability, and Haiku was stable on all four.

**If they push:** Did you repeat it? Four cases three times for determinism. No model was bit-identical, so the cache is what makes reruns identical.

---

## Q44. Hard-coded answers? Special cases for the 32?

**Best presenter:** AI engineer  |  **Group:** Skeptical

**Say it aloud first. Then check yourself:**

> No. The repo rule is no hard-coded answers and no well list. Wells come from file names. Our generalisation set uses questions the code had never seen, with expected answers from separate code that reads the XML directly. Tests assert routes and contexts for the 32 are unchanged.

**If they push:** Can I grep for it? Yes. There are no question IDs in the pipeline code.

---

## Q45. Who did what on the team?

**Best presenter:** Product designer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> [VERIFY: confirm roles with the team before presenting.] The AI engineer built the pipeline, verifier and API. The petroleum engineer owned the data traps, the XML-PDF audit and the hand check. The product designer built the dashboard and this presentation. Please fill in the exact roles before the talk so the answer is specific and true.

**If they push:** Who owns the numbers? Each slide names its source file.

**Honest gap.** Best way to say it: Confirm the roles with the team before the talk. Say what each person did, in one sentence each.

---

## Q46. What went wrong along the way?

**Best presenter:** AI engineer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> Several things. The verifier first rejected correct answers because it read dates as digits, so we made dates and times whole tokens. Replies were cut off at 400 tokens, so we added a retry at 1,500. Requiring parameters made every call 404, so we pinned the provider. A bit with two nozzle blocks lost one in the parser. And one question routed to the wrong report, which we fixed in the router.

**If they push:** Which hurt most? The date-window trap. Larger models abstained on it, so a bigger model was not the fix.

---

## Q47. What did you learn?

**Best presenter:** AI engineer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> That checking beats trusting. The most useful code was the verifier and the trace. We also learned that the model was not the bottleneck: cost and accuracy were driven by what we put in the context. And that an honest abstention is worth building for.

**If they push:** What would you do differently? Build the blind test set first.

---

## Q48. What would you do with another week?

**Best presenter:** AI engineer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> Get the petroleum engineer's hand check of all 32 answers, build a blind test set, add a field-match check to the verifier, and test on a second report format. Then repeat the second pass test with a committed script. The key file for the hand check is already prepared, with a row for each of the 32 answers.

**If they push:** Is any of that started? The key file for the hand check is ready and empty.

**Honest gap.** Best way to say it: These are not done: the hand check, a blind test and the field-match check. The key file for the hand check exists with no verdicts yet.

---

## Q49. How did you decide the design?

**Best presenter:** Product designer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> The brief was trust. So the interface shows the evidence page first, the confidence rule beside the answer, and a trace that replays the real stages. Red is the brand colour only and never means failed. Abstentions use amber, verified uses green.

**If they push:** Is the trace real or animated? Real. Each event comes from the pipeline's actual calls.

---

## Q50. How did you check the claims in the pack?

**Best presenter:** AI engineer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> Every number was read from a repository file or a test run and is cited on the slide. Anything we could not find in the repository is marked to verify. We also reran the full tests and the offline rerun, and confirmed the predictions file has the same checksum.

**If they push:** Which claims are not in the repo? The local benchmark notes, the second pass test and the second 40-question run.

---

## Q51. How did you use AI tools to build this?

**Best presenter:** AI engineer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> [VERIFY: confirm how the team wants to describe this.] We used an AI coding assistant for much of the implementation and review, with the rules in a project file: no hard-coded answers, no secrets, tests for every change. Humans set the goals and checked the results.

**If they push:** Who is accountable? The team.

**Honest gap.** Best way to say it: Agree the wording with the team beforehand. Be plain that an AI assistant helped build it, and that the team set the rules and checked the results.

---

## Q52. What surprised you in the data?

**Best presenter:** Petroleum engineer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> That the PDF prints Y for tight well and HPHT in every report while the XML says 0. And that Western Atlas, a company name, is a wireline logging company and not mud logging. And that one 1980 report is a placeholder with a 1997 spud date.

**If they push:** Did you tell the organisers? We documented them in the data notes and handled them in code.

---

## Q53. What is the one thing you want the judges to remember?

**Best presenter:** Product designer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> That we answer with proof, and we say 'not in the archive' when it is not. Every answer carries the page it came from. Say it slowly, then stop. Let the demo carry the rest.

**If they push:** And one number? 32 reports, 24 answered, 8 honest abstentions, about 2 cents a question.

---

## Q54. What do you ask of the judges and of Heirs?

**Best presenter:** Petroleum engineer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> A pilot on a small set of real Heirs reports, scored on their engineers' own questions. And a decision on where the model call may run. The ask is small and concrete, which makes it easy to say yes to.

**If they push:** When? We would start as soon as a data sample is available.

---

## Q55. How do I run it myself?

**Best presenter:** AI engineer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> Open the notebook and run all cells. With no key it takes about 10 seconds and reproduces the 32 answers. Put OPENROUTER_KEY in a .env file to answer your own questions. The reviewer guide in the submission has the steps. If you have a key, the same notebook answers your own questions from a CSV file you point it at.

**If they push:** Where is it? submission/docs/REVIEWER_GUIDE.md.

---

## Q56. What is still pending?

**Best presenter:** AI engineer  |  **Group:** Process

**Say it aloud first. Then check yourself:**

> The petroleum engineer's hand check of the 32 answers, an independent blind test, and the committed second-pass test. Also a hosted deployment with real URLs. We say so on the slides. We list these on the limits slide so nobody has to find them for us.

**If they push:** Does it affect the score? The hidden test result is unknown until the organisers run it.

---
