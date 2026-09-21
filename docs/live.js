/* ============================================================
   Live consultation — runs the triage loop in the browser.

   SAFETY MODEL
   - The visitor supplies their own OpenJEV key. It is held in
     sessionStorage (cleared when the tab closes), never sent
     anywhere except api.openjev.sh, and never committed.
   - Symptom text goes to the OpenJEV API only.
   - No phrasing LLM client-side: probes are shown verbatim, so
     no second credential is needed and no model can reword a
     clinical question unsupervised.
   - Hard stop: this is a demo, not advice. Consent gate first.
   ============================================================ */

/* Demo key, deliberately public: this is a static site with no server to
   hide a credential. Visitors need not bring their own. Rotate at
   openjev.sh if it is abused. A visitor-supplied key overrides it. */
const DEMO_KEY = "oj_live.user_3JdHzlgTpOzAGjJRFhXhwXQhtOe.ea5dd9772784dfc8d137a2a9d2e3b1b3";
const API = "https://api.openjev.sh/v1/systemone";
const LIMITS = { rounds: 8, dominance: 0.97, minGain: 0.02, outside: 0.60, floor: 0.02 };

let BANK = null;
let S = null;   // live session state

/* ---------- maths (mirrors triage_loop.py) ---------- */
const H = d => -Object.values(d).reduce((a, p) => p > 1e-12 ? a + p * Math.log2(p) : a, 0);

function temper(d, floor = LIMITS.floor) {
  const n = Object.keys(d).length, out = {};
  for (const k in d) out[k] = (1 - floor * n) * d[k] + floor;
  return out;
}
function lk(f, dis) {
  if (f.supports && dis in f.supports) return f.supports[dis];
  if (f.against && dis in f.against) return f.against[dis];
  return 0.15;
}
function post(prior, f, present) {
  const o = {};
  let t = 0;
  for (const d in prior) { const l = lk(f, d); o[d] = prior[d] * (present ? l : 1 - l); t += o[d]; }
  if (t <= 0) return { ...prior };
  for (const d in o) o[d] /= t;
  return o;
}
function eig(prior, f, p) {
  return H(prior) - (p * H(post(prior, f, true)) + (1 - p) * H(post(prior, f, false)));
}

/* ---------- API ---------- */
async function jev(state, questions) {
  const res = await fetch(API, {
    method: "POST",
    headers: { Authorization: "Bearer " + S.key, "Content-Type": "application/json" },
    body: JSON.stringify({ model: "openjev", state, questions })
  });
  if (res.status === 401) throw new Error("Invalid API key — check it at openjev.sh");
  if (res.status === 422) throw new Error("The API rejected the request body (422).");
  if (res.status === 503) throw new Error("OpenJEV is temporarily unavailable (503). Try again shortly.");
  if (!res.ok) throw new Error("API error " + res.status);
  const d = await res.json();
  const u = d.usage || {};
  S.usage.calls++;
  S.usage.cost += u.cost || 0;
  S.usage.in += u.input_tokens || 0;
  S.usage.out += u.output_tokens || 0;
  return d.answers;
}

function roundQuestions(remaining) {
  const crit = {};
  BANK.diseases.forEach(d => crit[d] = d.replace(/_/g, " "));
  crit.other = "None of the listed conditions explains this illness";
  const q = {
    primary_diagnosis: {
      type: "choice",
      instructions: "Based only on the information in the state, which condition best explains this patient's illness? Answer 'other' if none of the listed conditions fits.",
      criteria: crit
    },
    outside_differential: {
      type: "noul",
      instructions: "Does this illness most likely lie OUTSIDE the differential of acute tropical febrile illness (dengue, malaria, typhoid, leptospirosis, scrub typhus, influenza)?",
      criteria: {
        true: "Points to a condition outside this differential, such as an autoimmune, haematological, malignant or surgical cause",
        false: "Fits within acute tropical febrile illness"
      }
    },
    evidence_sufficient: {
      type: "noul",
      instructions: "Is the information in the state sufficient to commit to a single diagnosis without gathering any further history or test?",
      criteria: { true: "Decisive enough to name one diagnosis", false: "Still compatible with more than one condition" }
    },
    red_flags: {
      type: "noul",
      instructions: "Does the state describe any feature requiring urgent, same-day medical assessment?",
      criteria: {
        true: "Features such as breathlessness, confusion, persistent vomiting, bleeding, severe dehydration, chest pain or reduced urine output",
        false: "No urgent feature described"
      }
    }
  };
  remaining.forEach(f => {
    q["f_" + f.id] = {
      type: "noul",
      instructions: "Based on the state, is this true of the patient: " + f.probe,
      criteria: { true: "The state indicates this is present", false: "The state indicates this is absent, or does not say" }
    };
  });
  return q;
}

/* ---------- UI helpers ---------- */
const $ = s => document.querySelector(s);
const escq = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pctf = n => (n * 100).toFixed(0) + "%";

function diffBars(probs, host) {
  const sorted = Object.entries(probs).sort((a, b) => b[1] - a[1]);
  host.innerHTML = sorted.map(([k, v], i) =>
    `<div class="bar"><span class="nm">${escq(k)}</span>
      <span class="track"><span class="fill ${k === "other" ? "other" : i === 0 ? "top" : ""}" style="width:${v * 100}%"></span></span>
      <span class="pc">${pctf(v)}</span></div>`).join("");
}

function setBusy(on, msg) {
  $("#lv-busy").style.display = on ? "flex" : "none";
  if (msg) $("#lv-busy-txt").textContent = msg;
}
function showErr(m) {
  $("#lv-err").style.display = "block";
  $("#lv-err").textContent = m;
}
function clearErr() { $("#lv-err").style.display = "none"; }

/* ---------- flow ---------- */
async function startConsult() {
  clearErr();
  const key = $("#lv-key").value.trim() || DEMO_KEY;
  const sym = $("#lv-symptoms").value.trim();
  if (!key) return showErr("No API key available.");
  if (sym.length < 15) return showErr("Describe the symptoms in a little more detail (at least a sentence).");

  const age = $("#lv-age").value.trim();
  const sex = $("#lv-sex").value;
  const days = $("#lv-days").value.trim();
  const travel = $("#lv-travel").value.trim();

  let state = "Patient self-reported intake.\n";
  if (age) state += `Age: ${age}\n`;
  if (sex) state += `Sex: ${sex}\n`;
  if (days) state += `Duration of illness: ${days} days\n`;
  state += `\nReported symptoms:\n${sym}\n`;
  if (travel) state += `\nRecent travel or exposure:\n${travel}\n`;
  state += "\nNo examination has been performed. No investigations have been done.\n";

  S = {
    key, state, remaining: [...BANK.findings], asked: [], round: 0,
    usage: { calls: 0, cost: 0, in: 0, out: 0 }, stop: null
  };
  if (key !== DEMO_KEY) sessionStorage.setItem("ojk", key);

  $("#lv-intake").style.display = "none";
  $("#lv-run").style.display = "block";
  await nextRound();
}

async function nextRound() {
  if (S.round >= LIMITS.rounds) return finish("Question limit reached (" + LIMITS.rounds + ").");
  S.round++;
  setBusy(true, "Ranking " + S.remaining.length + " findings by information gain…");
  let ans;
  try {
    ans = await jev(S.state, roundQuestions(S.remaining));
  } catch (e) {
    setBusy(false);
    return showErr(e.message);
  }
  setBusy(false);

  const dx = ans.primary_diagnosis;
  const prior = temper(dx.probabilities);
  const outside = ans.outside_differential.noul;
  const suff = ans.evidence_sufficient.noul;
  const red = ans.red_flags.noul;
  const lead = Math.max(...Object.values(dx.probabilities));

  S.lastDx = dx; S.lastRed = red;
  diffBars(dx.probabilities, $("#lv-diff"));
  $("#lv-meta").innerHTML =
    `<span class="chip">round <b>${S.round}</b></span>
     <span class="chip">entropy <b>${H(prior).toFixed(2)} bits</b></span>
     <span class="chip">sufficient <b>${suff.toFixed(2)}</b></span>
     <span class="chip">outside <b>${outside.toFixed(2)}</b></span>
     <span class="chip">spent <b>$${S.usage.cost.toFixed(5)}</b></span>`;

  if (red > 0.6) return finish("URGENT features reported — stopping and advising same-day medical care.", true);
  if (outside >= LIMITS.outside || dx.choice === "other")
    return finish("This presentation falls outside the demo's six-illness differential, so the question bank cannot help. Escalate to a clinician.");
  if (suff >= 0.80) return finish("The model reports the evidence is sufficient (" + suff.toFixed(2) + ").");
  if (lead >= LIMITS.dominance) return finish("One condition now dominates at " + lead.toFixed(2) + " — history alone cannot go further; a laboratory test is needed.");
  if (!S.remaining.length) return finish("Question bank exhausted.");

  const scored = S.remaining
    .map(f => ({ f, g: eig(prior, f, ans["f_" + f.id].noul) }))
    .sort((a, b) => b.g - a.g);
  if (scored[0].g < LIMITS.minGain)
    return finish("No remaining question is worth asking (best gain " + scored[0].g.toFixed(3) + " bits).");

  S.pick = scored[0];
  $("#lv-q").textContent = scored[0].f.probe;
  $("#lv-gain").textContent = scored[0].g.toFixed(3) + " bits";
  $("#lv-cands").innerHTML = scored.slice(0, 5).map((c, i) => {
    const mx = Math.max(scored[0].g, 0.001);
    return `<div class="crow ${i === 0 ? "win" : ""}"><span class="cn">${escq(c.f.id)}</span>
      <span class="ctrack"><span class="cfill" style="width:${c.g / mx * 100}%"></span></span>
      <span class="cv">${c.g.toFixed(3)}</span></div>`;
  }).join("");
  $("#lv-ask").style.display = "block";
}

async function answer(kind) {
  const f = S.pick.f;
  const reply = { yes: "Yes, that is true.", no: "No, nothing like that.", unsure: "I am not sure." }[kind];
  $("#lv-ask").style.display = "none";
  S.state += `\nFollow-up history (round ${S.round}):\n- Asked: ${f.probe}\n- Patient replied: ${reply}\n`;
  S.asked.push({ id: f.id, kind, probe: f.probe, gain: S.pick.g });
  S.remaining = S.remaining.filter(x => x.id !== f.id);
  renderLog();
  await nextRound();
}

function renderLog() {
  $("#lv-log").innerHTML = S.asked.map((a, i) =>
    `<div class="logrow"><span class="lgn">${i + 1}</span>
      <span class="lgq">${escq(a.probe)}</span>
      <span class="verd ${a.kind === "yes" ? "present" : a.kind === "no" ? "absent" : "uncertain"}">${a.kind}</span></div>`).join("");
}

async function finish(reason, urgent) {
  $("#lv-ask").style.display = "none";
  setBusy(true, "Preparing the summary…");
  let fin = null;
  try {
    fin = await jev(S.state, {
      primary_diagnosis: {
        type: "choice",
        instructions: "Which condition best explains this patient's illness, given everything in the state? Answer 'other' if none fits.",
        criteria: { ...Object.fromEntries(BANK.diseases.map(d => [d, d.replace(/_/g, " ")])), other: "None of the listed conditions fits" }
      },
      care_urgency: {
        type: "score",
        instructions: "How urgently does this patient need to be seen?",
        criteria: ["Home care and review in a few days", "Outpatient review within 24 hours", "Same day assessment", "Immediate hospital assessment"]
      },
      safe_to_act_without_clinician: {
        type: "noul",
        instructions: "Would it be safe for an automated system to act on this assessment without a qualified clinician reviewing it?",
        criteria: { true: "Low risk and unambiguous", false: "A clinician must review" }
      }
    });
  } catch (e) { showErr(e.message); }
  setBusy(false);

  const dx = fin ? fin.primary_diagnosis : S.lastDx;
  const urg = fin ? fin.care_urgency.score : null;
  const safe = fin ? fin.safe_to_act_without_clinician.noul : null;

  $("#lv-run").style.display = "none";
  $("#lv-done").style.display = "block";
  $("#lv-log2").innerHTML = S.asked.length
    ? S.asked.map((a, i) =>
        `<div class="logrow"><span class="lgn">${i + 1}</span>
          <span class="lgq">${escq(a.probe)}</span>
          <span class="verd ${a.kind === "yes" ? "present" : a.kind === "no" ? "absent" : "uncertain"}">${a.kind}</span></div>`).join("")
    : '<p style="color:var(--dim);font-size:13px">No questions were asked — the model stopped immediately.</p>';
  if (dx) diffBars(dx.probabilities, $("#lv-final-diff"));

  $("#lv-verdict").innerHTML = `
    <div class="verdict">
      <span class="dx" style="color:${dx && dx.choice === "other" ? "var(--warn)" : "var(--ok)"}">${dx ? escq(dx.choice) : "—"}</span>
      <span class="cf">${dx ? "leading hypothesis · confidence " + dx.confidence.toFixed(2) : ""}</span>
    </div>
    <div class="reason${urgent ? " esc" : ""}">${escq(reason)}</div>
    <div style="margin-top:14px;display:flex;gap:9px;flex-wrap:wrap">
      ${urg !== null ? `<span class="chip">urgency <b>${urg.toFixed(2)}/3</b></span>` : ""}
      ${safe !== null ? `<span class="chip">safe without clinician <b>${safe.toFixed(2)}</b></span>` : ""}
      <span class="chip">questions <b>${S.asked.length}</b></span>
      <span class="chip">cost <b>$${S.usage.cost.toFixed(5)}</b></span>
      <span class="chip">API calls <b>${S.usage.calls}</b></span>
    </div>`;

  $("#lv-advice").innerHTML = urgent
    ? `<strong>You reported features that need urgent attention.</strong> Contact a doctor or go to an
       emergency department now. Do not wait for anything on this page.`
    : `<strong>This is not a diagnosis.</strong> It is a demonstration of how a calibrated decision model
       chooses questions. Take these symptoms to a qualified clinician — the model itself rated acting
       without one at ${safe !== null ? safe.toFixed(2) : "≈0.03"} on a 0–1 scale.`;
}

function resetLive() {
  $("#lv-done").style.display = "none";
  $("#lv-run").style.display = "none";
  $("#lv-intake").style.display = "block";
  $("#lv-log").innerHTML = "";
  clearErr();
  S = null;
}

/* ---------- boot ---------- */
async function initLive() {
  try {
    BANK = await (await fetch("data/findings_bank.json", { cache: "no-store" })).json();
  } catch (e) {
    $("#lv-intake").innerHTML = '<div class="err">Could not load the findings bank.</div>';
    return;
  }
  const saved = sessionStorage.getItem("ojk");
  if (saved) $("#lv-key").value = saved;

  $("#lv-start").onclick = startConsult;
  $("#lv-yes").onclick = () => answer("yes");
  $("#lv-no").onclick = () => answer("no");
  $("#lv-unsure").onclick = () => answer("unsure");
  $("#lv-stop").onclick = () => finish("You ended the consultation.");
  $("#lv-again").onclick = resetLive;

  document.querySelectorAll(".sym-chip").forEach(c => c.onclick = () => {
    const ta = $("#lv-symptoms");
    const t = c.dataset.t;
    ta.value = ta.value.trim() ? ta.value.trim().replace(/\.$/, "") + ". " + t : t;
    c.classList.add("used");
    ta.focus();
  });

  $("#consent-go").onclick = () => {
    $("#consent").style.display = "none";
    $("#lv-body").style.display = "block";
  };
}
