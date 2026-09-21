#!/usr/bin/env python3
"""Measure how Jev's calibrated `choice` degrades as the option set grows.

Ground truth is unambiguous: state_b.txt is NS1-positive dengue with falling
platelets. Any honest model should say dengue at every option-set size. So any
drift in rank / probability / confidence as N grows is pure scaling damage,
not diagnostic difficulty.

Two padding regimes, because they test different things:
  EASY  non-febrile chronic conditions - implausible, should be ignored outright
  HARD  other acute febrile illnesses - genuinely confusable, the real test
"""
import json, math, os, pathlib, sys, time
import requests

HERE = pathlib.Path(__file__).parent
ENDPOINT = "https://api.openjev.sh/v1/systemone"

# --- the six real ones ----------------------------------------------------
BASE = {
    "dengue": "Dengue fever",
    "malaria": "Malaria",
    "typhoid": "Enteric fever / typhoid",
    "influenza": "Influenza or another common viral respiratory illness",
    "leptospirosis": "Leptospirosis",
    "scrub_typhus": "Scrub typhus or another rickettsial illness",
}

# --- HARD distractors: acute febrile illnesses, genuinely confusable ------
HARD = """chikungunya|Chikungunya
zika|Zika virus infection
yellow_fever|Yellow fever
west_nile|West Nile virus infection
japanese_encephalitis|Japanese encephalitis
hepatitis_a|Acute hepatitis A
hepatitis_e|Acute hepatitis E
brucellosis|Brucellosis
q_fever|Q fever
murine_typhus|Murine (endemic) typhus
epidemic_typhus|Epidemic louse-borne typhus
indian_tick_typhus|Indian tick typhus / spotted fever
relapsing_fever|Louse-borne relapsing fever
melioidosis|Melioidosis
plague|Plague
tularemia|Tularemia
anthrax|Anthrax
visceral_leishmaniasis|Visceral leishmaniasis (kala-azar)
african_trypanosomiasis|African trypanosomiasis
katayama_fever|Acute schistosomiasis (Katayama fever)
amoebic_liver_abscess|Amoebic liver abscess
paratyphoid|Paratyphoid fever
ehrlichiosis|Ehrlichiosis
anaplasmosis|Anaplasmosis
babesiosis|Babesiosis
covid19|COVID-19
adenovirus|Adenovirus infection
ebv_mono|EBV infectious mononucleosis
cmv_mono|CMV mononucleosis
hiv_seroconversion|Acute HIV seroconversion illness
measles|Measles
rubella|Rubella
parvovirus_b19|Parvovirus B19 infection
hantavirus|Hantavirus infection
lassa_fever|Lassa fever
ebola|Ebola virus disease
marburg|Marburg virus disease
cchf|Crimean-Congo haemorrhagic fever
rift_valley_fever|Rift Valley fever
oropouche|Oropouche virus fever
mayaro|Mayaro virus fever
sandfly_fever|Sandfly (phlebotomus) fever
ross_river|Ross River virus infection
sindbis|Sindbis virus infection
tuberculosis|Tuberculosis
bacterial_pneumonia|Community-acquired bacterial pneumonia
pyelonephritis|Acute pyelonephritis
bacterial_endocarditis|Infective endocarditis
bacterial_meningitis|Bacterial meningitis
viral_meningitis|Viral meningitis
cholangitis|Acute cholangitis
liver_abscess_pyogenic|Pyogenic liver abscess
septic_arthritis|Septic arthritis
osteomyelitis|Osteomyelitis
cellulitis|Cellulitis
deep_neck_abscess|Deep neck space abscess
appendicitis|Acute appendicitis
cholecystitis|Acute cholecystitis
diverticulitis|Diverticulitis
pelvic_inflammatory|Pelvic inflammatory disease
prostatitis|Acute bacterial prostatitis
puerperal_sepsis|Puerperal sepsis
rheumatic_fever|Acute rheumatic fever
kawasaki|Kawasaki disease
stills_disease|Adult-onset Still's disease
sle_flare|Systemic lupus erythematosus flare
vasculitis|Systemic vasculitis
sarcoidosis|Sarcoidosis
lymphoma_fever|Lymphoma presenting as fever
leukaemia_fever|Acute leukaemia presenting as fever
drug_fever|Drug fever
thyroid_storm|Thyroid storm
heat_stroke|Heat stroke
haemophagocytic|Haemophagocytic lymphohistiocytosis
toxoplasmosis|Toxoplasmosis
histoplasmosis|Histoplasmosis
coccidioidomycosis|Coccidioidomycosis
cryptococcosis|Cryptococcosis
pneumocystis|Pneumocystis pneumonia
strongyloides_hyper|Strongyloides hyperinfection
trichinellosis|Trichinellosis
filariasis_acute|Acute lymphatic filariasis
loiasis|Loiasis
onchocerciasis|Onchocerciasis
leprosy_reaction|Leprosy type 2 reaction
melioid_relapse|Relapsed melioidosis
psittacosis|Psittacosis
legionella|Legionnaires disease
mycoplasma|Mycoplasma pneumonia
chlamydia_pneumo|Chlamydophila pneumoniae infection
rat_bite_fever|Rat-bite fever
cat_scratch|Cat-scratch disease
lyme_disease|Lyme disease
tick_borne_encephalitis|Tick-borne encephalitis
colorado_tick_fever|Colorado tick fever
rocky_mountain_spotted|Rocky Mountain spotted fever
boutonneuse|Mediterranean spotted fever
scrub_reinfection|Scrub typhus reinfection
enteroviral_fever|Enteroviral febrile illness
rotavirus|Rotavirus gastroenteritis
norovirus|Norovirus gastroenteritis
campylobacter|Campylobacter enteritis
shigellosis|Shigellosis
cholera|Cholera
giardiasis|Giardiasis
amoebic_colitis|Amoebic colitis
yersiniosis|Yersiniosis
listeriosis|Listeriosis
toxic_shock|Toxic shock syndrome
scarlet_fever|Scarlet fever
diphtheria|Diphtheria
pertussis|Pertussis
tetanus|Tetanus
rabies|Rabies
polio|Poliomyelitis
mumps|Mumps
varicella|Varicella (chickenpox)
herpes_zoster|Herpes zoster
hsv_encephalitis|HSV encephalitis
influenza_h5n1|Avian influenza H5N1
mers|MERS coronavirus infection
sars|SARS coronavirus infection
nipah|Nipah virus infection
monkeypox|Mpox"""

# --- EASY distractors: non-febrile, implausible for this state ------------
EASY = """osteoarthritis|Osteoarthritis
glaucoma|Glaucoma
cataract|Cataract
psoriasis|Psoriasis
atopic_eczema|Atopic eczema
gerd|Gastro-oesophageal reflux disease
ibs|Irritable bowel syndrome
hypothyroidism|Hypothyroidism
type2_diabetes|Type 2 diabetes mellitus
hypertension|Essential hypertension
migraine|Migraine
carpal_tunnel|Carpal tunnel syndrome
sciatica|Sciatica
gout|Gout
kidney_stones|Nephrolithiasis
bph|Benign prostatic hyperplasia
endometriosis|Endometriosis
iron_deficiency|Iron deficiency anaemia
vitamin_d_deficiency|Vitamin D deficiency
copd_stable|Stable COPD
asthma_stable|Stable asthma
allergic_rhinitis|Allergic rhinitis
sinusitis_chronic|Chronic sinusitis
otitis_externa|Otitis externa
tinnitus|Tinnitus
vertigo_bppv|Benign paroxysmal positional vertigo
insomnia|Chronic insomnia
depression|Major depressive disorder
anxiety_gad|Generalised anxiety disorder
adhd|Attention deficit hyperactivity disorder
autism|Autism spectrum condition
dyslexia|Dyslexia
epilepsy_stable|Well-controlled epilepsy
parkinsons|Parkinson disease
alzheimers|Alzheimer disease
multiple_sclerosis|Multiple sclerosis
myasthenia|Myasthenia gravis
peripheral_neuropathy|Diabetic peripheral neuropathy
varicose_veins|Varicose veins
haemorrhoids|Haemorrhoids
anal_fissure|Anal fissure
inguinal_hernia|Inguinal hernia
umbilical_hernia|Umbilical hernia
gallstones_silent|Asymptomatic gallstones
fatty_liver|Non-alcoholic fatty liver disease
coeliac|Coeliac disease
lactose_intolerance|Lactose intolerance
peptic_ulcer|Peptic ulcer disease
gastritis_chronic|Chronic gastritis
constipation_chronic|Chronic constipation
obesity|Obesity
dyslipidaemia|Dyslipidaemia
osteoporosis|Osteoporosis
vitiligo|Vitiligo
alopecia_areata|Alopecia areata
acne|Acne vulgaris
rosacea|Rosacea
seborrhoeic_dermatitis|Seborrhoeic dermatitis
onychomycosis|Onychomycosis
plantar_fasciitis|Plantar fasciitis
frozen_shoulder|Adhesive capsulitis
tennis_elbow|Lateral epicondylitis
rotator_cuff|Rotator cuff tendinopathy
scoliosis|Scoliosis
flat_feet|Pes planus
myopia|Myopia
astigmatism|Astigmatism
presbyopia|Presbyopia
dry_eye|Dry eye syndrome
blepharitis|Blepharitis
gingivitis|Gingivitis
dental_caries|Dental caries
bruxism|Bruxism
tmj_dysfunction|Temporomandibular joint dysfunction
snoring|Primary snoring
sleep_apnoea|Obstructive sleep apnoea
restless_legs|Restless legs syndrome
raynauds|Raynaud phenomenon
chronic_fatigue|Chronic fatigue syndrome
fibromyalgia|Fibromyalgia"""

def parse(block):
    out = {}
    for line in block.strip().splitlines():
        k, _, v = line.partition("|")
        out[k.strip()] = v.strip()
    return out

HARD_D, EASY_D = parse(HARD), parse(EASY)

def load_key():
    key = os.environ.get("OPENJEV_API_KEY", "").strip()
    if key:
        return key
    for line in (HERE / ".env").read_text().splitlines():
        if line.strip().startswith("OPENJEV_API_KEY="):
            return line.partition("=")[2].strip().strip("'\"")
    return ""

KEY = load_key()
state = (HERE / "state_b.txt").read_text()

def build(n, regime):
    """Base six + 'other' + distractors until the map has n entries."""
    opts = dict(BASE)
    if regime == "hard":
        pool = list(HARD_D.items()) + list(EASY_D.items())
    elif regime == "easy":
        pool = list(EASY_D.items()) + list(HARD_D.items())
    else:
        pool = [x for pair in zip(list(HARD_D.items()), list(EASY_D.items())) for x in pair]
    i = 0
    while len(opts) < n - 1 and i < len(pool):
        k, v = pool[i]; i += 1
        opts.setdefault(k, v)
    # synthesise filler if the pool runs dry, so we can push past its size
    j = 0
    while len(opts) < n - 1:
        j += 1
        opts[f"other_condition_{j:04d}"] = f"Other specified medical condition {j}"
    opts["other"] = "None of the listed conditions, or the data does not point to any one of them"
    return opts

def entropy(p):
    return -sum(v * math.log2(v) for v in p.values() if v > 0)

def probe(n, regime):
    opts = build(n, regime)
    q = {"primary_diagnosis": {
            "type": "choice",
            "instructions": "Based only on the information in the state, which single condition best explains this patient's illness?",
            "criteria": opts}}
    t0 = time.time()
    try:
        r = requests.post(ENDPOINT,
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
            json={"model": "openjev", "state": state, "questions": q}, timeout=180)
    except Exception as e:
        return {"n": len(opts), "regime": regime, "error": f"{type(e).__name__}: {e}"}
    dt = time.time() - t0
    if r.status_code != 200:
        return {"n": len(opts), "regime": regime, "error": f"HTTP {r.status_code}: {r.text[:180]}"}
    a = r.json()["answers"]["primary_diagnosis"]
    probs = a["probabilities"]
    ranked = sorted(probs.items(), key=lambda x: -x[1])
    rank = next((i + 1 for i, (k, _) in enumerate(ranked) if k == "dengue"), None)
    return {"n": len(opts), "regime": regime, "choice": a["choice"],
            "conf": a["confidence"], "p_dengue": probs.get("dengue", 0.0),
            "rank_dengue": rank, "entropy": entropy(probs),
            "max_entropy": math.log2(len(probs)),
            "returned": len(probs), "top3": ranked[:3],
            "in_tok": r.json()["usage"]["input_tokens"], "secs": round(dt, 1)}

PLAN = [(7,"hard"),(25,"easy"),(25,"hard"),(50,"hard"),(100,"hard"),
        (200,"mixed"),(400,"mixed"),(800,"mixed"),(1600,"mixed")]

results = []
for n, regime in PLAN:
    res = probe(n, regime)
    results.append(res)
    if "error" in res:
        print(f"n={res['n']:5d} {regime:6s}  ERROR  {res['error']}", flush=True)
        if "HTTP 4" in res["error"]:
            break
    else:
        print(f"n={res['n']:5d} {regime:6s}  choice={res['choice']:22s} "
              f"conf={res['conf']:.3f} p_dengue={res['p_dengue']:.3f} "
              f"rank={res['rank_dengue']} H={res['entropy']:.2f}/{res['max_entropy']:.2f} "
              f"tok={res['in_tok']} {res['secs']}s", flush=True)

(HERE / "scaling_results.json").write_text(json.dumps(results, indent=2))
print("\nsaved scaling_results.json")
