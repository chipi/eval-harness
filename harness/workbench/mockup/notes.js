// The mockup's own notes: what it only pretends, said on the screen where it happens. workbench.js (shared with the live
// Workbench) asks for a note by its key and draws none when nothing answers, so the shipped file carries no mockup text.
// workflows.js and round5.js pass their notes' text to WB.note directly.
(() => {
  const WB = window.WB;
  const { esc } = WB;
  WB.note = (text) => `<p class="mocknote">mockup: ${esc(text)}</p>`;
  const NOTES = {
    "first-visit": (goals) => `this project really has ${goals} goals; the mockup starts empty to show the first visit.`,
    "goal-extra": () => "the CNN goal's own extra measure is rouge1; margin and tie-break defaults are the goal schema's.",
    "source-paths": () => "round 1 mocks the Hugging Face path only; the others take the same four parts (where from, what's in it, its fields, name it).",
    "hf-answer-column": () => "the huggingface source takes the item's column and its id today; taking the answer column too is new (UXS-005).",
    "pretend-job": () => "a pretend job; the real one runs on the server and survives closing the page.",
    "profile-only-cnn": () => "round 1 reads only cnn_dailymail_200's profile and items; choose it in step 2 to see this part.",
    "ml-no-prompt": () => "ML models (BART) take no prompt; their arms carry their own settings.",
    "no-cnn-run": () => "this model has no CNN run, so the mockup has no real replies for it.",
    "r1-replies": () => "the replies, their cost and timing are the r1 run's real first three items.",
    "rounds-real": (tab) => (tab === "r5" ? "r1 to r3 are this project's real rounds; r4 and r5 are the ones this walk-through opens." : "r1 to r3 are this project's real rounds; r4 is the one this walk-through opens."),
    "r4-rows": () => "the rows are the project's Linux re-runs of 2026-09-30, standing in for r4's runs (a run counts in a round only when its config names it); bart_l's is the re-run the pair tests compared against, where evh round-list would read its r1 run. A clone has no run, so no scores.",
    "r5-stops": () => "this project has no runs past r4's re-runs, so this walk-through stops at r5's question; its arms, run and results would follow as in r4.",
    "link-out": () => "a link out of the Workbench; not part of the mockup.",
  };
  WB.mockNote = (key, ...a) => WB.note(NOTES[key](...a));
  document.querySelector("#mocknotes")?.addEventListener("change", (e) => document.body.classList.toggle("mocknotes-off", !e.target.checked));
})();
